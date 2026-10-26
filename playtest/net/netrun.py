"""Launch a headless netplay Session on localhost and collect what every machine saw.

The Host and each client are separate headless game processes, each in its own
working dir with its own ``--input`` script for its local Player. Every client
talks to the Host through its own :mod:`proxy` link (latency, jitter, loss).

    r = run(binary, out_dir, save="05-Twoson", host_script=boot_then(random_play(1, 3000)),
            clients=[Peer("p2", random_play(2, 3000))], net=Net(100, 30, 0.02), input_delay=20,
            end_frame=3000)
    r.check_agreement()      # raises unless every pair of machines hashed equal on shared frames

Each machine prints ``NETSYNC f=F hash=H PLAYERS ...`` every 60 frames and ``NET ...``
event lines (net/session.c); :class:`Result` parses them. Headless runs are
uncapped, so the frame rate is bounded by the round trip: D frames of input delay
buy about D frames per round trip. Everything is killed at ``timeout`` seconds of
wall time, or when the run ends; no process is left behind.

Command line (a quick look): ``python playtest/net/netrun.py --players 2 --frames 3000``.
"""

import argparse
import contextlib
import os
import queue
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proxy import Proxy  # noqa: E402

PLAYTEST = Path(__file__).resolve().parent.parent
SAVES = PLAYTEST / "saves"
# Title screen -> file select -> file 1 -> Continue, then wait for control (playtest/coop/lib.py BOOT)
BOOT = "300 -\n1 START\n200 -\n1 A\n120 -\n1 A\n120 -\n1 A\nuntil idle 900\n"
SANITIZER = re.compile(r"runtime error:|ERROR: AddressSanitizer|ERROR: LeakSanitizer")
SYNC = re.compile(r"NETSYNC f=(\d+) hash=([0-9a-f]+) (PLAYERS .*)")
DIRS = ["UP", "DOWN", "LEFT", "RIGHT", "UP+LEFT", "UP+RIGHT", "DOWN+LEFT", "DOWN+RIGHT"]


class NetError(Exception):
    """A netplay check failed."""


def random_play(seed, frames, menus=True, players=1, a_rate=0.05):
    """An input script: a seeded random walk with occasional A/B presses, ``frames`` long, then idle.

    With ``players`` > 1 (several local Players at one machine), P2.. walk too: their
    direction is a sticky hold that changes now and then while P1's commands run.
    ``a_rate``: chance per step of a menu visit: A (on the overworld it opens the pause
    menu and takes the co-op input focus), a cursor move, then B to back out.
    """
    rng = random.Random(seed)  # noqa: S311 - test input, not crypto
    out, t = [], 0
    while t < frames:
        for k in range(2, players + 1):
            if rng.random() < 0.3:
                out.append(f"hold P{k} {rng.choice(DIRS)}" if rng.random() < 0.8 else f"release P{k}")
        r = rng.random()
        if menus and r < a_rate:
            # Open a menu (on the overworld: the pause menu, taking the input focus),
            # move the cursor, then back out with B so the focus moves on again
            out += ["press A", "wait 20", f"press {rng.choice(['UP', 'DOWN', 'LEFT', 'RIGHT'])}", "press B 5"]
            t += 6 + 20 + 6 + 30
        elif menus and r < a_rate + 0.05:
            out.append("press B")
            t += 6
        elif r < 0.25:
            k = rng.randint(10, 60)
            out.append(f"wait {k}")
            t += k
        else:
            k = rng.randint(10, 90)
            out.append(f"{k} {rng.choice(DIRS)}")
            t += k
    out.append("wait 1000000")  # never run out: the Session ends with --net-end-frame
    return "\n".join(out) + "\n"


def boot_then(script):
    """Boot file 1 of the save (Continue), then play ``script``."""
    return BOOT + script


def free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@dataclass
class Net:
    """Network conditions on every client's link (latency is one way, per direction)."""

    latency: float = 0.0
    jitter: float = 0.0
    loss: float = 0.0
    seed: int = 0


@dataclass
class Peer:
    """One client machine."""

    name: str
    script: str
    start_after: int | None = None  # start once the Host has hashed this frame
    start_on: str | None = None  # ... or once a Host line matches this regex (after start_after)
    kill_after: int | None = None  # SIGKILL it (no goodbye) once it has hashed this frame
    env: dict = field(default_factory=dict)
    local_players: int = 1  # Players at this machine (--local-players)


@dataclass
class Machine:
    """What one process printed."""

    name: str
    dir: Path
    rc: int | None = None
    syncs: dict = field(default_factory=dict)  # frame -> (hash, PLAYERS line)
    events: list = field(default_factory=list)  # "NET ..." lines, in order
    killed: bool = False
    stderr: str = ""

    @property
    def last_frame(self):
        return max(self.syncs, default=-1)

    def took_focus(self, player):
        """True if some hash point shows ``player`` holding the overworld input lock (it opened a menu)."""
        return any(f"focus=P{player} locked" in pl for _, pl in self.syncs.values())

    def event(self, pattern):
        """The first NET line matching ``pattern`` (regex), or None."""
        rx = re.compile(pattern)
        return next((e for e in self.events if rx.search(e)), None)

    def sanitizer_report(self):
        m = SANITIZER.search(self.stderr)
        return self.stderr[m.start() : self.stderr.find("\n", m.start())] if m else None


@dataclass
class Result:
    machines: list
    wall: float
    proxy_stats: dict
    timed_out: bool

    def by_name(self, name):
        return next(m for m in self.machines if m.name == name)

    @property
    def desyncs(self):
        return sum(1 for m in self.machines for e in m.events if e.startswith("NET DESYNC"))

    def agreement(self, a, b):
        """(frames both hashed, frames where hash or PLAYERS differ)."""
        common = sorted(set(a.syncs) & set(b.syncs))
        bad = [f for f in common if a.syncs[f] != b.syncs[f]]
        return common, bad

    def check_agreement(self, min_common=1):
        """Every client agrees with the Host on every frame both hashed (at least ``min_common``)."""
        host = self.machines[0]
        for m in self.machines[1:]:
            common, bad = self.agreement(host, m)
            if bad:
                f = bad[0]
                raise NetError(f"{m.name} disagrees with the host at frame {f}: {host.syncs[f]} vs {m.syncs[f]}")
            if len(common) < min_common:
                raise NetError(f"{m.name} shared only {len(common)} hash points with the host (< {min_common})")

    def check_clean(self, end_frame):
        """No desync, no sanitizer report, and every machine not killed ran to ``end_frame`` and exited 0."""
        if self.timed_out:
            raise NetError(f"timed out after {self.wall:.0f}s; frames reached {self.summary()}")
        if self.desyncs:
            raise NetError(f"{self.desyncs} desync report(s): {self.summary()}")
        for m in self.machines:
            rep = m.sanitizer_report()
            if rep and os.environ.get("EB_COOP_SANITIZE") == "1":
                raise NetError(f"{m.name}: sanitizer report: {rep} (see {m.dir / 'stderr.txt'})")
            if m.killed:
                continue
            if m.rc != 0 or not m.event(rf"^NET END f={end_frame}$"):
                raise NetError(f"{m.name} did not end cleanly at frame {end_frame}: rc={m.rc}, {m.events[-3:]}")

    def summary(self):
        return ", ".join(f"{m.name}: f={m.last_frame} rc={m.rc}" for m in self.machines)


def _reader(proc, name, q, log):
    for ln in proc.stdout:
        log.write(ln)
        q.put((name, ln.rstrip("\n")))
    q.put((name, None))


def run(
    binary,
    out_dir,
    save,
    host_script,
    clients,
    net=None,
    input_delay=3,
    end_frame=3000,
    timeout=600.0,
    host_env=None,
    wait_players=0,
    host_local_players=1,
):
    """Run one Session. ``save``: story save name or .srm path for the Host. Returns a :class:`Result`."""
    net = net or Net()
    out_dir = Path(out_dir)
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    save = Path(save) if str(save).endswith(".srm") else SAVES / f"{save}.srm"
    if not save.exists():
        raise NetError(f"no save {save} (see docs/coop-setup.md)")
    port = free_udp_port()
    proxy = Proxy(seed=net.seed)
    links = [proxy.add_link(port, net.latency, net.jitter, net.loss) for _ in clients]
    proxy.start()

    q = queue.Queue()
    procs, machines, logs = {}, {}, []

    def launch(name, args, script, env):
        d = out_dir / name
        d.mkdir()
        (d / "in.play").write_text(script)
        log = (d / "out.txt").open("w")
        err = (d / "stderr.txt").open("w")
        logs.extend([log, err])
        p = subprocess.Popen(  # noqa: S603
            [binary, "--headless", "--input", "in.play", *args],
            cwd=d,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=err,
            text=True,
            env={**os.environ, **(env or {})},
        )
        procs[name] = p
        machines[name] = Machine(name, d)
        threading.Thread(target=_reader, args=(p, name, q, log), daemon=True).start()

    shutil.copy(save, out_dir / "host.srm")
    host_args = ["--save", "../host.srm", "--host", str(port), "--input-delay", str(input_delay)]
    if end_frame:
        host_args += ["--net-end-frame", str(end_frame)]
    if wait_players:
        host_args += ["--net-wait-players", str(wait_players)]
    if host_local_players > 1:
        host_args += ["--local-players", str(host_local_players)]
    launch("host", host_args, host_script, host_env)
    order = ["host"] + [c.name for c in clients]
    pending = list(zip(clients, links, strict=True))
    t0 = time.time()
    timed_out = False
    open_streams = 1
    try:
        while open_streams or pending:
            if time.time() - t0 > timeout:
                timed_out = True
                break
            # Start clients whose condition holds
            host = machines["host"]
            for c, lk in list(pending):
                if c.start_after is not None and host.last_frame < c.start_after:
                    continue
                if c.start_on and not any(re.search(c.start_on, e) for e in host.events):
                    continue
                if procs["host"].poll() is not None:
                    pending.remove((c, lk))  # the host is gone: never start it
                    continue
                pending.remove((c, lk))
                if c.name in machines:  # a rejoin under the same name: keep the old one's output
                    raise NetError(f"duplicate peer name {c.name}")
                launch(c.name, ["--join", f"127.0.0.1:{lk}", "--local-players", str(c.local_players)], c.script, c.env)
                open_streams += 1
            try:
                name, ln = q.get(timeout=0.05)
            except queue.Empty:
                continue
            m = machines[name]
            if ln is None:
                open_streams -= 1
                continue
            s = SYNC.match(ln)
            if s:
                m.syncs[int(s.group(1))] = (s.group(2), s.group(3))
                spec = next((c for c in clients if c.name == name), None)
                if spec and spec.kill_after is not None and int(s.group(1)) >= spec.kill_after and not m.killed:
                    procs[name].send_signal(signal.SIGKILL)
                    m.killed = True
            elif ln.startswith("NET "):
                m.events.append(ln)
    finally:
        for p in procs.values():
            if p.poll() is None:
                p.kill()
        for name, p in procs.items():
            with contextlib.suppress(subprocess.TimeoutExpired):
                p.wait(timeout=10)
            machines[name].rc = p.returncode
        # Drain what the readers still hold
        deadline = time.time() + 2
        while time.time() < deadline:
            try:
                name, ln = q.get(timeout=0.05)
            except queue.Empty:
                break
            if ln is None:
                continue
            s = SYNC.match(ln)
            if s:
                machines[name].syncs[int(s.group(1))] = (s.group(2), s.group(3))
            elif ln.startswith("NET "):
                machines[name].events.append(ln)
        proxy.stop()
        for f in logs:
            f.close()
    for m in machines.values():
        m.stderr = (m.dir / "stderr.txt").read_text(errors="replace")
    ms = [machines[n] for n in order if n in machines]
    return Result(ms, time.time() - t0, proxy.stats(), timed_out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bin", default=os.environ.get("EB_BIN", ""))
    ap.add_argument("--save", default="05-Twoson")
    ap.add_argument("--players", type=int, default=2)
    ap.add_argument("--frames", type=int, default=3000)
    ap.add_argument("--delay", type=int, default=3)
    ap.add_argument("--latency", type=float, default=0)
    ap.add_argument("--jitter", type=float, default=0)
    ap.add_argument("--loss", type=float, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--out", default=str(PLAYTEST / "out" / "net" / "manual"))
    a = ap.parse_args()
    if not a.bin or not Path(a.bin).is_absolute():
        sys.exit("--bin / $EB_BIN must be an absolute path to the game binary")
    clients = [Peer(f"p{i + 1}", random_play(a.seed * 10 + i, a.frames)) for i in range(1, a.players)]
    r = run(
        a.bin,
        a.out,
        a.save,
        boot_then(random_play(a.seed, a.frames)),
        clients,
        Net(a.latency, a.jitter, a.loss, a.seed),
        a.delay,
        a.frames,
        a.timeout,
        wait_players=a.players,
    )
    for m in r.machines[1:]:
        common, bad = r.agreement(r.machines[0], m)
        print(f"{m.name}: {len(common)} shared hash points, {len(bad)} differ")
    print(f"desyncs={r.desyncs} wall={r.wall:.1f}s {r.summary()} proxy={r.proxy_stats}")
    return 0 if not r.desyncs and not r.timed_out else 1


if __name__ == "__main__":
    sys.exit(main())

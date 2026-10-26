"""Co-op soak bot (PLAN.md M4 Soak): random play from every story save, looking for trouble.

For each story save, one headless game with ``--players N`` boots file 1 and a bot plays
it for ``--minutes`` of game time. Every Player has its own seeded ``random.Random``:

- P2..PN random-walk, but walk toward the Leader whenever their Walker is more than
  ``LEASH_PX`` from it (positions come from the PLAYERS line, read every chunk).
- P1 (unless ``--no-p1``) random-walks on its own, so the story world gets exercised.
- Everyone taps A, B, L, Start and Select now and then, and sometimes holds a button
  for a few seconds (SELECT+START for 2 s makes P2..P4 leave; a later Start rejoins).

The bot drives every pad with sticky holds (``hold Pn BUTTONS; wait N``), so each frame's
pads are exact and the game stays deterministic: (save, seed, players, minutes, binary)
reproduces a run, and ``repro.play`` in the save's output dir replays it without Python.

Failures, per save:

- ``CRASH``: the game exited (signal or non-zero status) or quit by itself.
- ``SANITIZER``: an ASan/UBSan report on stderr (build with ``ENABLE_ASAN``/``ENABLE_UBSAN``).
- ``SUSPECT_FROZEN``: for ``--freeze-frames`` frames (default 5400 = 90 s) the bot kept
  pressing buttons but nothing it can see changed: STATE (minus ``frame=``), PARTY,
  PLAYERS, FOLLOW, the open windows' text, the text printed and the screenshot were all
  identical. If only the screenshot changed (the coffee-break text scroll runs ~9000
  frames), it is listed under ``stalls`` in results.json instead, not a failure.
- ``HARNESS_ERR``: the input-script player printed an ``ERR`` line.
- ``HANG``: a chunk took longer than ``--chunk-timeout`` wall seconds (the process is
  sampled with macOS ``sample`` into ``stack.txt``, then killed).

``--net``: instead, each save is played as a localhost netplay Session through
``playtest/net/netrun.py``, one headless machine per Player, each running its Player's
bot as a fixed input script (no pull toward the Leader: a script can't read state). A
Session passes when every machine ends cleanly with no desync report and agrees with the
Host on every hash point. ``--net-delay/--net-latency/--net-loss`` set the link.

Dad's save-and-quit ends in a wait for RESET, as in the original; the bot "presses RESET"
by restarting the game from the SRAM just saved (a ``<save>-resetN`` output dir) and plays on.

Usage::

    source .venv/bin/activate
    python playtest/coop/soak.py --bin $PWD/port/unix/build-wide/earthbound            # all 36, 30 min, 4 Players
    python playtest/coop/soak.py --bin ... -k 05-Twoson -k 27 --minutes 2 --seed 7

Output (under ``--out``, default ``playtest/out/coop/soak/``): one summary line per save
with what it reached (distinct modes, 256 px map sectors, % of chunks in battle, join/leave
changes, resets), ``results.json``, and per save ``<save>/`` (log.txt, stderr.txt, start.srm,
repro.play, last.png; on a failure also failure.png and log_tail.txt). Exits non-zero if any
save failed.
"""

import argparse
import contextlib
import hashlib
import json
import os
import random
import re
import shlex
import subprocess
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

OUT = lib.OUT / "soak"
REPO = lib.PLAYTEST.parent
CHUNK = 120  # frames between state reads
LEASH_PX = 100  # a Walker farther than this from the Leader walks back toward it
DIRS = ["UP", "UP+RIGHT", "RIGHT", "DOWN+RIGHT", "DOWN", "DOWN+LEFT", "LEFT", "UP+LEFT"]
# Taps depend on where the game is. Walking (idle=yes): rare, mostly A/L (talk, check,
# the menu). Anywhere else (menus, text, battles): often, and more B than A, so menus get
# closed again and the Party gets back to walking.
TAPS_IDLE = ["A", "A", "L", "B", "START", "SELECT"]
TAPS_BUSY = ["A"] * 3 + ["B"] * 4 + ["L", "START", "SELECT"]
TAPS_HPPP = ["B", "B", "B", "A"]  # only the HP/PP window (B toggles it): mostly close it
LONG_HOLDS = ["A", "B", "L", "START", "SELECT"] * 3 + ["SELECT+START"]  # SELECT+START: P2..P4 leave
TAP_CHANCE_IDLE = 1 / 240  # per frame, when not already tapping
TAP_CHANCE_BUSY = 1 / 40
LONG_CHANCE = 1 / 4000  # per frame: a 1-4 s hold, about every 70 s per Player


def pad_join(*parts):
    """``pad_join("UP+LEFT", "A")`` -> ``"UP+LEFT+A"``; nothing -> ``"-"``."""
    s = "+".join(p for p in parts if p and p != "-")
    return s or "-"


class PlayerBot:
    """One Player's random input: a direction that changes now and then, taps, long holds."""

    def __init__(self, rng, follow_leader):
        self.rng = rng
        self.follow_leader = follow_leader
        self.dir, self.dir_left = None, 0
        self.tap, self.tap_left, self.cool = None, 0, 0
        self.long, self.long_left = None, 0
        self.idle = True  # the game was walkable at the last state read
        self.taps = TAPS_IDLE

    def plan(self, walker, leader):
        """Before a chunk: if this Player's Walker strays past LEASH_PX, head back toward the Leader."""
        if not (self.follow_leader and walker and leader):
            return
        dx, dy = leader[0] - walker[0], leader[1] - walker[1]
        if dx * dx + dy * dy <= LEASH_PX * LEASH_PX:
            return
        if self.rng.random() < 0.15:  # sometimes wander instead, to get around walls
            self.dir, self.dir_left = self.rng.choice(DIRS), self.rng.randint(16, CHUNK)
            return
        sx = (dx > 8) - (dx < -8)
        sy = (dy > 8) - (dy < -8)
        self.dir = pad_join({-1: "UP", 1: "DOWN"}.get(sy, ""), {-1: "LEFT", 1: "RIGHT"}.get(sx, ""))
        self.dir_left = CHUNK

    def frame(self):
        """Return the pad for the next frame, as script BUTTONS."""
        r = self.rng
        if self.dir_left <= 0:
            self.dir = None if r.random() < 0.1 else r.choice(DIRS)
            self.dir_left = r.randint(16, 150)
        self.dir_left -= 1
        if self.long_left > 0:
            self.long_left -= 1
            return pad_join(self.dir if self.long != "SELECT+START" else None, self.long)
        if r.random() < LONG_CHANCE:
            self.long, self.long_left = r.choice(LONG_HOLDS), r.randint(60, 240)
        btn = None
        if self.tap_left > 0:
            self.tap_left -= 1
            btn = self.tap
        elif self.cool > 0:
            self.cool -= 1
        elif r.random() < (TAP_CHANCE_IDLE if self.idle else TAP_CHANCE_BUSY):
            self.tap, self.tap_left, self.cool = r.choice(self.taps), 1, r.randint(4, 30)
            btn = self.tap
        return pad_join(self.dir, btn)


class Bot:
    """Drives Players 1..players; ``chunk(state)`` returns the next chunk's commands."""

    def __init__(self, seed, save, players, drive_p1=True):
        self.players = players
        self.bots = {
            p: PlayerBot(random.Random(f"{seed}:{save}:P{p}"), follow_leader=p > 1)  # noqa: S311
            for p in range(1, players + 1)
            if p > 1 or drive_p1
        }

    def chunk(self, st, frames=CHUNK):
        """Commands for ``frames`` frames: the full hold set first, then only the changes."""
        leader = st.pos if st else None
        walkers = st.players if st else {}
        for p, b in self.bots.items():
            w = walkers.get(p)
            b.plan(w.pos if w else None, leader)
            b.idle = st is None or " idle=yes " in st.state
            hppp = st is not None and "modes=[OVERWORLD>HPPP_DISPLAY]" in st.state
            b.taps = TAPS_IDLE if b.idle else TAPS_HPPP if hppp else TAPS_BUSY
        cmds, cur, run = [], {}, 0
        for f in range(frames):
            pads = {p: b.frame() for p, b in self.bots.items()}
            changed = [p for p in pads if f == 0 or pads[p] != cur[p]]
            if changed and run:
                cmds.append(f"wait {run}")
                run = 0
            for p in changed:
                cmds.append(f"hold P{p} {pads[p]}")
            cur = pads
            run += 1
        cmds.append(f"wait {run}")
        return cmds


def fingerprint(lines):
    """What the bot can see of the game, for freeze detection: everything but frame= and NEAR."""
    keep = []
    for ln in lines:
        if ln.startswith("STATE "):
            keep.append(re.sub(r"^STATE \S+ frame=\d+ ", "STATE ", ln))
        elif ln.startswith(("PARTY", "PLAYERS", "FOLLOW", "WIN", "MENU", "TEXT", "ENEMIES")):
            keep.append(ln)
    return hashlib.sha256("\n".join(keep).encode()).hexdigest()


def parse_state(lines):
    st = lib.State()
    for ln in lines:
        for prefix, attr in (("STATE ", "state"), ("PARTY", "party"), ("PLAYERS", "players_line")):
            if ln.startswith(prefix):
                setattr(st, attr, ln)
        if ln.startswith("FOLLOW"):
            st.follow = ln
    return st if st.state else None


def tail(path, n=60):
    try:
        return "\n".join(Path(path).read_text(errors="replace").splitlines()[-n:])
    except OSError:
        return ""


def sanitizer_report(stderr_path):
    err = Path(stderr_path).read_text(errors="replace") if Path(stderr_path).exists() else ""
    m = lib.SANITIZER.search(err)
    if not m:
        return None
    return err[m.start() : m.start() + 4000]


def repro_command(args, save, minutes):
    cmd = [
        "python",
        "playtest/coop/soak.py",
        "-k",
        save,
        "--seed",
        str(args.seed),
        "--players",
        str(args.players),
        "--minutes",
        f"{minutes:g}",
        "--bin",
        args.bin,
    ]
    if args.no_p1:
        cmd.append("--no-p1")
    return shlex.join(cmd)


def write_repro(sess):
    """Every command sent, as an --input script: ``earthbound --headless --save save.srm --players N --input repro.play``."""
    lines = []
    for i, batch in enumerate(sess.history):
        lines.append(f"# batch {i}")
        lines.extend(batch)
    lines.append("end")
    (sess.dir / "repro.play").write_text("\n".join(lines) + "\n")


def is_reset_wait(st):
    """The game waits for RESET: Dad's save-and-quit ends with input disabled (ESHOP3 _PAPA_END).

    The original does the same (disable_controller_input, then halt_without_prompt), so the
    soak presses "RESET": it restarts the game from the SRAM Dad just saved.
    """
    return st is not None and "TELEPHONE_MENU" in st.state and " input=0 " in st.state


def run_segment(sess, bot, res, total, args, cov):
    """Play one game process until ``total`` frames, a failure, or a RESET wait.

    Returns (failure dict or None, reset?, last frame= seen).
    """
    last_fp, still_since, frame = None, res["frames"], None
    last_screen, screen_since, stall_noted = None, res["frames"], False
    try:
        sess.do(lib.BOOT, timeout=max(300, args.chunk_timeout))
        st = parse_state(sess.do("state booted"))
        while res["frames"] < total:
            n = min(CHUNK, total - res["frames"])
            out = sess.do("\n".join(bot.chunk(st, n) + ["state soak", "text", "shot last.png"]), strict=False)
            res["frames"] += n
            err = next((ln for ln in out if ln.startswith("ERR")), None)
            if err:
                return {"kind": "HARNESS_ERR", "detail": err}, False, frame
            st = parse_state(out) or st
            m = re.search(r"frame=(\d+)", st.state) if st else None
            frame = int(m.group(1)) if m else frame
            note_coverage(cov, st)
            screen = hashlib.sha256((sess.dir / "last.png").read_bytes()).hexdigest()
            if screen != last_screen:
                last_screen, screen_since = screen, res["frames"]
            fp = fingerprint(out)
            if fp != last_fp:
                last_fp, still_since, stall_noted = fp, res["frames"], False
                continue
            still = res["frames"] - still_since
            if still >= 600 and is_reset_wait(st):
                return None, True, frame
            if still < args.freeze_frames:
                continue
            if res["frames"] - screen_since >= still:  # the screen didn't change either
                detail = f"nothing visible changed for {still} frames: {st.state}"
                return {"kind": "SUSPECT_FROZEN", "detail": detail}, False, frame
            if not stall_noted:  # e.g. the coffee-break text scroll: only the picture moves
                res["stalls"].append({"frames": res["frames"], "state": st.state})
                stall_noted = True
    except lib.ScenarioError as e:
        with contextlib.suppress(subprocess.TimeoutExpired):
            sess.proc.wait(timeout=2)  # an exited game may not be reaped yet
        rc = sess.proc.poll()
        if rc is not None:
            return {"kind": "CRASH", "detail": f"rc={rc}: {e}"}, False, frame
        failure = {"kind": "HANG", "detail": str(e)}
        stack = sess.dir / "stack.txt"
        subprocess.run(["sample", str(sess.proc.pid), "2", "-file", str(stack)], capture_output=True)  # noqa: S603,S607
        if stack.exists():
            failure["stack"] = str(stack)
        sess.proc.kill()
        return failure, False, frame
    return None, False, frame


def note_coverage(cov, st):
    """Tally what a chunk reached: modes, 256 px map sectors, battles, joined Players."""
    if st is None:
        return
    m = re.search(r"modes=\[([^\]]*)\]", st.state)
    if m:
        cov["modes"].update(m.group(1).split(">"))
    if st.pos:
        cov["sectors"].add((st.pos[0] // 256, st.pos[1] // 256))
    if re.search(r" battle=[1-9]", st.state) or "BATTLE" in (m.group(1) if m else ""):
        cov["battle_chunks"] += 1
    joined = sum(p.joined for p in st.players.values()) if st.players_line else 0
    if cov["joined"] is not None and joined != cov["joined"]:
        cov["join_changes"] += 1
    cov["joined"] = joined
    cov["chunks"] += 1


def soak_one(save, args):
    """Play one save; return its result dict."""
    t0 = time.time()
    name = save.stem
    out_root = Path(args.out)
    ctx = types.SimpleNamespace(dir=out_root, bin=args.bin)
    res = {
        "save": name,
        "seed": args.seed,
        "players": args.players,
        "minutes": args.minutes,
        "bin": args.bin,
        "status": "PASS",
        "frames": 0,
        "resets": [],
        "stalls": [],
        "repro": repro_command(args, name, args.minutes),
    }
    bot = Bot(args.seed, name, args.players, drive_p1=not args.no_p1)
    total = int(args.minutes * 3600)
    cov = {"modes": set(), "sectors": set(), "battle_chunks": 0, "chunks": 0, "joined": None, "join_changes": 0}
    start = save
    while True:
        seg = len(res["resets"])
        sess = lib.Session(
            ctx, name if not seg else f"{name}-reset{seg}", save=start, players=args.players, timeout=args.chunk_timeout
        )
        (sess.dir / "start.srm").write_bytes(sess.start_save)
        failure, reset, frame = run_segment(sess, bot, res, total, args, cov)
        write_repro(sess)
        with contextlib.suppress(lib.ScenarioError, OSError):
            sess.close()
        rc = sess.proc.returncode
        if failure is None and rc not in (0, None):
            failure = {"kind": "CRASH", "detail": f"rc={rc} at quit"}
        san = sanitizer_report(sess.dir / "stderr.txt")
        if san:  # a sanitizer report explains a crash too, so it takes precedence
            failure = {"kind": "SANITIZER", "detail": san.splitlines()[0], "report": san, "was": failure}
        if reset and not failure:
            res["resets"].append(res["frames"])
            start = sess.dir / "save.srm"
            continue
        break
    res["dir"] = str(sess.dir)
    res["frame"] = frame
    res["wall_s"] = round(time.time() - t0, 1)
    res["coverage"] = {
        "modes": sorted(cov["modes"]),
        "sectors": len(cov["sectors"]),
        "battle_pct": round(100 * cov["battle_chunks"] / max(1, cov["chunks"])),
        "join_changes": cov["join_changes"],
    }
    if failure:
        res["status"] = failure["kind"]
        res["failure"] = failure
        res["repro"] = repro_command(args, name, max(res["frames"], CHUNK) / 3600)
        res["repro_play"] = (
            f"cd {sess.dir} && {shlex.quote(args.bin)} --headless --save start.srm"
            f" --players {args.players} --input repro.play"
        )
        last = sess.dir / "last.png"
        if last.exists():
            (sess.dir / "failure.png").write_bytes(last.read_bytes())
            failure["shot"] = str(sess.dir / "failure.png")
        (sess.dir / "log_tail.txt").write_text(
            tail(sess.dir / "log.txt") + "\n--- stderr ---\n" + tail(sess.dir / "stderr.txt")
        )
        failure["log_tail"] = str(sess.dir / "log_tail.txt")
    return res


def bot_script(seed, save, player, frames):
    """Player ``player``'s bot input as a fixed --input script for one netplay machine.

    A netplay machine runs an ``--input`` script, so the bot can't read state: no pull
    toward the Leader, and walking-mode taps throughout. The machine's local Player is
    its script's P1. Ends with a long wait (the Session ends at --net-end-frame).
    """
    bot = PlayerBot(random.Random(f"{seed}:{save}:P{player}"), follow_leader=False)  # noqa: S311
    out, cur, run = [], None, 0
    for _ in range(frames):
        pad = bot.frame()
        if pad != cur:
            if run:
                out.append(f"wait {run}")
            out.append(f"hold P1 {pad}")
            cur, run = pad, 0
        run += 1
    out += [f"wait {run}", "hold P1 -", "wait 1000000"]
    return "\n".join(out) + "\n"


def net_one(save, args):
    """Soak one save as a netplay Session: one headless machine per Player via playtest/net/netrun.py.

    Every machine must end cleanly with no desync report and agree with the Host on every
    hash point (netrun's checks); returns a result dict like soak_one's.
    """
    sys.path.insert(0, str(lib.PLAYTEST / "net"))
    import netrun  # noqa: PLC0415 - only the --net mode needs it

    t0 = time.time()
    frames = int(args.minutes * 3600)
    host = netrun.boot_then(bot_script(args.seed, save.stem, 1, frames))
    clients = [netrun.Peer(f"p{p}", bot_script(args.seed, save.stem, p, frames)) for p in range(2, args.players + 1)]
    out = Path(args.out) / "net" / save.stem
    res = {"save": save.stem, "seed": args.seed, "players": args.players, "minutes": args.minutes, "frames": frames}
    res["repro"] = repro_command(args, save.stem, args.minutes) + " --net"
    try:
        r = netrun.run(
            args.bin,
            out,
            save,
            host,
            clients,
            netrun.Net(args.net_latency, args.net_latency / 3, args.net_loss, args.seed),
            input_delay=args.net_delay,
            end_frame=frames,
            timeout=args.net_timeout,
            wait_players=args.players,
        )
        res["wall_s"] = round(r.wall, 1)
        r.check_clean(frames)
        r.check_agreement(min_common=frames // 60 - 2)
        res["status"] = "PASS"
        res["detail"] = f"{len(r.agreement(r.machines[0], r.machines[-1])[0])} hash points agree, {r.summary()}"
    except netrun.NetError as e:
        res["status"] = "NET_FAIL"
        res["detail"] = str(e)
        res.setdefault("wall_s", round(time.time() - t0, 1))
    res["dir"] = str(out)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-k", action="append", default=[], help="only saves whose name contains this (repeatable)")
    ap.add_argument("--minutes", type=float, default=30, help="in-game minutes per save (default 30)")
    ap.add_argument("--players", type=int, default=4, choices=[1, 2, 3, 4])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--bin", default=os.environ.get("EB_BIN", str(REPO / "port/unix/build-wide/earthbound")))
    ap.add_argument("-j", "--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--no-p1", action="store_true", help="leave P1's pad alone (the bot drives P2..PN only)")
    ap.add_argument("--freeze-frames", type=int, default=5400, help="SUSPECT_FROZEN after this many still frames")
    ap.add_argument("--chunk-timeout", type=float, default=120, help="wall seconds per chunk before HANG")
    ap.add_argument("--progress", action="store_true", help="print each save's progress every 10 game minutes")
    ap.add_argument("--out", default=str(OUT), help=f"output dir (default {OUT})")
    ap.add_argument(
        "--net",
        action="store_true",
        help="play each save as a localhost netplay Session instead (one machine per Player, playtest/net/)",
    )
    ap.add_argument("--net-delay", type=int, default=20, help="--net: input delay in frames (default 20)")
    ap.add_argument("--net-latency", type=float, default=0, help="--net: one-way latency in ms (jitter = 1/3)")
    ap.add_argument("--net-loss", type=float, default=0, help="--net: packet loss, 0-1")
    ap.add_argument("--net-timeout", type=float, default=1800, help="--net: wall seconds per Session")
    args = ap.parse_args()
    args.bin = str(Path(args.bin).resolve())
    if not Path(args.bin).exists():
        sys.exit(f"no game binary at {args.bin}")
    saves = sorted(lib.SAVES.glob("*.srm"))
    if args.k:
        saves = [s for s in saves if any(k in s.stem for k in args.k)]
    if not saves:
        sys.exit(f"no story saves matched in {lib.SAVES}")
    Path(args.out).mkdir(parents=True, exist_ok=True)
    print(f"soak: {len(saves)} saves x {args.minutes:g} min, {args.players} Players, seed {args.seed}, {args.bin}")
    t0 = time.time()
    results = []
    if args.net:
        if args.players < 2:
            sys.exit("--net needs --players 2..4")
        failed = 0
        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            for r in ex.map(lambda s: net_one(s, args), saves):
                results.append(r)
                failed += r["status"] != "PASS"
                print(f"{r['status']:<9} {r['save']:<14} {r['wall_s']:6.1f}s  {r['detail'][:300]}", flush=True)
                if r["status"] != "PASS":
                    print(f"    out: {r['dir']}\n    repro: {r['repro']}", flush=True)
        results_path = Path(args.out) / "net" / "results.json"
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(json.dumps(results, indent=1))
        print(f"soak --net: {len(results) - failed}/{len(results)} Sessions clean (results: {results_path})")
        return 1 if failed else 0
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for r in ex.map(lambda s: soak_one(s, args), saves):
            results.append(r)
            mins = r["frames"] / 3600
            c = r["coverage"]
            line = (
                f"{r['status']:<14} {r['save']:<14} {mins:5.1f} min {r['wall_s']:6.1f}s  modes={len(c['modes'])}"
                f" sectors={c['sectors']} battle={c['battle_pct']}% joins={c['join_changes']} resets={len(r['resets'])}"
                f" stalls={len(r['stalls'])}"
            )
            if r["status"] != "PASS":
                f = r["failure"]
                line += f"  {f['detail'][:200]}\n    shot: {f.get('shot', '-')}\n    repro: {r['repro']}"
            print(line, flush=True)
    failed = [r for r in results if r["status"] != "PASS"]
    results_path = Path(args.out) / "results.json"
    results_path.write_text(json.dumps(results, indent=1))
    print(
        f"soak: {len(results) - len(failed)}/{len(results)} saves passed in {time.time() - t0:.0f}s"
        f" (results: {results_path})"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

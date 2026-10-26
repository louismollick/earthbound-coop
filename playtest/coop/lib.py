"""Helpers for co-op scenarios (``playtest/coop/scenarios/*.py``).

A scenario is a module with ``run(ctx)``. ``ctx`` is a :class:`Scenario`: it starts
headless game sessions (``ctx.session(...)``), each driven over the ``--session``
FIFO with the input-script language of ``port/unix/platform/sdl2_input_script.c``
(Player prefixes included: ``P2 press START``). A session blocks between commands,
so every step is deterministic.

    s = ctx.session(players=2)           # empty SRAM; --players 2 auto-joins P2
    s.new_game()                         # playtest/scripts/newgame.play: Ness in his bedroom
    p = s.players()                      # parsed PLAYERS line, keyed 1..4
    expect(p[2].joined and p[2].owns == [], "P2 joined, owning nothing", p[2])
    ctx.shot(s, "bedroom")               # an important shot: it goes on the contact sheet

Failures raise :class:`ScenarioError` with what was expected and what was seen.
With ``EB_COOP_SANITIZE=1``, closing a session fails if the game's stderr has an
ASan/UBSan report. Output goes to ``playtest/out/coop/<scenario>/<session>/``.
"""

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAYTEST = HERE.parent
OUT = PLAYTEST / "out" / "coop"
NEWGAME = PLAYTEST / "scripts" / "newgame.play"
SAVES = PLAYTEST / "saves"
# Title screen -> file select -> file 1 -> Continue, then wait for control (pt.py BOOT)
BOOT = "300 -; 1 START; 200 -; 1 A; 120 -; 1 A; 120 -; 1 A; until idle 900"
SANITIZER = re.compile(r"runtime error:|ERROR: AddressSanitizer|ERROR: LeakSanitizer")


class ScenarioError(Exception):
    """A scenario check failed; the message says what was expected and what was seen."""


def expect(cond, what, seen):
    """Fail with ``expected WHAT, saw SEEN`` unless ``cond``."""
    if not cond:
        raise ScenarioError(f"expected {what}, saw {seen}")


@dataclass
class Player:
    """One segment of the PLAYERS line."""

    num: int
    joined: bool
    owns: list = field(default_factory=list)
    walker: str | None = None
    pos: tuple | None = None
    dir: str | None = None
    walk: int | None = None
    spectator: bool = False
    standin: bool = False  # the Walker is a Guest this Player stands in for

    def __str__(self):
        if not self.joined:
            return f"P{self.num}:-"
        s = f"P{self.num}:joined owns={','.join(self.owns) or '-'} walker={self.walker or '-'}"
        if self.pos:
            s += f" pos={self.pos} dir={self.dir} walk={self.walk}"
        return s + (" spectator" if self.spectator else "") + (" standin" if self.standin else "")


def parse_players(line):
    """``PLAYERS P1:joined owns=Ness walker=Ness pos=(1,2) dir=UP walk=0 | P2:- ...`` -> {1: Player, ...}.

    A Guest's name may have spaces: ``walker=Bubble Monkey standin pos=...``.
    """
    out = {}
    for seg in line[len("PLAYERS") :].split("|"):
        seg = seg.strip()
        m = re.match(r"P(\d):(\S+)(.*)", seg)
        if not m:
            continue
        num, rest = int(m.group(1)), m.group(3)
        if m.group(2) != "joined":
            out[num] = Player(num, False)
            continue
        owns = re.search(r"owns=(\S+)", rest)
        walker = re.search(r"walker=(.+?)(?= standin| spectator| pos=|$)", rest)
        pos = re.search(r"pos=\((\d+),(\d+)\)", rest)
        dir_ = re.search(r"dir=(\S+)", rest)
        walk = re.search(r"walk=(\d+)", rest)
        out[num] = Player(
            num,
            True,
            owns=[] if not owns or owns.group(1) == "-" else owns.group(1).split(","),
            walker=None if not walker or walker.group(1) == "-" else walker.group(1),
            pos=(int(pos.group(1)), int(pos.group(2))) if pos else None,
            dir=dir_.group(1) if dir_ else None,
            walk=int(walk.group(1)) if walk else None,
            spectator=" spectator" in rest,
            standin=" standin" in rest,
        )
    return out


@dataclass
class State:
    """The lines one ``state`` command printed."""

    state: str = ""
    party: str = ""
    players_line: str = ""
    follow: str = ""
    near_line: str = ""
    camera_line: str = ""
    extra: list = field(default_factory=list)  # every other line (CONTACT, TEXT, ...)

    @property
    def players(self):
        return parse_players(self.players_line)

    @property
    def focus(self):
        """The PLAYERS line's input focus: ``"P2 locked"``, ``"P1"`` or ``"ALL"``."""
        m = re.search(r"\| focus=(\S+( locked)?)", self.players_line)
        return m.group(1) if m else None

    def hp(self, member):
        """Party member ``member``'s (1-4) current HP from the PARTY line, or None."""
        m = re.search(rf"(?:^PARTY|\|) {member}:\S+ L\d+ HP (\d+)/", self.party)
        return int(m.group(1)) if m else None

    @property
    def money(self):
        m = re.search(r"money=(\d+)", self.state)
        return int(m.group(1)) if m else None

    @property
    def pos(self):
        m = re.search(r"pos=\((\d+),(\d+)\)", self.state)
        return (int(m.group(1)), int(m.group(2))) if m else None

    @property
    def follow_offsets(self):
        """FOLLOW line as {party member id: (dx, dy) from the Leader}."""
        return {int(m[0]): (int(m[1]), int(m[2])) for m in re.findall(r" (\d+):\(([+-]\d+),([+-]\d+)\)", self.follow)}

    @property
    def near(self):
        """NEAR line as {"npc1065": (dx, dy), ...}, offsets from the Leader."""
        return {m[0]: (int(m[1]), int(m[2])) for m in re.findall(r"(npc\d+) \(([+-]\d+),([+-]\d+)\)", self.near_line)}

    @property
    def dir(self):
        m = re.search(r" dir=(\S+)", self.state)
        return m.group(1) if m else None

    @property
    def camera(self):
        """CAMERA line: the view centre in world pixels (BG1 scroll + half the viewport)."""
        m = re.search(r"CAMERA \((\d+),(\d+)\)", self.camera_line)
        return (int(m.group(1)), int(m.group(2))) if m else None

    @property
    def view(self):
        """CAMERA line: the viewport size (width, height) of the binary."""
        m = re.search(r"view=(\d+)x(\d+)", self.camera_line)
        return (int(m.group(1)), int(m.group(2))) if m else None

    def on_screen(self, pos):
        """``pos`` (world pixels) relative to the view's top-left corner."""
        (cx, cy), (w, h) = self.camera, self.view
        return (pos[0] - cx + w // 2, pos[1] - cy + h // 2)

    @property
    def idle(self):
        m = re.search(r"idle=(\S+)", self.state)
        return m.group(1) if m else None


def leash_margin(view):
    """The leash keeps a Walker this far (x, y) inside the view: 1/8 of the viewport (coop_camera.h)."""
    return (view[0] // 8, view[1] // 8)


def expect_in_leash(st, pos, what):
    """Fail unless world position ``pos`` is on screen at least the leash margin from every edge."""
    sx, sy = st.on_screen(pos)
    (mx, my), (w, h) = leash_margin(st.view), st.view
    expect(mx <= sx <= w - mx and my <= sy <= h - my, f"{what} inside the view minus {mx},{my} px", (sx, sy))


def split_commands(cmds):
    return [c.strip() for c in re.split(r"[;\n]", cmds) if c.strip() and not c.strip().startswith("#")]


class Session:
    """One headless game process driven over its ``--session`` FIFO."""

    def __init__(self, scenario, name, save=None, players=1, timeout=120.0, binary=None):
        self.scenario = scenario
        self.dir = scenario.dir / name
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True)
        if save:
            shutil.copy(save, self.dir / "save.srm")
        else:
            (self.dir / "save.srm").write_bytes(bytes(8192))  # empty SRAM: new game
        os.mkfifo(self.dir / "cmd.fifo")
        args = [binary or scenario.bin, "--headless", "--save", "save.srm", "--session", "cmd.fifo"]
        if players > 1:
            args += ["--players", str(players)]
        self.timeout = timeout
        self.seq = 0
        self.players_arg = players
        self.start_save = (self.dir / "save.srm").read_bytes()
        # Every command batch sent with do(), in order (sync markers left out): with
        # start_save and players_arg it replays this session (continuity.py)
        self.history = []
        self.log = (self.dir / "log.txt").open("w")
        self.stderr = (self.dir / "stderr.txt").open("w")
        self.proc = subprocess.Popen(  # noqa: S603
            args, cwd=self.dir, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=self.stderr, text=True
        )
        self.lines = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self.fifo = None
        deadline = time.time() + 10
        while self.fifo is None:
            try:
                self.fifo = os.open(self.dir / "cmd.fifo", os.O_WRONLY | os.O_NONBLOCK)
            except OSError:
                if self.proc.poll() is not None or time.time() > deadline:
                    raise ScenarioError(f"game did not open its session FIFO (rc={self.proc.poll()})") from None
                time.sleep(0.01)
        os.set_blocking(self.fifo, True)

    def _read(self):
        for ln in self.proc.stdout:
            self.log.write(ln)
            self.lines.put(ln.rstrip("\n"))
        self.lines.put(None)

    def do(self, cmds, timeout=None, strict=True):
        """Send ``;``/newline-separated commands; return the lines printed until they finish.

        ``strict``: raise on an ``ERR`` line (else it is returned with the rest).
        """
        self.seq += 1
        cmd_list = split_commands(cmds)
        self.history.append(cmd_list)
        body = cmd_list + [f"sync {self.seq}"]
        os.write(self.fifo, ("\n".join(body) + "\n").encode())
        marker = f"SYNC {self.seq} "
        out = []
        deadline = time.time() + (timeout or self.timeout)
        while True:
            try:
                ln = self.lines.get(timeout=max(0.1, deadline - time.time()))
            except queue.Empty:
                raise ScenarioError(f"timed out waiting for {cmds!r} (last lines: {out[-5:]})") from None
            if ln is None:
                raise ScenarioError(f"game exited during {cmds!r} (rc={self.proc.poll()}, last lines: {out[-5:]})")
            if ln.startswith(marker):
                return out
            if strict and ln.startswith("ERR"):
                raise ScenarioError(f"script error during {cmds!r}: {ln}")
            out.append(ln)

    def state(self, label="-"):
        st = State()
        for ln in self.do(f"state {label}"):
            if ln.startswith("STATE "):
                st.state = ln
            elif ln.startswith("PARTY"):
                st.party = ln
            elif ln.startswith("PLAYERS"):
                st.players_line = ln
            elif ln.startswith("FOLLOW"):
                st.follow = ln
            elif ln.startswith("NEAR"):
                st.near_line = ln
            elif ln.startswith("CAMERA"):
                st.camera_line = ln
            else:
                st.extra.append(ln)
        expect(st.players_line, "a PLAYERS line after 'state'", st.state or "nothing")
        return st

    def players(self):
        return self.state().players

    def said(self, cmds, timeout=None):
        """Run ``cmds``; return the game text they printed (the TEXT lines, joined)."""
        return " ".join(ln[5:] for ln in self.do(cmds, timeout) if ln.startswith("TEXT "))

    def menu(self):
        """The menu being driven now: (options, cursor index), or None (``text``'s MENU line)."""
        for ln in self.do("text"):
            if ln.startswith("MENU "):
                opts = re.findall(r" (>?)\[([^\]]*)\]", ln)
                sel = next((i for i, (m, _) in enumerate(opts) if m), None)
                return [o for _, o in opts], sel
        return None

    def windows(self):
        """The open windows and the driven menu: ``text``'s WIN and MENU lines.

        Two equal results mean nothing on screen changed (no cursor move, no window opened or closed).
        """
        return [ln for ln in self.do("text") if ln.startswith(("WIN ", "MENU "))]

    def title(self):
        """The focused window's title (``WIN w15* [Paula P2]|`` -> ``"Paula P2"``), or None."""
        for ln in self.windows():
            m = re.match(r"WIN w\d+\* \[([^\]]*)\]\|", ln)
            if m:
                return m.group(1)
        return None

    def boot(self):
        """Boot the save's file 1 (Continue) until the Leader can walk."""
        self.do(BOOT, timeout=300)
        st = self.state("booted")
        expect(st.idle == "yes", "the Party idle after booting the save", st.state)
        return st

    def new_game(self):
        """Play playtest/scripts/newgame.play: default names, Ness controllable in his bedroom."""
        self.do("\n".join(ln for ln in NEWGAME.read_text().splitlines() if not ln.startswith("sync")), timeout=300)
        st = self.state("bedroom")
        expect(st.idle == "yes", "Ness idle in his bedroom after the new-game script", st.state)
        return st

    def kraken_spot(self, where="desert"):
        """Boot 27-Kraken (Ness, Paula, Jeff, Poo), no enemies, and teleport the Party.

        ``desert``: all on one spot of open Scaraba desert at (1400,5520), Ness facing DOWN; open
        ground 100+ px every way except the shore (a wall) about 85 px below.
        ``sailor``: the Summers harbour nook (7264,2900) right above the standing sailor npc1065
        (7264,2928); then P1 walks Ness right to (7341,2912) and non-Leader Walkers stay put.
        """
        self.boot()
        if where == "sailor":
            self.do("flag 11 1; teleport 7264 2900 2; 60 RIGHT; 30 -")
        else:
            self.do("flag 11 1; teleport 1400 5520 4; 30 -")
        return self.state(where)

    def shot(self, label):
        for ln in self.do(f"shot {label}"):
            if ln.startswith("SHOT "):
                return self.dir / ln.split()[1]
        raise ScenarioError(f"no SHOT line for shot {label}")

    def close(self):
        if self.proc.poll() is None:
            try:
                os.write(self.fifo, b"quit\n")
                self.proc.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                self.proc.kill()
                self.proc.wait()
        os.close(self.fifo)
        self.stderr.close()
        self.log.close()
        if os.environ.get("EB_COOP_SANITIZE") == "1":
            err = (self.dir / "stderr.txt").read_text(errors="replace")
            m = SANITIZER.search(err)
            if m:
                line = err[m.start() : err.find("\n", m.start())]
                raise ScenarioError(f"no sanitizer report, saw: {line} (see {self.dir / 'stderr.txt'})")


class Scenario:
    """What a scenario's ``run(ctx)`` gets: sessions, important shots, its output dir."""

    def __init__(self, name, binary):
        self.name = name
        self.bin = binary
        self.dir = OUT / name
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True)
        self.sessions = []
        self.important = []

    @property
    def native_bin(self):
        """The 256x224 build (``$EB_NATIVE_BIN``, else ``port/unix/build/earthbound`` next to ``$EB_BIN``'s build)."""
        env = os.environ.get("EB_NATIVE_BIN")
        path = Path(env) if env else Path(self.bin).resolve().parents[1] / "build" / "earthbound"
        if not path.exists():
            raise ScenarioError(f"a 256x224 build at {path} (or set EB_NATIVE_BIN)")
        return str(path)

    def session(self, name="main", save=None, players=1, binary=None):
        """Start a new game session.

        ``save``: a story save name (``27-Kraken``) or .srm path; None = empty SRAM. ``binary``: another game
        binary for this session (e.g. ``ctx.native_bin``).
        """
        if save and not str(save).endswith(".srm"):
            save = SAVES / f"{save}.srm"
            if not save.exists():
                raise ScenarioError(f"story save {save} (see docs/coop-setup.md)")
        s = Session(self, name, save=save, players=players, binary=binary)
        self.sessions.append(s)
        return s

    def shot(self, session, label):
        """Take a screenshot that belongs on the contact sheet."""
        path = session.shot(label)
        self.important.append({"path": str(path), "label": f"{self.name}: {label}"})
        (self.dir / "important.json").write_text(json.dumps(self.important, indent=1))
        return path

    def close(self):
        errors = []
        for s in self.sessions:
            try:
                s.close()
            except ScenarioError as e:
                errors.append(str(e))
        if errors:
            raise ScenarioError("; ".join(errors))

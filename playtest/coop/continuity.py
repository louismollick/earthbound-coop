"""Savestate continuity: a game restored in a fresh process must carry on exactly as the original.

This catches co-op state that is not serialized, which would break savestates and online
joins (a joining Player receives a savestate). For one command stream it runs:

- **A**, continuous: the stream from the start save, with ``snap mid`` at the first batch
  boundary at or past half its frames, and ``snap end`` at the end.
- **B**, cold: a fresh process given A's ``mid`` slot (and A's SRAM and other snaps as they
  were at that moment) restores it, re-applies the sticky holds active at the split, plays
  the rest of the stream, then ``snap end``.
- **A2**, determinism: a second fresh process replays A's whole stream, snaps included.

A, A2 and B must end with byte-identical ``end`` slots. The slot's 24-byte header (seq,
CRC, informational frame) is skipped: the tamp-compressed payload is decompressed and
compared section by section, so a divergence names the first differing section and byte
offset. The STATE/PARTY/PLAYERS/FOLLOW/NEAR/ENEMIES/UNTIL lines after every batch are
compared too, and the first differing line and field locate where the runs parted. (TEXT,
WIN and MENU lines are left out of A vs B: the harness's text capture is process state, not
game state, and starts empty after a restore.) Every batch ends with ``state cont``, so the
transcript has a checkpoint per batch; it takes no frame.

Streams:

- soak segments (default): ``soak.py``'s bot for ``--minutes`` from each save in ``-k``
  (default three saves), A driving the bot live and B/A2 replaying what it sent.
- every co-op scenario: ``run_all.py --continuity`` records each scenario session's batches
  (``lib.Session.history``) and checks each session with at least 2 batches.

Usage::

    source .venv/bin/activate
    python playtest/coop/continuity.py --bin $PWD/port/unix/build-wide/earthbound            # 3 saves x 2 min x 4 Players
    python playtest/coop/continuity.py --bin ... -k 27-Kraken --minutes 5 --seed 3

Prints ``PASS``/``FAIL name: first difference`` per stream; exits non-zero on any FAIL.
Output: ``playtest/out/coop/continuity/<name>/{a,a2,b}/``.
"""

import argparse
import json
import os
import re
import shutil
import struct
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src" / "vendor" / "tamp"))
import lib  # noqa: E402
import soak  # noqa: E402

OUT = lib.OUT / "continuity"
REPO = lib.PLAYTEST.parent
DEFAULT_SAVES = ["05-Twoson", "17-GoldMine", "27-Kraken"]
STATE_LINES = ("STATE", "PARTY", "PLAYERS", "FOLLOW", "NEAR", "ENEMIES", "UNTIL", "SNAP", "RESTORE", "ERR")
HEADER = struct.Struct("<IHHIIII")  # magic, version, frame, seq, crc32, payload_len, layout_id


class SkipError(Exception):
    """The stream can't be checked (e.g. no snap was possible past its middle)."""


def section_names():
    """{section id: "CORE", ...} from src/core/state_dump.c, for naming a differing section."""
    src = (REPO / "src" / "core" / "state_dump.c").read_text()
    return {int(v, 16): k for k, v in re.findall(r"SECTION_(\w+)\s*=\s*0x([0-9A-Fa-f]+)", src)}


def read_slot(prefix):
    """Decompressed sections of the newest valid slot ``prefix.0``/``prefix.1``: [(id, bytes), ...]."""
    from tamp.decompressor import decompress  # vendored pure-Python tamp (src/vendor/tamp)

    best = None
    for f in prefix.parent.glob(prefix.name + ".*"):
        d = f.read_bytes()
        if len(d) < HEADER.size:
            continue
        magic, _ver, _frame, seq, _crc, plen, _layout = HEADER.unpack_from(d)
        if magic == 0x44534245 and len(d) >= HEADER.size + plen and (best is None or seq > best[0]):
            best = (seq, d[HEADER.size : HEADER.size + plen])
    if best is None:
        return None
    p, o, out = bytes(decompress(best[1])), 0, []
    while o + 2 <= len(p):
        (sid,) = struct.unpack_from("<H", p, o)
        o += 2
        if sid == 0xFFFF:
            break
        (size,) = struct.unpack_from("<I", p, o)
        o += 4
        out.append((sid, p[o : o + size]))
        o += size
    return out


def diff_slots(a, b):
    """First difference between two read_slot() results, or None."""
    if a is None or b is None:
        return f"missing slot ({'A' if a is None else 'other'})"
    names = section_names()
    if [s for s, _ in a] != [s for s, _ in b]:
        return "different section lists"
    diffs = []
    for (sid, x), (_, y) in zip(a, b):
        if x == y:
            continue
        name = names.get(sid, hex(sid))
        if len(x) != len(y):
            diffs.append(f"{name}: size {len(x)} vs {len(y)}")
            continue
        offs = [i for i in range(len(x)) if x[i] != y[i]]
        o = offs[0]
        diffs.append(
            f"{name} (0x{sid:02X}): {len(offs)} bytes differ, first at +{o}: "
            f"{x[o : o + 8].hex(' ')} vs {y[o : o + 8].hex(' ')}"
        )
    return "; ".join(diffs) or None


def state_lines(out, text=False):
    """The lines of one batch's output that describe game state."""
    keep = STATE_LINES + (("TEXT", "WIN", "MENU") if text else ())
    return [ln for ln in out if ln.startswith(keep)]


def first_line_diff(a, b, base=0):
    """(batch index, description) of the first differing transcript line, or None.

    ``a``/``b``: per-batch lists of lines; ``base`` is added to the reported batch index.
    """
    for i, (x, y) in enumerate(zip(a, b)):
        for lx, ly in zip(x, y):
            if lx != ly:
                tx, ty = lx.split(), ly.split()
                j = next((k for k, (p, q) in enumerate(zip(tx, ty)) if p != q), min(len(tx), len(ty)))
                field = f"{tx[j] if j < len(tx) else '<end>'} vs {ty[j] if j < len(ty) else '<end>'}"
                return base + i, f"{tx[0]} {field}\n      {lx}\n      {ly}"
        if len(x) != len(y):
            return base + i, f"line counts differ ({len(x)} vs {len(y)}): {x[len(y) :] or y[len(x) :]}"
    if len(a) != len(b):
        return base + min(len(a), len(b)), f"batch counts differ ({len(a)} vs {len(b)})"
    return None


def holds_after(batches):
    """Sticky holds in force after ``batches``: {player: BUTTONS} for every nonzero hold."""
    holds = {}
    for batch in batches:
        for cmd in batch:
            toks = cmd.split()
            player = next((int(t[1]) for t in toks if re.fullmatch(r"P[1-4]", t)), 1)
            toks = [t for t in toks if not re.fullmatch(r"P[1-4]", t)]
            if toks and toks[0] == "hold":
                pad = toks[1] if len(toks) > 1 else "-"
                holds[player] = pad
            elif toks and toks[0] == "release":
                holds[player] = "-"
    return {p: v for p, v in holds.items() if v != "-"}


def restore_cmds(before):
    """B's ``restore mid``, with the sticky holds in force at the split set first.

    The holds go before the restore so that the frame the restore takes sees the same pads
    as the frame A's ``snap mid`` took: the platform's previous-frame pad (``pad_prev`` in
    sdl2_input.c, which platform_input_get_pad_new() edges against) is not in the slot.
    """
    holds = holds_after(before)
    return [f"hold P{p} {pad}" for p, pad in sorted(holds.items())] + ["restore mid"]


class Run:
    """One game process of a continuity check, recording its per-batch transcript."""

    def __init__(self, root, name, binary, save_bytes, players):
        ctx = types.SimpleNamespace(dir=root, bin=binary)
        save = root / f"{name}-start.srm"
        save.write_bytes(save_bytes)
        self.sess = lib.Session(ctx, name, save=save, players=players, timeout=300)
        save.unlink()
        self.outs = []

    def do(self, cmds):
        out = self.sess.do("\n".join(cmds), strict=False)
        self.outs.append(out)
        return out

    def close(self):
        self.sess.close()


def check(name, binary, save_bytes, players, source, total_frames=None, warm=False):
    """Run A/B/A2 over a command stream; return a list of problems (empty = PASS).

    ``warm``: B first plays the stream's batch 0 (the boot) before it restores, so caches
    the game fills lazily (asset pointers) are filled as in A; a divergence that only shows
    cold is such a cache, one that also shows warm is live state missing from the slot.

    ``source(prev_state)`` yields the next batch (a list of commands) or None at the end;
    ``prev_state`` is the parsed state after the previous batch (None before the first).
    ``total_frames``: the stream's length, to place the split; None = take it from the
    stream (played first without a split, which needs a fixed ``source``).
    """
    root = OUT / name
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    (root / "start.srm").write_bytes(save_bytes)
    problems = []

    # A: the source live, snap mid at the first boundary past half its frames
    a = Run(root, "a", binary, save_bytes, players)
    stream, split, st, last, played = [], None, None, None, 0
    try:
        while True:
            batch = source(st)
            if batch is None:
                break
            batch = list(batch) + ["state cont"]
            stream.append(batch)
            out = a.do(batch)
            st = soak.parse_state(out) or st
            m = re.search(r"frame=(\d+)", st.state) if st else None
            if m:  # frames since the first batch; core.frame_counter is 16 bits
                played += (int(m.group(1)) - last) % 65536 if last is not None else 0
                last = int(m.group(1))
            if split is None and total_frames and played >= total_frames // 2:
                stream.append(["snap mid"])
                if any("SNAP mid ok" in ln for ln in a.do(["snap mid"])):
                    split = len(stream)
                    shutil.copytree(a.sess.dir / "snaps", root / "mid-snaps")
                    shutil.copy(a.sess.dir / "save.srm", root / "mid.srm")
        stream.append(["snap end"])
        a.do(["snap end"])
    finally:
        a.close()
    # The exact stream, for a manual rerun: [[commands of batch 0], ...] and the split
    (root / "stream.json").write_text(json.dumps({"split": split, "players": players, "warm": warm, "batches": stream}))
    if split is None:
        raise SkipError("no successful snap mid at any batch boundary past half the frames")

    # A2: the whole stream again in a fresh process
    a2 = Run(root, "a2", binary, save_bytes, players)
    try:
        for batch in stream:
            a2.do(batch)
    finally:
        a2.close()

    # B: a fresh process restores mid, then plays the rest
    b = Run(root, "b", binary, (root / "mid.srm").read_bytes(), players)
    try:
        shutil.copytree(root / "mid-snaps", b.sess.dir / "snaps")
        if warm:
            b.do(stream[0])
        out = b.do(restore_cmds(stream[:split]))
        if not any("RESTORE mid ok" in ln for ln in out):
            problems.append(f"B: restore mid failed: {out}")
        b.outs.clear()
        for batch in stream[split:]:
            b.do(batch)
    finally:
        b.close()

    end_a = read_slot(a.sess.dir / "snaps" / "end")
    for other, run, base, text in (("A2", a2, 0, True), ("B", b, split, False)):
        ta = [state_lines(o, text) for o in a.outs[base:]]
        tb = [state_lines(o, text) for o in run.outs]
        d = first_line_diff(ta, tb, base)
        if d:
            problems.append(f"A vs {other}: transcript differs at batch {d[0]}: {d[1]}")
        sd = diff_slots(end_a, read_slot(run.sess.dir / "snaps" / "end"))
        if sd:
            problems.append(f"A vs {other}: end slot differs: {sd}")
        if (a.sess.dir / "save.srm").read_bytes() != (run.sess.dir / "save.srm").read_bytes():
            problems.append(f"A vs {other}: final SRAM differs")
    return problems


def locate(name, binary, max_frames=2400):
    """Find the first frame after the split where B's state differs from A's.

    Reruns a finished check's stream (``OUT/name/stream.json``) as C (A's stream, restoring
    mid in-process) and B (restore mid in a fresh process), with every ``wait N`` after the
    split cut into single frames and a ``snap qK`` after each frame and each other command
    (snap/state commands of the stream left out; both runs get the same commands, so they
    stay comparable; "frames" below counts probes). Returns a description
    of the first differing probe, or None.
    """
    root = OUT / name
    d = json.loads((root / "stream.json").read_text())
    split, batches, players = d["split"], d["batches"], d["players"]
    rest, frames = [], 0
    for cmd in (c for b in batches[split:] for c in b if not c.startswith(("snap", "state"))):
        if frames >= max_frames:
            rest.append(cmd)
        elif cmd.startswith("wait "):
            for _ in range(int(cmd.split()[1])):
                rest += ["wait 1", f"snap q{frames}"] if frames < max_frames else ["wait 1"]
                frames += 1
        else:  # press/until/N BUTTONS can't be cut up: probe after the whole command
            rest += [cmd, f"snap q{frames}"]
            frames += 1
    after = restore_cmds(batches[:split])
    loc = root / "locate"
    shutil.rmtree(loc, ignore_errors=True)
    loc.mkdir()
    c = Run(loc, "c", binary, (root / "start.srm").read_bytes(), players)
    try:
        for b in batches[:split]:
            c.do(b)
        c.do(after + rest)  # restore mid in-process: A's own continuation (shown identical to A)
    finally:
        c.close()
    b = Run(loc, "b", binary, (root / "mid.srm").read_bytes(), players)
    try:
        shutil.copytree(root / "mid-snaps", b.sess.dir / "snaps")
        if d.get("warm"):
            b.do(batches[0])
        b.do(after + rest)
    finally:
        b.close()
    found = None
    for k in range(frames):
        sd = diff_slots(read_slot(c.sess.dir / "snaps" / f"q{k}"), read_slot(b.sess.dir / "snaps" / f"q{k}"))
        if sd:
            found = f"first differs at probe {k} after the restore: {sd}"
            break
    for run in (c, b):  # the per-frame slots are big; keep only the logs
        shutil.rmtree(run.sess.dir / "snaps", ignore_errors=True)
    return found


def soak_source(save_name, seed, players, minutes):
    """A source for check(): boot, then soak.py's bot for ``minutes``."""
    bot = soak.Bot(seed, save_name, players)
    left = [int(minutes * 3600)]
    booted = [False]

    def source(st):
        if not booted[0]:
            booted[0] = True
            return lib.split_commands(lib.BOOT)
        if left[0] <= 0:
            return None
        n = min(soak.CHUNK, left[0])
        left[0] -= n
        return bot.chunk(st, n)

    return source


def fixed_source(batches):
    """A source for check() that sends ``batches`` in order."""
    it = iter(batches)
    return lambda _st: next(it, None)


def check_session(label, binary, sess, warm=False):
    """Continuity over a finished lib.Session (a scenario session): its batches, start save and players.

    Raises SkipError when the session has fewer than 2 batches (nothing to split).
    """
    batches = [b for b in sess.history if b]
    if len(batches) < 2:
        raise SkipError("one batch")
    # The scenario's own run printed SYNC n frame=F after each batch: that gives the length
    syncs = [int(m.group(1)) for m in re.finditer(r"^SYNC \d+ frame=(\d+)", (sess.dir / "log.txt").read_text(), re.M)]
    total = sum((b - a) % 65536 for a, b in zip(syncs, syncs[1:]))
    return check(label, binary, sess.start_save, sess.players_arg, fixed_source(batches), total, warm=warm)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-k", action="append", default=[], help="saves whose name contains this (default: 3 saves)")
    ap.add_argument("--minutes", type=float, default=2)
    ap.add_argument("--players", type=int, default=4, choices=[1, 2, 3, 4])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--bin", default=os.environ.get("EB_BIN", str(REPO / "port/unix/build-wide/earthbound")))
    ap.add_argument("-j", "--jobs", type=int, default=3)
    ap.add_argument("--warm", action="store_true", help="B boots the save before it restores (see check())")
    ap.add_argument("--locate", action="store_true", help="on a FAIL, find the first differing frame (see locate())")
    a = ap.parse_args()
    binary = str(Path(a.bin).resolve())
    saves = sorted(lib.SAVES.glob("*.srm"))
    keys = a.k or DEFAULT_SAVES
    saves = [s for s in saves if any(k in s.stem for k in keys)]
    if not saves:
        sys.exit("no story saves matched")

    def one(save):
        name = f"soak-{save.stem}"
        src = soak_source(save.stem, a.seed, a.players, a.minutes)
        try:
            problems = check(name, binary, save.read_bytes(), a.players, src, int(a.minutes * 3600), a.warm)
        except SkipError as e:
            return name, [f"SKIP: {e}"]
        if problems and a.locate:
            problems.append(f"locate: {locate(name, binary) or 'no differing frame within 2400 frames'}")
        return name, problems

    failed = 0
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for name, problems in ex.map(one, saves):
            print(f"{'FAIL' if problems else 'PASS'} {name}" + "".join(f"\n  {p}" for p in problems), flush=True)
            failed += bool(problems)
    print(f"continuity: {len(saves) - failed}/{len(saves)} streams identical ({a.minutes:g} min, {a.players} Players)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

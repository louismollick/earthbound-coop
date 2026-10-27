"""Drive a long-lived headless game session, one step at a time.

Usage (from the repo root)::

    uv run --no-sync python playtest/pt.py start NAME --save playtest/saves/24-Museum.srm
    uv run --no-sync python playtest/pt.py do NAME "press A; wait 20; 30 DOWN"
    uv run --no-sync python playtest/pt.py stop NAME
    uv run --no-sync python playtest/pt.py history NAME > repro.play
    uv run --no-sync python playtest/pt.py replay NAME NEWNAME
    uv run --no-sync python playtest/pt.py video NAME [--out PATH] [--scale N] [--skip-boot]
    uv run --no-sync python playtest/pt.py start NAME --emu --save ...   # the original game (emu.py)

The game runs with ``--session FIFO``: it executes the commands it is sent and
then blocks (no frame advances) until the next ``do``. Every ``do`` ends with
``text``, ``state`` and a screenshot unless told otherwise, and prints the
resulting lines (window text, state, screenshot path). The command language is
documented in port/unix/platform/sdl2_input_script.c and playtest/README.md.

The binary is ``$EB_BIN`` (default port/unix/build/earthbound). Session files
live in playtest/out/sessions/NAME/ (log.txt, history.play, shots/, snaps/,
debug/, save.srm, start.srm). log.txt echoes each ``do`` batch as a ``> ...``
line; history.play holds every command sent, so ``replay`` can rebuild the
session from start.srm, and ``video`` can render it to an MP4 (a headless
replay with ``--record-video``/``--record-audio``, piped to ffmpeg, with one
chapter per ``do`` step).

``start --emu`` runs the original game instead, in the reference emulator
(playtest/emu.py, a snes9x libretro core), which takes the same flags and
commands; ``do``/``stop``/``history``/``replay``/``video`` work the same on it.
"""

import argparse
import errno
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SESSIONS = HERE / "out" / "sessions"
# Windows has no FIFOs: the game serves a named pipe instead (port/unix/platform/win_compat.c)
WINDOWS = os.name == "nt"
if WINDOWS:
    import _winapi  # WaitNamedPipe
BIN = os.environ.get("EB_BIN", str(ROOT / ("port/unix/build/earthbound" + (".exe" if WINDOWS else ""))))
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

# Title screen -> file select -> file 1 -> Continue, then wait for control.
BOOT = "300 -; 1 START; 200 -; 1 A; 120 -; 1 A; 120 -; 1 A; until idle 900"
# The same in the original (emu.py): its intro runs longer; in:/input follow the asm call chain
EMU = HERE / "emu.py"
EMU_BOOT = (
    "until in:FILE_SELECT_INIT 3000 START*; until input 600; wait 10; press A; wait 30; "
    "until input 600; wait 10; press A; until idle 1500"
)


def engine(d):
    """``"emu"`` if session dir ``d`` runs the original game (emu.py), else ``"port"``."""
    f = d / "engine"
    return f.read_text().strip() if f.exists() else "port"


def players(d):
    """Session dir ``d``'s co-op Player count (``start --players N``; default 1)."""
    f = d / "players"
    return int(f.read_text()) if f.exists() else 1


def game_command(d):
    """The game command line (before its arguments) for session dir ``d``'s engine."""
    if engine(d) == "emu":
        return [sys.executable, str(EMU)]
    n = players(d)
    return [BIN, "--players", str(n)] if n > 1 else [BIN]


def check_binary(d):
    """Exit with a message if session dir ``d``'s game can't run."""
    if engine(d) == "port" and not Path(BIN).exists():
        sys.exit(f"game binary not found: {BIN} (set EB_BIN)")


KEEP = (
    "STATE",
    "PARTY",
    "ENEMIES",
    "NEAR",
    "TEXT",
    "WIN",
    "MENU",
    "SHOT",
    "UNTIL",
    "ERR",
    "FLAG",
    "GIVE",
    "MONEY",
    "RNG",
    "HPT",
    "TELEPORT",
    "SNAP",
    "RESTORE",
    "WARP",
    "FOLLOW",
    "STATUS",
    "DEBUG",
    "PLAYERS",
    ">",
)
PROBLEM = re.compile(r"error|halt|assert|abort|unknown script", re.IGNORECASE)


def session_dir(name):
    return SESSIONS / name


def pid_alive(pid):
    """Whether process ``pid`` runs (on Windows ``os.kill(pid, 0)`` would terminate it)."""
    if not WINDOWS:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    import ctypes  # noqa: PLC0415

    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
    k32.CloseHandle(h)
    return bool(ok) and code.value == 259  # STILL_ACTIVE


def read_pid(d):
    try:
        pid = int((d / "pid").read_text())
    except (OSError, ValueError):
        return None
    return pid if pid_alive(pid) else None


def cmd_channel(d):
    """Session dir ``d``'s command channel: ``cmd.fifo``, or on Windows the pipe named in ``d/pipe``."""
    return (d / "pipe").read_text().strip() if WINDOWS else d / "cmd.fifo"


def send_windows(d, text):
    """Windows: each send is one client of the game's pipe; it is busy while the game finishes the last.

    Returns the open client: the caller closes it once the game acknowledged the commands (their
    ``sync``), so the game never sees a client that left before it was accepted.
    """
    deadline = time.time() + 60
    while True:
        try:
            f = open(cmd_channel(d), "wb", buffering=0)  # noqa: PTH123, SIM115
        except FileNotFoundError:
            sys.exit(f"session {d.name} is not running")
        except OSError:
            if read_pid(d) is None:
                sys.exit(f"session {d.name} is not running")
            if time.time() > deadline:
                sys.exit(f"session {d.name} did not take the command (still busy)")
            time.sleep(0.01)
            continue
        try:
            f.write(text.encode())
        except OSError:
            f.close()
            raise
        return f


def send(d, text):
    """Write command text to the session FIFO (the game holds it open).

    On Windows returns the pipe client to close after the game's ack (send_windows); else None.
    """
    if WINDOWS:
        return send_windows(d, text)
    try:
        fd = os.open(d / "cmd.fifo", os.O_WRONLY | os.O_NONBLOCK)
    except OSError as e:
        if e.errno in (errno.ENXIO, errno.ENOENT):
            sys.exit(f"session {d.name} is not running")
        raise
    data = text.encode()
    try:
        while data:
            try:
                n = os.write(fd, data)
                data = data[n:]
            except BlockingIOError:
                time.sleep(0.01)
    finally:
        os.close(fd)
    return None


def split_commands(cmds):
    out = []
    for part in re.split(r"[;\n]", cmds):
        part = part.strip()
        if part:
            out.append(part)
    return out


def scale_png(path, factor):
    im = Image.open(path)
    im.resize((im.width * factor, im.height * factor), Image.NEAREST).save(path)


def make_sheet(paths, out, cols=4):
    tiles = [Image.open(p).convert("RGB") for p in paths]
    w, h = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (w * min(cols, len(tiles)), (h + 12) * rows), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (im, p) in enumerate(zip(tiles, paths)):
        x, y = (i % cols) * w, (i // cols) * (h + 12)
        sheet.paste(im, (x, y + 12))
        draw.text((x + 2, y), Path(p).stem, fill="black")
    sheet.save(out)
    return out


def shot_command(crop=None, zoom=1):
    """Build the automatic final ``shot`` command."""
    cmd = "shot"
    if crop:
        w, h = crop
        cmd += f" --crop {w} {h}"
    if zoom > 1:
        cmd += f" --zoom {zoom}"
    return cmd


def parse_crop(text):
    """Parse ``WxH`` (or a single ``N`` for a square) into a (w, h) tuple."""
    m = re.fullmatch(r"(\d+)(?:[xX,](\d+))?", text)
    if not m:
        raise argparse.ArgumentTypeError("expected WxH, e.g. 96x96")
    w = int(m.group(1))
    return w, int(m.group(2) or w)


_JA_TABLE: dict[int, str] | None = None


def ja_letters(text: str) -> str:
    """Turn the game's U+E000 + code letters (Japanese window text) into kana.

    The game writes a Mother 2 letter it can't show as ASCII that way; the
    Japanese text table (src/assets/ja/text_table.json, `ebtools extract-ja`)
    names it.
    """
    global _JA_TABLE
    if not any("\ue000" <= ch <= "\ue0ff" for ch in text):
        return text
    if _JA_TABLE is None:
        path = HERE.parent / "src" / "assets" / "ja" / "text_table.json"
        _JA_TABLE = {int(k, 16): v for k, v in json.loads(path.read_text()).items()} if path.exists() else {}
    return "".join(
        _JA_TABLE.get(ord(ch) - 0xE000, f"{{{ord(ch) - 0xE000:02X}}}") if "\ue000" <= ch <= "\ue0ff" else ch
        for ch in text
    )


def do(name, cmds, shot=True, sheet=False, scale=1, timeout=300.0, quiet=False, crop=None, zoom=1, tag=None):
    d = session_dir(name)
    pid = read_pid(d)
    if pid is None:
        sys.exit(f"session {name} is not running (start it first)")
    seq_file = d / "seq"
    seq = int(seq_file.read_text()) + 1 if seq_file.exists() else 1
    seq_file.write_text(str(seq))

    user = split_commands(cmds)
    with (d / "history.play").open("a") as f:
        f.write(f"# {tag or f'do {seq}'}\n" + "".join(f"{c}\n" for c in user))
    # The game reads 255-byte lines: keep the echoed note short
    note = "; ".join(user)
    if len(note) > 200:
        note = note[:197] + "..."
    lines = ([f"note {note}"] if user else []) + user
    if not quiet:
        lines += ["text", "state"]
    if shot:
        lines.append(shot_command(crop, zoom))
    lines.append(f"sync {seq}")

    log = d / "log.txt"
    start = log.stat().st_size
    client = send(d, "\n".join(lines) + "\n")

    marker = f"SYNC {seq} "
    deadline = time.time() + timeout
    buf = ""
    try:
        while True:
            with log.open("rb") as f:
                f.seek(start)
                buf = ja_letters(f.read().decode(errors="replace"))
            if marker in buf:
                break
            if read_pid(d) is None:
                print(buf[-3000:])
                sys.exit(f"session {name}: game exited")
            if time.time() > deadline:
                print(buf[-3000:])
                sys.exit(f"session {name}: timed out after {timeout:.0f}s waiting for sync {seq}")
            time.sleep(0.02)
    finally:
        if client is not None:
            client.close()

    shots = []
    for ln in buf.splitlines():
        if ln.startswith(marker):
            break
        if ln.startswith("SHOT "):
            rel = ln.split()[1]
            p = d / rel
            shots.append(p)
            if scale > 1:
                scale_png(p, scale)
            print(f"SHOT {p} {' '.join(ln.split()[2:])}")
        elif ln.startswith(KEEP) or PROBLEM.search(ln):
            print(ln)
    if sheet and len(shots) > 1:
        out = make_sheet(shots, d / "shots" / f"sheet-{seq:04d}.png")
        print(f"SHEET {out}")


def start(name, save, boot=True, scale=1, history=None, emu=False, num_players=1):
    d = session_dir(name)
    if read_pid(d) is not None:
        sys.exit(f"session {name} is already running (stop it first)")
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    if emu:
        (d / "engine").write_text("emu\n")
    if num_players > 1:
        (d / "players").write_text(f"{num_players}\n")
    check_binary(d)
    shutil.copy(save, d / "save.srm")
    shutil.copy(save, d / "start.srm")
    (d / "history.play").write_text(f"# pt.py session {name} from {save}\n")
    if WINDOWS:
        (d / "pipe").write_text(rf"\\.\pipe\eb-pt-{name}-{uuid.uuid4().hex}" + "\n")
        # Outlive this pt.py process (and its console's job, when allowed)
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        detach = [{"creationflags": flags | subprocess.CREATE_BREAKAWAY_FROM_JOB}, {"creationflags": flags}]
    else:
        os.mkfifo(d / "cmd.fifo")
        detach = [{"start_new_session": True}]
    with (d / "log.txt").open("wb") as log:
        for i, extra in enumerate(detach):
            try:
                p = subprocess.Popen(  # noqa: S603
                    [*game_command(d), "--headless", "--save", "save.srm", "--session", str(cmd_channel(d))],
                    cwd=d,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    **extra,
                )
                break
            except PermissionError:  # the job forbids breakaway
                if i == len(detach) - 1:
                    raise
    (d / "pid").write_text(str(p.pid))
    # Wait until the game has opened the FIFO (Windows: created the pipe; waiting for an instance
    # doesn't connect, so the game never sees a client that closes at once)
    for _ in range(500):
        try:
            if WINDOWS:
                _winapi.WaitNamedPipe(str(cmd_channel(d)), 100)
            else:
                os.close(os.open(d / "cmd.fifo", os.O_WRONLY | os.O_NONBLOCK))
            break
        except OSError:
            if p.poll() is not None:
                sys.exit(f"game exited: see {d / 'log.txt'}")
            time.sleep(0.01)
    print(f"SESSION {name} pid={p.pid} dir={d}")
    if history is not None:
        do(name, history, scale=scale, timeout=3600.0, tag="replay")
    else:
        boot_cmds = (EMU_BOOT if emu else BOOT) if boot else ""
        do(name, boot_cmds, scale=scale, tag="boot", timeout=600.0)


def history_commands(name, boot=True):
    """The commands sent to session NAME, one per line, as a .play script."""
    f = session_dir(name) / "history.play"
    if not f.exists():
        sys.exit(f"no history for session {name}")
    text = f.read_text()
    if not boot:
        # Drop the boot batch so run.py, which boots by itself, can play it
        blocks = re.split(r"(?m)^(?=# )", text)
        text = "".join(b for b in blocks if not b.startswith("# boot\n"))
    return text


def replay(name, new):
    """Start session NEW from NAME's start.srm and resend NAME's whole history."""
    src = session_dir(name)
    if not (src / "start.srm").exists():
        sys.exit(f"session {name} has no start.srm (started before replay support?)")
    cmds = [ln for ln in history_commands(name).splitlines() if ln.strip() and not ln.startswith("#")]
    tmp = SESSIONS / f".replay-{new}.srm"
    SESSIONS.mkdir(parents=True, exist_ok=True)
    shutil.copy(src / "start.srm", tmp)
    try:
        start(new, tmp, history="\n".join(cmds), emu=engine(src) == "emu", num_players=players(src))
    finally:
        tmp.unlink(missing_ok=True)


# Effective SPC700 output rate: the port generates 534 stereo samples per frame
AUDIO_RATE = 534 * 60
BLOCK_HEADER = re.compile(r"^# (boot|replay|do \d+)$")


def history_blocks(name):
    """Session NAME's history as (tag, [commands]) per ``do`` batch."""
    f = session_dir(name) / "history.play"
    if not f.exists():
        sys.exit(f"no history for session {name}")
    blocks = []
    for ln in f.read_text().splitlines():
        m = BLOCK_HEADER.match(ln)
        if m:
            blocks.append((m.group(1), []))
        elif ln.strip() and not ln.startswith("#") and blocks:
            blocks[-1][1].append(ln.strip())
    return blocks


def chapter_metadata(marks, total):
    """Build ffmetadata text with one chapter per mark (in frames, 1/60 s units); return (text, count)."""

    def esc(t):
        return re.sub(r"([=;#\\\n])", r"\\\1", t)

    out, count = [";FFMETADATA1"], 0
    for i, (n, title) in enumerate(marks):
        n = 0 if i == 0 else n  # the first chapter also covers the frames before its mark
        end = marks[i + 1][0] if i + 1 < len(marks) else total
        if end > n:  # a batch that took no frames has no chapter
            out += ["[CHAPTER]", "TIMEBASE=1/60", f"START={n}", f"END={end}", f"title={esc(title)}"]
            count += 1
    return "\n".join(out) + "\n", count


def video(name, out=None, scale=3, fps=60, skip_boot=False, audio=True, crf=18, keep=False):
    """Replay session NAME headlessly and encode every frame (and the audio) to an MP4."""
    src = session_dir(name)
    if not (src / "start.srm").exists():
        sys.exit(f"session {name} has no start.srm")
    check_binary(src)
    if not Path(FFMPEG).exists():
        sys.exit(f"ffmpeg not found: {FFMPEG} (set FFMPEG)")
    blocks = history_blocks(name)
    out = Path(out).resolve() if out else src / f"{name}.mp4"

    # The script: each batch's commands, preceded by a chapter mark
    lines = []
    skipping = skip_boot and blocks and blocks[0][0] == "boot"
    for i, (tag, cmds) in enumerate(blocks):
        if not (skipping and i == 0):
            title = f"{tag}: {'; '.join(cmds)}" if cmds else tag
            lines.append("mark " + (title if len(title) <= 200 else title[:197] + "..."))
        lines += cmds
        if skipping and i == 0:
            lines.append("record on")
    if skip_boot and not skipping:
        print("note: no '# boot' batch in the history; recording from the start", file=sys.stderr)

    work = src / "video-tmp"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    shutil.copy(src / "start.srm", work / "save.srm")
    (work / "video.play").write_text("\n".join(lines) + "\n")
    if WINDOWS:  # the game serves it
        video_in = rf"\\.\pipe\eb-video-{uuid.uuid4().hex}"
    else:
        video_in = "video.fifo"
        os.mkfifo(work / video_in)
    cmd = [*game_command(src), "--headless", "--save", "save.srm", "--input", "video.play"]
    cmd += ["--record-video", video_in]
    if audio:
        cmd += ["--record-audio", "audio.raw"]
    if skipping:
        cmd.append("--record-paused")

    t0 = time.time()
    log = (work / "log.txt").open("w")
    game = subprocess.Popen(  # noqa: S603
        cmd, cwd=work, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    size = None
    for ln in game.stdout:
        log.write(ln)
        m = re.match(r"RECORD video (\d+)x(\d+)", ln)
        if m:
            size = (int(m.group(1)), int(m.group(2)))
            break
    if size is None:
        game.wait()
        what = "emu.py" if engine(src) == "emu" else f"{BIN} (built before --record-video? rebuild it)"
        sys.exit(f"{what} did not start recording: see {work / 'log.txt'}")

    vf = []
    if scale > 1:
        vf.append(f"scale=iw*{scale}:ih*{scale}:flags=neighbor")
    if fps != 60:
        vf.append(f"fps={fps}")
    enc = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24"]
    enc += ["-s", f"{size[0]}x{size[1]}", "-framerate", "60", "-i", video_in]
    enc += ["-vf", ",".join(vf)] if vf else []
    enc += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p", "video.mp4"]
    encoder = subprocess.Popen(enc, cwd=work, stdin=subprocess.DEVNULL)  # noqa: S603

    def watchdog():
        # ffmpeg dying before it opens the FIFO would leave the game blocked in open()
        if encoder.wait() != 0 and game.poll() is None:
            game.kill()

    threading.Thread(target=watchdog, daemon=True).start()

    marks, total, last = [], None, 0.0
    for ln in game.stdout:
        log.write(ln)
        if ln.startswith("MARK "):
            m = re.match(r"MARK n=(\d+) frame=\d+ (.*)", ln.rstrip("\n"))
            if m:
                marks.append((int(m.group(1)), m.group(2)))
                if time.time() - last > 5:
                    last = time.time()
                    print(f"... {m.group(2)[:60]} (video frame {m.group(1)})", file=sys.stderr)
        elif ln.startswith("RECORD done"):
            total = int(ln.split("frames=")[1])
    game.wait()
    rc = encoder.wait()
    log.close()
    if rc != 0 or total is None:
        sys.exit(f"recording failed (game rc={game.returncode}, ffmpeg rc={rc}): see {work / 'log.txt'}")
    t_render = time.time() - t0

    chapters, nchapters = chapter_metadata(marks, total)
    (work / "chapters.txt").write_text(chapters)
    mux = [FFMPEG, "-y", "-loglevel", "error", "-i", "video.mp4"]
    if audio:
        mux += ["-f", "s16le", "-ar", str(AUDIO_RATE), "-ac", "2", "-i", "audio.raw"]
    meta = 2 if audio else 1
    mux += ["-i", "chapters.txt", "-map", "0:v"] + (["-map", "1:a"] if audio else [])
    mux += ["-map_metadata", str(meta), "-map_chapters", str(meta), "-c:v", "copy"]
    mux += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000"] if audio else []
    mux += ["-movflags", "+faststart", str(out)]
    if subprocess.run(mux, cwd=work).returncode != 0:  # noqa: S603
        sys.exit(f"muxing failed: see {work}")
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    secs = total / 60
    print(
        f"VIDEO {out} frames={total} duration={int(secs // 60)}:{secs % 60:05.2f} "
        f"chapters={nchapters} "
        f"size={out.stat().st_size / 1e6:.1f}MB render={t_render:.1f}s ({total / t_render:.0f} frames/s)"
    )


def stop(name):
    d = session_dir(name)
    pid = read_pid(d)
    if pid is None:
        print(f"session {name} is not running")
        return
    client = send(d, "quit\n")
    for _ in range(200):
        if read_pid(d) is None:
            break
        time.sleep(0.02)
    else:
        os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))  # SIGTERM = TerminateProcess on Windows
    if client is not None:
        client.close()
    print(f"stopped {name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start", help="launch a session from a save")
    s.add_argument("name")
    s.add_argument("--save", required=True, help=".srm save file (booted as file 1 -> Continue)")
    s.add_argument("--no-boot", action="store_true", help="stay on the title screen")
    s.add_argument("--scale", type=int, default=1, help="upscale screenshots by this factor")
    s.add_argument("--emu", action="store_true", help="run the original game in the reference emulator (emu.py)")
    s.add_argument("--players", type=int, default=1, help="co-op: auto-join P2..PN at startup (game --players)")
    s = sub.add_parser("do", help="run commands, then print text/state and a screenshot")
    s.add_argument("name")
    s.add_argument("commands", help="';' or newline separated commands")
    s.add_argument("--no-shot", action="store_true", help="skip the automatic final screenshot")
    s.add_argument("--quiet", action="store_true", help="skip the automatic text/state lines")
    s.add_argument("--sheet", action="store_true", help="tile this step's screenshots into one image")
    s.add_argument("--scale", type=int, default=1, help="upscale screenshots by this factor")
    s.add_argument("--timeout", type=float, default=300.0)
    s.add_argument("--crop", type=parse_crop, help="crop the final screenshot to WxH around the leader")
    s.add_argument("--zoom", type=int, default=1, help="scale the final screenshot N times (in the game)")
    s = sub.add_parser("stop", help="quit a session")
    s.add_argument("name")
    s = sub.add_parser("history", help="print every command sent to a session, as a .play script")
    s.add_argument("name")
    s.add_argument("--no-boot", action="store_true", help="drop the boot batch (for run.py, which boots itself)")
    s = sub.add_parser("replay", help="start NEW from NAME's starting save and resend NAME's history")
    s.add_argument("name")
    s.add_argument("new")
    s = sub.add_parser("video", help="render a session (finished or live) to an MP4 by replaying its history")
    s.add_argument("name")
    s.add_argument("--out", help="output .mp4 (default: the session dir, NAME.mp4)")
    s.add_argument("--scale", type=int, default=3, help="nearest-neighbour upscale factor (default 3)")
    s.add_argument("--fps", type=int, default=60, help="output frame rate (the game runs at 60)")
    s.add_argument("--skip-boot", action="store_true", help="start the video after the boot batch")
    s.add_argument("--no-audio", action="store_true", help="video only")
    s.add_argument("--crf", type=int, default=18, help="x264 quality (lower is better, default 18)")
    s.add_argument("--keep", action="store_true", help="keep the work dir (video-tmp/: log, raw audio, chapters)")
    sub.add_parser("list", help="list sessions")
    a = ap.parse_args()

    if a.cmd == "start":
        start(a.name, a.save, boot=not a.no_boot, scale=a.scale, emu=a.emu, num_players=a.players)
    elif a.cmd == "do":
        do(
            a.name,
            a.commands,
            shot=not a.no_shot,
            sheet=a.sheet,
            scale=a.scale,
            timeout=a.timeout,
            quiet=a.quiet,
            crop=a.crop,
            zoom=a.zoom,
        )
    elif a.cmd == "stop":
        stop(a.name)
    elif a.cmd == "history":
        sys.stdout.write(history_commands(a.name, boot=not a.no_boot))
    elif a.cmd == "replay":
        replay(a.name, a.new)
    elif a.cmd == "video":
        video(a.name, a.out, a.scale, a.fps, a.skip_boot, not a.no_audio, a.crf, a.keep)
    else:
        for d in sorted(SESSIONS.glob("*")):
            print(d.name, "running" if read_pid(d) else "stopped", "(emu)" if engine(d) == "emu" else "")


if __name__ == "__main__":
    main()

# Co-op on Windows

The desktop port builds natively on Windows 10/11 with MinGW-w64 (MSYS2), plays local and online co-op, and runs the whole test harness. A Windows build draws every frame exactly as the macOS and Linux builds do, so a Windows machine and a Mac can share an online Session (same commit, same viewport).

## Setup (once)

1. **Git for Windows** (it provides Git Bash), **uv** (`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`) and **MSYS2** (<https://www.msys2.org>, default `C:\msys64`).
2. In an MSYS2 shell, install the toolchain:

   ```
   pacman -S --needed mingw-w64-ucrt-x86_64-{gcc,SDL2,ninja,cmake,pkgconf}
   pacman -S --needed mingw-w64-clang-x86_64-{clang,compiler-rt,SDL2}    # only for the ASan+UBSan build
   ```

3. Put the US ROM at `earthbound.sfc` in the repo root, then in **Git Bash**:

   ```
   scripts/coop-setup.sh            # EB_MSYS2=/d/msys64 scripts/coop-setup.sh if MSYS2 is elsewhere
   ```

   It creates `.venv`, fetches the story saves, extracts the assets and builds `port/unix/build-wide` (320x240), `port/unix/build` (256x224) and `port/unix/build-debug` (CLANG64, ASan+UBSan). There are no `build-base*` builds on Windows (see Tests).

To build by hand (Git Bash; PowerShell works the same with `;` for `&&`):

```
export PATH="/c/msys64/ucrt64/bin:$PWD/.venv/Scripts:$PATH" PYTHONUTF8=1
cmake -S port/unix -B port/unix/build-wide -G Ninja -DCMAKE_BUILD_TYPE=Release -DEB_VIEWPORT_WIDTH=320 -DEB_VIEWPORT_HEIGHT=240
cmake --build port/unix/build-wide
```

The build copies `SDL2.dll` next to `earthbound.exe`; nothing else is needed at run time (the C runtime is the UCRT that ships with Windows), so the folder runs from Explorer.

## Play

Double-click `port/unix/build-wide/earthbound.exe`, or from a terminal:

```
port/unix/build-wide/earthbound.exe                 # local co-op
port/unix/build-wide/earthbound.exe --players 2     # P2 already joined
```

The save (`earthbound.srm`) and F6 savestates go in the working directory (the exe's folder when started from Explorer). A save is staged next to the live file and swapped in with one `MoveFileExW`, so a crash or a closed window mid-save leaves the old save or the new one, never neither. A console window opens next to the game; it shows the log, and closing it closes the game.

Controls are those of `docs/coop-log.md` ("Play local co-op"): P1 on the arrows, X/Z, Enter and Right Shift; P2 on I/J/K/L, U/O, P and `[`; controllers join in connection order.

## Online

As in `docs/coop-online.md`:

```
earthbound.exe --host 7744                          # the Host
earthbound.exe --join 192.168.1.20:7744             # a client
```

- **Firewall:** the first `--host` from an exe brings up a Windows Defender Firewall prompt (once per exe path, so once per build folder). Allow it for the network type you are on (Settings > Network shows whether that's Private or Public); without that, clients from other machines time out. To open the port without the prompt (an administrator PowerShell): `New-NetFirewallRule -DisplayName "EarthBound co-op" -Direction Inbound -Protocol UDP -LocalPort 7744 -Action Allow`. A client needs no rule.
- **Mixed Windows/Mac Sessions** work when both machines build the same commit at the same viewport from the same ROM. The fingerprint check names any difference.

## Tests

Use Git Bash with the MSYS2 UCRT64 `bin` on `PATH` (for `SDL2.dll`) and `PYTHONUTF8=1` (Python's default text encoding on Windows is the ANSI code page, and several tests read UTF-8 sources). `scripts/coop-gates.sh` sets both itself.

```
EB_MSYS2=/c/msys64 scripts/coop-gates.sh --full --framehash
```

What differs from macOS/Linux:

- **Vanilla gate:** upstream d32c421 doesn't build on Windows, so there is no `build-base-fix` here. Gate 3 checks the tracked text goldens (`regress.py check main --text`), and `--framehash` checks every frame against `playtest/regress/framedigest/base.json`, recorded from `build-base-fix` on Linux (`playtest/framedigest.py`). Passing both means the Windows build plays and draws exactly as vanilla on the other OSes.
- **FIFOs:** Windows has none, so the harness uses named pipes. With a `\\.\pipe\NAME` path for `--session` or `--record-video`, the game creates the pipe and waits for the driver (`port/unix/platform/win_compat.c`). `pt.py` (sessions, `video`), `playtest/coop/lib.py`, `framehash.py` and `netrun.py` pick that automatically. A client that closes before the game accepts it doesn't end a session (what it wrote is still read); `pt.py` waits for the pipe with `WaitNamedPipe` instead of a connect-and-close probe and holds each `do`'s connection until its `sync`.
- **ASan+UBSan** needs clang (MinGW gcc has no ASan runtime): `build-debug` is a CLANG64 build without `-Werror` (clang 23 warns about a write-only global ported from the asm), run with `C:\msys64\clang64\bin` first on `PATH`.
- **Not ported:** `pt.py --emu` (the snes9x libretro core in `playtest/emu/` is built with `make` against a Unix toolchain).

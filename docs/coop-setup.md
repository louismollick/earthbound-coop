# Spike notes (2026-10-25, macOS arm64)

Windows: see `docs/coop-windows.md` (MSYS2 toolchain, Git Bash, `scripts/coop-setup.sh` works there too).

Repo: BrianPugh/earthbound pinned at d32c421e7417f5f76bed22344870d2e5d99d9fac, local branch `coop`.
Only untracked additions: this file, `playtest/scripts/newgame.play`, gitignored `earthbound.sfc`, `playtest/saves/`, `.venv`, build dirs.

## ROM
- `/tmp/eb-rom/EarthBound (USA).sfc`: 3,145,728 bytes (headerless, no 512-byte copier header), sha1 d67a8ef36ef616bc39306aa1b486e1bd3047815a (matches No-Intro US).
- Repo does not check a sha1. `ebtools/rom.py detect()` reads the SNES header at 0xFFB0 (headerless) or 0x101B0 (512-byte SMC header), checks checksum/complement and the title string. Both layouts accepted.
- `*.sfc` is in .gitignore (verified with `git check-ignore`).

## Build (works, ~35 s total incl. asset extraction)
System python3 is 3.9 and the project needs >=3.10, and `make unix` runs `pip` and needs `ebtools` on PATH. Fix is environment only:

    brew install cmake pkg-config          # sdl2 (sdl2-compat), uv, ffmpeg already present
    cd earthbound
    git submodule update --init            # make unix does this itself
    uv venv --seed --python 3.12 .venv     # --seed so `pip` exists for the Makefile
    source .venv/bin/activate              # ebtools must be on PATH for cmake configure
    make unix                              # -> port/unix/build/earthbound (256x224)
    # wide viewport (320x240), what goldens/regress expect:
    cmake -S port/unix -B port/unix/build-wide -DCMAKE_BUILD_TYPE=Release -DEB_WERROR=ON -DEB_VIEWPORT_WIDTH=320 -DEB_VIEWPORT_HEIGHT=240
    cmake --build port/unix/build-wide -j10    # ~11 s

No ca65/ld65/spcasm needed for the port itself (only for `make` of the SNES ROM, which unlocks 5 skipped pytest tests).

## Tests
Saves (needed by regress; gitignored `playtest/saves/`): downloaded the 36 zips from fantasyanime.com/legacy/saves/earthbsave*.zip and extracted `earthbound.srm` as `NN-Name.srm`.

    source .venv/bin/activate; uv pip install pytest numpy
    python -m pytest tests -q -rs                       # 1827 passed, 5 skipped, 49 s
    python playtest/regress.py check main --text --bin $PWD/port/unix/build-wide/earthbound   # 31/32 cases same, 6 s
    python playtest/regress.py framehash A B            # per-frame md5 of every case, 108 s for 31 cases x2 binaries

- C unit test (`tests/c/battle_math_test`, run inside pytest): 3320/3320 battle cases match the ROM.
- Skips need `make` (build/earthbound.map via cc65+spcasm) and the snes9x core (`playtest/emu/build.sh`).
- regress `bus` case differs: the Runaway Five bus never starts; stderr has `resolve_text_addr(0xC79B98) returned NULL` (MSG_EVT_RIDE_TONZURABUS_CHAOUS, asm/bin/US/text_data/EEVENT1.ebtxt). Reproducible, looks like an upstream HEAD bug (asset CI is disabled upstream), not an environment issue. Not investigated further.
- framehash of the same binary against a copy: 0 differing frames over ~120k frames (deterministic).

## Headless harness
    export EB_BIN=$PWD/port/unix/build-wide/earthbound   # absolute
    pt(){ python playtest/pt.py "$@"; }
    head -c 8192 /dev/zero > /tmp/eb-empty.srm
    pt start ng --save /tmp/eb-empty.srm --no-boot       # empty SRAM = new game
    pt do ng "until in:SELECTION_MENU 2000 START|-; wait 10"
    # then see playtest/scripts/newgame.play for the whole new-game path (file select, 3 menus,
    # 7 names via keyboard "Don't Care" = default names, OK, "Yep", intro cutscene)
    pt do ng "press A; wait 30; until idle 6000 advance; 30 RIGHT; 20 DOWN; snap bedroom"
    pt stop ng

One-shot batch (no pt.py), 6074 frames in 0.57 s wall:

    mkdir /tmp/x && cd /tmp/x && head -c 8192 /dev/zero > save.srm
    $EB_BIN --headless --save save.srm --input /path/to/playtest/scripts/newgame.play

Raw `--input` files take ONE command per line (no `;`); only pt.py/regress.py split on `;`.
Headless is uncapped: ~10-15k frames/s (60 fps game => ~170-250x realtime). Keyboard screen: cursor starts on `A`; DOWN x5 reaches "Don't Care", RIGHT x2 from there reaches OK.

## Verified artifacts
- Keyboard screen shot: playtest/out/sessions/ng/shots/0003.png; "Ness" filled in: 0004.png
- Bedroom, Ness controllable: playtest/out/sessions/ng/shots/0008.png (state pos=(8156,1144), music=156, party Ness L1 30/30)
- Snap: playtest/out/sessions/ng/snaps/bedroom.0 (same process only; use F6 savestate or replay history for cross-process)

## Co-op relevant code facts
- Input script parse: `port/unix/platform/sdl2_input_script.c` `parse_buttons()` (l.873), command loop in `input_script_next()` (l.1277): `N BUTTONS` -> hold_pad, `press` -> press_pad, `until ... PATTERN` -> `until_step()` (l.926). One uint16_t pad per frame.
- Pad plumbing: `sdl2_input.c` pad_state; `platform.h:97` `platform_input_get_pad()`; single consumer in game: `src/game_main.c:468` -> `memory_update_joypad()` -> `core.pad1_raw`. No pad2 anywhere in src/ or port/. Menus use `platform_input_get_pad_new()` (15 sites).
- framehash.py hashes the final rendered framebuffer (rgb24 at viewport size, md5 per frame, via `--record-video` FIFO). No RAM or audio hashing. regress.py `check` additionally compares STATE/PARTY/window text lines at checkpoints.
- Windows: upstream has only `_WIN32` guards in sdl2_save.c / sdl2_savestate.c, `MSVC` branches in src/core/types.h and cmake/EbWarnings.cmake. No Windows CMake block, no SDL_MAIN_HANDLED, 2-arg `mkdir()` in sdl2_debug.c and sdl2_input_script.c, POSIX FIFO `open()` in session mode (pt.py sessions are Unix only). Upstream CI (.github/workflows/ci.yml): ruff, asset-free pytest, gw cross-compile, cppcheck on ubuntu; asset jobs gated on a self-hosted runner var that is off.
- earthbound-companion (rages4calm) builds Windows with MinGW-w64 (tools/mingw64) + Ninja + SDL2 2.32.10 mingw dev libs, from a patched fork (seanstaggsQU/earthboundRecompLinux2026 @76eacab5 + patches/native-*.patch). Their Windows delta includes `winmm`/`dxguid` link libs and SDL_MAIN_HANDLED/chdir_to_executable_dir in main.c.

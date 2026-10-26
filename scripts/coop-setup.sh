#!/usr/bin/env bash
# Idempotent co-op dev setup (macOS/Linux, and Windows in Git Bash). Run from anywhere; expects
# earthbound.sfc (US retail) in the repo root. Creates .venv, installs deps,
# fetches the 36 story saves if missing, extracts assets, and builds:
#   port/unix/build-base   baseline at upstream d32c421, 320x240 (never rebuilt once present)
#   port/unix/build-base-fix  the same source packed with this fork's ebtools (bus fix): the gates' reference
#   port/unix/build-wide   current tree, 320x240, -Werror
#   port/unix/build        current tree, 256x224 (native), -Werror
#   port/unix/build-debug  current tree, 320x240, ASan+UBSan
# On Windows (docs/coop-windows.md) the toolchain is MSYS2 at $EB_MSYS2 (default C:\msys64):
# UCRT64 gcc + SDL2 for the builds, CLANG64 clang for the ASan build. There are no base
# builds there: the gates check Windows against goldens recorded from vanilla elsewhere.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BASE_COMMIT=d32c421e7417f5f76bed22344870d2e5d99d9fac
NPROC="$(sysctl -n hw.ncpu 2>/dev/null || nproc)"
log() { printf '=== %s\n' "$*"; }

WIN=0
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) WIN=1 ;; esac

[ -f earthbound.sfc ] || { echo "ERROR: put the US EarthBound ROM at $ROOT/earthbound.sfc"; exit 1; }
if [ "$WIN" = 1 ]; then
  MSYS2="${EB_MSYS2:-/c/msys64}"
  PKGS="mingw-w64-ucrt-x86_64-{gcc,SDL2,ninja,cmake,pkgconf} mingw-w64-clang-x86_64-{clang,compiler-rt,SDL2}"
  [ -x "$MSYS2/ucrt64/bin/gcc.exe" ] && [ -f "$MSYS2/ucrt64/lib/pkgconfig/sdl2.pc" ] ||
    { echo "ERROR: no MSYS2 UCRT64 gcc + SDL2 in $MSYS2 (set EB_MSYS2; pacman -S $PKGS)"; exit 1; }
  export PATH="$MSYS2/ucrt64/bin:$PATH" PYTHONUTF8=1 CMAKE_GENERATOR=Ninja
  for t in uv git; do
    command -v "$t" >/dev/null || { echo "ERROR: missing $t (https://docs.astral.sh/uv/, Git for Windows)"; exit 1; }
  done
else
  for t in cmake pkg-config uv git; do
    command -v "$t" >/dev/null || { echo "ERROR: missing $t (brew install cmake pkg-config sdl2 uv)"; exit 1; }
  done
  pkg-config --exists sdl2 || { echo "ERROR: SDL2 not found (brew install sdl2)"; exit 1; }
fi

log "submodules"
[ -f src/vendor/tamp/tamp/_c_src/tamp/compressor.c ] || git submodule update --init

log "venv"
VENV_BIN=.venv/bin
[ "$WIN" = 1 ] && VENV_BIN=.venv/Scripts
[ -x "$VENV_BIN/python" ] || [ -x "$VENV_BIN/python.exe" ] || uv venv --seed --python 3.12 .venv
# shellcheck disable=SC1091
source "$VENV_BIN/activate"
uv pip install -q -e . pytest numpy "ruff==0.15.4"

log "story saves"
SAVES=(01-Start 02-Sharks 03-GiantStep 04-Police 05-Twoson 06-ToHappy 07-InHappy 08-Carpainter
  09-MondoMole 10-ToThreed 11-Winters 12-Zombies 13-Undergrnd 14-BelchBase 15-Desert 16-Fourside
  17-GoldMine 18-DeptStore 19-Moonside 20-TarahRama 21-Monotoli 22-RainyCircle 23-Summers 24-Museum
  25-Sewer 26-Dalaam 27-Kraken 28-Scaraba 29-DungeonM 30-DeepDark 31-StonehBase 32-LumineHall
  33-FireSpring 34-Magicant 35-Onett 36-CavePast)
mkdir -p playtest/saves
for i in "${!SAVES[@]}"; do
  name="${SAVES[$i]}"; n="${name%%-*}"
  [ -f "playtest/saves/$name.srm" ] && continue
  tmp="$(mktemp -d)"
  curl -fsSL "https://fantasyanime.com/legacy/saves/earthbsave$name.zip" -o "$tmp/s.zip"
  python -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$tmp/s.zip" "$tmp/x"
  cp "$(find "$tmp/x" -iname 'earthbound.srm' | head -1)" "playtest/saves/$name.srm"
  rm -rf "$tmp"
done

log "assets"
if [ ! -f asm/bin/assets.manifest ] || [ ! -f src/assets/items/items.json ] || [ ! -f src/assets/music_tracks.json ]; then
  ebtools extract
fi

build() {  # build DIR SRC_DIR extra-cmake-args...
  local dir="$1" src="$2"; shift 2
  cmake -S "$src/port/unix" -B "$dir" "$@" >/dev/null
  cmake --build "$dir" -j"$NPROC" >/dev/null
  log "built $dir"
}
WIDE=(-DEB_VIEWPORT_WIDTH=320 -DEB_VIEWPORT_HEIGHT=240)

log "baseline build (upstream $BASE_COMMIT)"
if [ "$WIN" = 1 ]; then
  log "skipped on Windows (upstream doesn't build there)"
elif [ ! -x port/unix/build-base/earthbound ]; then
  WT="$ROOT/../ebsrc-base"
  [ -d "$WT" ] || git worktree add --detach "$WT" "$BASE_COMMIT"
  # A reused checkout must still be at the baseline, or the vanilla gate compares against co-op code
  if [ "$(git -C "$WT" rev-parse HEAD)" != "$BASE_COMMIT" ] || [ -n "$(git -C "$WT" status --porcelain --untracked-files=no)" ]; then
    echo "ERROR: $WT is not a clean checkout of $BASE_COMMIT; fix or remove it"; exit 1
  fi
  for p in asm/bin src/assets src/vendor/tamp; do
    [ -e "$WT/$p" ] && [ ! -L "$WT/$p" ] && rm -rf "${WT:?}/$p"
    [ -e "$WT/$p" ] || ln -s "$ROOT/$p" "$WT/$p"
  done
  build "$ROOT/port/unix/build-base" "$WT" -DCMAKE_BUILD_TYPE=Release -DEB_WERROR=ON "${WIDE[@]}"
fi
# The gates' vanilla reference: the same upstream source packed by this checkout's ebtools
# (which fix the bank C3 text remap). Only differs from build-base in the bus/attract cases.
if [ "$WIN" = 0 ] && [ ! -x port/unix/build-base-fix/earthbound ]; then
  build "$ROOT/port/unix/build-base-fix" "$ROOT/../ebsrc-base" -DCMAKE_BUILD_TYPE=Release -DEB_WERROR=ON "${WIDE[@]}"
fi

log "current tree builds"
build port/unix/build-wide "$ROOT" -DCMAKE_BUILD_TYPE=Release -DEB_WERROR=ON "${WIDE[@]}"
build port/unix/build "$ROOT" -DCMAKE_BUILD_TYPE=Release -DEB_WERROR=ON -DEB_VIEWPORT_WIDTH=256 -DEB_VIEWPORT_HEIGHT=224
if [ "$WIN" = 1 ]; then
  if [ -x "$MSYS2/clang64/bin/clang.exe" ]; then
    # MinGW gcc has no ASan runtime; clang 23 warns about a write-only global, hence no -Werror
    PATH="$MSYS2/clang64/bin:$PATH" build port/unix/build-debug "$ROOT" -DCMAKE_C_COMPILER=clang -DEB_WERROR=OFF       -DCMAKE_BUILD_TYPE=Debug -DENABLE_ASAN=ON -DENABLE_UBSAN=ON "${WIDE[@]}"
  else
    log "no CLANG64 clang in $MSYS2: skipped build-debug (pacman -S mingw-w64-clang-x86_64-{clang,compiler-rt,SDL2})"
  fi
else
  build port/unix/build-debug "$ROOT" -DCMAKE_BUILD_TYPE=Debug -DENABLE_ASAN=ON -DENABLE_UBSAN=ON "${WIDE[@]}"
fi

log "setup done"

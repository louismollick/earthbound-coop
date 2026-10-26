#!/usr/bin/env bash
# Co-op gates (PLAN.md "Gates"). Prints one verdict line, exits non-zero on failure.
#   scripts/coop-gates.sh             gates 1-4: -Werror builds at 320x240 and 256x224, ruff, pytest,
#                                     regress compare vs build-base, co-op scenario suite
#   scripts/coop-gates.sh --framehash also run regress framehash vs build-base (renderer/camera changes)
#                                     and check every frame against the cross-OS digest
#                                     (playtest/regress/framedigest/base.json)
#   scripts/coop-gates.sh --full      also gates 5-6: co-op suite under ASan+UBSan (build-debug),
#                                     the mutable-globals audit test on that build, savestate
#                                     continuity (every scenario restored in a fresh process, ~40 s)
#                                     and a contact sheet of scenario screenshots to read
# Logs go to playtest/out/gates/. Run scripts/coop-setup.sh once first.
#
# Windows (Git Bash, MSYS2 at $EB_MSYS2, default C:\msys64; docs/coop-windows.md): the
# builds use UCRT64 gcc, the ASan+UBSan build CLANG64 clang (MinGW gcc has no ASan) without
# -Werror (clang 23 flags a write-only global ported from the asm). There is no Windows
# baseline build: gate 3 checks the tracked text goldens (regress.py check) and --framehash
# the frame digest, both recorded from vanilla builds on other machines.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# In a git worktree, the venv, saves and base build live in the main checkout.
MAIN="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
WIN=0; EXE=""
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) WIN=1; EXE=".exe" ;; esac
if [ "$WIN" = 1 ]; then
  MSYS2="${EB_MSYS2:-/c/msys64}"
  [ -x "$MSYS2/ucrt64/bin/gcc.exe" ] || { echo "VERDICT FAIL: no MSYS2 UCRT64 gcc in $MSYS2 (set EB_MSYS2)"; exit 1; }
  export PATH="$MSYS2/ucrt64/bin:$PATH" PYTHONUTF8=1 CMAKE_GENERATOR=Ninja
  # shellcheck disable=SC1091
  source "$MAIN/.venv/Scripts/activate"
else
  # shellcheck disable=SC1091
  source "$MAIN/.venv/bin/activate"
fi
NPROC="$(sysctl -n hw.ncpu 2>/dev/null || nproc)"
OUT="$ROOT/playtest/out/gates"; mkdir -p "$OUT"
FULL=0; FRAMEHASH=0
for a in "$@"; do
  case "$a" in --full) FULL=1 ;; --framehash) FRAMEHASH=1 ;; *) echo "unknown arg $a"; exit 2 ;; esac
done
# The vanilla reference: upstream d32c421 built with this fork's ebtools, which fix the
# bank C3 text remap (the Runaway Five bus). build-base (pure upstream) differs from it
# only in `bus` and `attract`; see docs/coop-log.md.
BASE="${EB_BASE_BIN:-$MAIN/port/unix/build-base-fix/earthbound$EXE}"
WIDE="$ROOT/port/unix/build-wide/earthbound$EXE"
DEBUG="$ROOT/port/unix/build-debug/earthbound$EXE"
[ "$WIN" = 1 ] || [ -x "$BASE" ] || { echo "VERDICT FAIL: no $BASE (run scripts/coop-setup.sh)"; exit 1; }

FAILED=()
gate() {  # gate NAME CMD...: run CMD, log to $OUT/NAME.log
  local name="$1"; shift
  printf '%-12s ' "$name"
  if "$@" >"$OUT/$name.log" 2>&1; then echo ok; else echo "FAIL ($OUT/$name.log)"; FAILED+=("$name"); fi
}
build() { cmake -S port/unix -B "$1" "${@:2}" && cmake --build "$1" -j"$NPROC"; }
# The sanitizer build and its runs: CLANG64 first on PATH on Windows
debug_env() { if [ "$WIN" = 1 ]; then PATH="$MSYS2/clang64/bin:$PATH" "$@"; else "$@"; fi; }
DEBUG_ARGS=(-DCMAKE_BUILD_TYPE=Debug -DENABLE_ASAN=ON -DENABLE_UBSAN=ON -DEB_VIEWPORT_WIDTH=320 -DEB_VIEWPORT_HEIGHT=240)
[ "$WIN" = 1 ] && DEBUG_ARGS+=(-DCMAKE_C_COMPILER=clang -DEB_WERROR=OFF)

gate build-wide build port/unix/build-wide -DCMAKE_BUILD_TYPE=Release -DEB_WERROR=ON -DEB_VIEWPORT_WIDTH=320 -DEB_VIEWPORT_HEIGHT=240
gate build-native build port/unix/build -DCMAKE_BUILD_TYPE=Release -DEB_WERROR=ON -DEB_VIEWPORT_WIDTH=256 -DEB_VIEWPORT_HEIGHT=224
gate ruff sh -c "ruff check . -q && ruff format --check . -q"
gate pytest python -m pytest tests -q -x
if [ "$WIN" = 1 ]; then
  gate regress python playtest/regress.py check main --text --bin "$WIDE"
else
  gate regress python playtest/regress.py compare "$BASE" "$WIDE"
  [ "$FRAMEHASH" = 1 ] && gate framehash python playtest/regress.py framehash "$BASE" "$WIDE"
fi
[ "$FRAMEHASH" = 1 ] && gate framedigest python playtest/framedigest.py check base "$WIDE"
gate coop env EB_BIN="$WIDE" python playtest/coop/run_all.py

if [ "$FULL" = 1 ]; then
  gate build-debug debug_env build port/unix/build-debug "${DEBUG_ARGS[@]}"
  gate coop-asan debug_env env EB_BIN="$DEBUG" EB_COOP_SANITIZE=1 python playtest/coop/run_all.py
  gate globals debug_env python -m pytest tests/test_mutable_globals.py -q
  gate continuity env EB_BIN="$WIDE" python playtest/coop/run_all.py --continuity cold
  gate sheet python playtest/coop/run_all.py --sheet-only "$OUT/contact.png"
  [ -f "$OUT/contact.png" ] && echo "contact sheet: $OUT/contact.png (read it: gate 6 is a human/agent check)"
fi

if [ ${#FAILED[@]} -eq 0 ]; then echo "VERDICT PASS"; exit 0; fi
echo "VERDICT FAIL: ${FAILED[*]}"; exit 1

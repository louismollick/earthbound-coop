#!/usr/bin/env bash
# Co-op gates (PLAN.md "Gates"). Prints one verdict line, exits non-zero on failure.
#   scripts/coop-gates.sh             gates 1-4: -Werror builds at 320x240 and 256x224, ruff, pytest,
#                                     regress compare vs build-base, co-op scenario suite
#   scripts/coop-gates.sh --framehash also run regress framehash vs build-base (renderer/camera changes)
#   scripts/coop-gates.sh --full      also gates 5-6: co-op suite under ASan+UBSan (build-debug),
#                                     the mutable-globals audit test on that build, savestate
#                                     continuity (every scenario restored in a fresh process, ~40 s)
#                                     and a contact sheet of scenario screenshots to read
# Logs go to playtest/out/gates/. Run scripts/coop-setup.sh once first.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# In a git worktree, the venv, saves and base build live in the main checkout.
MAIN="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
# shellcheck disable=SC1091
source "$MAIN/.venv/bin/activate"
NPROC="$(sysctl -n hw.ncpu 2>/dev/null || nproc)"
OUT="$ROOT/playtest/out/gates"; mkdir -p "$OUT"
FULL=0; FRAMEHASH=0
for a in "$@"; do
  case "$a" in --full) FULL=1 ;; --framehash) FRAMEHASH=1 ;; *) echo "unknown arg $a"; exit 2 ;; esac
done
BASE="${EB_BASE_BIN:-$MAIN/port/unix/build-base/earthbound}"
WIDE="$ROOT/port/unix/build-wide/earthbound"
[ -x "$BASE" ] || { echo "VERDICT FAIL: no $BASE (run scripts/coop-setup.sh)"; exit 1; }

FAILED=()
gate() {  # gate NAME CMD...: run CMD, log to $OUT/NAME.log
  local name="$1"; shift
  printf '%-12s ' "$name"
  if "$@" >"$OUT/$name.log" 2>&1; then echo ok; else echo "FAIL ($OUT/$name.log)"; FAILED+=("$name"); fi
}
build() { cmake -S port/unix -B "$1" "${@:2}" && cmake --build "$1" -j"$NPROC"; }

gate build-wide build port/unix/build-wide -DCMAKE_BUILD_TYPE=Release -DEB_WERROR=ON -DEB_VIEWPORT_WIDTH=320 -DEB_VIEWPORT_HEIGHT=240
gate build-native build port/unix/build -DCMAKE_BUILD_TYPE=Release -DEB_WERROR=ON -DEB_VIEWPORT_WIDTH=256 -DEB_VIEWPORT_HEIGHT=224
gate ruff sh -c "ruff check . -q && ruff format --check . -q"
gate pytest python -m pytest tests -q -x
gate regress python playtest/regress.py compare "$BASE" "$WIDE"
[ "$FRAMEHASH" = 1 ] && gate framehash python playtest/regress.py framehash "$BASE" "$WIDE"
gate coop env EB_BIN="$WIDE" python playtest/coop/run_all.py

if [ "$FULL" = 1 ]; then
  gate build-debug build port/unix/build-debug -DCMAKE_BUILD_TYPE=Debug -DENABLE_ASAN=ON -DENABLE_UBSAN=ON -DEB_VIEWPORT_WIDTH=320 -DEB_VIEWPORT_HEIGHT=240
  gate coop-asan env EB_BIN="$ROOT/port/unix/build-debug/earthbound" EB_COOP_SANITIZE=1 python playtest/coop/run_all.py
  gate globals python -m pytest tests/test_mutable_globals.py -q
  gate continuity env EB_BIN="$WIDE" python playtest/coop/run_all.py --continuity cold
  gate sheet python playtest/coop/run_all.py --sheet-only "$OUT/contact.png"
  [ -f "$OUT/contact.png" ] && echo "contact sheet: $OUT/contact.png (read it: gate 6 is a human/agent check)"
fi

if [ ${#FAILED[@]} -eq 0 ]; then echo "VERDICT PASS"; exit 0; fi
echo "VERDICT FAIL: ${FAILED[*]}"; exit 1

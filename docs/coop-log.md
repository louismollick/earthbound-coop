# Co-op build log

One entry per PLAN.md item: what changed, gate results, decisions and deviations.

## M0 Foundation

### scripts/coop-setup.sh (2026-10-26)
- Idempotent setup: checks tools, submodules, `uv venv --seed --python 3.12 .venv`, installs ebtools + pytest + numpy, fetches any missing story save from fantasyanime (`earthbsaveNN.zip`), extracts assets once, builds `build-base` (worktree `../ebsrc-base` at d32c421, 320x240, only when missing), `build-wide` (320x240, -Werror), `build` (256x224, -Werror), `build-debug` (320x240, ASan+UBSan).
- Fresh run 1m52s; second run 32s and rebuilds nothing but the incremental current-tree builds.
- Baseline: `regress.py compare build-base build-wide` = 0 of 32 cases differ (the `bus` bug is in both, so it doesn't show as a diff).

### scripts/coop-gates.sh (2026-10-26)
- Gates 1-4 (both -Werror builds, ruff, pytest, regress compare vs build-base, co-op suite), `--framehash`, `--full` (ASan+UBSan co-op suite and a contact sheet at `playtest/out/gates/contact.png`). One verdict line, non-zero exit on failure. ~50 s.
- Setup now installs ruff 0.15.4 (the pre-commit pin) into the venv.

### Four pads, per-Player scripts, join model, scenario runner (a2119053)
- `platform_input_get_pad_n/_new_n`; unix has per-Player pads, P2 keyboard layout IJKL/U/O/P/[, SDL GameControllers in connection order. Other ports return P1 for 0.
- Script syntax: `P2 10 RIGHT`, `press P3 A`, `until text 60 P4 START*`, sticky `hold P2 RIGHT` / `release P2`. STATE prints `PLAYERS P1:joined owns=... walker=... pos=(x,y) | ...`.
- `src/coop/coop.{h,c}`: CoopState (17 bytes, SECTION_COOP): join order, joined, leave-hold counters, hero owners. Start joins, Select+Start 120 frames leaves, `--players N`.
- `playtest/coop/run_all.py` + 6 scenarios (bedroom join, `--players`, leave, savestate across processes, prefix forms at 4P, full-Party ownership on 27-Kraken).
- Gates: PASS. regress 0/32 differ, framehash 0 changed frames over 31 cases, pytest 1827 passed / 5 skipped, co-op 6/6, ASan+UBSan 6/6 clean. Contact sheet read: shots match state.
- Untested: the IJKL layout and real controllers (need a windowed session), the arm builds (no toolchain here). The external gw firmware repo will need `src/coop/coop.c` and the `_n` functions.

### M0 adversarial review (GPT 6.1 Sol, one pass) and fixes
- Bug: join edges came from the platform's unserialized `pad_prev`. Fixed: `CoopState.prev_held[4]` (serialized; struct now 26 bytes) and `coop_tick(held)` computes edges itself.
- Bug: capture-unwind frames reset leave counters and could fake a fresh Start (rejoin). Fixed: `coop_tick` is skipped on unwind frames, and paused script frames keep sticky holds. New scenario `p2_capture_holds` (failed before, passes after).
- Risk: out-of-order ownership was only checked with Ness present (a by-Player-number deal passed). Fixed: `ownership_full_party` now joins P3, P4, P2 with all four Heroes, has a middle Player leave and rejoin, and asserts every owner.
- Risk: setup could reuse a moved `../ebsrc-base`. Fixed: setup checks it's a clean checkout of d32c421.
- Gates `--full --framehash`: PASS (regress 0 differ, framehash 0 changed frames, co-op 7/7, ASan+UBSan clean).

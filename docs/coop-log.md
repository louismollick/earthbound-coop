# Co-op build log

One entry per PLAN.md item: what changed, gate results, decisions and deviations.

## M0 Foundation

### scripts/coop-setup.sh (2026-10-26)
- Idempotent setup: checks tools, submodules, `uv venv --seed --python 3.12 .venv`, installs ebtools + pytest + numpy, fetches any missing story save from fantasyanime (`earthbsaveNN.zip`), extracts assets once, builds `build-base` (worktree `../ebsrc-base` at d32c421, 320x240, only when missing), `build-wide` (320x240, -Werror), `build` (256x224, -Werror), `build-debug` (320x240, ASan+UBSan).
- Fresh run 1m52s; second run 32s and rebuilds nothing but the incremental current-tree builds.
- Baseline: `regress.py compare build-base build-wide` = 0 of 32 cases differ (the `bus` bug is in both, so it doesn't show as a diff).

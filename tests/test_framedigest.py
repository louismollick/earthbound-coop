"""playtest/framedigest.py: ``check`` fails unless every selected case ran and matches.

A run that stops before the end of its script is never accepted either.

The comparison tests use a tiny fake digest and results (no game). The truncated-run test plays a
two-line script on ``$EB_BIN`` or ``port/unix/build-wide/earthbound`` and skips when it isn't built.
"""

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")  # framehash; not a declared dependency

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "playtest"))
import framedigest  # noqa: E402

BIN = Path(os.environ.get("EB_BIN", ROOT / "port" / "unix" / "build-wide" / "earthbound"))
WANT = {
    "viewport": "320x240",
    "cases": {"alpha": {"frames": 10, "sha256": "aa"}, "beta": {"frames": 20, "sha256": "bb"}},
}


def res(frames, sha, size=(320, 240)):
    return {"frames": frames, "sha256": sha, "size": list(size)}


def test_all_match():
    bad, total, _ = framedigest.compare(WANT, {"alpha": res(10, "aa"), "beta": res(20, "bb")}, {}, [])
    assert (bad, total) == (0, 2)


def test_k_excludes_unselected_cases():
    assert framedigest.compare(WANT, {"alpha": res(10, "aa")}, {}, ["alp"])[0] == 0


def test_empty_selection_fails():
    assert framedigest.compare(WANT, {}, {}, ["nothing"])[0] == 1
    assert framedigest.compare({"viewport": "320x240", "cases": {}}, {}, {}, [])[0] == 1


def test_recorded_case_not_run_fails():
    bad, _, lines = framedigest.compare(WANT, {"alpha": res(10, "aa")}, {}, [])
    assert bad == 1
    assert any("beta" in ln for ln in lines)


def test_unrecorded_case_fails():
    results = {"alpha": res(10, "aa"), "beta": res(20, "bb"), "gamma": res(5, "cc")}
    assert framedigest.compare(WANT, results, {}, [])[0] == 1


def test_diff_viewport_and_failed_run_fail():
    assert framedigest.compare(WANT, {"alpha": res(11, "aa"), "beta": res(20, "bb")}, {}, [])[0] == 1
    assert framedigest.compare(WANT, {"alpha": res(10, "aa", (256, 224)), "beta": res(20, "bb")}, {}, [])[0] == 1
    assert framedigest.compare(WANT, {"alpha": res(10, "aa")}, {"beta": "TIMEOUT"}, [])[0] == 1


@pytest.mark.skipif(not BIN.exists(), reason=f"{BIN} not built")
@pytest.mark.parametrize("args, ok", [([], True), (["--frames", "2"], False)])
def test_run_must_reach_end_of_script(tmp_path, args, ok):
    case = {
        "name": "short",
        "save": None,
        "script": "wait 30\nsync rg-end\n",
        "args": args,
        "timeout": 60.0,
        "end_marker": "SYNC rg-end ",
    }
    _, digest, status = framedigest.run_case(case, BIN, tmp_path)
    assert (digest is not None) == ok, status
    if not ok:
        assert status == "ended before the end of the script"

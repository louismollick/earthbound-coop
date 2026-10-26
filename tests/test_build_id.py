"""port/unix/net/build_id.cmake: the netplay revision depends on the tree, never on git config.

Builds a throwaway repo, dirties it, and runs the script under different user configs (git reads
``GIT_CONFIG_COUNT``/``KEY``/``VALUE`` like ``-c``); a git that fails after HEAD resolves must give
``+unknown``, not a clean revision.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "port" / "unix" / "net" / "build_id.cmake"
GIT, CMAKE = shutil.which("git"), shutil.which("cmake")

pytestmark = pytest.mark.skipif(not (GIT and CMAKE), reason="needs cmake and git")


def git(repo, *args):
    subprocess.run([GIT, "-C", str(repo), *args], check=True, capture_output=True)  # noqa: S603


def build_id(repo, tmp_path, config=None, path=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG")}
    if config:
        env["GIT_CONFIG_COUNT"] = str(len(config))
        for i, (k, v) in enumerate(config.items()):
            env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"] = k, v
    if path:
        env["PATH"] = path
    out = tmp_path / "net_build_id.h"
    out.unlink(missing_ok=True)
    p = subprocess.run(  # noqa: S603
        [CMAKE, f"-DROOT={repo}", f"-DOUT={out}", "-P", str(SCRIPT)], env=env, capture_output=True, text=True
    )
    assert p.returncode == 0, p.stderr
    return re.search(r'NET_GAME_REVISION "([^"]*)"', out.read_text()).group(1), p.stderr


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "src" / "a.c").write_text("int a;\n")
    (r / "src" / "b.c").write_text("int b;\n")
    git(r, "init", "-q")
    git(r, "add", ".")
    git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return r


def test_clean_tree_is_the_commit(repo, tmp_path):
    rev, _ = build_id(repo, tmp_path)
    assert re.fullmatch(r"[0-9a-f]{12}", rev)


def test_dirty_id_ignores_git_config(repo, tmp_path):
    (repo / "src" / "a.c").write_text("int a = 1;\n")
    (repo / "src" / "b.c").unlink()
    (repo / "src" / "new.c").write_text("int n;\n")
    ids = {
        build_id(repo, tmp_path, cfg)[0]
        for cfg in (
            None,
            {"color.ui": "always"},
            {"color.diff": "always", "diff.noprefix": "true", "diff.mnemonicPrefix": "true"},
            {"diff.relative": "true", "diff.renames": "copies", "core.quotepath": "true"},
        )
    }
    assert len(ids) == 1, ids
    assert "+dirty." in ids.pop()


def test_different_edits_differ(repo, tmp_path):
    (repo / "src" / "a.c").write_text("int a = 1;\n")
    one, _ = build_id(repo, tmp_path)
    (repo / "src" / "a.c").write_text("int a = 2;\n")
    two, _ = build_id(repo, tmp_path)
    assert one != two


@pytest.mark.skipif(sys.platform == "win32", reason="the failing-git shim is a shell script")
def test_git_failure_is_unknown(repo, tmp_path):
    (repo / "src" / "a.c").write_text("int a = 1;\n")
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "git").write_text(f'#!/bin/sh\ncase "$*" in *rev-parse*) exec "{GIT}" "$@";; esac\nexit 1\n')
    (shim / "git").chmod(0o755)
    rev, err = build_id(repo, tmp_path, path=f"{shim}{os.pathsep}{os.environ['PATH']}")
    assert rev.endswith("+unknown"), rev
    assert "build_id" in err

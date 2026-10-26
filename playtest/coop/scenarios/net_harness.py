"""netrun.py's command line fails a run that never happened and passes a real one.

A "game" that exits at once (``true`` exits 0, ``false`` 1) must make netrun.py
exit non-zero; a short real 2-Player run must make it exit 0.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from lib import expect

NETRUN = Path(__file__).resolve().parents[2] / "net" / "netrun.py"


def netrun_cli(ctx, binary, name, frames):
    out = ctx.dir / name
    cmd = [sys.executable, str(NETRUN), "--bin", binary, "--frames", str(frames), "--timeout", "120", "--out", str(out)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180)  # noqa: S603


def run(ctx):
    for prog in ("true", "false"):
        exe = shutil.which(prog)
        expect(exe, f"a {prog} binary", exe)
        p = netrun_cli(ctx, exe, prog, 600)
        expect(p.returncode != 0, f"netrun.py to fail when the game is `{prog}`", p.stdout[-300:])
    p = netrun_cli(ctx, ctx.bin, "real", 900)
    expect(p.returncode == 0 and "PASS" in p.stdout, "a real 900-frame run to pass", p.stdout[-500:])

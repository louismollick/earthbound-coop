"""Shared bits of the net_* scenarios: import playtest/net/netrun.py, register shots."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "net"))
import netrun  # noqa: E402,F401
from lib import ScenarioError  # noqa: E402


def check(fn, *args, **kw):
    """Run a netrun check, turning its NetError into a ScenarioError."""
    try:
        return fn(*args, **kw)
    except netrun.NetError as e:
        raise ScenarioError(str(e)) from None


def shots(ctx, result, frame, label):
    """Put every machine's EB_NET_SHOT_FRAMES shot of ``frame`` on the contact sheet; they must be identical."""
    paths = [m.dir / f"net-{frame}.png" for m in result.machines if (m.dir / f"net-{frame}.png").exists()]
    if len(paths) < 2:
        raise ScenarioError(f"expected a net-{frame}.png from every machine, found {paths}")
    first = paths[0].read_bytes()
    for p in paths[1:]:
        if p.read_bytes() != first:
            raise ScenarioError(f"expected identical screens at frame {frame}, {p} differs from {paths[0]}")
    for p in paths:
        ctx.important.append({"path": str(p), "label": f"{ctx.name}: {label} ({p.parent.name})"})
    (ctx.dir / "important.json").write_text(json.dumps(ctx.important, indent=1))

"""Online Companion: the client is absent (07-InHappy: Ness alone) and walks its Mr. Saturn.

The client's random walk moves Mr. Saturn and its A presses Check/Talk from it (Look-only text or the
Mr. Saturn sound); the Host walks Ness. Every hash point agrees and the final screens are identical.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _net import check, netrun, shots
from lib import expect


def run(ctx):
    end = 3000
    env = {"EB_NET_SHOT_FRAMES": str(end - 60)}
    r = netrun.run(
        ctx.bin,
        ctx.dir / "run",
        "07-InHappy",
        netrun.boot_then(netrun.random_play(31, end, menus=False)),
        [netrun.Peer("p2", netrun.random_play(32, end, a_rate=0.15), env=env)],
        netrun.Net(latency=30, jitter=10, loss=0.01, seed=8),
        input_delay=6,
        end_frame=end,
        timeout=300,
        host_env=env,
        wait_players=2,
    )
    host = r.machines[0]
    check(r.check_clean, end)
    check(r.check_agreement, min_common=end // 60 - 2)
    seen = set()
    for _, players in host.syncs.values():
        seg = next(x for x in players.split("|") if "P2:" in x)
        if "walker=Mr. Saturn companion" in seg:
            m = re.search(r"pos=\((\d+),(\d+)\)", seg)
            if m:
                seen.add(m.groups())
    expect(len(seen) > 3, "the client's Mr. Saturn to walk", sorted(seen)[:5])
    expect(host.took_focus(2), "the client to take the lock (Check/Talk from Mr. Saturn)", "never")
    shots(ctx, r, end - 60, "Host P1 Ness, client P2 Mr. Saturn")

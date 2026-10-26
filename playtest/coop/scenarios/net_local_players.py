"""Mixed local + online: the Host has 2 local Players (P1, P2), a client has 1 (P3).

All three walk (the Fourside save has Ness, Paula and Jeff, so each Player has a
Walker) and the Session stays in sync; the client is assigned P3.
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
        "16-Fourside",
        netrun.boot_then(netrun.random_play(20, end, players=2)),
        [netrun.Peer("p3", netrun.random_play(21, end), env=env)],
        netrun.Net(latency=30, jitter=10, loss=0.01, seed=6),
        input_delay=8,
        end_frame=end,
        timeout=300,
        host_env=env,
        wait_players=3,
        host_local_players=2,
    )
    host, p3 = r.machines
    check(r.check_clean, end)
    check(r.check_agreement, min_common=end // 60 - 2)
    expect(p3.event(r"^NET WELCOME P3\+0 "), "the client to be P3", p3.events[:2])
    first = host.syncs[min(f for f in host.syncs if f > 0)][1]
    expect("P2:joined" in first, "the Host's second local Player joined from the start", first)
    # Every Walker moved at some point
    for p in (1, 2, 3):
        seen = set()
        for _, players in host.syncs.values():
            seg = next(x for x in players.split("|") if f"P{p}:" in x)
            m = re.search(r"pos=\((\d+),(\d+)\)", seg)
            if m:
                seen.add(m.groups())
        expect(len(seen) > 3, f"P{p}'s Walker to move", sorted(seen)[:5])
    shots(ctx, r, end - 60, "Host P1+P2, client P3")

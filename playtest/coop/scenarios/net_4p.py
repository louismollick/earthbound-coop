"""Four Players in one Session: P2 from the start, P3 and P4 join later. Everyone agrees."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _net import check, netrun, shots
from lib import expect


def run(ctx):
    end = 3600
    env = {"EB_NET_SHOT_FRAMES": str(end - 60)}
    r = netrun.run(
        ctx.bin,
        ctx.dir / "run",
        "16-Fourside",
        netrun.boot_then(netrun.random_play(8, end)),
        [
            netrun.Peer("p2", netrun.random_play(9, end), env=env),
            netrun.Peer("p3", netrun.random_play(10, end), start_after=900, env=env),
            netrun.Peer("p4", netrun.random_play(11, end), start_after=1800, env=env),
        ],
        netrun.Net(latency=40, jitter=15, loss=0.01, seed=4),
        input_delay=10,
        end_frame=end,
        timeout=400,
        host_env=env,
        wait_players=2,
    )
    host = r.machines[0]
    check(r.check_clean, end)
    check(r.check_agreement, min_common=10)
    for p in (3, 4):
        ev = host.event(rf"^NET JOIN P{p} f=")
        expect(ev, f"P{p} to join", host.events)
        expect(int(re.search(r"f=(\d+)", ev).group(1)) >= 900, f"P{p} to join mid-game", ev)
    last = host.syncs[max(host.syncs)][1]
    expect(all(f"P{p}:joined" in last for p in (1, 2, 3, 4)), "all four Players joined at the end", last)
    shots(ctx, r, end - 60, "4 Players")

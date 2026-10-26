"""2-Player Session through a bad network: 100 ms each way, +-30 ms jitter, 2% loss. Zero desyncs.

The default run is 3000 frames (about 30 s). ``NET_LONG=1`` runs the 30-game-minute
soak (108000 frames) with a 30-frame input delay to keep the wall time down; the
headless game is uncapped, so it runs as fast as the round trip allows.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _net import check, netrun, shots
from lib import expect


def run(ctx):
    long = os.environ.get("NET_LONG") == "1"
    frames = 108000 if long else 3000
    delay = 30 if long else 20
    env = {"EB_NET_SHOT_FRAMES": "2400"}
    r = netrun.run(
        ctx.bin,
        ctx.dir / "run",
        "16-Fourside",
        netrun.boot_then(netrun.random_play(1, frames, menus=False)),
        [netrun.Peer("p2", netrun.random_play(2, frames, a_rate=0.12), env=env)],
        netrun.Net(latency=100, jitter=30, loss=0.02, seed=1),
        input_delay=delay,
        end_frame=frames,
        timeout=4 * 3600 if long else 300,
        host_env=env,
        wait_players=2,
    )
    host, p2 = r.machines
    summary = {
        "frames": frames,
        "input_delay": delay,
        "wall_s": round(r.wall, 1),
        "desyncs": r.desyncs,
        "hash_points": len(r.agreement(host, p2)[0]),
        "proxy (forwarded, dropped, reordered)": r.proxy_stats,
    }
    (ctx.dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(f"net_soak: {summary}", flush=True)
    check(r.check_clean, frames)
    check(r.check_agreement, min_common=frames // 60 - 2)
    fwd, dropped, reordered = next(iter(r.proxy_stats.values()))
    expect(dropped > 0 and reordered > 0, "the proxy to drop and reorder packets", (fwd, dropped, reordered))
    last = host.syncs[max(host.syncs)][1]
    expect("P2:joined" in last, "P2 joined at the end", last)
    expect(host.took_focus(2), "P2 to open a menu (take the input focus) at some point", last)
    shots(ctx, r, 2400, "frame 2400")

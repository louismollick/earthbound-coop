"""A Player's machine dies, the Session drops them, and they rejoin.

The client is SIGKILLed (no goodbye); the Session stalls for 10 s, drops P2, and
the restarted machine joins again as a fresh join.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _net import check, netrun, shots
from lib import expect


def frame_of(m, pattern):
    ev = m.event(pattern)
    expect(ev, f"a host event matching {pattern!r}", m.events[-6:])
    return int(re.search(r"f=(\d+)", ev).group(1))


def run(ctx):
    end = 4000
    env = {"EB_NET_SHOT_FRAMES": str(end - 60)}
    r = netrun.run(
        ctx.bin,
        ctx.dir / "run",
        "05-Twoson",
        netrun.boot_then(netrun.random_play(5, end)),
        [
            netrun.Peer("p2", netrun.random_play(6, end), kill_after=1200),
            netrun.Peer("p2-again", netrun.random_play(7, end), start_on=r"^NET LEAVE P2", env=env),
        ],
        netrun.Net(latency=20, jitter=5, loss=0.01, seed=3),
        input_delay=6,
        end_frame=end,
        timeout=300,
        host_env=env,
        wait_players=2,
    )
    host, p2, again = r.machines
    check(r.check_clean, end)
    expect(p2.killed, "the first P2 to be killed", p2.rc)
    expect(host.event(r"^NET DROP P2 stopped responding"), "the Host to drop P2 for silence", host.events)
    left = frame_of(host, r"^NET LEAVE P2 f=")
    # Nothing ran while the Session waited for the dead machine
    expect(1200 <= left <= 1200 + 60, "P2 to leave right where its machine died (frame 1200+)", left)
    expect(again.event(r"^NET WELCOME P2\+0 "), "the restarted machine to be P2 again", again.events)
    joins = [int(re.search(r"f=(\d+)", e).group(1)) for e in host.events if e.startswith("NET JOIN P2 ")]
    expect(len(joins) == 2, "P2 to join twice", joins)
    rejoined = joins[1]
    expect(rejoined > left, f"the rejoin after the leave at {left}", rejoined)
    gap = [f for f in host.syncs if left < f < rejoined]
    expect(all("P2:-" in host.syncs[f][1] for f in gap), "P2 not joined between leave and rejoin", gap[:1])
    for m in (p2, again):
        common, bad = r.agreement(host, m)
        expect(common and not bad, f"{m.name} to agree with the Host on every shared frame", bad[:3])
    after = r.agreement(host, again)[0]
    expect(after[-1] - after[0] >= 1000, "1000+ frames of agreement after the rejoin", (after[0], after[-1]))
    expect("P2:joined" in host.syncs[max(host.syncs)][1], "P2 joined at the end", host.syncs[max(host.syncs)])
    shots(ctx, r, end - 60, "after a rejoin")

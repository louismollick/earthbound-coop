"""A Player joins a running Session mid-game (Fourside, after the Host has played 1500 frames).

The joiner gets the Host's savestate + SRAM at a root boundary and resumes on the
same frame; its PLAYERS line and state hashes must match the Host's on every hash
point from the join on, for at least 1000 frames.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _net import check, netrun, shots
from lib import expect


def run(ctx):
    end = 6000
    env = {"EB_NET_SHOT_FRAMES": str(end - 60)}
    r = netrun.run(
        ctx.bin,
        ctx.dir / "run",
        "16-Fourside",
        netrun.boot_then(netrun.random_play(3, end, menus=False)),
        [netrun.Peer("p2", netrun.random_play(4, end, a_rate=0.12), start_after=1500, env=env)],
        netrun.Net(latency=30, jitter=10, loss=0.01, seed=2),
        input_delay=8,
        end_frame=end,
        timeout=300,
        host_env=env,
    )
    host, p2 = r.machines
    check(r.check_clean, end)
    ev = host.event(r"^NET JOIN P2 f=(\d+)")
    expect(ev, "a JOIN P2 event on the Host", host.events)
    j = int(re.search(r"f=(\d+)", ev).group(1))
    expect(j >= 1500 and j + 1000 <= end, f"the join between frame 1500 and {end - 1000}", j)
    expect(p2.event(rf"^NET LOADED P2 f={j}$"), f"the joiner loaded the game at frame {j}", p2.events)
    common, bad = r.agreement(host, p2)
    expect(not bad, "the joiner to agree with the Host on every shared frame", bad[:3])
    # A hash point on the JOIN frame itself is taken before the event applies, so "after" is
    # strictly later frames (the join frame depends on wall-clock timing: it can land on a
    # multiple of the hash interval).
    after = [f for f in common if f > j]
    expect(after and after[-1] - after[0] >= 1000, "1000+ frames of agreement after the join", after[-1:])
    before = [f for f in host.syncs if f < j]
    expect(all("P2:-" in host.syncs[f][1] for f in before), "P2 not joined before the join", before[-1:])
    expect(all("P2:joined" in host.syncs[f][1] for f in after), "P2 joined after the join", after[:1])
    expect(host.took_focus(2), "the joiner to open a menu (take the input focus)", host.syncs[max(host.syncs)])
    shots(ctx, r, end - 60, "after a mid-game join")

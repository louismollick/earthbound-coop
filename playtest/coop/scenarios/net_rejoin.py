"""A Player's machine dies, the Session drops them, and they rejoin from the same endpoint.

The client is SIGKILLed (no goodbye) at frame 1200 and restarted at once through
the same proxy link, so the Host sees the same address and port. The Host must
not let the new process's HELLO replace the open connection: the Session stalls
for 10 s, drops P2 for silence, and only then admits the restarted machine as a
fresh join.

Once P2 is back, the proxy replays the old connection's packets from the same
endpoint (HELLOs, INPUTs, and a BYE built from their header) and the Host's old
packets to the new client. They carry the old connection's epoch, so neither side
may act on them: no second DROP or LEAVE, and the new P2 plays on to the end.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _net import check, netrun, shots
from lib import expect

replayed = {}


def frame_of(m, pattern):
    ev = m.event(pattern)
    expect(ev, f"a host event matching {pattern!r}", m.events[-6:])
    return int(re.search(r"f=(\d+)", ev).group(1))


def replay_old(ctx):
    """Replay the dead connection's traffic on P2's link (both directions)."""
    port = ctx.ports["p2"]
    link = ctx.proxy.link(port)
    old = link.log[0][1]  # the first client's address
    up = link.received("up", old)
    down = link.received("down", old)
    stale_up = up[:10] + up[-300:] + [netrun.bye_like(up[-1])] * 3
    stale_down = down[-300:]
    ctx.proxy.inject(port, "up", stale_up, spacing=0.002)
    ctx.proxy.inject(port, "down", stale_down, spacing=0.002)
    replayed.update(new_client=link.client != old, up=len(stale_up), down=len(stale_down))


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
            netrun.Peer("p2-again", netrun.random_play(7, end), start_after_exit="p2", link="p2", env=env),
        ],
        netrun.Net(latency=20, jitter=5, loss=0.01, seed=3),
        input_delay=6,
        end_frame=end,
        timeout=300,
        host_env=env,
        wait_players=2,
        triggers=[netrun.Trigger(r"^NET JOIN P2 f=", replay_old, nth=2)],
    )
    host, p2, again = r.machines
    check(r.check_clean, end)
    expect(p2.killed, "the first P2 to be killed", p2.rc)
    session = host.events[: host.events.index(f"NET END f={end}")]  # after END, clients say goodbye
    drops = [e for e in session if e.startswith("NET DROP")]
    expect(drops == ["NET DROP P2 stopped responding"], "one DROP, for silence", drops)
    expect(
        any(e.startswith("NET HELLO from") and "waits" in e for e in session),
        "the restarted machine's HELLO to wait while the old connection is open",
        session,
    )
    leaves = [e for e in host.events if e.startswith("NET LEAVE")]
    expect(len(leaves) == 1, "one LEAVE", leaves)
    left = frame_of(host, r"^NET LEAVE P2 f=")
    # Nothing ran while the Session waited for the dead machine
    expect(1200 <= left <= 1200 + 60, "P2 to leave right where its machine died (frame 1200+)", left)
    expect(again.event(r"^NET WELCOME P2\+0 "), "the restarted machine to be P2 again", again.events)
    joins = [int(re.search(r"f=(\d+)", e).group(1)) for e in host.events if e.startswith("NET JOIN P2 ")]
    expect(len(joins) == 2, "P2 to join twice", joins)
    rejoined = joins[1]
    expect(rejoined > left, f"the rejoin after the leave at {left}", rejoined)
    expect(replayed.get("new_client") and replayed.get("up", 0) > 100, "the old packets replayed", replayed)
    gap = [f for f in host.syncs if left < f < rejoined]
    expect(all("P2:-" in host.syncs[f][1] for f in gap), "P2 not joined between leave and rejoin", gap[:1])
    for m in (p2, again):
        common, bad = r.agreement(host, m)
        expect(common and not bad, f"{m.name} to agree with the Host on every shared frame", bad[:3])
    after = r.agreement(host, again)[0]
    expect(after[-1] - after[0] >= 1000, "1000+ frames of agreement after the rejoin", (after[0], after[-1]))
    expect("P2:joined" in host.syncs[max(host.syncs)][1], "P2 joined at the end", host.syncs[max(host.syncs)])
    shots(ctx, r, end - 60, "after a rejoin")

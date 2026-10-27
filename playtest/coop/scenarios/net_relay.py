"""Three machines play through a relay room, with the auto input delay.

The Host opens a room at the Node relay (relay/node/server.ts, which holds every
message 50 ms: ~100 ms round trips), P2 joins at once and P3 mid-game, both by the
Host's invite. Nobody passes --input-delay: the Host must raise the delay from
the measured pings before each join, and everyone must stay in sync to the end.
The Host holds the game until all three are in (--net-wait-players 3) and P3
starts 12 s late, so P2 waits past the 10 s silence timeout: over the relay its
keepalives must keep it in.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _net import check, netrun, shots
from lib import expect


def run(ctx):
    end = 4000
    env = {"EB_NET_SHOT_FRAMES": str(end - 60)}
    with netrun.Relay(delay_ms=50) as relay:
        r = netrun.run(
            ctx.bin,
            ctx.dir / "run",
            "05-Twoson",
            netrun.boot_then(netrun.random_play(50, end)),
            [
                netrun.Peer("p2", netrun.random_play(51, end), env=env),
                netrun.Peer("p3", netrun.random_play(52, end), start_after_s=12, env=env),
            ],
            input_delay=None,
            end_frame=end,
            timeout=300,
            host_env=env,
            relay=relay,
            wait_players=3,
        )
    host, p2, p3 = r.machines
    check(r.check_clean, end)
    expect(
        host.event(r"^NET HOST room=[A-Z2-9]{6} invite=ws://127\.0\.0\.1:\d+/[A-Z2-9]{6} delay=3 \(auto\)"),
        "the Host to open a room with the auto delay",
        host.events[:1],
    )
    delays = [int(m.group(1)) for e in host.events if (m := re.match(r"^NET DELAY (\d+) ", e))]
    expect(delays and max(delays) >= 7, "the auto delay to cover a ~100 ms round trip (7+ frames)", host.events)
    for m in (p2, p3):
        ev = host.event(rf"^NET JOIN P{m.name[1]} f=(\d+)")
        expect(ev, f"{m.name} to join", host.events)
        j = int(re.search(r"f=(\d+)", ev).group(1))
        common, bad = r.agreement(host, m)
        expect(not bad, f"{m.name} to agree with the Host on every shared frame", bad[:3])
        expect([f for f in common if f > j], f"{m.name} to play on after its join", common[-1:])
    shots(ctx, r, end - 60, "3 Players through a relay room")

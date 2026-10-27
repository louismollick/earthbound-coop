"""The auto input delay follows the slowest machine, up and down, while others play.

P2 is on a fast link (5 ms each way) and joins first: the delay stays at 3. P3
joins on a slow one (60 ms each way): the Host raises the delay before P3's
capture while P2 is playing. P3 then drops (killed, no goodbye) and the delay
falls back once it's gone. P2 must follow both changes (its sampling fills the
frames a longer delay skips, and skips the ones a shorter delay repeats) and stay
in sync with the Host throughout.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _net import check, netrun
from lib import expect


def run(ctx):
    end = 6000
    r = netrun.run(
        ctx.bin,
        ctx.dir / "run",
        "05-Twoson",
        netrun.boot_then(netrun.random_play(60, end)),
        [
            netrun.Peer("p2", netrun.random_play(61, end), net=netrun.Net(latency=5)),
            netrun.Peer(
                "p3", netrun.random_play(62, end), start_on=r"^NET JOIN P2", kill_after=3600, net=netrun.Net(latency=60)
            ),
        ],
        input_delay=None,
        end_frame=end,
        timeout=300,
    )
    host, p2, p3 = r.machines
    check(r.check_clean, end)
    ev = host.events

    def delays(lo=0, hi=None):
        return [int(m.group(1)) for e in ev[lo:hi] if (m := re.match(r"^NET DELAY (\d+) ", e))]

    j2, j3 = (next((i for i, e in enumerate(ev) if e.startswith(f"NET JOIN P{p} ")), None) for p in (2, 3))
    expect(j2 is not None and j3 is not None and j2 < j3, "P2, then P3 to join", ev)
    # P2's own join may already raise it a little on a loaded machine; P3's must raise it while P2 plays
    expect(max(delays(j2, j3), default=0) >= 8, "the delay to rise for P3's ~120 ms round trip", ev)
    expect(delays()[-1] == 3, "the delay to fall back to 3 once P3 is gone", ev)
    common, bad = r.agreement(host, p2)
    expect(not bad, "P2 to agree with the Host on every shared frame", bad[:3])
    leave = int(re.search(r"f=(\d+)", host.event(r"^NET LEAVE P3 f=\d+")).group(1))
    expect([f for f in common if f > leave + 600], "P2 to play on in sync after the delay fell", common[-1:])
    common3, bad3 = r.agreement(host, p3)
    expect(common3 and not bad3, "P3 to agree with the Host until it dropped", bad3[:3])

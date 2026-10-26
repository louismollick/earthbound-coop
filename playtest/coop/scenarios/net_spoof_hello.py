"""A HELLO from an active client's endpoint never evicts it.

Mid-Session the proxy sends the Host two HELLOs from P2's endpoint: a garbage one
(nonce 0, zeroed build fingerprint, 1 Player) and a copy of P2's own HELLO with
another nonce (a "restarted" client of the same build). The Host must turn the
first away and ignore the second while P2's connection is open: no DROP, no
LEAVE, and P2 plays on to the end in sync.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _net import check, netrun
from lib import expect

sent = {}


def spoof(ctx):
    port = ctx.ports["p2"]
    hello = ctx.proxy.link(port).received("up")[0]  # P2's first datagram: its HELLO
    expect(hello[3] == netrun.MSG_HELLO, "P2's first datagram to be a HELLO", hello[:8])
    restarted = hello[:4] + b"\xef\xbe\xad\xde" + hello[8:]
    garbage = hello[:4] + bytes(len(hello) - 5) + b"\x01"
    sent["n"] = 6
    ctx.proxy.inject(port, "up", [garbage, restarted] * 3, spacing=0.05)


def run(ctx):
    end = 1500
    r = netrun.run(
        ctx.bin,
        ctx.dir / "run",
        "05-Twoson",
        netrun.boot_then(netrun.random_play(30, end)),
        [netrun.Peer("p2", netrun.random_play(31, end))],
        netrun.Net(latency=10, jitter=3, seed=7),
        input_delay=4,
        end_frame=end,
        timeout=120,
        wait_players=2,
        triggers=[netrun.Trigger(r"^NETSYNC f=600 ", spoof)],
    )
    host = r.machines[0]
    expect(sent.get("n"), "the spoofed HELLOs to be sent", sent)
    session = host.events[: host.events.index(f"NET END f={end}")]  # after END, clients say goodbye
    expect(not [e for e in session if re.match(r"NET (DROP|LEAVE)", e)], "no DROP or LEAVE on the Host", session)
    expect(host.event(r"^NET REJECT .* build differs: "), "the garbage HELLO turned away", session)
    expect(host.event(r"^NET HELLO from .* waits: P2's connection"), "the restarted HELLO told to wait", session)
    check(r.check_clean, end)
    check(r.check_agreement, min_common=end // 60 - 2)
    expect("P2:joined" in host.syncs[max(host.syncs)][1], "P2 joined at the end", host.syncs[max(host.syncs)])

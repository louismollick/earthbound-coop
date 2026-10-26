"""A client from an incompatible build is turned away cleanly.

The Host runs the wide build (320x240), the client the native one (256x224) from
the same tree. The client must stop before joining with a message naming the
viewport, and the Host must play on alone to the end.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _net import netrun
from lib import expect


def run(ctx):
    native = os.environ.get("EB_BIN_NATIVE") or str(Path(ctx.bin).parents[1] / "build" / "earthbound")
    expect(Path(native).exists() and native != ctx.bin, "a native (256x224) build next to the wide one", native)
    end = 12000  # the lone Host runs uncapped: long enough for the client to start and ask
    r = netrun.run(
        ctx.bin,
        ctx.dir / "run",
        "05-Twoson",
        netrun.boot_then(netrun.random_play(40, end)),
        [netrun.Peer("p2", netrun.random_play(41, end), binary=native)],
        input_delay=4,
        end_frame=end,
        timeout=120,
    )
    host, p2 = r.machines
    expect(not r.desyncs, "no desync", host.events[-3:])
    expect(host.rc == 0 and host.event(rf"^NET END f={end}$"), "the Host to play on to the end", host.events[-3:])
    expect(not host.event(r"^NET (JOIN|CAPTURE) P2"), "the native client never to join", host.events)
    expect(host.event(r"^NET REJECT .*viewport"), "the Host to log the rejected build", host.events)
    expect(p2.rc not in (0, None), "the client to exit with an error", p2.rc)
    expect(
        "viewport" in p2.stderr and "320x240" in p2.stderr and "256x224" in p2.stderr,
        "the client's message to name both viewports",
        p2.stderr[-400:],
    )

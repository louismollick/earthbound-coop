"""The desync detector stops the Session within 60 frames of a deliberate desync.

One client's RNG is perturbed (EB_NET_TEST_DESYNC); the stop names the RNG section,
and both machines write their dumps.
"""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _net import netrun
from lib import expect

DIFF = Path(__file__).resolve().parents[2] / "net" / "desync_diff.py"


def run(ctx):
    bad = 700
    r = netrun.run(
        ctx.bin,
        ctx.dir / "run",
        "05-Twoson",
        netrun.boot_then(netrun.random_play(12, 3000)),
        [netrun.Peer("p2", netrun.random_play(13, 3000), env={"EB_NET_TEST_DESYNC": str(bad)})],
        netrun.Net(latency=10, seed=5),
        input_delay=4,
        end_frame=3000,
        timeout=120,
        wait_players=2,
    )
    host, p2 = r.machines
    expect(p2.event(rf"^NET TEST perturbed the RNG at f={bad}$"), f"the client to perturb its RNG at {bad}", p2.events)
    ev = host.event(r"^NET DESYNC f=(\d+) P1 P2 sections=(.*)")
    expect(ev, "the Host to report a desync", host.events[-5:])
    m = re.match(r"NET DESYNC f=(\d+) P1 P2 sections=(.*)", ev)
    f, sections = int(m.group(1)), m.group(2).split(", ")
    expect(bad < f <= bad + 60, f"detection within 60 frames of {bad}", f)
    expect("RNG" in sections, "the RNG section named", sections)
    expect(host.rc == 3 and p2.rc == 3, "both machines to stop with status 3", (host.rc, p2.rc))
    expect(p2.event(rf"^NET DESYNC f={f} "), "the client to get the stop message", p2.events[-4:])
    dumps = [mm.dir / f"desync-{f}-P{i}.state" for i, mm in ((1, host), (2, p2))]
    for d in dumps:
        expect(d.exists() and d.with_suffix(".txt").exists(), "a .state and .txt dump", d)
    txt = dumps[1].with_suffix(".txt").read_text()
    expect(re.search(r"^RNG .* DIFFERS$", txt, re.M), "the client's .txt to mark RNG as differing", txt[:200])
    out = subprocess.run([sys.executable, DIFF, *map(str, dumps)], capture_output=True, text=True, check=True)  # noqa: S603
    expect("RNG:" in out.stdout, "desync_diff.py to show the RNG bytes", out.stdout[:300])

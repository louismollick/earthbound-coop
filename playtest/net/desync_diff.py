"""Compare two netplay desync dumps (``desync-<frame>-P<n>.state``) section by section.

    python playtest/net/desync_diff.py host/desync-1680-P1.state p2/desync-1680-P2.state

Prints each differing section with its byte count and the first differing offsets
(a ``.state`` file is "EBND", u32 frame, u32 count, then per section u16 id,
u8 name length, name, u32 size, bytes; see net/session.c).
"""

import argparse
import struct
import sys
from pathlib import Path


def load(path):
    """{section name: bytes} of one dump, in file order."""
    data = Path(path).read_bytes()
    magic, frame, count = struct.unpack_from("<4sII", data, 0)
    if magic != b"EBND":
        sys.exit(f"{path}: not a desync dump")
    pos, out = 12, {}
    for _ in range(count):
        _sid, nl = struct.unpack_from("<HB", data, pos)
        pos += 3
        name = data[pos : pos + nl].decode()
        pos += nl
        (size,) = struct.unpack_from("<I", data, pos)
        pos += 4
        out[name] = data[pos : pos + size]
        pos += size
    return frame, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--max", type=int, default=16, help="differing offsets to list per section")
    a = ap.parse_args()
    fa, sa = load(a.a)
    fb, sb = load(a.b)
    print(f"frame {fa} vs {fb}")
    for name in sa:
        x, y = sa[name], sb.get(name, b"")
        if x == y:
            continue
        offs = [i for i in range(min(len(x), len(y))) if x[i] != y[i]]
        print(f"{name}: {len(offs)} bytes differ (sizes {len(x)}/{len(y)})")
        for i in offs[: a.max]:
            print(f"  +0x{i:05x}: {x[i]:02x} {y[i]:02x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

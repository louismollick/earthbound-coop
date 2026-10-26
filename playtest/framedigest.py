"""Frame digests that travel between machines: every frame of the regress replays, one hash per case.

Usage (from the repo root)::

    uv run --no-sync python playtest/framedigest.py record NAME BIN [-k PATTERN] [-j N]
    uv run --no-sync python playtest/framedigest.py check NAME BIN [-k PATTERN] [-j N]

``framehash.py`` compares two builds on one machine. This compares a build with a digest recorded
on any machine: per case the frame count and a sha256 over its frames' hashes in order (the
per-frame md5 that framehash takes of the raw rgb24 frames). ``record`` writes
``playtest/regress/framedigest/NAME.json`` (tracked); ``check`` runs BIN over the same cases and
exits non-zero unless every case matches.

``base.json`` is recorded from ``port/unix/build-base-fix`` (upstream d32c421 packed with this
fork's ebtools; it never changes) at 320x240. A wide co-op build that passes ``check base`` on
macOS, Linux and Windows draws every frame of every case exactly as vanilla does on each of them
(PLAN.md M5 and the vanilla invariant). A mismatch names the case; on that machine,
``regress.py framehash build-base-fix BIN -k CASE --png 5`` finds the frames. Per-frame hashes of
each run go to ``playtest/out/regress/framedigest/NAME/CASE.hashes``.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import framehash  # noqa: E402
import regress  # noqa: E402

DIGESTS = HERE / "regress" / "framedigest"
OUT = HERE / "out" / "regress" / "framedigest"


def run_case(case, binary, outdir):
    """Play one case on ``binary``; return (name, {"frames", "sha256"} or None, status).

    A run counts only if the game reached the end of its script (the case's ``end_marker``, the
    final ``sync``) and exited cleanly: a game that stops early (``--frames``, a crash, an early
    quit) fails rather than recording or matching a truncated digest.
    """
    tmp = Path(tempfile.mkdtemp(prefix=f"eb-framedigest-{case['name']}-"))
    run = framehash.GameRun(binary, tmp / "run", case["save"], case["script"], case.get("args", ()))
    deadline = time.monotonic() + case["timeout"]
    status = "done"
    try:
        run.start()
        if run.wait_size(deadline) is None:
            status = "NO VIDEO"
        else:
            while run.next_frame(deadline) is not None:
                pass
            status = run.finish(grace=max(1.0, deadline - time.monotonic()))
        marker = case.get("end_marker")
        if status == "done" and marker and marker not in run.log.read_text(errors="replace"):
            status = "ended before the end of the script"
    except framehash.CaseTimeoutError:
        status = f"TIMEOUT after {case['timeout']:.0f}s"
    finally:
        run.close()
        shutil.rmtree(tmp, ignore_errors=True)
    (outdir / f"{case['name']}.hashes").write_text("".join(f"{x}\n" for x in run.hashes), newline="\n")
    if status != "done":
        return case["name"], None, status
    digest = hashlib.sha256("".join(f"{x}\n" for x in run.hashes).encode()).hexdigest()
    return case["name"], {"frames": run.frames, "sha256": digest, "size": list(run.size)}, status


def run_all(binary, patterns, jobs, outdir):
    cases = framehash.regress_cases(regress, patterns)
    shutil.rmtree(outdir, ignore_errors=True)
    outdir.mkdir(parents=True)
    results, failed = {}, {}

    def one(case):
        name, res, status = run_case(case, binary, outdir)
        what = status if res is None else f"{res['frames']} frames"
        print(f"  {name:<28} {what}", flush=True)
        return name, res, status

    with ThreadPoolExecutor(max_workers=jobs) as ex:
        for name, res, status in ex.map(one, cases):
            if res is None:
                failed[name] = status
            else:
                results[name] = res
    return results, failed


def compare(want, results, failed, patterns):
    """Check a run against the digest ``want``; return (failures, cases, report lines).

    ``results``: case name -> {"frames", "sha256", "size"} of the cases that finished; ``failed``:
    case name -> status of those that didn't. Every recorded case that ``patterns`` (``-k``) selects
    must have run and match; a case run but not recorded fails too, and so does an empty selection.
    """
    selected = {n for n in want["cases"] if not patterns or any(p in n for p in patterns)}
    names = selected | set(results) | set(failed)
    if not names:
        return 1, 0, [f"no cases selected (-k {' '.join(patterns)})" if patterns else "no cases"]
    lines = [f"CASE {name}: {status}" for name, status in sorted(failed.items())]
    bad = len(failed)
    for name, res in sorted(results.items()):
        size = "x".join(map(str, res["size"]))
        exp = want["cases"].get(name)
        if exp is None:
            bad += 1
            lines.append(f"CASE {name}: no digest recorded")
        elif size != want["viewport"]:
            bad += 1
            lines.append(f"CASE {name}: viewport {size}, the digest is {want['viewport']}")
        elif (res["frames"], res["sha256"]) != (exp["frames"], exp["sha256"]):
            bad += 1
            lines.append(f"CASE {name}: DIFF frames {res['frames']} (digest {exp['frames']})")
        else:
            lines.append(f"CASE {name}: same ({res['frames']} frames)")
    missing = sorted(selected - set(results) - set(failed))
    if missing:
        bad += len(missing)
        lines.append(f"recorded but not run: {', '.join(missing)}")
    return bad, len(names), lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["record", "check"])
    ap.add_argument("name", help="digest name (playtest/regress/framedigest/NAME.json)")
    ap.add_argument("bin", help="game binary")
    ap.add_argument("-k", action="append", default=[], help="only cases whose name contains this (repeatable)")
    ap.add_argument("-j", type=int, default=None, help="parallel games (default: the CPU count)")
    a = ap.parse_args()
    binary = str(Path(a.bin).resolve())
    path = DIGESTS / f"{a.name}.json"
    if a.cmd == "check" and not path.exists():
        raise SystemExit(f"no digest {path}")
    t0 = time.time()
    results, failed = run_all(binary, a.k, a.j or os.cpu_count() or 4, OUT / a.name)
    if a.cmd == "record":
        for name, status in sorted(failed.items()):
            print(f"CASE {name}: {status}")
        if not results and not failed:
            raise SystemExit("no cases selected")
        if failed:
            raise SystemExit(f"not recorded: {len(failed)} cases did not finish")
        sizes = {tuple(r.pop("size")) for r in results.values()}
        doc = {
            "about": "per regress case: frame count and sha256 of its per-frame hashes (playtest/framedigest.py)",
            "viewport": "x".join(map(str, sizes.pop())) if len(sizes) == 1 else "mixed",
            "recorded_on": platform.system(),
            "cases": dict(sorted(results.items())),
        }
        DIGESTS.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, indent=1) + "\n", newline="\n")
        print(f"recorded {len(results)} cases to {path} ({time.time() - t0:.0f}s)")
        return
    want = json.loads(path.read_text())
    bad, total, lines = compare(want, results, failed, a.k)
    print("\n".join(lines))
    print(
        f"\n{bad} of {total} cases differ from {path.name} "
        f"(recorded on {want.get('recorded_on', '?')}, {time.time() - t0:.0f}s); hashes in {OUT / a.name}"
    )
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

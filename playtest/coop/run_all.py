"""Run every co-op scenario in playtest/coop/scenarios/ (PLAN.md gate 4).

Usage::

    EB_BIN=$PWD/port/unix/build-wide/earthbound python playtest/coop/run_all.py [NAME ...]
    python playtest/coop/run_all.py --sheet-only OUT.png

Prints ``PASS name`` / ``FAIL name: reason`` per scenario and a summary, and exits
non-zero on any failure. Scenarios run in parallel. ``$EB_BIN`` must be an absolute
path. ``EB_COOP_SANITIZE=1`` also fails a scenario whose game printed an ASan/UBSan
report. ``--continuity [cold|warm]`` also runs playtest/coop/continuity.py over every passing
scenario's sessions (snap at the middle batch, restore in a fresh process, compare the
end slots). ``--sheet-only`` runs nothing: it tiles the important shots of each
scenario's latest run (``playtest/out/coop/<name>/important.json``) into OUT.png.
"""

import argparse
import importlib.util
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import continuity  # noqa: E402
import lib  # noqa: E402

SCENARIOS = Path(__file__).resolve().parent / "scenarios"
sys.path.insert(0, str(SCENARIOS))  # shared scenario bodies: scenarios/_*.py (not run themselves)


def scenario_files(names):
    files = sorted(p for p in SCENARIOS.glob("*.py") if not p.name.startswith("_"))
    if names:
        files = [p for p in files if p.stem in names]
    return files


def run_one(path, binary, continuity_mode=None):
    """Run scenario file ``path``; return (name, error message or None, seconds).

    ``continuity_mode`` ("cold" or "warm"): when the scenario passes, also run continuity.py's
    check over each of its sessions' command streams.
    """
    t0 = time.time()
    ctx = lib.Scenario(path.stem, binary)
    err = None
    try:
        spec = importlib.util.spec_from_file_location(f"coop_scenario_{path.stem}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.run(ctx)
    except lib.ScenarioError as e:
        err = str(e)
    except Exception as e:  # noqa: BLE001 - a broken scenario is a failure, not a crash of the runner
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    try:
        ctx.close()
    except lib.ScenarioError as e:
        err = f"{err}; {e}" if err else str(e)
    if continuity_mode and not err:
        notes = []
        for s in ctx.sessions:
            label = f"{path.stem}-{s.dir.name}"
            try:
                problems = continuity.check_session(label, binary, s, warm=continuity_mode == "warm")
            except continuity.SkipError as e:
                notes.append(f"{s.dir.name}: continuity skipped ({e})")
                continue
            if problems:
                err = f"continuity {s.dir.name}: " + "; ".join(problems)
                break
        if not err and notes:
            print(f"  {path.stem}: " + ", ".join(notes), flush=True)
    return path.stem, err, time.time() - t0


def contact_sheet(out, cols=3):
    """Tile every scenario's important shots, labelled, into ``out``."""
    tiles = []
    for d in sorted(p for p in lib.OUT.iterdir() if p.is_dir()) if lib.OUT.exists() else []:
        f = d / "important.json"
        if not f.exists():
            continue
        for item in json.loads(f.read_text()):
            if Path(item["path"]).exists():
                tiles.append((Image.open(item["path"]).convert("RGB"), item["label"]))
    if not tiles:
        sys.exit("no scenario shots found (run the suite first)")
    w = max(im.width for im, _ in tiles)
    h = max(im.height for im, _ in tiles)
    lab = 14
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (w * min(cols, len(tiles)), (h + lab) * rows), "black")
    d = ImageDraw.Draw(sheet)
    for i, (im, label) in enumerate(tiles):
        x, y = (i % cols) * w, (i // cols) * (h + lab)
        d.text((x + 2, y + 1), label, fill="white")
        sheet.paste(im, (x, y + lab))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"SHEET {out} ({len(tiles)} shots)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="run only these scenarios")
    ap.add_argument("--sheet-only", metavar="OUT.png", help="build the contact sheet of the latest run and exit")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 4)
    ap.add_argument(
        "--continuity",
        nargs="?",
        const="cold",
        choices=["cold", "warm"],
        help="also check every passing scenario's sessions with continuity.py (default cold; warm: B boots first)",
    )
    a = ap.parse_args()
    if a.sheet_only:
        contact_sheet(a.sheet_only)
        return 0
    binary = os.environ.get("EB_BIN", "")
    if not binary or not Path(binary).is_absolute() or not Path(binary).exists():
        sys.exit(f"EB_BIN must be an absolute path to the game binary (got {binary!r})")
    files = scenario_files(a.names)
    if not files:
        sys.exit("no scenarios found")
    t0 = time.time()
    failed = 0
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for name, err, secs in ex.map(lambda p: run_one(p, binary, a.continuity), files):
            if err:
                failed += 1
                print(f"FAIL {name}: {err}", flush=True)
            else:
                print(f"PASS {name} ({secs:.1f}s)", flush=True)
    print(f"{len(files) - failed}/{len(files)} scenarios passed in {time.time() - t0:.0f}s ({binary})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

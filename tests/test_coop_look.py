"""Co-op Look-only scan (src/coop/coop_look.c) on known text scripts.

Runs the desktop binary with ``--selftest-look``, which prints
``LOOK <LABEL> <0|1> ...`` per test label and stats over every NPC config
entry. The binary is ``$EB_BIN`` or ``port/unix/build-wide/earthbound``; the test
skips when it hasn't been built (it embeds the extracted assets).
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
BIN = Path(os.environ.get("EB_BIN", ROOT / "port" / "unix" / "build-wide" / "earthbound"))

# label -> expected Look-only, and why
EXPECTED = {
    "MSG_TWSN_BUS_B": True,  # Twoson townsperson: a flag check and text
    "MSG_ONET_SHARK_D_JOIN_REFUSE": False,  # deletes an NPC (1F 1E)
    "MSG_ONET_CHECK_HOTEL_KANBAN": True,  # Hotel Onett sign (OBJECT)
    "MSG_ONET_HOTEL_PORTER": True,  # Hotel Onett porter: plain text
    "MSG_NEWS_HOTEL_ONETT_PAPERBOY": True,  # calls + a 29-way JUMP_MULTI2, all text
    "MSG_SHOP2_HOTEL_ONETT": False,  # hotel clerk: a paid stay
    "MSG_GLOBAL_TELEPHONE": False,  # phone menu (1A 0A)
    "MSG_GLOBAL_CASHDISPENSER": False,  # ATM withdraw (1D 07)
    "MSG_ONET_DRUG_SHOP1": False,  # shop clerk: temp flag, then the shop flow
    "MSG_SYS_CONTAINER_PRESENT": False,  # present box (ITEM_BOX): flag, item
    "MSG_ONET_LIBRARY_PATRON_SILENT": False,  # sets FLG_TEMP_1
}


@pytest.fixture(scope="module")
def selftest_output() -> str:
    if not BIN.exists():
        pytest.skip(f"needs the desktop build ({BIN}); set EB_BIN")
    result = subprocess.run(  # noqa: S603
        [str(BIN), "--selftest-look"], capture_output=True, text=True, timeout=120, check=False
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return result.stdout


def test_labels(selftest_output: str) -> None:
    got = {}
    for line in selftest_output.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "LOOK":
            got[parts[1]] = parts[2] == "1"
    assert got == EXPECTED


def test_npc_stats(selftest_output: str) -> None:
    stats = [line for line in selftest_output.splitlines() if line.startswith("LOOK-STATS ")]
    person = next(line for line in stats if line.startswith("LOOK-STATS person "))
    item_box = next(line for line in stats if line.startswith("LOOK-STATS item_box "))
    # Plenty of townspeople are Look-only; every present/chest/trash can gives an item.
    assert int(person.split("entries look=")[1].split()[0]) > 300
    assert item_box.split("entries look=")[1].split()[0] == "0"

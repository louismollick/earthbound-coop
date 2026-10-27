"""The Japanese interface tables (ebtools/ja_interface.py, docs/ja-plan.md J2).

The layout tests need nothing or only the extracted US binaries; the ROM tests
read ``mother2.sfc`` and skip without it.
"""

import re
from pathlib import Path

import pytest

from ebtools.ja_interface import (
    NAME_TABLES,
    UI_TEXT_SIZE,
    UI_TEXTS,
    extract_name_tables,
    extract_ui_texts,
    pack_name_table,
    pack_ui_texts,
    rom_symbols_from_map,
    rom_symbols_used,
)
from ebtools.ja_locale import load_ja_locale

ROOT = Path(__file__).parent.parent
ROM = ROOT / "mother2.sfc"
MAP = ROOT / "build" / "mother2.map"
BIN = ROOT / "asm" / "bin"

needs_rom = pytest.mark.skipif(not ROM.exists(), reason="needs mother2.sfc")


def _config():
    return load_ja_locale(ROOT / "ja_locale.yml")


def test_ui_text_enum_matches_the_c_header():
    header = (ROOT / "src" / "game" / "ui_text.h").read_text(encoding="utf-8")
    body = header.split("typedef enum {")[1].split("} UiText;")[0]
    names = re.findall(r"^\s*(UI_[A-Z0-9_]+),", body, re.MULTILINE)
    assert names[-1] == "UI_TEXT_COUNT"
    assert names[:-1] == [name for name, _, _, _ in UI_TEXTS]
    assert f"#define UI_TEXT_SIZE {UI_TEXT_SIZE}" in header


def test_rom_symbols_cover_every_table():
    assert sorted(_config().romSymbols) == rom_symbols_used()


@pytest.mark.skipif(not MAP.exists(), reason="needs build/mother2.map (make mother2)")
def test_rom_symbols_match_the_map():
    assert rom_symbols_from_map(MAP.read_text(encoding="utf-8"), rom_symbols_used()) == _config().romSymbols


@pytest.mark.parametrize("table", NAME_TABLES, ids=lambda t: t.name)
def test_name_fields_fit_the_us_table(table):
    """Every field lies inside the US table, but a last field may grow it."""
    path = BIN / table.us_path
    if not path.exists():
        pytest.skip(f"needs {path} (ebtools extract)")
    size = len(path.read_bytes())
    ends = sorted(f.us_off + (f.count - 1) * f.us_stride + f.us_len for f in table.fields)
    assert all(end <= size for end in ends[:-1])
    for f in table.fields:
        assert f.us_len <= f.us_stride
        assert f.m2_len <= f.us_len, f"{table.name}.{f.key}: the Mother 2 field must fit the US one"


def test_pack_name_table_replaces_only_names():
    table = next(t for t in NAME_TABLES if t.name == "enemies")
    us = bytes(range(256)) * (94 * 231 // 256 + 1)
    us = us[: 94 * 231]
    reverse = {"ア": 0xB0, "イ": 0xC0}
    fields = {"names": ["アイ"] * 231, "encounter_texts": ["MSG_A"] + [None] * 230, "death_texts": [None] * 231}
    out = pack_name_table(table, us, fields, reverse, {"MSG_A": 0x123456})
    assert len(out) == len(us)
    assert out[45:49] == bytes([0x56, 0x34, 0x12, 0x00])  # enemy 0's encounter_text_ptr
    for i in range(231):
        rec, orig = out[i * 94 : (i + 1) * 94], us[i * 94 : (i + 1) * 94]
        assert rec[0] == 0  # the_flag
        assert rec[1:26] == bytes([0xB0, 0xC0]) + bytes(23)
        if i:
            assert rec[26:] == orig[26:]
        else:
            assert rec[26:45] == orig[26:45] and rec[49:] == orig[49:]


@needs_rom
def test_extract_and_pack_from_the_rom():
    from ebtools.config import load_dump_doc
    from ebtools.ja_locale import ja_text_table

    config = _config()
    rom = ROM.read_bytes()
    table = ja_text_table(load_dump_doc(ROOT / "mother2.yml"), config)
    names = extract_name_tables(rom, config.romSymbols, table, lambda addr: f"L{addr:06X}")
    ui = extract_ui_texts(rom, config.romSymbols, table)

    # Spot checks against asm/data (JPN branches)
    assert names["command_window_text"]["labels"] == ["はなす", "グッズ", "PSI", "そうび", "チェック", "つよさ"]
    assert names["psi_categories"]["names"] == ["こうげき", "かいふく", "アシスト", "そのほか"]
    assert names["pp_cost_text"]["text"] == "しょうひPP:"
    assert names["status_window_text"]["labels"][0] == {"col": 1, "row": 0, "text": "レベル:"}
    assert ui["UI_FILE_CONTINUE"] == "つづき"
    assert ui["UI_BATTLE_BASH"] == "たたく"
    assert ui["UI_GOODS_HELP"] == "せつめい"
    assert sum(1 for n in names["items"]["names"] if n) > 200
    assert sum(1 for n in names["enemies"]["names"] if n) > 200
    encounters = names["enemies"]["encounter_texts"]
    assert len(encounters) == 231 and all(label.startswith("LC") for label in encounters)

    reverse = {c: code for code, c in table.items()}
    packed = pack_ui_texts(ui, reverse)
    assert len(packed) == len(UI_TEXTS) * UI_TEXT_SIZE
    label_addrs = {label: 0x100000 + i for i, label in enumerate(sorted(set(encounters)))}
    label_addrs.update(dict.fromkeys(names["enemies"]["death_texts"], 1048576))
    for t in NAME_TABLES:
        us_path = BIN / t.us_path
        if us_path.exists():
            pack_name_table(t, us_path.read_bytes(), names[t.name], reverse, label_addrs)

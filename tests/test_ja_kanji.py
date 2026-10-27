"""Japanese kanji Locale (docs/ja-plan.md J4, ebtools/ja_kanji.py).

The encoding, font and checker tests use a tiny synthetic kana Locale and kanji
script in a temp dir, and the committed k8x12 font: no ROM.  The reading test
needs SudachiPy (the ``kanji`` extra).  ``test_local_kanji_script`` checks the
local script in ``src/custom_assets/ja_kanji/`` and skips without one.
"""

import importlib.util
import json
import re
import struct
from pathlib import Path

import pytest

from ebtools.ja_kanji import (
    INLINE_STRINGS_FILE,
    KANJI_FONT_BDF,
    KANJI_OVERRIDE_SUBDIR,
    check_override,
    glyph_pixels,
    load_bdf,
    normalise_reading,
    override_files,
    pack_kanji,
    pack_kanji_font,
)
from ebtools.ja_locale import JA_DIALOGUE_BASE, JA_INLINE_BASE, write_text_table
from ebtools.text_dsl.compiler import compile_text_block
from ebtools.text_dsl.decoder import decode_text_block
from ebtools.text_dsl.kanji import KANJI_MAX, KANJI_PREFIX, kanji_code, kanji_index, kanji_reverse_table
from ebtools.text_dsl.yaml_io import deserialize_dialogue_file, serialize_dialogue_file

ROOT = Path(__file__).parent.parent
CUSTOM = ROOT / "src" / "custom_assets"
FONT = CUSTOM / KANJI_FONT_BDF
JA = ROOT / "src" / "assets" / "ja"

# A tiny kana text table (Mother 2's codes for these few letters don't matter here)
TABLE = {0x20: " ", 0x40: "•", 0x5F: "。", 0x60: "あ", 0x61: "い", 0x62: "え", 0x63: "は", 0x64: "な", 0x65: "し"}
REVERSE = {ch: code for code, ch in TABLE.items()}


def txt(s: str) -> dict:
    return {"op": "text", "value": s}


END = {"op": "end_block"}
HALT = {"op": "halt_with_prompt"}
FLAG = {"op": "set_event_flag", "flag": 5}

KANA = {
    "MSG_A": [txt("•いえ。"), HALT, FLAG, END],
    "MSG_B": [txt("•はなし"), END],
    "MSG_KBD_LAYOUT_X": [txt("あい"), END],
}
KANA_INLINE = {"us one": "{start_new_line}•いえ。{halt_without_prompt}", "us two": "•あ"}


def make_locale(tmp_path: Path, script: dict[str, list[dict]] | None, inline: dict | None = None) -> tuple[Path, Path]:
    """Write the kana Locale (ja/) and a kanji script (ja_kanji/); return both dirs."""
    ja = tmp_path / "ja"
    (ja / "dialogue").mkdir(parents=True)
    write_text_table(ja / "text_table.json", TABLE)
    (ja / "dialogue" / "E01.yml").write_text(serialize_dialogue_file(KANA), encoding="utf-8")
    (ja / INLINE_STRINGS_FILE).write_text(json.dumps(KANA_INLINE, ensure_ascii=False), encoding="utf-8")
    over = tmp_path / KANJI_OVERRIDE_SUBDIR
    over.mkdir()
    (over / "README.md").write_text("not a script file\n")
    if script is not None:
        (over / "E01.yml").write_text(serialize_dialogue_file(script), encoding="utf-8")
    if inline is not None:
        (over / INLINE_STRINGS_FILE).write_text(json.dumps(inline, ensure_ascii=False), encoding="utf-8")
    return ja, over


def converted() -> dict[str, list[dict]]:
    return {**KANA, "MSG_A": [txt("•家。"), HALT, FLAG, END], "MSG_B": [txt("•話"), END]}


# --- Encoding --------------------------------------------------------------------


def test_kanji_code_round_trips_and_digits_are_letters():
    for index in (0, 1, 223, 224, 1000, KANJI_MAX - 1):
        code = kanji_code(index)
        assert code[0] == KANJI_PREFIX and code[1] >= 0x20 and code[2] >= 0x20
        assert kanji_index(code[1], code[2]) == index
    with pytest.raises(ValueError):
        kanji_code(KANJI_MAX)


def test_compile_and_decode_kanji_text():
    kanji = ["家", "話"]
    table = kanji_reverse_table(REVERSE, kanji)
    ops = [txt("•家は 話。"), HALT, END]
    blob = compile_text_block(ops, table)
    assert blob == bytes([0x40]) + kanji_code(0) + bytes([0x63, 0x20]) + kanji_code(1) + bytes([0x5F, 0x03, 0x02])
    assert decode_text_block(blob, TABLE, kanji=kanji) == ops
    with pytest.raises(ValueError):
        kanji_reverse_table(REVERSE, ["あ"])  # a kana is never a kanji


# --- Font ------------------------------------------------------------------------


def test_font_glyphs_keep_the_kana_grid():
    font = load_bdf(FONT)
    assert "家" in font and "話" in font and "A" not in font  # half-width glyphs are left out
    cell = glyph_pixels(font["家"])
    assert len(cell) == 16 and all(len(row) == 8 for row in cell)
    ink_rows = [y for y, row in enumerate(cell) if any(row)]
    assert ink_rows[0] >= 2 and ink_rows[-1] <= 12  # Mother 2's kana sit on rows 3-11
    assert not any(row[0] for row in cell)  # column 0 blank, like the kana
    glyphs, widths, chars = pack_kanji_font(font, ["家", "話"])
    assert len(glyphs) == 32 and widths == bytes([7, 7])
    assert struct.unpack("<2H", chars) == (ord("家"), ord("話"))
    assert glyphs[0] == 0xFF  # inverted 1bpp: an empty row is all ones


# --- Checker -----------------------------------------------------------------------


def test_check_passes_a_good_script(tmp_path):
    ja, over = make_locale(tmp_path, converted(), {"us one": "{start_new_line}•家。{halt_without_prompt}"})
    report = check_override(ja, over, FONT, readings=False)
    assert report.errors == []
    assert report.files == ["E01.yml", INLINE_STRINGS_FILE]
    assert report.converted == 3 and report.kanji == {"家", "話"}


def test_check_labels(tmp_path):
    script = converted()
    reordered = {"MSG_B": script["MSG_B"], "MSG_A": script["MSG_A"], "MSG_KBD_LAYOUT_X": script["MSG_KBD_LAYOUT_X"]}
    ja, over = make_locale(tmp_path, reordered)
    report = check_override(ja, over, FONT, readings=False)
    assert len(report.errors) == 1 and "reordered" in report.errors[0]
    (over / "E01.yml").write_text(serialize_dialogue_file({"MSG_A": script["MSG_A"]}), encoding="utf-8")
    assert "missing ['MSG_B'" in check_override(ja, over, FONT, readings=False).errors[0]
    (over / "E99.yml").write_text(serialize_dialogue_file({}), encoding="utf-8")
    assert any("no kana file" in e for e in check_override(ja, over, FONT, readings=False).errors)


def test_check_ops_and_characters(tmp_path):
    script = converted()
    script["MSG_A"] = [txt("•家。"), {"op": "pause", "frames": 5}, FLAG, END]  # a presentation op changed
    script["MSG_B"] = [txt("•"), END]  # nowhere: not in the table nor the font
    script["MSG_KBD_LAYOUT_X"] = [txt("家い"), END]  # the naming keyboard stays kana
    inline = {"us one": "{start_new_line}•家。", "nope": "•家"}
    ja, over = make_locale(tmp_path, script, inline)
    errors = check_override(ja, over, FONT, readings=False).errors
    assert len(errors) == 5, errors
    assert sum("ops differ" in e for e in errors) == 2  # MSG_A and the inline string's dropped halt
    assert any("MSG_B" in e and "not in the text table" in e for e in errors)
    assert any("kana-only" in e for e in errors)
    assert any("not a kana inline string" in e for e in errors)


def test_normalise_reading():
    assert normalise_reading("トーキョー") == normalise_reading("とうきょう") == normalise_reading("トオキョオ")
    assert normalise_reading("•おまえ  ねーよ!") == "オマエネエヨ"
    assert normalise_reading("せんせい") == normalise_reading("センセー")


@pytest.mark.skipif(importlib.util.find_spec("sudachipy") is None, reason="needs the kanji extra (SudachiPy)")
def test_check_readings(tmp_path):
    script = converted()
    script["MSG_B"] = [txt("•声"), END]  # はなし is not こえ
    ja, over = make_locale(tmp_path, script)
    report = check_override(ja, over, FONT)
    assert report.ok and report.readings_checked
    assert len(report.readings) == 1 and "MSG_B" in report.readings[0]


# --- Packing -----------------------------------------------------------------------


def test_pack_kanji(tmp_path):
    ja, over = make_locale(tmp_path, converted(), {"us one": "{start_new_line}•家。{halt_without_prompt}"})
    out = tmp_path / "packed" / "JA_KANJI"  # (not beside ja_kanji/: case-insensitive file systems)
    kana_dialogue = [(ja / "dialogue" / "E01.yml", KANA)]
    us_addrs = {"MSG_A": 0x100000, "MSG_B": 0x100010, "MSG_KBD_LAYOUT_X": 0x100020}
    files = pack_kanji(
        over, FONT, out, kana_dialogue, REVERSE, {}, us_addrs, {"us one": 0, "us two": 9}, KANA_INLINE, ja
    )
    assert files == 6
    chars = (out / "fonts" / "kanji_chars.bin").read_bytes()
    kanji = [chr(c) for (c,) in struct.iter_unpack("<H", chars)]
    assert kanji == ["家", "話"]
    assert len((out / "fonts" / "kanji.gfx").read_bytes()) == 16 * len(kanji)
    xlat = dict(struct.iter_unpack("<II", (out / "text" / "xlat.bin").read_bytes()))
    blob = (out / "text" / "dialogue.bin").read_bytes()
    a = xlat[0x100000] - JA_DIALOGUE_BASE
    assert decode_text_block(blob[a:], TABLE, kanji=kanji, stop_at_end_block=True) == converted()["MSG_A"]
    inline = (out / "text" / "inline_strings.bin").read_bytes()
    one, two = xlat[0] - JA_INLINE_BASE, xlat[9] - JA_INLINE_BASE
    assert decode_text_block(inline[one:], TABLE, kanji=kanji, stop_at_end_block=True)[1] == txt("•家。")
    assert decode_text_block(inline[two:], TABLE, kanji=kanji, stop_at_end_block=True)[0] == txt("•あ")

    # A broken script: no JA_KANJI/ (the kana Locale still builds)
    (over / "E01.yml").write_text(serialize_dialogue_file({"MSG_A": KANA["MSG_A"]}), encoding="utf-8")
    assert pack_kanji(over, FONT, out, kana_dialogue, REVERSE, {}, us_addrs, {}, KANA_INLINE, ja) == 0
    assert not out.exists()

    # A text op that isn't a string (text: null): an error, never a crash
    yml = re.sub(r"text: .*", "text: null", serialize_dialogue_file(converted()), count=1)
    (over / "E01.yml").write_text(yml, encoding="utf-8")
    assert any("not a string" in e for e in check_override(ja, over, FONT, readings=False).errors)
    assert pack_kanji(over, FONT, out, kana_dialogue, REVERSE, {}, us_addrs, {}, KANA_INLINE, ja) == 0
    assert not out.exists()


def test_override_folder_is_only_scripts(tmp_path):
    assert override_files(tmp_path / "none") == []
    _ja, over = make_locale(tmp_path, None)
    assert override_files(over) == []  # the README alone is no script


# --- The local kanji script --------------------------------------------------------


@pytest.mark.skipif(
    not override_files(CUSTOM / KANJI_OVERRIDE_SUBDIR) or not (JA / "text_table.json").exists(),
    reason="no local kanji script in src/custom_assets/ja_kanji (or no src/assets/ja)",
)
def test_local_kanji_script():
    report = check_override(JA, CUSTOM / KANJI_OVERRIDE_SUBDIR, FONT, readings=False)
    assert report.errors == []
    for f in override_files(CUSTOM / KANJI_OVERRIDE_SUBDIR):
        if f.suffix in (".yml", ".yaml"):
            assert deserialize_dialogue_file(f.read_text(encoding="utf-8"))

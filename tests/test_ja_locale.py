"""Japanese Locale tools (docs/adr/0003-japanese-locale.md).

The splice tests need nothing.  The asset tests check ``src/assets/ja`` (from
``ebtools extract-ja``) against the US dialogue and skip without it or without
``mother2.sfc``.
"""

import contextlib
import io
import json
import shutil
import struct
import tempfile
from functools import cache
from pathlib import Path
from unittest import mock

import pytest

from ebtools.text_dsl.splice import splice, splice_chain, strip_presentation

ROOT = Path(__file__).parent.parent
ASSETS = ROOT / "src" / "assets"
JA = ASSETS / "ja"


def txt(s: str) -> dict:
    return {"op": "text", "value": s}


FLAG_A = {"op": "set_event_flag", "flag": "A"}
END = {"op": "end_block"}
HALT = {"op": "halt_with_prompt"}


def _same(label: object) -> object:
    return label


# --- Splice (no ROM) -----------------------------------------------------------


def test_splice_takes_us_logic_and_jp_presentation():
    us = [txt("Hi"), FLAG_A, txt("Bye"), HALT, END]
    jp = [txt("やあ"), FLAG_A, txt("じゃ"), {"op": "pause", "frames": 5}, END]
    assert splice(us, jp, _same) == [txt("やあ"), FLAG_A, txt("じゃ"), {"op": "pause", "frames": 5}, END]


def test_splice_keeps_us_args_and_us_only_ops():
    # The US fixed the item id and added an article helper call.
    us = [
        {"op": "give_item_to_character", "character": 1, "item": 7},
        txt("a "),
        {"op": "call_text", "dest": "ART"},
        END,
    ]
    jp = [{"op": "give_item_to_character", "character": 1, "item": 6}, txt("もらった"), END]
    out = splice(us, jp, _same)
    assert out == [us[0], us[2], txt("もらった"), END]
    assert strip_presentation(out) == strip_presentation(us)


def test_splice_keeps_text_of_jp_only_logic():
    # A Mother 2-only flag op: its text joins the next run; the op itself is dropped.
    us = [txt("x"), END]
    jp = [txt("あ"), FLAG_A, txt("い"), END]
    assert splice(us, jp, _same) == [txt("あ"), txt("い"), END]


def test_splice_trailing_text_goes_before_the_final_terminator():
    us = [{"op": "jump", "dest": "B"}]
    jp = [{"op": "jump", "dest": "B2"}, txt("dead")]
    assert splice(us, jp, _same) == [txt("dead"), {"op": "jump", "dest": "B"}]


def test_splice_maps_menu_labels():
    menu = {"op": "load_string_to_memory", "payload": {"text": [1], "terminator": "select_script", "label": "JP_L"}}
    out = splice([END], [menu, END], lambda label: {"JP_L": "US_L"}[label])
    assert out[0]["payload"]["label"] == "US_L"


def test_splice_chain_respects_shared_label_boundaries():
    us = [("A", [txt("a"), FLAG_A]), ("B", [txt("b"), END])]
    jp = [("A", [txt("あ"), FLAG_A]), ("B", [txt("い"), END])]
    assert splice_chain(us, jp, _same) == {"A": [txt("あ"), FLAG_A], "B": [txt("い"), END]}


def test_splice_chain_us_only_label_gets_the_text_it_prints():
    # The US split a Mother 2 message with a new label (jumped to on a repeat
    # visit): the text before the US-only label's ops moves into it, so both
    # entry points print.
    us = [("P", [{"op": "jump_if_flag_set", "flag": "T", "dest": "M"}, txt("Oh, hi.")]), ("M", [txt("Pokey..."), END])]
    jp = [("P", [txt("あ こんばんわ。"), txt("ポーキー"), END])]
    out = splice_chain(us, jp, _same)
    assert out == {"P": [us[0][1][0]], "M": [txt("あ こんばんわ。"), txt("ポーキー"), END]}


# --- extract-ja -----------------------------------------------------------------


def test_extract_ja_rejects_wrong_rom(tmp_path):
    from ebtools.cli.extract_ja import extract_ja

    rom = tmp_path / "bad.sfc"
    rom.write_bytes(b"\0" * 1024)
    with pytest.raises(SystemExit, match="SHA-1"):
        extract_ja(rom, tmp_path / "assets", ja_config=ROOT / "ja_locale.yml")
    assert not (tmp_path / "assets").exists()


# --- Assets (src/assets/ja) -----------------------------------------------------

needs_ja = pytest.mark.skipif(
    not (JA / "dialogue").is_dir() or not (ROOT / "mother2.sfc").exists() or not (ASSETS / "dialogue").is_dir(),
    reason="needs mother2.sfc and `ebtools extract-ja` output in src/assets/ja",
)


def _load(dialogue_dir: Path) -> dict[str, list[tuple[str, list[dict]]]]:
    from ebtools.text_dsl.yaml_io import deserialize_dialogue_file

    return {p.name: list(deserialize_dialogue_file(p.read_text()).items()) for p in sorted(dialogue_dir.glob("*.yml"))}


@cache
def _dialogue() -> tuple[dict, dict]:
    return _load(ASSETS / "dialogue"), _load(JA / "dialogue")


@needs_ja
def test_same_labels_files_and_order():
    us, ja = _dialogue()
    assert list(us) == list(ja)
    for name in us:
        assert [label for label, _ in us[name]] == [label for label, _ in ja[name]], name


@needs_ja
def test_logic_invariant():
    """With presentation ops stripped, every Japanese message is its US message.

    Except ja_locale.yml's motherLogic labels, unused US copies of Mother 2's
    messages that the Japanese interface runs with Mother 2's logic.
    """
    from ebtools.ja_locale import load_ja_locale

    mother_logic = set(load_ja_locale(ROOT / "ja_locale.yml").motherLogic)
    us, ja = _dialogue()
    bad = [
        label
        for name in us
        for (label, us_ops), (_, ja_ops) in zip(us[name], ja[name])
        if label not in mother_logic and strip_presentation(us_ops) != strip_presentation(ja_ops)
    ]
    assert not bad, bad[:10]


@cache
def _packed() -> tuple[Path, dict]:
    """pack-all into a temporary directory, capturing what pack_ja was given."""
    from ebtools.cli import pack_ja as pack_ja_mod
    from ebtools.cli.pack_all import pack_all

    out = Path(tempfile.mkdtemp(prefix="eb_ja_"))
    seen: dict = {}
    real = pack_ja_mod.pack_ja

    def spy(assets_dir, output_dir, common_data, us_label_addrs, us_inline, bin_dir):
        seen["labels"] = dict(us_label_addrs)
        seen["inline"] = us_inline.entries()
        return real(assets_dir, output_dir, common_data, us_label_addrs, us_inline, bin_dir)

    with mock.patch.object(pack_ja_mod, "pack_ja", spy), contextlib.redirect_stdout(io.StringIO()):
        pack_all(
            ASSETS,
            out / "packed",
            bin_dir=ROOT / "asm" / "bin",
            yaml_config=ROOT / "earthbound.yml",
            commondata=ROOT / "commondefs.yml",
            text_refs_dir=out,
            custom_dir=ROOT / "src" / "custom_assets",
        )
    return out, seen


@pytest.fixture(scope="module")
def packed():
    if not (JA / "dialogue").is_dir() or not (ROOT / "mother2.sfc").exists():
        pytest.skip("needs mother2.sfc and src/assets/ja")
    out, seen = _packed()
    yield out / "packed" / "JA", seen
    shutil.rmtree(out, ignore_errors=True)


def test_xlat_covers_every_label_and_inline_string(packed):
    from ebtools.ja_locale import JA_DIALOGUE_BASE, JA_INLINE_BASE

    ja_dir, seen = packed
    raw = (ja_dir / "text" / "xlat.bin").read_bytes()
    pairs = [struct.unpack_from("<II", raw, i) for i in range(0, len(raw), 8)]
    keys = [k for k, _ in pairs]
    assert keys == sorted(set(keys)), "us_addr keys must be unique and sorted"
    xlat = dict(pairs)
    assert set(seen["labels"].values()) | set(seen["inline"].values()) == set(xlat)

    dialogue_end = JA_DIALOGUE_BASE + (ja_dir / "text" / "dialogue.bin").stat().st_size
    inline_end = JA_INLINE_BASE + (ja_dir / "text" / "inline_strings.bin").stat().st_size
    for us_addr, ja_addr in xlat.items():
        if us_addr >= 0x100000:
            assert JA_DIALOGUE_BASE <= ja_addr <= dialogue_end
        else:
            assert JA_INLINE_BASE <= ja_addr < inline_end


def test_font_and_glyph_range(packed):
    from ebtools.ja_locale import JA_FIRST_GLYPH, JA_FONT_GLYPHS, JA_GLYPH_COUNT, read_text_table
    from ebtools.text_dsl.inline import parse_inline_to_ops

    ja_dir, _ = packed
    assert (ja_dir / "fonts" / "main.gfx").stat().st_size == JA_FONT_GLYPHS * 32
    assert (ja_dir / "fonts" / "main.bin").stat().st_size == JA_FONT_GLYPHS

    table = read_text_table(JA / "text_table.json")
    reverse = {char: code for code, char in table.items()}
    font = range(JA_FIRST_GLYPH, JA_FIRST_GLYPH + JA_GLYPH_COUNT)
    assert all(code in font for code in table)

    inline = json.loads((JA / "inline_strings.json").read_text())
    messages = [ops for files in _dialogue()[1].values() for _, ops in files]
    messages += [parse_inline_to_ops(text) for text in inline.values()]
    for ops in messages:
        for op in ops:
            if op["op"] == "text":
                assert all(ch in reverse for ch in op["value"]), op
            elif op["op"] == "load_string_to_memory":
                assert all(b in font for b in op["payload"]["text"]), op


# --- Interface (naming data, Mr. Saturn and title fonts) -----------------------


def test_interface_text_round_trip():
    from ebtools.ja_naming import _decode, _encode

    table = {0x60: "あ", 0x62: "か", 0x20: " "}
    reverse = {v: k for k, v in table.items()}
    raw = bytes([0x62, 0x20, 0x60, 0, 0])
    assert _decode(raw, table) == "か あ"
    assert _encode("か あ", 5, reverse) == raw
    with pytest.raises(ValueError):
        _encode("かかかかかか", 5, reverse)
    with pytest.raises(ValueError):
        _decode(bytes([0x60, 0, 0x60]), table)


def test_interface_is_current_needs_every_file(tmp_path):
    from ebtools.ja_naming import interface_is_current

    assert not interface_is_current(tmp_path)


@needs_ja
def test_naming_data_from_the_rom():
    naming = json.loads((JA / "naming.json").read_text())
    assert len(naming["prompts"]) == 7
    assert [g[0] for g in naming["dont_care_names"]] == [
        "ネス",
        "ポーラ",
        "ジェフ",
        "プー",
        "チビ",
        "ハンバーグ",
        "キアイ",
    ]
    assert naming["yep"] == "はい" and naming["nope"] == "いいえ"
    assert sorted(naming["transliteration"]) == [chr(c) for c in range(0x41, 0x5B)]


def test_interface_packed(packed):
    from ebtools.ja_locale import JA_FONT_GLYPHS

    ja_dir, _ = packed
    sizes = {
        "data/naming_prompts.bin": 7 * 15,
        "data/dont_care_names.bin": 49 * 6,
        "data/naming_confirm.bin": 9 + 11 + 12 + 3 + 4,
        "data/name_registry_request_string.bin": 11,
        "data/consonant_vowel_transliteration_pairs.bin": 26 * 5 * 2,
        "fonts/mrsaturn.gfx": JA_FONT_GLYPHS * 32,
        "fonts/mrsaturn.bin": JA_FONT_GLYPHS,
        "fonts/title.gfx": 224 * 16,
    }
    for rel, size in sizes.items():
        assert (ja_dir / rel).stat().st_size == size, rel
    # Mr. Saturn's own glyphs (kana, his space and marks) have a width; the
    # codes Mother 2 prints with the normal font have 0.
    widths = (ja_dir / "fonts" / "mrsaturn.bin").read_bytes()
    assert widths[0x60 - 0x20] and widths[0x20 - 0x20] and widths[-2] and widths[-1]
    assert widths[0x41 - 0x20] == 0

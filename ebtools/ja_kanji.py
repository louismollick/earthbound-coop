"""The Japanese kanji Locale (docs/ja-plan.md J4).

A kanji script is a local, never committed copy of the kana dialogue with kanji
in its text (``src/custom_assets/ja_kanji/``, see the README there): the same
file names as ``<assets>/ja/dialogue/``, the same labels in the same order, and
the same ops but for the ``text`` values; optionally an ``inline_strings.json``
with converted values of ``<assets>/ja/inline_strings.json``.  A file it lacks
is the kana file.

- :func:`check_override` (``ebtools check-kanji``, ``tests/test_ja_kanji.py``)
  checks a script against the kana assets and the kanji font.
- :func:`pack_kanji` (``pack-all``, after the kana Locale) packs it to
  ``<output>/JA_KANJI/``: the kanji dialogue, inline strings and their xlat,
  and the kanji font (glyph table, glyphs and widths), used only when the
  Locale is ``LOCALE_JA_KANJI``.

Kanji are drawn with k8x12 (``src/custom_assets/fonts/k8x12/``): its kanji
are 7x11 in an 8x12 cell, so they keep Mother 2's 8 px letter grid.  Every
character the Japanese text table lacks is a "kanji" here (also, say, a
full-width symbol the font has); kana keep Mother 2's glyphs.
"""

import json
import re
import shutil
import struct
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Annotated

import yaml
from cyclopts import Parameter

from ebtools.ja_locale import (
    JA_ASSETS_SUBDIR,
    JA_DIALOGUE_BASE,
    JA_INLINE_BASE,
    JA_TEXT_TABLE_FILE,
    read_text_table,
)
from ebtools.parsers._tiles import encode_1bpp_font_glyph
from ebtools.text_dsl.kanji import kanji_reverse_table, kanji_table
from ebtools.text_dsl.splice import strip_presentation

# Under src/custom_assets/
KANJI_OVERRIDE_SUBDIR = "ja_kanji"
KANJI_FONT_BDF = Path("fonts") / "k8x12" / "k8x12.bdf"
# Under the packed output
KANJI_PACKED_SUBDIR = "JA_KANJI"
INLINE_STRINGS_FILE = "inline_strings.json"

# Messages the C reads as glyph codes rather than printing them through the
# text engine (the naming keyboard, src/intro/naming_ja.c): kana only.
KANA_ONLY_LABEL_PREFIXES = ("MSG_KBD_LAYOUT_",)

# Glyph cell of the Japanese text font: 8 px wide, 16 rows.  A k8x12 glyph's
# baseline goes on row 12 (Mother 2's kana sit on rows 3-11) and its pixels one
# column right (Mother 2's kana leave column 0 blank, k8x12's column 7).
GLYPH_ROWS = 16
GLYPH_BASELINE = 12
GLYPH_ADVANCE = 8


def override_files(override_dir: Path) -> list[Path]:
    """Return the script files of the override folder (dialogue YAML, inline strings)."""
    if not override_dir.is_dir():
        return []
    files = sorted(override_dir.glob("*.yml")) + sorted(override_dir.glob("*.yaml"))
    inline = override_dir / INLINE_STRINGS_FILE
    return files + ([inline] if inline.is_file() else [])


# --- The font ---------------------------------------------------------------------


@dataclass(frozen=True)
class BdfGlyph:
    """One BDF glyph: its bounding box, advance and bitmap rows (MSB = leftmost pixel)."""

    width: int
    height: int
    x_off: int
    y_off: int
    advance: int
    rows: tuple[int, ...]


_BDF_CHAR = re.compile(
    r"ENCODING (-?\d+)\n.*?DWIDTH (\d+) \d+\n.*?BBX (-?\d+) (-?\d+) (-?\d+) (-?\d+)\nBITMAP\n(.*?)ENDCHAR", re.S
)


@cache
def load_bdf(path: Path) -> dict[str, BdfGlyph]:
    """Return the full-width glyphs (advance 8) of a BDF font, by character."""
    out: dict[str, BdfGlyph] = {}
    for m in _BDF_CHAR.finditer(path.read_text(encoding="ascii")):
        enc, adv, w, h, xo, yo = (int(m.group(i)) for i in range(1, 7))
        if enc < 0 or adv != GLYPH_ADVANCE or w > GLYPH_ADVANCE:
            continue
        nbytes = (w + 7) // 8
        rows = tuple(int(r, 16) >> (8 * nbytes - 8) for r in m.group(7).split())
        out[chr(enc)] = BdfGlyph(w, h, xo, yo, adv, rows)
    return out


def glyph_pixels(g: BdfGlyph) -> list[list[int]]:
    """Return ``g`` in the Japanese font's 8x16 cell (1 = ink)."""
    cell = [[0] * 8 for _ in range(GLYPH_ROWS)]
    shift = 1 if g.x_off + g.width < 8 else 0
    top = GLYPH_BASELINE - (g.y_off + g.height)
    for r, bits in enumerate(g.rows):
        y = top + r
        for c in range(g.width):
            x = shift + g.x_off + c
            if 0 <= y < GLYPH_ROWS and 0 <= x < 8 and bits & (0x80 >> c):
                cell[y][x] = 1
    return cell


def pack_kanji_font(font: dict[str, BdfGlyph], kanji: list[str]) -> tuple[bytes, bytes, bytes]:
    """Return ``(glyphs, widths, chars)`` for the kanji glyph table ``kanji``.

    ``glyphs``: 16 bytes a glyph, the US VWF format (one inverted 1bpp byte a
    row, one 8 px column); ``widths``: one byte a glyph (advance - 1, the VWF
    adds CHARACTER_PADDING); ``chars``: the code points as u16 LE, for the
    playtest harness's window text.
    """
    glyphs = b"".join(encode_1bpp_font_glyph(glyph_pixels(font[ch])) for ch in kanji)
    widths = bytes(font[ch].advance - 1 for ch in kanji)
    chars = b"".join(struct.pack("<H", ord(ch)) for ch in kanji)
    return glyphs, widths, chars


# --- Checking a script --------------------------------------------------------------


@dataclass
class CheckReport:
    """What :func:`check_override` found."""

    files: list[str] = field(default_factory=list)  # override files checked
    messages: int = 0  # messages (and inline strings) checked
    converted: int = 0  # of them, with a text change
    kanji: set[str] = field(default_factory=set)  # characters drawn from the kanji font
    errors: list[str] = field(default_factory=list)  # (a)-(c): the script can't be packed
    readings: list[str] = field(default_factory=list)  # (d): warnings, for review
    readings_checked: bool = False

    @property
    def ok(self) -> bool:
        """True when the script can be packed."""
        return not self.errors


def _shape(ops: list[dict]) -> list[dict]:
    """``ops`` with every text value blanked: what must not change."""
    return [{"op": "text"} if op["op"] == "text" else op for op in ops]


def _texts(ops: list[dict]) -> list[str]:
    return [op["value"] for op in ops if op["op"] == "text"]


def _check_message(
    report: CheckReport,
    where: str,
    kana_ops: list[dict],
    kanji_ops: list[dict],
    table_chars: set[str],
    font: dict[str, BdfGlyph],
    kana_only: bool,
    reader: "Callable[[str], str] | None",
) -> None:
    report.messages += 1
    if _shape(kana_ops) != _shape(kanji_ops):
        report.errors.append(f"{where}: ops differ from the kana message (only text may change)")
        return
    kana_texts, kanji_texts = _texts(kana_ops), _texts(kanji_ops)
    if not all(isinstance(t, str) for t in kanji_texts):
        report.errors.append(f"{where}: a text op's value is not a string")
        return
    if kana_texts != kanji_texts:
        report.converted += 1
    for kana, text in zip(kana_texts, kanji_texts):
        extra = {ch for ch in text if ch not in table_chars}
        if extra and kana_only:
            report.errors.append(f"{where}: kana-only message has {''.join(sorted(extra))!r}")
            continue
        missing = sorted(ch for ch in extra if ch not in font)
        if missing:
            report.errors.append(f"{where}: not in the text table or the kanji font: {''.join(missing)!r}")
        report.kanji |= extra.difference(missing)
        if reader is not None and kana != text:
            got = normalise_reading(reader(text))
            if got != normalise_reading(kana):
                report.readings.append(f"{where}: {kana!r} -> {text!r} reads {got!r}")


def check_override(ja_dir: Path, override_dir: Path, font_path: Path, *, readings: bool = True) -> CheckReport:
    """Check the kanji script in ``override_dir`` against the kana assets in ``ja_dir``.

    (a) every override file has a kana file, with the same labels in the same
    order (inline strings: only keys the kana file has); (b) every message has
    the kana message's ops, only ``text`` values may differ; (c) every
    character is in the Japanese text table or the kanji font (kana only in
    ``KANA_ONLY_LABEL_PREFIXES``); (d) with SudachiPy installed and
    ``readings``, every changed text reads as its kana original.
    """
    from ebtools.text_dsl.inline import parse_inline_to_ops
    from ebtools.text_dsl.yaml_io import deserialize_dialogue_file

    report = CheckReport()
    table_chars = set(read_text_table(ja_dir / JA_TEXT_TABLE_FILE).values())
    font = load_bdf(font_path)
    reader = sudachi_reader() if readings else None
    report.readings_checked = reader is not None

    for f in override_files(override_dir):
        report.files.append(f.name)
        kana_path = (ja_dir / f.name) if f.name == INLINE_STRINGS_FILE else (ja_dir / "dialogue" / f.name)
        if not kana_path.is_file():
            report.errors.append(f"{f.name}: no kana file {kana_path.name} to convert")
            continue
        try:
            if f.name == INLINE_STRINGS_FILE:
                kana_map = json.loads(kana_path.read_text(encoding="utf-8"))
                kanji_map = json.loads(f.read_text(encoding="utf-8"))
                pairs = []
                for key, value in kanji_map.items():
                    if key not in kana_map:
                        report.errors.append(f"{f.name}: {key[:40]!r}...: not a kana inline string")
                        continue
                    pairs.append((key, parse_inline_to_ops(kana_map[key]), parse_inline_to_ops(value)))
                for key, kana_ops, kanji_ops in pairs:
                    where = f"{f.name} {key[:40]!r}"
                    _check_message(report, where, kana_ops, kanji_ops, table_chars, font, False, reader)
                continue
            kana_msgs = deserialize_dialogue_file(kana_path.read_text(encoding="utf-8"))
            kanji_msgs = deserialize_dialogue_file(f.read_text(encoding="utf-8"))
        except Exception as exc:  # bad YAML or JSON, an unknown op, a malformed op
            report.errors.append(f"{f.name}: can't be read: {exc}")
            continue
        if list(kana_msgs) != list(kanji_msgs):
            gone = [label for label in kana_msgs if label not in kanji_msgs]
            new = [label for label in kanji_msgs if label not in kana_msgs]
            report.errors.append(
                f"{f.name}: labels differ from the kana file (missing {gone[:3]}, unknown {new[:3]}"
                f"{', reordered' if not gone and not new else ''})"
            )
            continue
        for label, kana_ops in kana_msgs.items():
            kana_only = label.startswith(KANA_ONLY_LABEL_PREFIXES)
            _check_message(
                report, f"{f.name} {label}", kana_ops, kanji_msgs[label], table_chars, font, kana_only, reader
            )
    return report


# --- Readings (SudachiPy, optional) ---------------------------------------------------


def sudachi_reader() -> "Callable[[str], str] | None":
    """Return ``text -> reading`` with SudachiPy and ``sudachidict_core``, or None without them.

    A morpheme with a character outside the kana blocks reads as its Sudachi
    reading; the rest (kana, spaces, symbols) as itself.
    """
    try:
        from sudachipy import dictionary, tokenizer
    except ImportError:
        return None
    d = dictionary.Dictionary(dict="core")
    tok = d.tokenizer() if hasattr(d, "tokenizer") else d.create()
    mode = tokenizer.Tokenizer.SplitMode.C

    def read(text: str) -> str:
        return "".join(
            m.reading_form() if any(_is_kanji(ch) for ch in m.surface()) else m.surface()
            for m in tok.tokenize(text, mode)
        )

    return read


def _is_kanji(ch: str) -> bool:
    o = ord(ch)
    return 0x3400 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF or ch in "々〆〇ヶ"


_VOWELS = {
    **dict.fromkeys("アァカガサザタダナハバパマヤャラワヮ", "ア"),
    **dict.fromkeys("イィキギシジチヂニヒビピミリヰ", "イ"),
    **dict.fromkeys("ウゥクグスズツヅヌフブプムユュルヴ", "ウ"),
    **dict.fromkeys("エェケゲセゼテデネヘベペメレヱ", "エ"),
    **dict.fromkeys("オォコゴソゾトドノホボポモヨョロヲ", "オ"),
}


def normalise_reading(s: str) -> str:
    """Katakana letters of ``s``, with long vowels spelled one way.

    Hiragana becomes katakana; anything else but katakana (spaces, symbols,
    bullets, digits) is dropped; ``ー`` and the long-vowel spellings オウ and
    エイ become the vowel repeated (トーキョー, トウキョウ, トオキョオ all match).
    """
    out: list[str] = []
    for ch in s:
        o = ord(ch)
        if 0x3041 <= o <= 0x3096:
            ch = chr(o + 0x60)
        if not 0x30A1 <= ord(ch) <= 0x30FC:
            continue
        prev = _VOWELS.get(out[-1]) if out else None
        if ch == "ー" or (ch == "ウ" and prev == "オ") or (ch == "イ" and prev == "エ"):
            if prev is None:
                continue
            ch = prev
        out.append(ch)
    return "".join(out)


# --- Packing ------------------------------------------------------------------------


def pack_kanji(
    override_dir: Path,
    font_path: Path,
    out: Path,
    kana_dialogue: list[tuple[Path, dict[str, list[dict]]]],
    reverse_table: dict[str, int],
    reverse_names: dict,
    us_label_addrs: dict[str, int],
    us_inline: dict[str, int],
    kana_inline: dict[str, str],
    ja_dir: Path,
) -> int:
    """Pack the kanji script to ``out`` (``<output>/JA_KANJI/``); return the files written.

    Called by ``pack_ja`` once the kana Locale is packed, with what it packed
    (``kana_dialogue``: file and messages in packing order; ``us_inline``: US
    inline string -> offset).  A script that fails :func:`check_override`'s
    (a)-(c), or changes a message's logic, is skipped with a warning (kana
    Japanese and English still build).
    """
    from ebtools.cli.pack_all import _compile_dialogue
    from ebtools.text_dsl.string_table import StringTableBuilder
    from ebtools.text_dsl.yaml_io import deserialize_dialogue_file

    if out.exists():
        shutil.rmtree(out)
    if not override_files(override_dir):
        return 0
    try:
        report = check_override(ja_dir, override_dir, font_path, readings=False)
    except (ValueError, TypeError, KeyError, OSError, yaml.YAMLError) as exc:
        # A broken script must not take the English and kana build down
        print(f"Warning: skipping the Japanese kanji Locale, {override_dir} can't be read: {exc}", file=sys.stderr)
        return 0
    if not report.ok:
        print(
            f"Warning: skipping the Japanese kanji Locale, {len(report.errors)} problems in "
            f"{override_dir} (run `ebtools check-kanji`): {report.errors[:3]}",
            file=sys.stderr,
        )
        return 0

    by_name = {f.name: f for f in override_files(override_dir)}
    dialogue = [
        (f, deserialize_dialogue_file(by_name[f.name].read_text(encoding="utf-8")) if f.name in by_name else msgs)
        for f, msgs in kana_dialogue
    ]
    # The logic invariant (J1's, against the kana message, which pack_ja checked
    # against the US one): check_override's op check implies it; kept explicit.
    kana_by_label = {label: ops for _f, msgs in kana_dialogue for label, ops in msgs.items()}
    drifted = [
        label
        for _f, msgs in dialogue
        for label, ops in msgs.items()
        if strip_presentation(ops) != strip_presentation(kana_by_label[label])
    ]
    if drifted:
        print(
            f"Warning: skipping the Japanese kanji Locale, {len(drifted)} messages don't run the kana "
            f"message's logic: {drifted[:5]}",
            file=sys.stderr,
        )
        return 0

    inline_path = override_dir / INLINE_STRINGS_FILE
    inline = {**kana_inline, **(json.loads(inline_path.read_text(encoding="utf-8")) if inline_path.is_file() else {})}

    kanji = kanji_table(report.kanji)
    table = kanji_reverse_table(reverse_table, kanji)
    blob, label_addrs = _compile_dialogue(dialogue, JA_DIALOGUE_BASE, table, reverse_names)
    xlat: dict[int, int] = {}
    for label, us_addr in us_label_addrs.items():
        xlat.setdefault(us_addr, label_addrs[label])
    strings = StringTableBuilder(table)
    for us_text, us_offset in us_inline.items():
        xlat[us_offset] = JA_INLINE_BASE + strings.add(inline.get(us_text, ""))
    inline_blob = strings.build()
    glyphs, widths, chars = pack_kanji_font(load_bdf(font_path), kanji)

    files = {
        "text/dialogue.bin": blob,
        "text/inline_strings.bin": inline_blob,
        "text/xlat.bin": b"".join(struct.pack("<II", k, v) for k, v in sorted(xlat.items())),
        "fonts/kanji.gfx": glyphs,
        "fonts/kanji.bin": widths,
        "fonts/kanji_chars.bin": chars,
    }
    for rel, data in files.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(
        f"  Packed Japanese kanji Locale: {len(report.files)} script files, {report.converted} converted "
        f"messages, {len(kanji)} kanji, dialogue {len(blob)} bytes"
    )
    return len(files)


# --- CLI ----------------------------------------------------------------------------


def check_kanji(
    override: Annotated[Path | None, Parameter(help="The kanji script (default src/custom_assets/ja_kanji)")] = None,
    *,
    assets: Annotated[Path, Parameter(help="The assets dir with ja/ (extract-ja)")] = Path("src/assets"),
    font: Annotated[Path | None, Parameter(help="The kanji font BDF")] = None,
    readings: Annotated[bool, Parameter(help="Compare readings with SudachiPy, when installed")] = True,
    show: Annotated[int, Parameter(help="Problems listed per kind (0 = all)")] = 50,
) -> None:
    """Check a kanji script (the Japanese kanji Locale's override folder) before packing it.

    Errors (exit 1): an unknown file, labels that differ from the kana file, an op
    other than text that changed, a character neither the text table nor the
    kanji font has. Warnings: texts whose SudachiPy reading differs from the kana.
    """
    custom = assets.parent / "custom_assets"
    override = override or custom / KANJI_OVERRIDE_SUBDIR
    font = font or custom / KANJI_FONT_BDF
    ja_dir = assets / JA_ASSETS_SUBDIR
    if not (ja_dir / JA_TEXT_TABLE_FILE).is_file():
        sys.exit(f"check-kanji: no kana assets in {ja_dir} (run `ebtools extract-ja`)")
    if not override_files(override):
        sys.exit(f"check-kanji: no kanji script in {override}")
    report = check_override(ja_dir, override, font, readings=readings)

    def listing(items: list[str]) -> None:
        for line in items[: show or None]:
            print(f"  {line}")
        if show and len(items) > show:
            print(f"  ... and {len(items) - show} more")

    print(
        f"check-kanji: {len(report.files)} files, {report.messages} messages, {report.converted} converted, "
        f"{len(report.kanji)} kanji"
    )
    print(f"errors: {len(report.errors)}")
    listing(report.errors)
    if report.readings_checked:
        print(f"reading mismatches (warnings, review them): {len(report.readings)}")
        listing(report.readings)
    elif readings:
        print("readings not checked: install the kanji extra (sudachipy, sudachidict_core)")
    if not report.ok:
        sys.exit(1)

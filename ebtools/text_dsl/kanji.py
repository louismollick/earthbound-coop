"""Kanji glyph codes, for the Japanese kanji Locale (docs/ja-plan.md J4).

Mother 2's text table has no kanji: codes below 0x20 are control codes and
0x20-0xFF are its kana and symbol glyphs.  A kanji (any character of a kanji
script that the Japanese text table lacks) is three bytes:

    KANJI_PREFIX, 0x20 + index // 224, 0x20 + index % 224

``index`` is the character's position in the kanji glyph table that pack-all
builds from the characters the script uses (``JA_KANJI/fonts/kanji_chars.bin``).

0x15 is the US compressed-text prefix.  The port's text never carries it (US
pack-all writes dictionary text out in full and Mother 2 text has no
dictionary), so it is free in every Japanese text stream.  Both digits are
0x20 or above, so a scanner that steps over 0x15 as a one-byte op and reads the
digits as letters (``coop_look.c``, ``cc_skip_args``) still stays in step with
the stream.
"""

from collections.abc import Iterable, Sequence

KANJI_PREFIX = 0x15
KANJI_DIGIT_BASE = 0x20
KANJI_DIGITS = 0x100 - KANJI_DIGIT_BASE
KANJI_MAX = KANJI_DIGITS * KANJI_DIGITS


def kanji_code(index: int) -> bytes:
    """Return the three-byte text code of kanji ``index``."""
    if not 0 <= index < KANJI_MAX:
        raise ValueError(f"kanji index {index} out of range (max {KANJI_MAX - 1})")
    return bytes((KANJI_PREFIX, KANJI_DIGIT_BASE + index // KANJI_DIGITS, KANJI_DIGIT_BASE + index % KANJI_DIGITS))


def kanji_index(d1: int, d2: int) -> int:
    """Return the kanji index of the two digit bytes after ``KANJI_PREFIX``."""
    if d1 < KANJI_DIGIT_BASE or d2 < KANJI_DIGIT_BASE:
        raise ValueError(f"bad kanji digits 0x{d1:02X} 0x{d2:02X}")
    return (d1 - KANJI_DIGIT_BASE) * KANJI_DIGITS + (d2 - KANJI_DIGIT_BASE)


def kanji_reverse_table(reverse_table: dict[str, int], kanji: Sequence[str]) -> dict[str, int | bytes]:
    """Return ``reverse_table`` (char -> code) plus every kanji's three-byte code.

    For ``compile_text_block`` and ``StringTableBuilder``.
    """
    clash = [ch for ch in kanji if ch in reverse_table]
    if clash:
        raise ValueError(f"kanji already in the text table: {clash[:5]}")
    return {**reverse_table, **{ch: kanji_code(i) for i, ch in enumerate(kanji)}}


def kanji_table(chars: Iterable[str]) -> list[str]:
    """Return the kanji glyph table for ``chars``: each character once, by code point."""
    table = sorted(set(chars))
    if len(table) > KANJI_MAX:
        raise ValueError(f"{len(table)} kanji, more than the {KANJI_MAX} the code holds")
    return table

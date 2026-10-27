"""Japanese interface assets: naming screen data and the Mr. Saturn and title fonts.

``extract-ja`` calls :func:`extract_interface` (Mother 2 ROM -> ``<assets>/ja/``)
and ``pack-all`` calls :func:`pack_interface` (``<assets>/ja/`` -> ``<output>/JA/``).
The ROM offsets are in ``ja_locale.yml`` ``rom``.

Written to ``<assets>/ja/``:

- ``naming.json``: the naming prompts, the confirmation strings, the Don't Care
  names, the name registry prompt and the romaji -> kana pairs, as text.
- ``fonts/mrsaturn.png`` + ``.json``: Mr. Saturn's glyphs in the US variable-width
  font format, one per text code (0x20-0xFF) plus his dakuten and handakuten
  marks. Width 0 marks a code Mother 2 prints as a normal tile.
- ``fonts/title.png``: the 8x8 window title glyphs (2bpp, one per code 0x20-0xFF).

Packed to ``<output>/JA/``: ``data/naming_prompts.bin``,
``data/dont_care_names.bin`` and ``data/name_registry_request_string.bin``
(overriding the US assets of the same path), ``data/naming_confirm.bin``,
``data/consonant_vowel_transliteration_pairs.bin``, ``fonts/mrsaturn.gfx``/``.bin``
and ``fonts/title.gfx``.
"""

import json
from pathlib import Path

from PIL import Image

from ebtools.ja_locale import JA_EXTRA_GLYPH_CODES, JA_FIRST_GLYPH, JA_FONT_GLYPHS, JaLocaleConfig

NAMING_FILE = "naming.json"

# Mother 2 string sizes (asm/intro/file_select_menu_loop-jp.asm and the -jp files
# it calls): NAME_THEM_STRING_LENGTH, the PRINT_STRING lengths of the
# confirmation labels, a Don't Care name, NAME_REGISTRY_REQUEST_STRING.
PROMPT_SIZE = 15
PROMPT_COUNT = 7
DONT_CARE_SIZE = 6
DONT_CARE_GROUPS = 7
# naming_confirm.bin: the confirmation strings in ROM order (src/intro/naming_ja.c).
CONFIRM_FIELDS = (("favorite_food", 9), ("coolest_thing", 11), ("are_you_sure", 12), ("yep", 3), ("nope", 4))
_CONFIRM_KEYS = ("favoriteFood", "coolestThing", "areYouSure", "areYouSureYep", "areYouSureNope")  # ja_locale.yml
REGISTRY_SIZE = 11
TRANSLIT_VOWELS = 5

# The US variable-width font format (ebtools/parsers/font.py): 1bpp, 0 = ink,
# 16 rows per 8 px column, two columns per glyph.
_GLYPH_BYTES = 32


def _decode(raw: bytes, table: dict[int, str]) -> str:
    """Text up to the first 0 (only zeros may follow)."""
    end = raw.index(0) if 0 in raw else len(raw)
    if any(raw[end:]):
        raise ValueError(f"bytes after the terminator: {raw.hex()}")
    return "".join(table[c] for c in raw[:end])


def _encode(text: str, size: int, reverse: dict[str, int]) -> bytes:
    """``text`` in the Mother 2 encoding, zero-padded to ``size`` bytes."""
    raw = bytes(reverse[ch] for ch in text)
    if len(raw) > size:
        raise ValueError(f"{text!r} is longer than {size} bytes")
    return raw.ljust(size, b"\0")


# --- Extraction ----------------------------------------------------------------


def extract_interface(
    rom: bytes, config: JaLocaleConfig, table: dict[int, str], main_glyphs: bytes, out_dir: Path
) -> dict:
    """Write the naming data and the Mr. Saturn and title fonts to ``out_dir`` (``<assets>/ja``).

    ``main_glyphs`` is the Japanese main font in the US format (``JA_FONT_GLYPHS``
    glyphs): Mr. Saturn's tile codes reuse it, as PRINT_MRSATURN_LETTER prints
    them with the normal font.
    """
    r = config.rom

    def strings(key: str) -> list[str]:
        return [_decode(raw, table) for raw in r[key].read(rom)]

    names = strings("dontCareNames")
    pairs = r["transliterationPairs"].read(rom)[0]
    naming = {
        "prompts": strings("namingPrompts"),
        **{field: strings(key)[0] for (field, _), key in zip(CONFIRM_FIELDS, _CONFIRM_KEYS)},
        "name_registry_request": strings("nameRegistryRequest")[0],
        "dont_care_names": [names[g * 7 : g * 7 + 7] for g in range(DONT_CARE_GROUPS)],
        # PROCESS_NAME_INPUT_STRING: letter -> kana for the vowels a, i, u, e, o
        "transliteration": {
            chr(0x41 + letter): [
                "".join(table[c] for c in pairs[(letter * 5 + v) * 2 : (letter * 5 + v) * 2 + 2] if c)
                for v in range(TRANSLIT_VOWELS)
            ]
            for letter in range(26)
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / NAMING_FILE).write_text(json.dumps(naming, ensure_ascii=False, indent=1) + "\n")

    saturn = export_mrsaturn_font(rom, config, main_glyphs, out_dir / "fonts")
    export_title_font(r["titleFont"].read(rom)[0], out_dir / "fonts" / "title.png")
    return {"mrsaturn_glyphs": saturn}


def _tile_rows(tiles: bytes, tile: int) -> list[int]:
    """The 8 rows of a 2bpp tile, 1 = background (colour 3, both planes set)."""
    return [tiles[tile * 16 + y * 2] & tiles[tile * 16 + y * 2 + 1] for y in range(8)]


def export_mrsaturn_font(rom: bytes, config: JaLocaleConfig, main_glyphs: bytes, fonts_dir: Path) -> int:
    """Mr. Saturn's glyphs, one per Japanese font glyph (codes 0x20-0xFF, then the marks).

    PRINT_MRSATURN_LETTER (asm/text/print_mrsaturn_letter.asm) looks the code up
    in MRSATURN_CHAR_TILE_MAP[code - 16]: 0 prints the code as a normal tile,
    else glyph ``map - 1`` of MRSATURN_FONT_DATA, ``MRSATURN_CHAR_WIDTH_TABLE``
    pixels wide (RENDER_MRSATURN_VWF_CHARACTER: no CHARACTER_PADDING). Glyph
    ``i`` is the 2x2 tiles at ``(i & 7) * 2 + (i >> 3) * 32`` (+1 right, +16
    bottom) of the 16-tile-wide sheet. The stored width is the Mother 2 width
    minus 1 (the US renderer adds CHARACTER_PADDING 1); a tile code gets the
    main font's glyph and width 0.
    """
    from ebtools.parsers.font import export_font_png

    r = config.rom
    char_map = r["mrSaturnCharMap"].read(rom)[0]
    widths_m2 = r["mrSaturnWidths"].read(rom)[0]
    sheet = r["mrSaturnFont"].read(rom)[0]

    codes = list(range(JA_FIRST_GLYPH, 0x100)) + list(JA_EXTRA_GLYPH_CODES)
    gfx = bytearray()
    widths = bytearray()
    vwf = 0
    for i, code in enumerate(codes):
        m = char_map[code - 16]
        if not m:
            gfx += main_glyphs[i * _GLYPH_BYTES : (i + 1) * _GLYPH_BYTES]
            widths.append(0)
            continue
        idx = m - 1
        tl = (idx & 7) * 2 + (idx >> 3) * 32
        for col in (tl, tl + 1):  # left column, right column: top tile then bottom
            gfx += bytes(_tile_rows(sheet, col) + _tile_rows(sheet, col + 16))
        widths.append(widths_m2[idx] - 1)
        vwf += 1
    assert len(codes) == JA_FONT_GLYPHS
    export_font_png(bytes(gfx), bytes(widths), "mrsaturn", _GLYPH_BYTES, fonts_dir, glyph_count=JA_FONT_GLYPHS)
    return vwf


_TITLE_COLS = 16
_TITLE_PALETTE = [0, 0, 0, 255, 255, 255, 170, 170, 170, 85, 85, 85]


def export_title_font(tiles: bytes, png_path: Path) -> None:
    """The title glyphs as a 4-colour indexed PNG, 16 tiles per row (code 0x20 first)."""
    from ebtools.parsers._tiles import decode_2bpp_tile

    count = len(tiles) // 16
    img = Image.new("P", (_TITLE_COLS * 8, -(-count // _TITLE_COLS) * 8))
    img.putpalette(_TITLE_PALETTE + [0] * (768 - len(_TITLE_PALETTE)))
    for t in range(count):
        for y, row in enumerate(decode_2bpp_tile(tiles, t * 16)):
            for x, p in enumerate(row):
                img.putpixel(((t % _TITLE_COLS) * 8 + x, (t // _TITLE_COLS) * 8 + y), p)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(png_path)


# --- Packing -------------------------------------------------------------------


def interface_is_current(ja_dir: Path) -> bool:
    """Whether ``ja_dir`` has every interface file and the main font with the marks.

    An extraction from before them would build a Japanese Locale whose C code
    references assets that don't exist.
    """
    from ebtools.parsers.font import FontMetadata

    fonts = ja_dir / "fonts"
    needed = [ja_dir / NAMING_FILE, fonts / "mrsaturn.png", fonts / "mrsaturn.json", fonts / "title.png"]
    if not all(p.exists() for p in needed) or not (fonts / "main.json").exists():
        return False
    return FontMetadata.model_validate_json((fonts / "main.json").read_bytes()).glyph_count == JA_FONT_GLYPHS


def pack_interface(ja_dir: Path, out: Path, reverse: dict[str, int]) -> int:
    """Pack ``ja_dir`` (``<assets>/ja``) to ``out`` (``<output>/JA``); return the files written."""
    from ebtools.parsers._tiles import encode_2bpp_tile
    from ebtools.parsers.font import pack_font

    written = 0

    def write(rel: str, data: bytes) -> None:
        nonlocal written
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written += 1

    naming_path = ja_dir / NAMING_FILE
    if naming_path.exists():
        n = json.loads(naming_path.read_text())
        if len(n["prompts"]) != PROMPT_COUNT or len(n["dont_care_names"]) != DONT_CARE_GROUPS:
            raise ValueError(f"{naming_path}: expected {PROMPT_COUNT} prompts and {DONT_CARE_GROUPS} name groups")
        write("data/naming_prompts.bin", b"".join(_encode(s, PROMPT_SIZE, reverse) for s in n["prompts"]))
        write(
            "data/dont_care_names.bin",
            b"".join(_encode(s, DONT_CARE_SIZE, reverse) for group in n["dont_care_names"] for s in group),
        )
        write("data/naming_confirm.bin", b"".join(_encode(n[f], size, reverse) for f, size in CONFIRM_FIELDS))
        write("data/name_registry_request_string.bin", _encode(n["name_registry_request"], REGISTRY_SIZE, reverse))
        pairs = bytearray()
        for letter in range(26):
            for kana in n["transliteration"][chr(0x41 + letter)]:
                pairs += _encode(kana, 2, reverse)
        write("data/consonant_vowel_transliteration_pairs.bin", bytes(pairs))

    fonts = ja_dir / "fonts"
    if (fonts / "mrsaturn.png").exists():
        gfx, widths = pack_font(fonts / "mrsaturn.png", fonts / "mrsaturn.json")
        write("fonts/mrsaturn.gfx", gfx)
        write("fonts/mrsaturn.bin", widths)
    if (fonts / "title.png").exists():
        img = Image.open(fonts / "title.png")
        tiles = bytearray()
        for t in range((img.width // 8) * (img.height // 8)):
            tx, ty = (t % (img.width // 8)) * 8, (t // (img.width // 8)) * 8
            tiles += encode_2bpp_tile([[img.getpixel((tx + x, ty + y)) & 3 for x in range(8)] for y in range(8)])
        write("fonts/title.gfx", bytes(tiles))
    return written

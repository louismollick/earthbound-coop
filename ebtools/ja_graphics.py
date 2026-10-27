"""Japanese graphics and cinematics (docs/ja-plan.md J3): Mother 2 data that replaces US data.

``extract-ja`` calls :func:`extract_graphics` (Mother 2 ROM -> ``<assets>/ja/``)
and ``pack-all`` calls :func:`pack_graphics` (``<assets>/ja/`` -> ``<output>/JA/``).

Written to ``<assets>/ja/bin/``, each file the Mother 2 bytes for the asset at
the same path, copied to ``JA/<path>`` as is (``ASSET_DATA`` serves them in
Japanese):

- Same format and meaning as the US asset (no C change): the town map labels,
  maps 2 and 4 and icon spritemaps (``icon_spritemap_ptrs.bin`` rebased to the
  US spritemap address the C code subtracts), the sound stone, the gas station
  and Nintendo logo of the attract mode, the staff credits font, and the map
  tilesets (``MAP_DUMP_SUBDIRS``: graphics and arrangements, whose signs
  have Mother 2's words; packed decompressed, as ``.gfx.raw`` / ``.arr.raw``,
  which is what the map loader reads). The map chunks stay US (two blocks the US moved,
  collision included), and so do the map palettes (their colours are the same;
  only an embedded pointer moved).
- Same meaning, Mother 2's format (Japanese C paths read them): the flyover and
  coffee/tea scripts (two-byte glyph codes), the "TO BE CONTINUED..." animation
  (its own tile size and frame count), the staff text, the Lumine Hall wall
  text (3 + name + 97 codes) and the cast names' graphics and palette.
- Japanese only: ``fonts/flyover.gfx`` (the cinematic font, 12x12 1bpp glyphs
  with kana and ~100 kanji), ``fonts/flyover_map.bin`` (text code - 0x20 ->
  flyover glyph, for party names), ``ending/cast_names.bin`` (the cast
  names as text codes) and ``graphics/mother2_text_window.gfx.lzhal`` (Mother
  2's text window graphics, whose font tiles the cast names are drawn with).

``<assets>/ja/text_window_tiles.bin`` holds Mother 2's "YOU WIN!" tiles; pack-all
patches them into the US text window graphics (whose other tiles stay US).
``<assets>/ja/graphics_files.json`` lists the ``bin/`` files; pack-all skips the
Japanese Locale unless all of them are there (:func:`graphics_are_current`).
"""

import json
import struct
from pathlib import Path

from ebtools.config import DumpDoc

BIN_SUBDIR = "bin"
TEXT_WINDOW_TILES_FILE = "text_window_tiles.bin"
MANIFEST_FILE = "graphics_files.json"  # the bin/ files extract_graphics wrote

# (mother2.yml subdir, name, extension) -> asset path: raw Mother 2 ROM bytes
# (compressed as stored) for the asset at that path.
RAW_DUMPS: dict[tuple[str, str, str], str] = {
    ("JP/town_maps", "label", "gfx"): "town_maps/label.gfx.lzhal",
    ("JP/town_maps", "2", "bin"): "town_maps/2.bin.lzhal",
    ("JP/town_maps", "4", "bin"): "town_maps/4.bin.lzhal",
    ("JP/graphics", "sound_stone", "gfx"): "graphics/sound_stone.gfx.lzhal",
    ("JP/graphics/animations", "the_end", "anim"): "graphics/animations/the_end.anim.lzhal",
    ("JP/intro", "gas_station", "gfx"): "intro/gas_station.gfx.lzhal",
    ("JP/intro", "gas_station", "arr"): "intro/gas_station.arr.lzhal",
    ("JP/intro/logos", "nintendo", "gfx"): "intro/logos/nintendo.gfx.lzhal",
    ("JP/intro/logos", "nintendo", "arr"): "intro/logos/nintendo.arr.lzhal",
    ("JP/ending", "credits_font", "gfx"): "ending/credits_font.gfx.lzhal",
    ("JP/ending", "cast_names", "gfx"): "ending/cast_names.gfx.lzhal",
    ("JP", "coffee", "flyover"): "coffee.bin",
    ("JP", "tea", "flyover"): "tea.bin",
    # Mother 2's text window graphics as they are (its 8x16 font at the text
    # codes): the cast names' tiles (LOAD_CAST_SCENE, load_cast_scene-jp.asm)
    ("JP/graphics", "text_window", "gfx"): "graphics/mother2_text_window.gfx.lzhal",
    # UNKNOWN_E10000 (asm/bankconfig/common/bank21.asm): 313 flyover glyphs of
    # 18 bytes (DECOMP_ENTRY2, asm/system/decomp.asm)
    ("JP", "E10000", "bin"): "fonts/flyover.gfx",
}

# Every Mother 2 dump in these mother2.yml subdirs replaces the US asset at
# maps/<kind>/<name>.<ext>.lzhal (block ids, and so collision, are the same).
MAP_DUMP_SUBDIRS = ("JP/maps/gfx", "JP/maps/arrangements")
MAP_PACKED_DIRS = ("maps/gfx/", "maps/arrangements/")

# The eight PLAY_FLYOVER_SCRIPT scripts, one asset each like the US
# (src/game/flyover.c flyover_script_ids): mother2.yml flyoverLabels splits
# the JP "flyovers" dump.
FLYOVERS_DUMP = ("JP", "flyovers", "flyover")
FLYOVER_LABELS = (
    "FLYOVER_INTRO1",
    "FLYOVER_INTRO2",
    "FLYOVER_INTRO3",
    "FLYOVER_WINTERS_INTRO1",
    "FLYOVER_WINTERS_INTRO2",
    "FLYOVER_DALAAM_INTRO1",
    "FLYOVER_DALAAM_INTRO2",
    "FLYOVER_ENDING",
)

# The US text window tiles that differ from Mother 2 in words: "YOU WON!" /
# "YOU WIN!" (two rows of 9 tiles). Mother 2's text window graphics have 256 more
# tiles (its 8x16 font) before them: Mother 2 tile = US tile + 0x100.
YOU_WIN_TILES = (*range(0x180, 0x189), *range(0x190, 0x199))
TEXT_WINDOW_US_PATH = "US/graphics/text_window.gfx.lzhal"
_M2_TEXT_WINDOW_EXTRA_TILES = 0x100
_TILE_2BPP = 16

# US TOWN_MAP_ICON_SPRITEMAP's address in its bank: src/game/town_map.c
# SPRITEMAP_ROM_BASE subtracts it from the pointer table's entries.
US_TOWN_MAP_SPRITEMAP_BASE = 0xF203
TOWN_MAP_ICON_PALETTE_SIZE = 64  # TOWN_MAP_ICON_SPRITEMAP follows the palette

# romSymbols this module reads (ja_interface.rom_symbols_used adds them).
ROM_SYMBOLS = (
    "CAST_BG_PALETTE",
    "JP_CAST_NAME_PTR_TABLE",
    "JP_FONT_WIDTH_TABLE",
    "STAFF_TEXT",
    "TOWN_MAP_ICON_PALETTE",
    "TOWN_MAP_ICON_SPRITEMAP_PTR_TABLE",
)

# JP_FONT_WIDTH_TABLE's first part: text code - 0x20 -> flyover glyph
# (RENDER_PARTY_MEMBER_NAME, asm/intro/render_party_member_name-jp.asm). The
# cast name strings follow it, up to JP_CAST_NAME_PTR_TABLE.
FLYOVER_MAP_SIZE = 0xE0
CAST_NAME_COUNT = 48


def _dump(rom: bytes, doc: DumpDoc, key: tuple[str, str, str]) -> tuple[int, bytes]:
    """The ROM offset and bytes of the mother2.yml dump entry ``key``."""
    subdir, name, ext = key
    (e,) = [e for e in doc.dumpEntries if e.subdir == subdir and e.name == name and e.extension == ext]
    return e.offset, rom[e.offset : e.offset + e.size]


def map_tilesets(rom: bytes, doc: DumpDoc) -> dict[str, bytes]:
    """``{asset path: compressed data}`` for the map tileset dumps (``MAP_DUMP_SUBDIRS``)."""
    out = {}
    for e in doc.dumpEntries:
        if e.subdir in MAP_DUMP_SUBDIRS:
            if not e.compressed:
                raise ValueError(f"mother2.yml {e.subdir}/{e.name}: expected compressed")
            out[f"{e.subdir.removeprefix('JP/')}/{e.name}.{e.extension}.lzhal"] = rom[e.offset : e.offset + e.size]
    return out


def split_flyovers(rom: bytes, doc: DumpDoc) -> dict[str, bytes]:
    """``{asset path: script}`` for the eight flyovers (each ends at its 0x00)."""
    base, data = _dump(rom, doc, FLYOVERS_DUMP)
    by_label = {label: addr - 0xC00000 - base for addr, label in doc.flyoverLabels.items()}
    starts = [by_label[label] for label in FLYOVER_LABELS]
    if starts != sorted(starts) or starts[0] != 0:
        raise ValueError("mother2.yml flyoverLabels: the flyovers are not in script order")
    ends = [*starts[1:], len(data)]
    return {f"{label.lower()}.bin": data[s:e] for label, s, e in zip(FLYOVER_LABELS, starts, ends)}


def town_map_spritemaps(rom: bytes, symbols: dict[str, tuple[int, int]]) -> tuple[bytes, bytes]:
    """Mother 2's town map icon spritemaps and their pointer table, rebased to the US address."""
    pal, _ = symbols["TOWN_MAP_ICON_PALETTE"]
    ptrs_off, ptrs_size = symbols["TOWN_MAP_ICON_SPRITEMAP_PTR_TABLE"]
    start = pal + TOWN_MAP_ICON_PALETTE_SIZE
    m2_base = (start + 0xC00000) & 0xFFFF
    ptrs = struct.unpack(f"<{ptrs_size // 2}H", rom[ptrs_off : ptrs_off + ptrs_size])
    if any(not m2_base <= p < m2_base + ptrs_off - start for p in ptrs):
        raise ValueError("TOWN_MAP_ICON_SPRITEMAP_PTR_TABLE points outside the spritemaps")
    rebased = struct.pack(f"<{len(ptrs)}H", *(p - m2_base + US_TOWN_MAP_SPRITEMAP_BASE for p in ptrs))
    return rom[start:ptrs_off], rebased


def cast_names(rom: bytes, symbols: dict[str, tuple[int, int]]) -> bytes:
    """The cast names (JP_CAST_NAME_PTR_TABLE) as 48 u16 offsets, then the strings.

    Each offset is from the start of the returned data; a string is text codes
    up to a 0 (PREPARE_CAST_NAME_TILEMAP, asm/ending/prepare_cast_name_tilemap-jp.asm).
    """
    table_off, table_size = symbols["JP_FONT_WIDTH_TABLE"]
    ptrs_off, ptrs_size = symbols["JP_CAST_NAME_PTR_TABLE"]
    if ptrs_size < CAST_NAME_COUNT * 2 or table_off + table_size != ptrs_off:
        raise ValueError("JP_CAST_NAME_PTR_TABLE does not follow the cast name strings")
    strings_off = table_off + FLYOVER_MAP_SIZE
    strings = rom[strings_off:ptrs_off]
    bank_base = (strings_off + 0xC00000) & 0xFFFF
    header = CAST_NAME_COUNT * 2
    offsets = []
    for p in struct.unpack(f"<{CAST_NAME_COUNT}H", rom[ptrs_off : ptrs_off + header]):
        rel = p - bank_base
        if not 0 <= rel < len(strings) or 0 not in strings[rel:]:
            raise ValueError(f"JP_CAST_NAME_PTR_TABLE entry 0x{p:04X} is not a cast name string")
        offsets.append(header + rel)
    return struct.pack(f"<{CAST_NAME_COUNT}H", *offsets) + strings


def staff_text_length(data: bytes) -> int:
    """Bytes up to and including the staff text's end command (CREDITS_SCROLL_FRAME).

    Commands: 1 / 2 text up to a 0 (small / big), 3 n (spacing), 4 (the
    player's name), 0xFF (end); include/staffmacros.asm.
    """
    i = 0
    while i < len(data):
        cmd = data[i]
        if cmd in (1, 2):
            i = data.index(0, i + 1) + 1
        elif cmd == 3:
            i += 2
        elif cmd == 4:
            i += 1
        elif cmd == 0xFF:
            return i + 1
        else:
            raise ValueError(f"staff text: unknown command 0x{cmd:02X} at {i}")
    raise ValueError("staff text: no end command")


def you_win_tiles(rom: bytes, doc: DumpDoc) -> bytes:
    """Mother 2's tiles for ``YOU_WIN_TILES``, in that order (2bpp)."""
    from ebtools.hallz.decompress import decompress

    _, data = _dump(rom, doc, ("JP/graphics", "text_window", "gfx"))
    gfx = decompress(data)
    out = bytearray()
    for t in YOU_WIN_TILES:
        m2 = t + _M2_TEXT_WINDOW_EXTRA_TILES
        out += gfx[m2 * _TILE_2BPP : (m2 + 1) * _TILE_2BPP]
    return bytes(out)


def extract_graphics(
    rom: bytes, doc: DumpDoc, symbols: dict[str, tuple[int, int]], rom_ranges: dict, out_dir: Path
) -> int:
    """Write ``<out_dir>/bin/`` and the text window tiles (``out_dir`` is ``<assets>/ja``).

    ``rom_ranges`` is ``ja_locale.yml`` ``rom`` (for ``lumineHallText``).
    Returns the number of files written.
    """
    files: dict[str, bytes] = {path: _dump(rom, doc, key)[1] for key, path in RAW_DUMPS.items()}
    files.update(map_tilesets(rom, doc))
    files.update(split_flyovers(rom, doc))
    files["town_maps/icon_spritemaps.bin"], files["town_maps/icon_spritemap_ptrs.bin"] = town_map_spritemaps(
        rom, symbols
    )
    off, size = symbols["JP_FONT_WIDTH_TABLE"]
    files["fonts/flyover_map.bin"] = rom[off : off + FLYOVER_MAP_SIZE]
    files["ending/cast_names.bin"] = cast_names(rom, symbols)
    off, size = symbols["CAST_BG_PALETTE"]
    files["ending/cast_bg_palette.pal"] = rom[off : off + size]
    off, size = symbols["STAFF_TEXT"]
    staff = rom[off : off + size]
    files["ending/staff_text.bin"] = staff[: staff_text_length(staff)]
    files["data/text/lumine_hall_text.bin"] = rom_ranges["lumineHallText"].read(rom)[0]

    missing = required_bin_files() - set(files)
    if missing:
        raise ValueError(f"extract_graphics wrote no {sorted(missing)}")
    bin_dir = out_dir / BIN_SUBDIR
    for path, data in files.items():
        dest = bin_dir / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    for stale in [p for p in bin_dir.rglob("*") if p.is_file()]:
        if stale.relative_to(bin_dir).as_posix() not in files:
            stale.unlink()
    (out_dir / TEXT_WINDOW_TILES_FILE).write_bytes(you_win_tiles(rom, doc))
    (out_dir / MANIFEST_FILE).write_text(json.dumps(sorted(files), indent=1) + "\n", encoding="utf-8")
    return len(files) + 1


# Files of ``bin/`` that are not RAW_DUMPS or flyovers (extract_graphics).
DERIVED_FILES = (
    "town_maps/icon_spritemaps.bin",
    "town_maps/icon_spritemap_ptrs.bin",
    "fonts/flyover_map.bin",
    "ending/cast_names.bin",
    "ending/cast_bg_palette.pal",
    "ending/staff_text.bin",
    "data/text/lumine_hall_text.bin",
)


def required_bin_files() -> set[str]:
    """Every ``bin/`` file but the map tilesets (whose list comes from mother2.yml).

    The Japanese C paths read all of them (the Japanese-only ones by their
    ``ASSET_JA_*`` ids, which don't exist without them).
    """
    return {*RAW_DUMPS.values(), *(f"{label.lower()}.bin" for label in FLYOVER_LABELS), *DERIVED_FILES}


def graphics_are_current(ja_dir: Path) -> bool:
    """Whether ``ja_dir`` has every file of this module (an older or damaged extraction doesn't).

    ``extract_graphics`` lists what it wrote in ``MANIFEST_FILE``; every listed
    file, every ``required_bin_files()`` file and the text window tiles must be there.
    """
    manifest = ja_dir / MANIFEST_FILE
    if not manifest.exists() or not (ja_dir / TEXT_WINDOW_TILES_FILE).exists():
        return False
    listed = set(json.loads(manifest.read_text(encoding="utf-8")))
    return required_bin_files() <= listed and all((ja_dir / BIN_SUBDIR / p).is_file() for p in listed)


def patch_text_window(us_compressed: bytes, tiles: bytes) -> bytes:
    """The US text window graphics (compressed) with ``tiles`` at ``YOU_WIN_TILES``, recompressed."""
    from ebtools.hallz.compress import compress
    from ebtools.hallz.decompress import decompress

    if len(tiles) != len(YOU_WIN_TILES) * _TILE_2BPP:
        raise ValueError(f"{TEXT_WINDOW_TILES_FILE}: expected {len(YOU_WIN_TILES)} tiles")
    gfx = bytearray(decompress(us_compressed))
    for i, t in enumerate(YOU_WIN_TILES):
        gfx[t * _TILE_2BPP : (t + 1) * _TILE_2BPP] = tiles[i * _TILE_2BPP : (i + 1) * _TILE_2BPP]
    return compress(bytes(gfx))


def pack_graphics(ja_dir: Path, us_table) -> dict[str, bytes]:
    """``{path under JA/: bytes}``: ``bin/``, and the patched text window graphics.

    Files are copied as they are, but the map tilesets: the map loader reads
    them decompressed (``.gfx.raw`` / ``.arr.raw``, pack-all's
    ``RAW_DECOMPRESSED_FAMILIES``), so they are packed that way.
    ``us_table(path)`` returns a US asset (packed or extracted) by its ``US/`` path.
    """
    from ebtools.hallz.decompress import decompress

    bin_dir = ja_dir / BIN_SUBDIR
    out = {}
    for p in sorted(bin_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(bin_dir).as_posix()
        if rel.startswith(MAP_PACKED_DIRS) and rel.endswith(".lzhal"):
            out[rel.removesuffix(".lzhal") + ".raw"] = decompress(p.read_bytes())
        else:
            out[rel] = p.read_bytes()
    tiles = ja_dir / TEXT_WINDOW_TILES_FILE
    if tiles.exists():
        out[TEXT_WINDOW_US_PATH.removeprefix("US/")] = patch_text_window(
            us_table(TEXT_WINDOW_US_PATH), tiles.read_bytes()
        )
    return out

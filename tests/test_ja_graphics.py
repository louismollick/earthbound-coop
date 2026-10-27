"""Japanese graphics and cinematics (ebtools/ja_graphics.py, docs/ja-plan.md J3).

The format tests need nothing or the extracted US binaries; the ROM tests read
``mother2.sfc`` and skip without it.
"""

import struct
from pathlib import Path

import pytest

from ebtools.config import load_dump_doc
from ebtools.hallz.compress import compress
from ebtools.hallz.decompress import decompress
from ebtools.ja_graphics import (
    BIN_SUBDIR,
    CAST_NAME_COUNT,
    FLYOVER_LABELS,
    MANIFEST_FILE,
    RAW_DUMPS,
    TEXT_WINDOW_TILES_FILE,
    US_TOWN_MAP_SPRITEMAP_BASE,
    YOU_WIN_TILES,
    extract_graphics,
    graphics_are_current,
    map_tilesets,
    pack_graphics,
    patch_text_window,
    required_bin_files,
    split_flyovers,
    staff_text_length,
)
from ebtools.ja_locale import load_ja_locale

ROOT = Path(__file__).parent.parent
ROM = ROOT / "mother2.sfc"
BIN = ROOT / "asm" / "bin"

needs_rom = pytest.mark.skipif(not ROM.exists(), reason="needs mother2.sfc")

# The flyover commands (asm/misc/play_flyover_script-jp.asm); any other byte
# starts a two-byte glyph code.
_FLYOVER_ARG_CMDS = {0x01, 0x02, 0x08}
_FLYOVER_GLYPHS = 313  # UNKNOWN_E10000: 0x1602 bytes of 18-byte glyphs


def test_staff_text_length():
    data = bytes([3, 2, 1, 0x42, 0x43, 0, 2, 0x81, 0, 4, 0xFF, 0xAA])
    assert staff_text_length(data) == 11
    with pytest.raises(ValueError):
        staff_text_length(bytes([3, 2, 7]))


def test_us_staff_text_ends_at_its_end_command():
    path = BIN / "US" / "ending" / "staff_text.bin"
    if not path.exists():
        pytest.skip(f"needs {path} (ebtools extract)")
    data = path.read_bytes()
    assert staff_text_length(data) == len(data)


def test_patch_text_window_replaces_only_the_you_win_tiles():
    gfx = bytes(range(256)) * (0x1A0 * 16 // 256)
    tiles = bytes([0xEE]) * (len(YOU_WIN_TILES) * 16)
    out = decompress(patch_text_window(compress(gfx), tiles))
    for t in range(len(gfx) // 16):
        want = tiles[:16] if t in YOU_WIN_TILES else gfx[t * 16 : (t + 1) * 16]
        assert out[t * 16 : (t + 1) * 16] == want, hex(t)


def _flyover_glyph_codes(script: bytes) -> list[int]:
    """The glyph codes of a Mother 2 flyover script, checking its commands."""
    codes, i = [], 0
    while True:
        b = script[i]
        if b == 0:  # the coffee dump runs on past its end to the tea's
            return codes
        if b in _FLYOVER_ARG_CMDS:
            i += 2
        elif b == 0x09:
            i += 1
        else:
            codes.append((b << 8) | script[i + 1])
            i += 2


@needs_rom
def test_extract_and_pack_from_the_rom(tmp_path):
    rom = ROM.read_bytes()
    doc = load_dump_doc(ROOT / "mother2.yml")
    config = load_ja_locale(ROOT / "ja_locale.yml")
    out = tmp_path / "ja"
    assert not graphics_are_current(out)
    extract_graphics(rom, doc, config.romSymbols, config.rom, out)
    assert graphics_are_current(out)
    files = {
        p.relative_to(out / BIN_SUBDIR).as_posix(): p.read_bytes() for p in (out / BIN_SUBDIR).rglob("*") if p.is_file()
    }

    # Every compressed dump decompresses; each map tileset replaces a US one
    # of the same size.
    for path in map_tilesets(rom, doc):
        us = BIN / "US" / path
        if us.exists():
            assert len(decompress(files[path])) == len(decompress(us.read_bytes())), path
    for path in [*RAW_DUMPS.values(), *map_tilesets(rom, doc)]:
        if path.endswith(".lzhal"):
            assert decompress(files[path]), path

    # The flyovers: eight scripts, all glyphs in the font.
    flyovers = split_flyovers(rom, doc)
    assert list(flyovers) == [f"{label.lower()}.bin" for label in FLYOVER_LABELS]
    assert len(files["fonts/flyover.gfx"]) == _FLYOVER_GLYPHS * 18
    for name in [*flyovers, "coffee.bin", "tea.bin"]:
        codes = _flyover_glyph_codes(files[name])
        assert codes and all(0 <= c - 0x8000 < _FLYOVER_GLYPHS for c in codes), name
    assert all(g < _FLYOVER_GLYPHS for g in files["fonts/flyover_map.bin"])

    # The town map spritemap pointers land on spritemaps once rebased.
    sprites = files["town_maps/icon_spritemaps.bin"]
    ptrs = struct.unpack(
        f"<{len(files['town_maps/icon_spritemap_ptrs.bin']) // 2}H", files["town_maps/icon_spritemap_ptrs.bin"]
    )
    assert all(0 <= p - US_TOWN_MAP_SPRITEMAP_BASE < len(sprites) for p in ptrs)

    # The cast names: 48 strings inside the data.
    cast = files["ending/cast_names.bin"]
    for off in struct.unpack(f"<{CAST_NAME_COUNT}H", cast[: CAST_NAME_COUNT * 2]):
        assert 0 in cast[off:]

    # LUMINE_HALL_TEXT is what LOAD_CHARACTER_PORTRAIT_SCREEN (C45EB7) loads (LDA f:addr,X).
    lumine = config.rom["lumineHallText"]
    addr = (lumine.offset + 0xC00000).to_bytes(3, "little")
    assert b"\xbf" + addr in rom[0x045EB7 : 0x045EB7 + 0x200]
    assert files["data/text/lumine_hall_text.bin"] == rom[lumine.offset : lumine.offset + lumine.size]

    assert staff_text_length(files["ending/staff_text.bin"]) == len(files["ending/staff_text.bin"])

    us_window = BIN / "US" / "graphics" / "text_window.gfx.lzhal"
    if us_window.exists():
        packed = pack_graphics(out, lambda rel: (BIN / rel).read_bytes())
        # The map tilesets pack decompressed, under the names the map loader reads.
        tilesets = map_tilesets(rom, doc)
        raw = {p.removesuffix(".lzhal") + ".raw" for p in tilesets}
        assert raw <= set(packed) and not set(tilesets) & set(packed)
        assert set(files) - set(tilesets) < set(packed)
        assert len(decompress(packed["graphics/text_window.gfx.lzhal"])) == len(decompress(us_window.read_bytes()))
    assert len((out / TEXT_WINDOW_TILES_FILE).read_bytes()) == len(YOU_WIN_TILES) * 16


@needs_rom
@pytest.mark.parametrize(
    "victim", ["ending/cast_names.bin", "flyover_intro1.bin", "maps/gfx/2.gfx.lzhal", MANIFEST_FILE]
)
def test_graphics_are_current_needs_every_file(tmp_path, victim):
    """A damaged extraction makes pack-all skip the Japanese Locale (pack_ja)."""
    doc = load_dump_doc(ROOT / "mother2.yml")
    config = load_ja_locale(ROOT / "ja_locale.yml")
    out = tmp_path / "ja"
    extract_graphics(ROM.read_bytes(), doc, config.romSymbols, config.rom, out)
    assert graphics_are_current(out)
    (out / victim if victim == MANIFEST_FILE else out / BIN_SUBDIR / victim).unlink()
    assert not graphics_are_current(out)


def test_required_files_cover_the_c_references():
    """Every Japanese-only asset the C code names is a required file."""
    import re

    src = ROOT / "src"
    refs = set()
    for path in [*src.rglob("*.c"), *src.rglob("*.h")]:
        if "assets" in path.parts or "vendor" in path.parts:
            continue
        refs |= set(re.findall(r"ASSET_JA_([A-Z0-9_]+)", path.read_text(errors="replace")))
    ours = {re.sub(r"[^A-Z0-9]", "_", p.upper()) for p in required_bin_files()}
    graphics_refs = {r for r in refs if r.startswith(("FONTS_FLYOVER", "ENDING_", "GRAPHICS_MOTHER2"))}
    assert graphics_refs and graphics_refs <= ours

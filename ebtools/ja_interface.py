"""The Japanese interface (docs/ja-plan.md J2): name tables and UI strings.

Everything here comes from the Mother 2 ROM; what is committed is where
(``ja_locale.yml`` ``romSymbols``: symbol -> ROM offset and size, regenerated
from a Mother 2 linker map by ``ebtools ja-offsets``) and the layouts below.

- **Name tables.** Each US table with embedded names gets a Japanese variant
  with the US layout: the US table's bytes (gameplay values, pointers) with
  only the name fields replaced by the Mother 2 names, null-padded to the US
  field size. ``extract-ja`` writes the names to ``<assets>/ja/names/*.json``;
  ``pack-all`` patches the packed US table and writes it to ``JA/<US path>``,
  so ``ASSET_DATA(id)`` serves it in Japanese.
- **UI strings** (``UI_TEXTS``, the order of ``UiText`` in
  ``src/game/ui_text.h``): the strings the C code prints from literals in
  English, as Mother 2 prints them. ``<assets>/ja/ui_strings.json`` ->
  ``JA/text/ui_strings.bin``, ``UI_TEXT_SIZE`` bytes per id.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# --- Name tables ---------------------------------------------------------------


@dataclass(frozen=True)
class NameField:
    """``count`` strings of a table, on both sides.

    US: ``us_len`` bytes at ``us_off + i * us_stride``; Mother 2: ``m2_len``
    bytes at ``symbol + m2_off + i * m2_stride``.
    """

    key: str
    count: int
    us_off: int
    us_stride: int
    us_len: int
    symbol: str
    m2_off: int
    m2_stride: int
    m2_len: int


@dataclass(frozen=True)
class NameTable:
    """A US table with names.

    ``us_path`` is its pack output (or extracted binary) path; ``clear`` lists
    bytes zeroed in Japanese as ``(offset, stride, count)`` (enemy_data::the_flag,
    which only drives English articles).
    """

    name: str
    us_path: str
    fields: tuple[NameField, ...]
    clear: tuple[tuple[int, int, int], ...] = ()


def _one(key: str, us_len: int, symbol: str, m2_len: int, us_off: int = 0, count: int = 1) -> NameField:
    """A field of ``count`` strings stored back to back on both sides."""
    return NameField(key, count, us_off, us_len, us_len, symbol, 0, m2_len, m2_len)


# US layouts: include/structs.asm (USA) and earthbound.yml; Mother 2 layouts:
# the JPN branches of include/structs.asm and asm/data/**.
NAME_TABLES: tuple[NameTable, ...] = (
    # item: name[25] (US) / name[10] (Mother 2), 39 / 24 bytes
    NameTable(
        "items",
        "data/item_configuration_table.bin",
        (NameField("names", 254, 0, 39, 25, "ITEM_CONFIGURATION_TABLE", 0, 24, 10),),
    ),
    # enemy_data: the_flag, name[25], gender (US) / name[10] (Mother 2), 94 / 77 bytes
    NameTable(
        "enemies",
        "data/enemy_configuration_table.bin",
        (NameField("names", 231, 1, 94, 25, "ENEMY_CONFIGURATION_TABLE", 0, 77, 10),),
        clear=((0, 94, 231),),
    ),
    NameTable("psi_names", "data/psi_name_table.bin", (_one("names", 25, "PSI_NAME_TABLE", 10, count=17),)),
    NameTable("psi_suffixes", "data/psi_suffixes.bin", (_one("suffixes", 2, "PSI_SUFFIXES", 2, count=5),)),
    # psi_teleport_destination: name[25] / name[10], 31 / 16 bytes
    NameTable(
        "psi_teleport_destinations",
        "data/psi_teleport_dest_table.bin",
        (NameField("names", 17, 0, 31, 25, "PSI_TELEPORT_DEST_TABLE", 0, 16, 10),),
    ),
    # telephone_contact: label[25] / label[10], 31 / 16 bytes
    NameTable(
        "telephone_contacts",
        "data/telephone_contacts_table.bin",
        (NameField("labels", 7, 0, 31, 25, "TELEPHONE_CONTACTS_TABLE", 0, 16, 10),),
    ),
    NameTable("phone_call_text", "data/phone_call_text.bin", (_one("text", 5, "PHONE_CALL_TEXT", 4),)),
    # STATUS_EQUIP_WINDOW_TEXT_4/5/6
    NameTable(
        "status_equip_text",
        "data/status_equip_text.bin",
        (
            _one("psi_prompt", 35, "STATUS_EQUIP_WINDOW_TEXT_4", 27),
            _one("afflictions", 16, "STATUS_EQUIP_WINDOW_TEXT_5", 10, us_off=35, count=9),
            _one("homesick", 16, "STATUS_EQUIP_WINDOW_TEXT_6", 10, us_off=179),
        ),
    ),
    NameTable(
        "status_equip_window_text_7",
        "data/status_equip_window_text_7.bin",
        (_one("text", 12, "STATUS_EQUIP_WINDOW_TEXT_7", 6),),
    ),
    # STATUS_EQUIP_WINDOW_TEXT_8 to _13. Mother 2's _10 and _11 are one table
    # (the slot names). _13 ("None", 5 bytes) is そうびしない (6): the last field
    # of the table, it grows to 7 and the C reads it to the end of the asset.
    NameTable(
        "status_equip_window_text_8_13",
        "data/status_equip_window_text_8_13.bin",
        (
            _one("offense_label", 8, "STATUS_EQUIP_WINDOW_TEXT_8", 6),
            _one("defense_label", 8, "STATUS_EQUIP_WINDOW_TEXT_9", 7, us_off=8),
            _one("equipment_slot_labels", 11, "STATUS_EQUIP_WINDOW_TEXT_10", 4, us_off=16, count=4),
            _one("equipment_category_titles", 8, "STATUS_EQUIP_WINDOW_TEXT_11", 4, us_off=60, count=4),
            _one("nothing_text", 10, "STATUS_EQUIP_WINDOW_TEXT_12", 4, us_off=92),
            _one("none_text", 7, "STATUS_EQUIP_WINDOW_TEXT_13", 7, us_off=102),
        ),
    ),
    NameTable(
        "status_equip_window_text_14",
        "data/status_equip_window_text_14.bin",
        (_one("text", 3, "STATUS_EQUIP_WINDOW_TEXT_14", 3),),
    ),
    NameTable(
        "command_window_text", "US/data/command_window_text.bin", (_one("labels", 10, "CMD_WINDOW_TEXT", 5, count=6),)
    ),
    NameTable("psi_categories", "US/data/psi_categories.bin", (_one("names", 8, "PSI_CATEGORIES", 5, count=4),)),
    NameTable("psi_target_text", "US/data/psi_target_text.bin", (_one("texts", 20, "PSI_TARGET_TEXT", 9, count=10),)),
    NameTable("pp_cost_text", "US/data/pp_cost_text.bin", (_one("text", 8, "PP_COST_TEXT", 8),)),
    NameTable("misc_target_text", "US/data/misc_target_text.bin", (_one("texts", 10, "MISC_TARGET_TEXT", 4, count=5),)),
    NameTable(
        "battle_front_row_text", "US/data/battle_front_row_text.bin", (_one("text", 13, "BATTLE_FRONT_ROW_TEXT", 4),)
    ),
    NameTable(
        "battle_back_row_text", "US/data/battle_back_row_text.bin", (_one("text", 13, "BATTLE_BACK_ROW_TEXT", 4),)
    ),
    NameTable(
        "name_registry_request_string",
        "US/data/name_registry_request_string.bin",
        (_one("text", 26, "NAME_REGISTRY_REQUEST_STRING", 11),),
    ),
)

# The status window labels (STATUS_WINDOW_TEXT): a text block of
# FORCE_TEXT_ALIGNMENT + label pairs. Mother 2's alignment is a text cursor
# column (asm/text/ccs/force_text_alignment-jp.asm), the US one a pixel x;
# the Japanese font is 8 px a letter, so the Japanese block puts each label at
# column * 8. The US block's tail after its labels (the panels it opens) stays.
STATUS_WINDOW_TABLE = "status_window_text"
STATUS_WINDOW_US_PATH = "data/status_window_text.bin"
STATUS_WINDOW_SYMBOL = "STATUS_WINDOW_TEXT"
_CC_OPEN_WINDOW = (0x18, 0x01)
_CC_FORCE_ALIGNMENT = (0x18, 0x05)
_CC_END_BLOCK = 0x02

# --- UI strings ----------------------------------------------------------------

# Bytes per UI string in JA/text/ui_strings.bin (null-padded; UI_TEXT_SIZE in ui_text.h).
UI_TEXT_SIZE = 32

# (UiText name, symbol, offset in the symbol, max length or None = to the next
# symbol); a string ends at its first null. Order = enum UiText.
UI_TEXTS: tuple[tuple[str, str, int, int | None], ...] = (
    # asm/data/text/file_select_text.asm
    ("UI_FILE_START_NEW_GAME", "FILE_SELECT_TEXT_START_NEW_GAME", 0, None),
    ("UI_FILE_LEVEL", "FILE_SELECT_TEXT_LEVEL", 0, None),
    ("UI_FILE_TEXT_SPEED", "FILE_SELECT_TEXT_TEXTSPEED", 0, None),
    ("UI_FILE_SPEED_FAST", "FILE_SELECT_TEXT_TEXTSPEED_STRINGS", 0, 4),
    ("UI_FILE_SPEED_MEDIUM", "FILE_SELECT_TEXT_TEXTSPEED_STRINGS", 4, 4),
    ("UI_FILE_SPEED_SLOW", "FILE_SELECT_TEXT_TEXTSPEED_STRINGS", 8, 4),
    ("UI_FILE_CONTINUE", "FILE_SELECT_TEXT_CONTINUE", 0, None),
    ("UI_FILE_COPY", "FILE_SELECT_TEXT_COPY", 0, None),
    ("UI_FILE_DELETE", "FILE_SELECT_TEXT_DELETE", 0, None),
    ("UI_FILE_SET_UP", "FILE_SELECT_TEXT_SET_UP", 0, None),
    ("UI_FILE_COPY_TO_WHERE", "FILE_SELECT_TEXT_COPY_TO_WHERE", 0, None),
    ("UI_FILE_DELETE_CONFIRM", "FILE_SELECT_TEXT_ARE_YOU_SURE_DELETE", 0, None),
    ("UI_FILE_DELETE_NO", "FILE_SELECT_TEXT_ARE_YOU_SURE_DELETE_NO", 0, None),
    ("UI_FILE_DELETE_YES", "FILE_SELECT_TEXT_ARE_YOU_SURE_DELETE_YES", 0, None),
    ("UI_FILE_SELECT_TEXT_SPEED", "FILE_SELECT_TEXT_SELECT_TEXT_SPEED", 0, None),
    ("UI_FILE_SELECT_SOUND", "FILE_SELECT_TEXT_SELECT_SOUND_SETTING", 0, None),
    ("UI_FILE_SOUND_STEREO", "FILE_SELECT_TEXT_SOUND_SETTING_STRINGS", 0, 5),
    ("UI_FILE_SOUND_MONO", "FILE_SELECT_TEXT_SOUND_SETTING_STRINGS", 5, 5),
    ("UI_FILE_WHICH_STYLE", "FILE_SELECT_TEXT_WHICH_STYLE", 0, None),
    ("UI_FILE_FLAVOR_PLAIN", "FILE_SELECT_TEXT_FLAVOR_PLAIN", 0, None),
    ("UI_FILE_FLAVOR_MINT", "FILE_SELECT_TEXT_FLAVOR_MINT", 0, None),
    ("UI_FILE_FLAVOR_STRAWBERRY", "FILE_SELECT_TEXT_FLAVOR_STRAWBERRY", 0, None),
    ("UI_FILE_FLAVOR_BANANA", "FILE_SELECT_TEXT_FLAVOR_BANANA", 0, None),
    ("UI_FILE_FLAVOR_PEANUT", "FILE_SELECT_TEXT_FLAVOR_PEANUT", 0, None),
    ("UI_FILE_FAVORITE_FOOD", "FILE_SELECT_TEXT_FAVORITE_FOOD", 0, None),
    ("UI_FILE_COOLEST_THING", "FILE_SELECT_TEXT_COOLEST_THING", 0, None),
    ("UI_FILE_ARE_YOU_SURE", "FILE_SELECT_TEXT_ARE_YOU_SURE", 0, None),
    ("UI_FILE_YEP", "FILE_SELECT_TEXT_ARE_YOU_SURE_YEP", 0, None),
    ("UI_FILE_NOPE", "FILE_SELECT_TEXT_ARE_YOU_SURE_NOPE", 0, None),
    # asm/data/text/battle_menu_text-jp.asm: 5 bytes each (Do Nothing 7); the
    # map exports only some of the labels, so the others are offsets
    ("UI_BATTLE_BASH", "BATTLE_MENU_TEXT", 0, 5),
    ("UI_BATTLE_GOODS", "BATTLE_MENU_TEXT", 5, 5),
    ("UI_BATTLE_AUTO_FIGHT", "BATTLE_MENU_TEXT", 10, 5),
    ("UI_BATTLE_PSI", "BATTLE_MENU_TEXT_PSI", 0, 5),
    ("UI_BATTLE_DEFEND", "BATTLE_MENU_TEXT_PSI", 5, 5),
    ("UI_BATTLE_PRAY", "BATTLE_MENU_TEXT_PRAY", 0, 5),
    ("UI_BATTLE_SHOOT", "BATTLE_MENU_TEXT_SHOOT", 0, 5),
    ("UI_BATTLE_SPY", "BATTLE_MENU_TEXT_SPY", 0, 5),
    ("UI_BATTLE_RUN_AWAY", "BATTLE_MENU_TEXT_SPY", 5, 5),
    ("UI_BATTLE_MIRROR", "BATTLE_MENU_TEXT_MIRROR", 0, 5),
    ("UI_BATTLE_DO_NOTHING", "BATTLE_MENU_TEXT_DO_NOTHING", 0, 7),
    ("UI_BATTLE_TO", "BATTLE_TO_TEXT", 0, 8),
    # asm/data/item_use_menu_strings.asm (5 bytes each)
    ("UI_GOODS_USE", "ITEM_USE_MENU_STRINGS", 0, 5),
    ("UI_GOODS_GIVE", "ITEM_USE_MENU_STRINGS", 5, 5),
    ("UI_GOODS_DROP", "ITEM_USE_MENU_STRINGS", 10, 5),
    ("UI_GOODS_HELP", "ITEM_USE_MENU_STRINGS", 15, 5),
    # asm/data/text/menu_overflow_text.asm: the "more" item of a paged menu
    ("UI_MENU_OVERFLOW", "MENU_OVERFLOW_TEXT", 0, None),
)


def rom_symbols_used() -> list[str]:
    """Every Mother 2 symbol the interface reads (``ja_locale.yml`` ``romSymbols``)."""
    names = {f.symbol for t in NAME_TABLES for f in t.fields}
    names |= {sym for _, sym, _, _ in UI_TEXTS}
    names.add(STATUS_WINDOW_SYMBOL)
    return sorted(names)


# --- Mother 2 linker map -> romSymbols ----------------------------------------


def parse_map_exports(map_text: str) -> dict[str, int]:
    """``symbol -> address`` from a ld65 map's "Exports list by value"."""
    section = map_text.split("Exports list by value:")[1].split("Imports list:")[0]
    return {m.group(1): int(m.group(2), 16) for m in re.finditer(r"(\S+)\s+([0-9A-F]{6}) R\w\w", section)}


def rom_symbols_from_map(map_text: str, names: list[str]) -> dict[str, tuple[int, int]]:
    """``symbol -> (ROM file offset, bytes to the next exported address)`` for ``names``.

    The Mother 2 ROM is HiROM from 0xC00000 (unheadered).
    """
    exports = parse_map_exports(map_text)
    addrs = sorted(set(exports.values()))
    out: dict[str, tuple[int, int]] = {}
    for name in names:
        if name not in exports:
            raise KeyError(f"{name} is not in the map")
        addr = exports[name]
        nxt = next(a for a in addrs if a > addr)
        out[name] = (addr - 0xC00000, nxt - addr)
    return out


_ROM_SYMBOLS_HEADER = "romSymbols:"


def write_rom_symbols(config_path: Path, symbols: dict[str, tuple[int, int]]) -> None:
    """Replace the ``romSymbols:`` block (the end of ``ja_locale.yml``)."""
    text = config_path.read_text()
    head = text.split(_ROM_SYMBOLS_HEADER)[0].rstrip("\n")
    lines = [f"  {name}: [0x{off:06X}, {size}]" for name, (off, size) in sorted(symbols.items())]
    config_path.write_text(head + "\n" + _ROM_SYMBOLS_HEADER + "\n" + "\n".join(lines) + "\n")


def ja_offsets(
    map_path: Path = Path("build/mother2.map"),
    config: Path = Path("ja_locale.yml"),
) -> None:
    """Regenerate ``ja_locale.yml`` ``romSymbols`` from a Mother 2 linker map (``make mother2``)."""
    symbols = rom_symbols_from_map(map_path.read_text(), rom_symbols_used())
    write_rom_symbols(config, symbols)
    print(f"Wrote {len(symbols)} Mother 2 symbols to {config}")


# --- Extraction ----------------------------------------------------------------


def _decode(data: bytes, table: dict[int, str], where: str) -> str:
    """Mother 2 text bytes (up to the first null) as text."""
    out = []
    for b in data.split(b"\0")[0]:
        if b not in table:
            raise ValueError(f"{where}: byte 0x{b:02X} is not in the Japanese text table")
        out.append(table[b])
    return "".join(out)


def _symbol_bytes(rom: bytes, symbols: dict[str, tuple[int, int]], name: str, off: int, length: int | None) -> bytes:
    base, size = symbols[name]
    if length is None:
        length = size - off
    if off + length > size:
        raise ValueError(f"{name}+{off}: {length} bytes run past the symbol's {size}")
    return rom[base + off : base + off + length]


def extract_name_tables(rom: bytes, symbols: dict[str, tuple[int, int]], table: dict[int, str]) -> dict[str, dict]:
    """Return ``{table name: {field key: names}}`` for NAME_TABLES and the status window.

    A field of one string holds the string, others a list.
    """
    out: dict[str, dict] = {}
    for t in NAME_TABLES:
        fields: dict[str, str | list[str]] = {}
        for f in t.fields:
            names = [
                _decode(
                    _symbol_bytes(rom, symbols, f.symbol, f.m2_off + i * f.m2_stride, f.m2_len),
                    table,
                    f"{f.symbol}[{i}]",
                )
                for i in range(f.count)
            ]
            fields[f.key] = names[0] if f.count == 1 else names
        out[t.name] = fields
    out[STATUS_WINDOW_TABLE] = {"labels": _status_window_labels(rom, symbols, table)}
    return out


def _status_window_labels(rom: bytes, symbols: dict[str, tuple[int, int]], table: dict[int, str]) -> list[dict]:
    """Mother 2's status window labels: ``[{"col", "row", "text"}]`` up to the END_BLOCK."""
    data = _symbol_bytes(rom, symbols, STATUS_WINDOW_SYMBOL, 0, None)
    labels: list[dict] = []
    i = 0
    while data[i] != _CC_END_BLOCK:
        if tuple(data[i : i + 2]) == _CC_OPEN_WINDOW:
            i += 3
        elif tuple(data[i : i + 2]) == _CC_FORCE_ALIGNMENT:
            labels.append({"col": data[i + 2], "row": data[i + 3], "text": ""})
            i += 4
        elif data[i] >= 0x20 and labels:
            labels[-1]["text"] += _decode(data[i : i + 1], table, STATUS_WINDOW_SYMBOL)
            i += 1
        else:
            raise ValueError(f"{STATUS_WINDOW_SYMBOL}+{i}: unexpected byte 0x{data[i]:02X}")
    return labels


def extract_ui_texts(rom: bytes, symbols: dict[str, tuple[int, int]], table: dict[int, str]) -> dict[str, str]:
    """``{UiText name: Mother 2 string}``."""
    return {
        name: _decode(_symbol_bytes(rom, symbols, sym, off, length), table, name) for name, sym, off, length in UI_TEXTS
    }


def write_interface_json(out_dir: Path, names: dict[str, dict], ui: dict[str, str]) -> None:
    """Write ``names/*.json`` and ``ui_strings.json`` under ``<assets>/ja``."""
    names_dir = out_dir / "names"
    names_dir.mkdir(parents=True, exist_ok=True)
    for name, fields in names.items():
        (names_dir / f"{name}.json").write_text(json.dumps(fields, ensure_ascii=False, indent=1) + "\n")
    (out_dir / "ui_strings.json").write_text(json.dumps(ui, ensure_ascii=False, indent=1) + "\n")


# --- Packing -------------------------------------------------------------------


def _encode(text: str, reverse: dict[str, int], size: int, where: str) -> bytes:
    """Japanese text as bytes, null-padded to ``size``."""
    try:
        data = bytes(reverse[ch] for ch in text)
    except KeyError as exc:
        raise ValueError(f"{where}: {exc.args[0]!r} is not in the Japanese text table") from None
    if len(data) > size:
        raise ValueError(f"{where}: {text!r} is {len(data)} bytes, the field {size}")
    return data + bytes(size - len(data))


def pack_name_table(t: NameTable, us: bytes, fields: dict[str, str | list[str]], reverse: dict[str, int]) -> bytes:
    """Return the US table ``us`` with the Japanese names.

    Its ``clear`` bytes are zeroed; it grows if a field ends past it.
    """
    end = max([len(us)] + [f.us_off + (f.count - 1) * f.us_stride + f.us_len for f in t.fields])
    out = bytearray(us) + bytes(end - len(us))
    for f in t.fields:
        names = [fields[f.key]] if isinstance(fields[f.key], str) else fields[f.key]
        if len(names) != f.count:
            raise ValueError(f"ja/names/{t.name}.json {f.key}: {len(names)} entries, expected {f.count}")
        for i, name in enumerate(names):
            at = f.us_off + i * f.us_stride
            out[at : at + f.us_len] = _encode(name, reverse, f.us_len, f"{t.name}.{f.key}[{i}]")
    for off, stride, count in t.clear:
        for i in range(count):
            out[off + i * stride] = 0
    return bytes(out)


def pack_status_window(us: bytes, labels: list[dict], reverse: dict[str, int]) -> bytes:
    """Return the Japanese status window block.

    The labels (US FORCE_TEXT_ALIGNMENT, x = column * 8), then the US block
    from its first END_BLOCK on.
    """
    i = 0
    while us[i] != _CC_END_BLOCK:
        i += 4 if tuple(us[i : i + 2]) == _CC_FORCE_ALIGNMENT else 1
    out = bytearray()
    for n, label in enumerate(labels):
        text = label["text"]
        out += bytes([*_CC_FORCE_ALIGNMENT, label["col"] * 8, label["row"]])
        out += _encode(text, reverse, len(text), f"{STATUS_WINDOW_TABLE}[{n}]")
    return bytes(out) + us[i:]


def pack_ui_texts(ui: dict[str, str], reverse: dict[str, int]) -> bytes:
    """``JA/text/ui_strings.bin``: UI_TEXT_SIZE bytes per UiText, in enum order."""
    return b"".join(_encode(ui[name], reverse, UI_TEXT_SIZE - 1, name) + b"\0" for name, _, _, _ in UI_TEXTS)


def pack_interface(ja_dir: Path, us_table: Callable[[str], bytes], reverse: dict[str, int]) -> dict[str, bytes]:
    """Every interface table: ``{packed path under JA/: bytes}``.

    ``us_table(path)`` returns the US table at ``path`` (packed or extracted).
    """
    out: dict[str, bytes] = {}
    names_dir = ja_dir / "names"
    for t in NAME_TABLES:
        fields = json.loads((names_dir / f"{t.name}.json").read_text())
        path = t.us_path.removeprefix("US/")
        out[path] = pack_name_table(t, us_table(t.us_path), fields, reverse)
    labels = json.loads((names_dir / f"{STATUS_WINDOW_TABLE}.json").read_text())["labels"]
    out[STATUS_WINDOW_US_PATH] = pack_status_window(us_table(STATUS_WINDOW_US_PATH), labels, reverse)
    ui = json.loads((ja_dir / "ui_strings.json").read_text())
    out["text/ui_strings.bin"] = pack_ui_texts(ui, reverse)
    return out

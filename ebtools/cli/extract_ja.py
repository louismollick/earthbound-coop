"""The ``extract-ja`` command: Japanese assets from a Mother 2 ROM.

Writes ``<assets>/ja/`` only (docs/adr/0003-japanese-locale.md):

- ``dialogue/<US file>.yml``: the US label set, files and order; each message
  is the US logic ops with Mother 2's presentation ops (``text_dsl.splice``).
- ``inline_strings.json``: US inline markup -> Japanese inline markup.
- ``fonts/main.json`` + ``main.png``: the 224 Mother 2 text glyphs (codes
  0x20-0xFF) in the US main-font format.
- ``text_table.json``: the Japanese text table, for pack-all.
- ``names/*.json``, ``ui_strings.json``: the interface (``ebtools.ja_interface``).
"""

import difflib
import hashlib
import json
import struct
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter

from ebtools.config import DEFAULT_ASSETS_DIR, CommonData, DumpDoc, load_common_data, load_dump_doc
from ebtools.ja_interface import extract_name_tables, extract_ui_texts, write_interface_json
from ebtools.ja_locale import (
    JA_ASSETS_SUBDIR,
    JA_FIRST_GLYPH,
    JA_GLYPH_COUNT,
    JA_TEXT_TABLE_FILE,
    ja_text_table,
    load_ja_locale,
    write_text_table,
)
from ebtools.text_dsl.splice import (
    falls_through,
    is_presentation,
    label_args,
    map_label_args,
    match_logic,
    splice,
    splice_chain,
    strip_presentation,
)

# (json path, list key, inline field, US table bin, record size, pointer offset):
# every inline string the US pack-all builds (pack_all json_packers order).
_INLINE_SOURCES = [
    ("items/items.json", "items", "help_text", "data/item_configuration_table.bin", 39, 35),
    ("enemies/enemies.json", "enemies", "text_1", "data/enemy_configuration_table.bin", 94, 45),
    ("enemies/enemies.json", "enemies", "text_2", "data/enemy_configuration_table.bin", 94, 49),
    ("battle/battle_actions.json", "actions", "description", "data/battle_action_table.bin", 12, 4),
    ("battle/psi_abilities.json", "abilities", "description", "data/psi_ability_table.bin", 15, 11),
]

Messages = dict[str, list[dict]]


def extract_ja(
    mother2_rom: Annotated[Path, Parameter(help="Unheadered Mother 2 ROM")] = Path("mother2.sfc"),
    assets_dir: Annotated[Path, Parameter(help="Assets dir; output goes to <assets_dir>/ja/")] = DEFAULT_ASSETS_DIR,
    *,
    bin_dir: Annotated[Path, Parameter(help="US extracted binaries (inline string sources)")] = Path("asm/bin"),
    mother2_yaml: Annotated[Path, Parameter(help="Mother 2 dump doc")] = Path("mother2.yml"),
    us_yaml: Annotated[Path, Parameter(help="US dump doc")] = Path("earthbound.yml"),
    commondata: Annotated[Path, Parameter(help="Common data definitions")] = Path("commondefs.yml"),
    ja_config: Annotated[Path, Parameter(help="Japanese Locale config")] = Path("ja_locale.yml"),
) -> None:
    """Extract the Japanese dialogue, inline strings and font from a Mother 2 ROM."""
    config = load_ja_locale(ja_config)
    if not mother2_rom.exists():
        raise SystemExit(f"error: {mother2_rom} not found")
    rom = mother2_rom.read_bytes()
    sha1 = hashlib.sha1(rom, usedforsecurity=False).hexdigest()
    if sha1 != config.romSha1:
        raise SystemExit(
            f"error: {mother2_rom} has SHA-1 {sha1}, expected {config.romSha1} (unheadered Mother 2, Japan)"
        )

    m2_doc = load_dump_doc(mother2_yaml)
    us_doc = load_dump_doc(us_yaml)
    common = load_common_data(commondata)
    table = ja_text_table(m2_doc, config)

    us_dialogue_dir = assets_dir / "dialogue"
    us_files = _load_us_dialogue(us_dialogue_dir)
    if not us_files:
        raise SystemExit(f"error: no US dialogue in {us_dialogue_dir} (run `ebtools extract` first)")
    us_msgs: Messages = {label: ops for _, msgs in us_files for label, ops in msgs.items()}

    jp_msgs, jp_next = decode_mother2_dialogue(rom, m2_doc, table, common)
    us2jp, stats = align_labels(us_msgs, jp_msgs, config.labels)
    jp2us: dict[str, str] = {}
    for u, j in us2jp.items():
        jp2us.setdefault(j, u)

    out_dir = assets_dir / JA_ASSETS_SUBDIR
    dialogue_out = out_dir / "dialogue"
    dialogue_out.mkdir(parents=True, exist_ok=True)

    unresolved_presentation_labels: list[str] = []

    def jp_label_to_us(label: object) -> object:
        if isinstance(label, str):
            if label in jp2us:
                return jp2us[label]
            if label in us_msgs:
                return label
            unresolved_presentation_labels.append(label)
        return label

    from ebtools.text_dsl.yaml_io import serialize_dialogue_file

    ja_msgs = splice_dialogue(list(us_msgs.items()), jp_msgs, jp_next, us2jp, jp2us, jp_label_to_us)
    for label in config.motherLogic:
        ja_msgs[label] = mother_logic_message(label, us_msgs, jp_msgs, us2jp, jp_label_to_us)
    written = set()
    for path, msgs in us_files:
        (dialogue_out / path.name).write_text(
            serialize_dialogue_file({label: ja_msgs[label] for label in msgs}), encoding="utf-8"
        )
        written.add(path.name)
    for stale in dialogue_out.glob("*.y*ml"):
        if stale.name not in written:
            stale.unlink()

    inline, inline_stats = build_inline_strings(assets_dir, bin_dir, us_doc, us2jp, jp_msgs)
    (out_dir / "inline_strings.json").write_text(
        json.dumps(inline, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    if not config.romSymbols:
        raise SystemExit(f"error: {ja_config} has no romSymbols (run `ebtools ja-offsets`)")
    jp_addr_label = _addr_to_label(m2_doc)

    def us_label_of(jp_addr: int) -> str | None:
        label = jp_addr_label.get(jp_addr)
        if label is None:
            return None
        return jp2us.get(label, label if label in us_msgs else None)

    names = extract_name_tables(rom, config.romSymbols, table, us_label_of)
    ui = extract_ui_texts(rom, config.romSymbols, table)
    write_interface_json(out_dir, names, ui)

    write_text_table(out_dir / JA_TEXT_TABLE_FILE, table)
    font_stats = export_ja_font(rom, m2_doc, out_dir / "fonts")

    _report(us_msgs, jp_msgs, us2jp, ja_msgs, stats, inline_stats, font_stats, unresolved_presentation_labels)
    print(f"Interface: {len(names)} name tables, {len(ui)} UI strings")
    print(f"Wrote {len(written)} dialogue files, {len(inline)} inline strings and the font to {out_dir}")


def mother_logic_message(
    label: str,
    us_msgs: Messages,
    jp_msgs: Messages,
    us2jp: dict[str, str],
    jp_label_to_us: Callable[[object], object],
) -> list[dict]:
    """Mother 2's whole message for US ``label`` (``ja_locale.yml`` ``motherLogic``).

    Its label arguments name US labels; it must end (or fall through) as the
    US message does, since it keeps the US message's place.
    """
    if label not in us2jp:
        raise SystemExit(f"error: ja_locale.yml motherLogic: {label} has no Mother 2 message")
    ops = [map_label_args(op, jp_label_to_us) for op in jp_msgs[us2jp[label]]]
    if falls_through(ops) != falls_through(us_msgs[label]):
        raise SystemExit(f"error: ja_locale.yml motherLogic: {label} ends unlike its US message")
    return ops


def _load_us_dialogue(dialogue_dir: Path) -> list[tuple[Path, Messages]]:
    """Load the US dialogue YAML in pack-all's order (``_pack_dialogue``)."""
    from ebtools.text_dsl.yaml_io import deserialize_dialogue_file

    files = sorted(dialogue_dir.glob("*.yaml")) + sorted(dialogue_dir.glob("*.yml"))
    return [(p, deserialize_dialogue_file(p.read_text(encoding="utf-8"))) for p in files]


# --- Mother 2 dialogue ---------------------------------------------------------


def decode_mother2_dialogue(
    rom: bytes, doc: DumpDoc, table: dict[int, str], common: CommonData
) -> tuple[Messages, dict[str, str]]:
    """Decode every Mother 2 text block into ``{label: ops}``.

    Labels come from ``mother2.yml`` renameLabels.  An address that a message
    jumps to but no label names gets ``_JP_<block>_<offset>``, and splits the
    message it falls in (as a named label would), until no such address is left.
    Label arguments become label names; IDs become commondefs names.

    Returns ``(messages, next_label)``, ``next_label`` mapping a label to the
    one that follows it in the same block.
    """
    from ebtools.cli.migrate_text import _resolve_label_addresses, _resolve_symbolic_names
    from ebtools.text_dsl.decoder import decode_text_block

    blocks = [
        (e.name, 0xC00000 + e.offset, rom[e.offset : e.offset + e.size])
        for e in doc.dumpEntries
        if e.extension == "ebtxt"
    ]
    labels: dict[int, str] = {}
    for name, base, _ in blocks:
        for off, label in doc.renameLabels.get(name, {}).items():
            labels[base + off] = label

    while True:
        msgs: Messages = {}
        next_label: dict[str, str] = {}
        for _name, base, data in blocks:
            starts = sorted(a for a in labels if base <= a < base + len(data))
            for i, start in enumerate(starts):
                end = starts[i + 1] if i + 1 < len(starts) else base + len(data)
                ops = decode_text_block(data[start - base : end - base], table)
                _resolve_label_addresses(ops, labels)
                msgs[labels[start]] = ops
                if i + 1 < len(starts):
                    next_label[labels[start]] = labels[end]
        new = 0
        for ops in msgs.values():
            for op in ops:
                for target in label_args(op):
                    if isinstance(target, int) and target not in labels:
                        for name, base, data in blocks:
                            if base <= target < base + len(data):
                                labels[target] = f"_JP_{name}_{target - base:04X}"
                                new += 1
        if not new:
            break

    for ops in msgs.values():
        _resolve_symbolic_names(ops, common)
    return msgs, next_label


def splice_dialogue(
    us_labels: list[tuple[str, list[dict]]],
    jp_msgs: Messages,
    jp_next: dict[str, str],
    us2jp: dict[str, str],
    jp2us: dict[str, str],
    jp_label_to_us: Callable[[object], object],
) -> Messages:
    """Splice every US message, one fallthrough chain at a time (``splice_chain``).

    A chain is a run of consecutive US labels (pack-all order) where each but
    the last falls through.  Its Mother 2 side is the counterpart of every
    aligned chain label, each followed by the Mother 2-only labels it falls into.
    """
    aligned_jp = set(jp2us)
    out: Messages = {}
    chain: list[tuple[str, list[dict]]] = []
    for i, (label, ops) in enumerate(us_labels):
        chain.append((label, ops))
        if falls_through(ops) and i + 1 < len(us_labels):
            continue
        us_calls = {op["dest"] for _, ops in chain for op in ops if op["op"] == "call_text"}
        parts: list[tuple[str | None, list[dict]]] = []
        for u, _ in chain:
            j = us2jp.get(u)
            if j is None:
                continue
            parts.append((u, _inline_text_calls(jp_msgs[j], jp_msgs, jp2us, us_calls)))
            while falls_through(jp_msgs[j]) and jp_next.get(j) and jp_next[j] not in aligned_jp:
                j = jp_next[j]
                parts.append((None, _inline_text_calls(jp_msgs[j], jp_msgs, jp2us, us_calls)))
        out.update(splice_chain(chain, parts, jp_label_to_us))
        chain = []
    return out


def _inline_text_calls(
    ops: list[dict], jp_msgs: Messages, jp2us: dict[str, str], us_calls: set, depth: int = 0
) -> list[dict]:
    """Replace a Mother 2 ``call_text`` the US message lacks by the text it calls.

    Only for a callee with no logic but its end_block once its own calls are
    replaced (Mother 2 shares text, like an item description's stat line,
    that the US inlined).
    """
    out: list[dict] = []
    for op in ops:
        dest = op.get("dest") if op["op"] == "call_text" else None
        callee = jp_msgs.get(dest) if isinstance(dest, str) and depth < 4 else None
        if callee is not None and jp2us.get(dest, dest) not in us_calls:
            body = _first_message(_inline_text_calls(callee, jp_msgs, jp2us, us_calls, depth + 1))
            if all(is_presentation(c) for c in body):
                out.extend(body)
                continue
        out.append(op)
    return out


# --- Label alignment -----------------------------------------------------------


def align_labels(us_msgs: Messages, jp_msgs: Messages, renames: dict[str, str]) -> tuple[dict[str, str], dict]:
    """Pair US labels with Mother 2 labels.

    Seeds: the same name, then ``ja_locale.yml`` ``labels``.  Propagation: for
    every aligned pair, the label arguments of matched logic ops (same op) pair
    up, US destination with Mother 2 destination, if the two destinations'
    logic op names are at least half similar; repeat until nothing changes.
    A Mother 2 label may end up paired with several US labels.

    Returns ``(us2jp, stats)``.
    """
    us2jp = {u: u for u in us_msgs if u in jp_msgs}
    by_name = len(us2jp)
    for u, j in renames.items():
        if u not in us_msgs or j not in jp_msgs:
            print(f"Warning: ja_locale.yml labels: {u} -> {j} names a missing label", file=sys.stderr)
            continue
        us2jp[u] = j
    queue = list(us2jp.items())
    propagated = conflicts = rejected = 0
    while queue:
        u, j = queue.pop()
        ul, jl = strip_presentation(us_msgs[u]), strip_presentation(jp_msgs[j])
        for a, b in match_logic(ul, jl):
            if ul[a]["op"] != jl[b]["op"]:
                continue
            for x, y in zip(label_args(ul[a]), label_args(jl[b])):
                if not (isinstance(x, str) and isinstance(y, str) and x in us_msgs and y in jp_msgs):
                    continue
                if x not in us2jp:
                    if _logic_similarity(us_msgs[x], jp_msgs[y]) < 0.5:
                        rejected += 1
                        continue
                    us2jp[x] = y
                    queue.append((x, y))
                    propagated += 1
                elif us2jp[x] != y:
                    conflicts += 1
    return us2jp, {
        "by_name": by_name,
        "config": len(renames),
        "propagated": propagated,
        "rejected": rejected,
        "conflicts": conflicts,
    }


def _logic_similarity(a: list[dict], b: list[dict]) -> float:
    """Return the difflib ratio of two messages' logic op names."""
    names_a = [op["op"] for op in strip_presentation(a)]
    names_b = [op["op"] for op in strip_presentation(b)]
    return difflib.SequenceMatcher(None, names_a, names_b, autojunk=False).ratio()


# --- Inline strings ------------------------------------------------------------


def _addr_to_label(doc: DumpDoc) -> dict[int, str]:
    out: dict[int, str] = {}
    for e in doc.dumpEntries:
        if e.extension == "ebtxt":
            for off, label in doc.renameLabels.get(e.name, {}).items():
                out[0xC00000 + e.offset + off] = label
    return out


def _ops_to_inline(ops: list[dict]) -> str:
    """Inline markup for ops (text literal, other ops as ``{op arg ...}``)."""
    from ebtools.cli.migrate_text import _ops_to_inline as to_inline

    return to_inline(ops)


def _first_message(ops: list[dict]) -> list[dict]:
    """The ops up to (not including) the first end_block."""
    for i, op in enumerate(ops):
        if op["op"] == "end_block":
            return ops[:i]
    return ops


def build_inline_strings(
    assets_dir: Path, bin_dir: Path, us_doc: DumpDoc, us2jp: dict[str, str], jp_msgs: Messages
) -> tuple[dict[str, str], dict]:
    """Map every US inline markup string to its Japanese markup.

    The US string's label is recovered from the US table's original text
    pointer (``bin_dir`` holds the tables as extracted from the US ROM); the
    Mother 2 message of the aligned label gives the presentation.  An inline
    string whose label has no Mother 2 counterpart maps to its logic alone.
    """
    from ebtools.text_dsl.inline import parse_inline_to_ops

    addr_to_label = _addr_to_label(us_doc)
    out: dict[str, str] = {}
    stats = {"strings": 0, "japanese": 0, "silent": [], "differing_duplicates": 0}
    for json_rel, list_key, field, table_rel, size, ptr_off in _INLINE_SOURCES:
        json_path, table_path = assets_dir / json_rel, bin_dir / table_rel
        if not json_path.exists():
            continue
        if not table_path.exists():
            raise SystemExit(f"error: {table_path} not found (run `ebtools extract` first)")
        table = table_path.read_bytes()
        for idx, entry in enumerate(json.loads(json_path.read_text(encoding="utf-8"))[list_key]):
            us_text = entry.get(field)
            if us_text is None:
                continue
            (addr,) = struct.unpack_from("<I", table, idx * size + ptr_off)
            jp_label = us2jp.get(addr_to_label.get(addr, ""))
            us_ops = parse_inline_to_ops(us_text)
            if jp_label:
                jp_ops = _inline_text_calls(_first_message(jp_msgs[jp_label]), jp_msgs, {}, set())
                ja_text = _ops_to_inline(splice(us_ops, jp_ops, lambda x: x))
            else:
                ja_text = _ops_to_inline(strip_presentation(us_ops))
            if us_text in out:
                stats["differing_duplicates"] += out[us_text] != ja_text
                continue
            out[us_text] = ja_text
            stats["strings"] += 1
            if jp_label:
                stats["japanese"] += 1
            else:
                stats["silent"].append(f"{json_rel}[{idx}].{field} {addr_to_label.get(addr, hex(addr))}")
    return out, stats


# --- Font ----------------------------------------------------------------------


def export_ja_font(rom: bytes, doc: DumpDoc, fonts_dir: Path) -> dict:
    """Convert the Mother 2 text glyphs to the US main-font format and export it.

    Code ``c`` is two stacked 8x8 2bpp tiles of ``JP/graphics/text_window.gfx``:
    top ``(c & 0xF0) * 2 + (c & 0x0F)``, bottom top + 16
    (asm/text/window/write_tile_to_window-jp.asm).  Colour 3 is background, any
    other colour is ink.  The US format is 1bpp inverted (0 = ink), 16 rows per
    8 px column, two columns per glyph; the right column is left blank.  Every
    width is 7 (the renderer adds ``character_padding`` = 1: an 8 px advance).
    """
    from ebtools.hallz.decompress import decompress
    from ebtools.parsers.font import export_font_png

    (entry,) = [e for e in doc.dumpEntries if e.subdir == "JP/graphics" and e.name == "text_window"]
    gfx = decompress(rom[entry.offset : entry.offset + entry.size])

    out = bytearray()
    eighth_column: list[int] = []
    for code in range(JA_FIRST_GLYPH, JA_FIRST_GLYPH + JA_GLYPH_COUNT):
        top = (code & 0xF0) * 2 + (code & 0x0F)
        rows = []
        for tile in (top, top + 16):
            for y in range(8):
                lo, hi = gfx[tile * 16 + y * 2], gfx[tile * 16 + y * 2 + 1]
                rows.append(lo & hi)  # background (colour 3) has both planes set
        if any(r & 1 == 0 for r in rows):
            eighth_column.append(code)
        out.extend(rows)
        out.extend(b"\xff" * 16)

    widths = bytes([7] * JA_GLYPH_COUNT)
    export_font_png(bytes(out), widths, "main", 32, fonts_dir, glyph_count=JA_GLYPH_COUNT)
    return {"eighth_column": eighth_column}


# --- Report --------------------------------------------------------------------


def _text_len(ops: list[dict]) -> int:
    """Visible characters (US cutscenes pad with spaces, Mother 2 does not)."""
    return sum(len(op["value"].strip()) for op in ops if op["op"] == "text")


def _report(
    us_msgs: Messages,
    jp_msgs: Messages,
    us2jp: dict[str, str],
    ja_msgs: Messages,
    stats: dict,
    inline_stats: dict,
    font_stats: dict,
    unresolved: list[str],
) -> None:
    jp_only = len(set(jp_msgs) - set(us2jp.values()))
    identical = sum(
        1
        for u, j in us2jp.items()
        if [op["op"] for op in strip_presentation(us_msgs[u])] == [op["op"] for op in strip_presentation(jp_msgs[j])]
    )
    print("Label alignment:")
    print(f"  US labels {len(us_msgs)}, Mother 2 labels {len(jp_msgs)}")
    print(f"  same name {stats['by_name']}, config {stats['config']}, propagated {stats['propagated']}")
    print(f"  propagations rejected as dissimilar {stats['rejected']}")
    print(f"  conflicts {stats['conflicts']}, US-only {len(us_msgs) - len(us2jp)}, Mother 2-only {jp_only}")
    print(f"  aligned pairs with the same logic op names: {identical}/{len(us2jp)}")

    with_text = sum(1 for u in us2jp if any(is_presentation(op) for op in ja_msgs[u]))
    print(
        f"Messages: {len(us2jp)} take Mother 2 presentation ({with_text} non-empty), "
        f"{len(us_msgs) - len(us2jp)} logic only"
    )
    silent = sorted(
        ((u, _text_len(us_msgs[u])) for u in us_msgs if _text_len(us_msgs[u]) and not _text_len(ja_msgs[u])),
        key=lambda t: -t[1],
    )
    print(f"  labels with English text and no Japanese text: {len(silent)}")
    for u, n in silent[:20]:
        print(f"    {n:5d} chars  {u}{'' if u in us2jp else ' (US-only)'}")
    if unresolved:
        print(f"  Mother 2 menu labels with no US counterpart: {sorted(set(unresolved))}")
    unknown = sum(1 for ops in ja_msgs.values() for op in ops if op["op"] == "unknown")
    print(f"  unknown ops in the output: {unknown}")

    print(
        f"Inline strings: {inline_stats['strings']}, {inline_stats['japanese']} Japanese, "
        f"{len(inline_stats['silent'])} silent, {inline_stats['differing_duplicates']} shared US strings "
        "whose Mother 2 texts differ (first kept)"
    )
    for s in inline_stats["silent"][:20]:
        print(f"    silent: {s}")
    cols = font_stats["eighth_column"]
    print(f"Font: {JA_GLYPH_COUNT} glyphs, {len(cols)} use the 8th pixel column (the advance must stay 8 px)")
    sys.stdout.flush()

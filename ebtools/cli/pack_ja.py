"""Pack the Japanese Locale (``<assets>/ja/``, from ``ebtools extract-ja``).

Called by ``pack-all`` after the US packers.  Writes ``<output>/JA/``:

- ``text/dialogue.bin``: the Japanese dialogue, labels at 0x200000+.
- ``text/inline_strings.bin``: the Japanese inline strings, at 0x300000+.
- ``text/xlat.bin``: ``(u32 us_addr, u32 ja_addr)`` pairs sorted by
  ``us_addr``: every US dialogue label address and US inline string offset to
  its Japanese address.
- ``fonts/main.gfx`` / ``fonts/main.bin``: the 224 Mother 2 glyphs.
- The interface (``ebtools.ja_interface``): every US name table with the
  Mother 2 names, at the US table's path, and ``text/ui_strings.bin``.

Without ``<assets>/ja/`` it removes a stale ``<output>/JA/`` and writes nothing.
"""

import json
import shutil
import struct
import sys
from pathlib import Path

from ebtools.config import CommonData
from ebtools.ja_locale import (
    JA_ASSETS_SUBDIR,
    JA_DIALOGUE_BASE,
    JA_INLINE_BASE,
    JA_PACKED_SUBDIR,
    JA_TEXT_TABLE_FILE,
    read_text_table,
)
from ebtools.text_dsl.string_table import StringTableBuilder


def pack_ja(
    assets_dir: Path,
    output_dir: Path,
    common_data: CommonData,
    us_label_addrs: dict[str, int],
    us_inline: StringTableBuilder,
    bin_dir: Path,
) -> int:
    """Pack ``<assets_dir>/ja/`` to ``<output_dir>/JA/``; return the asset groups packed.

    Parameters
    ----------
    us_label_addrs
        US dialogue label -> address, as ``_pack_dialogue`` assigned them.
    us_inline
        The US inline string table, fully built (its offsets are final).
    bin_dir
        The US extracted binaries (the US tables pack-all doesn't pack).
    """
    from ebtools.cli.pack_all import _compile_dialogue
    from ebtools.parsers.font import pack_font
    from ebtools.text_dsl.compiler import build_reverse_names
    from ebtools.text_dsl.yaml_io import deserialize_dialogue_file

    ja_dir = assets_dir / JA_ASSETS_SUBDIR
    out = output_dir / JA_PACKED_SUBDIR
    if out.exists():
        shutil.rmtree(out)
    if not ja_dir.is_dir():
        return 0
    if not us_label_addrs:
        # No US dialogue packed (nothing for xlat or the tables' text pointers)
        print("Warning: skipping the Japanese Locale, no US dialogue was packed", file=sys.stderr)
        return 0

    reverse_table = {char: code for code, char in read_text_table(ja_dir / JA_TEXT_TABLE_FILE).items()}

    # Dialogue: the same files (and so the same label order) as the US.
    yaml_files = sorted((ja_dir / "dialogue").glob("*.yaml")) + sorted((ja_dir / "dialogue").glob("*.yml"))
    all_dialogue = [(f, deserialize_dialogue_file(f.read_text())) for f in yaml_files]
    blob, ja_label_addrs = _compile_dialogue(
        all_dialogue, JA_DIALOGUE_BASE, reverse_table, build_reverse_names(common_data)
    )
    missing = [label for label in us_label_addrs if label not in ja_label_addrs]
    if missing:
        # Stale Japanese assets must not break the English build.
        print(
            f"Warning: skipping the Japanese Locale, its dialogue lacks {len(missing)} US labels "
            f"(rerun `ebtools extract-ja`): {missing[:5]}",
            file=sys.stderr,
        )
        return 0
    _write(out / "text" / "dialogue.bin", blob)

    xlat: dict[int, int] = {}
    # US labels sharing an address (empty messages) take the first label's
    # Japanese address: in file order it falls through into the others.
    for label, us_addr in us_label_addrs.items():
        xlat.setdefault(us_addr, ja_label_addrs[label])

    # Inline strings, in the US table's order.
    ja_inline_map: dict[str, str] = json.loads((ja_dir / "inline_strings.json").read_text())
    ja_inline = StringTableBuilder(reverse_table)
    stale = 0
    for us_text, us_offset in us_inline.entries().items():
        ja_text = ja_inline_map.get(us_text)
        if ja_text is None:
            stale += 1
            ja_text = ""
        xlat[us_offset] = JA_INLINE_BASE + ja_inline.add(ja_text)
    inline_blob = ja_inline.build()
    _write(out / "text" / "inline_strings.bin", inline_blob)

    _write(out / "text" / "xlat.bin", b"".join(struct.pack("<II", k, v) for k, v in sorted(xlat.items())))

    gfx, widths = pack_font(ja_dir / "fonts" / "main.png", ja_dir / "fonts" / "main.json")
    _write(out / "fonts" / "main.gfx", gfx)
    _write(out / "fonts" / "main.bin", widths)

    from ebtools.ja_interface import pack_interface

    def us_table(rel: str) -> bytes:
        packed = output_dir / rel
        return packed.read_bytes() if packed.exists() else (bin_dir / rel).read_bytes()

    interface = pack_interface(ja_dir, us_table, reverse_table, us_label_addrs)
    for rel, data in interface.items():
        _write(out / rel, data)

    print(
        f"  Packed Japanese Locale: dialogue {len(blob)} bytes, inline strings {len(inline_blob)} bytes, "
        f"xlat {len(xlat)} entries, font {len(widths)} glyphs, {len(interface)} interface tables"
    )
    if stale:
        print(f"  Warning: {stale} US inline strings missing from ja/inline_strings.json print nothing")
    return 4 + len(interface)


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

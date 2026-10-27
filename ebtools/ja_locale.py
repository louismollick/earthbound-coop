"""Japanese Locale constants and config (docs/adr/0003-japanese-locale.md).

``ebtools extract-ja`` writes the Japanese assets to ``<assets>/ja/``;
``ebtools pack-all`` packs them to ``<output>/JA/``.
"""

import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ebtools.config import DumpDoc

# Text address ranges (docs/ja-plan.md "Text addresses").  US inline strings
# sit at 0x000000 and US dialogue at 0x100000 (pack_all._pack_dialogue).
JA_DIALOGUE_BASE = 0x200000
JA_INLINE_BASE = 0x300000

# Subdirectory of the assets dir (extract-ja output) and of the packed output.
JA_ASSETS_SUBDIR = "ja"
JA_PACKED_SUBDIR = "JA"

# Written by extract-ja next to the dialogue so pack-all needs no Mother 2 config.
JA_TEXT_TABLE_FILE = "text_table.json"

# Mother 2 glyph codes 0x20-0xFF, one font glyph each.
JA_FIRST_GLYPH = 0x20
JA_GLYPH_COUNT = 0x100 - JA_FIRST_GLYPH


class JaLocaleConfig(BaseModel):
    """``ja_locale.yml``: what extract-ja needs beyond ``mother2.yml``."""

    model_config = ConfigDict(extra="forbid")

    romSha1: str
    textTable: dict[int, str] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    # US labels whose Japanese message is Mother 2's whole message, logic too.
    motherLogic: list[str] = Field(default_factory=list)
    # Mother 2 symbol -> (ROM offset, bytes to the next symbol), for the
    # interface tables (ebtools.ja_interface; regenerate with `ebtools ja-offsets`).
    romSymbols: dict[str, tuple[int, int]] = Field(default_factory=dict)


def load_ja_locale(path: Path) -> JaLocaleConfig:
    """Load ``ja_locale.yml``."""
    return JaLocaleConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def ja_text_table(mother2_doc: DumpDoc, config: JaLocaleConfig) -> dict[int, str]:
    """Return the Japanese text table: Mother 2's ``textTable`` plus the supplement.

    Raises ``ValueError`` if two codes share a character (encoding must round-trip).
    """
    table = {**mother2_doc.textTable, **config.textTable}
    seen: dict[str, int] = {}
    for code, char in sorted(table.items()):
        if char in seen:
            raise ValueError(f"JA text table: {char!r} is both 0x{seen[char]:02X} and 0x{code:02X}")
        seen[char] = code
    return table


def write_text_table(path: Path, table: dict[int, str]) -> None:
    """Write the text table as JSON (``{"0x20": " ", ...}``)."""
    path.write_text(
        json.dumps({f"0x{k:02X}": v for k, v in sorted(table.items())}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )


def read_text_table(path: Path) -> dict[int, str]:
    """Read a text table written by :func:`write_text_table`."""
    return {int(k, 16): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}

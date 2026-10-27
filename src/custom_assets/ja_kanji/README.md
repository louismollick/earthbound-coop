# Kanji script (local, never committed)

Put a kanji version of the Japanese dialogue here to get the **Japanese (kanji)** Language (`--lang ja-kanji`, the launcher's Language row). It is game text: everything in this folder but this README is gitignored, and must stay that way.

## Layout

- `<NAME>.yml`: a converted copy of `src/assets/ja/dialogue/<NAME>.yml` (from `ebtools extract-ja`). Same labels in the same order, same ops; only the `text:` strings change. A file you leave out is played from the kana file.
- `inline_strings.json` (optional): converted values of `src/assets/ja/inline_strings.json` (item, enemy, PSI and action descriptions). Same keys; a key you leave out keeps its kana text. Change only the text between the `{...}` codes.

Kanji, and any other character Mother 2's text table lacks, are drawn from k8x12 (`src/custom_assets/fonts/k8x12/`), 8 px wide like the kana. Leave kana as kana, and leave the naming keyboard (`MSG_KBD_LAYOUT_*`) and menu labels (`load_string_to_memory`) alone.

## Making and checking it

1. Copy the files you want to convert from `src/assets/ja/dialogue/` here and convert their `text:` strings (by hand, or with a local LLM pass).
2. `ebtools check-kanji` checks labels, ops and characters against the kana files (errors, exit 1) and, with the `kanji` extra installed (`uv pip install -e '.[kanji]'`: SudachiPy and its core dictionary), compares each converted text's reading with the kana (warnings to review).
3. Build as usual. `pack-all` packs the script to `JA_KANJI/`; if a check fails it warns and builds without the kanji Language.

Kana and kanji share saves. Savestates and online Sessions keep them apart.

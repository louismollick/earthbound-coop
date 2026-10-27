# Japanese plan

Play the C port in Japanese, with the text, fonts and graphics of the user's Mother 2 ROM, in the same executable as English. Architecture: ADR 0003. Each milestone is one PR, merged when its gates pass.

## Settled decisions

- **Language** is picked before the game starts: a launcher row (English, Japanese, and Japanese kanji when the local kanji script exists) and `--lang en|ja|ja-kanji` (also `EB_LANG`) for headless runs and builds without the launcher. It never changes while the game runs.
- **Text-only Locale.** Japanese messages keep the US logic ops and take Mother 2's presentation ops. US-only messages keep their logic and print nothing. A label that exists only in Mother 2 is dropped.
- **Donor ROM.** `mother2.sfc` (unheadered, SHA-1 `8738cff9e38a8b86ae30bfe0e5fbcb2828c2b16e`) in the repo root, gitignored. Without it the build is English-only and the launcher has no Language row.
- **Assets.** `ebtools extract-ja` writes the editable Japanese assets to `src/assets/ja/` (dialogue YAML in the US file layout and label order, JSON tables). `pack-all` packs them to `build/packed_assets/JA/`, and the registry embeds them as overrides: in Japanese, `ASSET_DATA(id)` returns the `JA/` variant when there is one. In English nothing changes.
- **Text addresses.** US inline strings `0x000000`, US dialogue `0x100000`, Japanese dialogue `0x200000`, Japanese inline strings `0x300000`. In Japanese, a US address is translated through a label table (`JA/text/xlat.bin`) when text is resolved; Japanese internal jumps already point into the Japanese ranges.
- **Encoding.** Japanese text keeps Mother 2's encoding: control codes below `0x20`, glyphs `0x20` to `0xFF`. The code that classifies or converts characters asks the Locale (`eb_char_space()`, `eb_glyph_index()`, `ascii_to_eb_char()`, ...).
- **Font.** The Japanese glyphs are Mother 2's 8x16 text tiles (two stacked tiles per code in `JP/graphics/text_window.gfx`), packed into the US variable-width font format with a fixed 8 px advance.
- **Saves.** A Japanese save block carries `JA` in the last two padding bytes. File select shows a save of the other Language as a locked slot labelled `English` or `日本語`: it can't be loaded, copied over or started over, only deleted from its own Language. Kana and kanji share saves.
- **Savestates** record the Locale; loading one from another Locale is rejected like a layout mismatch.
- **Online.** The fingerprint carries the Locale, and the asset hash covers only the active Locale's assets, so an English-only build can join an English Session of a build that also has Japanese.
- **English is untouched.** All Japanese paths are gated on the Locale.

## Gates (every milestone)

1. Build `-DEB_WERROR=ON` at both viewports, with and without `mother2.sfc` extracted.
2. `uv run --no-sync python -m pytest tests -q` passes, including the Japanese tests when the Japanese assets exist.
3. English bit-identical: `regress.py compare BASE NEW` shows no diffs and `regress.py framehash BASE NEW` 0 changed frames, BASE being the merge base.
4. Japanese playtest: the milestone's scenes reached with `--lang ja`, screenshots read by hand.
5. One adversarial review per milestone (GPT 6.1 Sol), findings fixed or rebutted.

## J1 Locale switch and Japanese dialogue

- [ ] `make mother2` builds a ROM identical to `mother2.sfc` (renamed labels in the JP-only files).
- [ ] `ebtools extract-ja`: Japanese dialogue YAML (US logic, Mother 2 presentation), Japanese inline strings for item, enemy, PSI and action descriptions, the Japanese font.
- [ ] Packing and embedding: `JA/` overrides, the Japanese dialogue and inline blobs, the address table.
- [ ] Runtime Locale, `--lang`, `EB_LANG`, the launcher's Language row.
- [ ] Text engine: glyph index, space, word wrap, bullet, text sounds and number printing follow the Locale; all variable-width fonts use the Japanese glyphs.
- [ ] Save tag and locked slots, savestate Locale, online fingerprint.
- [ ] Tests: logic invariant over every label; save tag round trip; an untagged save loads as English.
- [ ] Playtest: Ness's house to the meteorite, a shop, a battle and an item description in Japanese.

## J2 Japanese interface

- [x] Name tables: items, enemies, PSI, teleport destinations, phone contacts, store and status text. Window titles: see below.
- [x] The strings hardcoded in C (file select, battle commands, equip and Goods menus) come from the Mother 2 ROM in Japanese.
- [x] Battle grammar: enemy suffixes and articles.
- [ ] Kana naming keyboard and the Mother 2 Don't Care names.
- [ ] Mr. Saturn's Japanese font.

## J3 Japanese graphics and cinematics

- [ ] Town map labels, the sound stone, attract mode text.
- [ ] Flyovers, the coffee and tea breaks and Lumine Hall, with the cinematic font's kanji.
- [ ] Staff credits and cast names.

## J4 Kanji

- [ ] An extended glyph code for kanji, in the text DSL and the renderer.
- [ ] A free pixel kanji font (redistributable license) in `src/custom_assets/`.
- [ ] A gitignored override folder for a kanji script, packed over the kana dialogue when present; the launcher's Japanese kanji choice.
- [ ] A checker test (skips without an override): control codes unchanged, every glyph in the font, and, with SudachiPy installed, the reading of every converted line equals the original kana.

## Decisions made during the build

- **Interface tables** (`ebtools/ja_interface.py`): a Japanese table keeps the US table's layout and bytes, with only the name fields replaced by Mother 2's (null-padded to the US size) and packed to `JA/<US path>`, so gameplay data stays the US data and `ASSET_DATA` serves it. Mother 2 offsets are `ja_locale.yml` `romSymbols`, regenerated from `build/mother2.map` by `ebtools ja-offsets`. The enemy table also takes Mother 2's encounter and death message choices (the US added encounter verbs Mother 2 has no text for) and clears `the_flag`, so English articles print nothing.
- **UI strings**: C literals go through `ui_text(UI_X, "English")` (`src/game/ui_text.h`), which returns the literal in English and the Mother 2 string from `JA/text/ui_strings.bin` in Japanese.
- **Encoding round trip**: in Japanese `eb_char_to_ascii` / `ascii_to_eb_char` are one bijection (identity but `:`/0x5B and `$`/0x23 swapped), so names survive the char strings of menu labels and `print_string`; no English literal reaches them in Japanese.
- **Mother 2 logic exception**: `ja_locale.yml` `motherLogic` lists US labels whose Japanese message is Mother 2's whole message. Only the Goods Give messages (`MSG_SYS_ITEM_TRANSFER*`), which the US keeps as unused copies; Japanese Give runs Mother 2's flow (`open_menu-jp.asm`) with them.
- **Japanese layouts**: where Mother 2's text doesn't fit the US positions, the Japanese path uses Mother 2's (status window, file select details, delete confirmation, equip menu and stats, battle target text, PP cost, `PRINT_CURRENCY_VALUE` with its `00` sign, number padding with spaces), and a few windows take Mother 2's size (`ja_window_configs` in `window.c`). The VWF renderer doesn't claim the empty tile after a Japanese letter (they all end on a tile edge), so text can fill a line and print next to other text.
- **Window titles** (TINY font) and the naming screen are separate work; a title's chars are `eb_char_to_ascii` chars like menu labels.

## Blocked

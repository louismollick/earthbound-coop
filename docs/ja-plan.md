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

- [x] `make mother2` builds a ROM identical to `mother2.sfc` (renamed labels in the JP-only files).
- [x] `ebtools extract-ja`: Japanese dialogue YAML (US logic, Mother 2 presentation), Japanese inline strings for item, enemy, PSI and action descriptions, the Japanese font.
- [x] Packing and embedding: `JA/` overrides, the Japanese dialogue and inline blobs, the address table.
- [x] Runtime Locale, `--lang`, `EB_LANG`, the launcher's Language row.
- [x] Text engine: glyph index, space, word wrap, bullet, text sounds and number printing follow the Locale; all variable-width fonts use the Japanese glyphs.
- [x] Save tag and locked slots, savestate Locale, online fingerprint.
- [x] Tests: logic invariant over every label; save tag round trip; an untagged save loads as English.
- [x] Playtest: Ness's house to the meteorite, a shop, a battle and an item description in Japanese.

## J2 Japanese interface

- [x] Name tables: items, enemies, PSI, teleport destinations, phone contacts, store and status text. 
- [x] The strings hardcoded in C (file select, battle commands, equip and Goods menus) come from the Mother 2 ROM in Japanese.
- [x] Battle grammar: enemy suffixes and articles.
- [x] Kana naming keyboard and the Mother 2 Don't Care names.
- [x] Mr. Saturn's Japanese font.
- [x] Window titles in Mother 2's 8x8 title font.

## J3 Japanese graphics and cinematics

- [x] Town map labels, the sound stone, attract mode text.
- [x] Flyovers, the coffee and tea breaks and Lumine Hall, with the cinematic font's kanji.
- [x] Staff credits and cast names.

## J4 Kanji

- [x] An extended glyph code for kanji, in the text DSL and the renderer.
- [x] A free pixel kanji font (redistributable license) in `src/custom_assets/`.
- [x] A gitignored override folder for a kanji script, packed over the kana dialogue when present; the launcher's Japanese kanji choice.
- [x] A checker test (skips without an override): control codes unchanged, every glyph in the font, and, with SudachiPy installed, the reading of every converted line equals the original kana.

## Decisions made during the build

- J1: Japanese text is a fallthrough chain splice (labels the US added inside a Mother 2 message keep its text); Mother 2 `call_text` to logic-free text the US lacks is inlined. 144 US labels end up silent in Japanese, mostly English grammar helpers and the US-only item-give messages (J2 ports Mother 2's give flow).
- J1: the Locale is folded into the savestate layout id (no format change); a locked slot reads `Japanese` in English and `えいご` in Japanese.
- J1: `$` is 0x23 in Mother 2's encoding (0x24 is the `00` tile).
- J1: pack-all skips the Japanese Locale (with a warning) when its dialogue lacks a US label or a message's logic drifted from the US; English always builds.
- J2: **Interface tables** (`ebtools/ja_interface.py`): a Japanese table keeps the US table's layout and bytes, with only the name fields replaced by Mother 2's (null-padded to the US size) and packed to `JA/<US path>`, so gameplay data stays the US data and `ASSET_DATA` serves it. Mother 2 offsets are `ja_locale.yml` `romSymbols`, regenerated from `build/mother2.map` by `ebtools ja-offsets`. The enemy table also takes Mother 2's encounter and death message choices (the US added encounter verbs Mother 2 has no text for) and clears `the_flag`, so English articles print nothing.
- J2: **UI strings**: C literals go through `ui_text(UI_X, "English")` (`src/game/ui_text.h`), which returns the literal in English and the Mother 2 string from `JA/text/ui_strings.bin` in Japanese.
- J2: **Encoding round trip**: in Japanese `eb_char_to_ascii` / `ascii_to_eb_char` are one bijection (identity but `:`/0x5B and `$`/0x23 swapped), so names survive the char strings of menu labels and `print_string`; no English literal reaches them in Japanese.
- J2: **Mother 2 logic exception**: `ja_locale.yml` `motherLogic` lists US labels whose Japanese message is Mother 2's whole message. Only the Goods Give messages (`MSG_SYS_ITEM_TRANSFER*`), which the US keeps as unused copies; Japanese Give runs Mother 2's flow (`open_menu-jp.asm`) with them.
- J2: **Japanese layouts**: where Mother 2's text doesn't fit the US positions, the Japanese path uses Mother 2's (status window, file select details, delete confirmation, equip menu and stats, battle target text, PP cost, `PRINT_CURRENCY_VALUE` with its `00` sign, number padding with spaces), and a few windows take Mother 2's size (`ja_window_configs` in `window.c`). The VWF renderer doesn't claim the empty tile after a Japanese letter (they all end on a tile edge), so text can fill a line and print next to other text.
- J2: **Naming screens and titles**: ported from the JPN asm (`src/intro/naming_ja.c`): the kana keyboard re-reads its layout message and keeps the name in its own buffer (Mother 2 reads both back from the tilemap); titles draw Mother 2's 8x8 title glyphs, one tile per byte; the naming windows take Mother 2's sizes.
- J3: **Graphics and cinematics** (`ebtools/ja_graphics.py`): Mother 2's bytes for an asset go to `src/assets/ja/bin/<US path>` and are packed as they are to `JA/<US path>`. Where the format and meaning match the US asset there is no C change: the town map labels, maps 2 and 4 and icon spritemaps (the pointer table rebased to the US address the C subtracts), the sound stone, the attract mode's gas station ("MOTHER 2 GYIYG STRIKES BACK!") and Nintendo logo, the staff credits font, the map tilesets' graphics and arrangements (their signs). The map chunks stay US (two blocks the US moved; block ids carry collision), and so do the map palettes (same colours, only an embedded pointer moved). The text window graphics stay US but for Mother 2's "YOU WIN!" tiles, patched in by pack-all.
- J3: **Mother 2 formats behind `locale_is_ja()`**, ported from the JPN asm: the flyovers and the coffee and tea breaks (two-byte glyph codes, the 12x12 cinematic font with its kanji, 18 px lines, `flyover.c`), the "TO BE CONTINUED..." animation (one frame; the US event script plays it), the staff text (the player's name codes as they are, the smaller font), Lumine Hall's wall text (3 + name + 97 codes, 8 px each), the cast names (text codes on Mother 2's text window tiles, redrawn half a tile right when odd, `ending.c`).
- J3: the title screen stays US ("EarthBound"): Mother 2's is another design (two BG layers, its own letter sprites and event scripts 792-798 with JP-only callroutines), a port of its own. Mother 2's 55 differing overworld sprites stay US (the port loads them from prepacked banks, not checked for words), and battle sprite 62 (five tiles, no words).

- J4: **Kanji script**: `src/custom_assets/ja_kanji/` (gitignored but its README) holds converted copies of `src/assets/ja/dialogue/*.yml` (same labels and ops, only `text` values change; a missing file is the kana file) and optionally `inline_strings.json` (converted values, same keys). It is made locally (by hand or an LLM) and never committed. `ebtools check-kanji` (also `tests/test_ja_kanji.py`) errors on unknown files, changed labels or label order, any changed op but `text`, kanji in the naming keyboard (`MSG_KBD_LAYOUT_*`, which the C reads as glyph codes) and characters neither the text table nor the font has; with the `kanji` extra (SudachiPy, `sudachidict_core`) it warns where a converted text's reading differs from the kana (a morpheme with a kanji reads as Sudachi's reading, the rest as written; katakana, long vowels and オウ/エイ normalised).
- J4: **Kanji code**: a character the Japanese text table lacks is `0x15 d1 d2`, digits `0x20`-`0xFF`, index `(d1 - 0x20) * 224 + (d2 - 0x20)` (50176 glyphs) into a glyph table pack-all builds from the characters the script uses (sorted by code point). 0x15 is the US compressed-text prefix, which no port text stream carries; with digits >= 0x20 a scanner that doesn't know kanji (coop_look, `cc_skip_args`) still steps over one as three letters. The text engine reads the three bytes in one step (DISPLAY_TEXT's loop and the word-wrap lookahead), so no savestated reader rests inside one. Only text ops (dialogue and inline strings) can hold kanji; menu labels stay kana.
- J4: **Kanji font**: k8x12 (Num Kadoma, free, redistributable and modifiable; `src/custom_assets/fonts/k8x12/`, the unmodified BDF). Its kanji are 7x11 in an 8x12 cell, so a kanji is one 8 px Mother 2 letter: a converted line is never wider than the kana one, and the J2 tile-edge rule holds. Only its 8 px wide glyphs are used, placed one column right with the baseline on row 12 (Mother 2's kana are rows 3-11), as 16-byte VWF glyphs with width 7.
- J4: **Packing**: with a script, pack-all (after the kana Locale) writes `JA_KANJI/text/{dialogue,inline_strings,xlat}.bin` (same address ranges as the kana, own xlat) and `JA_KANJI/fonts/kanji{.gfx,.bin,_chars.bin}`, checked against the kana messages (labels, ops, characters; the logic invariant follows from the kana's). A failing script is skipped with a warning; English and kana build as before. The registry defines `EB_HAVE_JA_KANJI`; `asset_is_ja` is 2 for `JA_KANJI/` assets, which only the kanji Locale reads and hashes. Kanji binds the `JA_KANJI` text and the kanji font at `game_init`; kana and English never read them. The launcher row reads "Japanese (kanji)"; savestates (layout salt "JK") and the online fingerprint (Locale byte, asset hash) already told the Locales apart.
- J4: the playtest harness prints a kanji as itself (`TEXT_TRACE_KANJI`, the code point from `kanji_chars.bin`).

## Blocked

# Japanese is a text-only Locale on the US engine

The game can run in Japanese, with Mother 2's own text, fonts and graphics, extracted at build time from the user's Mother 2 ROM. The game logic stays the US port's: every message keeps the US version's flags, items, events and jumps, and only what is printed (text, line breaks, pauses, prompts) comes from Mother 2. One executable holds every Locale it found assets for, and the Language is picked before the game starts.

Porting Mother 2 itself (its JP-only code paths, struct sizes, RAM layout and ROM addresses) was rejected: it is a second port of an older, buggier build. 5764 of the 5901 messages both versions share already run the same logic, and the rest are US fixes (an item ID, an event number, a facing direction) or renamed labels, so splicing Mother 2's text onto the US logic loses nothing worth keeping.

## Consequences

- A test checks the invariant: with presentation ops stripped, every Japanese message equals its US message.
- English stays bit-identical: `regress.py compare` and `framehash` show no diffs.
- Saves and savestates record their Language. A save from the other Language can't be loaded, copied over or overwritten (the typed names would be garbage in the other encoding).
- Online Sessions run in one Language; it is part of the build fingerprint.
- Mother 2 data never enters the repo. Offsets into the Mother 2 ROM (like `earthbound.yml`'s) are committed; the extracted assets go to the gitignored `src/assets/ja/`.

# Party changes, Stand-in, Companion, Look-only, Battle rotation (M4/M7): design memo

Research memo, 2026-10-26, against 8a41f674. Line numbers drift.

**As built (M4 Stand-in, Unconscious, Edge cases):** `coop_standin` / `coop_walker` (`src/coop/coop.c`) follow the detector below. A Stand-in's chain is its Guest alone (`current_chain`); `chain_of_entity` searches every chain by `party_characters` index; Bubble Monkey's tick is a follower tick with a one-line hook (`callroutine_screen.c`) and his chain counts as scripted while `ow.bubble_monkey_mode != 0` (his tick, which advances the modes, doesn't run while he is walked, so he stays in mode 0 until a snap). A Guest Leader (every Hero unconscious) belongs to its Stand-in. PLAYERS prints the Guest's battler name (`coop_member_name`: enemy configuration through NPC_AI_TABLE) and ` standin`. PSI Teleport's tick swap (`set_party_tick_callbacks`) regroups everyone. The bus (`m4_bus_2p`) and the Sky Runner Winters to Threed ride (`m4_solo_winters`) are tested with several Walkers. A Walker standing on an NPC when it becomes independent (followers walk through NPCs) can walk off it: `walker_step` turns off the collision of NPCs it already overlaps for its step. Solo Chapter scenarios: `m4_solo_mu`, `m4_solo_magicant`, `m4_solo_winters`, `m4_solo_paula`, and the handoffs played through: `m4_solo_winters_walk` (Tony joins and leaves, Bubble Monkey joins, Tessie), `m4_solo_paula_return` (Clumsy Robot to Paula's return) (see coop-log.md). After any snap (a door, a ride, a battle) the Monkey runs his vanilla modes until he is back in mode 0, so his Stand-in can wait a few seconds for him (about 250 frames after the Tessie ride).

## Solo Chapters

**Party changes.** Every Party change goes through text CCs `1F 11` / `1F 12` (`display_text_cc.c:81`, `:778-790`). These call `add_char_to_party` / `remove_char_from_party` (`inventory.c:689/746`), then `add_party_member` / `remove_party_member` (`overworld.c:474/961`), then `update_party` (`battle.c:5818`). The game never saves and restores the Party: each exit script re-adds a fixed member list.

| Chapter | Starts | Ends | Saves |
|---|---|---|---|
| Jeff, Winters | `EEVENT1.yml:2722` | Sky Runner crash `EEVENT2.yml:487` | `10-ToThreed` before; `11-Winters` = [Jeff, Bubble Monkey] |
| Poo, Mu training | `EEVENT3.yml:428` | `:658`, Poo joins `:683` | `23-Summers` before |
| Magicant | `EEVENT5.yml:48` | `:306/407/496/585` | `33-FireSpring` before; `34-Magicant` = [Ness] (Flying Men as Guests) |
| Paula kidnapped | `EEVENT2.yml:2058` | `EGLOBAL.yml:262` | `19`-`21` = [Ness, Jeff] |

Other Party changes:
- Poo leaves at Scaraba (`29-DungeonM`).
- The Teddy Bears are Party members 16/17.

**Detector.** Base it on the Party, not on story flags.
- **Absent:** a joined Player none of whose Heroes is in `party_members` (conscious or not).
  - **Stand-in:** the k-th absent Player in join order gets the k-th eligible Guest in Party order.
  - **Companion:** every other absent Player. Decided: this covers every absent Player, not just Solo Chapters, so a P2 waiting for Paula in early Onett gets a Companion too.
- **All Heroes KO'd:** a Player whose Heroes are all KO'd is a plain Spectator, with no Companion.
- **Battle rotation:** only when the Party has exactly one Hero.

## Guests (Stand-in)

**How Guests are stored.**
- Ids 5-15 in `party_members`.
- Entity slot 28, or 29 if 28 is taken (`overworld.c:400-418`).
- `var[1]` = slot − 24, giving `party_characters[4..5]` for the trail index.
- They follow the Leader's trail. Bubble Monkey is the exception: `EVENT_SCRIPT_003`, tick `UPDATE_PARTY_FOLLOWER_MOVEMENT`, `callroutine_screen.c:456`.

**Changes needed for Stand-ins.**
- `coop_walker` returns Heroes only, so it needs a Stand-in mapping.
- `current_chain` only takes `coop_conscious_hero`.
- `chain_of_entity` rejects char id ≥ 4. It should search every Player's chain for the member index instead.
- `chain_scripted` treats the Monkey's tick as scripted. Accept his tick (`0xEF031E`) but snap while `ow.bubble_monkey_mode != 0`.

**Eligible Guests:** 5-9 and 11-15. Exclude Dungeon Man (10, building-sized) and the Teddy Bears (16-17).

**Bug.** The PLAYERS printer reads `party_characters[w.member - 1].name` (`sdl2_input_script.c` ~615), which overruns for a Guest. It needs a Guest name table.

**Focus.** `decide_focus` lets anyone with a Walker take the lock, so Stand-ins get menus.

**Battle.** Guest battle actions are fully AI (`battle.c:3861-3880`, skipped at `:4798`, `btl_enemy_ai` `:4232`). A Guest command menu isn't simple. Keep the AI.

## Unconscious Heroes

**Vanilla behaviour.** `update_party` sorts KO'd and diamondized Heroes last, and they get the angel sprite. Co-op already drops them from chains.

**Missing scenarios:**
- (a) All of a Player's Heroes KO'd: `spectator`, with no Stand-in or Companion.
- (b) Leader KO: the new Leader's Owner gets focus.
- (c) A KO in battle, then back to the overworld.

## Edge cases

| Case | Status |
|---|---|
| Bicycle | Already caught. A join never changes the Party, so the bike stays legal and the new Player is a Spectator or Companion. No forced dismount. |
| Teleport | Caught (`psi_teleport_destination`, swapped ticks). Teleport Beta steering follows the focus. |
| Sky Runner | Caught (`set_player_lock`). |
| Bus | Caught while the bus event holds the Party. Add a scenario. |
| Taxi | No taxi ride exists in the data. Drop it. |
| Escalators | Done. |
| Mini ghost | An NPC-slot entity that tracks the Leader. Leave it. |

## Companion (Mr. Saturn)

**As built (M7):** `src/coop/coop_companion.{h,c}`, state in `CoopState.companions[4]`. Differences from the plan below:
- Script `EVENT_44` (renders, then halts), not `EVENT_10_11`, whose slow blink would fight the walk frames; co-op drives direction, frame (8 frames per walking frame) and visibility itself. Spawned in the highest free NPC slot; owned by slot + sprite + script + `var0 = 0x5A70 + Player`. A failed spawn retries every 30 frames.
- The step is the Walkers' (`coop_borrowed_step`, `coop_walk_internal.h`) with `COOP_STEP_COMPANION`: only door type 1 (ladder/rope) works, every other door type is a wall. `player_has_moved_since_map_load` is restored.
- Leash: to the view (a step taking it further out of the view minus the Walkers' margin is reverted on that axis); if the view leaves it behind (sprite off screen) it reappears next to the Leader. It never enters the camera's box or the Walkers' leash.
- Hidden means removed (no entity, so no slot, script, VRAM or spritemaps held): from an enemy touch through the battle and whenever the game controls movement (`WALK_CONTROLLED`, the Leader moving or not, a fully frozen cutscene included), checked every frame by `coop_companion_watch` from `coop_tick` since no entity ticks then; also at a door's fade or PSI Teleport (`coop_walk_regroup`) and on a trail reset. Shown again next to the Leader (beside, behind or in front: a clear spot no other Mr. Saturn takes).
- The game's entities win: when `entity_init` has no slot or script slot, or `create_entity` fails (sprite VRAM, spritemaps), every Companion is removed and the allocation retried (`coop_companion_reclaim`); the Companion spawns again only into a free slot (`create_entity_raw`). `find_entity_by_sprite_id` and `find_entity_by_npc_id` skip Companions (`coop_companion_slot`).
- Interaction: A or L takes the lock (`capture_buttons`); A reads as L while it holds it. `coop_companion_interact` searches with its hitbox enabled and its own slot marked collision-disabled. `coop_interact_muted` (one line in `QCT_TEXT`) closes the empty text window and plays `MYSTERIOUS_2` (114) when the text isn't Look-only; that includes "nothing here" (`MSG_SYS_NOTHING_WRONG_HERE` can jump to a debug item gift).
- PLAYERS: `walker=Mr. Saturn companion pos=... dir=... walk=...` or `... companion hidden`.

**Sprite.** `MR_SATURN = 171`: 4 directions × 2 frames, no diagonals (collapse diagonals to a cardinal), 8×8 hitbox, 16×24.

**Spawn.** `create_entity(171, script, -1, x, y)` allocates from slots 0-21. Use a static NPC script (`EVENT_10_11`) that doesn't despawn. Never use `EVENT_8`, which despawns.

**Walking.**
- Use the same walker-step swap with `current_party_members` set to its slot.
- Its own door hook: ladders and ropes only.
- `hitbox_enabled = 0`: it walks through NPCs, never fills `collided_objects[23]`, and so can't start a battle.
- Write its position, direction and animation frame.
- Leash it to the screen. It doesn't move the camera.

**Lifetime.**
- `clear_map_entities` wipes slots 0-29 on loads, so respawn on the first free frame after a trail reset, and retry when VRAM is full.
- While the game controls movement: hide it, park it at the Leader, and show it again afterwards.
- Store it in CoopState.

**Sound.** There's no "boing" SFX. The candidates are `CHEEP=101`, `CLUCK=104` and `MYSTERIOUS_2=114` (Saturn Valley uses `MYSTERIOUS_2`).

## Look-only scan

**As built (M7):** `coop_look_scan` / `coop_look_only` (`src/coop/coop_look.c`), over `display_text_resolve` (`display_text.c`). Lists below are what it does; they come from the C runtime (`step_display_text_run`, the `cc_18`..`cc_1f` dispatchers), not `opcodes.py`. `--selftest-look` prints the test labels and NPC stats; `tests/test_coop_look.py` checks them. Of the NPC config entries with text: PERSON 536 Look-only / 463 not, OBJECT 69 / 69, ITEM_BOX 0 / 177. A YAML-level reachability walk with the same whitelist agrees on all 1314.

**Where text lives.**
- Text is one dialogue blob, addresses ≥ 0x100000 (`display_text.c:85`, `resolve_text_addr` `:520`). Lower addresses are the inline string table; jumps can land there, and the scan follows them too.
- NPC text comes from `get_npc_config_text_pointer` via `talk_to` / `check_action`.
- Argument lengths follow the C handlers. `opcodes.py` differs on 18 08 (U24, the runtime reads a dword), 19 24 (4 bytes, the runtime and the asm read 5) and 1C 09 (none, the runtime reads 1).

**Allowed CCs.**
- Letters ≥ 0x20. 15-17 are 1-byte no-ops in the C runtime (no dictionary; `cc_skip_args`), not +1.
- 00, 01, 03, 06-14.
- 18 00-0A, 0D (status window).
- 19 02, 04, 10, 11, 14, 16, 18-1B, 1D (only with a 0 second byte; non-zero clears the queued item), 1E-25, 27, 28.
- 1A 00, 01, 04, 05, 08, 09.
- All of 1B.
- 1C 00-0F, 11, 12, 14, 15.
- 1D 02-05, 0A-0D, 10, 11, 14, 15, 17, 19-24 (24 not with argument 2, which clears `unknownC4`).
- 1F 02, 04, 30, 31, 50, 51, 52, 60, 62, A2, C0, D1.

**Branches followed:** 06, 08, 09, 0A, 1B 02/03, 1F C0 (zero entries skipped), 18 08 (the post-menu jump, if non-zero), 1A 00/01 (the 4 member scripts, if non-zero), and the 19 02 hover script (01 + dword, if non-zero). A label stops after 25 bytes without a terminator and the rest runs as script, as in the runtime.

**Forbidden:** everything else. Notably:
- 04, 05.
- 19 05, 1C (removes an item), 26.
- 1A 06/07/0A/0B (shop, Escargo, phone, teleport menu).
- 1C 13.
- 1D 00, 01, 06-09, 0E, 0F, 12, 13, 18.
- All of 1E.
- Every other 1F, including 1F 61 (waits on an actionscript).

**Fail closed:** a CC off the list (including ones the runtime FATALs on, like 1C 10), a 0 or unresolvable target where the runtime would jump (it warns and falls through), running off the end of a block, more than 512 targets (the most any NPC text uses is 57).

**Deviations from the first draft:** 19 1C was listed both as allowed and as an effect; it is an effect. 1D 0C is a read (Escargo item status), so it is allowed. 15-17 take no argument. Added 18 0D, 1A 00/04/08/09, 1F 50/51/C0 and the 18 08 / 1A 00 / 19 02 branches. 1C 10 doesn't exist.

**Hook.**
- A Companion's A or L press takes the lock and is treated as L (QUICK_CHECKTALK).
- `coop_interact` uses the Companion's position.
- In `QCT_TEXT`, if the text isn't look-only: play the SFX, set `phase=QCT_FADE`, and return CONTINUE.

**Test labels:** `MSG_TWSN_BUS_B` (look-only), `MSG_ONET_SHARK_D_JOIN_REFUSE` (not look-only), plus a sign, the Hotel Onett porter, clerk and phone, an ATM, a shop clerk, a present and a flag-setting NPC (`tests/test_coop_look.py`).

## Battle rotation

`st->turn_counter` resets every battle, so turn 1 would always go to the Owner. Use a serialized `coop.rotation` instead, advanced from a hook in `btl_start_turn` when exactly one Hero is in the Party. Back/cancel doesn't move it.

**As built (M7):** `coop_battle_menu_player()` in `src/coop/coop_battle.c` gives the menu's Player: the Owner, then the other joined Players in join order, indexed by `(coop.rotation - 1) % player_count`. The hook in `btl_start_turn` (`coop_battle_start_turn`) advances it. The focus hook and the title tag both go through `coop_battle_menu_player()`, so the rotation's Player holds the whole menu, Run Away included. Scenarios: `m7_rotation`, `m7_rotation_full_party`.

`coop_battle_menu_player(member_id)`:
- Normally: the Owner.
- In a Solo Chapter: `[Owner, absent Players in join order][rotation % n]`.

The M2 hook at `btl_step_menu_open` calls it. Whoever holds the menu may pick Run.

## Tasks

- **A (M4).** Stand-in mapping, Guest chains, the Monkey tick, Guest names in PLAYERS with a `standin` token, KO scenarios, edge-case scenarios (bicycle + join, Teleport and bus with 3 Walkers).
- **B (M7).** Companion plus Look-only, with a scanner pytest.
- **C (M7).** Battle rotation, after M2.

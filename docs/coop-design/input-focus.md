# Input focus (M2 battle, M3 menus): design memo

Research memo, 2026-10-26. Line numbers are against d32c421 and drift.

**As built (M1 Interaction, M3):** `src/coop/coop_input.{h,c}`. It follows the memo, with these differences:
- Only a Player with a Walker can take the lock.
- Capture-eligible is the release predicate plus no window, no queued interaction or demo, and not on the bicycle, which keeps the dismount with the Leader's Owner.
- The Leader's step reads its Owner's pad while someone else has the focus (`coop_leader_pad_enter/leave`).
- Talk/Check swap in the focused Walker only while it is independent (`coop_interact`).
- The text-script party select (a shop's "Which of you will carry this?") also starts on the Walker.
- Battle (M2, `src/coop/coop_battle.{h,c}`): one hook at the top of every `mode_step_battle` iteration requests the Owner of `party_members[party_slot]` during `BTL_MENU_SELECT`..`BTL_MENU_DECIDE` and ALL in every other phase, instead of separate calls at `menu_open`, `BTL_ENEMY_AI` and the abort paths. The title tag is `coop_battle_title()` in `bm_build_menu`.

## Model

One serialized input focus: P1..P4 or ALL.

- In co-op, `memory_update_joypad()` receives the focused Player's pad, or the OR of all pads for ALL.
- The direct `platform_input_get_pad_new()` sites go through one wrapper, `coop_pad_new()`.
- In solo the focus is always P1, so nothing changes.
- Focus is decided in `host_process_frame`, before `memory_update_joypad`. The overworld input check (`OWP_POST_INPUT`) therefore sees the capturing Player's press on the same frame.

**Rebase on every switch.** `memory_update_joypad` (`memory.c:38-69`) derives `pressed = cur & ~pad1_held` and shares one `pad_timer`, so switching sources creates phantom presses and instant autorepeat. Fix: `memory_rebase_joypad(prev_raw)`:

```c
core.pad1_held = prev_raw & 0xFFF0;
core.pad1_autorepeat = 0;
core.pad_timer = PAD_INITIAL_DELAY;
```

- `prev_raw` is the new source's pad from the previous frame. Keep `coop_prev_pad[4]` and serialize it.
- The host calls the rebase whenever the requested focus differs from the applied focus.
- Battle code only sets `coop_focus`. The host applies the change on its next frame.

The co-op feed runs before the demo-playback override and before the `capture_unwinding` zeroing (`game_main.c:468-485`), so both still win.

## Battle
- **Menu loop:** `btl_step_menu_body` (`battle.c:4789`). It skips Guests (`member_id > 4`, `:4798`) and members that can't act (`:4803`).
- **Current Hero:** known at `btl_step_menu_open` (`battle.c:4827`). Set focus to that Hero's Owner there. Back/cancel (`:4897-4906`) re-enters `menu_open`, so the same hook covers it.
- **Exit:** the loop exits at `:4823` (`BTL_ENEMY_AI`). Set focus to ALL there and at battle entry (`mode_step_battle_entry`, `:6583`).
- **Input readers:**
  - The command menu, Goods and PSI go through the selection menu: `window.c:1730` reads the platform directly and `:1764` reads `core.pad1_autorepeat`.
  - Enemy and row targeting read the platform directly: `battle_targeting.c:390` and `:592`.
  - Ally targeting reads `core.pad1_pressed`: `mode_step_char_select`, `battle.c:461-475`.
- **Run and Auto Fight** appear only when `num_selected == 0` (`:2807-2820`), which is the first Hero with a menu. Run is converted at `:4886-4893` and sets `initiative_mode` 3/4, so the rest skip their menus. Auto Fight (`:2978`) sets `game_state.auto_fight_enable`.
- **Auto Fight cancel** is `core.pad1_held & PAD_B` in `battle_push_text_ex` (`battle.c:3739`). With focus ALL, any Player can cancel it.
- **Battle text advance** reads `core.pad1_pressed & PAD_TEXT_ADVANCE` in `display_text_cc.c` (`:464`, `:642`, `:655`, `:676`). Rule: outside a command menu, battle focus is ALL.
- **P1-P4 tag:** goes in the command window title. `bm_build_menu` calls `set_window_title(window_id, name_buf, 5)` at `battle.c:2782-2789`. It uses the TINY font (`render_title_to_vram`, `text.c:4581`, 6px advance, 16 tiles per title slot), which has `P` and the digits. In co-op, build `"Paula P2"` with `max_len >= 8`.

## Overworld
- **Buttons** in `OWP_POST_INPUT` (`game_main.c:1457-1490`):
  - A: pause menu.
  - B or Select: HP/PP display.
  - X: town map.
  - L: `QUICK_CHECKTALK`.
- **Other Leader-only pad uses:**
  - bicycle dismount (`:1402`) and bell (`position_buffer.c:1198`)
  - Leader movement (`position_buffer.c:983`, `core.pad1_held`)
  - mushroom d-pad swap (`:1085-1092`)
  - Teleport Beta steering (`overworld_teleport.c:295`)
- **Default character cursor:** `char_select_make_init` (`battle.c:625-631`) starts at `win.battle_menu_current_character_id`, or 0 when it is -1, which is the overworld case. Callers: Goods `text.c:2841`, Equip `:1553`, PSI `:2023`, Status `:1802`, Give `:3029`. In co-op, start on the focused Walker's slot. For PSI, use it only if the slot passes `CS_CHECKVALID_PSI`.
- **Script-driven interactions** (text, yes/no, shops, ATM, phone/save, hotel, Escargo) read input through four places:
  - text prompts: `core.pad1_*`
  - selection menus: `window.c:1730`
  - number select: `display_text_cc.c:377-415`
  - character selects
- **Direct platform pad reads** (all to go through `coop_pad_new()`):
  - `window.c:1730`
  - `battle_targeting.c:390`, `:592`
  - `game_main.c:676`
  - `file_select.c:862`, `:1147`
  - `title_screen.c:190`, `attract_mode.c:140`, `logo_screen.c:192`
  - `gas_station.c:210/237/265/278/315`
- **Talk and Check search from the Leader.** This covers `talk_to`/`check_action` (`overworld_interaction.c:419/457`), the find-nearby searches (`:365/392`) and `set_entity_direction_from_leader`, all using `game_state.leader_x/y/direction`. M1 must swap in the focused Walker's position and direction for the search.

## Lock state machine (overworld)

**Capture-eligible:** all of these hold:

- the mode stack is OVERWORLD only
- `!ow.pending_interactions`
- `!ow.input_disable_frame_counter`
- no swirl or enemy touch
- `!any_window_open()`
- no demo playback

**Release:** the harness `idle` predicate (`sdl2_input_script.c:453-478`), which adds:

- the Leader is frozen
- escalator, stairs
- `camera_mode`
- auto-walk, fade

Behaviour:

- **Unlocked:** focus is the Leader's Owner.
- **Capture:** on an eligible frame, the lowest-numbered Player with a new press of A, L, X, B or SELECT takes the lock.
- **Release:** the lock is released on the first release-idle frame.
- **Battle:** battle entry clears the lock.

## Entity scripts

`GET_PAD_PRESS` and `GET_PAD_STATE` (`callroutine.c:1105-1113`) read `core.pad1_*`, so they follow the focus.

## Simultaneous battle input (M7)

Parallel menus are hard: there is one mode stack and global menu state, and there are only 5 title slots. A cheap version, "first come, first served": in `btl_step_menu_body`, the next menu goes to whichever Player with unchosen Heroes presses A first. Turn order comes from initiative (`btl_find_attacker`, `battle.c:4413`), not from menu order.

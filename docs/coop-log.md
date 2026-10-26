# Co-op build log

One entry per PLAN.md item: what changed, gate results, decisions and deviations.

## M0 Foundation

### scripts/coop-setup.sh (2026-10-26)
- Idempotent setup: checks tools, submodules, `uv venv --seed --python 3.12 .venv`, installs ebtools + pytest + numpy, fetches any missing story save from fantasyanime (`earthbsaveNN.zip`), extracts assets once, builds `build-base` (worktree `../ebsrc-base` at d32c421, 320x240, only when missing), `build-wide` (320x240, -Werror), `build` (256x224, -Werror), `build-debug` (320x240, ASan+UBSan).
- Fresh run 1m52s; second run 32s and rebuilds nothing but the incremental current-tree builds.
- Baseline: `regress.py compare build-base build-wide` = 0 of 32 cases differ (the `bus` bug is in both, so it doesn't show as a diff).

### scripts/coop-gates.sh (2026-10-26)
- Gates 1-4 (both -Werror builds, ruff, pytest, regress compare vs build-base, co-op suite), `--framehash`, `--full` (ASan+UBSan co-op suite and a contact sheet at `playtest/out/gates/contact.png`). One verdict line, non-zero exit on failure. ~50 s.
- Setup now installs ruff 0.15.4 (the pre-commit pin) into the venv.

### Four pads, per-Player scripts, join model, scenario runner (a2119053)
- `platform_input_get_pad_n/_new_n`; unix has per-Player pads, P2 keyboard layout IJKL/U/O/P/[, SDL GameControllers in connection order. Other ports return P1 for 0.
- Script syntax: `P2 10 RIGHT`, `press P3 A`, `until text 60 P4 START*`, sticky `hold P2 RIGHT` / `release P2`. STATE prints `PLAYERS P1:joined owns=... walker=... pos=(x,y) | ...`.
- `src/coop/coop.{h,c}`: CoopState (17 bytes, SECTION_COOP): join order, joined, leave-hold counters, hero owners. Start joins, Select+Start 120 frames leaves, `--players N`.
- `playtest/coop/run_all.py` + 6 scenarios (bedroom join, `--players`, leave, savestate across processes, prefix forms at 4P, full-Party ownership on 27-Kraken).
- Gates: PASS. regress 0/32 differ, framehash 0 changed frames over 31 cases, pytest 1827 passed / 5 skipped, co-op 6/6, ASan+UBSan 6/6 clean. Contact sheet read: shots match state.
- Untested: the IJKL layout and real controllers (need a windowed session), the arm builds (no toolchain here). The external gw firmware repo will need `src/coop/coop.c` and the `_n` functions.

### M0 adversarial review (GPT 6.1 Sol, one pass) and fixes
- Bug: join edges came from the platform's unserialized `pad_prev`. Fixed: `CoopState.prev_held[4]` (serialized; struct now 26 bytes) and `coop_tick(held)` computes edges itself.
- Bug: capture-unwind frames reset leave counters and could fake a fresh Start (rejoin). Fixed: `coop_tick` is skipped on unwind frames, and paused script frames keep sticky holds. New scenario `p2_capture_holds` (failed before, passes after).
- Risk: out-of-order ownership was only checked with Ness present (a by-Player-number deal passed). Fixed: `ownership_full_party` now joins P3, P4, P2 with all four Heroes, has a middle Player leave and rejoin, and asserts every owner.
- Risk: setup could reuse a moved `../ebsrc-base`. Fixed: setup checks it's a clean checkout of d32c421.
- Gates `--full --framehash`: PASS (regress 0 differ, framehash 0 changed frames, co-op 7/7, ASan+UBSan clean).

## M1 Overworld

### Ownership/Walkers and independent walking (items 1-2)
- `src/coop/coop_walk.{h,c}`. The Leader walks the vanilla path on its Owner's pad (`coop_pad1_feed`, with `memory_rebase_joypad` on a switch, only during overworld play). Each other Player's Walker takes `update_overworld_player_input()` with its state swapped into the Leader globals and writes its own 256-entry trail. That Player's other conscious Heroes follow the trail with vanilla spacing and animation; Guests, the Leader's Owner's other Heroes and unconscious members trail the Leader.
- Hooks (all gated on `coop_player_count() > 1`): end of `update_leader_movement`, top of `update_follower_state`, the ladder/door tile check in `update_overworld_player_input` (escalators and stairs are walls for Walkers), `init_party_position_buffer` / `fill_party_position_buffer` (trail reset → snap), `update_party_sprite_position` (chain members always recompute screen coords), `host_process_frame` (pad feed, unwind = no Walker input).
- Snap/unsnap: shadow `position_index` per the memo; unsnap lays straight segments through the members' current positions. Windows/text only pause Walkers. A temporary clamp (viewport/2 − 16 px from the Leader) stands in for the leash.
- CoopState +8330 bytes (26 → 8356): `walk_pad[4]`, `pad1_player`, `walkers[4]` (Walker state, touched, active, head, chain, ring indices, trail). `state_layout.h` regenerated.
- Scenarios (all failed on the pre-change build): `m1_p2_walks_wall`, `m1_npc_blocks`, `m1_diagonal`, `m1_water`, `m1_trails`, `m1_snap`, `m1_stairs_rope`, `m1_walker_ko`, `m1_pad_source`, `m1_3p`, `m1_4p`.
- Gates `--framehash --full`: PASS. regress 0 of 32 differ, framehash 0 of 31 cases / 0 frames, pytest 1827 passed / 5 skipped, co-op 18/18, ASan+UBSan 18/18. The 11 M1 scenarios also pass at 256x224. Contact sheet read: sprites sit where PLAYERS/FOLLOW say, unconscious Paula shows the vanilla ghost sprite.
- Untested: escalators (stairs are covered, and both go through the same door-type check), real pads, the arm builds and cppcheck (no toolchain here).

### Interaction (M1) and M3 Menus and dialogue: the input focus
- `src/coop/coop_input.{h,c}`, per `docs/coop-design/input-focus.md`. One serialized focus (P1-P4 or ALL) feeds `core.pad1` from `host_process_frame` before `memory_update_joypad`, with `memory_rebase_joypad` on every switch. It replaces M1's `coop_pad1_feed`. Every direct `platform_input_get_pad_new()` in game code (window.c, battle_targeting.c, file_select, title, attract, logo, gas_station, `wait_frames_or_button`) now calls `coop_pad_new()`: in solo that is the platform call, and in co-op it returns the focused pad's edges from `CoopState.prev_held`.
- Overworld lock: unlocked, the focus is the Leader's Owner. On a capture-eligible frame (Party idle, no window, no queued interaction or demo, not on the bicycle), the lowest-numbered Player with a Walker who newly presses A/L/X/B/SELECT takes it, and that same press opens the menu, Check, the town map or the HP/PP window. It releases on the first idle frame. Battle entry clears it and sets ALL.
- Hooks (gated on `coop_player_count() > 1`): the host feed; the 14 `coop_pad_new()` sites; `coop_leader_pad_enter/leave` around the Leader's step in `update_leader_movement` (the Leader reads its Owner's pad while someone else has the focus); `coop_interact(talk_to)` / `coop_interact(check_action)` at the pause menu's Talk to/Check and QUICK_CHECKTALK (search from the focused Walker, so the NPC faces it); `coop_char_select_index` in `char_select_make_init` and `party_selector_battle_prepare`.
- CoopState 8356 -> 8360 bytes: `pad1_player` became `focus`, plus `focus_request`, `focus_locked`, `focus_in_battle`, `focus_new`. `state_layout.h` regenerated. `CoopWalkerInfo` gained `entity`. PLAYERS ends with `| focus=P2 locked` / `focus=P1` / `focus=ALL`.
- Scenarios (all failed on the pre-change build): `m1_p2_talks`, `m3_yesno_pad` (L), `m3_p2_buys`, `m3_p2_phone_save` (save.srm changes, a fresh process boots it), `m3_p3_goods`, `m3_lock_release` (no 1-frame Leader step on the locker's d-pad: without the Leader pad swap Ness moved 1 px on the menu-close frame), `m3_battle_all`, solo guard `m3_solo_menus`. `m1_pad_source` now has P3 close its own menu.
- Gates `--framehash`, then `--full`: PASS. regress 0 of 32 differ, framehash 0 of 31 cases / 0 differing frames, pytest 1827 passed / 5 skipped, co-op 26/26 at 320x240 and at 256x224, ASan+UBSan 26/26. Contact sheet read: the menu and carry cursors are on the locker's Hero (Paula, Jeff), Ness in solo, and the sailor faces Paula.
- Not scenario-tested: ATMs, hotels and Escargo (they read input through the same selection menus, number select and text prompts), and the town map and HP/PP window opened by a non-Leader (the HP/PP capture shows up in `m3_p2_buys`).

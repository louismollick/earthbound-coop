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

### Camera, leash, enemy contact, regrouping (M1 items 3, 4, 6, 7)
- `src/coop/coop_camera.{h,c}`: while any non-Leader Walker is independent the view centres on the Walkers' bounding box, through vanilla's `center_screen` / `map_refresh_tilemaps` (tile streaming, collision grid, NPC spawns). Otherwise it follows the Leader as vanilla. Switching eases (integer decay, ~12 frames); a jump of more than a screen cuts. Smooth camera off in co-op.
- Leash (`coop_walk.c`): a step that would widen the spread past viewport - 2 x viewport/8 on an axis is reverted on that axis, for the Leader too (`coop_leader_step` wraps its step). It replaces `TEMP_CLAMP_*`.
- Despawn: `IS_ENTITY_NEAR_LEADER` and `RESET_ENTITY_ANIMATION`'s near test measure from the view centre in co-op (`coop_near_x/y`). Every party sprite recomputes its screen position in co-op.
- Contact: a Walker's step touching an enemy counts in `check_entity_enemy_collision`; `HANDLE_ENEMY_CONTACT` targets that Walker; first strike uses the target's own facing for another Player's Hero (`coop_contact_facing`); during the touch shake each chain turns with its own pad. Enemy touch, swirl and battle only hold the chains, so Walkers are back where they stood after the battle (members track a `shown` trail entry so `refresh_party_entities` can't misplace them).
- Regroup: under game control chains hold until the Leader actually moves, then snap and take vanilla formation on the Leader's trail at once; the exit fade of a screen transition (`screen_transition_prepare`, door.c) regroups everyone. Door text, an NPC line or a scripted pause no longer pull Walkers anywhere.
- Hooks (gated on `coop_player_count() > 1`): `update_leader_movement` (leashed step, vanilla `center_screen` skipped), `update_camera_mode_3` (2 lines), `update_party_sprite_position`, the two near tests, `check_entity_enemy_collision`, `HANDLE_ENEMY_CONTACT`, `initiate_enemy_encounter`, `screen_transition_prepare`, `smooth_camera_prepare`.
- CoopState 8360 -> 8394 bytes: `CoopCamera camera` (ease, last view, midpoint flag, explicit pad) and `CoopWalker.shown[6]`. `state_layout.h` regenerated. STATE prints `CAMERA (x,y) view=WxH`, plus `CONTACT enemy= target= initiative=` from a touch until the battle (regress compares neither).
- Scenarios (all failed on the pre-change build except `m1_escalator`, a verification): `m1_leash_edge`, `m1_leash_native` (256x224 via `ctx.native_bin`), `m1_camera_midpoint` (incl. the Onett map top edge), `m1_enemy_contact` (P2's touch targets Paula; first strike by Paula's facing: normal, where Ness's facing gave enemies first), `m1_door_regroup`, `m1_cutscene_recover` (Kraken voyage to Scaraba), `m1_camera_3p`, `m1_camera_4p`, `m1_escalator`.
- Gates `--framehash --full`: PASS. regress 0 of 32 differ, framehash 0 of 31 cases / 0 differing frames, pytest 1827 passed / 5 skipped, co-op 35/35 at 320x240 and at 256x224, ASan+UBSan 35/35. Contact sheet read: Walkers sit the margin inside the edges at the leash, the camera frames the box centre, the Party stands in formation behind Ness at a door fade and on the escalator; no NPC popped at the edges in the shots.
- Not scenario-tested: a Leader-only hotspot transition (same control path as doors and cutscenes); a Party-first case judged by a Walker (no deterministic setup found; the enemies-first/normal divergence covers the facing rule); NPC despawn at P2's edge (checked by reading the hook, not by a scenario). When a Player leaves mid-spread, the camera jumps to the Leader on the next step (solo is vanilla).

### Interaction (M1) and M3 Menus and dialogue: the input focus
- `src/coop/coop_input.{h,c}`, per `docs/coop-design/input-focus.md`. One serialized focus (P1-P4 or ALL) feeds `core.pad1` from `host_process_frame` before `memory_update_joypad`, with `memory_rebase_joypad` on every switch. It replaces M1's `coop_pad1_feed`. Every direct `platform_input_get_pad_new()` in game code (window.c, battle_targeting.c, file_select, title, attract, logo, gas_station, `wait_frames_or_button`) now calls `coop_pad_new()`: in solo that is the platform call, and in co-op it returns the focused pad's edges from `CoopState.prev_held`.
- Overworld lock: unlocked, the focus is the Leader's Owner. On a capture-eligible frame (Party idle, no window, no queued interaction or demo, not on the bicycle), the lowest-numbered Player with a Walker who newly presses A/L/X/B/SELECT takes it, and that same press opens the menu, Check, the town map or the HP/PP window. It releases on the first idle frame. Battle entry clears it and sets ALL.
- Hooks (gated on `coop_player_count() > 1`): the host feed; the 14 `coop_pad_new()` sites; `coop_leader_pad_enter/leave` around the Leader's step in `update_leader_movement` (the Leader reads its Owner's pad while someone else has the focus); `coop_interact(talk_to)` / `coop_interact(check_action)` at the pause menu's Talk to/Check and QUICK_CHECKTALK (search from the focused Walker, so the NPC faces it); `coop_char_select_index` in `char_select_make_init` and `party_selector_battle_prepare`.
- CoopState 8356 -> 8360 bytes: `pad1_player` became `focus`, plus `focus_request`, `focus_locked`, `focus_in_battle`, `focus_new`. `state_layout.h` regenerated. `CoopWalkerInfo` gained `entity`. PLAYERS ends with `| focus=P2 locked` / `focus=P1` / `focus=ALL`.
- Scenarios (all failed on the pre-change build): `m1_p2_talks`, `m3_yesno_pad` (L), `m3_p2_buys`, `m3_p2_phone_save` (save.srm changes, a fresh process boots it), `m3_p3_goods`, `m3_lock_release` (no 1-frame Leader step on the locker's d-pad: without the Leader pad swap Ness moved 1 px on the menu-close frame), `m3_battle_all`, solo guard `m3_solo_menus`. `m1_pad_source` now has P3 close its own menu.
- Gates `--framehash`, then `--full`: PASS. regress 0 of 32 differ, framehash 0 of 31 cases / 0 differing frames, pytest 1827 passed / 5 skipped, co-op 26/26 at 320x240 and at 256x224, ASan+UBSan 26/26. Contact sheet read: the menu and carry cursors are on the locker's Hero (Paula, Jeff), Ness in solo, and the sailor faces Paula.
- Not scenario-tested: ATMs, hotels and Escargo (they read input through the same selection menus, number select and text prompts), and the town map and HP/PP window opened by a non-Leader (the HP/PP capture shows up in `m3_p2_buys`).

### M1 milestone end (ba4646ca)
- Gates `--full --framehash`: PASS (regress 0/32, framehash 0 changed frames, co-op 35/35 at both viewports and under ASan+UBSan). Contact sheet read: leash margins, 3P/4P framing, door and escalator regroup all match the state output.
- GPT 6.1 Sol review (one pass) found: (1) leash axis rejection can land a Walker inside an NPC hitbox after a diagonal step; (2) leaving co-op while spread keeps the co-op camera and follower offsets in solo until the Leader moves; (3) `_camera_np.py` 4P Leader-leash check never reaches the limit. All three go to the next agent (fix before M4 work).
- The M3 review's first attempt failed on model capacity (no pass consumed); retried.
## M2 Battle

### Command input per Owner, Run/Auto Fight, turn tag, scenarios (items 1-4)
- `src/coop/coop_battle.{h,c}`. Hook at the top of every `mode_step_battle` iteration: `coop_battle_focus(phase, party_slot)` requests the Owner of that slot's Hero during `BTL_MENU_SELECT`..`BTL_MENU_DECIDE`, and ALL in every other phase. `BTL_MENU_SELECT` and `BTL_MENU_OPEN` each wait a frame, so the host has applied the focus before the menu reads input. The command menu, Goods, PSI, the "Whom?" select and the enemy target select all read the focused pad already (`coop_pad_new()`, `core.pad1_*`). Back (B) re-enters the previous Hero's menu, and the focus follows.
- Run Away and Auto Fight need no code: vanilla puts them on the turn's first command menu, which is its Hero's Owner's. Auto Fight's B cancel is read at text pushes, where the focus is ALL.
- Tag: `bm_build_menu` calls `coop_battle_title()`, which appends `" P%d"` with the Owner's pad number and raises `max_len` (`name_buf` is now `WINDOW_TITLE_SIZE`). The tag is in the game's tiny title font and fits at 256x224 and 320x240, in the narrow Jeff window too. Solo titles are unchanged.
- No new state: the request is the existing serialized `CoopState.focus_request`, so there is no layout change.
- Scenarios (all but the solo one failed on the pre-change build): `m2_2p_battle` (28-Scaraba; Ness's Lifeup on Paula through PSI and "Whom?", Paula and Poo defend, Jeff shoots; every other-Player probe leaves the WIN/MENU text unchanged), `m2_4p_battle` (one Hero per Player, three probes per menu, P2's B back to Ness's menu, Jeff's Goods read only P3), `m2_run` (P2 can't pick Run on Ness's menu and P1 can; with Ness asleep, Paula's first menu carries Run and P2 picks it), `m2_autofight_cancel` (the control from a snap plays the battle out, and P2 holding B brings Ness's menu back), `m2_exits` (debug win, guaranteed flee from the Onett crow's surprise opening, and a game over through "another shot?" Yes; each ends idle with focus=P1, and P2 can still take and release the lock), `m2_solo_battle` (titles "Ness", "Paula", "Jeff"). `m3_battle_all` now asserts the new rule: a Spectator advances text but can't pick Ness's command. `lib.Session.windows()` and `.title()` added.
- Gates `--framehash`, then `--full`: PASS. regress 0 of 32 cases differ, framehash 0 of 31 cases / 0 differing frames, pytest 1827 passed / 5 skipped, co-op 32/32, ASan+UBSan 32/32 clean. The M2 scenarios also pass at 256x224. Contact sheet read: the tags, the Run Away cursor, Ness's sleep icon, the raised HP window of the Hero whose turn it is, and the untagged solo title all match the state output.
- Not scenario-tested: a Player leaving mid-battle (the request then names an unjoined Player, so the focus falls back to ALL), and the Giygas prayer menus (they use the same command menu).

### M3 review (GPT 6.1 Sol, one pass, retry after a capacity failure)
- Bug (high): the Leader pad override in `coop_input.c` replaces demo/scripted input, so closing a menu at a stair entry strands the auto-walk and the lock. Bug (medium): a join/leave in the same frame leaves `focus_new` stale (dropped or replayed presses). Risk: ALL focus has different edge semantics for `coop_pad_new()` vs `core.pad1_pressed`. All three to a fix agent (m3fix).

### M3 review fixes (m3fix)
- Leader pad override: `coop_leader_pad_enter` no longer swaps in the Owner's pad during demo playback (`ow.demo_recording_flags & 0x4000`, the door/stair/escalator approach walk), only for human-driven steps. On the stairs themselves P1 (the Leader's Owner) still steers. Scenario `m3_lock_scripted_walk`: P2's menu closed at a stair entry (Ness was stuck at (5232,3567), auto-walk, P2 locked) and at an escalator entry (exit walk ended at (4736,6704), 21 px short of solo's (4715,6704)).
- Join/leave edges: the host now calls `coop_input_feed` every frame, solo too, instead of only in co-op. It runs before `coop_tick`, so the cached presses are always this frame's presses of the pad core.pad1 got, whatever the count becomes. Chosen over moving `coop_tick` before the feed, which would need the pre-tick `prev_held`. Solo stays vanilla: the feed returns P1's pad unchanged and `coop_pad_new()` is still `platform_input_get_pad_new()`; the only solo difference is the serialized `focus_new` byte. Scenario `m3_join_leave_edges`: P2's START on the intro-logo frame of P1's A (the A was dropped), and P2 leaving on the frame of P1's menu DOWN then rejoining (the cursor moved down again).
- ALL edges: `coop_all_focus_edges()` right after `memory_update_joypad`, co-op and focus ALL only, adds the per-Player edges (`focus_new`) to `core.pad1_pressed` and `core.pad1_autorepeat`, so both readers agree that any one Player's press is a press. `m3_battle_all` now confirms the target with an A P1 keeps holding while P2 advances the victory text (it stuck on "Ness gained 3 exp." before).
- No CoopState change, no layout regen.
- Netplay (merged coop ba27ff1a+): the feed and `coop_all_focus_edges` read only the confirmed pads and the serialized `CoopState`, and net joins run inside `platform_input_poll` before the feed, so every machine computes the same edges.
- Gates on the merged tree: `--framehash` PASS (regress 0 of 32 differ, framehash 0 of 31 cases / 0 differing frames, pytest 1827 passed / 5 skipped, co-op 49/49), then `--full` PASS (ASan+UBSan 49/49 clean). Shots of the new scenarios match their state.

### M6 Online (merged fdb7a936)
- Star-topology input lockstep in `port/unix/net/` (UDP, the Host relays confirmed 4-pad frame sets; K-frame redundancy; `--host`, `--join`, `--input-delay`, `--local-players`). Joins: a CAPTURE session event makes every machine unwind identically, the Host ships state + SRAM + platform pad history in 1 KB chunks, then a JOIN event runs `coop_join` everywhere. A client silent for 10 s is dropped with a LEAVE event. Per-section state hashes every 60 frames; a mismatch stops the Session and writes `desync-*` dumps.
- Found and fixed two real cold-load bugs via join desyncs (flavour-palette cache, lazily bound battle action table); both also affected F7 after a restart.
- Long soak: 108,000 frames, 2 Players, 100 ms one-way + 30 ms jitter + 2% loss, input delay 30 (for throughput; headless is uncapped), 0 desyncs, 612 s wall. Short soak, mid-game join, rejoin, 4P, mixed local+remote and a deliberate-desync detector run in the normal suite.
- Gates on the merged tree (with M2): `--framehash` PASS (regress 0/32, framehash 0 changed frames).

### M2 review (GPT 6.1 Sol, one pass)
- Bug: a join/leave while a battle menu (or its PSI/Goods/target child) is open leaves the menu on the old Owner's pad and a stale tag. Sent to the M7 battle agent (it is reworking the same focus code) with a scenario-first brief.
- Risk: `m2_exits` lock check passes vacuously when P2 has no Walker. Same agent.
- Rebutted: "Run belongs to another Owner when the Leader cannot act". When the Leader is asleep or can't act, vanilla puts Run on the first Hero who can act; that Hero's Owner holding Run keeps the escape option with someone who has a menu this turn, and a Leader who can't act shouldn't block the Party. PLAN's M2 wording now states this explicitly.

### M6 review (GPT 6.1 Sol, one pass)
- Bugs, all to a fix agent (m6fix): (1) an unvalidated HELLO from a spoofed endpoint evicts an active client; (2) a delayed BYE from an old connection drops a rejoined client (no connection epoch); (3) the handshake accepts a 256x224 client on a 320x240 Host (layout id isn't a simulation fingerprint), which then desyncs; (4) `netrun.py` exits 0 when neither process ran.
- Rebutted: frame-counter wrap stalls lockstep. It needs ~829 days of one continuous Session at 60 fps; documented as a limitation instead.

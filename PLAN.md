# Co-op plan

Local, then online, multiplayer for the EarthBound C port. This file drives the autonomous build loop: work top to bottom, tick boxes as items pass their gates, and keep `docs/coop-log.md` current.

Vocabulary is in `CONTEXT.md`. Architecture decisions are in `docs/adr/`. Environment setup and harness facts are in `docs/coop-setup.md`.

## Settled decisions

- **Shared World.** One simulation and one screen. No independent exploration (ADR 0002).
- **Ownership.** Heroes are dealt round-robin to Players by join order. A Player walks their Walker, and their other owned members trail behind it. In battle, each Player picks commands for every Hero they own.
- **Absent Hero.** A Player whose Heroes are all out of the Party stands in for a Guest if there is one, and otherwise spectates. Solo Chapters fall out of this rule.
- **Battle input** is sequential, as in the original. Simultaneous input is M7 (built as claimed menus: see the M7 decisions).
- **Online** is input lockstep with a small fixed input delay and no rollback. The Host owns the save, and a joining Player receives a savestate.
- **Windows (M5) waits for the user.** Skip it and continue with M6. Never block on it.

## Working rules

- **Never stop for input.** When a decision is ambiguous, pick the simplest option that fits the settled decisions, record it under "Decisions made during the build" below, and keep going.
- **Delegation.** Delegate implementation, tests and debugging to Opus 5.5 subagents (`model: "opus"`) in auto/full-access mode. You own the architecture, the UX calls and final acceptance, which includes looking at the screenshots yourself.
- **Adversarial review.** Each milestone gets one review from GPT 6.1 Sol (`delegate_task`, provider `codex`, model `gpt-6.1-sol`, `reasoningEffort: "high"`). That is one pass per milestone, never a re-review after fixes. Fix or rebut every finding, and log what you did.
- **Repo rules.** Follow `CLAUDE.md` (uv/.venv, warning flags, the playtest skill, the regress workflow). Its "port faithfully from asm" rule covers vanilla behaviour. Co-op is new behaviour, so write it as clean, well-commented C in new files where possible (`src/coop/`, `port/unix/net/`), and keep the hooks into original code small.
- **Vanilla invariant.** With one Player, the game must be bit-identical to the baseline. `regress.py compare BASE NEW` must show no diffs except the known `bus` case, and `regress.py framehash BASE NEW` must show 0 changed frames. All co-op paths are gated on `coop_player_count() > 1`.
- **Determinism.** Co-op state lives in serialized structs: savestate layout plus `state_layout.h` regeneration. Use only the game RNG, no wall-clock time in game logic, and no uninitialised memory.
- **Commits.** Commit to `coop` after every green item and push to `origin` (the public fork). Never commit the ROM, `playtest/saves`, extracted assets, `asm/bin`, `src/assets` or build output. Use `--no-verify` only per the CLAUDE.md parallel-agent note.
- **When stuck.** After 3 failed attempts on an item, write it under "Blocked" with what you learned, then move to the next item that doesn't depend on it.
- **Baseline binary.** `port/unix/build-base/earthbound` is built from upstream commit d32c421 at the wide viewport. Build it once and never rebuild it from co-op code. The gates compare against `port/unix/build-base-fix` (the same source packed with this fork's ebtools, which fix the bank C3 text remap; see the log).

## Gates (every item)

1. Build `-DEB_WERROR=ON` at both viewports (256x224 and 320x240).
2. `python -m pytest tests -q` passes.
3. `regress.py compare BASE NEW`: vanilla unchanged (the known `bus` diff only). Run `framehash` whenever renderer or camera code changed.
4. Co-op scenario suite: `playtest/coop/run_all.py` is green. Every item adds its acceptance scenarios to the suite before the implementation, and the scenarios assert on STATE/PARTY output, not just "no crash".
5. Run the co-op suite under ASan+UBSan (`build-debug`) at each milestone end.
6. At each milestone end, read a contact sheet of screenshots from the new scenarios and confirm that what's on screen matches what the state output claims.

## M0 Foundation

- [x] `scripts/coop-setup.sh`: idempotent. It creates the venv, installs deps, fetches the 36 story saves if missing (see `docs/coop-setup.md`), and builds base, wide, native and debug. It expects `earthbound.sfc` in the repo root.
- [x] `scripts/coop-gates.sh`: runs gates 1 to 4 and prints a one-line verdict, with `--full` adding gates 5 and 6. It exits non-zero on failure.
- [x] Platform supports four pads.
  - `platform_input_get_pad_n(p)` and `platform_input_get_pad_new_n(p)` for P1 to P4, with the P1 functions unchanged.
  - SDL GameControllers are assigned to Players in connection order.
  - The keyboard stays P1. Add a second keyboard layout for P2 (IJKL movement, U/O for A/B, P for Start, `[` for Select) so co-op can be tested on one Mac with no controllers.
- [x] Input scripts take a per-Player prefix (`P2 10 RIGHT`, `press P3 A`, `until ... P2 ...`). Plain commands still mean P1. Headless STATE prints a `PLAYERS` line with join state, owned Heroes, Walker and position.
- [x] Join model: pressing Start on an unjoined pad joins that Player, and holding Select+Start for 2 seconds leaves. Player count, ownership and Walkers are serialized in savestates. `--players N` is a test flag that auto-joins.
- [x] `playtest/coop/` scenario runner and a first scenario: P2 joins in Ness's bedroom, and the PLAYERS line shows P2 joined with no Heroes owned. While only Ness is in the Party, P2 is a Spectator.

## M1 Overworld

- [x] Ownership and Walkers follow the settled rule and recompute whenever the Party changes (join, leave, unconscious).
- [x] Independent walking.
  - Every Walker moves with the leader's own movement and collision code, covering walls, NPCs, surfaces (water, ladders, stairs) and diagonals.
  - Each Walker has its own position trail, and that Player's other owned members follow it.
  - Members nobody owns follow the Leader, as in vanilla.
- [x] Camera.
  - It follows the midpoint of all Walkers, clamped to the map.
  - A Walker can't move past the visible screen edge minus a small margin (the leash).
  - Use the 320x240 wide view for slack, and make the leash scale with viewport size so 256x224 works too.
- [x] Enemy contact: any Walker touching an overworld enemy starts the battle for the whole Party. First strike is judged against the Walker that was touched.
- [x] Interaction: any Player can press A to talk to or check whatever their Walker faces. The world pauses for everyone while a text box is open, as in vanilla.
- [x] Regrouping.
  - Doors, stairs and screen transitions: when any Walker triggers one, everyone regroups behind the Leader and goes through together.
  - Scripted cutscenes and forced movement do the same. Non-Leader Walkers snap into the Leader's trail while the game controls movement, and get independence back when control returns.
- [x] Scenarios:
  - P2 (Paula) walks away from Ness and is stopped by a wall.
  - The leash stops P2 at the screen edge.
  - P2 touches an enemy and the battle starts.
  - P2 talks to an NPC.
  - P2 enters a door and the whole Party transitions.
  - A cutscene runs with 2 Walkers and both recover.
  - The same checks at 3 and 4 Players.

## M2 Battle

- [x] Command input for each Hero comes from its Owner's pad: command menu, PSI, Goods, target selection.
- [x] Party-wide choices: Run belongs to the Leader's Owner (when the Leader can't act, to the Owner of the first Hero who can, where vanilla puts Run). Auto Fight keeps vanilla behaviour (whole Party), and any Player can cancel it.
- [x] The battle UI shows whose turn it is: a small P1 to P4 tag next to the acting Hero's name. Keep it tiny and pixel-consistent with the game.
- [x] Scenarios: a 2-Player and a 4-Player battle where each Owner's input decides their Hero's command, and the other Players' input is ignored during that menu. Win, flee and game over all exit cleanly.

## M3 Menus and dialogue

- [x] Any Player can open the overworld menu (Goods, PSI, Equip, Check, Status). Whoever opens it controls it until it closes, and the cursor starts on their Walker. No per-Hero restriction: keep it simple.
- [x] Text boxes, yes/no prompts, shops, ATMs, phones (including saving), hotels and Escargo Express are all controlled by whoever started the interaction.
- [x] Scenarios: P2 buys an item, P2 saves at a phone (`save.srm` changes and reloads), P3 uses an item from Goods, and yes/no prompts come from the right pad.

## M4 Party changes and soak

- [x] Stand-in: a Player whose Heroes are all absent walks a Guest when one is present. Guest battle actions stay AI-driven unless giving the Stand-in a command menu is simple.
- [x] Unconscious Heroes trail the Leader as vanilla ghosts, and their Owner's Walker becomes their next owned conscious Hero. If they have none, they spectate until a revive.
- [ ] Solo Chapters (Jeff in Winters, Poo's Mu training, Magicant, Paula's kidnapping) play correctly with 2 to 4 Players joined.
- [ ] Edge cases: the bicycle (joining while Ness rides forces a dismount, or the join is deferred until he dismounts, whichever is simpler), Teleport, Sky Runner, the bus and the taxi with several Walkers. Bicycle and Teleport done (`m4_bicycle_join`, `m4_teleport_3p`); the bus is Blocked (below); Sky Runner untested (no save near it); the taxi doesn't exist.
- [x] Soak: a bot drives P2 to P4 (random walk biased toward the Leader, random menu presses) for 30 or more in-game minutes from every story save. It must not crash, the mode stack must not stay frozen, and there must be no ASan/UBSan reports.
- [ ] Short playtest notes for the user at the top of `docs/coop-log.md`: how to play local co-op on the Mac, and what to look at.

## M5 Windows (user present, skip for now)

- [ ] MinGW-w64 build (apply the Companion-style Windows fixes).
- [ ] The same replay on Mac and Windows produces identical frame hashes.
- [ ] The user does a 10-minute test on their PC.

## M6 Online

- [x] Netcode in `port/unix/net/`.
  - UDP transport. Every packet carries the last K frames of local input for redundancy.
  - Fixed input delay, 3 frames by default, set with `--input-delay`.
  - Up to 4 Players, and a machine may have several local Players (keyboard, IJKL layout, controllers) in one Session. Direct IP and port only: no matchmaking and no NAT traversal (document Tailscale or port forwarding).
- [x] Session flow.
  - `--host PORT` and `--join ADDR:PORT`.
  - A joining Player gets a savestate from the Host at a root-loop boundary, then everyone resumes on the same frame.
  - When a Player disconnects, the others pause for 10 seconds, then continue with that Player left.
- [x] Desync detection: every 60 frames, peers exchange a hash of the serialized game state. On a mismatch, both sides dump a state diff and the session stops with a clear message.
- [x] Headless netplay test harness: 2 to 4 headless processes on localhost behind a Python UDP proxy that injects latency, jitter, loss and reordering.
- [x] Scenarios:
  - A 2-Player session runs 30 game minutes of scripted play with 100 ms of latency, 30 ms of jitter and 2% loss, with zero desyncs.
  - A Player joins mid-game and the session stays in sync.
  - A Player disconnects and rejoins.
  - The same session at 4 Players.
- [x] `docs/coop-online.md`: how to host and join.

## M7 Polish

- [x] Simultaneous battle input: every Player picks their Heroes' commands at the same time, and the turn starts when all are locked in. Vanilla order is preserved when one Player owns several Heroes.
- [ ] Solo Chapter Companion (CONTEXT.md): Spectators walk a Mr. Saturn (existing overworld sprite) during Solo Chapters. Overworld only, sits out battles. A Companion can trigger Look-only interactions (static scan of the text script); anything else plays a Mr. Saturn sound with no text. On by default, no flag.
- [x] Battle rotation in Solo Chapters: the solo Hero's command menu goes to its Owner, then each Spectator in join order, one turn each.

## Decisions made during the build

- Controllers are assigned to the first free Player slot in connection order; the first controller is P1 together with the keyboard, the IJKL layout is P2 together with the second controller. Headless runs never open controllers. (M0)
- Joins persist across new games and file loads within a process; a savestate load replaces them with the savestate's. (M0)
- Ownership is dealt by join order, not by Player number. Walkers are derived (not stored) from ownership plus the Party. (M0)
- Savestate format stays v16; the new SECTION_COOP changes `layout_id`, which already rejects old slots. (M0)
- Every absent Player (no Hero in the Party) gets a Stand-in Guest if one is free, else the Companion, not only in Solo Chapters; a Player whose Heroes are all KO'd is a plain Spectator. Bicycle: no forced dismount (a join never changes the Party). The taxi doesn't exist as a ride; dropped. (M4/M7 research, docs/coop-design/party-changes.md)
- Solo Chapters: Mr. Saturn Companion with Look-only interactions plus Battle rotation, both shipped on by default; Claude owns testing and sign-off. (user, 2026-10-26)
- Local and online co-op are both first-class, including mixed (several local Players on one machine in an online Session). Claude owns all testing and should improve the test loop when it finds gaps. (user, 2026-10-26)
- Co-op join edges use co-op's own serialized pad history; capture-unwind frames are invisible to co-op. (M0 review)
- Design memos for input focus (M2/M3) and Walkers (M1) are in `docs/coop-design/`. (M0)
- A Walker must be able to walk: unconscious and diamondized Heroes are skipped, as vanilla's party sort does. (M1)
- core.pad1 follows the Leader's Owner during overworld play only (P1 on title, file select, boot and in battle until M2), with `memory_rebase_joypad` on every switch. Menus opened by that Player still read P1's platform pad directly (window.c etc.): M3. (M1)
- Levels of "not free": a window, text box or interaction pauses non-Leader Walkers (they hold their spot); so do an enemy touch, the swirl and the battle (chains stay independent, so everyone is back where they stood afterwards). When the game controls movement (camera_mode, stairs, escalator, bicycle, door, teleport, demo, a frozen or scripted Leader) chains hold until the game actually moves the Leader, then snap and regroup into vanilla formation on the Leader's trail; a screen transition's fade-out regroups everyone (entities are frozen by then). So a door's text or a scripted pause doesn't pull anyone onto the Leader. (M1)
- Trails: the memo's shadow `position_index` is kept (every independent chain member's index equals its Party predecessor's), so snapping is just "stop overriding". Unsnapping lays the chain's trail as straight segments through the members' current positions at vanilla spacing instead of copying the Leader's ring, so it is seamless wherever the members stand. Any chain change (join, leave, KO, revive, party change) snaps and unsnaps. (M1)
- Camera = centre of the Walkers' bounding box (the Leader plus independent Walkers), not their mean: the box centre keeps everyone within half the spread, so one spread cap is exactly the on-screen guarantee at any Player count. No map clamp: vanilla's CENTER_SCREEN has none, and the midpoint never shows further past an edge than vanilla would with either Walker leading. (M1)
- Leash: a step (the Leader's too) that would widen the Walkers' spread past viewport - 2 x viewport/8 on an axis is reverted on that axis, so every Walker stays viewport/8 inside the view (40/30 px at 320x240, 32/28 at 256x224). (M1)
- Camera transitions ease (offset decays by a quarter plus a pixel per frame, ~12 frames from a screen away; a jump bigger than a screen cuts) between the midpoint and vanilla Leader-following, and from a view another routine set (the reload after a battle) back to the midpoint. While following the Leader, a view set by a door, teleport or script is left alone, as vanilla. (M1)
- First strike: a Hero of another Player than the Leader's Owner (their Walker or its chain) is judged by its own facing; during the 12-frame touch shake each independent chain turns with its own Player's pad. (M1)
- Input focus (`src/coop/coop_input.{h,c}`) replaces M1's pad feed: P1 outside overworld play, the Leader's Owner on the overworld, the lock holder while locked, ALL in battle. Only a Player with a Walker can take the lock (a Spectator has nobody to talk from). (M3)
- Capture-eligible = the harness idle predicate plus no window open, no queued interaction or demo, and the Leader not on the bicycle. So the bicycle dismount (A/L) and anything else that only works while riding stay with the Leader's Owner; nothing else special-cases Leader-only presses. (M3)
- While someone else has the focus, the Leader's step reads only its Owner's held pad (no presses). Without it, the locker's d-pad turned and moved Ness for 1 frame on the frame the menu closed. (M3)
- Talk to / Check search from the focused Player's Walker only while it walks independently; a Walker that is snapped onto the Leader's trail searches from the Leader, as vanilla. Scripted text still names the Leader ("Ness picked up the receiver"). (M3)
- "Who?" cursors (Goods, PSI if the Hero can use PSI, Equip, Status, and the text-script party select such as a shop's "Which of you will carry this?") start on the focused Walker. "Whom?" target selects keep vanilla's start. (M3)
- Whoever starts an interaction drives all of it, saving at a phone included, though CONTEXT.md lists saving as a Leader action: the lock is simpler than a per-action rule, and the save is party-wide anyway. (M3)
- Battle focus is ALL for the whole battle until M2 moves it per Hero with `coop_set_focus()`. (M3)
- Run Away goes with the turn's first command menu, as in vanilla, so its Hero's Owner picks it. That is the Leader's Owner unless the Leader can't act (asleep, solidified, ...); then the first Hero who can act carries Run Away and Auto Fight, and its Owner picks them. No special rule. (M2)
- Battle focus is per phase: the Hero's Owner from `BTL_MENU_SELECT` to `BTL_MENU_DECIDE`, ALL in every other phase. Between two command menus there are 1-2 ALL frames where presses do nothing. During Auto Fight the focus still visits each Owner on those menu frames; B is read at text pushes under ALL, so any Player cancels it. (M2)
- A Spectator gets no command menu until Battle rotation (a later item): in a Solo Chapter battle the solo Hero's Owner picks every command, and the Spectator only advances text. (M2)
- The turn tag is the Owner's pad number in the title's tiny font after a space ("Paula P2"), co-op only. With custom 5-letter names it is still 8 glyphs, well inside the 16-tile title slot and the narrowest (Jeff) window. (M2)
- Stand-in: a Stand-in's chain is its Guest alone; Bubble Monkey's own tick counts as a follower tick, and his chain snaps while he is off on his own (`bubble_monkey_mode != 0`). A Guest that leads (every Hero unconscious) belongs to its Stand-in, or to P1 if nobody stands in for it. PSI Teleport (which swaps the party's ticks, so co-op's tick doesn't run) regroups the Party when it takes the ticks. (M4)
- A join or leave while a chain walks regroups the whole Party behind the Leader on the next frame outside a battle, then the new chains unsnap. After the last other Player leaves, co-op keeps the camera until it has eased back to the Leader; a session that never had co-op never runs any of it. A leashed step slides along the leash only if the position left is clear of walls and NPCs, else it is rejected whole. (M1 review)
- Battle rotation applies to every battle with exactly one Hero in the Party and more than one Player (so early Onett too, not only story Solo Chapters). The rotation is the Owner, then every other joined Player in join order (all of them are absent then). `CoopState.rotation` counts such turns, advanced in `btl_start_turn`, so a turn whose menu is skipped (asleep, enemy-first surprise) still uses up that Player's turn, and the count carries across battles and savestates. The menu's Player gets the focus, the tag and Run Away. (M7)
- Simultaneous battle input is built as claimed menus, first come first served: a turn's command menus open in the order Players press A for them, one at a time (one mode stack, global menu state, and four command windows don't fit at 256 px). A press while another Player's menu is open queues for the next one. A claim opens the claimer's first unchosen Hero (vanilla order within a Player). No claim is needed when only one Player has Heroes left (a Party owned by one Player, Solo Chapters, the last menus of a turn) or during Auto Fight: menus then open by themselves in Party order. While the battle waits, the PSI-name box at the top lists who may claim ("P1  P2"). (M7)
- Run Away and Auto Fight stay with the Leader's Owner (the settled M2 rule): they are on the Leader's command menu, or, when the Leader can't act, on the first Hero who can act (vanilla's placement), whatever order the menus are claimed in, even if others have already chosen. Picking Run discards the turn's other choices, as the remaining Heroes skip after a vanilla Run. Under Battle rotation they stay with whoever holds the solo Hero's menu. B goes back to the same Player's previous Hero this turn (un-choosing it), or reopens their menu at their first one; it never reopens another Player's choice. (M7)
- In the co-op menu loop, members who can't act get vanilla's BACT_NO_EFFECT when nobody is left to choose, instead of interleaved with the menus (nothing reads the order). A turn started in co-op keeps the claimed loop to its end even if Players leave meanwhile, so no Hero is skipped. (M7)
- The battle focus is derived every frame from the battle routine's serialized state (phase and menu slot in the mode stack), not requested by battle code, so a join or leave under an open menu or its children moves it at once; the tag is reconciled every frame too. (M2 review)

## Blocked

- **Bus (M4 edge case).** The Runaway Five bus never starts, in solo too (the known regress `bus` case): `earthbound.yml` names the C3 script bank `bank_c3_scripts_combined`, but `ebtools/cli/extract.py` still maps `events/bank_c3_scripts.bin` to `locale/events/bank_c3_scripts.json`, so that JSON is never written and `pack_all` skips the text-address remap for every C3 event script. EVENT_181 (`asm/data/events/scripts/181.asm`) then queues the raw ROM pointer 0xC79B98 and `resolve_text_addr` returns NULL. Fixing it means changing extract/pack and re-extracting the shared assets in the main checkout, which this agent must not touch. `m4_bus_2p` waits for that fix.

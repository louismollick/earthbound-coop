# Co-op plan

Local, then online, multiplayer for the EarthBound C port. This file drives the autonomous build loop: work top to bottom, tick boxes as items pass their gates, and keep `docs/coop-log.md` current.

Vocabulary is in `CONTEXT.md`. Architecture decisions are in `docs/adr/`. Environment setup and harness facts are in `docs/coop-setup.md`.

## Settled decisions

- **Shared World.** One simulation and one screen. No independent exploration (ADR 0002).
- **Ownership.** Heroes are dealt round-robin to Players by join order. A Player walks their Walker, and their other owned members trail behind it. In battle, each Player picks commands for every Hero they own.
- **Absent Hero.** A Player whose Heroes are all out of the Party stands in for a Guest if there is one, and otherwise spectates. Solo Chapters fall out of this rule.
- **Battle input** is sequential, as in the original. Simultaneous input is M7.
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
- **Baseline binary.** `port/unix/build-base/earthbound` is built from upstream commit d32c421 at the wide viewport. Build it once and never rebuild it from co-op code.

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

- [ ] Ownership and Walkers follow the settled rule and recompute whenever the Party changes (join, leave, unconscious).
- [ ] Independent walking.
  - Every Walker moves with the leader's own movement and collision code, covering walls, NPCs, surfaces (water, ladders, stairs) and diagonals.
  - Each Walker has its own position trail, and that Player's other owned members follow it.
  - Members nobody owns follow the Leader, as in vanilla.
- [ ] Camera.
  - It follows the midpoint of all Walkers, clamped to the map.
  - A Walker can't move past the visible screen edge minus a small margin (the leash).
  - Use the 320x240 wide view for slack, and make the leash scale with viewport size so 256x224 works too.
- [ ] Enemy contact: any Walker touching an overworld enemy starts the battle for the whole Party. First strike is judged against the Walker that was touched.
- [ ] Interaction: any Player can press A to talk to or check whatever their Walker faces. The world pauses for everyone while a text box is open, as in vanilla.
- [ ] Regrouping.
  - Doors, stairs and screen transitions: when any Walker triggers one, everyone regroups behind the Leader and goes through together.
  - Scripted cutscenes and forced movement do the same. Non-Leader Walkers snap into the Leader's trail while the game controls movement, and get independence back when control returns.
- [ ] Scenarios:
  - P2 (Paula) walks away from Ness and is stopped by a wall.
  - The leash stops P2 at the screen edge.
  - P2 touches an enemy and the battle starts.
  - P2 talks to an NPC.
  - P2 enters a door and the whole Party transitions.
  - A cutscene runs with 2 Walkers and both recover.
  - The same checks at 3 and 4 Players.

## M2 Battle

- [ ] Command input for each Hero comes from its Owner's pad: command menu, PSI, Goods, target selection.
- [ ] Party-wide choices: Run belongs to the Leader's Owner. Auto Fight keeps vanilla behaviour (whole Party), and any Player can cancel it.
- [ ] The battle UI shows whose turn it is: a small P1 to P4 tag next to the acting Hero's name. Keep it tiny and pixel-consistent with the game.
- [ ] Scenarios: a 2-Player and a 4-Player battle where each Owner's input decides their Hero's command, and the other Players' input is ignored during that menu. Win, flee and game over all exit cleanly.

## M3 Menus and dialogue

- [ ] Any Player can open the overworld menu (Goods, PSI, Equip, Check, Status). Whoever opens it controls it until it closes, and the cursor starts on their Walker. No per-Hero restriction: keep it simple.
- [ ] Text boxes, yes/no prompts, shops, ATMs, phones (including saving), hotels and Escargo Express are all controlled by whoever started the interaction.
- [ ] Scenarios: P2 buys an item, P2 saves at a phone (`save.srm` changes and reloads), P3 uses an item from Goods, and yes/no prompts come from the right pad.

## M4 Party changes and soak

- [ ] Stand-in: a Player whose Heroes are all absent walks a Guest when one is present. Guest battle actions stay AI-driven unless giving the Stand-in a command menu is simple.
- [ ] Unconscious Heroes trail the Leader as vanilla ghosts, and their Owner's Walker becomes their next owned conscious Hero. If they have none, they spectate until a revive.
- [ ] Solo Chapters (Jeff in Winters, Poo's Mu training, Magicant, Paula's kidnapping) play correctly with 2 to 4 Players joined.
- [ ] Edge cases: the bicycle (joining while Ness rides forces a dismount, or the join is deferred until he dismounts, whichever is simpler), Teleport, Sky Runner, the bus and the taxi with several Walkers.
- [ ] Soak: a bot drives P2 to P4 (random walk biased toward the Leader, random menu presses) for 30 or more in-game minutes from every story save. It must not crash, the mode stack must not stay frozen, and there must be no ASan/UBSan reports.
- [ ] Short playtest notes for the user at the top of `docs/coop-log.md`: how to play local co-op on the Mac, and what to look at.

## M5 Windows (user present, skip for now)

- [ ] MinGW-w64 build (apply the Companion-style Windows fixes).
- [ ] The same replay on Mac and Windows produces identical frame hashes.
- [ ] The user does a 10-minute test on their PC.

## M6 Online

- [ ] Netcode in `port/unix/net/`.
  - UDP transport. Every packet carries the last K frames of local input for redundancy.
  - Fixed input delay, 3 frames by default, set with `--input-delay`.
  - Up to 4 Players. Direct IP and port only: no matchmaking and no NAT traversal (document Tailscale or port forwarding).
- [ ] Session flow.
  - `--host PORT` and `--join ADDR:PORT`.
  - A joining Player gets a savestate from the Host at a root-loop boundary, then everyone resumes on the same frame.
  - When a Player disconnects, the others pause for 10 seconds, then continue with that Player left.
- [ ] Desync detection: every 60 frames, peers exchange a hash of the serialized game state. On a mismatch, both sides dump a state diff and the session stops with a clear message.
- [ ] Headless netplay test harness: 2 to 4 headless processes on localhost behind a Python UDP proxy that injects latency, jitter, loss and reordering.
- [ ] Scenarios:
  - A 2-Player session runs 30 game minutes of scripted play with 100 ms of latency, 30 ms of jitter and 2% loss, with zero desyncs.
  - A Player joins mid-game and the session stays in sync.
  - A Player disconnects and rejoins.
  - The same session at 4 Players.
- [ ] `docs/coop-online.md`: how to host and join.

## M7 Polish

- [ ] Simultaneous battle input: every Player picks their Heroes' commands at the same time, and the turn starts when all are locked in. Vanilla order is preserved when one Player owns several Heroes.
- [ ] Solo Chapter companion: a small cat, using an existing cat overworld sprite from the ROM, that Spectators walk during Solo Chapters. It is overworld-only and sits out battles. Gate it behind `--coop-cat` until the user signs off.

## Decisions made during the build

- Controllers are assigned to the first free Player slot in connection order; the first controller is P1 together with the keyboard, the IJKL layout is P2 together with the second controller. Headless runs never open controllers. (M0)
- Joins persist across new games and file loads within a process; a savestate load replaces them with the savestate's. (M0)
- Ownership is dealt by join order, not by Player number. Walkers are derived (not stored) from ownership plus the Party. (M0)
- Savestate format stays v16; the new SECTION_COOP changes `layout_id`, which already rejects old slots. (M0)
- Co-op join edges use co-op's own serialized pad history; capture-unwind frames are invisible to co-op. (M0 review)
- Design memos for input focus (M2/M3) and Walkers (M1) are in `docs/coop-design/`. (M0)

## Blocked

(append here)

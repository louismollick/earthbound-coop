#ifndef EB_COOP_COOP_INPUT_H
#define EB_COOP_COOP_INPUT_H

/*
 * Local co-op input focus (M1 Interaction, M3 menus; design in
 * docs/coop-design/input-focus.md, vocabulary in CONTEXT.md).
 *
 * The game has one pad, core.pad1. In co-op the focus decides whose pad that
 * is: one Player (P1..P4 = 0..3) or COOP_FOCUS_ALL (the OR of every joined
 * Player's pad). The host applies the focus once per frame, before
 * memory_update_joypad, and rebases the pad state on every switch
 * (memory_rebase_joypad), so a switch never makes a phantom press or an
 * instant autorepeat. Game code that reads the platform's new presses directly
 * reads coop_pad_new() instead.
 *
 * Who has the focus:
 * - Title, file select, boot, game-over reboot: P1.
 * - Overworld, unlocked: the Leader's Owner (it walks the Leader).
 * - Overworld lock: on a capture-eligible frame (the Party idle, no window
 *   open), the lowest-numbered Player with a Walker who newly presses A, L, X,
 *   B or SELECT takes the lock. The focus moves to them before the overworld's
 *   input check runs, so that same press opens the pause menu, Check, the town
 *   map or the HP/PP window exactly as in vanilla, and they drive every menu,
 *   text box, yes/no prompt, shop, phone or save that follows. The lock is
 *   released on the first frame the Party is idle again. While someone else
 *   holds the lock, the Leader's step still reads only its Owner's pad
 *   (coop_leader_pad_enter/leave).
 * - Battle: entering a battle clears the lock and sets the focus to ALL;
 *   battle code then moves it with coop_set_focus: each Hero's command menu
 *   is its Owner's, everything else is ALL (coop_battle.h).
 *
 * Every hook is gated on coop_player_count() > 1, so solo play is vanilla:
 * the feed isn't called and coop_pad_new() is platform_input_get_pad_new().
 * The state lives in the serialized CoopState (coop.h).
 */

#include "core/types.h"
#include "include/pad.h"
#include "platform/platform.h"

#define COOP_FOCUS_ALL PLATFORM_MAX_PLAYERS /* the OR of every joined Player's pad */

/* Buttons that take the overworld lock: A (pause menu), L (Check/Talk),
 * X (town map), B and SELECT (HP/PP window). */
#define COOP_CAPTURE_BUTTONS (PAD_A | PAD_L | PAD_X | PAD_B | PAD_SELECT)

/* Battle code (coop_battle.c): ask for the focus to move to Player `focus` (0-3) or to
 * COOP_FOCUS_ALL. The host applies it on its next frame, with a rebase. Only
 * consulted during a battle (outside one the overworld lock owns the focus);
 * battle entry resets it to ALL. An unjoined Player means ALL. */
void coop_set_focus(int focus);

/* The focus that feeds core.pad1 now: a Player 0-3 or COOP_FOCUS_ALL. */
int coop_focus(void);

/* True while a Player holds the overworld lock. */
bool coop_focus_locked(void);

/* Host, once per frame between platform_input_poll and memory_update_joypad
 * (co-op, or while the focus isn't P1 yet): decide the focus, rebase on a
 * switch, compute the focused new presses for coop_pad_new(), and return the
 * pad for core.pad1. `p1_pad` is P1's platform pad. On a capture-unwind frame
 * nobody can take the lock and coop_pad_new() is 0. */
uint16_t coop_input_feed(uint16_t p1_pad, bool unwinding);

/* The new presses of the focused pad this frame: every game-code site that
 * used platform_input_get_pad_new() (menus, battle targeting, title, file
 * select, ...). In co-op the edges come from the serialized pad history
 * (CoopState.prev_held), not the platform's; in solo this is exactly
 * platform_input_get_pad_new(). */
uint16_t coop_pad_new(void);

/* Hook, update_leader_movement around the Leader's step: while another Player
 * holds the focus, core.pad1_held is the Leader's Owner's pad (no presses), so
 * a capturing Player's d-pad never steers the Leader. Co-op only. */
void coop_leader_pad_enter(void);
void coop_leader_pad_leave(void);

/* Talk to / Check (pause menu and the L button): run `fn` (talk_to or
 * check_action) searching from the focused Player's Walker instead of the
 * Leader (position, direction, hitbox entity), so the NPC faces that Walker.
 * The Walker turns to face what it found, as the Leader does. In solo, or for
 * a Walker that is the Leader or trails it, this is just fn(). */
uint32_t coop_interact(uint32_t (*fn)(void));

/* char_select_make_init: the starting cursor of an overworld "Who?" select
 * (Goods, PSI, Equip, Status). In co-op it's the focused Player's Walker; for
 * PSI only if that Hero passes the PSI check. Anything else keeps `index`. */
uint16_t coop_char_select_index(uint16_t index, uint16_t mode, uint8_t check_valid_id);

#endif /* EB_COOP_COOP_INPUT_H */

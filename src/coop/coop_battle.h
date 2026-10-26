#ifndef EB_COOP_COOP_BATTLE_H
#define EB_COOP_COOP_BATTLE_H

/*
 * Local co-op in battle (M2; vocabulary in CONTEXT.md, input model in
 * coop_input.h).
 *
 * Command input is sequential, as in vanilla. While a Hero's command menu is
 * up (the battle routine's BTL_MENU_SELECT .. BTL_MENU_DECIDE phases), the
 * focus is that Hero's Owner, so the command menu, Goods, PSI, the "Whom?"
 * ally select and the enemy target select all read only the Owner's pad.
 * Everywhere else in a battle the focus is ALL: any Player advances text, and
 * any Player can cancel Auto Fight by holding B (battle_push_text_ex).
 *
 * Party-wide choices fall out of vanilla: Run Away and Auto Fight sit only on
 * the turn's first command menu, so they belong to that Hero's Owner, normally
 * the Leader's (if the Leader can't act, the first Hero who can carries them).
 *
 * The command window's title carries the Owner's tag ("Paula P2"). No state
 * of its own: the focus request lives in CoopState (coop.h). Every hook is
 * gated on coop_player_count() > 1.
 */

#include "core/types.h"

/* Hook, top of every mode_step_battle iteration: request the focus for the
 * battle routine's `phase` (BattleRoutinePhase) with `party_slot` its menu
 * loop index: the Owner of that slot's Hero during its command menu, else
 * ALL. Co-op only. */
void coop_battle_focus(uint8_t phase, uint16_t party_slot);

/* Hook, bm_build_menu: append the Owner's tag to the command window title
 * `name` (Hero `char_id`, 1-4; buffer of `size` bytes) and return the title's
 * new length for set_window_title. Co-op only. */
int coop_battle_title(char *name, int size, uint8_t char_id);

#endif /* EB_COOP_COOP_BATTLE_H */

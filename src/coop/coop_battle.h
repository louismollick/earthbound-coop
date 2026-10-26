#ifndef EB_COOP_COOP_BATTLE_H
#define EB_COOP_COOP_BATTLE_H

/*
 * Local co-op in battle (M2, M7; vocabulary in CONTEXT.md, input model in
 * coop_input.h).
 *
 * Command input is sequential, as in vanilla. While a Hero's command menu is
 * up (the battle routine's BTL_MENU_SELECT .. BTL_MENU_DECIDE phases), the
 * focus is that menu's Player (coop_battle_menu_player), so the command menu,
 * Goods, PSI, the "Whom?" ally select and the enemy target select all read only
 * that Player's pad. Everywhere else in a battle the focus is ALL: any Player
 * advances text, and any Player can cancel Auto Fight by holding B
 * (battle_push_text_ex). The host derives the focus every frame from the
 * battle routine's serialized state (its phase and menu slot in the mode
 * stack), and re-tags the open command window, so a join or leave that hands
 * an open menu, or its PSI/Goods/target child, to another Owner takes effect
 * on the next frame.
 *
 * A menu's Player is the Hero's Owner, except in a Solo Chapter battle (exactly
 * one Hero in the Party, more than one Player joined): there Battle rotation
 * hands the solo Hero's menu to its Owner, then to each other Player (all of
 * them absent) in join order, one turn each, round and round. The rotation
 * counter is serialized and advances once per turn (btl_start_turn), so back
 * and cancel never move it and it carries across battles: short battles still
 * reach every Player.
 *
 * Party-wide choices fall out of vanilla: Run Away and Auto Fight sit only on
 * the turn's first command menu, so they belong to that menu's Player.
 *
 * The command window's title carries the menu Player's tag ("Paula P2"). Every
 * hook is gated on coop_player_count() > 1; the state is in CoopState (coop.h).
 */

#include "core/types.h"

/* coop_input_feed, every co-op frame in a battle: the focus the battle
 * routine's state calls for: the menu Player of the Hero whose command menu is
 * up (a Player 0-3), else COOP_FOCUS_ALL. */
int coop_battle_focus(void);

/* coop_input_feed, every co-op frame in a battle: if a command window is open,
 * make its title tag name the menu's Player now (after a join or leave). */
void coop_battle_retitle(void);

/* Hook, btl_start_turn: a new turn; advances Battle rotation in a Solo Chapter
 * battle. Co-op only. */
void coop_battle_start_turn(void);

/* The Player (0-3) who picks Hero `char_id`'s (1-4) command this turn: the
 * Battle rotation's Player in a Solo Chapter battle, else the Hero's Owner. */
int coop_battle_menu_player(uint8_t char_id);

/* Hook, bm_build_menu: append the menu Player's tag to the command window
 * title `name` (Hero `char_id`, 1-4; buffer of `size` bytes) and return the
 * title's new length for set_window_title. Co-op only. */
int coop_battle_title(char *name, int size, uint8_t char_id);

#endif /* EB_COOP_COOP_BATTLE_H */

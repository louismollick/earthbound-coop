#ifndef EB_COOP_COOP_BATTLE_H
#define EB_COOP_COOP_BATTLE_H

/*
 * Local co-op in battle (M2, M7; vocabulary in CONTEXT.md, input model in
 * coop_input.h).
 *
 * Menu Player. Every Hero's command menu belongs to one Player
 * (coop_battle_menu_player): its Owner, except in a Solo Chapter battle
 * (exactly one Hero in the Party, more than one Player joined), where Battle
 * rotation hands the solo Hero's menu to its Owner, then to each other Player
 * (all of them absent) in join order, one turn each, round and round. The
 * rotation counter advances once per turn (btl_start_turn), so back and cancel
 * never move it and it carries across battles: short battles still reach
 * every Player.
 *
 * Claimed menus (simultaneous input). The command menus of a turn open in the
 * order Players claim them, not in Party order: no menu opens until a Player
 * with a Hero left to choose for presses A (the claim wait; the PLAYERS line
 * shows "choose=P1,P2"), and an A press while another Player's menu is open
 * queues that Player for the next menu, so a ready Player never waits on a
 * slow one for more than the menu already open. A claim opens the claimer's
 * first unchosen Hero, so each Player's own Heroes keep vanilla order. When
 * only one Player has Heroes left (one Player owns the whole Party, a Solo
 * Chapter, the last menus of a turn) and during Auto Fight, menus open by
 * themselves in Party order, as vanilla. Initiative, not menu order, decides
 * who acts first (btl_find_attacker). B goes back to the same Player's
 * previous Hero this turn, or reopens the menu at their first one; it never
 * reopens another Player's choice. Run Away and Auto Fight stay on the
 * turn's first menu (vanilla's num_selected == 0), so whoever claims first
 * holds them.
 *
 * Focus. While a command menu is up (the battle routine's BTL_MENU_SELECT ..
 * BTL_MENU_DECIDE phases), the focus is that menu's Player, so the command
 * menu, Goods, PSI, the "Whom?" ally select and the enemy target select read
 * only that Player's pad. Everywhere else in a battle (the claim wait
 * included) the focus is ALL: any Player advances text, and any Player can
 * cancel Auto Fight by holding B (battle_push_text_ex). The host derives the
 * focus every frame from the battle routine's serialized state (its phase and
 * menu slot in the mode stack), and re-tags the open command window, so a join
 * or leave that hands an open menu, or its PSI/Goods/target child, to another
 * Owner takes effect on the next frame.
 *
 * The command window's title carries the menu Player's tag ("Paula P2"). Every
 * hook is gated on coop_player_count() > 1 (the menu loop hooks on
 * coop_battle_claiming(), which only a co-op turn sets); all state is in
 * CoopState (coop.h).
 */

#include "core/mode_stack.h"
#include "core/types.h"
#include "platform/platform.h"

/* coop_input_feed, every co-op frame in a battle: the focus the battle
 * routine's state calls for: the menu Player of the Hero whose command menu is
 * up (a Player 0-3), else COOP_FOCUS_ALL. */
int coop_battle_focus(void);

/* coop_input_feed, every co-op frame in a battle: if a command window is open,
 * make its title tag name the menu's Player now (after a join or leave). */
void coop_battle_retitle(void);

/* coop_input_feed, every co-op frame in a battle, after the focus is decided:
 * during the turn's menu loop, queue each joined Player who newly pressed A
 * (`pressed`) and doesn't hold the open menu (`focus`) for the next menu. */
void coop_battle_note_claims(const uint16_t pressed[PLATFORM_MAX_PLAYERS], int focus);

/* Hook, btl_start_turn: a new turn. Advances Battle rotation in a Solo
 * Chapter battle and starts claiming this turn's menus. Co-op only. */
void coop_battle_start_turn(void);

/* The turn's command menus are being claimed: the battle's menu loop runs the
 * co-op body and back (btl_step_menu_body_coop, btl_step_menu_decide). Stays
 * set to the end of the loop even if Players leave meanwhile. */
bool coop_battle_claiming(void);

/* Whether party slot `slot` already has a command chosen this turn (it is in
 * the battle's selection stack). */
bool coop_battle_chosen(const BattleRoutineState *st, uint16_t slot);

/* The co-op menu loop: `pending` (bit = party slot) are the Heroes who can
 * act and have no command yet. Returns the slot whose menu opens now, or -1
 * to wait a frame for a claim. */
int coop_battle_claim(uint8_t pending);

/* The co-op menu loop found nothing left to choose: stop claiming. */
void coop_battle_menus_done(void);

/* Hook, btl_step_menu_decide on B: go back to this menu Player's previous
 * Hero this turn (un-choosing it), or reopen this menu at their first one. */
void coop_battle_back(BattleRoutineState *st);

/* While the battle waits for a claim: bit p set if Player p may claim
 * (has a Hero left to choose for); else 0. For the harness and the HUD. */
uint8_t coop_battle_choosers(void);

/* The Player (0-3) who picks Hero `char_id`'s (1-4) command this turn: the
 * Battle rotation's Player in a Solo Chapter battle, else the Hero's Owner. */
int coop_battle_menu_player(uint8_t char_id);

/* Hook, bm_build_menu: append the menu Player's tag to the command window
 * title `name` (Hero `char_id`, 1-4; buffer of `size` bytes) and return the
 * title's new length for set_window_title. Co-op only. */
int coop_battle_title(char *name, int size, uint8_t char_id);

#endif /* EB_COOP_COOP_BATTLE_H */

/*
 * Local co-op in battle. See coop_battle.h.
 */
#include "coop/coop_battle.h"

#include <stdio.h>
#include <string.h>

#include "coop/coop.h"
#include "coop/coop_input.h"
#include "core/mode_stack.h"
#include "game/game_state.h"

/* The phases from choosing a Hero's menu to acting on its result (SELECT and
 * OPEN wait a frame each before the menu reads input, so the host has applied
 * the new focus by then). */
static bool menu_phase(uint8_t phase) {
    switch ((BattleRoutinePhase)phase) {
    case BTL_MENU_SELECT:
    case BTL_MENU_OPEN:
    case BTL_MENU_RESULT:
    case BTL_MENU_CLOSE:
    case BTL_MENU_DECIDE:
        return true;
    default:
        return false;
    }
}

void coop_battle_focus(uint8_t phase, uint16_t party_slot) {
    uint8_t hero = party_slot < TOTAL_PARTY_COUNT ? game_state.party_members[party_slot] : 0;
    if (menu_phase(phase) && hero >= 1 && hero <= COOP_HERO_COUNT)
        coop_set_focus(coop_hero_owner(hero - 1));
    else
        coop_set_focus(COOP_FOCUS_ALL);
}

int coop_battle_title(char *name, int size, uint8_t char_id) {
    int len = (int)strlen(name);
    if (char_id >= 1 && char_id <= COOP_HERO_COUNT)
        snprintf(name + len, (size_t)(size - len), " P%d", coop_hero_owner(char_id - 1) + 1);
    return (int)strlen(name);
}

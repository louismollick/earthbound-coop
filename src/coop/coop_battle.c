/*
 * Local co-op in battle. See coop_battle.h.
 */
#include "coop/coop_battle.h"

#include <stdio.h>
#include <string.h>

#include "coop/coop.h"
#include "coop/coop_input.h"
#include "core/mode_stack.h"
#include "game/battle.h"
#include "game/game_state.h"
#include "game/window.h"
#include "game/text.h"

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

/* A Solo Chapter battle: exactly one Hero (conscious or not) in the Party, and
 * more than one Player, so everyone but its Owner is absent. */
static bool solo_chapter_battle(void) {
    int heroes = 0;
    for (int i = 0; i < TOTAL_PARTY_COUNT; i++) {
        uint8_t id = game_state.party_members[i];
        if (id >= 1 && id <= COOP_HERO_COUNT)
            heroes++;
    }
    return heroes == 1 && coop_player_count() > 1;
}

int coop_battle_menu_player(uint8_t char_id) {
    int owner = coop_hero_owner(char_id - 1);
    if (!solo_chapter_battle())
        return owner;
    /* This turn's place in the rotation: the Owner, then the others in join order */
    int n = coop_player_count();
    int k = (coop.rotation ? coop.rotation - 1 : 0) % n;
    for (int i = 0; i < n && k > 0; i++) {
        int p = coop.join_order[i];
        if (p != owner && --k == 0)
            return p;
    }
    return owner;
}

void coop_battle_start_turn(void) {
    if (solo_chapter_battle())
        coop.rotation++;
}

/* The live state of the innermost mode `mode` on the stack, or NULL. */
static ModeState *mode_state(GameMode mode) {
    for (int i = g_mode_stack.depth - 1; i >= 0; i--)
        if (g_mode_stack.mode[i] == mode)
            return &g_mode_stack.state[i];
    return NULL;
}

int coop_battle_focus(void) {
    ModeState *ms = mode_state(GAME_MODE_BATTLE);
    if (!ms || !menu_phase(ms->battle.phase) || ms->battle.party_slot >= TOTAL_PARTY_COUNT)
        return COOP_FOCUS_ALL;
    uint8_t hero = game_state.party_members[ms->battle.party_slot];
    if (hero < 1 || hero > COOP_HERO_COUNT)
        return COOP_FOCUS_ALL;
    int p = coop_battle_menu_player(hero);
    return coop_player_joined(p) ? p : COOP_FOCUS_ALL;
}

int coop_battle_title(char *name, int size, uint8_t char_id) {
    int len = (int)strlen(name);
    if (char_id >= 1 && char_id <= COOP_HERO_COUNT)
        snprintf(name + len, (size_t)(size - len), " P%d", coop_battle_menu_player(char_id) + 1);
    return (int)strlen(name);
}

void coop_battle_retitle(void) {
    ModeState *ms = mode_state(GAME_MODE_BATTLE_MENU);
    if (!ms || ms->battle_menu.phase == BM_ENTER)
        return; /* no command window built yet */
    uint8_t char_id = (uint8_t)ms->battle_menu.char_id;
    WindowInfo *w = get_window(battle_menu_window_id(ms->battle_menu.window_index));
    if (!w || char_id < 1 || char_id > COOP_HERO_COUNT)
        return;
    /* As bm_build_menu: the Hero's name (5 letters at most), then the tag */
    char title[WINDOW_TITLE_SIZE];
    int j;
    for (j = 0; j < 5 && party_characters[char_id - 1].name[j]; j++)
        title[j] = eb_char_to_ascii(party_characters[char_id - 1].name[j]);
    title[j] = '\0';
    int len = coop_battle_title(title, (int)sizeof(title), char_id);
    if (strcmp(w->title, title) != 0)
        set_window_title(battle_menu_window_id(ms->battle_menu.window_index), title, len);
}

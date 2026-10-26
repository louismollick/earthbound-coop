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
#include "include/pad.h"

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
    coop.claiming = 1;
    coop.claim_count = 0;
    coop.menu_next = 0;
    coop.choosers = 0;
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

/* The battle routine's phases from its menu loop's dead check to acting on a
 * menu's result: an A press then is a claim for the next menu. */
static bool menu_loop_phase(uint8_t phase) {
    return phase == BTL_MENU || phase == BTL_MENU_BODY || menu_phase(phase);
}

/* ---- Claimed menus ---- */

bool coop_battle_claiming(void) {
    return coop.claiming != 0;
}

void coop_battle_note_claims(const uint16_t pressed[PLATFORM_MAX_PLAYERS], int focus) {
    ModeState *ms = mode_state(GAME_MODE_BATTLE);
    if (!coop.claiming || !ms || !menu_loop_phase(ms->battle.phase))
        return;
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        if (p == focus || !coop_player_joined(p) || !(pressed[p] & PAD_A))
            continue;
        bool queued = false;
        for (int i = 0; i < coop.claim_count; i++)
            queued |= coop.claims[i] == p;
        if (!queued && coop.claim_count < PLATFORM_MAX_PLAYERS)
            coop.claims[coop.claim_count++] = (uint8_t)p;
    }
}

bool coop_battle_chosen(const BattleRoutineState *st, uint16_t slot) {
    for (uint16_t i = 0; i < st->num_selected && i < TOTAL_PARTY_COUNT; i++)
        if (bt.party_members_with_selected_actions[i] == slot)
            return true;
    return false;
}

static int slot_player(uint16_t slot) {
    return coop_battle_menu_player(game_state.party_members[slot]);
}

/* Player p's first slot in `pending` (vanilla order within a Player), or -1. */
static int first_slot(uint8_t pending, int p) {
    for (int slot = 0; slot < TOTAL_PARTY_COUNT; slot++)
        if ((pending & (1u << slot)) && (p < 0 || slot_player((uint16_t)slot) == p))
            return slot;
    return -1;
}

/* The claim wait's cue: the small action-name box (where a single-target
 * PSI's name shows) lists the Players who may claim, "P1 P2". Shown, or
 * reprinted, when `choosers` differs from what it shows; 0 closes it. */
static void show_choosers(uint8_t choosers) {
    bool open = coop.choosers && get_window(WINDOW_BATTLE_ACTION_NAME) != NULL;
    if (open && choosers == coop.choosers)
        return;
    if (open)
        close_window(WINDOW_BATTLE_ACTION_NAME);
    coop.choosers = choosers;
    if (!choosers)
        return;
    char text[16] = "";
    for (int p = 0, n = 0; p < PLATFORM_MAX_PLAYERS; p++)
        if (choosers & (1u << p))
            n += snprintf(text + n, sizeof(text) - (size_t)n, "%sP%d", n ? "  " : "", p + 1);
    create_window(WINDOW_BATTLE_ACTION_NAME);
    print_string(text);
}

/* The slot whose menu opens now, or -1 with *waiting = the Players who may
 * claim it. */
static int claim(uint8_t pending, uint8_t *waiting) {
    *waiting = 0;
    int next = coop.menu_next - 1;
    coop.menu_next = 0;
    if (next >= 0 && (pending & (1u << next)))
        return next; /* B: back to this Player's previous Hero, or the same one */
    uint8_t players = 0;
    for (int slot = 0; slot < TOTAL_PARTY_COUNT; slot++)
        if (pending & (1u << slot))
            players |= (uint8_t)(1u << slot_player((uint16_t)slot));
    /* One Player left, or Auto Fight: no claim needed, vanilla order */
    if (game_state.auto_fight_enable || !(players & (players - 1)))
        return first_slot(pending, -1);
    while (coop.claim_count) {
        int p = coop.claims[0];
        coop.claim_count--;
        memmove(coop.claims, coop.claims + 1, coop.claim_count);
        coop.claims[coop.claim_count] = 0;
        if (players & (1u << p))
            return first_slot(pending, p);
    }
    *waiting = players;
    return -1;
}

int coop_battle_claim(uint8_t pending) {
    uint8_t waiting;
    int slot = claim(pending, &waiting);
    show_choosers(waiting);
    return slot;
}

void coop_battle_menus_done(void) {
    show_choosers(0);
    coop.claiming = 0;
    coop.claim_count = 0;
    memset(coop.claims, 0, sizeof(coop.claims));
    coop.menu_next = 0;
    coop.choosers = 0;
}

void coop_battle_back(BattleRoutineState *st) {
    int p = slot_player(st->party_slot);
    uint16_t reopen = st->party_slot;
    for (int i = (int)st->num_selected - 1; i >= 0; i--) {
        uint16_t slot = bt.party_members_with_selected_actions[i];
        if (slot >= TOTAL_PARTY_COUNT || slot_player(slot) != p)
            continue;
        /* Un-choose it: later choices (other Players') keep their order */
        for (int j = i; j + 1 < (int)st->num_selected; j++)
            bt.party_members_with_selected_actions[j] = bt.party_members_with_selected_actions[j + 1];
        st->num_selected--;
        reopen = slot;
        break;
    }
    coop.menu_next = (uint8_t)(reopen + 1);
    st->phase = BTL_MENU;
}

uint8_t coop_battle_choosers(void) {
    ModeState *ms = mode_state(GAME_MODE_BATTLE);
    return ms && ms->battle.phase == BTL_MENU_BODY ? coop.choosers : 0;
}

/* ---- The title tag ---- */

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

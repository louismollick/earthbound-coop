/*
 * Local co-op join model. See coop.h.
 */
#include "coop/coop.h"

#include "game/battle.h"
#include "game/game_state.h"
#include "include/pad.h"

/* Solo play: P1 joined and owning every Hero. */
CoopState coop = { .player_count = 1, .joined = { 1 } };

/* Deal Hero h to the (h mod N)-th joined Player. Called whenever the join order
 * changes. Every chain snaps (coop_walk.h); the new chains unsnap from where
 * their members stand on the next free frame. */
static void deal_heroes(void) {
    for (int h = 0; h < COOP_HERO_COUNT; h++)
        coop.hero_owner[h] = coop.join_order[h % coop.player_count];
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++)
        coop.walkers[p].active = 0;
}

static bool valid_player(int player) {
    return player >= 0 && player < PLATFORM_MAX_PLAYERS;
}

void coop_join(int player) {
    if (!valid_player(player) || coop.joined[player] || coop.player_count >= PLATFORM_MAX_PLAYERS)
        return;
    coop.joined[player] = 1;
    coop.leave_hold[player] = 0;
    coop.join_order[coop.player_count++] = (uint8_t)player;
    deal_heroes();
}

void coop_leave(int player) {
    if (!valid_player(player) || player == 0 || !coop.joined[player])
        return;
    int i = 0;
    while (i < coop.player_count && coop.join_order[i] != player)
        i++;
    if (i == coop.player_count)
        return; /* joined but not in the order: can't happen */
    for (; i + 1 < coop.player_count; i++)
        coop.join_order[i] = coop.join_order[i + 1];
    coop.join_order[--coop.player_count] = 0;
    coop.joined[player] = 0;
    coop.leave_hold[player] = 0;
    deal_heroes();
}

void coop_tick(const uint16_t held[PLATFORM_MAX_PLAYERS]) {
    uint16_t pressed[PLATFORM_MAX_PLAYERS];
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        pressed[p] = held[p] & ~coop.prev_held[p];
        coop.prev_held[p] = held[p];
        coop.walk_pad[p] = held[p];
    }
    for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++) {
        if (!coop.joined[p]) {
            if (pressed[p] & PAD_START)
                coop_join(p);
        } else if ((held[p] & (PAD_SELECT | PAD_START)) == (PAD_SELECT | PAD_START)) {
            if (++coop.leave_hold[p] >= COOP_LEAVE_FRAMES)
                coop_leave(p);
        } else {
            coop.leave_hold[p] = 0;
        }
    }
}

void coop_unwind_frame(void) {
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++)
        coop.walk_pad[p] = 0;
}

int coop_player_count(void) {
    return coop.player_count;
}

bool coop_player_joined(int player) {
    return valid_player(player) && coop.joined[player];
}

int coop_hero_owner(int hero) {
    return hero >= 0 && hero < COOP_HERO_COUNT ? coop.hero_owner[hero] : 0;
}

uint8_t coop_conscious_hero(int i) {
    uint8_t id = game_state.party_order[i];
    if (id < 1 || id > COOP_HERO_COUNT)
        return 0;
    /* As UPDATE_PARTY's sort, which moves these members behind the walking ones */
    uint8_t s = party_characters[id - 1].afflictions[STATUS_GROUP_PERSISTENT_EASYHEAL];
    if (s == STATUS_0_UNCONSCIOUS || s == STATUS_0_DIAMONDIZED)
        return 0;
    return id;
}

uint8_t coop_walker(int player) {
    if (!coop_player_joined(player))
        return 0;
    for (int i = 0; i < game_state.party_count && i < TOTAL_PARTY_COUNT; i++) {
        uint8_t id = coop_conscious_hero(i);
        if (id && coop.hero_owner[id - 1] == player)
            return id;
    }
    return 0;
}

int coop_leader_owner(void) {
    uint8_t id = game_state.party_count ? game_state.party_order[0] : 0;
    return id >= 1 && id <= COOP_HERO_COUNT ? coop.hero_owner[id - 1] : 0;
}

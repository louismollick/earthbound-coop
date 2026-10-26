/*
 * Local co-op join model. See coop.h.
 */
#include "coop/coop.h"

#include "data/assets.h"
#include "game/battle.h"
#include "game/game_state.h"
#include "include/pad.h"

/* Solo play: P1 joined and owning every Hero. */
CoopState coop = { .player_count = 1, .joined = { 1 } };

/* Deal Hero h to the (h mod N)-th joined Player. Called whenever the join order
 * changes. Every chain snaps and, if one was walking, the Party regroups behind
 * the Leader on the next frame outside a battle (coop.regroup); the new chains
 * unsnap from there on the next free frame. That also runs after the last
 * other Player left, so solo play goes on from vanilla formation with the
 * camera back on the Leader (coop_overworld_active). */
static void deal_heroes(void) {
    for (int h = 0; h < COOP_HERO_COUNT; h++)
        coop.hero_owner[h] = coop.join_order[h % coop.player_count];
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        if (coop.walkers[p].active)
            coop.regroup = 1;
        coop.walkers[p].active = 0;
    }
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

bool coop_overworld_active(void) {
    return coop.player_count > 1 || coop.regroup || coop.camera.midpoint || coop.camera.ease_x ||
           coop.camera.ease_y;
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

/* Party member id `id` is a Guest a Stand-in may walk: Pokey, Picky, King, Tony,
 * Bubble Monkey and the Flying Men. Not Dungeon Man (a walking building) nor
 * the Teddy Bears (decoys that trail the Party). */
static bool standin_guest(uint8_t id) {
    return (id >= PARTY_MEMBER_POKEY && id <= PARTY_MEMBER_BUBBLE_MONKEY) ||
           (id >= PARTY_MEMBER_FLYING_MAN1 && id <= PARTY_MEMBER_FLYING_MAN5);
}

/* Joined Player p has no Hero in the Party, conscious or not. */
static bool absent(int player) {
    for (int i = 0; i < game_state.party_count && i < TOTAL_PARTY_COUNT; i++) {
        uint8_t id = game_state.party_order[i];
        if (id >= 1 && id <= COOP_HERO_COUNT && coop.hero_owner[id - 1] == player)
            return false;
    }
    return true;
}

uint8_t coop_standin(int player) {
    if (!coop_player_joined(player) || !absent(player))
        return 0;
    /* Player's rank among the absent Players in join order */
    int k = 0;
    for (int j = 0; j < coop.player_count && coop.join_order[j] != player; j++)
        if (absent(coop.join_order[j]))
            k++;
    for (int i = 0; i < game_state.party_count && i < TOTAL_PARTY_COUNT; i++) {
        uint8_t id = game_state.party_order[i];
        if (standin_guest(id) && k-- == 0)
            return id;
    }
    return 0;
}

uint8_t coop_walker(int player) {
    if (!coop_player_joined(player))
        return 0;
    for (int i = 0; i < game_state.party_count && i < TOTAL_PARTY_COUNT; i++) {
        uint8_t id = coop_conscious_hero(i);
        if (id && coop.hero_owner[id - 1] == player)
            return id;
    }
    return coop_standin(player);
}

int coop_leader_owner(void) {
    uint8_t id = game_state.party_count ? game_state.party_order[0] : 0;
    if (id >= 1 && id <= COOP_HERO_COUNT)
        return coop.hero_owner[id - 1];
    /* A Guest leads (every Hero is unconscious): its Stand-in, if any */
    for (int p = 0; id && p < PLATFORM_MAX_PLAYERS; p++)
        if (coop_standin(p) == id)
            return p;
    return 0;
}

const uint8_t *coop_member_name(uint8_t id, int *len) {
    if (id >= 1 && id <= COOP_HERO_COUNT) {
        *len = 5;
        return party_characters[id - 1].name;
    }
    /* A Guest's battler: its enemy configuration through NPC_AI_TABLE, as
     * battle init sets it up (battle.c) */
    const uint8_t *npc_ai = ASSET_DATA(ASSET_DATA_NPC_AI_TABLE_BIN);
    const EnemyData *enemies = (const EnemyData *)ASSET_DATA(ASSET_DATA_ENEMY_CONFIGURATION_TABLE_BIN);
    if (id < PARTY_MEMBER_POKEY || id > PARTY_MEMBER_PLUSH_TEDDY_BEAR || !npc_ai || !enemies) {
        *len = 0;
        return NULL;
    }
    *len = ENEMY_NAME_SIZE;
    return enemies[npc_ai[id * 2 + 1]].name;
}

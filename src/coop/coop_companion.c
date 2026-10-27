/*
 * Local co-op Companion (Mr. Saturn). See coop_companion.h.
 */
#include "coop/coop_companion.h"

#include "coop/coop.h"
#include "coop/coop_camera.h"
#include "entity/entity.h"
#include "entity/sprite.h"
#include "game/game_state.h"
#include "game/map_loader.h"
#include "game/overworld.h"
#include "include/constants.h"

#include <stdlib.h>

#define COMPANION_SPRITE 171      /* OVERWORLD_SPRITE::MR_SATURN: 4 directions x 2 frames */
#define COMPANION_SCRIPT 44       /* EVENT_44: static NPC (renders, then halts; never despawns) */
#define COMPANION_MARK 0x5A70     /* entity var0 = COMPANION_MARK + Player: whose Mr. Saturn */
#define LAST_NPC_SLOT 21          /* create_entity's auto range is slots 0-21 */
#define RETRY_FRAMES 30           /* between spawn attempts while slots or VRAM are full */
#define PARK_DISTANCE 20          /* px from the Leader when it (re)appears */
#define WALK_PERIOD 8             /* frames per walking frame, like a party member's var3 */

/* Directions are 0 = UP, clockwise; the sprite has the 4 cardinal ones. A
 * diagonal shows its vertical, as SPRITE_DIRECTION_MAPPING_4_DIRECTION does. */
static uint16_t cardinal(uint16_t dir) {
    static const uint8_t to_cardinal[8] = { 0, 0, 2, 4, 4, 4, 6, 0 };
    return to_cardinal[dir & 7];
}

/* `c->entity` is still Player p's Mr. Saturn: a map load (clear_map_entities)
 * may have wiped it and given the slot to someone else. */
static bool owns_entity(int p, const CoopCompanion *c) {
    int16_t e = c->entity;
    return c->spawned && e >= 0 && e <= LAST_NPC_SLOT && entities.script_table[e] == COMPANION_SCRIPT &&
           entities.sprite_ids[e] == COMPANION_SPRITE && entities.var[0][e] == COMPANION_MARK + p;
}

/* Put the entity where the state says: position, surface, facing and walking
 * frame (re-rendered only when facing or frame changed). */
static void present(const CoopCompanion *c) {
    int16_t e = c->entity;
    entities.abs_x[e] = (int16_t)c->x;
    entities.abs_y[e] = (int16_t)c->y;
    entities.surface_flags[e] = (uint8_t)c->surface;
    entities.hitbox_enabled[e] = 0;
    int8_t frame = (int8_t)(c->moved && ((c->anim / WALK_PERIOD) & 1));
    if (entities.directions[e] != (int16_t)c->direction || entities.animation_frame[e] != frame ||
        entities.use_8dir_sprites[e]) {
        entities.directions[e] = (int16_t)c->direction;
        entities.animation_frame[e] = frame;
        entities.use_8dir_sprites[e] = 0;
        render_entity_sprite(e);
    }
    entities.spritemap_ptr_hi[e] &= (uint16_t)~0x8000;
}

/* Hidden = no entity: remove it (if a map load hasn't already), so a hidden
 * Companion holds no entity slot, script slot, sprite VRAM or spritemaps. */
static void hide(int p, CoopCompanion *c) {
    if (owns_entity(p, c))
        remove_entity(c->entity);
    c->spawned = 0;
    c->moved = 0;
}

/* A spot Mr. Saturn may stand on: no wall under its footprint. */
static bool spot_clear(int16_t x, int16_t y, uint16_t size) {
    return !(lookup_surface_flags(x, y, size) & 0x00C0);
}

/* Another visible Companion stands on (x, y). */
static bool taken(const CoopCompanion *self, int16_t x, int16_t y) {
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        const CoopCompanion *o = &coop.companions[p];
        if (o != self && o->spawned && abs((int16_t)o->x - x) < 12 && abs((int16_t)o->y - y) < 12)
            return true;
    }
    return false;
}

/* Show it next to the Leader: beside him, else behind, else in front (a
 * clear spot no other Mr. Saturn stands on), else on his spot; facing his way. */
static void park(CoopCompanion *c) {
    int16_t lx = (int16_t)game_state.leader_x_coord, ly = (int16_t)game_state.leader_y_coord;
    uint16_t dir = cardinal(game_state.leader_direction);
    static const int8_t step_x[8] = { 0, 1, 1, 1, 0, -1, -1, -1 };
    static const int8_t step_y[8] = { -1, -1, 0, 1, 1, 1, 0, -1 };
    /* Right of his facing, left of it, behind, in front */
    const uint16_t tries[4] = { (uint16_t)((dir + 2) & 7), (uint16_t)((dir + 6) & 7), (uint16_t)((dir + 4) & 7), dir };
    uint16_t size = entities.sizes[c->entity];
    c->x = (uint16_t)lx;
    c->y = (uint16_t)ly;
    for (int i = 0; i < 4; i++) {
        int16_t x = (int16_t)(lx + step_x[tries[i]] * PARK_DISTANCE);
        int16_t y = (int16_t)(ly + step_y[tries[i]] * PARK_DISTANCE);
        if (spot_clear(x, y, size) && !taken(c, x, y)) {
            c->x = (uint16_t)x;
            c->y = (uint16_t)y;
            break;
        }
    }
    c->x_frac = c->y_frac = 0;
    c->direction = dir;
    c->walking_style = WALKING_STYLE_NORMAL;
    c->surface = lookup_surface_flags((int16_t)c->x, (int16_t)c->y, size);
    c->moved = 0;
    c->anim = 0;
}

/* Spawn Player p's Mr. Saturn in the highest free NPC slot, leaving the low
 * ones to the game. False if there's no room yet. The game's own entities
 * always win: create_entity removes Companions when it runs out of room
 * (coop_companion_reclaim), and this spawns only into what is free. */
static bool spawn(int p, CoopCompanion *c) {
    if (c->retry) {
        c->retry--;
        return false;
    }
    int16_t slot = -1;
    for (int16_t s = LAST_NPC_SLOT; s >= 0 && slot < 0; s--)
        if (entity_slot_available((uint16_t)s, (uint16_t)(s + 1)))
            slot = s;
    int16_t e = slot < 0 ? -1
                         : create_entity_raw(COMPANION_SPRITE, COMPANION_SCRIPT, slot,
                                             (int16_t)game_state.leader_x_coord, (int16_t)game_state.leader_y_coord);
    if (e < 0) {
        c->retry = RETRY_FRAMES;
        return false;
    }
    entities.var[0][e] = (int16_t)(COMPANION_MARK + p);
    entities.hitbox_enabled[e] = 0;
    entities.use_8dir_sprites[e] = 0;
    c->entity = e;
    c->spawned = 1;
    park(c);
    return true;
}

/* How far `v` lies outside [lo, hi]. */
static int outside(int v, int lo, int hi) {
    return v < lo ? lo - v : v > hi ? v - hi : 0;
}

/* The axes (1 = x, 2 = y) of a step from (fx, fy) to (tx, ty) that the view
 * leash reverts: the ones that take it further out of the view minus the
 * Walkers' leash margin. */
static int view_leash(int fx, int fy, int tx, int ty) {
    int cx = coop_near_x(), cy = coop_near_y();
    int lo_x = cx - EB_VIEWPORT_WIDTH / 2 + COOP_LEASH_MARGIN_X, hi_x = cx + EB_VIEWPORT_WIDTH / 2 - COOP_LEASH_MARGIN_X;
    int lo_y = cy - EB_VIEWPORT_HEIGHT / 2 + COOP_LEASH_MARGIN_Y, hi_y = cy + EB_VIEWPORT_HEIGHT / 2 - COOP_LEASH_MARGIN_Y;
    return (outside(tx, lo_x, hi_x) > outside(fx, lo_x, hi_x) ? 1 : 0) |
           (outside(ty, lo_y, hi_y) > outside(fy, lo_y, hi_y) ? 2 : 0);
}

/* The view left it behind: its 16x24 sprite (feet at x, y) is off screen. */
static bool off_screen(const CoopCompanion *c) {
    int cx = coop_near_x(), cy = coop_near_y();
    int sx = (int)c->x - (cx - EB_VIEWPORT_WIDTH / 2), sy = (int)c->y - (cy - EB_VIEWPORT_HEIGHT / 2);
    return sx < -8 || sx > EB_VIEWPORT_WIDTH + 8 || sy < 0 || sy > EB_VIEWPORT_HEIGHT + 24;
}

/* Under game control it hides once the game moves the Party (boarding a bus,
 * a cutscene walk) or the view leaves it behind; a freeze alone (most NPC
 * dialogue) leaves it standing where it is. From the Leader's tick only:
 * game_state.leader_moved is that tick's, and stale on frames it doesn't run. */
static bool hidden_by_control(const CoopCompanion *c) {
    return coop_game_moves_party() || off_screen(c);
}

/* One frame of walking on Player p's pad. For the step its hitbox is on and
 * its own slot is skipped, so NPCs (the game's invisible road blocks too) stop
 * it as they stop a Walker; enemies don't (no contact, no battle), and neither
 * do NPCs it already stands on, so it can walk off them. */
static void step(int p, CoopCompanion *c) {
    int16_t e = c->entity;
    CoopBody b = { c->x, c->y, c->x_frac, c->y_frac, c->direction, c->surface, c->walking_style };
    int16_t touched;
    int16_t npc_collision[INIT_ENTITY_SLOT];
    entities.hitbox_enabled[e] = 1;
    entities.directions[e] = (int16_t)c->direction; /* the hitbox npc_collision_check picks */
    coop_shade_npcs((int16_t)c->x, (int16_t)c->y, e, true, npc_collision);
    entities.collided_objects[e] = ENTITY_COLLISION_DISABLED;
    /* A Companion's step is no player movement for the map's sake */
    uint8_t moved_since_load = ow.player_has_moved_since_map_load;
    bool stepped = coop_borrowed_step(COOP_STEP_COMPANION, coop.walk_pad[p], &b, e, &touched);
    ow.player_has_moved_since_map_load = moved_since_load;

    uint16_t x = b.x, x_frac = b.x_frac, y = b.y, y_frac = b.y_frac;
    int revert = view_leash(c->x, c->y, x, y);
    if (revert & 1) {
        x = c->x;
        x_frac = c->x_frac;
    }
    if (revert & 2) {
        y = c->y;
        y_frac = c->y_frac;
    }
    /* Sliding along the leash only where that position is free; else no step */
    if (revert && !coop_leashed_position_clear((int16_t)c->x, (int16_t)c->y, (int16_t)x, (int16_t)y, (uint16_t)e)) {
        x = c->x;
        x_frac = c->x_frac;
        y = c->y;
        y_frac = c->y_frac;
    }
    coop_unshade_npcs(npc_collision);
    entities.hitbox_enabled[e] = 0;
    c->moved = stepped && (x != c->x || x_frac != c->x_frac || y != c->y || y_frac != c->y_frac);
    c->x = x;
    c->x_frac = x_frac;
    c->y = y;
    c->y_frac = y_frac;
    c->direction = cardinal(b.direction);
    c->walking_style = b.walking_style;
    c->surface = lookup_surface_flags((int16_t)c->x, (int16_t)c->y, entities.sizes[e]);
    if (c->moved)
        c->anim++;
}

void coop_companion_tick(WalkControl control) {
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        CoopCompanion *c = &coop.companions[p];
        if (c->spawned && !owns_entity(p, c))
            hide(p, c); /* wiped by a map load or reclaimed: respawn next to the Leader */
        if (!coop_companion(p) || control == WALK_BATTLE || (control == WALK_CONTROLLED && hidden_by_control(c))) {
            hide(p, c);
            continue;
        }
        if (control != WALK_FREE) {
            c->moved = 0; /* paused or under game control: stand still */
        } else if (c->spawned || spawn(p, c)) {
            step(p, c);
            if (off_screen(c))
                park(c);
        }
        if (c->spawned)
            present(c);
    }
}

void coop_companion_watch(void) {
    /* From an enemy touch to the end of the battle, and in a cutscene that
     * freezes the Party (or the init entity), the Leader's tick and so
     * coop_companion_tick don't run: hide here, once per frame, and under
     * game control once the view has left it behind (whether the game moved
     * the Party is coop_companion_tick's call, see hidden_by_control). */
    if (!coop_companion_spawned())
        return;
    WalkControl control = coop_walk_control();
    if (control == WALK_BATTLE) {
        coop_companion_hide_all();
    } else if (control == WALK_CONTROLLED) {
        for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++)
            if (coop.companions[p].spawned && off_screen(&coop.companions[p]))
                hide(p, &coop.companions[p]);
    }
}

void coop_companion_warp(int player) {
    CoopCompanion *c = &coop.companions[player];
    if (owns_entity(player, c))
        park(c);
}

void coop_companion_hide_all(void) {
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++)
        hide(p, &coop.companions[p]);
}

bool coop_companion_spawned(void) {
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++)
        if (coop.companions[p].spawned)
            return true;
    return false;
}

bool coop_companion_reclaim(void) {
    bool any = false;
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        CoopCompanion *c = &coop.companions[p];
        any |= owns_entity(p, c);
        hide(p, c);
    }
    return any;
}

bool coop_companion_slot(int16_t e) {
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        const CoopCompanion *c = &coop.companions[p];
        if (c->entity == e && owns_entity(p, c))
            return true;
    }
    return false;
}

int16_t coop_companion_entity(int player) {
    if (player < 0 || player >= PLATFORM_MAX_PLAYERS)
        return -1;
    const CoopCompanion *c = &coop.companions[player];
    return owns_entity(player, c) ? c->entity : -1;
}

uint32_t coop_companion_interact(int player, uint32_t (*fn)(void)) {
    int16_t e = coop_companion_entity(player);
    if (e < 0)
        return 0;
    CoopCompanion *c = &coop.companions[player];
    uint16_t lx = game_state.leader_x_coord, ly = game_state.leader_y_coord;
    uint16_t ldir = game_state.leader_direction, lslot = game_state.current_party_members;
    int8_t collided = entities.collided_objects[e];
    game_state.leader_x_coord = c->x;
    game_state.leader_y_coord = c->y;
    game_state.leader_direction = c->direction;
    game_state.current_party_members = (uint16_t)e;
    /* The search probes with the searcher's hitbox (npc_collision_check) and
     * must not find Mr. Saturn himself among the NPC slots */
    entities.hitbox_enabled[e] = 1;
    entities.collided_objects[e] = ENTITY_COLLISION_DISABLED;
    uint32_t text = fn();
    /* The search turns the "Leader" to face what it found: that was Mr. Saturn */
    uint16_t found_dir = game_state.leader_direction;
    game_state.leader_x_coord = lx;
    game_state.leader_y_coord = ly;
    game_state.leader_direction = ldir;
    game_state.current_party_members = lslot;
    if (owns_entity(player, c)) { /* not reclaimed meanwhile */
        entities.hitbox_enabled[e] = 0;
        entities.collided_objects[e] = collided;
        c->direction = cardinal(found_dir);
        present(c);
    }
    return text;
}

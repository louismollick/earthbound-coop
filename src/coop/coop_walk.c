/*
 * Local co-op Walkers and trails on the overworld. See coop_walk.h for the
 * model; this file only reuses the original movement routines
 * (update_overworld_player_input, process_door_at_tile, lookup_surface_flags,
 * update_party_entity_graphics) with a Walker's state swapped in.
 */
#include "coop/coop_walk.h"

#include "coop/coop.h"
#include "coop/coop_camera.h"
#include "core/memory.h"
#include "core/mode_stack.h"
#include "data/assets.h"
#include "entity/entity.h"
#include "game/door.h"
#include "game/game_state.h"
#include "game/map_loader.h"
#include "game/overworld.h"
#include "game/position_buffer.h"
#include "game/window.h"
#include "include/binary.h"
#include "include/constants.h"

#include <string.h>

#define NO_MEMBER 0xFF
#define FOLLOWER_TICK_ADDR 0xC04D78   /* UPDATE_FOLLOWER_STATE, as in callroutine_screen.c */
#define CHARACTER_SIZES_COUNT 17      /* CHARACTER_SIZES entries, as in position_buffer.c */
#define VAR7_SPACING_FLAG (1 << 12)   /* entity var7 bit 12, set while a follower catches up */

typedef enum {
    WALK_FREE,        /* plain overworld control: Walkers step */
    WALK_PAUSED,      /* a window, text box or interaction: Walkers hold still */
    WALK_BATTLE,      /* an enemy touched the party, the swirl or a battle: Walkers hold
                       * still and stay independent, so they are back where they stood
                       * after the battle (the touch disables every entity's tick, which
                       * would otherwise read as "scripted") */
    WALK_CONTROLLED,  /* the game controls movement: Walkers hold still; once the game
                       * actually moves the party (game_moves_party), chains snap and
                       * regroup */
} WalkControl;

static bool in_walker_step;

/* ---- Party helpers ---- */

static int16_t member_entity(uint8_t pidx) {
    return (int16_t)(PARTY_LEADER_ENTITY_INDEX + pidx);
}

/* party_characters index (entity var1) of Party position i, or NO_MEMBER. */
static uint8_t party_pos_pidx(int i) {
    int16_t e = (int16_t)read_u16_le(&game_state.party_entity_slots[i * 2]);
    if (e < PARTY_LEADER_ENTITY_INDEX || e >= MAX_ENTITIES)
        return NO_MEMBER;
    int16_t k = entities.var[1][e];
    return k >= 0 && k < TOTAL_PARTY_COUNT ? (uint8_t)k : NO_MEMBER;
}

/* Player p's chain as the Party stands now: the party_characters indices of p's
 * conscious owned Heroes in Party order, the Walker first. Empty (returns 0) if
 * p has no Walker, or walks the Leader (the Leader's Owner's chain is vanilla). */
static int current_chain(int p, uint8_t out[TOTAL_PARTY_COUNT]) {
    memset(out, NO_MEMBER, TOTAL_PARTY_COUNT);
    if (!coop_player_joined(p) || p == coop_leader_owner())
        return 0;
    int n = 0;
    for (int i = 1; i < game_state.party_count && i < TOTAL_PARTY_COUNT; i++) {
        uint8_t id = coop_conscious_hero(i);
        if (!id || coop_hero_owner(id - 1) != p)
            continue;
        uint8_t k = party_pos_pidx(i);
        if (k == NO_MEMBER)
            return 0;
        out[n++] = k;
    }
    return n;
}

static int chain_length(const uint8_t chain[TOTAL_PARTY_COUNT]) {
    int n = 0;
    while (n < TOTAL_PARTY_COUNT && chain[n] != NO_MEMBER)
        n++;
    return n;
}

/* A party entity whose tick is the follower tick (frozen or not). */
static bool runs_follower_tick(int16_t e) {
    uint32_t addr = ((uint32_t)(entities.tick_callback_hi[e] & 0xFF) << 16) | entities.tick_callback_lo[e];
    return entities.script_table[e] != ENTITY_NONE && addr == FOLLOWER_TICK_ADDR;
}

/* A party entity that no longer runs the follower tick: a script owns it, it's
 * frozen, or it's gone. */
static bool member_scripted(int16_t e) {
    return !runs_follower_tick(e) || (entities.tick_callback_hi[e] & OBJECT_TICK_DISABLED);
}

/* A chain member is scripted: the game controls that chain. */
static bool chain_scripted(const uint8_t chain[TOTAL_PARTY_COUNT]) {
    for (int k = 0; k < TOTAL_PARTY_COUNT && chain[k] != NO_MEMBER; k++)
        if (member_scripted(member_entity(chain[k])))
            return true;
    return false;
}

/* Vanilla follower spacing in trail entries (UPDATE_FOLLOWER_STATE's table plus
 * CHARACTER_SIZES). Escalators can't occur in a chain: Walkers can't board them. */
static uint16_t follower_spacing(int16_t char_id, uint16_t walking_style) {
    uint16_t spacing;
    if (walking_style == WALKING_STYLE_LADDER || walking_style == WALKING_STYLE_ROPE)
        spacing = 30;
    else if (walking_style == WALKING_STYLE_STAIRS)
        spacing = 24;
    else if (game_state.character_mode == CHARACTER_MODE_SMALL)
        spacing = 8;
    else
        spacing = 12;
    if (char_id >= 0 && char_id < CHARACTER_SIZES_COUNT)
        spacing += read_u16_le(ASSET_DATA(ASSET_DATA_CHARACTER_SIZES_BIN) + (uint16_t)char_id * 2);
    return spacing;
}

/* update_party_entity_graphics picks walking or standing frames from
 * game_state.leader_moved; a chain animates with its Walker's instead. */
static void chain_graphics(const CoopWalker *w, int16_t ent, uint16_t walking_style) {
    uint16_t saved = game_state.leader_moved;
    game_state.leader_moved = w->moved;
    update_party_entity_graphics(entities.var[0][ent], walking_style, ent, entities.var[1][ent]);
    game_state.leader_moved = saved;
}

/* ---- Control ---- */

static WalkControl walk_control(void) {
    if (ow.battle_mode || ow.battle_swirl_countdown || ow.enemy_has_been_touched)
        return WALK_BATTLE;
    if (game_state.camera_mode || ow.player_movement_flags)
        return WALK_CONTROLLED;
    if (game_state.walking_style == WALKING_STYLE_ESCALATOR || game_state.walking_style == WALKING_STYLE_STAIRS ||
        game_state.walking_style == WALKING_STYLE_BICYCLE)
        return WALK_CONTROLLED;
    if ((ow.demo_recording_flags & 0x4000) || ow.demo_frames_left)
        return WALK_CONTROLLED;
    if (dr.using_door || ow.psi_teleport_destination)
        return WALK_CONTROLLED;
    int16_t lead = (int16_t)game_state.current_party_members;
    if ((entities.tick_callback_hi[INIT_ENTITY_SLOT] & OBJECT_TICK_DISABLED) ||
        (lead >= 0 && lead < MAX_ENTITIES && (entities.tick_callback_hi[lead] & OBJECT_TICK_DISABLED)))
        return WALK_CONTROLLED;
    if (g_mode_stack.depth != 1 || g_mode_stack.mode[0] != GAME_MODE_OVERWORLD)
        return WALK_PAUSED;
    if (any_window_open() || ow.pending_interactions || ow.input_disable_frame_counter)
        return WALK_PAUSED;
    return WALK_FREE;
}

/* Under WALK_CONTROLLED: the game is moving the party now (the Leader moved).
 * Until then the chains hold where they stand, so a door's text, an NPC
 * freezing the party for a line or a scripted pause doesn't pull everyone onto
 * the Leader. A door or screen transition regroups at its fade instead
 * (coop_walk_regroup), as every entity is frozen by then. */
static bool game_moves_party(void) {
    return game_state.leader_moved != 0;
}

bool coop_game_controls_movement(void) {
    WalkControl c = walk_control();
    return c == WALK_CONTROLLED || c == WALK_BATTLE;
}

/* ---- Snap / unsnap ---- */

static void snap(CoopWalker *w) {
    w->active = 0;
    w->moved = 0;
    w->touched = -1;
}

static int chain_of_entity(int16_t ent, int *k);

/* Snap's visible half: every follower takes its vanilla place on the Leader's
 * trail at once, `spacing` entries behind its Party predecessor, so a snapped
 * chain regroups behind the Leader (before a door's fade, a cutscene, the
 * stairs) instead of standing where it was until the Leader moves. Members of
 * chains still independent keep their shadow index and their place; members a
 * script owns keep their place (frozen ones are placed). */
static void regroup(void) {
    uint8_t lead = party_pos_pidx(0);
    if (lead == NO_MEMBER)
        return;
    uint8_t idx = (uint8_t)party_characters[lead].position_index;
    for (int i = 1; i < game_state.party_count && i < TOTAL_PARTY_COUNT; i++) {
        uint8_t pidx = party_pos_pidx(i);
        if (pidx == NO_MEMBER)
            continue;
        int16_t e = member_entity(pidx);
        int k;
        if (chain_of_entity(e, &k) < 0)
            idx = (uint8_t)(idx - follower_spacing(entities.var[0][e], game_state.walking_style));
        party_characters[pidx].position_index = idx;
        if (chain_of_entity(e, &k) >= 0 || !runs_follower_tick(e))
            continue;
        const PositionBufferEntry *en = &pb.player_position_buffer[idx];
        entities.abs_x[e] = en->x_coord;
        entities.abs_y[e] = en->y_coord;
        entities.directions[e] = (int16_t)en->direction;
        entities.surface_flags[e] = en->tile_flags;
    }
}

static PositionBufferEntry entity_entry(int16_t e) {
    PositionBufferEntry en = {
        .x_coord = entities.abs_x[e],
        .y_coord = entities.abs_y[e],
        .tile_flags = (uint8_t)entities.surface_flags[e],
        .walking_style = (uint8_t)entities.walking_styles[e],
        .direction = (uint8_t)(entities.directions[e] & 7),
    };
    return en;
}

/* Start a chain walking from where its members stand: the Walker's state comes
 * from its entity, and the trail is laid through the members' positions, each
 * segment a straight line of exactly the vanilla spacing, so the next frame
 * continues seamlessly (no jump, no catch-up). Entry k-1 to entry k spans
 * spacing_k - 1 entries because a follower shows the entry spacing - 1 behind
 * its predecessor's and its index is one past the entry it shows. */
static void unsnap(CoopWalker *w, const uint8_t chain[TOTAL_PARTY_COUNT]) {
    int n = chain_length(chain);
    memcpy(w->chain, chain, TOTAL_PARTY_COUNT);
    int16_t e0 = member_entity(chain[0]);
    w->x = (uint16_t)entities.abs_x[e0];
    w->y = (uint16_t)entities.abs_y[e0];
    w->x_frac = w->y_frac = 0;
    w->direction = (uint16_t)(entities.directions[e0] & 7);
    w->surface = (uint16_t)entities.surface_flags[e0];
    /* The party-wide style (normal, slowest, ...); ladders and ropes are per tile
     * and come back on the Walker's first step onto one. */
    w->walking_style = game_state.walking_style;
    if (w->walking_style == WALKING_STYLE_LADDER || w->walking_style == WALKING_STYLE_ROPE)
        w->walking_style = WALKING_STYLE_NORMAL;
    w->moved = 0;
    w->touched = -1;
    w->head = 0;

    PositionBufferEntry last = entity_entry(member_entity(chain[n - 1]));
    for (int i = 0; i < POSITION_BUFFER_SIZE; i++)
        w->trail[i] = last;
    uint8_t shown = (uint8_t)(w->head - 1); /* the Walker's current entry */
    w->trail[shown] = entity_entry(e0);
    w->ring_index[0] = w->head;
    for (int k = 1; k < n; k++) {
        int16_t ep = member_entity(chain[k - 1]), ek = member_entity(chain[k]);
        PositionBufferEntry en = entity_entry(ek);
        int segment = follower_spacing(entities.var[0][ek], en.walking_style) - 1;
        int x0 = entities.abs_x[ep], y0 = entities.abs_y[ep];
        for (int j = 1; j <= segment; j++) {
            PositionBufferEntry t = en;
            t.x_coord = (int16_t)(x0 + (en.x_coord - x0) * j / segment);
            t.y_coord = (int16_t)(y0 + (en.y_coord - y0) * j / segment);
            w->trail[(uint8_t)(shown - j)] = t;
        }
        shown = (uint8_t)(shown - segment);
        w->ring_index[k] = (uint8_t)(shown + 1);
        w->shown[k] = shown;
    }
    w->shown[0] = 0;
    for (int k = n; k < TOTAL_PARTY_COUNT; k++)
        w->ring_index[k] = w->shown[k] = 0;
    w->active = 1;
}

void coop_walk_regroup(void) {
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++)
        snap(&coop.walkers[p]);
    regroup();
}

void coop_walk_on_trail_reset(void) {
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++)
        snap(&coop.walkers[p]);
}

/* ---- The Walker step ---- */

bool coop_in_walker_step(void) {
    return in_walker_step;
}

uint16_t coop_walker_door(uint16_t x_tile, uint16_t y_tile) {
    uint8_t type = find_door_at_position(x_tile, y_tile);
    if (type == DOOR_TYPE_3 || type == DOOR_TYPE_4)
        return 0;
    return process_door_at_tile(x_tile, y_tile);
}

/* ---- The leash ---- */

/* A step from `from` to `to` on one axis widens the Walkers' spread past `cap`,
 * given the other Walkers' range [lo, hi] on that axis. A step that narrows an
 * already too wide spread is fine. */
static bool widens_past(int lo, int hi, int from, int to, int cap) {
    int before = (hi > from ? hi : from) - (lo < from ? lo : from);
    int after = (hi > to ? hi : to) - (lo < to ? lo : to);
    return after > cap && after > before;
}

/* The axes of a step the leash reverts (1 = x, 2 = y). `mover` is the Player
 * whose Walker steps, or -1 for the Leader; (leader_x, leader_y) is the
 * Leader's position, used when another Walker steps. */
static int leash(int mover, int leader_x, int leader_y, int from_x, int from_y, int to_x, int to_y) {
    int lo_x = 0, hi_x = 0, lo_y = 0, hi_y = 0;
    bool any = false;
    for (int p = -1; p < PLATFORM_MAX_PLAYERS; p++) {
        int x, y;
        if (p == mover)
            continue;
        if (p < 0) {
            x = leader_x;
            y = leader_y;
        } else if (coop.walkers[p].active) {
            x = coop.walkers[p].x;
            y = coop.walkers[p].y;
        } else {
            continue;
        }
        if (!any || x < lo_x) lo_x = x;
        if (!any || x > hi_x) hi_x = x;
        if (!any || y < lo_y) lo_y = y;
        if (!any || y > hi_y) hi_y = y;
        any = true;
    }
    if (!any)
        return 0;
    return (widens_past(lo_x, hi_x, from_x, to_x, COOP_LEASH_SPREAD_X) ? 1 : 0) |
           (widens_past(lo_y, hi_y, from_y, to_y, COOP_LEASH_SPREAD_Y) ? 2 : 0);
}

/* The step's collision checks (walls, then NPCs) cleared the position it moved
 * to; after the leash reverted one axis the Walker ends up somewhere else, so
 * check that position too, with the same two routines and the remaining
 * axis's direction. `slot` is the stepping entity (its hitbox). Side-effect
 * free: the scratch state the checks write is put back. */
static bool leashed_position_clear(int16_t from_x, int16_t from_y, int16_t x, int16_t y, uint16_t slot) {
    if (x == from_x && y == from_y)
        return true; /* where it stood */
    int16_t dir = x != from_x ? (x > from_x ? 2 : 6) : (y > from_y ? 4 : 0);
    int16_t final_dir = ow.final_movement_direction;
    uint8_t not_same_dir = ow.not_moving_in_same_direction_faced;
    uint16_t check_x = ow.checked_collision_left_x, check_y = ow.checked_collision_top_y;
    int16_t ladder_x = ow.ladder_stairs_tile_x, ladder_y = ow.ladder_stairs_tile_y;
    int16_t collided = entities.collided_objects[INIT_ENTITY_SLOT];

    uint16_t flags = check_directional_collision(x, y, dir);
    /* A wall, or a corner the game would nudge around */
    bool clear = !(flags & 0x00C0) && ow.final_movement_direction == dir;
    if (clear)
        clear = npc_collision_check(x, y, (int16_t)slot) == -1;

    ow.final_movement_direction = final_dir;
    ow.not_moving_in_same_direction_faced = not_same_dir;
    ow.checked_collision_left_x = check_x;
    ow.checked_collision_top_y = check_y;
    ow.ladder_stairs_tile_x = ladder_x;
    ow.ladder_stairs_tile_y = ladder_y;
    entities.collided_objects[INIT_ENTITY_SLOT] = collided;
    return clear;
}

void coop_leader_step(void) {
    uint16_t x = game_state.leader_x_coord, x_frac = game_state.leader_x_frac;
    uint16_t y = game_state.leader_y_coord, y_frac = game_state.leader_y_frac;
    update_overworld_player_input();
    if (walk_control() != WALK_FREE)
        return;
    int revert = leash(-1, 0, 0, x, y, game_state.leader_x_coord, game_state.leader_y_coord);
    if (revert & 1) {
        game_state.leader_x_coord = x;
        game_state.leader_x_frac = x_frac;
    }
    if (revert & 2) {
        game_state.leader_y_coord = y;
        game_state.leader_y_frac = y_frac;
    }
    /* Sliding along the leash only where that position is free; else no step */
    if (revert && !leashed_position_clear((int16_t)x, (int16_t)y, (int16_t)game_state.leader_x_coord,
                                          (int16_t)game_state.leader_y_coord, game_state.current_party_members)) {
        game_state.leader_x_coord = x;
        game_state.leader_x_frac = x_frac;
        game_state.leader_y_coord = y;
        game_state.leader_y_frac = y_frac;
    }
    /* Held in place on both axes: a stop, as at a wall */
    if (revert && game_state.leader_x_coord == x && game_state.leader_x_frac == x_frac &&
        game_state.leader_y_coord == y && game_state.leader_y_frac == y_frac)
        game_state.leader_moved = 0;
}

/* One frame of Player p's Walker: the Leader's own movement step with the
 * Walker swapped into the Leader globals and p's pad in core.pad1, then the
 * Walker's trail write (as position_buffer_write). Shared side effects are
 * suppressed (mushroom d-pad swap, hotspots) or kept (doors and door text queue
 * their interaction for the whole Party). */
static void walker_step(int p, CoopWalker *w) {
    int16_t slot = member_entity(w->chain[0]);

    /* The Leader's state, restored afterwards */
    uint16_t lx_frac = game_state.leader_x_frac, lx = game_state.leader_x_coord;
    uint16_t ly_frac = game_state.leader_y_frac, ly = game_state.leader_y_coord;
    uint16_t ldir = game_state.leader_direction, ltrod = game_state.trodden_tile_type;
    uint16_t lstyle = game_state.walking_style, lmoved = game_state.leader_moved;
    uint16_t lslot = game_state.current_party_members;
    uint16_t pad_held = core.pad1_held, pad_pressed = core.pad1_pressed;
    uint16_t stairs_direction = ow.stairs_direction;
    int16_t final_dir = ow.final_movement_direction;
    uint8_t not_same_dir = ow.not_moving_in_same_direction_faced;
    uint16_t check_x = ow.checked_collision_left_x, check_y = ow.checked_collision_top_y;
    int16_t ladder_x = ow.ladder_stairs_tile_x, ladder_y = ow.ladder_stairs_tile_y;
    uint8_t mushroom = ow.mushroomized_walking_flag;
    uint16_t hotspot_mode[NUM_ACTIVE_HOTSPOTS];
    uint16_t door_found = dr.door_found, door_found_type = dr.door_found_type;
    int16_t collided = entities.collided_objects[INIT_ENTITY_SLOT];

    game_state.leader_x_frac = w->x_frac;
    game_state.leader_x_coord = w->x;
    game_state.leader_y_frac = w->y_frac;
    game_state.leader_y_coord = w->y;
    game_state.leader_direction = w->direction;
    game_state.trodden_tile_type = w->surface;
    game_state.walking_style = w->walking_style;
    game_state.current_party_members = (uint16_t)slot;
    core.pad1_held = coop.walk_pad[p] & 0xFFF0;
    core.pad1_pressed = 0;
    ow.stairs_direction = 0xFFFF;
    ow.mushroomized_walking_flag = 0;
    for (int i = 0; i < NUM_ACTIVE_HOTSPOTS; i++) {
        hotspot_mode[i] = ow.active_hotspots[i].mode;
        ow.active_hotspots[i].mode = 0;
    }

    in_walker_step = true;
    update_overworld_player_input();
    in_walker_step = false;

    uint16_t x_frac = game_state.leader_x_frac, x = game_state.leader_x_coord;
    uint16_t y_frac = game_state.leader_y_frac, y = game_state.leader_y_coord;
    int revert = leash(p, lx, ly, w->x, w->y, x, y);
    if (revert & 1) {
        x = w->x;
        x_frac = w->x_frac;
    }
    if (revert & 2) {
        y = w->y;
        y_frac = w->y_frac;
    }
    /* Sliding along the leash only where that position is free; else no step */
    if (revert && !leashed_position_clear((int16_t)w->x, (int16_t)w->y, (int16_t)x, (int16_t)y, (uint16_t)slot)) {
        x = w->x;
        x_frac = w->x_frac;
        y = w->y;
        y_frac = w->y_frac;
    }
    bool moved = game_state.leader_moved &&
                 (x != w->x || x_frac != w->x_frac || y != w->y || y_frac != w->y_frac);
    w->x = x;
    w->x_frac = x_frac;
    w->y = y;
    w->y_frac = y_frac;
    w->direction = game_state.leader_direction;
    w->walking_style = game_state.walking_style;
    w->moved = moved;
    w->touched = entities.collided_objects[INIT_ENTITY_SLOT];

    game_state.leader_x_frac = lx_frac;
    game_state.leader_x_coord = lx;
    game_state.leader_y_frac = ly_frac;
    game_state.leader_y_coord = ly;
    game_state.leader_direction = ldir;
    game_state.trodden_tile_type = ltrod;
    game_state.walking_style = lstyle;
    game_state.leader_moved = lmoved;
    game_state.current_party_members = lslot;
    core.pad1_held = pad_held;
    core.pad1_pressed = pad_pressed;
    ow.stairs_direction = stairs_direction;
    ow.final_movement_direction = final_dir;
    ow.not_moving_in_same_direction_faced = not_same_dir;
    ow.checked_collision_left_x = check_x;
    ow.checked_collision_top_y = check_y;
    ow.ladder_stairs_tile_x = ladder_x;
    ow.ladder_stairs_tile_y = ladder_y;
    ow.mushroomized_walking_flag = mushroom;
    for (int i = 0; i < NUM_ACTIVE_HOTSPOTS; i++)
        ow.active_hotspots[i].mode = hotspot_mode[i];
    dr.door_found = door_found;
    dr.door_found_type = door_found_type;
    entities.collided_objects[INIT_ENTITY_SLOT] = collided;

    /* As update_leader_movement: surface flags under the Walker, then the trail */
    w->surface = lookup_surface_flags((int16_t)w->x, (int16_t)w->y, entities.sizes[slot]);
    PositionBufferEntry *en = &w->trail[w->head];
    if (w->moved) {
        en->x_coord = (int16_t)w->x;
        en->y_coord = (int16_t)w->y;
        w->head++;
        /* As update_overworld_frame does for the Leader: a moving Walker counts
         * as the player doing something, which doors require */
        ow.player_has_done_something_this_frame = 1;
    }
    en->tile_flags = (uint8_t)w->surface;
    en->walking_style = (uint8_t)w->walking_style;
    en->direction = (uint8_t)w->direction;
}

void coop_walk_leader_tick(void) {
    WalkControl control = walk_control();
    if (coop.regroup && control != WALK_BATTLE) {
        /* Ownership changed (a join or leave): everyone back in formation */
        coop_walk_regroup();
        coop.regroup = 0;
    }
    if (coop_player_count() <= 1) {
        /* The last other Player left: only the camera eases back to the Leader */
        if (control != WALK_BATTLE)
            coop_camera_update();
        return;
    }
    bool snapped = false;
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        CoopWalker *w = &coop.walkers[p];
        if (control == WALK_BATTLE) {
            w->moved = 0;
            w->touched = -1;
            continue;
        }
        uint8_t chain[TOTAL_PARTY_COUNT];
        int n = current_chain(p, chain);
        bool scripted = n && chain_scripted(chain);
        if (w->active && ((control == WALK_CONTROLLED && game_moves_party()) || scripted ||
                          memcmp(chain, w->chain, TOTAL_PARTY_COUNT) != 0)) {
            snap(w);
            snapped = true;
        }
        if (!w->active) {
            if (control == WALK_FREE && n && !scripted)
                unsnap(w, chain);
            continue;
        }
        if (control == WALK_FREE) {
            walker_step(p, w);
        } else {
            w->moved = 0;
            w->touched = -1;
        }
    }
    if (snapped)
        regroup();
    coop_camera_update();
}

/* ---- Chain members' ticks ---- */

/* The Player whose independent chain has entity `ent` at position *k, or -1. */
static int chain_of_entity(int16_t ent, int *k) {
    int16_t char_id = entities.var[0][ent];
    int16_t pidx = entities.var[1][ent];
    if (char_id < 0 || char_id >= COOP_HERO_COUNT || pidx < 0 || pidx >= TOTAL_PARTY_COUNT)
        return -1;
    int p = coop_hero_owner(char_id);
    const CoopWalker *w = &coop.walkers[p];
    if (!w->active)
        return -1;
    for (int i = 0; i < TOTAL_PARTY_COUNT && w->chain[i] != NO_MEMBER; i++) {
        if (w->chain[i] == pidx) {
            *k = i;
            return p;
        }
    }
    return -1;
}

bool coop_walk_entity_independent(int16_t ent) {
    int k;
    return chain_of_entity(ent, &k) >= 0;
}

/* Keep member pidx's vanilla trail index valid: its Party predecessor's index
 * (see "Snap" in coop_walk.h). */
static void update_shadow_index(int16_t ent, uint8_t pidx) {
    for (int i = 1; i < game_state.party_count && i < TOTAL_PARTY_COUNT; i++) {
        if ((int16_t)read_u16_le(&game_state.party_entity_slots[i * 2]) != ent)
            continue;
        uint8_t prev = party_pos_pidx(i - 1);
        if (prev != NO_MEMBER)
            party_characters[pidx].position_index = party_characters[prev].position_index;
        return;
    }
}

bool coop_walk_follower_tick(int16_t ent) {
    int k;
    int p = chain_of_entity(ent, &k);
    if (p < 0)
        return false;
    CoopWalker *w = &coop.walkers[p];

    /* The Leader's tick may not have run this frame (a frozen init entity), so
     * the chain re-checks that it is still independent. */
    WalkControl control = walk_control();
    uint8_t chain[TOTAL_PARTY_COUNT];
    current_chain(p, chain);
    if ((control == WALK_CONTROLLED && game_moves_party()) || memcmp(chain, w->chain, TOTAL_PARTY_COUNT) != 0 ||
        chain_scripted(chain)) {
        snap(w);
        regroup();
        return false;
    }
    if (control != WALK_FREE)
        w->moved = 0;

    uint8_t pidx = w->chain[k];
    update_shadow_index(ent, pidx);

    if (k == 0) {
        /* The Walker: its entity shows the Walker state (vanilla's Leader path) */
        entities.directions[ent] = (int16_t)w->direction;
        entities.surface_flags[ent] = (uint8_t)w->surface;
        chain_graphics(w, ent, w->walking_style);
        party_characters[pidx].buffer_walking_style = w->walking_style;
        entities.abs_x[ent] = (int16_t)w->x;
        entities.abs_y[ent] = (int16_t)w->y;
        entities.var[7][ent] &= (int16_t)~VAR7_SPACING_FLAG;
        return true;
    }

    /* A member trailing the Walker: UPDATE_FOLLOWER_STATE on this chain's trail,
     * spaced against its chain predecessor (the Walker's index is the head) */
    uint8_t idx = w->ring_index[k];
    const PositionBufferEntry *en = &w->trail[idx];
    entities.directions[ent] = (int16_t)en->direction;
    entities.surface_flags[ent] = en->tile_flags;
    chain_graphics(w, ent, en->walking_style);
    if (w->moved)
        w->shown[k] = idx;
    /* Placed every frame, not only when the Walker moves: after a battle
     * refresh_party_entities has put the chain on the Leader's trail */
    entities.abs_x[ent] = w->trail[w->shown[k]].x_coord;
    entities.abs_y[ent] = w->trail[w->shown[k]].y_coord;
    if (!w->moved)
        return true;
    party_characters[pidx].buffer_walking_style = en->walking_style;
    uint16_t spacing = follower_spacing(entities.var[0][ent], en->walking_style);
    uint8_t prev = k == 1 ? w->head : w->ring_index[k - 1];
    uint8_t distance = (uint8_t)(prev - idx);
    if (distance == spacing) {
        idx++;
        entities.var[7][ent] &= (int16_t)~VAR7_SPACING_FLAG;
    } else if (distance > spacing) {
        idx += 2;
        entities.var[7][ent] |= (int16_t)VAR7_SPACING_FLAG;
    }
    w->ring_index[k] = idx;
    return true;
}

/* ---- Enemy contact ---- */

int16_t coop_walker_touching(int16_t slot) {
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        const CoopWalker *w = &coop.walkers[p];
        if (w->active && w->touched == slot)
            return member_entity(w->chain[0]);
    }
    return -1;
}

uint16_t coop_contact_facing(int16_t target) {
    if (target >= PARTY_LEADER_ENTITY_INDEX && target < MAX_ENTITIES && target != (int16_t)game_state.current_party_members) {
        int16_t char_id = entities.var[0][target];
        if (char_id >= 0 && char_id < COOP_HERO_COUNT && coop_hero_owner(char_id) != coop_leader_owner())
            return (uint16_t)(entities.directions[target] & 7);
    }
    return game_state.leader_direction;
}

void coop_contact_turn(void) {
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        CoopWalker *w = &coop.walkers[p];
        if (!w->active || w->walking_style == WALKING_STYLE_LADDER || w->walking_style == WALKING_STYLE_ROPE)
            continue;
        uint16_t held = core.pad1_held;
        core.pad1_held = coop.walk_pad[p] & 0xFFF0;
        int16_t dir = map_input_to_direction(w->walking_style);
        core.pad1_held = held;
        if (dir < 0)
            continue;
        w->direction = (uint16_t)dir;
        for (int k = 0; k < TOTAL_PARTY_COUNT && w->chain[k] != NO_MEMBER; k++) {
            int16_t e = member_entity(w->chain[k]);
            if (entities.script_table[e] != ENTITY_NONE)
                entities.directions[e] = dir;
        }
    }
}

/* ---- Queries ---- */

bool coop_walker_info(int player, CoopWalkerInfo *out) {
    uint8_t id = coop_walker(player);
    if (!id)
        return false;
    memset(out, 0, sizeof(*out));
    out->member = id;
    out->touched = -1;
    if (game_state.party_order[0] == id) {
        out->leader = true;
        out->entity = (int16_t)game_state.current_party_members;
        out->x = game_state.leader_x_coord;
        out->y = game_state.leader_y_coord;
        out->direction = game_state.leader_direction;
        out->walking_style = game_state.walking_style;
        out->touched = entities.collided_objects[INIT_ENTITY_SLOT];
        return true;
    }
    const CoopWalker *w = &coop.walkers[player];
    if (w->active && coop_player_count() > 1) {
        out->independent = true;
        out->entity = member_entity(w->chain[0]);
        out->x = w->x;
        out->y = w->y;
        out->direction = w->direction;
        out->walking_style = w->walking_style;
        out->touched = w->touched;
        return true;
    }
    for (int i = 0; i < game_state.party_count && i < TOTAL_PARTY_COUNT; i++) {
        if (game_state.party_order[i] != id)
            continue;
        uint8_t pidx = party_pos_pidx(i);
        if (pidx == NO_MEMBER)
            return false;
        int16_t e = member_entity(pidx);
        out->entity = e;
        out->x = (uint16_t)entities.abs_x[e];
        out->y = (uint16_t)entities.abs_y[e];
        out->direction = (uint16_t)entities.directions[e];
        out->walking_style = (uint16_t)entities.walking_styles[e];
        return true;
    }
    return false;
}

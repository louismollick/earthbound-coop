/*
 * Local co-op Walkers and trails on the overworld. See coop_walk.h for the
 * model; this file only reuses the original movement routines
 * (update_overworld_player_input, process_door_at_tile, lookup_surface_flags,
 * update_party_entity_graphics) with a Walker's state swapped in.
 */
#include "coop/coop_walk.h"

#include "coop/coop.h"
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

/* TEMPORARY safety clamp, until the leash (M1 camera item) replaces it: the
 * camera still follows the Leader and the collision grid is only 64x64 tiles
 * around the camera, so a non-Leader Walker stays within this many px of the
 * Leader on each axis (on screen, 16 px from the edge). */
#define TEMP_CLAMP_X (EB_VIEWPORT_WIDTH / 2 - 16)
#define TEMP_CLAMP_Y (EB_VIEWPORT_HEIGHT / 2 - 16)

typedef enum {
    WALK_FREE,        /* plain overworld control: Walkers step */
    WALK_PAUSED,      /* a window, text box or interaction: Walkers hold still */
    WALK_CONTROLLED,  /* the game moves the party: chains snap */
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

/* A chain member that no longer runs the follower tick (a script owns it, it's
 * frozen, or it's gone): the game controls that chain. */
static bool chain_scripted(const uint8_t chain[TOTAL_PARTY_COUNT]) {
    for (int k = 0; k < TOTAL_PARTY_COUNT && chain[k] != NO_MEMBER; k++) {
        int16_t e = member_entity(chain[k]);
        uint32_t addr = ((uint32_t)(entities.tick_callback_hi[e] & 0xFF) << 16) | entities.tick_callback_lo[e];
        if (entities.script_table[e] == ENTITY_NONE || (entities.tick_callback_hi[e] & OBJECT_TICK_DISABLED) ||
            addr != FOLLOWER_TICK_ADDR)
            return true;
    }
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
        return WALK_CONTROLLED;
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

bool coop_game_controls_movement(void) {
    return walk_control() == WALK_CONTROLLED;
}

/* ---- Snap / unsnap ---- */

static void snap(CoopWalker *w) {
    w->active = 0;
    w->moved = 0;
    w->touched = -1;
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
    }
    for (int k = n; k < TOTAL_PARTY_COUNT; k++)
        w->ring_index[k] = 0;
    w->active = 1;
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
    /* TEMPORARY clamp (see TEMP_CLAMP_X): revert an axis that strays too far */
    if ((int16_t)(x - lx) > TEMP_CLAMP_X || (int16_t)(x - lx) < -TEMP_CLAMP_X) {
        x = w->x;
        x_frac = w->x_frac;
    }
    if ((int16_t)(y - ly) > TEMP_CLAMP_Y || (int16_t)(y - ly) < -TEMP_CLAMP_Y) {
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
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        CoopWalker *w = &coop.walkers[p];
        uint8_t chain[TOTAL_PARTY_COUNT];
        int n = current_chain(p, chain);
        bool scripted = n && chain_scripted(chain);
        if (w->active && (control == WALK_CONTROLLED || scripted ||
                          memcmp(chain, w->chain, TOTAL_PARTY_COUNT) != 0))
            snap(w);
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
    if (control == WALK_CONTROLLED || memcmp(chain, w->chain, TOTAL_PARTY_COUNT) != 0 || chain_scripted(chain)) {
        snap(w);
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
    if (!w->moved)
        return true;
    entities.abs_x[ent] = en->x_coord;
    entities.abs_y[ent] = en->y_coord;
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

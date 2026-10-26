#ifndef EB_COOP_COOP_WALK_H
#define EB_COOP_COOP_WALK_H

/*
 * Local co-op on the overworld: Walkers and their trails (M1). Vocabulary in
 * CONTEXT.md, design in docs/coop-design/walkers.md.
 *
 * The Leader is vanilla's (party_order[0]) and walks on the vanilla code path,
 * fed by its Owner's pad (the input focus, coop_input.h). Every other Player with a Walker has
 * a chain: the Walker plus that Player's other conscious owned Heroes. While the
 * chain is independent ("active"), its Walker takes the Leader's own movement
 * step each frame with its state swapped into the Leader globals
 * (update_overworld_player_input), writes its own trail, and the chain's
 * members follow that trail with vanilla spacing. Everyone else (Guests, the
 * Leader's Owner's other Heroes, unconscious members) trails the Leader as in
 * vanilla.
 *
 * Snap: when the game controls movement (coop_game_controls_movement), a chain
 * stops being independent. Its members then simply run vanilla follower code on
 * the Leader's trail: every frame a chain is independent, each member's
 * char_struct.position_index is kept as a "shadow" equal to its Party
 * predecessor's, so the vanilla trail indices stay valid for everything that
 * reads them (the next member's spacing, refresh_party_entities,
 * add_party_member). On a snap every follower is put in its vanilla place on
 * the Leader's trail at once (regroup), so the Party goes through a door or
 * into a cutscene together.
 * Unsnap: when control returns, the chain's trail is laid through the members'
 * current positions at vanilla spacing, so nobody jumps.
 * A window or text box only pauses Walkers (no step, no snap): the chain holds.
 * So does an enemy touch and the battle after it: Walkers are back where they
 * stood afterwards.
 * Leash: every step (the Leader's too) that would spread the Walkers wider than
 * the view allows is reverted on that axis (coop_camera.h).
 *
 * Every hook is gated on coop_player_count() > 1, so solo play is vanilla.
 */

#include "core/types.h"
#include "platform/platform.h"

/* Hook, end of update_leader_movement: snap / unsnap chains, run each
 * independent Walker's step, then move the camera (coop_camera_update). */
void coop_walk_leader_tick(void);

/* Hook, update_leader_movement's walking dispatch: the Leader's own step
 * (update_overworld_player_input), leashed to the independent Walkers. */
void coop_leader_step(void);

/* Hook, update_follower_state (after its early exits): runs the co-op tick and
 * returns true if `ent` is a member of an independent chain; false = vanilla. */
bool coop_walk_follower_tick(int16_t ent);

/* Hook, init_party_position_buffer / fill_party_position_buffer: the Leader's
 * trail was reset (map load, teleport), so every chain snaps. */
void coop_walk_on_trail_reset(void);

/* Hook, the exit (fade-out) half of a screen transition (doors, holes, hotspot
 * warps): every chain snaps and the Party regroups behind the Leader for the
 * fade, so nobody is left standing mid-screen. */
void coop_walk_regroup(void);

/* Hook, update_party_sprite_position: an independent chain member doesn't move
 * with the camera, so its screen position is always recomputed. */
bool coop_walk_entity_independent(int16_t ent);

/* Hook, update_overworld_player_input's ladder/door tile check. True only inside
 * a non-Leader Walker's step. */
bool coop_in_walker_step(void);
/* process_door_at_tile for a non-Leader Walker: escalators and stairs are walls
 * (the Leader takes them); ladders, ropes, doors and door text work. */
uint16_t coop_walker_door(uint16_t x_tile, uint16_t y_tile);

/* ---- Seams for camera, leash, contact, interaction and regrouping ---- */

/* The game moves the party itself right now (cutscene, camera_mode, stairs,
 * escalator, bicycle, door, teleport, demo, battle swirl, a frozen or scripted
 * Leader): non-Leader Walkers don't step and their chains are snapped. */
bool coop_game_controls_movement(void);

/* ---- Enemy contact ---- */

/* The entity slot of the independent Walker whose step this frame ran into
 * entity `slot`, or -1. CHECK_ENTITY_ENEMY_COLLISION counts it as a touch,
 * and HANDLE_ENEMY_CONTACT targets that Walker. */
int16_t coop_walker_touching(int16_t slot);

/* The facing INITIATE_ENEMY_ENCOUNTER judges first strike with, for the party
 * entity the enemy targets: a Hero of another Player than the Leader's Owner
 * (their Walker or a member of its chain) faces its own way; anyone else is
 * judged by the Leader's direction, as vanilla. */
uint16_t coop_contact_facing(int16_t target);

/* Hook, UPDATE_CAMERA_MODE_3 (the 12 frames after a touch, when the pad turns
 * the party): each independent chain turns with its own Player's pad; the
 * vanilla loop skips those members (coop_walk_entity_independent). */
void coop_contact_turn(void);

typedef struct {
    uint8_t member;        /* party member id (1-4) of the Walker */
    bool leader;           /* the Walker is the Leader (vanilla state) */
    bool independent;      /* a non-Leader Walker walking its own trail */
    uint16_t x, y;         /* world position */
    uint16_t direction;    /* 0 = UP, clockwise */
    uint16_t walking_style;
    int16_t entity;        /* the Walker's entity slot */
    int16_t touched;       /* the slot this frame's step ran into (-1 none); for the
                            * Leader, entities.collided_objects[23] */
} CoopWalkerInfo;

/* Player p's Walker as it stands now; false if p has none (not joined, Spectator). */
bool coop_walker_info(int player, CoopWalkerInfo *out);

#endif /* EB_COOP_COOP_WALK_H */

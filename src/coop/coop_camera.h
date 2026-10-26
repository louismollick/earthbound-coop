#ifndef EB_COOP_COOP_CAMERA_H
#define EB_COOP_COOP_CAMERA_H

/*
 * Local co-op camera and leash (M1). Design: docs/coop-design/walkers.md.
 *
 * While any non-Leader Walker walks independently, the view centres on the
 * middle of the Walkers' bounding box (the Leader plus every independent
 * Walker). The box centre, not the mean, because it keeps every Walker within
 * half the spread of the centre, so a spread cap is exactly a "stays on screen"
 * guarantee whatever the number of Walkers.
 * When the game controls movement the chains snap and the view follows the
 * Leader as in vanilla. Switching between the two (and any other routine moving
 * the view while the midpoint rules, e.g. the reload after a battle) eases
 * over about a dozen frames with integer math; a jump bigger than a screen cuts.
 *
 * The view goes through vanilla's CENTER_SCREEN (map_refresh_tilemaps), so tile
 * streaming, the collision grid and NPC spawns follow it. Vanilla never clamps
 * that camera to the map; the midpoint lies between Walkers that stand on the
 * map, so its scroll is always between the ones vanilla would show with either
 * of them leading, and needs no clamp of its own.
 *
 * Leash: a step that would widen the Walkers' spread past COOP_LEASH_SPREAD_*
 * on an axis is reverted on that axis (coop_walk.c). That keeps every Walker
 * at least COOP_LEASH_MARGIN_* inside the view. The margins scale with the
 * viewport (1/8 of it), so 256x224 and 320x240 both work.
 */

#include "core/types.h"

#define COOP_LEASH_MARGIN_X (EB_VIEWPORT_WIDTH / 8)
#define COOP_LEASH_MARGIN_Y (EB_VIEWPORT_HEIGHT / 8)
#define COOP_LEASH_SPREAD_X (EB_VIEWPORT_WIDTH - 2 * COOP_LEASH_MARGIN_X)
#define COOP_LEASH_SPREAD_Y (EB_VIEWPORT_HEIGHT - 2 * COOP_LEASH_MARGIN_Y)

/* End of coop_walk_leader_tick (co-op only): move the view for this frame. In
 * co-op it replaces update_leader_movement's CENTER_SCREEN call. */
void coop_camera_update(void);

/* Where IS_ENTITY_NEAR_LEADER measures from: the Leader in solo play (vanilla),
 * the view centre in co-op, so an NPC near another Walker doesn't despawn. */
uint16_t coop_near_x(void);
uint16_t coop_near_y(void);

#endif /* EB_COOP_COOP_CAMERA_H */

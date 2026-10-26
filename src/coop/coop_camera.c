/*
 * Local co-op camera. See coop_camera.h.
 */
#include "coop/coop_camera.h"

#include "coop/coop.h"
#include "game/game_state.h"
#include "game/overworld.h"
#include "snes/ppu.h"

#include <stdlib.h>

static uint16_t view_x(void) {
    return (uint16_t)(ppu.bg_hofs[0] + EB_VIEWPORT_CENTER_X);
}

static uint16_t view_y(void) {
    return (uint16_t)(ppu.bg_vofs[0] + EB_VIEWPORT_CENTER_Y);
}

/* The centre of the bounding box of the Leader and every independent Walker;
 * false (and nothing written) if no Walker walks independently. */
static bool walkers_midpoint(uint16_t *x, uint16_t *y) {
    int lo_x = game_state.leader_x_coord, hi_x = lo_x;
    int lo_y = game_state.leader_y_coord, hi_y = lo_y;
    bool any = false;
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        const CoopWalker *w = &coop.walkers[p];
        if (!w->active)
            continue;
        any = true;
        if (w->x < lo_x) lo_x = w->x;
        if (w->x > hi_x) hi_x = w->x;
        if (w->y < lo_y) lo_y = w->y;
        if (w->y > hi_y) hi_y = w->y;
    }
    if (any) {
        *x = (uint16_t)((lo_x + hi_x) / 2);
        *y = (uint16_t)((lo_y + hi_y) / 2);
    }
    return any;
}

/* One frame of easing: a quarter of the way plus a pixel, so it reaches 0 in
 * about a dozen frames from a screen away. */
static int16_t decay(int16_t e) {
    return (int16_t)(e - (e / 4 + (e > 0) - (e < 0)));
}

void coop_camera_update(void) {
    CoopCamera *c = &coop.camera;
    uint16_t cur_x = view_x(), cur_y = view_y();
    uint16_t tx = game_state.leader_x_coord, ty = game_state.leader_y_coord;
    bool midpoint = walkers_midpoint(&tx, &ty);
    bool moved_elsewhere = cur_x != c->last_x || cur_y != c->last_y;

    if (midpoint != c->midpoint || (midpoint && moved_elsewhere)) {
        /* Ease from where the view is now to the new target */
        c->ease_x = (int16_t)(cur_x - tx);
        c->ease_y = (int16_t)(cur_y - ty);
        if (abs(c->ease_x) > EB_VIEWPORT_WIDTH || abs(c->ease_y) > EB_VIEWPORT_HEIGHT)
            c->ease_x = c->ease_y = 0; /* a different place: cut */
    } else if (moved_elsewhere) {
        /* Following the Leader and another routine (door, teleport, a script
         * centring on an entity) owns the view: leave it to it, as vanilla */
        c->ease_x = c->ease_y = 0;
    }
    bool switched = midpoint != c->midpoint;
    c->midpoint = midpoint;

    bool easing = c->ease_x || c->ease_y;
    c->ease_x = decay(c->ease_x);
    c->ease_y = decay(c->ease_y);
    uint16_t want_x = (uint16_t)(tx + c->ease_x), want_y = (uint16_t)(ty + c->ease_y);
    /* Following the Leader, the view moves when the Leader does, as vanilla
     * (update_leader_movement), while it eases there, or on the switch (a cut) */
    bool apply = midpoint ? (want_x != cur_x || want_y != cur_y) : (game_state.leader_moved || easing || switched);
    if (apply)
        center_screen(want_x, want_y);
    c->last_x = view_x();
    c->last_y = view_y();
}

uint16_t coop_near_x(void) {
    return coop_player_count() > 1 ? view_x() : game_state.leader_x_coord;
}

uint16_t coop_near_y(void) {
    return coop_player_count() > 1 ? view_y() : game_state.leader_y_coord;
}

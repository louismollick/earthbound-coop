#ifndef EB_COOP_COOP_WALK_INTERNAL_H
#define EB_COOP_COOP_WALK_INTERNAL_H

/*
 * Shared by coop_walk.c (Walkers) and coop_companion.c (Mr. Saturn): how free
 * the overworld is this frame, and the borrowed Leader step both of them walk
 * with. Not for game code; the hooks are in coop_walk.h and coop_companion.h.
 */

#include "core/types.h"

typedef enum {
    WALK_FREE,        /* plain overworld control: Walkers step */
    WALK_PAUSED,      /* a window, text box or interaction: Walkers hold still */
    WALK_BATTLE,      /* an enemy touched the party, the swirl or a battle: Walkers hold
                       * still and stay independent, so they are back where they stood
                       * after the battle (the touch disables every entity's tick, which
                       * would otherwise read as "scripted") */
    WALK_CONTROLLED,  /* the game controls movement: Walkers hold still; once the game
                       * actually moves the party (coop_game_moves_party), chains snap and
                       * regroup */
} WalkControl;

/* Who a borrowed step is for: it picks the door rules (coop_walker_door). */
typedef enum { COOP_STEP_NONE, COOP_STEP_WALKER, COOP_STEP_COMPANION } CoopStepKind;

/* The part of a body the borrowed Leader step moves. */
typedef struct {
    uint16_t x, y, x_frac, y_frac, direction, surface, walking_style;
} CoopBody;

WalkControl coop_walk_control(void);

/* Under WALK_CONTROLLED: the game is moving the party now (the Leader moved). */
bool coop_game_moves_party(void);

/* The Leader's movement step run for body `b` (entity `slot`, held pad `pad`),
 * every Leader global put back afterwards. See coop_walk.c. */
bool coop_borrowed_step(CoopStepKind kind, uint16_t pad, CoopBody *b, int16_t slot, int16_t *touched);

/* A leash-reverted step's remaining position is clear of walls and NPCs for
 * entity `slot` stepping there from (from_x, from_y). Side-effect free. */
bool coop_leashed_position_clear(int16_t from_x, int16_t from_y, int16_t x, int16_t y, uint16_t slot);

#endif /* EB_COOP_COOP_WALK_INTERNAL_H */

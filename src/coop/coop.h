#ifndef EB_COOP_COOP_H
#define EB_COOP_COOP_H

/*
 * Local co-op: the join model (vocabulary in CONTEXT.md).
 *
 * P1 is always joined. On an unjoined P2-P4 pad, a fresh Start press joins that
 * Player; holding Select+Start on a joined P2-P4 pad for COOP_LEAVE_FRAMES
 * frames makes it leave. Heroes are dealt round-robin by join order: Hero h
 * (Ness = 0, Paula = 1, Jeff = 2, Poo = 3) belongs to the (h mod N)-th joined
 * Player, so with two Players P1 owns Ness and Jeff and P2 owns Paula and Poo.
 *
 * In solo play pads 2-4 are always 0, so nothing here ever changes and the game
 * stays bit-identical to vanilla. Every co-op behaviour elsewhere is gated on
 * coop_player_count() > 1.
 *
 * The state is one serialized struct (savestate SECTION_COOP). Joins are about
 * the people at the machine, so starting a new game or loading a file from the
 * file select keeps them; only a savestate load replaces them, with whatever the
 * savestate held.
 */

#include "core/types.h"
#include "platform/platform.h"

#define COOP_HERO_COUNT   4    /* Ness, Paula, Jeff, Poo (party member ids 1-4) */
#define COOP_LEAVE_FRAMES 120  /* Select+Start held this long (2 s) leaves */

typedef struct {
    uint8_t player_count;                       /* joined Players, 1..PLATFORM_MAX_PLAYERS */
    uint8_t join_order[PLATFORM_MAX_PLAYERS];   /* Players (0 = P1) in join order; [0] is P1,
                                                 * entries past player_count are 0 */
    uint8_t joined[PLATFORM_MAX_PLAYERS];       /* 1 if Player p is joined */
    uint8_t leave_hold[PLATFORM_MAX_PLAYERS];   /* consecutive frames Player p has held Select+Start */
    uint8_t hero_owner[COOP_HERO_COUNT];        /* Owner (Player) of Hero h; derived from join_order */
} CoopState;

extern CoopState coop;

/* Once per game frame, where the pad is sampled (host_process_frame): join and
 * leave from each Player's held / newly pressed buttons. Frames that must see no
 * input (a capture unwind) pass zeros. */
void coop_tick(const uint16_t held[PLATFORM_MAX_PLAYERS], const uint16_t pressed[PLATFORM_MAX_PLAYERS]);

/* Join / leave Player p (0 = P1; P1 can't leave). No-op if already in that state. */
void coop_join(int player);
void coop_leave(int player);

int coop_player_count(void);
bool coop_player_joined(int player);

/* The Owner of Hero h (0 = Ness .. 3 = Poo). */
int coop_hero_owner(int hero);

/* The party member id (1-4) of Player p's Walker, or 0 if p has none (a
 * Spectator). M0 rule: the Player's first owned Hero present in the Party, in
 * Party order. */
uint8_t coop_walker(int player);

#endif /* EB_COOP_COOP_H */

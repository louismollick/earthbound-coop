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
#include "game/game_state.h"
#include "game/position_buffer.h"
#include "platform/platform.h"

#define COOP_HERO_COUNT   4    /* Ness, Paula, Jeff, Poo (party member ids 1-4) */
#define COOP_LEAVE_FRAMES 120  /* Select+Start held this long (2 s) leaves */

/*
 * One Player's non-Leader Walker (coop_walk.h): the Leader-like state the
 * Walker step swaps into game_state's leader fields, and the position trail
 * that Player's other owned members follow. Only meaningful while `active`
 * (the chain is walking independently); while inactive the chain is snapped
 * onto the Leader's trail and runs vanilla follower code.
 */
typedef struct {
    uint16_t x, y;                 /* like game_state.leader_x/y_coord */
    uint16_t x_frac, y_frac;       /* like game_state.leader_x/y_frac */
    uint16_t direction;            /* like game_state.leader_direction */
    uint16_t surface;              /* like game_state.trodden_tile_type */
    uint16_t walking_style;        /* like game_state.walking_style */
    uint16_t moved;                /* like game_state.leader_moved, for this frame */
    int16_t touched;               /* entities.collided_objects[23] after this frame's
                                    * step: the NPC/enemy slot the Walker ran into, or -1 */
    uint8_t active;                /* 1: independent; 0: snapped to the Leader's trail */
    uint8_t head;                  /* trail write index, like game_state.position_buffer_index */
    uint8_t chain[TOTAL_PARTY_COUNT]; /* party_characters indices: [0] the Walker, then the
                                    * members trailing it, 0xFF-terminated (set on unsnap) */
    uint8_t ring_index[TOTAL_PARTY_COUNT]; /* trail read index per chain[] entry,
                                    * like char_struct.position_index */
    uint8_t shown[TOTAL_PARTY_COUNT]; /* the trail entry each chain[] member stands on
                                    * (members past the Walker), so they can be put back
                                    * there after refresh_party_entities moved them */
    PositionBufferEntry trail[POSITION_BUFFER_SIZE]; /* like pb.player_position_buffer */
} CoopWalker;

/*
 * The co-op camera (coop_camera.h). It eases between the Walkers' midpoint and
 * the Leader; `last` lets it notice when other code (a door, a teleport, a
 * script) moved the view.
 */
typedef struct {
    int16_t ease_x, ease_y;        /* view centre minus target, decaying to 0 */
    uint16_t last_x, last_y;       /* view centre after this frame's update */
    uint8_t midpoint;              /* 1: the target was the Walkers' midpoint, 0: the Leader */
    uint8_t unused;                /* explicit padding (savestates hash every byte) */
} CoopCamera;

typedef struct {
    uint8_t player_count;                       /* joined Players, 1..PLATFORM_MAX_PLAYERS */
    uint8_t join_order[PLATFORM_MAX_PLAYERS];   /* Players (0 = P1) in join order; [0] is P1,
                                                 * entries past player_count are 0 */
    uint8_t joined[PLATFORM_MAX_PLAYERS];       /* 1 if Player p is joined */
    uint8_t leave_hold[PLATFORM_MAX_PLAYERS];   /* consecutive frames Player p has held Select+Start */
    uint8_t hero_owner[COOP_HERO_COUNT];        /* Owner (Player) of Hero h; derived from join_order */
    uint16_t prev_held[PLATFORM_MAX_PLAYERS];   /* each pad as coop_tick last saw it: join edges are
                                                 * computed from this serialized history, not the
                                                 * platform's, so a savestate load can't fake or eat one */
    uint16_t walk_pad[PLATFORM_MAX_PLAYERS];    /* each pad's held buttons for this game frame's
                                                 * Walker steps (0 on capture-unwind frames) */
    /* Input focus (coop_input.h) */
    uint8_t focus;                              /* the Player (0-3) or COOP_FOCUS_ALL whose pad
                                                 * feeds core.pad1 now */
    uint8_t unused_focus;                       /* explicit padding (savestates hash every byte) */
    uint8_t focus_locked;                       /* overworld: `focus` holds the lock */
    uint8_t focus_in_battle;                    /* the last feed was in a battle (entry edge) */
    uint16_t focus_new;                         /* this frame's new presses of the focused pad(s),
                                                 * from prev_held: coop_pad_new() */
    /* Battle (coop_battle.h) */
    uint16_t rotation;                          /* Battle rotation: Solo Chapter battle turns
                                                 * started so far, carried across battles */
    uint8_t claims[PLATFORM_MAX_PLAYERS];       /* Players who pressed A for the next command
                                                 * menu, in press order (claim_count of them) */
    uint8_t claim_count;
    uint8_t claiming;                           /* 1 while this turn's command menus are being
                                                 * claimed (the co-op menu loop) */
    uint8_t menu_next;                          /* party slot + 1 whose menu opens next without a
                                                 * claim (B: back or retry), 0 = none */
    uint8_t choosers;                           /* while the battle waits for a claim: bit p set if
                                                 * Player p has a Hero left to choose for */
    /* Non-Leader Walkers by Player. RAM: PLATFORM_MAX_PLAYERS x ~2.1 KB (the
     * 256-entry trail is 2 KB), about 8.4 KB, all of it in savestates. */
    CoopWalker walkers[PLATFORM_MAX_PLAYERS];
    CoopCamera camera;
} CoopState;

extern CoopState coop;

/* Once per game frame, where the pad is sampled (host_process_frame): join and
 * leave from each Player's held buttons (edges against coop.prev_held). Not
 * called on capture-unwind frames, so an unwind neither releases a hold nor
 * resets a leave counter. */
void coop_tick(const uint16_t held[PLATFORM_MAX_PLAYERS]);

/* Instead of coop_tick on a capture-unwind frame: the Walkers get no input. */
void coop_unwind_frame(void);

/* Join / leave Player p (0 = P1; P1 can't leave). No-op if already in that state. */
void coop_join(int player);
void coop_leave(int player);

int coop_player_count(void);
bool coop_player_joined(int player);

/* The Owner of Hero h (0 = Ness .. 3 = Poo). */
int coop_hero_owner(int hero);

/* The party member id (1-4) of Player p's Walker, or 0 if p has none (a
 * Spectator): the Player's first owned Hero that is in the Party and conscious
 * (not unconscious or diamondized),
 * in Party order (game_state.party_order). Derived every call, so it follows
 * joins, leaves, KOs, revives and party changes by itself.
 * TODO(M4): a Player with no such Hero stands in for a Guest if there is one. */
uint8_t coop_walker(int player);

/* Hero id (1-4) at Party position i (party_order) if it is a Hero who can walk
 * (not unconscious or diamondized), else 0. */
uint8_t coop_conscious_hero(int i);

/* The Player who owns the Leader (party_order[0]); P1 (0) if the Leader is a
 * Guest or there is no Party. */
int coop_leader_owner(void);

#endif /* EB_COOP_COOP_H */

#ifndef EB_NET_NET_H
#define EB_NET_NET_H

/*
 * Online co-op: input lockstep in a star around the Host (ADR 0002,
 * docs/coop-online.md), over UDP or through a relay (transport.h). Every machine runs the same deterministic game; only pads
 * travel. The Host is P1 and the single source of truth for each frame's input set
 * (four pads plus one session event). Clients send their local pad to the Host
 * tagged for frame f + D (D = input delay); the Host broadcasts confirmed sets; every
 * machine runs frame f only once it holds the confirmed set for f. No rollback.
 *
 * The integration point is platform_input_poll (sdl2_input.c): in netplay it calls
 * net_frame(), which blocks (pumping SDL events) until this frame's set is here and
 * installs all four pads from it. Frames of a capture unwind (host_capture_unwinding)
 * are not net frames: every machine unwinds identically with no input, so they skip
 * net_frame entirely.
 */

#include <stdbool.h>
#include <stdint.h>

#include "platform/platform.h"

#define NET_DEFAULT_PORT        7744
#define NET_DEFAULT_INPUT_DELAY 3   /* and the auto delay's floor */

typedef struct {
    int host_port;          /* > 0: host a Session on this UDP port */
    const char *join;       /* "ADDR[:PORT]": join the Session there */
    bool host_room;         /* host a Session in a room at `relay` */
    const char *join_room;  /* join the relay room of this invite ("RELAY/CODE", or a CODE at `relay`) */
    const char *relay;      /* the relay (a URL or host name) */
    int input_delay;        /* Host: frames of input delay, 0 = auto from the pings (clients take the Host's) */
    int local_players;      /* Players at this machine (1-4): the Host is P1..PN, a client
                             * gets the next N free Players */
    uint32_t end_frame;     /* Host, tests: every machine quits after running this frame (0 = never) */
    int wait_players;       /* Host, tests: the game waits while fewer Players are in (0/1 = don't) */
} NetConfig;

/* Hooks net_frame needs from the input layer. */
typedef struct {
    void (*pump)(void);            /* handle pending SDL events (quit, keys) */
    /* this machine's pads (local pad k = its k-th Player), sampled once per net frame */
    void (*sample_local)(uint16_t pads[PLATFORM_MAX_PLAYERS], int count);
    void (*present)(void);         /* redraw the screen while a joiner waits for the game (overlay) */
} NetInputHooks;

/* Open the socket and, for a client, connect (blocks up to 10 s for the Host's
 * answer). Call after the platform layer is up and before game_init: a client
 * redirects its SRAM to a session temp file here so it never writes the local
 * save. Prints the reason and returns false on failure. */
bool net_start(const NetConfig *cfg);

bool net_active(void);
/* Why the last net_start failed. */
const char *net_error(void);

/* What the status overlay shows (net/ui.c). */
typedef struct {
    bool active, host;
    bool joined;            /* client: playing (not still waiting for the Host's game) */
    int delay;              /* frames of input delay now */
    char invite[160];       /* relay Sessions: "RELAY/CODE" */
    const char *relay_lost; /* Host: why the relay connection ended, or NULL */
    int npeers;             /* Host: the remote machines in the Session; client: 1 (itself) */
    struct {
        int player;         /* its first Player (0 = P1) */
        int rtt;            /* round trip to the Host in ms (0 = not measured yet) */
    } peer[PLATFORM_MAX_PLAYERS];
} NetStatus;
void net_status(NetStatus *st);

/* One net frame (see above): fills pads[] with the confirmed set of the next frame
 * and applies its session event. Blocks until the set is available. */
void net_frame(uint16_t pads[PLATFORM_MAX_PLAYERS], const NetInputHooks *hooks);

/* atexit: say goodbye (the Host first lets clients collect the last frames). */
void net_shutdown(void);

/* sdl2_input.c: the pads of the last poll and the one before. Game code reads
 * button edges from them (platform_input_get_pad_new) between polls, and they
 * aren't in the savestate, so a joiner gets the Host's along with the game. */
void platform_input_get_state(uint16_t pads[PLATFORM_MAX_PLAYERS], uint16_t prev[PLATFORM_MAX_PLAYERS]);
void platform_input_set_state(const uint16_t pads[PLATFORM_MAX_PLAYERS], const uint16_t prev[PLATFORM_MAX_PLAYERS]);

/* sdl2_input_script.c: print the PLAYERS line; write a screenshot PNG. */
void input_script_print_players(void);
void input_script_shot(const char *path);

#endif /* EB_NET_NET_H */

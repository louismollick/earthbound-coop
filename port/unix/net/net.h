#ifndef EB_NET_NET_H
#define EB_NET_NET_H

/*
 * Online co-op: input lockstep over UDP in a star around the Host (ADR 0002,
 * docs/coop-online.md). Every machine runs the same deterministic game; only pads
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
#define NET_DEFAULT_INPUT_DELAY 3

typedef struct {
    int host_port;          /* > 0: host a Session on this UDP port */
    const char *join;       /* "ADDR[:PORT]": join the Session there */
    int input_delay;        /* Host: frames of input delay (clients take the Host's) */
    uint32_t end_frame;     /* Host, tests: every machine quits after running this frame (0 = never) */
    int wait_players;       /* Host: the game waits until this many Players are in (0/1 = don't) */
} NetConfig;

/* Hooks net_frame needs from the input layer. */
typedef struct {
    void (*pump)(void);            /* handle pending SDL events (quit, keys) */
    uint16_t (*sample_local)(void);/* this machine's pad, sampled once per net frame */
} NetInputHooks;

/* Open the socket and, for a client, connect (blocks up to 10 s for the Host's
 * answer). Call after the platform layer is up and before game_init: a client
 * redirects its SRAM to a session temp file here so it never writes the local
 * save. Prints the reason and returns false on failure. */
bool net_start(const NetConfig *cfg);

bool net_active(void);

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

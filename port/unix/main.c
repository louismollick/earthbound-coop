#include <SDL.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "platform/platform.h"
#include "game_main.h"
#include "game/audio.h"
#include "core/log.h"
#include "core/state_dump.h"
#include "game/smooth_camera.h"
#include "coop/coop.h"
#include "net/net.h"

/* Unix-specific: set save file path (defined in sdl2_save.c) */
void platform_save_set_path(const char *path);
/* Unix-specific: savestate slot file prefix (defined in sdl2_savestate.c) */
void platform_savestate_set_path(const char *prefix);
/* Unix-specific: scripted input playback (defined in sdl2_input_script.c) */
bool input_script_open(const char *path);
bool input_script_open_session(const char *path);
void input_script_root_boundary(void);
/* Unix-specific: headless video/audio recording (defined in sdl2_record.c) */
bool record_open_video(const char *path);
bool record_open_audio(const char *path);
void record_start_audio(void);
void record_set_paused(bool paused);
bool record_active(void);
#include "verify/verify.h"

/* Cleanup handler registered with atexit() — runs on any exit() call. */
static void platform_cleanup(void) {
    platform_timer_shutdown();
    platform_audio_shutdown();
    platform_input_shutdown();
    platform_video_shutdown();
    SDL_Quit();
}

int main(int argc, char *argv[]) {
    const char *verify_rom_path = NULL;
    bool savestate_selftest = false;
    const char *coldload_prefix = NULL;
    int players = 1;
    NetConfig net = { .input_delay = NET_DEFAULT_INPUT_DELAY, .local_players = 1 };

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--verify") == 0 && i + 1 < argc) {
            verify_rom_path = argv[++i];
        } else if (strcmp(argv[i], "--selftest-savestate") == 0) {
            /* Run the savestate save->load->save round-trip self-test and exit.
             * Implies headless so it neither opens a window nor plays the game. */
            savestate_selftest = true;
            platform_headless = true;
        } else if (strcmp(argv[i], "--selftest-coldload") == 0 && i + 1 < argc) {
            /* Load PREFIX.0/.1 in this fresh process, re-save, compare; then exit. */
            coldload_prefix = argv[++i];
            platform_headless = true;
        } else if (strcmp(argv[i], "--headless") == 0) {
            platform_headless = true;
        } else if (strcmp(argv[i], "--frames") == 0 && i + 1 < argc) {
            platform_max_frames = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--save") == 0 && i + 1 < argc) {
            platform_save_set_path(argv[++i]);
        } else if (strcmp(argv[i], "--input") == 0 && i + 1 < argc) {
            if (!input_script_open(argv[++i]))
                return 1;
        } else if (strcmp(argv[i], "--session") == 0 && i + 1 < argc) {
            /* Interactive playtest: read commands from a FIFO, block when idle */
            if (!input_script_open_session(argv[++i]))
                return 1;
        } else if (strcmp(argv[i], "--record-video") == 0 && i + 1 < argc) {
            /* Raw rgb24 frames to a file/FIFO (playtest/pt.py video) */
            if (!record_open_video(argv[++i]))
                return 1;
        } else if (strcmp(argv[i], "--record-audio") == 0 && i + 1 < argc) {
            /* Raw s16le stereo SPC700 output, 534 samples per frame */
            if (!record_open_audio(argv[++i]))
                return 1;
        } else if (strcmp(argv[i], "--record-paused") == 0) {
            /* Start recording paused; the script's 'record on' resumes it */
            record_set_paused(true);
        } else if (strcmp(argv[i], "--smooth-camera") == 0) {
            /* Presentation only: sub-pixel scenery scroll while walking
             * (game/smooth_camera.h). Also EB_SMOOTH_CAMERA=1. */
            smooth_camera_enabled = true;
        } else if (strcmp(argv[i], "--players") == 0 && i + 1 < argc) {
            /* Co-op test flag: auto-join P2..PN at startup, in order */
            players = atoi(argv[++i]);
            if (players < 1 || players > PLATFORM_MAX_PLAYERS) {
                fprintf(stderr, "--players takes 1-%d\n", PLATFORM_MAX_PLAYERS);
                return 1;
            }
        } else if (strcmp(argv[i], "--host") == 0 && i + 1 < argc) {
            /* Online co-op: host a Session on this UDP port (docs/coop-online.md) */
            net.host_port = atoi(argv[++i]);
            if (net.host_port <= 0 || net.host_port > 65535) {
                fprintf(stderr, "--host takes a UDP port (default %d)\n", NET_DEFAULT_PORT);
                return 1;
            }
        } else if (strcmp(argv[i], "--join") == 0 && i + 1 < argc) {
            /* Online co-op: join the Session at ADDR[:PORT] */
            net.join = argv[++i];
        } else if (strcmp(argv[i], "--input-delay") == 0 && i + 1 < argc) {
            net.input_delay = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--local-players") == 0 && i + 1 < argc) {
            /* Online co-op: Players at this machine (keyboard, IJKL layout, controllers) */
            net.local_players = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--net-wait-players") == 0 && i + 1 < argc) {
            /* Host: the game waits until N Players (the Host included) are in */
            net.wait_players = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--net-end-frame") == 0 && i + 1 < argc) {
            /* Test flag (Host): every machine quits after this net frame */
            net.end_frame = (uint32_t)strtoul(argv[++i], NULL, 10);
        } else if (strcmp(argv[i], "--skip-intro") == 0) {
            platform_skip_intro = true;
        } else if (strcmp(argv[i], "--verbose") == 0) {
            verbose_level++;
        } else if (argv[i][0] == '-' && argv[i][1] == 'v' && argv[i][1] != '-') {
            /* Count v's: -v = 1, -vv = 2, -vvv = 3 */
            for (const char *p = &argv[i][1]; *p == 'v'; p++)
                verbose_level++;
        } else {
            fprintf(stderr, "Unknown option: %s\n", argv[i]);
            fprintf(stderr, "Usage: %s [--save FILE] [--input SCRIPT] [--session FIFO] [--headless] [--record-video FILE] [--record-audio FILE] [--record-paused] [--frames N] [--smooth-camera] [--players N] [--host PORT] [--join ADDR[:PORT]] [--input-delay N] [--local-players N] [--verbose] [--verify ROM] [--selftest-savestate] [--selftest-coldload PREFIX]\n",
                    argv[0]);
            return 1;
        }
    }

    bool netplay = net.host_port > 0 || net.join;
    if (net.host_port > 0 && net.join) {
        fprintf(stderr, "--host and --join are exclusive\n");
        return 1;
    }
    if (netplay && (players > 1 || savestate_selftest || coldload_prefix)) {
        fprintf(stderr, "--host/--join can't be combined with --players or the self-tests\n");
        return 1;
    }

    if (record_active() && !platform_headless) {
        fprintf(stderr, "--record-video/--record-audio need --headless\n");
        return 1;
    }

    /* Initialize SDL */
    uint32_t sdl_flags = SDL_INIT_TIMER;
    if (!platform_headless) {
        sdl_flags |= SDL_INIT_VIDEO;
#ifdef EB_ENABLE_AUDIO
        sdl_flags |= SDL_INIT_AUDIO;
#endif
    }
    if (SDL_Init(sdl_flags) < 0) {
        fprintf(stderr, "SDL_Init failed: %s\n", SDL_GetError());
        return 1;
    }

    /* Initialize subsystems */
    if (!platform_video_init()) {
        fprintf(stderr, "Video init failed: %s\n", SDL_GetError());
        SDL_Quit();
        return 1;
    }
    platform_input_init();
    platform_save_init();
    atexit(platform_cleanup);
    platform_timer_init();

    /* Online co-op: connect before game_init (a client moves its SRAM to a temp
     * file first, so it never writes the local save) */
    if (netplay) {
        if (!net_start(&net))
            return 1;
        atexit(net_shutdown); /* runs before platform_cleanup */
    }

    /* Initialize game systems */
    game_init();
    /* The Host's local Players are in from the start, like --players */
    if (net.host_port > 0)
        players = net.local_players;
    for (int p = 1; p < players; p++)
        coop_join(p);

    /* Savestate round-trip self-test: prove state_dump_load() reads back exactly
     * what state_dump_save() wrote (byte-identical), then exit. Runs against the
     * post-game_init boot state. */
    if (savestate_selftest) {
        bool ok = state_dump_roundtrip_test();
        fprintf(stderr, "savestate round-trip self-test: %s\n", ok ? "PASS" : "FAIL");
        bool ok_pert = state_dump_perturb_test();
        fprintf(stderr, "savestate perturb (cold-load) self-test: %s\n", ok_pert ? "PASS" : "FAIL");
        bool ok_cs = state_dump_crashsafe_test();
        fprintf(stderr, "savestate crash-safe self-test: %s\n", ok_cs ? "PASS" : "FAIL");
        bool ok_ap = state_dump_asset_pointer_test();
        fprintf(stderr, "savestate asset-pointer self-test: %s\n", ok_ap ? "PASS" : "FAIL");
        bool ok_rj = state_dump_reject_test();
        fprintf(stderr, "savestate reject (bad size / layout id / mode stack / index range / PSI pairing / corrupt) self-test: %s\n", ok_rj ? "PASS" : "FAIL");
        exit((ok && ok_pert && ok_cs && ok_ap && ok_rj) ? 0 : 1);
    }

    if (coldload_prefix) {
        platform_savestate_set_path(coldload_prefix);
        bool ok = state_dump_coldload_test();
        fprintf(stderr, "savestate cold-load self-test: %s\n", ok ? "PASS" : "FAIL");
        exit(ok ? 0 : 1);
    }

    /* Initialize audio (loads audio packs from embedded assets) */
    if (!platform_headless)
        platform_audio_init();
    else
        record_start_audio(); /* the emulator only, when recording audio */

#ifdef EB_ENABLE_VERIFY
    if (verify_rom_path) {
        if (!verify_init(verify_rom_path)) {
            fprintf(stderr, "Failed to initialize verification with ROM: %s\n", verify_rom_path);
        }
    }
#else
    (void)verify_rom_path;
#endif

    /* Start frame timer, then run the single top-level game loop:
     * advance the game one frame (game_loop_step), then perform the one
     * per-frame host yield (host_process_frame). Restart-on-game-over is
     * handled inside the step machine, so there is no restart wrapper.
     * See docs/plans/savestate-unified-loop.md. */
    platform_timer_frame_start();

    while (!platform_input_quit_requested()) {
        game_loop_step();
        host_process_frame();
        host_root_boundary(); /* root boundary: perform any pending torn-safe capture */
        input_script_root_boundary();
    }

#ifdef EB_ENABLE_VERIFY
    verify_shutdown();
#endif

    return 0;
}

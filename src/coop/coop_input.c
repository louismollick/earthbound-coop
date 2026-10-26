/*
 * Local co-op input focus. See coop_input.h for the model.
 */
#include "coop/coop_input.h"

#include "coop/coop.h"
#include "coop/coop_battle.h"
#include "coop/coop_companion.h"
#include "coop/coop_look.h"
#include "coop/coop_walk.h"
#include "core/memory.h"
#include "core/mode_stack.h"
#include "entity/entity.h"
#include "game/audio.h"
#include "game/game_state.h"
#include "game/overworld.h"
#include "game/window.h"
#include "include/constants.h"
#include "snes/ppu.h"

static bool mode_on_stack(GameMode mode) {
    for (int i = 0; i < g_mode_stack.depth; i++)
        if (g_mode_stack.mode[i] == mode)
            return true;
    return false;
}

static bool in_battle(void) {
    return ow.battle_mode || mode_on_stack(GAME_MODE_BATTLE);
}

/* Overworld play: the root overworld mode past its boot stages (not the title,
 * file select or a game-over reboot, which P1 drives). */
static bool overworld_play(void) {
    if (g_mode_stack.depth < 1 || g_mode_stack.mode[0] != GAME_MODE_OVERWORLD)
        return false;
    uint8_t phase = g_mode_stack.state[0].overworld.phase;
    return phase != OWP_BOOT_SETUP && phase != OWP_BOOT_AWAIT && phase != OWP_BOOT_FLUSH;
}

/* The Party is idle: the player could walk the Leader now. Releases the lock.
 * The same predicate as the playtest harness's idle (sdl2_input_script.c). */
static bool party_idle(void) {
    if (g_mode_stack.depth != 1 || g_mode_stack.mode[0] != GAME_MODE_OVERWORLD)
        return false;
    if (ow.battle_mode || ow.battle_swirl_countdown || ow.enemy_has_been_touched)
        return false;
    if (ow.pending_interactions || ow.input_disable_frame_counter)
        return false;
    if (entities.tick_callback_hi[PARTY_LEADER_ENTITY_INDEX] & (OBJECT_TICK_DISABLED | OBJECT_MOVE_DISABLED))
        return false;
    if (game_state.walking_style == WALKING_STYLE_ESCALATOR || game_state.walking_style == WALKING_STYLE_STAIRS)
        return false;
    if (game_state.camera_mode || ow.demo_frames_left || (ow.player_movement_flags & 0x02))
        return false;
    if ((ppu.inidisp & 0x80) || (ppu.inidisp & 0x0F) != 0x0F)
        return false;
    return true;
}

/* A press now may take the lock: the Party is idle, no window is open, no
 * queued interaction or demo is about to run, and the Leader isn't on the
 * bicycle (A/L there dismount: a Leader-only action, so its Owner keeps the
 * focus). */
static bool capture_eligible(void) {
    return party_idle() && !any_window_open() && !(ow.demo_recording_flags & 0x4000) &&
           ow.current_queued_interaction == ow.next_queued_interaction &&
           game_state.walking_style != WALKING_STYLE_BICYCLE;
}

/* The OR of every joined Player's v[] (focus ALL), or Player f's. */
static uint16_t focused(const uint16_t v[PLATFORM_MAX_PLAYERS], int f) {
    if (f < PLATFORM_MAX_PLAYERS)
        return v[f];
    uint16_t all = 0;
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++)
        if (coop_player_joined(p))
            all |= v[p];
    return all;
}

#define COMPANION_SFX 114 /* SFX::MYSTERIOUS_2, as Saturn Valley's Mr. Saturns */

/* The buttons with which Player p may take the overworld lock: all of
 * COOP_CAPTURE_BUTTONS with a Walker, A and L while walking a visible
 * Companion (it can only Check/Talk), none for a Spectator. */
static uint16_t capture_buttons(int p) {
    if (coop_walker(p))
        return COOP_CAPTURE_BUTTONS;
    return coop_companion_entity(p) >= 0 ? (PAD_A | PAD_L) : 0;
}

/* A Companion's Player drives this focus: their A is L (Check/Talk, and a
 * confirm or text advance like A), so the pause menu never opens for them. */
static bool companion_focus(int f) {
    return f < PLATFORM_MAX_PLAYERS && coop.focus_locked && coop_companion(f);
}

static uint16_t a_as_l(uint16_t pad) {
    return (pad & PAD_A) ? (uint16_t)((pad & ~PAD_A) | PAD_L) : pad;
}

/* This frame's focus. `pressed`: each Player's new presses. */
static int decide_focus(const uint16_t pressed[PLATFORM_MAX_PLAYERS]) {
    if (coop_player_count() <= 1) {
        coop.focus_locked = 0;
        coop.focus_in_battle = 0;
        return 0;
    }
    if (in_battle()) {
        /* Battle entry ends the lock; from then on the battle routine's
         * own state says whose pad it is */
        coop.focus_in_battle = 1;
        coop.focus_locked = 0;
        return coop_battle_focus();
    }
    coop.focus_in_battle = 0;
    if (!overworld_play()) {
        coop.focus_locked = 0;
        return 0;
    }
    if (coop.focus_locked && (party_idle() || !coop_player_joined(coop.focus)))
        coop.focus_locked = 0;
    if (!coop.focus_locked && capture_eligible()) {
        for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
            if (pressed[p] & capture_buttons(p)) {
                coop.focus_locked = 1;
                return p;
            }
        }
    }
    return coop.focus_locked ? coop.focus : coop_leader_owner();
}

uint16_t coop_input_feed(uint16_t p1_pad, bool unwinding) {
    uint16_t held[PLATFORM_MAX_PLAYERS], pressed[PLATFORM_MAX_PLAYERS];
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        held[p] = p == 0 ? p1_pad : platform_input_get_pad_n(p);
        /* Edges against co-op's serialized history (coop_tick updates it after
         * this), so a savestate load can't fake or eat a press */
        pressed[p] = unwinding ? 0 : (uint16_t)(held[p] & ~coop.prev_held[p]);
    }
    int want = decide_focus(pressed);
    bool remap = companion_focus(want);
    if (want != coop.focus) {
        uint16_t prev = focused(coop.prev_held, want);
        memory_rebase_joypad(remap ? a_as_l(prev) : prev);
        coop.focus = (uint8_t)want;
    }
    coop.focus_new = focused(pressed, want);
    if (coop.focus_in_battle) {
        coop_battle_note_claims(pressed, want);  /* A queues for the next command menu */
        coop_battle_retitle();  /* the open command menu's tag names its Player */
    }
    uint16_t pad = focused(held, want);
    if (remap) {
        coop.focus_new = a_as_l(coop.focus_new);
        pad = a_as_l(pad);
    }
    return pad;
}

int coop_focus(void) {
    return coop.focus;
}

bool coop_focus_locked(void) {
    return coop.focus_locked != 0;
}

void coop_all_focus_edges(void) {
    if (coop.focus != COOP_FOCUS_ALL)
        return;
    /* memory_update_joypad's edges of the OR are a subset of the OR of edges */
    uint16_t extra = (uint16_t)(coop.focus_new & 0xFFF0 & ~core.pad1_pressed);
    if (!extra)
        return;
    if (!core.pad1_pressed)
        ow.player_has_done_something_this_frame++;
    core.pad1_pressed |= extra;
    core.pad1_autorepeat |= extra;
}

uint16_t coop_pad_new(void) {
    return coop_player_count() > 1 ? coop.focus_new : platform_input_get_pad_new();
}

/* ---- The Leader's step ---- */

static bool leader_pad_swapped;
static uint16_t leader_saved_held, leader_saved_pressed;

void coop_leader_pad_enter(void) {
    int owner = coop_leader_owner();
    /* Demo playback (a door, stair or escalator approach walk) feeds core.pad1
     * the scripted pad: that is the game moving the Leader, not the locker, so
     * it stays. Only a human-driven step reads the Owner's pad. */
    leader_pad_swapped = coop.focus != owner && !(ow.demo_recording_flags & 0x4000);
    if (!leader_pad_swapped)
        return;
    leader_saved_held = core.pad1_held;
    leader_saved_pressed = core.pad1_pressed;
    core.pad1_held = coop.walk_pad[owner] & 0xFFF0;
    core.pad1_pressed = 0;
}

void coop_leader_pad_leave(void) {
    if (!leader_pad_swapped)
        return;
    core.pad1_held = leader_saved_held;
    core.pad1_pressed = leader_saved_pressed;
    leader_pad_swapped = false;
}

/* ---- Talk to / Check ---- */

uint32_t coop_interact(uint32_t (*fn)(void)) {
    int p = coop.focus;
    CoopWalkerInfo w;
    if (coop_player_count() > 1 && p < PLATFORM_MAX_PLAYERS && coop_companion(p))
        return coop_companion_interact(p, fn);
    if (coop_player_count() <= 1 || p >= PLATFORM_MAX_PLAYERS || !coop_walker_info(p, &w) || !w.independent)
        return fn();
    uint16_t lx = game_state.leader_x_coord, ly = game_state.leader_y_coord;
    uint16_t ldir = game_state.leader_direction, lslot = game_state.current_party_members;
    game_state.leader_x_coord = w.x;
    game_state.leader_y_coord = w.y;
    game_state.leader_direction = w.direction;
    game_state.current_party_members = (uint16_t)w.entity;
    uint32_t text = fn();
    /* The search turns the "Leader" to face what it found: that was the Walker */
    coop.walkers[p].direction = game_state.leader_direction;
    game_state.leader_x_coord = lx;
    game_state.leader_y_coord = ly;
    game_state.leader_direction = ldir;
    game_state.current_party_members = lslot;
    return text;
}

bool coop_interact_muted(uint32_t text) {
    int p = coop.focus;
    if (p >= PLATFORM_MAX_PLAYERS || !coop_companion(p) || coop_look_only(text))
        return false;
    /* No text and no window (talk_to / check_action opened the empty one) */
    close_window(WINDOW_TEXT_STANDARD);
    play_sfx(COMPANION_SFX);
    return true;
}

/* ---- Menus ---- */

uint16_t coop_char_select_index(uint16_t index, uint16_t mode, uint8_t check_valid_id) {
    /* Mode 2 is "Whom?" (a target, not the user) */
    if (coop_player_count() <= 1 || mode == 2 || coop.focus >= PLATFORM_MAX_PLAYERS || in_battle())
        return index;
    uint8_t id = coop_walker(coop.focus);
    if (!id)
        return index;
    uint8_t n = game_state.player_controlled_party_count & 0xFF;
    for (uint16_t i = 0; i < n && i < TOTAL_PARTY_COUNT; i++) {
        if ((game_state.party_members[i] & 0xFF) != id)
            continue;
        if (check_valid_id != CS_CHECKVALID_NONE && !cs_invoke_check_valid(check_valid_id, id))
            return index;
        return i;
    }
    return index;
}

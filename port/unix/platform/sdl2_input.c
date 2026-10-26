#include "platform/platform.h"
#include "include/pad.h"
#include <SDL.h>
#include <signal.h>
#include <string.h>

/*
 * Input: one pad per Player (P1-P4, PLATFORM_MAX_PLAYERS).
 *
 * P1 = the keyboard's main layout (arrows, X/Z = A/B, S/A = X/Y, Q/W = L/R,
 * Return = Start, Right Shift = Select) OR'd with the first connected game
 * controller. P2 = a second keyboard layout (I/J/K/L = Up/Left/Down/Right,
 * U/O = A/B, P = Start, [ = Select) OR'd with the second controller. P3/P4 =
 * the third/fourth controller. Controllers take the first free Player slot
 * when they connect, so they're assigned in connection order. An input script
 * (sdl2_input_script.c) replaces all four pads, so scripted runs never see real
 * keys or controllers; headless runs don't open controllers at all.
 */
static uint16_t pad_state[PLATFORM_MAX_PLAYERS];
static uint16_t pad_prev[PLATFORM_MAX_PLAYERS];
static uint16_t key_state[2];                           /* keyboard layouts: P1, P2 */
static SDL_GameController *controllers[PLATFORM_MAX_PLAYERS];  /* by Player */
static uint16_t aux_state;
static volatile sig_atomic_t quit_requested;

/* Scripted playback (sdl2_input_script.c) */
bool input_script_active(void);
void input_script_next(uint16_t pads[PLATFORM_MAX_PLAYERS], uint16_t *aux);
/* Headless recording (sdl2_record.c) */
void record_frame(void);

/* Global mode flags */
bool platform_headless = false;
bool platform_skip_intro = false;
int platform_max_frames = 0;

static void signal_handler(int sig) {
    (void)sig;
    quit_requested = 1;
}

bool platform_input_init(void) {
    memset(pad_state, 0, sizeof(pad_state));
    memset(pad_prev, 0, sizeof(pad_prev));
    memset(key_state, 0, sizeof(key_state));
    aux_state = 0;
    quit_requested = 0;
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    SDL_InitSubSystem(SDL_INIT_GAMECONTROLLER);
    return true;
}

void platform_input_shutdown(void) {
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        if (controllers[p])
            SDL_GameControllerClose(controllers[p]);
        controllers[p] = NULL;
    }
}

/* SDL device index `index` connected: give it the first free Player slot */
static void controller_added(int index) {
    if (platform_headless || !SDL_IsGameController(index))
        return;
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        if (!controllers[p]) {
            controllers[p] = SDL_GameControllerOpen(index);
            return;
        }
    }
}

/* Joystick instance `id` disconnected: free its Player slot */
static void controller_removed(SDL_JoystickID id) {
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        if (controllers[p] && SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controllers[p])) == id) {
            SDL_GameControllerClose(controllers[p]);
            controllers[p] = NULL;
        }
    }
}

/* A controller's buttons as a SNES pad. Face buttons are positional (SDL's
 * layout names them Xbox-style: A bottom, B right, X left, Y top; the SNES has
 * B bottom, A right, Y left, X top). The left stick past the deadzone is the dpad. */
static uint16_t controller_pad(SDL_GameController *c) {
    static const struct { SDL_GameControllerButton button; uint16_t bit; } map[] = {
        { SDL_CONTROLLER_BUTTON_B, PAD_A },        { SDL_CONTROLLER_BUTTON_A, PAD_B },
        { SDL_CONTROLLER_BUTTON_Y, PAD_X },        { SDL_CONTROLLER_BUTTON_X, PAD_Y },
        { SDL_CONTROLLER_BUTTON_LEFTSHOULDER, PAD_L }, { SDL_CONTROLLER_BUTTON_RIGHTSHOULDER, PAD_R },
        { SDL_CONTROLLER_BUTTON_START, PAD_START }, { SDL_CONTROLLER_BUTTON_BACK, PAD_SELECT },
        { SDL_CONTROLLER_BUTTON_DPAD_UP, PAD_UP },     { SDL_CONTROLLER_BUTTON_DPAD_DOWN, PAD_DOWN },
        { SDL_CONTROLLER_BUTTON_DPAD_LEFT, PAD_LEFT }, { SDL_CONTROLLER_BUTTON_DPAD_RIGHT, PAD_RIGHT },
    };
    enum { DEADZONE = 16000 };
    uint16_t pad = 0;
    for (size_t i = 0; i < sizeof(map) / sizeof(map[0]); i++)
        if (SDL_GameControllerGetButton(c, map[i].button))
            pad |= map[i].bit;
    int x = SDL_GameControllerGetAxis(c, SDL_CONTROLLER_AXIS_LEFTX);
    int y = SDL_GameControllerGetAxis(c, SDL_CONTROLLER_AXIS_LEFTY);
    if (x < -DEADZONE) pad |= PAD_LEFT;
    if (x > DEADZONE)  pad |= PAD_RIGHT;
    if (y < -DEADZONE) pad |= PAD_UP;
    if (y > DEADZONE)  pad |= PAD_DOWN;
    return pad;
}

void platform_input_poll(void) {
    SDL_Event event;

    record_frame(); /* --record-video/--record-audio: this frame is rendered */

    memcpy(pad_prev, pad_state, sizeof(pad_prev));

    while (SDL_PollEvent(&event)) {
        switch (event.type) {
        case SDL_QUIT:
            quit_requested = 1;
            break;
        case SDL_CONTROLLERDEVICEADDED:
            controller_added(event.cdevice.which);
            break;
        case SDL_CONTROLLERDEVICEREMOVED:
            controller_removed(event.cdevice.which);
            break;
        case SDL_KEYDOWN:
        case SDL_KEYUP: {
            uint16_t bit = 0, bit2 = 0; /* P1 / P2 layout */
            uint16_t aux_bit = 0;
            switch (event.key.keysym.scancode) {
            case SDL_SCANCODE_X:      bit = PAD_A;      break;
            case SDL_SCANCODE_Z:      bit = PAD_B;      break;
            case SDL_SCANCODE_S:      bit = PAD_X;      break;
            case SDL_SCANCODE_A:      bit = PAD_Y;      break;
            case SDL_SCANCODE_Q:      bit = PAD_L;      break;
            case SDL_SCANCODE_W:      bit = PAD_R;      break;
            case SDL_SCANCODE_RETURN: bit = PAD_START;  break;
            case SDL_SCANCODE_RSHIFT: bit = PAD_SELECT; break;
            case SDL_SCANCODE_UP:     bit = PAD_UP;            break;
            case SDL_SCANCODE_DOWN:   bit = PAD_DOWN;          break;
            case SDL_SCANCODE_LEFT:   bit = PAD_LEFT;          break;
            case SDL_SCANCODE_RIGHT:  bit = PAD_RIGHT;         break;
            case SDL_SCANCODE_I:           bit2 = PAD_UP;     break;
            case SDL_SCANCODE_K:           bit2 = PAD_DOWN;   break;
            case SDL_SCANCODE_J:           bit2 = PAD_LEFT;   break;
            case SDL_SCANCODE_L:           bit2 = PAD_RIGHT;  break;
            case SDL_SCANCODE_U:           bit2 = PAD_A;      break;
            case SDL_SCANCODE_O:           bit2 = PAD_B;      break;
            case SDL_SCANCODE_P:           bit2 = PAD_START;  break;
            case SDL_SCANCODE_LEFTBRACKET: bit2 = PAD_SELECT; break;
            case SDL_SCANCODE_F1:     aux_bit = AUX_DEBUG_DUMP;   break;
            case SDL_SCANCODE_F2:     aux_bit = AUX_VRAM_DUMP;    break;
            case SDL_SCANCODE_F3:     aux_bit = AUX_FPS_TOGGLE;   break;
            case SDL_SCANCODE_F6:     aux_bit = AUX_SAVESTATE;    break;
            case SDL_SCANCODE_F7:     aux_bit = AUX_LOAD_STATE;   break;
            case SDL_SCANCODE_TAB:    aux_bit = AUX_FAST_FORWARD; break;
            case SDL_SCANCODE_F5:     aux_bit = AUX_DEBUG_TOGGLE; break;
            default: break;
            }
            if (event.type == SDL_KEYDOWN) {
                key_state[0] |= bit;
                key_state[1] |= bit2;
                aux_state |= aux_bit;
            } else {
                key_state[0] &= ~bit;
                key_state[1] &= ~bit2;
                aux_state &= ~aux_bit;
            }
            break;
        }
        }
    }

    if (input_script_active()) {
        uint16_t aux = 0;
        input_script_next(pad_state, &aux);
        aux_state = aux;
        return;
    }
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        pad_state[p] = p < 2 ? key_state[p] : 0;
        if (controllers[p])
            pad_state[p] |= controller_pad(controllers[p]);
    }
}

uint16_t platform_input_get_pad(void) {
    return pad_state[0];
}

uint16_t platform_input_get_pad_new(void) {
    return pad_state[0] & ~pad_prev[0];
}

uint16_t platform_input_get_pad_n(int player) {
    return player >= 0 && player < PLATFORM_MAX_PLAYERS ? pad_state[player] : 0;
}

uint16_t platform_input_get_pad_new_n(int player) {
    return player >= 0 && player < PLATFORM_MAX_PLAYERS ? pad_state[player] & ~pad_prev[player] : 0;
}

uint16_t platform_input_get_aux(void) {
    return aux_state;
}

bool platform_input_quit_requested(void) {
    return quit_requested != 0;
}

void platform_request_quit(void) {
    quit_requested = 1;
}

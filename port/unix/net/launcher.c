/* The launcher screen and online.cfg. See launcher.h. */
#include "net/launcher.h"

#include <SDL.h>
#include <stdio.h>
#include <string.h>

#include "include/pad.h"
#include "net/relay.h"
#include "net/ui.h"
#include "platform/platform.h"

/* sdl2_input.c */
void input_text_enable(bool on);
size_t input_text_take(char *out, size_t cap);

#define CFG_PATH "online.cfg"
#define W EB_VIEWPORT_WIDTH
#define H EB_VIEWPORT_HEIGHT
#define LEFT 32
#define LINE 18

static char saved_relay[256], saved_invite[256];

/* ---- online.cfg: "relay=..." and "invite=..." lines ---- */

static void cfg_load(void) {
    FILE *f = fopen(CFG_PATH, "r");
    if (!f)
        return;
    char line[300];
    while (fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = '\0';
        if (strncmp(line, "relay=", 6) == 0)
            snprintf(saved_relay, sizeof saved_relay, "%s", line + 6);
        else if (strncmp(line, "invite=", 7) == 0)
            snprintf(saved_invite, sizeof saved_invite, "%s", line + 7);
    }
    fclose(f);
}

static void cfg_save(void) {
    FILE *f = fopen(CFG_PATH, "w");
    if (!f)
        return;
    fprintf(f, "relay=%s\ninvite=%s\n", saved_relay, saved_invite);
    fclose(f);
}

const char *launcher_saved_relay(void) {
    cfg_load();
    return saved_relay[0] ? saved_relay : NULL;
}

void launcher_remember(const char *relay, const char *invite) {
    cfg_load();
    if (relay)
        snprintf(saved_relay, sizeof saved_relay, "%s", relay);
    if (invite)
        snprintf(saved_invite, sizeof saved_invite, "%s", invite);
    cfg_save();
}

/* ---- Drawing ---- */

static pixel_t fb[H][W];

#define WHITE PIXEL_RGB(0xFF, 0xFF, 0xFF)
#define GRAY  PIXEL_RGB(0x80, 0x80, 0x80)
#define RED   PIXEL_RGB(0xFF, 0x55, 0x55)

static void text(int x, int y, int font, const char *s, pixel_t c) {
    for (int gy = 0; gy < ui_font_height(font); gy++)
        if (y + gy >= 0 && y + gy < H)
            ui_text_row(fb[y + gy], gy, x, font, s, c);
}

/* `s` word-wrapped to the screen's text width from y; returns the y below it. */
static int text_wrapped(int y, const char *s, pixel_t c) {
    const int max = W - 2 * LEFT;
    char line[160] = "";
    while (*s) {
        const char *sp = strchr(s, ' ');
        size_t wlen = sp ? (size_t)(sp - s) : strlen(s);
        char trial[160];
        snprintf(trial, sizeof trial, "%s%s%.*s", line, line[0] ? " " : "", (int)wlen, s);
        if (line[0] && ui_text_width(UI_FONT_MAIN, trial) > max) {
            text(LEFT, y, UI_FONT_MAIN, line, c);
            y += LINE;
            snprintf(line, sizeof line, "%.*s", (int)wlen, s);
        } else {
            snprintf(line, sizeof line, "%s", trial);
        }
        s += wlen;
        while (*s == ' ')
            s++;
    }
    if (line[0]) {
        text(LEFT, y, UI_FONT_MAIN, line, c);
        y += LINE;
    }
    return y;
}

static void present(void) {
    platform_video_begin_frame();
    for (int y = 0; y < H; y++)
        platform_video_send_scanline(y, fb[y]);
    platform_video_end_frame();
}

/* ---- Screens ---- */

enum { S_MENU, S_HOST, S_JOIN };
static const char *const ITEMS[] = { "Play", "Host online", "Join online" };

static void draw_menu(int sel, const char *status, bool err) {
    int y = H / 2 - 3 * LINE / 2 - 8;
    for (int i = 0; i < 3; i++) {
        pixel_t c = i == sel ? WHITE : GRAY;
        if (i == sel) /* a small right-pointing cursor */
            for (int dy = 0; dy < 7; dy++)
                for (int dx = 0; dx <= (dy < 4 ? dy : 6 - dy); dx++)
                    fb[y + 4 + dy][LEFT - 10 + dx] = c;
        text(LEFT, y, UI_FONT_MAIN, ITEMS[i], c);
        y += LINE;
    }
    if (status[0])
        text_wrapped(y + LINE, status, err ? RED : WHITE);
}

static void draw_field(int screen, const char *field, int frame, const char *status, bool err) {
    int y = H / 2 - 2 * LINE;
    text(LEFT, y, UI_FONT_MAIN, screen == S_HOST ? "Relay" : "Invite", WHITE);
    y += LINE + 4;
    /* The field's tail when it's too long, then a blinking caret */
    const int max = W - 2 * LEFT - 8;
    const char *shown = field;
    while (*shown && ui_text_width(UI_FONT_MAIN, shown) > max)
        shown++;
    text(LEFT, y, UI_FONT_MAIN, shown, WHITE);
    if ((frame / 30) % 2 == 0) {
        int cx = LEFT + ui_text_width(UI_FONT_MAIN, shown) + 1;
        for (int dy = 2; dy < 13 && cx < W; dy++)
            fb[y + dy][cx] = WHITE;
    }
    for (int x = LEFT; x < W - LEFT; x++)
        fb[y + 15][x] = GRAY;
    y += LINE + 8;
    if (status[0])
        text_wrapped(y, status, err ? RED : WHITE);
#ifdef __APPLE__
    const char *paste = "CMD+V PASTE";
#else
    const char *paste = "CTRL+V PASTE";
#endif
    char hint[96];
    snprintf(hint, sizeof hint, "ENTER %s   ESC BACK   %s", screen == S_HOST ? "HOST" : "JOIN", paste);
    text(LEFT, H - 20, UI_FONT_TINY, hint, GRAY);
}

/* The clipboard, if it holds an invite (a bare code counts with a fallback relay). */
static bool clipboard_invite(const char *fallback_relay, char *out, size_t cap) {
    if (platform_headless || !SDL_HasClipboardText())
        return false;
    char *clip = SDL_GetClipboardText();
    char base[256], code[RELAY_CODE_LEN + 1];
    bool ok = clip && relay_parse_invite(clip, fallback_relay, base, sizeof base, code);
    if (ok)
        snprintf(out, cap, "%s", clip);
    SDL_free(clip);
    return ok;
}

LaunchChoice launcher_run(NetConfig *cfg) {
    static char field[256], relay[256], invite[256];
    const char *cli_relay = cfg->relay; /* --relay: preferred over online.cfg's */
    cfg_load();
    input_text_enable(true);
    int screen = S_MENU, sel = 0, frame = 0;
    char status[512] = "";
    bool err = false;
    LaunchChoice choice = LAUNCH_QUIT;
    while (!platform_input_quit_requested()) {
        platform_input_poll();
        uint16_t pressed = platform_input_get_pad_new();
        char typed[256];
        size_t ntyped = input_text_take(typed, sizeof typed);

        if (screen == S_MENU) {
            if (pressed & PAD_UP)
                sel = (sel + 2) % 3;
            if (pressed & PAD_DOWN)
                sel = (sel + 1) % 3;
            if (pressed & (PAD_A | PAD_START)) {
                status[0] = '\0';
                if (sel == 0) {
                    choice = LAUNCH_PLAY;
                    break;
                }
                screen = sel == 1 ? S_HOST : S_JOIN;
                if (screen == S_HOST)
                    snprintf(field, sizeof field, "%s", cli_relay ? cli_relay : saved_relay);
                else if (!clipboard_invite(cli_relay ? cli_relay : saved_relay[0] ? saved_relay : NULL, field, sizeof field))
                    snprintf(field, sizeof field, "%s", saved_invite);
            }
        } else {
            /* Keys type here, so only Return (Start) submits and Escape goes back */
            bool submit = (pressed & PAD_START) != 0, back = false;
            for (size_t i = 0; i < ntyped; i++) {
                size_t len = strlen(field);
                char c = typed[i];
                if (c == '\b') {
                    if (len)
                        field[len - 1] = '\0';
                } else if (c == '\n') {
                    submit = true;
                } else if (c == 0x1B) {
                    back = true;
                } else if ((unsigned char)c >= 0x20 && (unsigned char)c < 0x7F && len + 1 < sizeof field) {
                    field[len] = c;
                    field[len + 1] = '\0';
                }
            }
            if (back) {
                screen = S_MENU;
                status[0] = '\0';
            } else if (submit && field[0]) {
                snprintf(status, sizeof status, "Connecting...");
                err = false;
                memset(fb, 0, sizeof fb);
                draw_field(screen, field, 0, status, err);
                present();
                cfg->host_port = 0;
                cfg->join = NULL;
                cfg->host_room = screen == S_HOST;
                cfg->join_room = NULL;
                if (screen == S_HOST) {
                    snprintf(relay, sizeof relay, "%s", field);
                    cfg->relay = relay;
                } else {
                    snprintf(invite, sizeof invite, "%s", field);
                    cfg->join_room = invite;
                    cfg->relay = cli_relay ? cli_relay : saved_relay[0] ? saved_relay : NULL; /* for a bare code */
                }
                if (net_start(cfg)) {
                    NetStatus st;
                    net_status(&st);
                    launcher_remember(screen == S_HOST ? relay : NULL, st.invite);
                    choice = LAUNCH_ONLINE;
                    break;
                }
                snprintf(status, sizeof status, "%s", net_error());
                err = true;
            }
        }

        memset(fb, 0, sizeof fb);
        if (screen == S_MENU)
            draw_menu(sel, status, err);
        else
            draw_field(screen, field, frame, status, err);
        present();
        frame++;
        if (!platform_headless)
            SDL_Delay(16);
    }
    input_text_enable(false);
    return choice;
}

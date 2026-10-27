/* Text drawing and the online status overlay. See ui.h. */
#include "net/ui.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "data/assets.h"
#include "game/text.h"
#include "net/net.h"
#include "platform/platform.h"

/* ---- Text ---- */

#define GLYPHS 96 /* both fonts: EB characters 0x50.. */

typedef struct {
    const uint8_t *gfx, *widths;
    int height, stride, padding;
} UiFont;

/* The fonts straight from the embedded assets (text_system_init's, but usable
 * before game_init: the launcher runs first). Glyph rows are 1 bit per pixel,
 * MSB left, 0 = ink. The main font gets the game's 1 px letter spacing. */
static const UiFont *font(int id) {
    static UiFont f[2];
    static bool loaded;
    if (!loaded) {
        f[UI_FONT_MAIN] = (UiFont){ ASSET_DATA(ASSET_FONTS_MAIN_GFX), ASSET_DATA(ASSET_FONTS_MAIN_BIN), 16,
                                    (int)(ASSET_SIZE(ASSET_FONTS_MAIN_GFX) / GLYPHS), 1 };
        f[UI_FONT_TINY] = (UiFont){ ASSET_DATA(ASSET_FONTS_TINY_GFX), ASSET_DATA(ASSET_FONTS_TINY_BIN), 8,
                                    (int)(ASSET_SIZE(ASSET_FONTS_TINY_GFX) / GLYPHS), 0 };
        loaded = true;
    }
    return &f[id];
}

int ui_font_height(int id) {
    return font(id)->height;
}

static int glyph_index(char c) {
    int i = ascii_to_eb_char(c) - 0x50;
    return i >= 0 && i < GLYPHS ? i : 0;
}

int ui_text_width(int id, const char *s) {
    const UiFont *f = font(id);
    int w = 0;
    for (; *s; s++)
        w += f->widths[glyph_index(*s)] + f->padding;
    return w;
}

void ui_text_row(pixel_t *row, int gy, int x, int id, const char *s, pixel_t color) {
    const UiFont *f = font(id);
    if (gy < 0 || gy >= f->height)
        return;
    for (; *s; s++) {
        int i = glyph_index(*s);
        int w = f->widths[i];
        uint8_t bits = f->gfx[i * f->stride + gy];
        for (int col = 0; col < w && col < 8; col++) {
            int px = x + col;
            if (!(bits & (0x80 >> col)) && px >= 0 && px < EB_VIEWPORT_WIDTH)
                row[px] = color;
        }
        x += w + f->padding;
    }
}

/* ---- Status overlay ---- */

#define LINES      5
#define NOTICE_FRAMES 240 /* 4 s */
#define COPIED_FRAMES 300

static bool details;               /* F4 */
static int copied_left;            /* frames left of "INVITE COPIED" */
static struct {
    char text[LINES][40];
    pixel_t color[LINES];
    int count;
} ov;
static char notice[40];
static int notice_left;
static uint8_t last_players;       /* remote Players last frame (bit p = Player p) */

void net_overlay_toggle(void) {
    details = !details;
}

void net_overlay_invite_copied(void) {
    copied_left = COPIED_FRAMES;
}

static void add(pixel_t color, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
static void add(pixel_t color, const char *fmt, ...) {
    if (ov.count == LINES)
        return;
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(ov.text[ov.count], sizeof ov.text[0], fmt, ap);
    va_end(ap);
    ov.color[ov.count++] = color;
}

bool net_overlay_prepare(void) {
    static int enabled = -1;
    if (enabled < 0) { /* EB_NET_OVERLAY=1 (headless shots), 2 with the F4 lines on */
        const char *env = getenv("EB_NET_OVERLAY");
        enabled = !platform_headless || env != NULL;
        details = env && strcmp(env, "2") == 0;
    }
    ov.count = 0;
    if (!enabled || !net_active())
        return false;
    NetStatus st;
    net_status(&st);
    const pixel_t white = PIXEL_RGB(0xFF, 0xFF, 0xFF), gray = PIXEL_RGB(0x99, 0x99, 0x99);
    const char *slash = strrchr(st.invite, '/');
    const char *code = slash ? slash + 1 : "";

    /* Joins and leaves (the Host's view of the remote machines' first Players) */
    uint8_t players = 0;
    for (int i = 0; st.host && i < st.npeers; i++)
        players |= (uint8_t)(1u << st.peer[i].player);
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
        uint8_t bit = (uint8_t)(1u << p);
        if ((players ^ last_players) & bit) {
            snprintf(notice, sizeof notice, "P%d %s", p + 1, players & bit ? "JOINED" : "LEFT");
            notice_left = NOTICE_FRAMES;
        }
    }
    last_players = players;

    if (!st.host && !st.joined) {
        add(white, "JOINING %s", code[0] ? code : "THE HOST");
        return true;
    }
    if (st.relay_lost)
        add(PIXEL_RGB(0xFF, 0x44, 0x44), "RELAY LOST");
    else if (st.host && code[0] && (st.npeers == 0 || details))
        add(white, "ROOM %s", code);
    if (copied_left > 0) {
        copied_left--;
        add(gray, "INVITE COPIED");
    }
    if (notice_left > 0) {
        notice_left--;
        add(white, "%s", notice);
    }
    if (details) {
        for (int i = 0; i < st.npeers; i++) {
            char ping[16] = "-";
            if (st.peer[i].rtt)
                snprintf(ping, sizeof ping, "%dMS", st.peer[i].rtt);
            if (st.host)
                add(gray, "P%d %s", st.peer[i].player + 1, ping);
            else
                add(gray, "PING %s", ping);
        }
        add(gray, "DELAY %d", st.delay);
    }
    return ov.count > 0;
}

void net_overlay_stamp(int y, pixel_t *pixels) {
    const int h = ui_font_height(UI_FONT_TINY), row_h = h + 1;
    int line = y / row_h, gy = y % row_h;
    if (line >= ov.count)
        return;
    int w = ui_text_width(UI_FONT_TINY, ov.text[line]);
    for (int x = 0; x < w + 2 && x < EB_VIEWPORT_WIDTH; x++)
        pixels[x] = PIXEL_RGB(0, 0, 0);
    if (gy < h)
        ui_text_row(pixels, gy, 1, UI_FONT_TINY, ov.text[line], ov.color[line]);
}

#ifndef EB_NET_UI_H
#define EB_NET_UI_H

/*
 * Online co-op screens of the desktop port, drawn straight into scanlines with the
 * game's own fonts (outside the PPU, so the game state never sees them):
 *   - the status overlay over the game (top left): the room to invite friends to,
 *     who joined or left, and with F4 each Player's ping and the input delay;
 *   - the text primitive launcher.c draws its screens with.
 * The overlay shows in a window only (headless runs hash and compare their
 * frames), or with EB_NET_OVERLAY=1 (2: with the F4 lines on).
 */

#include <stdbool.h>

#include "core/types.h"

enum { UI_FONT_MAIN, UI_FONT_TINY };

int ui_font_height(int font);
/* Pixel width of `s` in `font`. */
int ui_text_width(int font, const char *s);
/* Draw glyph row `gy` (0 = top) of `s`, starting at x, into one scanline. */
void ui_text_row(pixel_t *row, int gy, int x, int font, const char *s, pixel_t color);

/* F4: show or hide the ping and delay lines. */
void net_overlay_toggle(void);
/* The Host's invite went to the clipboard: say so for a few seconds. */
void net_overlay_invite_copied(void);
/* Once per rendered frame, before the scanlines: whether there is anything to stamp. */
bool net_overlay_prepare(void);
/* Stamp the overlay into scanline y (a scanline_stamp_cb_t). */
void net_overlay_stamp(int y, pixel_t *pixels);

#endif /* EB_NET_UI_H */

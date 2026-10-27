#ifndef INTRO_FILE_SELECT_INTERNAL_H
#define INTRO_FILE_SELECT_INTERNAL_H

/* Shared between file_select.c (the naming screens) and naming_ja.c (their
 * Japanese layout). Not for other subsystems. */

#include "core/types.h"
#include "game/window.h"

/* The EB-encoded Don't Care name [category][index] (DONT_CARE_NAMES: 7 x 7
 * names of 6 bytes; the Japanese asset has the same layout). */
const uint8_t *get_dont_care_name(int category, int index);

/* The buffer a NameTargetId names. */
uint8_t *name_target_buffer(int id);

/* The keyboard's battle-BG animation while the file menu is up. */
void text_input_bg_update(void);

/* Render `max_len` letters of `display` into the name display's fixed tiles
 * (0x2E0+, two per column); returns the columns rendered. */
int kb_render_name_tiles(const uint8_t *display, int max_len);

/* Point text row `text_y` of window `nw` at the name display tiles
 * (rewritten every frame: render_all_windows rebuilds the tilemap). */
void kb_write_name_tilemap_at(WindowInfo *nw, int num_cols, int text_y);

#endif /* INTRO_FILE_SELECT_INTERNAL_H */

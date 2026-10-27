/*
 * The naming screens in Japanese (see naming_ja.h): ports of the JPN asm.
 *
 *   TEXT_INPUT_DIALOG       asm/text/text_input_dialog-jp.asm
 *   RENDER_NAMING_CHARACTER asm/text/render_naming_character-jp.asm
 *   RENDER_DONT_CARE_NAME   asm/text/render_dont_care_name-jp.asm
 *   NAME_A_CHARACTER        asm/intro/name_a_character.asm (JPN branches)
 *   the confirmation        asm/intro/file_select_menu_loop-jp.asm
 *   ENTER_YOUR_NAME_PLEASE  asm/text/enter_your_name_please-jp.asm
 *   PROCESS_NAME_INPUT_STRING / TRANSLITERATE_CONSONANT_VOWEL
 *   FIND_NEXT_MENU_OPTION / MOVE_CURSOR, over the keyboard
 *
 * One model change: Mother 2 reads letters back from the window tilemap
 * (GET_MENU_TILE_AT_POSITION: the keyboard key under the cursor, the name box's
 * last letter for the dakuten keys, the whole name box on OK). The port's
 * Japanese text is VWF tiles, so the keyboard re-reads its layout message
 * (ja_kb_grid) and the name box is TextInputState's eb_name / name_pos (the
 * box's text_x), drawn into the name display tiles like the US keyboard's.
 *
 * TextInputState in Japanese: is_lowercase holds the keyboard page (0
 * hiragana, 1 katakana, 2 alphabet: TEXT_INPUT_DIALOG's @LOCAL09), and
 * frame_counter counts the frames since @CURSOR_SETUP (frame 0 is its
 * WINDOW_TICK; the input tick frames follow, the cursor blinking every 9).
 */
#include "intro/naming_ja.h"
#include "intro/file_select.h"
#include "intro/file_select_internal.h"
#include "game/window.h"
#include "game/text.h"
#include "game/game_state.h"
#include "game/display_text.h"
#include "game/audio.h"
#include "game/battle.h"
#include "game/overworld.h"
#include "entity/entity.h"
#include "entity/sprite.h"
#include "snes/ppu.h"
#include "core/math.h"
#include "core/memory.h"
#include "data/assets.h"
#include "data/text_refs.h"
#include "include/pad.h"
#include "coop/coop_input.h"
#include <string.h>

/* Mother 2's CHAR codes on the naming screen (include/macros.asm, JPN) */
#define JA_CHAR_PLACEHOLDER 0x5C
#define JA_KEY_MARKER       0x2F /* the blank key glyph FIND_NEXT_MENU_OPTION looks for */

/* The JPN keyboard window (WINDOW_CONFIGURATION_TABLE 0x1C: 30 x 20): its
 * window_stats::width and height / 2, the bounds of the key search. */
#define JA_KB_COLS 28
#define JA_KB_ROWS 9

/* The keyboard's buttons (TEXT_INPUT_DIALOG @CHECK_CONFIRM): row 8 Don't Care,
 * Backspace and OK, row 6 the pages. */
#define JA_KB_BUTTON_ROW 8
#define JA_KB_PAGE_ROW   6

#define JA_PROMPT_SIZE 15 /* NAME_THEM_STRING_LENGTH (JPN) */

/* naming_confirm.bin (ebtools/ja_interface.py CONFIRM_FIELDS): the
 * FILE_SELECT_TEXT_* strings, in ROM order, with their PRINT_STRING lengths. */
#define JA_CONFIRM_FOOD 0  /* FAVORITE_FOOD, 9 */
#define JA_CONFIRM_THING 9 /* COOLEST_THING, 11 */
#define JA_CONFIRM_SURE 20 /* ARE_YOU_SURE, 12 */

/* NAME_INPUT_WINDOW_SELECTION_LAYOUT_POINTERS: the six layouts, 0-2 hiragana,
 * katakana and alphabet with Don't Care, 3-5 without. mother2.yml names the
 * KEYBOARD block's labels after the US ones in the same order, so the Japanese
 * dialogue holds layout i under the i-th US label. */
static const uint32_t ja_kb_layouts[6] = {
    MSG_KBD_LAYOUT_UPPERCASE_A, MSG_KBD_LAYOUT_LOWERCASE_A, MSG_KBD_LAYOUT_UPPERCASE_B,
    MSG_KBD_LAYOUT_LOWERCASE_B, MSG_KBD_LAYOUT_BUTTONS_DONT_CARE, MSG_KBD_LAYOUT_BUTTONS_NO_DONT_CARE,
};

static uint32_t ja_kb_layout(const TextInputState *s) {
    return ja_kb_layouts[(s->has_dont_care ? 0 : 3) + (s->is_lowercase % 3)];
}

/* The Japanese-only assets (NULL in a build without the Mother 2 extraction,
 * where nothing here runs). */
static const uint8_t *ja_confirm_text(void) {
#ifdef EB_HAVE_JA
    return ASSET_DATA(ASSET_JA_DATA_NAMING_CONFIRM_BIN);
#else
    return NULL;
#endif
}

static const uint8_t *ja_transliteration_pairs(void) {
#ifdef EB_HAVE_JA
    return ASSET_DATA(ASSET_JA_DATA_CONSONANT_VOWEL_TRANSLITERATION_PAIRS_BIN);
#else
    return NULL;
#endif
}

int ja_naming_max_len(int i) {
    return i < 4 ? 4 : 6;
}

/* ---- The name box ------------------------------------------------------- */

/* The name box as Mother 2 leaves it after every edit: the letters, the bullet
 * at text_x (unless the name is full), placeholders after it. */
static int ja_name_display(uint8_t *display, const uint8_t *name, int pos, int max_len) {
    for (int i = 0; i < max_len; i++)
        display[i] = i < pos ? name[i] : i == pos ? JA_CHAR_BULLET : JA_CHAR_PLACEHOLDER;
    display[max_len] = 0;
    return kb_render_name_tiles(display, max_len);
}

static int ja_name_len(const uint8_t *name, int max_len) {
    int n = 0;
    while (n < max_len && name[n] != 0)
        n++;
    return n;
}

/* RENDER_NAMING_CHARACTER on the name box: `c` -1 deletes the last letter
 * (returning 1 if there was none), JA_CHAR_DAKUTEN / JA_CHAR_HANDAKUTEN voice
 * the last letter if Mother 2's kana layout has the voiced form at +1 / +2
 * (か さ た は rows, low nibbles 2 4 6 9; は row only for ゜), any other code
 * is typed if the box has room. */
static int ja_naming_character(TextInputState *s, int c) {
    uint8_t *last = s->name_pos ? &s->eb_name[s->name_pos - 1] : NULL;
    if (c == -1) {
        if (!last)
            return 1;
        *last = 0;
        s->name_pos--;
    } else if (c == JA_CHAR_DAKUTEN) {
        if (last && *last >= 0x60) {
            uint8_t low = *last & 0x0F;
            if (low == 2 || low == 4 || low == 6 || low == 9)
                (*last)++;
        }
    } else if (c == JA_CHAR_HANDAKUTEN) {
        if (last && *last > 0x60 && (*last & 0x0F) == 9)
            *last = (uint8_t)(*last + 2);
    } else if (s->name_pos < s->max_len) {
        s->eb_name[s->name_pos++] = (uint8_t)c;
    }
    return 0;
}

/* RENDER_DONT_CARE_NAME: the next Don't Care name of the group (the row
 * counter starts at -1 and wraps after 6), RENDER_DONT_CARE_NAME's length 4 for
 * the party (naming index < 4), 6 otherwise. */
static void ja_dont_care(TextInputState *s) {
    s->dont_care_row = (int16_t)(s->dont_care_row == 6 ? 0 : s->dont_care_row + 1);
    const uint8_t *name = get_dont_care_name(s->naming_index, s->dont_care_row);
    int len = ja_naming_max_len(s->naming_index);
    memset(s->eb_name, 0, sizeof s->eb_name);
    s->name_pos = 0;
    for (int i = 0; i < 6 && i < len && i < (int)s->max_len && name[i] != 0; i++)
        s->eb_name[s->name_pos++] = name[i];
}

/* ---- The keyboard ------------------------------------------------------- */

typedef struct {
    uint8_t c[JA_KB_ROWS][JA_KB_COLS];
} JaKbGrid;

/* What GET_MENU_TILE_AT_POSITION reads from the keyboard window: the codes the
 * layout message prints, one column each from its FORCE_TEXT_ALIGNMENT (18 05 x
 * y) positions, then TEXT_INPUT_DIALOG's dakuten and handakuten keys at (25, 3)
 * and (25, 4), over the layout's ! and ?. */
static void ja_kb_grid(const TextInputState *s, JaKbGrid *g) {
    memset(g, 0, sizeof *g);
    size_t n = 0;
    const uint8_t *p = display_text_resolve(ja_kb_layout(s), &n);
    int x = 0, y = 0;
    for (size_t i = 0; p && i < n;) {
        if (p[i] == 0x18 && i + 3 < n && p[i + 1] == 0x05) {
            x = p[i + 2];
            y = p[i + 3];
            i += 4;
            continue;
        }
        if (p[i] < 0x20)
            break; /* end_block: the layouts hold nothing else */
        if (x < JA_KB_COLS && y < JA_KB_ROWS)
            g->c[y][x] = p[i];
        x++;
        i++;
    }
    g->c[3][25] = JA_CHAR_DAKUTEN;
    g->c[4][25] = JA_CHAR_HANDAKUTEN;
}

static bool ja_kb_marker(const JaKbGrid *g, int x, int y) {
    return g->c[y][x] == JA_KEY_MARKER;
}

/* FIND_NEXT_MENU_OPTION (asm/battle/find_next_menu_option.asm): the next key
 * marker from (x0, y0). Vertically (dy != 0): the same column, then each row's
 * keys left of x0, then right of it; horizontally: the same row, then each
 * column's keys above y0, then below. Bounds are unsigned compares with the
 * window's width and height / 2. Plays `sfx` (>= 0) when found. Returns
 * (y << 8) + x, or -1. */
static int ja_find_next(const JaKbGrid *g, int x0, int y0, int dy, int dx, int sfx) {
    const unsigned w = JA_KB_COLS, h = JA_KB_ROWS;
    int x, y;
    if (dy != 0) {
        for (y = y0 + dy; (unsigned)y < h; y += dy)
            if (ja_kb_marker(g, (x = x0), y))
                goto found;
        for (y = y0 + dy; (unsigned)y < h; y += dy)
            for (x = x0 - 1; (unsigned)x < w; x--)
                if (ja_kb_marker(g, x, y))
                    goto found;
        for (y = y0 + dy; (unsigned)y < h; y += dy)
            for (x = x0 + 1; (unsigned)x < w; x++)
                if (ja_kb_marker(g, x, y))
                    goto found;
        return -1;
    }
    for (x = x0 + dx; (unsigned)x < w; x += dx)
        if (ja_kb_marker(g, x, (y = y0)))
            goto found;
    for (x = x0 + dx; (unsigned)x < w; x += dx)
        for (y = y0 - 1; (unsigned)y < h; y--)
            if (ja_kb_marker(g, x, y))
                goto found;
    for (x = x0 + dx; (unsigned)x < w; x += dx)
        for (y = y0 + 1; (unsigned)y < h; y++)
            if (ja_kb_marker(g, x, y))
                goto found;
    return -1;
found:
    if (sfx >= 0)
        play_sfx((uint16_t)sfx);
    return (y << 8) + x;
}

/* MOVE_CURSOR (asm/text/move_cursor.asm): FIND_NEXT_MENU_OPTION, else wrap:
 * search again from (wrap_x, wrap_y), keeping the result only if it stays in the
 * start row (horizontal) or column (vertical). Plays `sfx` on a move. */
static int ja_move_cursor(const JaKbGrid *g, int x, int y, int dy, int dx, int sfx,
                          int wrap_x, int wrap_y) {
    int r = ja_find_next(g, x, y, dy, dx, -1);
    if (r == -1) {
        r = ja_find_next(g, wrap_x, wrap_y, dy, dx, -1);
        if (r != -1 && (dy == 0 ? (r >> 8) != y : (r & 0xFF) != x))
            r = -1;
    }
    if (r != -1)
        play_sfx((uint16_t)sfx);
    return r;
}

/* @OPEN_KEYBOARD: (re)create the keyboard window and print the page's layout
 * (DISPLAY_TEXT), then the dakuten and handakuten keys. Instant printing until
 * @CURSOR_SETUP. The port prints the layout from ja_kb_grid, a fixed tile
 * column per letter, and leaves out the blank ones (the key markers and
 * spaces): Mother 2 draws every letter with its font tile, but each letter here
 * takes two BG2 tiles, and the whole layout through the VWF would need more
 * than the tile pool has (ALLOC_BG2_TILEMAP_ENTRY's 407). */
static void ja_kb_open(const TextInputState *s) {
    set_instant_printing();
    create_window(WINDOW_FILE_SELECT_NAMING_KB);
    win.current_focus_window = WINDOW_FILE_SELECT_NAMING_KB;
    JaKbGrid g;
    ja_kb_grid(s, &g);
    for (int y = 0; y < JA_KB_ROWS; y++) {
        for (int x = 0; x < JA_KB_COLS; x++) {
            uint8_t c = g.c[y][x];
            if (c == 0 || c == JA_KEY_MARKER || c == JA_CHAR_SPACE)
                continue;
            print_letter_tile_at(c, (uint16_t)x, (uint16_t)y);
        }
    }
    clear_instant_printing();
}

void ja_text_input_prepare(ModeState *init, int name_target, int max_len,
                           int naming_index, uint16_t name_display_window_id,
                           int name_text_y, const uint8_t *existing_name) {
    *init = (ModeState){0};
    TextInputState *s = &init->text_input;
    s->name_target = (uint8_t)name_target;
    s->naming_index = (int16_t)naming_index;
    s->has_dont_care = (naming_index >= 0);
    /* PARAM03, the first page: ENTER_YOUR_NAME_PLEASE types the EarthBound
     * player name on the alphabet page, everything else starts on hiragana. */
    s->is_lowercase = (name_target == NAME_TARGET_EB_PLAYER) ? 2 : 0;
    s->dont_care_row = -1;
    s->max_len = (uint16_t)max_len;
    s->name_display_window_id = name_display_window_id;
    s->name_text_y = (int16_t)name_text_y;
    if (existing_name)
        for (int i = 0; i < max_len && i < (int)sizeof s->eb_name && existing_name[i] != 0; i++)
            s->eb_name[s->name_pos++] = existing_name[i];
    ja_kb_open(s);
}

/* The keyboard frame: windows, the name box, the cursor (big on @CURSOR_SETUP's
 * WINDOW_TICK frame, then CURSOR_BLINK_UPPER/LOWER_TILES alternating every 9
 * input ticks), entity scripts, palettes, the battle BG. */
static StepResult ja_kb_render(TextInputState *s, WindowInfo *kw, WindowInfo *nw) {
    vwf_frame_reset();
    vwf_reserve_tiles(s->max_len * 2);
    render_all_windows();

    uint8_t display[32];
    int cols = ja_name_display(display, s->eb_name, s->name_pos, s->max_len);
    kb_write_name_tilemap_at(nw, cols, s->name_text_y);

    uint16_t fc = s->frame_counter;
    bool small = fc != 0 && ((fc - 1) / 9) % 2 != 0;
    uint16_t *tilemap = (uint16_t *)win.bg2_buffer;
    uint16_t mx = kw->content_x + (uint16_t)s->cur_x;
    uint16_t my = kw->content_y + (uint16_t)(s->cur_y * 2);
    if (mx < 32 && my + 1 < 32) {
        tilemap[my * 32 + mx] = small ? 0x268D : 0x2441;
        tilemap[(my + 1) * 32 + mx] = small ? 0x269D : 0x2451;
    }
    s->frame_counter++;

    upload_battle_screen_to_vram();
    oam_clear();
    if (run_actionscript_frame_step()) {
        s->flush = 1;
        return actionscript_frame_take_push();
    }
    render_all_priority_sprites();
    sync_palettes_to_cgram();
    text_input_bg_update();
    s->primed = 1;
    return STEP_RESULT_CONTINUE();
}

StepResult ja_text_input_step(ModeState *st) {
    TextInputState *s = &st->text_input;

    if (s->flush) {
        s->flush = 0;
        render_all_priority_sprites();
        sync_palettes_to_cgram();
        text_input_bg_update();
        s->primed = 1;
        return STEP_RESULT_CONTINUE();
    }

    WindowInfo *kw = get_window(WINDOW_FILE_SELECT_NAMING_KB);
    WindowInfo *nw = get_window(s->name_display_window_id);
    if (!kw || !nw) {
        close_window(WINDOW_FILE_SELECT_NAMING_KB);
        return STEP_RESULT_POP(-1);
    }

    /* Entering is @CURSOR_SETUP (after @OPEN_KEYBOARD, in the prepare). The
     * input is read only after an @INPUT_TICK frame (RENDER_FRAME_TICK), never
     * after the WINDOW_TICK frame. */
    bool cursor_setup = !s->primed;
    if (s->primed && s->frame_counter >= 2) {
        JaKbGrid g;
        ja_kb_grid(s, &g);
        uint16_t pressed = coop_pad_new();
        uint16_t held = core.pad1_autorepeat; /* PAD_HELD */
        int x = s->cur_x, y = s->cur_y;
        int moved = -2; /* -2: no direction; else MOVE_CURSOR / FIND_NEXT_MENU_OPTION's result */
        bool finish = false;

        if (pressed & PAD_UP)          moved = ja_move_cursor(&g, x, y, -1, 0, 124, x, JA_KB_ROWS);
        else if (pressed & PAD_LEFT)   moved = ja_move_cursor(&g, x, y, 0, -1, 123, JA_KB_COLS, y);
        else if (pressed & PAD_DOWN)   moved = ja_move_cursor(&g, x, y, 1, 0, 124, x, -1);
        else if (pressed & PAD_RIGHT)  moved = ja_move_cursor(&g, x, y, 0, 1, 123, -1, y);
        else if (held & PAD_UP)        moved = ja_find_next(&g, x, y, -1, 0, 124);
        else if (held & PAD_DOWN)      moved = ja_find_next(&g, x, y, 1, 0, 124);
        else if (held & PAD_LEFT)      moved = ja_find_next(&g, x, y, 0, -1, 123);
        else if (held & PAD_RIGHT)     moved = ja_find_next(&g, x, y, 0, 1, 123);

        if (moved != -2) {
            /* @PROCESS_CURSOR_MOVE: the old key gets its marker back (the port
             * draws the cursor over the tilemap each frame) */
            if (moved != -1) {
                s->cur_x = (int16_t)(moved & 0xFF);
                s->cur_y = (int16_t)((moved >> 8) & 0xFF);
            }
            cursor_setup = true;
        } else if (pressed & PAD_CONFIRM) {
            if (y == JA_KB_BUTTON_ROW) {
                if (x == 0) {               /* @DONT_CARE_BUTTON */
                    play_sfx(122);          /* SFX::TEXT_INPUT */
                    ja_dont_care(s);
                    cursor_setup = true;
                } else if (x == 19) {       /* @BACKSPACE_BUTTON */
                    play_sfx(122);
                    if (ja_naming_character(s, -1) && s->naming_index != -1) {
                        close_window(WINDOW_FILE_SELECT_NAMING_KB);
                        return STEP_RESULT_POP(-1);
                    }
                    cursor_setup = true;
                } else if (x == 24) {       /* @END_BUTTON */
                    play_sfx(94);           /* SFX::NAMING_CONFIRM */
                    finish = true;
                }
            } else {
                play_sfx(122);              /* @CHECK_SPECIAL_ROW */
                if (y == JA_KB_PAGE_ROW) {
                    if (x == 8 || x == 14 || x == 20) {
                        s->is_lowercase = (uint8_t)((x - 8) / 6);
                        ja_kb_open(s);
                        cursor_setup = true;
                    }
                } else if (x + 1 < JA_KB_COLS) { /* @INPUT_CHARACTER */
                    ja_naming_character(s, g.c[y][x + 1]);
                    cursor_setup = true;
                }
            }
        } else if (pressed & PAD_CANCEL) {
            play_sfx(125);                  /* SFX::NAMING_BACKSPACE */
            if (ja_naming_character(s, -1) && s->naming_index != -1) {
                close_window(WINDOW_FILE_SELECT_NAMING_KB);
                return STEP_RESULT_POP(-1);
            }
            cursor_setup = true;
        } else if (pressed & PAD_START) {
            play_sfx(126);                  /* SFX::NAMING_CONFIRM_ALT */
            finish = true;
        }

        /* @FINISH_ENTRY: an empty name box goes back to @CURSOR_SETUP; else the
         * name (text_x letters, zero-padded to the length) is the result. */
        if (finish) {
            if (s->name_pos == 0) {
                cursor_setup = true;
            } else {
                uint8_t *buf = name_target_buffer(s->name_target);
                if (buf)
                    for (int i = 0; i < (int)s->max_len; i++)
                        buf[i] = i < (int)s->name_pos ? s->eb_name[i] : 0;
                close_window(WINDOW_FILE_SELECT_NAMING_KB);
                return STEP_RESULT_POP(0);
            }
        }
    }

    if (cursor_setup) {
        rng_next_byte(); /* @CURSOR_SETUP's WINDOW_TICK */
        s->frame_counter = 0;
    }
    return ja_kb_render(s, kw, nw);
}

/* ---- NAME_A_CHARACTER and the confirmation ------------------------------ */

int ja_naming_front(int naming_index, const uint8_t *name) {
    int max_len = ja_naming_max_len(naming_index);
    create_window(WINDOW_FILE_SELECT_NAMING_BOX);
    if (create_window(WINDOW_FILE_SELECT_NAMING_MSG)) {
        set_focus_text_cursor(0, 0);
        print_eb_string(ASSET_DATA(ASSET_US_DATA_NAMING_PROMPTS_BIN) + naming_index * JA_PROMPT_SIZE,
                        JA_PROMPT_SIZE);
    }
    uint8_t display[16];
    return ja_name_display(display, name, ja_name_len(name, max_len), max_len);
}

/* Print `len` letters of `name` right-aligned on row 1 of the focus window
 * (window_stats::width - COUNT_STRING_LENGTH). */
static void ja_print_right_aligned(const uint8_t *name, int count_max, int print_len) {
    WindowInfo *w = get_window(win.current_focus_window);
    if (!w) return;
    set_focus_text_cursor((uint16_t)(w->width - 2 - ja_name_len(name, count_max)), 1);
    print_eb_string(name, print_len);
}

void ja_naming_confirm_build(void) {
    close_all_windows();
    set_instant_printing();

    /* PRINT_CHARACTER_NAME 1-4 (4 letters) and 7 (the dog, sizeof pet_name) */
    for (int c = 0; c < 4; c++)
        if (create_window((uint16_t)(WINDOW_FILE_SELECT_CONFIRM_NESS + c)))
            print_eb_string(party_characters[c].name, 4);
    if (create_window(WINDOW_FILE_SELECT_CONFIRM_KING))
        print_eb_string(game_state.pet_name, (int)sizeof game_state.pet_name);

    const uint8_t *text = ja_confirm_text();
    if (text && create_window(WINDOW_FILE_SELECT_CONFIRM_FOOD)) {
        print_eb_string(text + JA_CONFIRM_FOOD, 9);
        ja_print_right_aligned(game_state.favourite_food, 6, 6);
    }
    if (text && create_window(WINDOW_FILE_SELECT_CONFIRM_THING)) {
        print_eb_string(text + JA_CONFIRM_THING, 11);
        ja_print_right_aligned(game_state.favourite_thing + 2, 6, 7);
    }
    if (text && create_window(WINDOW_FILE_SELECT_CONFIRM_MSG)) {
        print_eb_string(text + JA_CONFIRM_SURE, 12);
        /* The menu labels are ASCII (MenuItem::label) until the menus take
         * Mother 2 text; はい / いいえ at text_x 13 / 17. */
        add_menu_item("Yep", 1, 13, 0);
        add_menu_item("Nope", 0, 17, 0);
    }
    print_menu_items();
}

/* ---- ENTER_YOUR_NAME_PLEASE ---------------------------------------------- */

/* TRANSLITERATE_CONSONANT_VOWEL: append CONSONANT_VOWEL_TRANSLITERATION_PAIRS'
 * kana (up to two codes) for `consonant` ('A'-'Z') and vowel 0-4 (a i u e o). */
static uint8_t *ja_transliterate(uint8_t *out, const uint8_t *pairs, uint8_t consonant, int vowel) {
    const uint8_t *p = pairs + (consonant - 0x41) * 10 + vowel * 2;
    for (int i = 0; i < 2 && p[i] != 0; i++)
        *out++ = p[i];
    return out;
}

/* PROCESS_NAME_INPUT_STRING: the romaji player name (alphabet page codes) to
 * kana, NUL-terminated in `out` (three times the input's length + 1 is enough). A
 * consonant waits for its vowel; a doubled one is っ ($7E), a lone N is ん ($9D),
 * any other lone consonant takes vowel 1. (Mother 2's own pair table gives odd
 * kana for several rows, as in the original.) */
static void ja_process_name_input(uint8_t *out, const uint8_t *in, const uint8_t *pairs) {
    static const uint8_t vowel_kana[5] = { 0x60, 0x70, 0x80, 0x90, 0xA0 }; /* あ い う え お */
    uint8_t pending = 0;
    for (; *in; in++) {
        uint8_t c = *in;
        int vowel = c == 0x41 ? 0 : c == 0x49 ? 1 : c == 0x55 ? 2 : c == 0x45 ? 3 : c == 0x4F ? 4 : -1;
        bool letter = c >= 0x41 && c <= 0x5A;
        if (!pending) {
            if (vowel >= 0)
                *out++ = vowel_kana[vowel];
            else if (letter)
                pending = c;
            else
                *out++ = c;
        } else if (c == pending) {
            *out++ = 0x7E; /* っ; the consonant stays pending */
        } else if (vowel >= 0) {
            out = ja_transliterate(out, pairs, pending, vowel);
            pending = 0;
        } else {
            if (pending == 0x4E)
                *out++ = 0x9D;
            else
                out = ja_transliterate(out, pairs, pending, 1);
            if (letter) {
                pending = c;
            } else {
                *out++ = c;
                pending = 0;
            }
        }
    }
    if (pending == 0x4E)
        *out++ = 0x9D;
    else if (pending)
        out = ja_transliterate(out, pairs, pending, 1);
    *out = 0;
}

StepResult ja_enter_name_step(ModeState *st) {
    EnterNameState *s = &st->enter_name;
    if (s->phase == EN_ENTER) {
        set_instant_printing();
        create_window(WINDOW_NAMING_PROMPT);
        set_focus_text_cursor(0, 0);
        if (s->param != 0) {
            /* The Mother 2 name (12, hiragana page) under the EarthBound one */
            print_eb_string(game_state.earthbound_playername, 24);
            const uint8_t *existing = ((uint8_t *)&game_state)[0] != 0 ? game_state.mother2_playername : NULL;
            ja_text_input_prepare(&g_mode_push_init, NAME_TARGET_M2_PLAYER, 12, -1,
                                  WINDOW_NAMING_PROMPT, 1, existing);
        } else {
            /* The EarthBound name (24, alphabet page) under NAME_REGISTRY_REQUEST_STRING */
            print_eb_string(ASSET_DATA(ASSET_US_DATA_NAME_REGISTRY_REQUEST_STRING_BIN),
                            (int)ASSET_SIZE(ASSET_US_DATA_NAME_REGISTRY_REQUEST_STRING_BIN));
            const uint8_t *existing = game_state.earthbound_playername[0] != 0 ? game_state.earthbound_playername : NULL;
            ja_text_input_prepare(&g_mode_push_init, NAME_TARGET_EB_PLAYER, 24, -1,
                                  WINDOW_NAMING_PROMPT, 1, existing);
        }
        s->phase = EN_DONE;
        return STEP_RESULT_PUSH_INIT(GAME_MODE_TEXT_INPUT, &g_mode_push_init);
    }

    s->result = (uint16_t)mode_child_result();
    const uint8_t *pairs = ja_transliteration_pairs();
    if (s->param == 0 && pairs) {
        /* PROCESS_NAME_INPUT_STRING into TEMPORARY_TEXT_BUFFER, then MEMCPY16 of
         * sizeof mother2_playername */
        uint8_t kana[3 * sizeof game_state.earthbound_playername + 1];
        uint8_t romaji[sizeof game_state.earthbound_playername + 1] = {0};
        memcpy(romaji, game_state.earthbound_playername, sizeof game_state.earthbound_playername);
        ja_process_name_input(kana, romaji, pairs);
        memcpy(game_state.mother2_playername, kana, sizeof game_state.mother2_playername);
    }
    close_window(WINDOW_FILE_SELECT_NAMING_KB);
    close_window(WINDOW_NAMING_PROMPT);
    return STEP_RESULT_POP(s->result);
}

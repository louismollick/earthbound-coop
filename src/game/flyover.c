/* Flyover text system — port of C4 bank flyover rendering functions.
 *
 * Assembly sources:
 *   BLIT_FONT_TO_VWF_BUFFER     (C49875.asm, 145 lines)
 *   RENDER_LARGE_FONT_CHARACTER  (C4999B.asm, 80 lines)
 *   INVERT_VWF_BUFFER            (C4984B.asm, 24 lines)
 *   INIT_FLYOVER_TEXT_SCREEN     (C49A56.asm, 113 lines)
 *   UPLOAD_VWF_BUFFER_TO_VRAM    (C49B6E.asm, 88 lines)
 *   SCROLL_FLYOVER_TEXT          (C49C56.asm, 95 lines US)
 *   ADVANCE_FLYOVER_PIXEL_OFFSET (C49CA8.asm, 20 lines)
 *   RENDER_FLYOVER_TEXT_CHARACTER (C49D16.asm, 8 lines)
 *   RENDER_PARTY_MEMBER_NAME     (C49CC3.asm, 38 lines)
 *   ADVANCE_TEXT_LINE_POSITION   (C49D1E.asm, 46 lines)
 *   PLAY_FLYOVER_SCRIPT          (C49EC4.asm, 122 lines)
 *   COFFEETEA_SCENE              (coffee_tea_scene.asm, 139 lines)
 *   UNDRAW_FLYOVER_TEXT          (undraw_flyover_text.asm, 29 lines)
 *
 * Japanese (Mother 2, gated on locale_is_ja()): the scripts and the cinematic
 * font are Mother 2's (JA/flyover_*.bin, JA/coffee.bin, JA/tea.bin,
 * JA/fonts/flyover.gfx); see "Japanese flyovers" below.
 */

#include "game/flyover.h"
#include "core/mode_stack.h"
#include "game/display_text.h"
#include "game/text.h"
#include "game/window.h"
#include "game/battle.h"
#include "game/fade.h"
#include "game/game_state.h"
#include "game/overworld.h"
#include "entity/entity.h"
#include "snes/ppu.h"
#include "data/assets.h"
#include "include/constants.h"
#include "platform/platform.h"
#include <string.h>

#include "game_main.h"

/* ======================================================================
 * Flyover VWF ert.buffer — separate from the window system's VWF ert.buffer.
 * Layout: 26 tiles per row, each tile = 16 bytes (8x8 2bpp).
 *   Bytes 0-415:   Row 0 top halves (26 × 16)
 *   Bytes 416-831: Row 0 bottom halves (26 × 16)
 *   Bytes 832+:    Additional rows
 * Total: VWF_BUFFER_SIZE = 52 × 32 = 1664 bytes
 * ====================================================================== */

/* Share the normal window VWF buffer — flyover is a blocking full-screen
 * takeover that never runs render_all_windows(), so the two uses are
 * mutually exclusive.  flyover_init_screen() memsets before first use. */
#define flyover_vwf vwf_buffer

/* Flyover state globals (matching assembly ram.asm variables) */
static uint16_t flyover_vwf_x;
static uint16_t flyover_vwf_y;
static uint16_t flyover_tiles_per_row;
static uint16_t flyover_tile_offset;
static uint16_t flyover_dirty_min;
static uint16_t flyover_dirty_max;
static uint16_t flyover_screen_offset;
static uint16_t flyover_pixel_offset;
static uint16_t flyover_byte_offset;

/* ---- Savestate snapshot (see FlyoverSaveState in flyover.h) ---- */
void flyover_savestate_pack(void *out) {
    FlyoverSaveState *s = (FlyoverSaveState *)out;
    s->flyover_vwf_x        = flyover_vwf_x;
    s->flyover_vwf_y        = flyover_vwf_y;
    s->flyover_tiles_per_row = flyover_tiles_per_row;
    s->flyover_tile_offset  = flyover_tile_offset;
    s->flyover_dirty_min    = flyover_dirty_min;
    s->flyover_dirty_max    = flyover_dirty_max;
    s->flyover_screen_offset = flyover_screen_offset;
    s->flyover_pixel_offset = flyover_pixel_offset;
    s->flyover_byte_offset  = flyover_byte_offset;
}

void flyover_savestate_unpack(const void *in) {
    const FlyoverSaveState *s = (const FlyoverSaveState *)in;
    flyover_vwf_x        = s->flyover_vwf_x;
    flyover_vwf_y        = s->flyover_vwf_y;
    flyover_tiles_per_row = s->flyover_tiles_per_row;
    flyover_tile_offset  = s->flyover_tile_offset;
    flyover_dirty_min    = s->flyover_dirty_min;
    flyover_dirty_max    = s->flyover_dirty_max;
    flyover_screen_offset = s->flyover_screen_offset;
    flyover_pixel_offset = s->flyover_pixel_offset;
    flyover_byte_offset  = s->flyover_byte_offset;
}

/* Script asset for each flyover ID (file scope so mode_step_flyover can re-derive
 * the script pointer from the saved id). Use .bin — ebtools decodes .flyover into
 * assembly source, but the C port needs raw binary bytecodes. */
static const AssetId flyover_script_ids[8] = {
    ASSET_FLYOVER_INTRO1_BIN,
    ASSET_FLYOVER_INTRO2_BIN,
    ASSET_FLYOVER_INTRO3_BIN,
    ASSET_FLYOVER_WINTERS_INTRO1_BIN,
    ASSET_FLYOVER_WINTERS_INTRO2_BIN,
    ASSET_FLYOVER_DALAAM_INTRO1_BIN,
    ASSET_FLYOVER_DALAAM_INTRO2_BIN,
    ASSET_FLYOVER_ENDING_BIN,
};

/* TILES_PER_ROW * BYTES_PER_TILE = 26 * 16 = 416 */
#define FLYOVER_ROW_BYTES    416
/* Total VRAM size for flyover tiles: 32 rows × 416 bytes = 13312 = 0x3400 */
#define FLYOVER_VRAM_TOTAL   0x3400

/* SCROLL_FLYOVER_TEXT's argument at a 0x09 (line break): the US line is 24 px,
 * Mother 2's 18 (play_flyover_script-jp.asm, coffee_tea_scene-jp.asm). */
#define FLYOVER_LINE_US 24
#define FLYOVER_LINE_JA 18
static uint16_t flyover_line_height(void) {
    return locale_is_ja() ? FLYOVER_LINE_JA : FLYOVER_LINE_US;
}

/* ======================================================================
 * Japanese flyovers (Mother 2)
 *
 * A script byte that isn't a command starts a two-byte glyph code
 * (first << 8 | second); glyph (code - 0x8000) of the cinematic font is a
 * 12x12 1bpp bitmap of 18 bytes (DECOMP_ENTRY2: each pair of rows is 3 bytes,
 * the first row's 12 bits then the second's), drawn by RENDER_VWF_GLYPH at
 * (FLYOVER_VWF_X, FLYOVER_VWF_Y) in colour 3, 12 px apart. The VWF buffer is
 * positive (0 = transparent) and 4 rows of 26 tiles, shifted up a row at a
 * time by SCROLL_FLYOVER_TEXT.
 * ====================================================================== */
#define JA_FLYOVER_GLYPH_BASE   0x8000
#define JA_FLYOVER_GLYPH_BYTES  18
#define JA_FLYOVER_GLYPH_ROWS   12
#define JA_FLYOVER_ADVANCE      12   /* RENDER_FLYOVER_TEXT_CHARACTER's Y */
#define JA_FLYOVER_NAME_MAX     4    /* RENDER_PARTY_MEMBER_NAME's LDX #4 */
#define JA_FLYOVER_VWF_ROWS     4    /* VWF_BUFFER = 4 rows of 26 tiles */

#ifdef EB_HAVE_JA
/* RENDER_VWF_GLYPH (asm/text/vwf/render_vwf_glyph.asm) with DECOMP_ENTRY2's
 * glyph decode: each 12-px row overwrites the 12 pixels at FLYOVER_VWF_X
 * (VWF_GLYPH_MASK_LEFT/CENTER/RIGHT), in the left, centre and right tiles. */
static void ja_flyover_render_glyph(uint16_t code) {
    uint16_t glyph = (uint16_t)(code - JA_FLYOVER_GLYPH_BASE);
    const uint8_t *font = ASSET_DATA(ASSET_JA_FONTS_FLYOVER_GFX);
    size_t font_size = ASSET_SIZE(ASSET_JA_FONTS_FLYOVER_GFX);
    if ((size_t)(glyph + 1) * JA_FLYOVER_GLYPH_BYTES > font_size) return;
    const uint8_t *g = font + (size_t)glyph * JA_FLYOVER_GLYPH_BYTES;

    uint16_t shift = flyover_vwf_x & 7;
    uint16_t sub_y = flyover_vwf_y & 7;
    uint16_t pos = (uint16_t)((((flyover_vwf_y >> 3) * flyover_tiles_per_row +
                                (flyover_vwf_x >> 3) + flyover_tile_offset) * 8 + sub_y) * 2);
    if (pos < flyover_dirty_min) flyover_dirty_min = pos;   /* UPDATE_VWF_DIRTY_MIN */
    /* The masks of the three tiles: 12 bits from `shift` in a 24-bit row. */
    uint32_t mask = 0xFFFu << (12 - shift);

    for (int row = 0; row < JA_FLYOVER_GLYPH_ROWS; row++) {
        const uint8_t *pair = g + (row / 2) * 3;
        uint16_t bits = (row & 1) ? (uint16_t)(((pair[1] & 0x0F) << 8) | pair[2])
                                  : (uint16_t)((pair[0] << 4) | (pair[1] >> 4));
        uint32_t v = (uint32_t)bits << (12 - shift);
        for (int t = 0; t < 3; t++) {
            uint8_t m = (uint8_t)(mask >> (16 - 8 * t));
            if (!m) continue;
            uint8_t b = (uint8_t)(v >> (16 - 8 * t));
            uint32_t at = (uint32_t)pos + (uint32_t)t * 16;
            if (at + 1 >= sizeof(flyover_vwf)) continue;
            /* Both planes: the glyph is colour 3. */
            flyover_vwf[at]     = (uint8_t)((flyover_vwf[at] & ~m) | (b & m));
            flyover_vwf[at + 1] = (uint8_t)((flyover_vwf[at + 1] & ~m) | (b & m));
        }
        pos += 2;
        if (row == JA_FLYOVER_GLYPH_ROWS - 1) break;
        sub_y = (sub_y + 1) & 7;
        if (sub_y == 0)   /* next tile row, same column */
            pos = (uint16_t)(pos + (flyover_tiles_per_row - 1) * 16);
    }
    pos = (uint16_t)(pos + 16 + ((mask & 0xFF) ? 16 : 0));
    if (pos > flyover_dirty_max) flyover_dirty_max = pos;   /* UPDATE_VWF_DIRTY_MAX */
}

/* RENDER_FLYOVER_TEXT_CHARACTER (render_flyover_text_character-jp.asm). */
static void ja_flyover_render_text_char(uint8_t first, uint8_t second) {
    ja_flyover_render_glyph((uint16_t)((first << 8) | second));
    flyover_vwf_x = (uint16_t)(flyover_vwf_x + JA_FLYOVER_ADVANCE);
}

/* RENDER_PARTY_MEMBER_NAME (render_party_member_name-jp.asm): up to 4 letters
 * of the name, each through JP_FONT_WIDTH_TABLE (text code - 0x20 -> glyph). */
static void ja_flyover_render_party_name(uint16_t char_id) {
    if (char_id < 1 || char_id > 4) return;
    const uint8_t *map = ASSET_DATA(ASSET_JA_FONTS_FLYOVER_MAP_BIN);
    size_t map_size = ASSET_SIZE(ASSET_JA_FONTS_FLYOVER_MAP_BIN);
    const uint8_t *name = party_characters[char_id - 1].name;
    for (int i = 0; i < JA_FLYOVER_NAME_MAX && name[i] != 0; i++) {
        size_t idx = (size_t)(name[i] - 0x20);
        if (name[i] < 0x20 || idx >= map_size) continue;
        ja_flyover_render_glyph((uint16_t)(map[idx] + JA_FLYOVER_GLYPH_BASE));
        flyover_vwf_x = (uint16_t)(flyover_vwf_x + JA_FLYOVER_ADVANCE);
    }
}
#endif /* EB_HAVE_JA */

/* ======================================================================
 * BLIT_FONT_TO_VWF_BUFFER (C49875)
 *
 * Blits a font glyph into the flyover VWF ert.buffer at the current position.
 * Handles sub-byte pixel alignment and tile boundary overlap.
 *
 * Assembly params: A=width, X=font_default_width (unused), Y=vwf_base,
 *                  @PARAM03=glyph_ptr (32-bit)
 * C port params: glyph_data=1bpp glyph, width=pixel width to blit
 * ====================================================================== */
static void flyover_blit_font(const uint8_t *glyph_data, uint16_t width) {
    uint16_t pixel_sub = flyover_pixel_offset % 8;  /* sub-byte position */
    uint16_t base_pos = flyover_byte_offset;         /* byte offset of current tile */

    /* Process two halves: top 8x8 (offset 0) and bottom 8x8 (offset +416) */
    for (int half = 0; half < 2; half++) {
        uint16_t write_pos = base_pos + (uint16_t)(half * FLYOVER_ROW_BYTES);
        for (int row = 0; row < 8; row++) {
            /* Read glyph byte (1bpp, inverted: 0=pixel, 1=bg) */
            uint8_t glyph_byte = glyph_data[half * 8 + row];

            /* Create mask: invert → shift right by pixel_sub → re-invert */
            uint8_t shifted = (uint8_t)((uint8_t)(~glyph_byte) >> pixel_sub);
            uint8_t mask = ~shifted;

            /* AND mask into plane 1 (odd byte), copy to plane 0 (even byte) */
            uint8_t result = flyover_vwf[write_pos + 1] & mask;
            flyover_vwf[write_pos + 1] = result;
            flyover_vwf[write_pos]     = result;

            write_pos += 2;  /* 2 bytes per row (plane 0 + plane 1) */
        }
    }

    /* Update pixel offset */
    flyover_pixel_offset += width;

    /* Check if we've crossed into the next tile */
    uint16_t new_byte_offset = (flyover_pixel_offset / 8) * 16;
    if (new_byte_offset == flyover_byte_offset) return;

    /* Handle overlap: glyph spans two tiles — blit remaining bits into next tile */
    flyover_byte_offset = new_byte_offset;
    uint16_t left_shift = 8 - pixel_sub;

    uint16_t overlap_base = new_byte_offset;

    for (int half = 0; half < 2; half++) {
        uint16_t write_pos = overlap_base + (uint16_t)(half * FLYOVER_ROW_BYTES);
        for (int row = 0; row < 8; row++) {
            uint8_t glyph_byte = glyph_data[half * 8 + row];
            uint8_t shifted = (uint8_t)((uint8_t)(~glyph_byte) << left_shift);
            uint8_t mask = ~shifted;

            uint8_t result = flyover_vwf[write_pos + 1] & mask;
            flyover_vwf[write_pos + 1] = result;
            flyover_vwf[write_pos]     = result;

            write_pos += 2;
        }
    }
}

/* ======================================================================
 * RENDER_LARGE_FONT_CHARACTER (C4999B)
 *
 * Renders an EB character (0x50+) using FONT_ID_LARGE into the flyover
 * VWF ert.buffer. Handles wide glyphs (>8px) by blitting in 8px chunks.
 * ====================================================================== */
static void flyover_render_large_char(uint16_t eb_char) {
    uint8_t glyph_index = (uint8_t)((eb_char - 0x50) & 0x7F);

    const uint8_t *glyph = font_get_glyph(FONT_ID_LARGE, glyph_index);
    if (!glyph) return;

    /* Get per-character pixel width from width data table */
    uint8_t char_width = font_get_width(FONT_ID_LARGE, glyph_index);
    uint16_t total_width = (uint16_t)char_width + 1;  /* assembly: INC @VIRTUAL02 */

    /* Column stride between 8-pixel chunks of a wide glyph.
     * Assembly uses font_table_entry::width (16), NOT bytes_per_glyph (32).
     * LARGE font: 32 bytes/glyph = two 16-byte columns (each 8px × 16 rows, 1bpp). */
    uint8_t font_stride = font_get_height(FONT_ID_LARGE);

    /* For wide glyphs (>8px), blit in 8-pixel chunks */
    const uint8_t *src = glyph;
    while (total_width > 8) {
        flyover_blit_font(src, 8);
        total_width -= 8;
        src += font_stride;  /* assembly: ADC @VIRTUAL04 (default width = stride) */
    }

    /* Blit remaining pixels */
    flyover_blit_font(src, total_width);
}

/* ======================================================================
 * RENDER_FLYOVER_TEXT_CHARACTER (C49D16) — thin wrapper
 * ====================================================================== */
static void flyover_render_text_char(uint16_t eb_char) {
    flyover_render_large_char(eb_char);
}

/* A script byte that is no command: one character (US), or the first byte of
 * a two-byte glyph code (Mother 2; the second byte follows). */
static void flyover_script_text(const uint8_t *script, uint32_t size, uint32_t *pos,
                                uint8_t first) {
#ifdef EB_HAVE_JA
    if (locale_is_ja()) {
        if (*pos < size)
            ja_flyover_render_text_char(first, script[(*pos)++]);
        return;
    }
#else
    (void)script; (void)size; (void)pos;
#endif
    flyover_render_text_char((uint16_t)first);
}

/* ======================================================================
 * RENDER_PARTY_MEMBER_NAME (C49CC3)
 *
 * Renders up to 5 characters of a party member's name using LARGE font.
 * Stops early if a character code is <= 0x50 (space = end of name).
 *
 * Assembly: char_id is 1-based party member index.
 * BRANCHGTS after CLC;SBC #79: branches while char > 0x50 (0x50 = space)
 * ====================================================================== */
static void flyover_render_party_name(uint16_t char_id) {
#ifdef EB_HAVE_JA
    if (locale_is_ja()) { ja_flyover_render_party_name(char_id); return; }
#endif
    if (char_id < 1 || char_id > 4) return;
    CharStruct *ch = &party_characters[char_id - 1];

    for (int i = 0; i < 5; i++) {
        uint8_t c = ch->name[i];
        /* Assembly: CLC; SBC #79; BRANCHGTS → branches when c >= 0x50 */
        if (c < 0x50) break;  /* characters below 0x50 are not valid EB text */
        flyover_render_large_char((uint16_t)c);
    }
}

/* ======================================================================
 * INVERT_VWF_BUFFER (C4984B)
 *
 * XORs entire flyover VWF ert.buffer with 0xFFFF.
 * Called before VRAM upload to convert from mask format
 * (0=glyph, 1=bg) to display format (1=glyph, 0=bg).
 * ====================================================================== */
static void flyover_invert_vwf(void) {
    uint16_t *buf = (uint16_t *)flyover_vwf;
    /* 32 * 26 = 832 words = 1664 bytes = full ert.buffer */
    for (int i = 0; i < 32 * 26; i++) {
        buf[i] ^= 0xFFFF;
    }
}

/* ======================================================================
 * Helper: set BG3 VRAM location registers.
 * Port of SET_BG3_VRAM_LOCATION (set_bg3_vram_location.asm).
 *
 * Assembly params: A=tilemap_size, X=tilemap_base, Y=tile_base
 * BG3SC = ((X>>8) & 0xFC) | (A & 0x03)
 * BG34NBA low nibble = (Y>>12) & 0x0F
 * Scroll positions reset to 0.
 * ====================================================================== */
static void set_bg3_vram_location(uint16_t tilemap_size, uint16_t tilemap_base,
                                   uint16_t tile_base) {
    ppu.bg_sc[2] = (uint8_t)(((tilemap_base >> 8) & 0xFC) | (tilemap_size & 0x03));
    ppu.bg_nba[1] = (uint8_t)((ppu.bg_nba[1] & 0xF0) | ((tile_base >> 12) & 0x0F));
    ppu.bg_hofs[2] = 0;
    ppu.bg_vofs[2] = 0;
}

/* ======================================================================
 * INIT_FLYOVER_TEXT_SCREEN (C49A56)
 *
 * Initializes the flyover text display:
 *   1. Force blank, set BG3 VRAM location
 *   2. Clear tile data in VRAM
 *   3. Load flyover palette (MOVEMENT_TEXT_STRING_PALETTE)
 *   4. Fill VWF ert.buffer with 0xFF
 *   5. Build BG2_BUFFER tilemap (26 usable tiles per row, 32 rows)
 *   6. Upload tilemap to VRAM
 *   7. Initialize flyover state variables
 * ====================================================================== */
/* The synchronous middle of flyover_init_screen() — everything between the
 * leading force-blank and the trailing blank-screen frame. Exposed so the
 * mode-step (FOP_CT_INIT_BODY) can run it between its own park-propagating
 * force/blank frames; the blocking flyover_init_screen() wrapper below keeps it
 * for the callroutine-context caller (play_flyover_script_prepare), which can't
 * park (disable_actionscript is set in a callroutine). */
static void flyover_init_screen_body(void) {
    /* SET_BG3_VRAM_LOCATION(NORMAL, TEXT_LAYER_TILEMAP=0x7C00, TEXT_LAYER_TILES=0x6000) */
    set_bg3_vram_location(0, VRAM_TEXT_LAYER_TILEMAP, VRAM_TEXT_LAYER_TILES);

    /* Clear all tile data: COPY_TO_VRAM1P ert.buffer(=0), TEXT_LAYER_TILES, $3800 bytes */
    memset(&ppu.vram[VRAM_TEXT_LAYER_TILES * 2], 0, 0x3800);

    /* Load flyover palette: MOVEMENT_TEXT_STRING_PALETTE → PALETTES[0..3] (8 bytes) */
    {
        size_t pal_size;
        pal_size = ASSET_SIZE(ASSET_DATA_MOVEMENT_TEXT_STRING_PALETTE_BIN);
        const uint8_t *pal_data = ASSET_DATA(ASSET_DATA_MOVEMENT_TEXT_STRING_PALETTE_BIN);
        if (pal_data && pal_size >= 8) {
            memcpy(ert.palettes, pal_data, 8);
        }
    }
    ert.palette_upload_mode = PALETTE_UPLOAD_FULL;

    /* Fill VWF ert.buffer with 0xFF (all background). Mother 2's buffer is
     * positive: 0 (init_flyover_text_screen-jp.asm). */
    memset(flyover_vwf, locale_is_ja() ? 0x00 : 0xFF, sizeof(flyover_vwf));

    /* Build BG2_BUFFER tilemap: 32 rows × 32 columns.
     * Columns 0-2 and 29-31: empty (0). Columns 3-28: tile indices with palette bit.
     * Tile indices start at 16 and increment across all rows. */
    uint16_t tile_idx = 16;
    for (int row = 0; row < 32; row++) {
        int tilemap_row_offset = row * 64;  /* 32 columns × 2 bytes */

        /* Clear first 3 entries (6 bytes) */
        win.bg2_buffer[tilemap_row_offset + 0] = 0;
        win.bg2_buffer[tilemap_row_offset + 1] = 0;
        win.bg2_buffer[tilemap_row_offset + 2] = 0;
        win.bg2_buffer[tilemap_row_offset + 3] = 0;
        win.bg2_buffer[tilemap_row_offset + 4] = 0;
        win.bg2_buffer[tilemap_row_offset + 5] = 0;

        /* Fill columns 3-28 (26 tiles) with tile indices + 0x2000 (palette/priority) */
        for (int col = 3; col < 29; col++) {
            uint16_t entry = tile_idx + 0x2000;
            int pos = tilemap_row_offset + col * 2;
            win.bg2_buffer[pos]     = (uint8_t)(entry & 0xFF);
            win.bg2_buffer[pos + 1] = (uint8_t)(entry >> 8);
            tile_idx++;
        }

        /* Clear last 3 entries (6 bytes) */
        win.bg2_buffer[tilemap_row_offset + 58] = 0;
        win.bg2_buffer[tilemap_row_offset + 59] = 0;
        win.bg2_buffer[tilemap_row_offset + 60] = 0;
        win.bg2_buffer[tilemap_row_offset + 61] = 0;
        win.bg2_buffer[tilemap_row_offset + 62] = 0;
        win.bg2_buffer[tilemap_row_offset + 63] = 0;
    }

    /* Upload tilemap to VRAM: COPY_TO_VRAM1P win.bg2_buffer, TEXT_LAYER_TILEMAP, $800 */
    memcpy(&ppu.vram[VRAM_TEXT_LAYER_TILEMAP * 2], win.bg2_buffer, 0x800);

    /* Initialize flyover state */
    flyover_tiles_per_row = 26;
    flyover_tile_offset = 0;
    flyover_dirty_min = 0xFFFF;  /* -1 */
    flyover_dirty_max = 0;
    flyover_vwf_x = 0;
    flyover_vwf_y = 0;
    flyover_pixel_offset = 0;
    flyover_byte_offset = 0;
}

/* Blocking INIT_FLYOVER_TEXT_SCREEN: force-blank frame, VRAM build, blank-screen
 * frame. Used only by the callroutine-context caller (play_flyover_script_prepare),
 * where disable_actionscript is set so neither frame can park. The mode-step
 * (FOP_CT_SETUP_A/FOP_CT_INIT_BODY) drives the same three steps with
 * park-propagating force/blank frames instead. */
static void flyover_init_screen(void) {
    force_blank_and_wait_vblank();
    flyover_init_screen_body();
    blank_screen_and_wait_vblank();
}

/* ======================================================================
 * UPLOAD_VWF_BUFFER_TO_VRAM (C49B6E)
 *
 * Inverts the VWF ert.buffer and uploads it to VRAM at the correct position
 * based on flyover_screen_offset. Handles VRAM wrapping when the upload
 * extends past the 32-row boundary.
 *
 * VRAM layout: 32 rows of 26 tiles at TEXT_LAYER_TILES + 0x150 (word offset).
 * Each row = 0x1A0 bytes (26 tiles × 16 bytes). Total = 0x3400 bytes.
 * Upload size = 0x04E0 bytes (3 rows).
 * ====================================================================== */
static void flyover_upload_vwf_to_vram_work(void) {
    /* Mother 2 (upload_vwf_buffer_to_vram-jp.asm): the buffer is already
     * positive, and the rows start at the tilemap's first tile (16). */
    if (!locale_is_ja())
        flyover_invert_vwf();

    uint16_t row_start = flyover_screen_offset * FLYOVER_ROW_BYTES;  /* offset * 0x1A0 */
    uint16_t upload_size = 0x04E0;  /* 3 rows */
    uint16_t vram_tile_start = VRAM_TEXT_LAYER_TILES +
        (locale_is_ja() ? 0x80 : 0x150);  /* word address */

    if (row_start + upload_size > FLYOVER_VRAM_TOTAL) {
        /* Wrap case: upload spans the 32-row boundary */
        uint16_t first_part = FLYOVER_VRAM_TOTAL - row_start;
        if (first_part > 0) {
            uint32_t vram_dest = (uint32_t)(vram_tile_start * 2) +
                                 (uint32_t)(flyover_screen_offset * 208 * 2);
            memcpy(&ppu.vram[vram_dest], flyover_vwf, first_part);
        }

        uint16_t second_part = upload_size - first_part;
        if (second_part > 0) {
            /* Wrapped portion goes to start of VRAM tile area */
            uint32_t wrap_src_offset = FLYOVER_VRAM_TOTAL - row_start;
            uint32_t vram_dest = (uint32_t)(vram_tile_start * 2);
            memcpy(&ppu.vram[vram_dest], flyover_vwf + wrap_src_offset, second_part);
        }
    } else {
        /* No wrap: straight copy */
        uint32_t vram_dest = (uint32_t)(vram_tile_start * 2) +
                             (uint32_t)(flyover_screen_offset * 208 * 2);
        memcpy(&ppu.vram[vram_dest], flyover_vwf, upload_size);
    }

    flyover_dirty_min = 0xFFFF;
    flyover_dirty_max = 0;
}

/* ======================================================================
 * SCROLL_FLYOVER_TEXT (C49C56, US version)
 *
 * Advances the text position by 'advance_y' pixels vertically.
 * Updates screen_offset for VRAM row wrapping.
 * Clears the VWF ert.buffer for the next line of text.
 * Resets horizontal position.
 * ====================================================================== */
static void flyover_scroll_text(uint16_t advance_y) {
    flyover_vwf_y += advance_y;
    flyover_vwf_x = 0;

    if (locale_is_ja()) {
        /* Mother 2: the screen moves by whole rows passed, and the VWF buffer
         * shifts up by them instead of being cleared. */
        uint16_t rows = flyover_vwf_y >> 3;
        flyover_screen_offset += rows;
        if (flyover_screen_offset >= 32)
            flyover_screen_offset -= 32;
        if (rows > JA_FLYOVER_VWF_ROWS) rows = JA_FLYOVER_VWF_ROWS;
        size_t keep = (size_t)(JA_FLYOVER_VWF_ROWS - rows) * FLYOVER_ROW_BYTES;
        memmove(flyover_vwf, flyover_vwf + (size_t)rows * FLYOVER_ROW_BYTES, keep);
        memset(flyover_vwf + keep, 0, (size_t)rows * FLYOVER_ROW_BYTES);
        flyover_vwf_y &= 0x0007;
        return;
    }

    /* Assembly (US): advance_y/8 + 1 rows added to screen offset */
    uint16_t rows = (flyover_vwf_y >> 3) + 1;
    flyover_screen_offset += rows;
    if (flyover_screen_offset >= 32)
        flyover_screen_offset -= 32;

    /* US version: wait for DMA, then clear entire VWF ert.buffer */
    memset(flyover_vwf, 0xFF, sizeof(flyover_vwf));

    /* Keep only sub-tile Y offset */
    flyover_vwf_y &= 0x0007;

    /* Reset horizontal position */
    flyover_pixel_offset = 0;
    flyover_byte_offset = 0;
}

/* ======================================================================
 * ADVANCE_FLYOVER_PIXEL_OFFSET (C49CA8)
 *
 * Advances the horizontal pixel position by (param + 8).
 * Updates flyover_byte_offset accordingly.
 * Used by flyover script opcode 0x01 for indentation/spacing.
 * ====================================================================== */
static void flyover_advance_pixel_offset(uint16_t advance) {
    if (locale_is_ja()) {
        /* Mother 2 (advance_flyover_pixel_offset-jp.asm): the argument is the
         * line's width in half glyphs, centred in 208 px: X = 104 - n * 24 / 8. */
        flyover_vwf_x = (uint16_t)(104 - (((advance & 0xFF) * 24) >> 3));
        return;
    }
    uint16_t val = (advance & 0xFF) + 8;
    flyover_pixel_offset += val;
    /* byte_offset = (pixel_offset / 8) * 16 */
    flyover_byte_offset = (flyover_pixel_offset >> 3) << 4;
}

/* ======================================================================
 * ADVANCE_TEXT_LINE_POSITION (C49D1E)
 *
 * Smoothly scrolls BG3 by advancing a sub-pixel accumulator.
 * Returns the updated accumulator value.
 * Used by COFFEETEA_SCENE for smooth line-by-line scrolling.
 *
 * Assembly: accumulator format = low 8 bits are sub-pixel,
 * high 8 bits count whole-pixel scrolls.
 * ====================================================================== */
static uint16_t flyover_advance_text_line(uint16_t accumulator) {
    oam_clear();

    uint16_t old_high = accumulator & 0xFF00;
    /* US retail: advance by 64 per tick; Mother 2 by 80 */
    uint16_t new_accum = accumulator + (locale_is_ja() ? 80 : 64);
    uint16_t new_high = new_accum & 0xFF00;

    if (new_high != old_high) {
        /* Crossed a whole-pixel boundary: scroll BG3 */
        int16_t delta = (int16_t)(new_high - old_high);
        /* ASR8_POSITIVE by 8: right shift by 8 = divide by 256 */
        int16_t pixels = delta >> 8;
        ppu.bg_vofs[2] += (uint16_t)pixels;
        update_screen();
    }

    return new_accum;
}

/* ======================================================================
 * UNDRAW_FLYOVER_TEXT (undraw_flyover_text.asm)
 *
 * Restores the normal BG3 text layer configuration after flyover mode.
 * ====================================================================== */
void undraw_flyover_text(void) {
    /* SET_BG3_VRAM_LOCATION(NORMAL, 0x7C00, 0x6000) — same as init */
    set_bg3_vram_location(0, VRAM_TEXT_LAYER_TILEMAP, VRAM_TEXT_LAYER_TILES);

    /* Restore battle screen tilemap to VRAM */
    upload_battle_screen_to_vram();

    /* Reload window border GFX */
    text_load_window_gfx();

    /* US version: upload text tiles (param=2) */
    upload_text_tiles_to_vram(2);

    /* Reload character window palette */
    load_character_window_palette();

    ert.palette_upload_mode = PALETTE_UPLOAD_FULL;

    /* Wide viewport (C port): end the camera shutter's gutter continuation
     * (LOAD_ANIMATION_SEQUENCE_FRAME). */
    if (ppu.bg_viewport_fill[2] == BG_VIEWPORT_CONTINUE)
        ppu.bg_viewport_fill[2] = BG_VIEWPORT_CENTER;
}

/* ======================================================================
 * Helper: load_background_animation (load_background_animation.asm)
 *
 * Sets up BG mode 1, configures BG1/BG2 VRAM locations, loads battle BG.
 * Used by COFFEETEA_SCENE for coffee/tea animated backgrounds.
 * ====================================================================== */
void load_background_animation(uint16_t bg1_layer, uint16_t bg2_layer) {
    force_blank_and_wait_vblank();

    /* SET_BGMODE(9): mode 1 + BG3 priority bit */
    ppu.bgmode = 0x09;

    /* SET_BG1_VRAM_LOCATION(size=NORMAL, tilemap=0x5800, tiles=0x0000) */
    ppu.bg_sc[0] = 0x58;
    ppu.bg_nba[0] = (uint8_t)(ppu.bg_nba[0] & 0xF0);  /* BG1 tile base = 0 */
    ppu.bg_hofs[0] = 0;
    ppu.bg_vofs[0] = 0;

    /* SET_BG2_VRAM_LOCATION(size=NORMAL, tilemap=0x5C00, tiles=0x1000) */
    ppu.bg_sc[1] = 0x5C;
    ppu.bg_nba[0] = (uint8_t)((ppu.bg_nba[0] & 0x0F) | 0x10);  /* BG2 tile base = 0x1000 */
    ppu.bg_hofs[1] = 0;
    ppu.bg_vofs[1] = 0;

    /* LOAD_BATTLE_BG(bg1_layer, bg2_layer, letterbox=4) */
    load_battle_bg(bg1_layer, bg2_layer, 4);

    /* Entities stay on screen over these backgrounds (MOVEMENT_LOAD_BATTLEBG:
     * Poo's Mu training spirit fight), placed in SNES screen coordinates
     * with BG1 scroll at 0 (EVENT_340 SET_X/SET_Y $80,$70, EVENT_342's
     * ENTITY_SCREEN_TO_WORLD). load_battle_bg centers sprites vertically
     * (sprite_y_offset); center them horizontally too, as the Sound Stone
     * does. No-op at native res; overworld_setup_vram() (RELOAD_MAP) resets it. */
    ppu.sprite_x_offset = EB_VIEWPORT_PAD_LEFT;

    blank_screen_and_wait_vblank();
}

/* BATTLEBG_LAYER enum values from battlebgs.asm (used by coffeetea_scene). */
#define BATTLEBG_COFFEE1 231
#define BATTLEBG_COFFEE2 232
#define BATTLEBG_TEA1    233
#define BATTLEBG_TEA2    234

/* ======================================================================
 * GAME_MODE_FLYOVER step
 *
 * Run-to-completion form of play_flyover_script() (FO_SCRIPT) and
 * coffeetea_scene() (FO_COFFEETEA). The single yield is owned by the pump; this
 * body never calls wait_for_vblank(). See the FlyoverState comment in
 * mode_stack.h. The internal for(;;) advances non-yielding phase transitions
 * (`continue`) and returns CONTINUE only at the original's yield points. The
 * flyover brightness ramps (no mosaic) are inlined; the script-render statics
 * (flyover_screen_offset, …) stay in .bss.
 * ====================================================================== */
StepResult mode_step_flyover(ModeState *st) {
    FlyoverState *s = &st->flyover;

    for (;;) {
        switch ((FlyoverPhase)s->phase) {

        /* ---------------- FO_SCRIPT (play_flyover_script) ---------------- */
        case FOP_S_PARSE: {
            const uint8_t *script = ASSET_DATA(flyover_script_ids[s->id]);
            /* opcode 0x09 continuation: upload (yielded) -> wait -> scroll. */
            if (s->sub == 1) { s->sub = 2; return STEP_RESULT_CONTINUE(); }
            if (s->sub == 2) { flyover_scroll_text(flyover_line_height()); s->sub = 0; }

            int to_fadein = 0;
            while (!to_fadein) {
                if (s->pos >= s->script_size) { to_fadein = 1; break; }
                uint8_t opcode = script[s->pos++];
                if (opcode == 0x00) {
                    to_fadein = 1;
                } else if (opcode == 0x02) {
                    if (s->pos < s->script_size)
                        flyover_screen_offset = script[s->pos++];
                } else if (opcode == 0x09) {
                    flyover_upload_vwf_to_vram_work();
                    s->sub = 1;
                    return STEP_RESULT_CONTINUE();   /* the upload's wait */
                } else if (opcode == 0x01) {
                    if (s->pos < s->script_size)
                        flyover_advance_pixel_offset(script[s->pos++]);
                } else if (opcode == 0x08) {
                    if (s->pos < s->script_size)
                        flyover_render_party_name(script[s->pos++]);
                } else {
                    flyover_script_text(script, s->script_size, &s->pos, opcode);
                }
            }

            /* Parse complete: TM=$04 (BG3 only) then fade in (step 1, delay 3). */
            ppu.tm = 0x04;
            ppu.inidisp = 0x00;
            ppu.mosaic = 0;
            s->ramp_delay_left = 0;
            s->phase = FOP_S_FADEIN;
            continue;
        }

        case FOP_S_FADEIN:
            if (s->ramp_delay_left > 0) { s->ramp_delay_left--; return STEP_RESULT_CONTINUE(); }
            {
                uint8_t  b    = ppu.inidisp & 0x0F;
                uint16_t next = (uint16_t)b + 1;
                if (next >= 0x0F) {
                    ppu.inidisp   = (uint8_t)((ppu.inidisp & 0xF0) | 0x0F);
                    s->display_left = 180;
                    s->phase      = FOP_S_DISPLAY;
                    continue;
                }
                ppu.inidisp      = (uint8_t)((ppu.inidisp & 0xF0) | (uint8_t)next);
                s->ramp_delay_left = 3;
                continue;
            }

        case FOP_S_DISPLAY:
            if (s->display_left == 0) {
                s->ramp_delay_left = 0;
                s->phase = FOP_S_FADEOUT;
                continue;
            }
            s->display_left--;
            return STEP_RESULT_CONTINUE();

        case FOP_S_FADEOUT:
            if (s->ramp_delay_left > 0) { s->ramp_delay_left--; return STEP_RESULT_CONTINUE(); }
            ppu.mosaic = 0;
            if (!(ppu.inidisp & 0x80)) {
                uint8_t b    = ppu.inidisp & 0x0F;
                int16_t next = (int16_t)b - 1;
                if (next >= 0) {
                    ppu.inidisp      = (uint8_t)((ppu.inidisp & 0xF0) | (uint8_t)next);
                    s->ramp_delay_left = 3;
                    continue;
                }
            }
            ppu.inidisp = 0x80;
            s->phase = FOP_S_CLEAN1;
            continue;

        case FOP_S_CLEAN1:
            ppu.tm = 0x17;
            memset(win.bg2_buffer, 0, 0x700);
            dt.enable_word_wrap = (uint16_t)-1;
            s->resume_phase = FOP_S_CLEAN2;
            if (force_blank_and_wait_vblank_work_step()) {
                s->phase = FOP_RTC_FLUSH;
                return actionscript_frame_take_push();
            }
            s->phase = FOP_S_CLEAN2;
            return STEP_RESULT_CONTINUE();

        case FOP_S_CLEAN2:
            undraw_flyover_text();
            entities.tick_callback_hi[ENT(23)] = s->saved_ent23_tick_hi;
            s->resume_phase = FOP_S_DONE;
            if (blank_screen_and_wait_vblank_work_step()) {
                s->phase = FOP_RTC_FLUSH;
                return actionscript_frame_take_push();
            }
            s->phase = FOP_S_DONE;
            return STEP_RESULT_CONTINUE();

        case FOP_S_DONE:
            return STEP_RESULT_POP(0);

        /* ---------------- FO_COFFEETEA (coffeetea_scene) ---------------- */
        case FOP_CT_FADEOUT1:
            /* flyover_fade_out_blocking(1, 1, 0): ramp down, delay 1, no mosaic. */
            if (s->ramp_delay_left > 0) { s->ramp_delay_left--; return STEP_RESULT_CONTINUE(); }
            ppu.mosaic = 0;
            if (!(ppu.inidisp & 0x80)) {
                uint8_t b    = ppu.inidisp & 0x0F;
                int16_t next = (int16_t)b - 1;
                if (next >= 0) {
                    ppu.inidisp      = (uint8_t)((ppu.inidisp & 0xF0) | (uint8_t)next);
                    s->ramp_delay_left = 1;
                    continue;
                }
            }
            ppu.inidisp = 0x80;
            s->phase = FOP_CT_SETUP_A;
            continue;

        case FOP_CT_SETUP_A:
            /* flyover_init_screen() leading force-blank frame (park-propagating). */
            s->resume_phase = FOP_CT_INIT_BODY;
            if (force_blank_and_wait_vblank_work_step()) {
                s->phase = FOP_RTC_FLUSH;
                return actionscript_frame_take_push();
            }
            s->phase = FOP_CT_INIT_BODY;
            return STEP_RESULT_CONTINUE();

        case FOP_CT_INIT_BODY:
            /* flyover_init_screen() VRAM build, then its trailing blank-screen frame. */
            flyover_init_screen_body();
            s->resume_phase = FOP_CT_SETUP_A2;
            if (blank_screen_and_wait_vblank_work_step()) {
                s->phase = FOP_RTC_FLUSH;
                return actionscript_frame_take_push();
            }
            s->phase = FOP_CT_SETUP_A2;
            return STEP_RESULT_CONTINUE();

        case FOP_CT_SETUP_A2:
            oam_clear();
            /* load_background_animation() start */
            s->resume_phase = FOP_CT_SETUP_B;
            if (force_blank_and_wait_vblank_work_step()) {
                s->phase = FOP_RTC_FLUSH;
                return actionscript_frame_take_push();
            }
            s->phase = FOP_CT_SETUP_B;
            return STEP_RESULT_CONTINUE();

        case FOP_CT_SETUP_B: {
            /* load_background_animation() body (replicated; the public blocking
             * version stays for ending.c / callroutine.c). */
            ppu.bgmode  = 0x09;
            ppu.bg_sc[0]  = 0x58;
            ppu.bg_nba[0] = (uint8_t)(ppu.bg_nba[0] & 0xF0);
            ppu.bg_hofs[0] = 0;
            ppu.bg_vofs[0] = 0;
            ppu.bg_sc[1]  = 0x5C;
            ppu.bg_nba[0] = (uint8_t)((ppu.bg_nba[0] & 0x0F) | 0x10);
            ppu.bg_hofs[1] = 0;
            ppu.bg_vofs[1] = 0;
            uint16_t bg1 = (s->id == 0) ? BATTLEBG_COFFEE1 : BATTLEBG_TEA1;
            uint16_t bg2 = (s->id == 0) ? BATTLEBG_COFFEE2 : BATTLEBG_TEA2;
            load_battle_bg(bg1, bg2, 4);
            s->resume_phase = FOP_CT_SETUP_C;
            if (blank_screen_and_wait_vblank_work_step()) {
                s->phase = FOP_RTC_FLUSH;
                return actionscript_frame_take_push();
            }
            s->phase = FOP_CT_SETUP_C;
            return STEP_RESULT_CONTINUE();
        }

        case FOP_CT_SETUP_C: {
            fade_in(1, 1);
            flyover_screen_offset = 28;
            const uint8_t *script = ASSET_DATA(s->id == 0 ? ASSET_COFFEE_BIN : ASSET_TEA_BIN);
            if (!script)
                return STEP_RESULT_POP(0);   /* blocking: if(!script) return; */
            dt.enable_word_wrap = 0;
            s->scroll_accum = 0;
            s->phase = FOP_CT_PARSE;
            continue;
        }

        case FOP_CT_PARSE: {
            const uint8_t *script = ASSET_DATA(s->id == 0 ? ASSET_COFFEE_BIN : ASSET_TEA_BIN);
            /* opcode 0x09 smooth-scroll inner loop continuation. After each yield
             * (upload's wait, then wait_and_update_battle_effects' wait) we run
             * update_battle_screen_effects(), then either advance + yield again or
             * finish the line. */
            if (s->sub == 1) {
                /* The line's scroll: 32 px of the accumulator's high byte (US),
                 * 18 (Mother 2, coffee_tea_scene-jp.asm's 4608). */
                uint16_t line_accum = locale_is_ja() ? (FLYOVER_LINE_JA << 8) : 8192;
                update_battle_screen_effects();
                if (s->scroll_accum < line_accum) {
                    s->scroll_accum = flyover_advance_text_line(s->scroll_accum);
                    return STEP_RESULT_CONTINUE();
                }
                s->scroll_accum -= line_accum;
                flyover_scroll_text(flyover_line_height());
                s->sub = 0;
            }

            int to_fadeout = 0;
            while (!to_fadeout) {
                if (s->pos >= s->script_size) { to_fadeout = 1; break; }
                uint8_t opcode = script[s->pos++];
                if (opcode == 0x00) {
                    to_fadeout = 1;
                } else if (opcode == 0x09) {
                    s->scroll_accum = flyover_advance_text_line(s->scroll_accum);
                    flyover_upload_vwf_to_vram_work();
                    s->sub = 1;
                    return STEP_RESULT_CONTINUE();   /* the upload's wait */
                } else if (opcode == 0x01) {
                    if (s->pos < s->script_size)
                        flyover_advance_pixel_offset(script[s->pos++]);
                } else if (opcode == 0x08) {
                    if (s->pos < s->script_size)
                        flyover_render_party_name(script[s->pos++]);
                } else {
                    flyover_script_text(script, s->script_size, &s->pos, opcode);
                }
            }

            fade_out(1, 1);
            s->fade_primed = 0;
            s->phase = FOP_CT_FADEWAIT;
            continue;
        }

        case FOP_CT_FADEWAIT:
            /* while (fade_active()) { wait; update_battle_screen_effects(); fade_update(); } */
            if (s->fade_primed) {
                update_battle_screen_effects();
                fade_update();
            }
            s->fade_primed = 1;
            if (!fade_active()) { s->phase = FOP_CT_CLEAN1; continue; }
            return STEP_RESULT_CONTINUE();

        case FOP_CT_CLEAN1:
            s->resume_phase = FOP_CT_CLEAN2;
            if (force_blank_and_wait_vblank_work_step()) {
                s->phase = FOP_RTC_FLUSH;
                return actionscript_frame_take_push();
            }
            s->phase = FOP_CT_CLEAN2;
            return STEP_RESULT_CONTINUE();

        case FOP_CT_CLEAN2:
            reload_map();
            memset(win.bg2_buffer, 0, 1792);
            dt.enable_word_wrap = 0xFF;
            s->resume_phase = FOP_CT_CLEAN3;
            if (force_blank_and_wait_vblank_work_step()) {
                s->phase = FOP_RTC_FLUSH;
                return actionscript_frame_take_push();
            }
            s->phase = FOP_CT_CLEAN3;
            return STEP_RESULT_CONTINUE();

        case FOP_CT_CLEAN3:
            undraw_flyover_text();
            s->resume_phase = FOP_CT_DONE;
            if (blank_screen_and_wait_vblank_work_step()) {
                s->phase = FOP_RTC_FLUSH;
                return actionscript_frame_take_push();
            }
            s->phase = FOP_CT_DONE;
            return STEP_RESULT_CONTINUE();

        case FOP_CT_DONE:
            fade_in(1, 1);
            return STEP_RESULT_POP(0);

        case FOP_RTC_FLUSH:
            /* Resume after a parked force/blank-screen frame: finish its render,
             * then return to the phase that requested it. */
            render_frame_tick_work_flush();
            s->phase = (uint8_t)s->resume_phase;
            return STEP_RESULT_CONTINUE();
        }

        return STEP_RESULT_POP(0);   /* unreachable */
    }
}

/* ======================================================================
 * PLAY_FLYOVER_SCRIPT (C49EC4)
 *
 * Bytecode interpreter for flyover text scripts.
 * Opcodes:
 *   0x00: end of script
 *   0x01 <byte>: advance pixel offset
 *   0x02 <byte>: set screen offset
 *   0x08 <byte>: render party member name
 *   0x09: upload VWF to VRAM, wait, scroll
 *   Other: render as EB character
 *
 * After parsing, fades in (mosaic), displays for 180 frames, fades out.
 * Then restores normal display.
 * ====================================================================== */
bool play_flyover_script_prepare(uint16_t id, uint16_t *saved_ent23_tick_hi,
                                 uint32_t *script_size) {
    if (id >= 8) return false;

    /* Assembly lines 11-15: save entity 23 tick_callback_hi then disable.
     * Prevents UPDATE_OVERWORLD_FRAME from running during the flyover.
     * The saved value is restored at the end so entity 23 returns to its
     * pre-flyover state (enabled or disabled). */
    *saved_ent23_tick_hi = entities.tick_callback_hi[ENT(23)];
    entities.tick_callback_hi[ENT(23)] = *saved_ent23_tick_hi |
        (OBJECT_TICK_DISABLED | OBJECT_MOVE_DISABLED);

    flyover_init_screen();

    /* Load script data */
    *script_size = (uint32_t)ASSET_SIZE(flyover_script_ids[id]);
    const uint8_t *script = ASSET_DATA(flyover_script_ids[id]);
    if (!script) return false;  /* (matches blocking: leaves entity 23 disabled) */

    dt.enable_word_wrap = 0;
    return true;
}

/* ======================================================================
 * COFFEETEA_SCENE (coffee_tea_scene.asm)
 *
 * Full-screen animated text sequence for coffee/tea breaks (type 0 = coffee,
 * 1 = tea). The entire scene runs to completion as GAME_MODE_FLYOVER
 * (FO_COFFEETEA): fade out with mosaic, init flyover screen + load coffee/tea
 * battle BG, clear OAM, fade in, parse the smooth-scroll text script, fade out
 * and wait, reload map, clear BG2, undraw flyover, fade in. The blocking
 * coffeetea_scene() pump bridge was deleted (D4b); its sole caller — the debug
 * Tea command and CC_1F_41 cases 1/2 (GAME_MODE_SPECIAL_EVENT) — build the
 * FO_COFFEETEA init and STEP_PUSH GAME_MODE_FLYOVER directly. (The script
 * null-check happens in FOP_CT_SETUP_C, after the fade/BG setup.)
 * ====================================================================== */

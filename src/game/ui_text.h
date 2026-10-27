#ifndef GAME_UI_TEXT_H
#define GAME_UI_TEXT_H

/*
 * Interface strings the C code prints from literals (menu items, prompts).
 *
 * English prints the literal at the call site, so the English path is the
 * code it always was. Japanese prints the Mother 2 string for the same
 * purpose, from JA/text/ui_strings.bin (ebtools/ja_interface.py UI_TEXTS,
 * which lists the ROM symbol of each and must stay in this enum's order;
 * tests/test_ja_interface.py checks).
 *
 *     add_menu_item(ui_text(UI_FILE_CONTINUE, "Continue"), 1, 0, 0);
 *     print_string(ui_text(UI_FILE_LEVEL, "Level:"));
 */

typedef enum {
    /* asm/data/text/file_select_text.asm */
    UI_FILE_START_NEW_GAME, /* after the slot number: ": Start New Game" */
    UI_FILE_LEVEL,
    UI_FILE_TEXT_SPEED,
    UI_FILE_SPEED_FAST,
    UI_FILE_SPEED_MEDIUM,
    UI_FILE_SPEED_SLOW,
    UI_FILE_CONTINUE,
    UI_FILE_COPY,
    UI_FILE_DELETE,
    UI_FILE_SET_UP,
    UI_FILE_COPY_TO_WHERE,
    UI_FILE_DELETE_CONFIRM, /* Japanese: after the name, "を けします。いいですか?" */
    UI_FILE_DELETE_NO,
    UI_FILE_DELETE_YES,
    UI_FILE_SELECT_TEXT_SPEED,
    UI_FILE_SELECT_SOUND,
    UI_FILE_SOUND_STEREO,
    UI_FILE_SOUND_MONO,
    UI_FILE_WHICH_STYLE,
    UI_FILE_FLAVOR_PLAIN,
    UI_FILE_FLAVOR_MINT,
    UI_FILE_FLAVOR_STRAWBERRY,
    UI_FILE_FLAVOR_BANANA,
    UI_FILE_FLAVOR_PEANUT,
    UI_FILE_FAVORITE_FOOD,
    UI_FILE_COOLEST_THING,
    UI_FILE_ARE_YOU_SURE,
    UI_FILE_YEP,
    UI_FILE_NOPE,
    /* asm/data/text/battle_menu_text-jp.asm, battle_to_text-jp.asm */
    UI_BATTLE_BASH,
    UI_BATTLE_GOODS,
    UI_BATTLE_AUTO_FIGHT,
    UI_BATTLE_PSI,
    UI_BATTLE_DEFEND,
    UI_BATTLE_PRAY,
    UI_BATTLE_SHOOT,
    UI_BATTLE_SPY,
    UI_BATTLE_RUN_AWAY,
    UI_BATTLE_MIRROR,
    UI_BATTLE_DO_NOTHING,
    UI_BATTLE_TO,
    /* asm/data/item_use_menu_strings.asm */
    UI_GOODS_USE,
    UI_GOODS_GIVE,
    UI_GOODS_DROP,
    UI_GOODS_HELP,
    /* asm/data/text/menu_overflow_text.asm: the item that pages a long menu */
    UI_MENU_OVERFLOW,
    UI_TEXT_COUNT,
} UiText;

/* Bytes per string in JA/text/ui_strings.bin (null-padded). */
#define UI_TEXT_SIZE 32

/* The string to print for `id`: `en` in English; in Japanese the Mother 2
 * string as eb_char_to_ascii chars (they round-trip through print_string and
 * add_menu_item), or `en` in a build without the Japanese assets. The
 * Japanese strings live as long as the program. */
const char *ui_text(UiText id, const char *en);

#endif /* GAME_UI_TEXT_H */

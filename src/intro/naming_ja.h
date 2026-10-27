#ifndef INTRO_NAMING_JA_H
#define INTRO_NAMING_JA_H

/*
 * The naming screens in Japanese: Mother 2's kana keyboard, prompts, Don't Care
 * names and confirmation (docs/adr/0003-japanese-locale.md). Each function is the
 * Japanese counterpart of a piece of file_select.c or display_text_menus.c and is
 * called only while locale_is_ja().
 */

#include "core/types.h"
#include "core/mode_stack.h"

/* Mother 2's name length for new-game naming index `i` (0-3 the party,
 * 4 the dog, 5 the food, 6 the thing): the JPN field sizes, 4 for a name, 6
 * otherwise. The US buffers are larger and stay as they are. */
int ja_naming_max_len(int i);

/* NAME_A_CHARACTER's front (asm/intro/name_a_character.asm, JPN): create the
 * name box and the message window, print the prompt, and render the name box as
 * the keyboard will show it (an existing name, the bullet, placeholders).
 * Returns the name display's tile columns. */
int ja_naming_front(int naming_index, const uint8_t *name);

/* The keyboard seed (TEXT_INPUT_DIALOG front, asm/text/text_input_dialog-jp.asm);
 * same arguments as text_input_prepare. The name is kept in the state: the
 * Japanese keyboard always starts from `existing_name`, as Mother 2's name box
 * shows the current name. */
void ja_text_input_prepare(ModeState *init, int name_target, int max_len,
                           int naming_index, uint16_t name_display_window_id,
                           int name_text_y, const uint8_t *existing_name);

/* GAME_MODE_TEXT_INPUT in Japanese (TEXT_INPUT_DIALOG, JPN). */
StepResult ja_text_input_step(ModeState *st);

/* The naming confirmation windows (file_select_menu_loop-jp.asm @SHOW_CONFIRM_NAME
 * .. PRINT_MENU_ITEMS), up to the selection menu the caller pushes. */
void ja_naming_confirm_build(void);

/* GAME_MODE_ENTER_NAME in Japanese (asm/text/enter_your_name_please-jp.asm). */
StepResult ja_enter_name_step(ModeState *st);

#endif /* INTRO_NAMING_JA_H */

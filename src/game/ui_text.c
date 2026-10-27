#include "game/ui_text.h"

#include "core/locale.h"
#include "data/assets.h"
#include "game/text.h"

const char *ui_text(UiText id, const char *en) {
#ifdef EB_HAVE_JA
    if (locale_is_ja() && (unsigned)id < UI_TEXT_COUNT) {
        /* Decoded once: the Locale never changes while the game runs */
        static char cache[UI_TEXT_COUNT][UI_TEXT_SIZE];
        static bool decoded;
        if (!decoded) {
            const uint8_t *data = ASSET_DATA(ASSET_JA_TEXT_UI_STRINGS_BIN);
            size_t size = ASSET_SIZE(ASSET_JA_TEXT_UI_STRINGS_BIN);
            for (size_t i = 0; i < UI_TEXT_COUNT && (i + 1) * UI_TEXT_SIZE <= size; i++) {
                const uint8_t *s = data + i * UI_TEXT_SIZE;
                for (size_t j = 0; j < UI_TEXT_SIZE - 1 && s[j]; j++)
                    cache[i][j] = eb_char_to_ascii(s[j]);
            }
            decoded = true;
        }
        return cache[id];
    }
#endif
    (void)id;
    return en;
}

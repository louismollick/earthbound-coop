/* The running Locale. See locale.h. */
#include "core/locale.h"

#include <string.h>

#include "data/assets.h" /* EB_HAVE_JA when the Japanese assets are embedded */

Locale g_locale = LOCALE_EN;

static const struct {
    const char *code, *name;
} k_locales[LOCALE_COUNT] = {
    [LOCALE_EN]       = { "en", "English" },
    [LOCALE_JA]       = { "ja", "Japanese" },
    [LOCALE_JA_KANJI] = { "ja-kanji", "Japanese (kanji)" },
};

bool locale_available(Locale l) {
    switch (l) {
    case LOCALE_EN:
        return true;
    case LOCALE_JA:
#ifdef EB_HAVE_JA
        return true;
#else
        return false;
#endif
    case LOCALE_JA_KANJI:
#if defined(EB_HAVE_JA) && defined(EB_HAVE_JA_KANJI)
        return true;
#else
        return false;
#endif
    default:
        return false;
    }
}

bool locale_set(Locale l) {
    if (!locale_available(l))
        return false;
    g_locale = l;
    return true;
}

bool locale_parse(const char *code, Locale *out) {
    for (int i = 0; i < LOCALE_COUNT; i++) {
        if (strcmp(code, k_locales[i].code) == 0) {
            *out = (Locale)i;
            return true;
        }
    }
    return false;
}

const char *locale_code(Locale l) {
    return (unsigned)l < LOCALE_COUNT ? k_locales[l].code : "?";
}

const char *locale_name(Locale l) {
    return (unsigned)l < LOCALE_COUNT ? k_locales[l].name : "?";
}

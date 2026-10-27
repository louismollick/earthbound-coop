#ifndef CORE_LOCALE_H
#define CORE_LOCALE_H

/*
 * The Locale: which Language the game prints (docs/adr/0003-japanese-locale.md).
 *
 * Picked once before the game starts (--lang, EB_LANG, the launcher) and never
 * changed while it runs. It is not game state: saves and savestates record it
 * only to refuse loading into the other Language. English is the default and
 * runs exactly the code paths it ran before Japanese existed.
 */

#include "core/types.h"

typedef enum {
    LOCALE_EN,       /* English: the US text and encoding */
    LOCALE_JA,       /* Japanese kana: Mother 2's text and encoding */
    LOCALE_JA_KANJI, /* Japanese with a local kanji script (J4); shares JA's saves */
    LOCALE_COUNT,
} Locale;

/* The running Locale. Read through locale_get() / locale_is_ja(). */
extern Locale g_locale;

static inline Locale locale_get(void) { return g_locale; }

/* True for both Japanese Locales (they share the text encoding and the fonts). */
static inline bool locale_is_ja(void) { return g_locale != LOCALE_EN; }

/* Set the Locale. Only valid before game_init() (fonts, text tables and asset
 * overrides are bound there) and before net_start() (the online fingerprint
 * carries it). Returns false, changing nothing, if this build lacks it. */
bool locale_set(Locale l);

/* Whether this build embeds the assets for `l`: English always, Japanese with
 * the Mother 2 extraction (EB_HAVE_JA), kanji also with its script (EB_HAVE_JA_KANJI). */
bool locale_available(Locale l);

/* "en", "ja" or "ja-kanji" (the --lang / EB_LANG / online.cfg spelling) to a
 * Locale; returns false for anything else. */
bool locale_parse(const char *code, Locale *out);

/* The --lang spelling of `l` ("en", ...). */
const char *locale_code(Locale l);

/* The Language's English display name ("English", "Japanese", "Japanese (kanji)"),
 * for the launcher and error messages. */
const char *locale_name(Locale l);

#endif /* CORE_LOCALE_H */

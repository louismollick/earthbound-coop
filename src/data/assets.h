#ifndef DATA_ASSETS_H
#define DATA_ASSETS_H

#include "core/types.h"
#include "embedded_assets.h"

/* Direct access macros — no branch, no out-pointer overhead.
 * Use ASSET_DATA(ASSET_FOO) and ASSET_SIZE(ASSET_FOO) instead of asset_get().
 * For parameterized families: ASSET_DATA(ASSET_FAMILY(n)) / ASSET_SIZE(ASSET_FAMILY(n)).
 *
 * Japanese overrides: in a build with the Japanese assets (EB_HAVE_JA, from the
 * generated registry), an asset with a JA/ variant (asset_ja_override[id] >= 0)
 * resolves to that variant while the Locale is Japanese. English, and every
 * build without them, reads the asset itself.
 */
#ifdef EB_HAVE_JA
#include "core/locale.h"
static inline AssetId asset_resolve(AssetId id) {
    return (locale_is_ja() && asset_ja_override[id] >= 0) ? (AssetId)asset_ja_override[id] : id;
}
#else
#define asset_resolve(id) (id)
#endif

#define ASSET_DATA(id) ((const uint8_t *)embedded_assets[asset_resolve(id)].data)
#define ASSET_SIZE(id) ((size_t)*embedded_assets[asset_resolve(id)].size_ptr)

/* The asset as embedded, never overridden: for the screens that stay English
 * (the launcher and online overlay's font) and anything that must see the raw
 * registry. */
#define ASSET_DATA_BASE(id) ((const uint8_t *)embedded_assets[id].data)
#define ASSET_SIZE_BASE(id) ((size_t)*embedded_assets[id].size_ptr)

#endif /* DATA_ASSETS_H */

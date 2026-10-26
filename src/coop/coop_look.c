/*
 * Look-only scan: see coop_look.h.
 *
 * The scan walks text bytecode exactly as the C runtime decodes it
 * (step_display_text_run in display_text.c and the cc_18..cc_1f dispatchers in
 * display_text_cc.c). Argument lengths come from those handlers, not from
 * ebtools/text_dsl/opcodes.py, which disagrees in a few places (19 24 reads 5
 * bytes, 1C 09 reads 1, 18 08 reads 4).
 *
 * Every distinct branch target is a "run": decode forward from it until 02
 * (END_BLOCK: the end of the path, or the return of a call, whose caller's
 * fallthrough is its own path) or 0A (JUMP: no fallthrough). Conditional
 * branches, calls and menu hover scripts add their targets to the work list and
 * the run carries on with the fallthrough. The work list is also the visited
 * set, so each target starts a run once (runs that merge re-decode the shared
 * tail, which the target cap bounds).
 *
 * Cross-checked against a YAML-level reachability walk over every NPC config
 * text pointer (same whitelist, 1314/1314 agree, 2026-10-26).
 */
#include "coop/coop_look.h"

#include "data/text_refs.h"
#include "game/display_text.h"
#include "game/map_loader.h"
#include "game/window.h"
#include "include/binary.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    uint32_t targets[COOP_LOOK_MAX_TARGETS]; /* visited targets in discovery order (the work list) */
    uint16_t count;
    CoopLookScan *out;
} Scan;

/* Record why the scan stopped; returns false for the caller to pass up. */
static bool stop(Scan *s, CoopLookReason reason, uint32_t addr, uint8_t cc, uint8_t sub) {
    s->out->reason = reason;
    s->out->addr = addr;
    s->out->cc = cc;
    s->out->sub = sub;
    return false;
}

/* Queue a branch target found at text address `at` (0 never resolves to text). */
static bool add_target(Scan *s, uint32_t target, uint32_t at) {
    if (target == 0)
        return stop(s, COOP_LOOK_BAD_ADDR, at, 0, 0);
    for (uint16_t i = 0; i < s->count; i++)
        if (s->targets[i] == target)
            return true;
    if (s->count == COOP_LOOK_MAX_TARGETS)
        return stop(s, COOP_LOOK_CAP, at, 0, 0);
    s->targets[s->count++] = target;
    return true;
}

/* Queue an optional target: 0 means none (the runtime skips it). */
static bool add_optional(Scan *s, uint32_t target, uint32_t at) {
    return target == 0 || add_target(s, target, at);
}

/* Argument byte count of a whitelisted fixed-length CC (after cc and sub).
 * Branches and variable lengths are handled in op_args. -1 = not whitelisted. */
static int fixed_len(uint8_t cc, uint8_t sub, const uint8_t *a, size_t avail) {
    switch (cc) {
    case 0x00: case 0x01: case 0x03:            /* line break, new line, prompt */
    case 0x0F:                                  /* increment secondary memory */
    case 0x11: case 0x12: case 0x13: case 0x14: /* selection menu, clear line, halts */
        return 0;
    case 0x07: return 2;                        /* check event flag */
    case 0x0B: case 0x0C: case 0x0D: case 0x0E: /* working/argument memory */
    case 0x10:                                  /* pause */
        return 1;

    case 0x18: /* windows */
        switch (sub) {
        case 0x00: case 0x02: case 0x04: case 0x06: case 0x0A: return 0;
        case 0x01: case 0x03: case 0x09: return 1;
        case 0x05: case 0x0D: return 2;          /* text alignment, status window */
        case 0x07: return 5;                     /* compare memory */
        default: return -1;
        }

    case 0x19: /* reads into working/argument memory */
        switch (sub) {
        case 0x04: case 0x14: case 0x1E: case 0x1F: case 0x20: return 0;
        case 0x10: case 0x11: case 0x18: case 0x1A: case 0x1B:
        case 0x21: case 0x25: case 0x27: case 0x28: return 1;
        case 0x16: case 0x19: return 2;
        case 0x1D: /* queued item data: a non-zero 2nd byte clears it */
            return (avail >= 2 && a[1] != 0) ? -1 : 2;
        case 0x22: return 4;
        case 0x23: case 0x24: return 5;
        default: return -1;  /* 05 status, 1C item transfer, 26 respawn point */
        }

    case 0x1A: /* menus */
        switch (sub) {
        case 0x04: case 0x08: case 0x09: return 0;
        case 0x05: return 2;                     /* show a character's inventory */
        default: return -1;  /* 06 shop, 07 Escargo, 0A phone, 0B teleport */
        }

    case 0x1B: /* text memory */
        switch (sub) {
        case 0x00: case 0x01: case 0x04: case 0x05: case 0x06: return 0;
        default: return -1;
        }

    case 0x1C: /* printing */
        switch (sub) {
        case 0x04: case 0x0D: case 0x0E: case 0x0F: return 0;
        case 0x00: case 0x01: case 0x02: case 0x03: case 0x05: case 0x06:
        case 0x07: case 0x08: case 0x09: case 0x0C: case 0x11: case 0x12:
        case 0x14: case 0x15: return 1;
        case 0x0A: case 0x0B: return 4;
        default: return -1;  /* 13 PSI animation */
        }

    case 0x1D: /* item / money / party reads */
        switch (sub) {
        case 0x20: case 0x22: return 0;
        case 0x02: case 0x03: case 0x0A: case 0x0B: case 0x19: case 0x21: case 0x23: return 1;
        case 0x04: case 0x05: case 0x0C: case 0x10: case 0x11: case 0x15: return 2;
        case 0x0D: return 3;
        case 0x14: case 0x17: return 4;
        case 0x24: /* game_state.unknownC4: argument 2 clears it */
            return (avail >= 1 && a[0] == 2) ? -1 : 1;
        default: return -1;  /* give/take items, ATM, wallet, Escargo moves */
        }

    case 0x1F: /* audio, fonts, input, delays */
        switch (sub) {
        case 0x30: case 0x31: case 0x50: case 0x51: case 0x60: case 0xA2: case 0xD1: return 0;
        case 0x02: case 0x04: case 0x52: case 0x62: return 1;
        default: return -1;
        }

    default:
        return -1;  /* 04/05 flag writes, 1E stats, anything unknown */
    }
}

/* Stop with `reason` at the CC at `at`; returns -1 for op_args. */
static int halt(Scan *s, CoopLookReason reason, uint32_t at, uint8_t cc, uint8_t sub) {
    stop(s, reason, at, cc, sub);
    return -1;
}

/* Queue `count` dword targets at `t` (optional ones may be 0). */
static bool add_table(Scan *s, const uint8_t *t, size_t count, bool optional, uint32_t at) {
    for (size_t i = 0; i < count; i++) {
        uint32_t target = read_u32_le(t + 4 * i);
        if (!(optional ? add_optional(s, target, at) : add_target(s, target, at)))
            return false;
    }
    return true;
}

/* Validate the arguments of the CC at text address `at` (a = its argument
 * bytes, avail = bytes left in the block) and queue its branch targets.
 * Returns its argument length, or -1 to stop the scan. */
static int op_args(Scan *s, uint32_t at, uint8_t cc, uint8_t sub,
                   const uint8_t *a, size_t avail) {
    size_t len;
    switch ((uint16_t)(cc << 8 | sub)) {
    case 0x0600: /* JUMP_IF_FLAG_SET flag, dest */
        if (avail < 6) break;
        return add_target(s, read_u32_le(a + 2), at) ? 6 : -1;
    case 0x0800: /* CALL_TEXT dest */
    case 0x0A00: /* JUMP dest */
    case 0x1B02: /* JUMP_IF_FALSE dest */
    case 0x1B03: /* JUMP_IF_TRUE dest */
        if (avail < 4) break;
        return add_target(s, read_u32_le(a), at) ? 4 : -1;
    case 0x0900: /* JUMP_MULTI count, dest[count] */
    case 0x1FC0: /* JUMP_MULTI2: calls the selected entry; 0 entries are skipped */
        if (avail < 1 || avail < (len = 1 + 4u * a[0])) break;
        return add_table(s, a + 1, a[0], cc == 0x1F, at) ? (int)len : -1;
    case 0x1808: /* SELECTION_MENU_NO_CANCEL: the dword is a jump taken after the menu */
        if (avail < 4) break;
        return add_optional(s, read_u32_le(a), at) ? 4 : -1;
    case 0x1A00: /* PARTY_MEMBER_SELECTION_MENU: 4 per-member scripts + mode */
    case 0x1A01:
        if (avail < 17) break;
        return add_table(s, a, 4, true, at) ? 17 : -1;
    case 0x1902:
        /* LOAD_STRING_TO_MEMORY: label bytes until 02, or 01 + a hover script
         * the selection menu runs. A label stops after MENU_LABEL_SIZE - 1
         * bytes even without a terminator; the rest then runs as script. */
        for (len = 0; len < MENU_LABEL_SIZE - 1; len++) {
            if (len >= avail)
                return halt(s, COOP_LOOK_OVERRUN, at, cc, sub);
            if (a[len] == 0x02)
                return (int)len + 1;
            if (a[len] == 0x01) {
                if (avail < len + 5)
                    return halt(s, COOP_LOOK_OVERRUN, at, cc, sub);
                return add_optional(s, read_u32_le(a + len + 1), at) ? (int)len + 5 : -1;
            }
        }
        return (int)len;
    default: {
        int n = fixed_len(cc, sub, a, avail);
        if (n < 0)
            return halt(s, COOP_LOOK_CC, at, cc, sub);
        if (avail < (size_t)n) break;
        return n;
    }
    }
    return halt(s, COOP_LOOK_OVERRUN, at, cc, sub);
}

/* Decode one run from `start` to its END_BLOCK or JUMP. */
static bool scan_run(Scan *s, uint32_t start) {
    size_t n;
    const uint8_t *p = display_text_resolve(start, &n);
    if (!p)
        return stop(s, COOP_LOOK_BAD_ADDR, start, 0, 0);
    size_t off = 0;
    for (;;) {
        uint32_t at = start + (uint32_t)off;
        if (off >= n)
            return stop(s, COOP_LOOK_OVERRUN, at, 0, 0);
        uint8_t cc = p[off];
        /* Letters, and 15-17, which the runtime treats as 1-byte no-ops
         * (dictionary substitution isn't wired up; cc_skip_args) */
        if (cc >= 0x20 || (cc >= 0x15 && cc <= 0x17)) {
            off++;
            continue;
        }
        if (cc == 0x02)
            return true;
        size_t head = cc >= 0x18 ? 2 : 1; /* trees 18-1F carry a sub-opcode */
        if (off + head > n)
            return stop(s, COOP_LOOK_OVERRUN, at, cc, 0);
        uint8_t sub = head == 2 ? p[off + 1] : 0;
        int len = op_args(s, at, cc, sub, p + off + head, n - off - head);
        if (len < 0)
            return false;
        if (cc == 0x0A)
            return true;
        off += head + (size_t)len;
    }
}

bool coop_look_scan(uint32_t text_addr, CoopLookScan *out) {
    CoopLookScan local;
    Scan s;
    s.count = 0;
    s.out = out ? out : &local;
    s.out->reason = COOP_LOOK_OK;
    s.out->cc = s.out->sub = 0;
    s.out->addr = text_addr;

    bool ok = add_target(&s, text_addr, text_addr);
    for (uint16_t i = 0; ok && i < s.count; i++)
        ok = scan_run(&s, s.targets[i]);
    s.out->targets = s.count;
    return ok;
}

bool coop_look_only(uint32_t text_addr) {
    return coop_look_scan(text_addr, NULL);
}

/* ---- Self-test (--selftest-look) ---- */

/* Labels the pytest (tests/test_coop_look.py) checks; see it for what each is. */
static const struct { const char *name; uint32_t addr; } look_tests[] = {
#define T(label) { #label, label }
    T(MSG_TWSN_BUS_B),
    T(MSG_ONET_SHARK_D_JOIN_REFUSE),
    T(MSG_ONET_CHECK_HOTEL_KANBAN),
    T(MSG_ONET_HOTEL_PORTER),
    T(MSG_NEWS_HOTEL_ONETT_PAPERBOY),
    T(MSG_SHOP2_HOTEL_ONETT),
    T(MSG_GLOBAL_TELEPHONE),
    T(MSG_GLOBAL_CASHDISPENSER),
    T(MSG_ONET_DRUG_SHOP1),
    T(MSG_SYS_CONTAINER_PRESENT),
    T(MSG_ONET_LIBRARY_PATRON_SILENT),
#undef T
};

typedef struct { char name[16]; unsigned count; } ReasonCount;

/* Short name of a failure, e.g. "1F00" or "cap". */
static void reason_name(const CoopLookScan *r, char *buf, size_t size) {
    switch (r->reason) {
    case COOP_LOOK_CC:
        if (r->cc >= 0x18) snprintf(buf, size, "%02X%02X", r->cc, r->sub);
        else snprintf(buf, size, "%02X", r->cc);
        break;
    case COOP_LOOK_BAD_ADDR: snprintf(buf, size, "bad_addr"); break;
    case COOP_LOOK_OVERRUN:  snprintf(buf, size, "overrun"); break;
    case COOP_LOOK_CAP:      snprintf(buf, size, "cap"); break;
    default:                 snprintf(buf, size, "ok"); break;
    }
}

int coop_look_selftest(void) {
    map_loader_init(); /* binds the NPC config table */
    bool dump = getenv("EB_LOOK_DUMP") != NULL; /* also print one line per NPC */

    for (size_t i = 0; i < sizeof(look_tests) / sizeof(look_tests[0]); i++) {
        CoopLookScan r;
        bool ok = coop_look_scan(look_tests[i].addr, &r);
        char why[16];
        reason_name(&r, why, sizeof(why));
        printf("LOOK %s %d %s targets=%u\n", look_tests[i].name, ok ? 1 : 0, why, r.targets);
    }

    /* Per NPC type (index 0 = any other type): entries look/not/no text,
     * distinct text addresses look/not. */
    enum { TYPES = 4, MAX_REASONS = 128 };
    unsigned entry_look[TYPES] = {0}, entry_not[TYPES] = {0}, entry_none[TYPES] = {0};
    unsigned addr_look[TYPES] = {0}, addr_not[TYPES] = {0};
    ReasonCount reasons[MAX_REASONS];
    unsigned nreasons = 0;
    unsigned max_targets = 0;

    for (uint16_t id = 0; id < NPC_CONFIG_COUNT; id++) {
        uint8_t type = get_npc_config_type(id);
        unsigned t = type < TYPES ? type : 0;
        uint32_t addr = get_npc_config_text_pointer(id);
        if (addr == 0) {
            entry_none[t]++;
            continue;
        }
        CoopLookScan r;
        bool ok = coop_look_scan(addr, &r);
        if (r.targets > max_targets) max_targets = r.targets;
        (ok ? entry_look : entry_not)[t]++;
        char why[16];
        reason_name(&r, why, sizeof(why));
        if (dump)
            printf("NPC %u type=%u text=0x%06X look=%d %s targets=%u\n", id, type, addr,
                   ok ? 1 : 0, why, r.targets);

        /* First entry of this type with this address: count it as distinct */
        bool first = true;
        for (uint16_t j = 0; j < id && first; j++)
            if (get_npc_config_text_pointer(j) == addr && get_npc_config_type(j) == type)
                first = false;
        if (!first)
            continue;
        (ok ? addr_look : addr_not)[t]++;
        if (ok)
            continue;
        unsigned k = 0;
        while (k < nreasons && strcmp(reasons[k].name, why) != 0) k++;
        if (k == nreasons && nreasons < MAX_REASONS) {
            snprintf(reasons[k].name, sizeof(reasons[k].name), "%s", why);
            reasons[k].count = 0;
            nreasons++;
        }
        if (k < nreasons) reasons[k].count++;
    }

    static const char *const type_names[TYPES] = { "other", "person", "item_box", "object" };
    for (unsigned t = 0; t < TYPES; t++)
        printf("LOOK-STATS %s entries look=%u not=%u no_text=%u distinct look=%u not=%u\n",
               type_names[t], entry_look[t], entry_not[t], entry_none[t], addr_look[t], addr_not[t]);
    printf("LOOK-STATS max_targets=%u\n", max_targets);

    /* Top failure reasons over distinct (type, address) pairs */
    printf("LOOK-REASONS");
    for (unsigned shown = 0; shown < 12 && shown < nreasons; shown++) {
        unsigned best = shown;
        for (unsigned k = shown + 1; k < nreasons; k++)
            if (reasons[k].count > reasons[best].count) best = k;
        if (best != shown) {
            ReasonCount tmp = reasons[shown];
            reasons[shown] = reasons[best];
            reasons[best] = tmp;
        }
        printf(" %s=%u", reasons[shown].name, reasons[shown].count);
    }
    printf("\n");
    fflush(stdout);
    return 0;
}

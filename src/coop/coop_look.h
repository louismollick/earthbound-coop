#ifndef EB_COOP_COOP_LOOK_H
#define EB_COOP_COOP_LOOK_H

/*
 * Look-only scan (M7). Design: docs/coop-design/party-changes.md, "Look-only scan".
 *
 * A text script is Look-only when every control code reachable from its start
 * (fallthrough, jumps, calls, conditional and multi-way branches, menu hover
 * scripts) only prints, waits, prompts, drives windows and menus, or reads game
 * state into the text system's working/argument memory. One write anywhere
 * (flag, item, money, party, music, entity, teleport, battle, event, ...) and it
 * is not. The scan is static and fails closed: an opcode off the whitelist, an
 * unresolvable address, running off the end of a text block, or more than
 * COOP_LOOK_MAX_TARGETS branch targets all mean "not Look-only".
 *
 * Pure function of the address and the read-only text blobs (no static state),
 * so every netplay peer gets the same answer. Callers gate on co-op.
 */

#include "core/types.h"

/* Most distinct branch targets one scan follows. */
#define COOP_LOOK_MAX_TARGETS 512

/* Why a scan stopped. */
typedef enum {
    COOP_LOOK_OK = 0,      /* Look-only */
    COOP_LOOK_CC,          /* reached a control code off the whitelist (cc/sub) */
    COOP_LOOK_BAD_ADDR,    /* a start or branch address doesn't resolve (or is 0) */
    COOP_LOOK_OVERRUN,     /* a path ran off the end of its text block */
    COOP_LOOK_CAP,         /* more than COOP_LOOK_MAX_TARGETS targets */
} CoopLookReason;

/* Details of one scan, for the self-test and stats. */
typedef struct {
    CoopLookReason reason;
    uint8_t  cc, sub;      /* the failing control code (COOP_LOOK_CC; sub 0 if none) */
    uint32_t addr;         /* text address where the scan stopped */
    uint16_t targets;      /* branch targets visited, including the start */
} CoopLookScan;

/* Scan the text script at text_addr (an NPC config text pointer, a door's
 * map_object_text, or any other display_text address). Returns true if it is
 * Look-only. out may be NULL. */
bool coop_look_scan(uint32_t text_addr, CoopLookScan *out);

/* True if the text script at text_addr is Look-only. */
bool coop_look_only(uint32_t text_addr);

/* --selftest-look: print `LOOK <LABEL> <0|1>` for each test label, then
 * Look-only stats over every NPC config entry's text pointer. Needs the text
 * blobs and map tables loaded (game_init). Returns the process exit code. */
int coop_look_selftest(void);

#endif /* EB_COOP_COOP_LOOK_H */

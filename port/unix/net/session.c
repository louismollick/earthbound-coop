/*
 * Online co-op Session: the wire protocol, the Host relay, the client, joins,
 * disconnects and desync detection. Overview in net.h and docs/coop-online.md.
 *
 * Machines and Players. A machine has one or more local Players (--local-players
 * N): the Host is P1..PN, and a client asks for N slots and gets the next free
 * Players. Its local pads go to them in order (net_frame's sample_local).
 *
 * Frames. Net frame f is the f-th call of net_frame() since the Host started (the
 * Host's local counter; a joiner starts at the frame it joins on). Each confirmed
 * frame carries all four pads and at most one session event, for a mask of Players
 * (one machine's):
 *
 *   EV_CAPTURE    every machine requests a root call (host_request_root_call): the
 *                 same torn-safe unwind a savestate uses. At the root boundary the
 *                 Host serializes the game + SRAM for the joining machine. The Host
 *                 confirms nothing past this frame until the join resolves, so
 *                 everyone waits at the next frame (J) while the joiner loads.
 *   EV_JOIN       coop_join(p) for each Player on every machine; their pads are 0
 *                 for frames J..J+D-1 and their own input from J+D on. The joiner
 *                 resumes at J.
 *   EV_LEAVE      coop_leave(p) for each Player on every machine. The Host stopped
 *                 waiting for their input when it dropped the machine (pads are 0
 *                 from then on).
 *   EV_END        tests (--net-end-frame): every machine quits after this frame.
 *
 * Redundancy. A client's INPUT carries every local pad the Host hasn't confirmed
 * yet (the last D+1 or so); the Host's FRAMES carries every confirmed set from the
 * client's ack on (up to 32). A lost packet is covered by the next one, and both
 * sides resend every 10 ms while waiting.
 *
 * Desyncs. Every 60 frames each machine walks the serialized state (state_dump_visit)
 * at the start of net_frame, keeps a raw copy, and hashes each section (FNV-1a).
 * Clients send their hashes to the Host in every INPUT; the Host compares them with
 * its own and, on a mismatch, stops the Session: every machine writes
 * desync-<frame>-P<n>.state/.txt and exits with status 3.
 *
 * Connections. A client picks a random nonce for each process; it is the
 * connection's epoch and travels in the header of every datagram, both ways. Each
 * side ignores datagrams with another epoch, so a delayed packet of an earlier
 * connection from the same endpoint (a restarted client behind the same NAT
 * mapping) can't touch the current one. A HELLO never replaces an open connection:
 * a restarted client at the same endpoint is told to wait (REJECT busy) until the
 * old connection is gone, by its BYE or by 10 s of silence.
 *
 * Compatibility. HELLO carries this build's fingerprint (savestate layout,
 * viewport, simulation build options, game revision, a hash of the game data, the
 * Locale); the Host turns away any difference and names it.
 *
 * Wire format: little-endian; every datagram starts 'E' 'N' version type, then the
 * u32 connection nonce.
 */
#include "net/net.h"
#include "net/transport.h"

#include <SDL.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "coop/coop.h"
#include "core/locale.h"
#include "core/math.h"
#include "core/state_dump.h"
#include "embedded_assets.h"
#include "game/audio.h"
#include "game/battle.h"
#include "game_main.h"
#include "net_build_id.h"

/* sdl2_savestate.c: memory-backed slots */
void savestate_mem_enable(bool on);
void savestate_mem_clear(void);
const unsigned char *savestate_mem_data(int slot, size_t *len);
bool savestate_mem_put(int slot, const void *data, size_t len);
/* sdl2_save.c */
void platform_save_set_path(const char *path);

#define PROTO_VERSION     3
#define RING              512u    /* frames of pad / confirmed-set history (power of 2) */
#define MAX_DELAY         60
#define HASH_INTERVAL     hash_interval
#define TIMEOUT_MS        10000u  /* silence before a Player is dropped / the Host is given up on */
#define CONNECT_MS        (TIMEOUT_MS + 5000u) /* a restarted client may wait out its old connection */
#define JOIN_TIMEOUT_MS   30000u  /* capture-to-loaded budget for one join */
#define RESEND_MS         10u
#define KEEPALIVE_MS      100u
#define HELLO_MS          250u
#define CHUNK_BYTES       1024u
#define CHUNK_RESEND_MS   150u
#define MAX_CHUNKS        1024u
#define CHUNKS_PER_TICK   32
#define MAX_SEND_FRAMES   32u
#define MAX_SEND_INPUTS   64u
#define MAX_SECTIONS      64
#define JOIN_RETRY_FRAMES 120u
#define SNAPSHOTS         4
#define PKT_MAX           1400
#define SRAM_MAX          65536
#define BLOB_MAGIC        0x4A4E4245u  /* "EBNJ" */
#define AUTO_DELAY_MAX    20      /* auto input delay cap (frames): a 320 ms round trip */
#define RTT_WAIT_MS       2000u   /* auto delay: how long a join waits for its first ping */

/* Frames between hash points: 60, or EB_NET_HASH_INTERVAL (debugging; every
 * machine must use the same value). */
static uint32_t hash_interval = 60;

/* Payloads, after the header (whose nonce is the client's connection epoch) */
enum {
    MSG_HELLO = 1,  /* C->H  fingerprint, u8 local Players, ping echo */
    MSG_WELCOME,    /* H->C  u8 n, n x u8 Player, u8 input delay, u16 stamp */
    MSG_REJECT,     /* H->C  u8 reason (STOP_*); STOP_BUILD: the Host's fingerprint */
    MSG_INPUT,      /* C->H  u8 first Player, ping echo, u32 ack, u32 first, u8 n, u8 k, n x k x u16 pad, report */
    MSG_FRAMES,     /* H->C  u16 stamp, u16 round trip, u8 input delay, u32 first, u8 n,
                     *       n x (4 x u16 pad, u8 event, u8 Player mask) */
    MSG_CHUNK,      /* H->C  u32 total, u16 index, u16 count, u16 len, bytes */
    MSG_CHUNK_ACK,  /* C->H  u16 count, ceil(count/8) bitmap bytes */
    MSG_STOP,       /* H->C  u8 reason, u32 frame, u8 Player, u8 n, n x u8 section index */
    MSG_BYE,        /* both  leaving */
};
/* report = u8 present, then u32 frame, u8 n, n x u32 section hash
 * fingerprint = u32 layout, u16 width, u16 height, u32 options, u32 assets, u8 locale, u8 n, n x revision char
 * Pings. The Host stamps WELCOME and FRAMES with its clock (u16 ms, never 0); a
 * client echoes the latest stamp it got (ping echo = u16 stamp, u16 ms it held it;
 * 0 0 before the first), so the Host measures every round trip and sends each
 * client its own in FRAMES. */

/* STOP_BUSY (REJECT only): this endpoint still has an open connection; retry.
 * STOP_LOCALE (REJECT only, + u8 the Host's Locale): the client plays in another Language */
enum { STOP_DESYNC = 1, STOP_KICKED, STOP_FULL, STOP_BUILD, STOP_BUSY, STOP_LOCALE };
enum { EV_NONE = 0, EV_CAPTURE, EV_JOIN, EV_LEAVE, EV_END };

typedef struct {
    uint16_t pad[PLATFORM_MAX_PLAYERS];
    uint8_t ev, ev_mask;   /* session event and the Players (bit p = Player p) it is for */
} FrameSet;

typedef struct {
    uint32_t frame;
    uint8_t count;
    uint32_t hash[MAX_SECTIONS];
} HashReport;

/* ---- Packets ---- */

typedef struct {
    uint8_t b[PKT_MAX];
    size_t n;
} Pkt;

static void put8(Pkt *p, uint32_t v) {
    if (p->n < PKT_MAX)
        p->b[p->n++] = (uint8_t)v;
}
static void put16(Pkt *p, uint32_t v) {
    put8(p, v);
    put8(p, v >> 8);
}
static void put32(Pkt *p, uint32_t v) {
    put16(p, v);
    put16(p, v >> 16);
}
static void putn(Pkt *p, const void *d, size_t len) {
    if (p->n + len <= PKT_MAX) {
        memcpy(p->b + p->n, d, len);
        p->n += len;
    }
}
/* `nonce`: the epoch of the connection the datagram belongs to */
static void pkt_begin(Pkt *p, int type, uint32_t nonce) {
    p->n = 0;
    put8(p, 'E');
    put8(p, 'N');
    put8(p, PROTO_VERSION);
    put8(p, (uint32_t)type);
    put32(p, nonce);
}
#define HEADER_BYTES 8

typedef struct {
    const uint8_t *b;
    size_t n, pos;
    bool ok;
} Rd;

static uint32_t get8(Rd *r) {
    if (r->pos >= r->n) {
        r->ok = false;
        return 0;
    }
    return r->b[r->pos++];
}
static uint32_t get16(Rd *r) {
    uint32_t lo = get8(r);
    return lo | get8(r) << 8;
}
static uint32_t get32(Rd *r) {
    uint32_t lo = get16(r);
    return lo | get16(r) << 16;
}

static void put_report(Pkt *p, const HashReport *rep, bool have) {
    put8(p, have);
    if (!have)
        return;
    put32(p, rep->frame);
    put8(p, rep->count);
    for (int i = 0; i < rep->count; i++)
        put32(p, rep->hash[i]);
}

static bool get_report(Rd *r, HashReport *rep) {
    if (!get8(r))
        return false;
    rep->frame = get32(r);
    rep->count = (uint8_t)get8(r);
    if (rep->count > MAX_SECTIONS)
        rep->count = MAX_SECTIONS;
    for (int i = 0; i < rep->count; i++)
        rep->hash[i] = get32(r);
    return r->ok;
}

/* ---- Compatibility fingerprint ---- */

/* Everything that must match for two builds to run the same simulation. Nothing
 * compiler- or OS-specific goes in, so one commit built on macOS and on Windows
 * agrees. */
typedef struct {
    uint32_t layout;      /* savestate layout id (state_layout.h) */
    uint16_t width, height; /* EB_VIEWPORT_WIDTH x HEIGHT: changes the PPU state, which is hashed */
    uint32_t options;     /* FP_OPT_*: compile-time options that change the game state */
    uint32_t assets;      /* FNV-1a over the Locale's embedded assets (size + bytes), in registry order */
    uint8_t locale;       /* Locale: a Session runs in one Language */
    char revision[64];    /* NET_GAME_REVISION: git commit, "+dirty.<hash>" with local changes */
} Fingerprint;

/* The smooth camera, frame skip and the PPU render options are presentation only:
 * they never touch the serialized state. */
enum { FP_OPT_AUDIO = 1, FP_OPT_VERIFY = 2, FP_OPT_LETTERBOX = 4, FP_OPT_B_MENU = 8 };

static Fingerprint my_fp;

/* English skips the Japanese assets (JA/), so a build without them hashes the same. */
static uint32_t asset_hash(void) {
    uint32_t h = 2166136261u;
    for (int i = 0; i < ASSET_COUNT; i++) {
#ifdef EB_HAVE_JA
        if (asset_is_ja[i] && !locale_is_ja())
            continue;
#endif
        const AssetEntry *e = &embedded_assets[i];
        uint32_t size = e->size_ptr ? *e->size_ptr : 0;
        for (int k = 0; k < 4; k++)
            h = (h ^ ((size >> (8 * k)) & 0xFF)) * 16777619u;
        for (uint32_t b = 0; e->data && b < size; b++)
            h = (h ^ e->data[b]) * 16777619u;
    }
    return h;
}

static void fingerprint_init(void) {
    my_fp.layout = state_dump_layout_id();
    my_fp.width = EB_VIEWPORT_WIDTH;
    my_fp.height = EB_VIEWPORT_HEIGHT;
    my_fp.options = 0;
#ifdef EB_ENABLE_AUDIO
    my_fp.options |= FP_OPT_AUDIO;
#endif
#ifdef EB_ENABLE_VERIFY
    my_fp.options |= FP_OPT_VERIFY;
#endif
#if EB_BATTLE_LETTERBOX
    my_fp.options |= FP_OPT_LETTERBOX;
#endif
#ifdef EB_B_OPENS_MAIN_MENU
    my_fp.options |= FP_OPT_B_MENU;
#endif
    my_fp.assets = asset_hash();
    my_fp.locale = (uint8_t)locale_get();
    snprintf(my_fp.revision, sizeof my_fp.revision, "%s", NET_GAME_REVISION);
}

static void put_fp(Pkt *p, const Fingerprint *f) {
    put32(p, f->layout);
    put16(p, f->width);
    put16(p, f->height);
    put32(p, f->options);
    put32(p, f->assets);
    put8(p, f->locale);
    size_t len = strlen(f->revision);
    put8(p, (uint32_t)len);
    putn(p, f->revision, len);
}

static void get_fp(Rd *r, Fingerprint *f) {
    memset(f, 0, sizeof *f);
    f->layout = get32(r);
    f->width = (uint16_t)get16(r);
    f->height = (uint16_t)get16(r);
    f->options = get32(r);
    f->assets = get32(r);
    f->locale = (uint8_t)get8(r);
    uint32_t len = get8(r);
    for (uint32_t i = 0; i < len; i++) {
        uint32_t c = get8(r);
        if (i < sizeof f->revision - 1)
            f->revision[i] = c >= 0x20 && c < 0x7F ? (char)c : '?';
    }
}

static const char *options_str(uint32_t o, char *buf, size_t cap) {
    snprintf(buf, cap, "%s%s%s%s", o & FP_OPT_AUDIO ? "+audio" : "-audio", o & FP_OPT_VERIFY ? " +verify" : "",
             o & FP_OPT_LETTERBOX ? " +letterbox" : " -letterbox", o & FP_OPT_B_MENU ? " +b-opens-menu" : "");
    return buf;
}

/* "" if the Host's and the client's fingerprints match, else what differs:
 * "viewport: Host 320x240, <them> 256x224; ..." (`them`: "client" or "this machine"). */
static const char *fp_diff(const Fingerprint *host, const Fingerprint *client, const char *them) {
    static char s[512];
    char a[64], b[64];
    s[0] = '\0';
#define FP_ADD(...) snprintf(s + strlen(s), sizeof s - strlen(s), __VA_ARGS__)
    if (host->width != client->width || host->height != client->height)
        FP_ADD("%sviewport: Host %ux%u, %s %ux%u", *s ? "; " : "", (unsigned)host->width, (unsigned)host->height,
               them, (unsigned)client->width, (unsigned)client->height);
    if (strcmp(host->revision, client->revision) != 0)
        FP_ADD("%sgame revision: Host %s, %s %s", *s ? "; " : "", *host->revision ? host->revision : "?", them,
               *client->revision ? client->revision : "?");
    if (host->options != client->options)
        FP_ADD("%sbuild options: Host %s, %s %s", *s ? "; " : "", options_str(host->options, a, sizeof a), them,
               options_str(client->options, b, sizeof b));
    if (host->assets != client->assets)
        FP_ADD("%sgame data: Host %08x, %s %08x (different ROM or edited assets)", *s ? "; " : "",
               (unsigned)host->assets, them, (unsigned)client->assets);
    if (host->layout != client->layout)
        FP_ADD("%ssavestate layout: Host %08x, %s %08x", *s ? "; " : "", (unsigned)host->layout, them,
               (unsigned)client->layout);
#undef FP_ADD
    return s;
}

/* ---- State ---- */

/* One remote machine (Host side). */
enum { P_FREE, P_JOINING, P_IN, P_LEAVING };
typedef struct {
    int state;
    uint8_t nplayers;
    uint8_t player[PLATFORM_MAX_PLAYERS]; /* its Players, in local pad order */
    NetAddr addr;
    uint32_t nonce;        /* its connection epoch */
    uint32_t busy_nonce;   /* last HELLO told to wait for this connection to go (logged once) */
    uint64_t last_recv, last_send;
    uint32_t ack;          /* the client holds the confirmed sets of frames < ack */
    uint32_t sent_end;     /* set_end when FRAMES were last sent to it (relay: the end of what was sent) */
    uint32_t first_frame;  /* its pads are 0 before this frame */
    uint32_t retry_at;     /* joining: capture no earlier than this frame */
    uint16_t in[RING][PLATFORM_MAX_PLAYERS];
    uint32_t in_tag[RING]; /* frame + 1 of in[] (0 = empty) */
    HashReport report;
    bool has_report;
    uint32_t checked;      /* report frame already compared */
    uint64_t hello_ms;     /* its first HELLO */
    uint16_t rtt;          /* round trip in ms (smoothed); valid once rtt_known */
    bool rtt_known;
} Peer;

enum { J_NONE, J_CAPTURING, J_TRANSFER, J_READY };
enum { C_WAIT_STATE, C_LOADING, C_IN };

static struct {
    bool active, host, shutting, ended, stopped;
    bool host_left;               /* client: the Host said goodbye (finish the frames held, then stop) */
    int delay;
    bool auto_delay;              /* Host: the delay follows the slowest round trip (no --input-delay) */
    char invite[160];             /* a relay Session's invite ("" otherwise) */
    char err[512];                /* why net_start failed */
    int me;                       /* this machine's first Player (0 = P1) */
    int nlocal;                   /* its local Players */
    uint8_t mine[PLATFORM_MAX_PLAYERS]; /* which Players they are, in local pad order */
    uint32_t frame;               /* next net frame to run */
    uint32_t end_frame;           /* Host: EV_END on this frame (0 = never) */
    bool end_emitted;
    int wait_players;             /* Host: hold the game while fewer Players are in (0 = don't) */
    FrameSet set[RING];
    uint32_t set_tag[RING];       /* client: frame + 1 held in set[] */
    uint32_t set_end;             /* confirmed sets are known for frames < set_end */
    uint16_t local[RING][PLATFORM_MAX_PLAYERS];
    uint32_t local_start;         /* first frame this machine contributes a pad to */
    uint32_t local_end;           /* local pads are recorded for frames < local_end */
    uint32_t test_desync_frame;   /* EB_NET_TEST_DESYNC: perturb the RNG on this frame */
    uint32_t shot_frame[8];       /* EB_NET_SHOT_FRAMES: screenshot at these frames (tests) */

    /* client */
    NetAddr host_addr;
    uint16_t host_stamp;          /* the Host's latest ping stamp, received at host_stamp_ms */
    uint64_t host_stamp_ms;
    uint16_t my_rtt;              /* this machine's round trip, as the Host measured it */
    uint32_t nonce;
    int cstate;
    uint64_t last_host_recv;
    unsigned char *blob;
    uint32_t blob_len;
    uint16_t blob_chunks, blob_have;
    uint8_t chunk_have[MAX_CHUNKS];
    char save_path[512];
    HashReport my_report;
    bool have_report;

    /* host */
    Peer peer[PLATFORM_MAX_PLAYERS];
    bool hold;                    /* confirm nothing past hold_frame (a join in flight) */
    uint32_t hold_frame;
} n;

static struct {
    int phase, peer;              /* the joining machine (n.peer index), -1 = none / gone */
    uint32_t nonce;
    unsigned char *blob;
    uint32_t len;
    uint16_t chunks, acked_count;
    uint8_t acked[MAX_CHUNKS];
    uint64_t sent_ms[MAX_CHUNKS];
    uint64_t started;
} join = { .peer = -1 };

static uint64_t now_ms(void) {
    uint64_t tps = platform_timer_ticks_per_sec();
    return platform_timer_ticks() / (tps >= 1000 ? tps / 1000 : 1);
}

static void say(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
/* Status lines go to stdout (the test harness reads them), prefixed "NET". */
static void say(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    printf("NET ");
    vprintf(fmt, ap);
    printf("\n");
    fflush(stdout);
    va_end(ap);
}

static void send_pkt(const NetAddr *to, const Pkt *p) {
    tp_send(to, p->b, p->n);
}

/* `nonce`: the epoch of the connection that ends */
static void send_bye(const NetAddr *to, uint32_t nonce) {
    Pkt p;
    pkt_begin(&p, MSG_BYE, nonce);
    send_pkt(to, &p);
}

/* Stop this machine's part of the Session: print why and exit with `code`. */
static void fatal(int code, const char *fmt, ...) __attribute__((format(printf, 2, 3), noreturn));
static void fatal(int code, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    char msg[512];
    vsnprintf(msg, sizeof msg, fmt, ap);
    va_end(ap);
    fprintf(stderr, "netplay: %s\n", msg);
    say("STOP code=%d %s", code, msg);
    n.stopped = true; /* net_shutdown: no lingering */
    if (!platform_headless) /* a game started from the desktop has no console to read */
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "Online co-op", msg, NULL);
    exit(code);
}

/* net_start: record why it failed (the launcher shows it) and print it. */
static bool fail(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static bool fail(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(n.err, sizeof n.err, fmt, ap);
    va_end(ap);
    fprintf(stderr, "netplay: %s\n", n.err);
    tp_close();
    return false;
}

/* ---- Pings ---- */

/* The Host's ping stamp: its clock in ms, never 0 (0 = no stamp yet). */
static uint16_t ping_stamp(void) {
    uint16_t s = (uint16_t)now_ms();
    return s ? s : 1;
}

/* Client: echo the Host's latest stamp and how long it was held here. */
static void put_echo(Pkt *p) {
    uint64_t held = n.host_stamp ? now_ms() - n.host_stamp_ms : 0;
    put16(p, n.host_stamp);
    put16(p, held > 0xFFFF ? 0xFFFF : (uint32_t)held);
}

/* Host: one round-trip sample from a client's echo. */
static void take_echo(Peer *pe, Rd *r) {
    uint16_t echo = (uint16_t)get16(r), held = (uint16_t)get16(r);
    if (!r->ok || !echo)
        return;
    uint16_t rtt = (uint16_t)((uint16_t)now_ms() - echo - held);
    if (rtt > 5000)
        return; /* a stale echo across a clock wrap */
    pe->rtt = pe->rtt_known ? (uint16_t)((pe->rtt * 3u + rtt) / 4u) : rtt;
    pe->rtt_known = true;
}

/* ---- State hashes and snapshots ---- */

static int sec_count;
static uint16_t sec_id[MAX_SECTIONS];
static const char *sec_name[MAX_SECTIONS];

typedef struct {
    bool valid;
    uint32_t frame;
    unsigned char *data;
    size_t len, cap;
    size_t off[MAX_SECTIONS], size[MAX_SECTIONS];
    HashReport rep;
} Snapshot;
static Snapshot snaps[SNAPSHOTS];

typedef struct {
    Snapshot *s;
    int idx;
    bool excluded;
    uint32_t h;
} VisitCtx;

/* Sections that legitimately differ between machines: the music bookkeeping only
 * changes when audio is enabled (headless or not), and game logic never reads it. */
static bool section_excluded(const char *name) {
    return strcmp(name, "AUDIO") == 0;
}

static void visit_finish(VisitCtx *v) {
    if (v->idx >= 0 && v->idx < MAX_SECTIONS)
        v->s->rep.hash[v->idx] = v->excluded ? 0 : v->h;
}

static void visit_begin(void *ctx, uint16_t id, const char *name, uint32_t size) {
    VisitCtx *v = ctx;
    visit_finish(v);
    v->idx++;
    if (v->idx >= MAX_SECTIONS)
        return;
    sec_id[v->idx] = id;
    sec_name[v->idx] = name;
    v->s->off[v->idx] = v->s->len;
    v->s->size[v->idx] = size;
    v->excluded = section_excluded(name);
    v->h = 2166136261u;
}

static void visit_bytes(void *ctx, const void *data, size_t len) {
    VisitCtx *v = ctx;
    Snapshot *s = v->s;
    if (v->idx >= MAX_SECTIONS)
        return;
    if (s->len + len > s->cap) {
        size_t cap = (s->len + len) * 2;
        unsigned char *d = realloc(s->data, cap);
        if (!d)
            fatal(1, "out of memory");
        s->data = d;
        s->cap = cap;
    }
    memcpy(s->data + s->len, data, len);
    s->len += len;
    const uint8_t *p = data;
    uint32_t h = v->h;
    for (size_t i = 0; i < len; i++)
        h = (h ^ p[i]) * 16777619u;
    v->h = h;
}

static Snapshot *find_snapshot(uint32_t frame) {
    Snapshot *s = &snaps[(frame / HASH_INTERVAL) % SNAPSHOTS];
    return s->valid && s->frame == frame ? s : NULL;
}

static uint32_t combined_hash(const HashReport *r) {
    uint32_t h = 2166136261u;
    for (int i = 0; i < r->count; i++)
        for (int k = 0; k < 4; k++)
            h = (h ^ ((r->hash[i] >> (8 * k)) & 0xFF)) * 16777619u;
    return h;
}

static void host_check(int p);


/* Hash point at the start of net frame `frame` (identical on every machine). */
static void hash_point(uint32_t frame) {
    Snapshot *s = &snaps[(frame / HASH_INTERVAL) % SNAPSHOTS];
    s->valid = false;
    s->len = 0;
    VisitCtx v = { s, -1, false, 0 };
    StateDumpVisitor vis = { visit_begin, visit_bytes, &v };
    state_dump_visit(&vis);
    visit_finish(&v);
    sec_count = v.idx + 1 < MAX_SECTIONS ? v.idx + 1 : MAX_SECTIONS;
    s->rep.frame = frame;
    s->rep.count = (uint8_t)sec_count;
    s->frame = frame;
    s->valid = true;
    printf("NETSYNC f=%u hash=%08x ", (unsigned)frame, (unsigned)combined_hash(&s->rep));
    input_script_print_players();
    fflush(stdout);
    if (n.host) {
        for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++)
            host_check(p);
    } else {
        n.my_report = s->rep;
        n.have_report = true;
    }
}

/* desync-<frame>-P<n>.state (raw sections: "EBND", u32 frame, u32 count, then per
 * section u16 id, u8 name length, name, u32 size, bytes) and .txt (one line per
 * section: name size hash, "DIFFERS" where the Host saw a mismatch). */
static void write_dump(uint32_t frame, const bool *differs) {
    Snapshot *s = find_snapshot(frame);
    if (!s) {
        fprintf(stderr, "netplay: no snapshot of frame %u left to dump\n", (unsigned)frame);
        return;
    }
    char path[64];
    snprintf(path, sizeof path, "desync-%u-P%d.state", (unsigned)frame, n.me + 1);
    FILE *f = fopen(path, "wb");
    if (f) {
        uint32_t hdr[3] = { 0x444E4245u /* "EBND" */, frame, (uint32_t)s->rep.count };
        fwrite(hdr, sizeof hdr, 1, f);
        for (int i = 0; i < s->rep.count; i++) {
            uint8_t nl = (uint8_t)strlen(sec_name[i]);
            uint32_t size = (uint32_t)s->size[i];
            fwrite(&sec_id[i], 2, 1, f);
            fwrite(&nl, 1, 1, f);
            fwrite(sec_name[i], 1, nl, f);
            fwrite(&size, 4, 1, f);
            fwrite(s->data + s->off[i], 1, size, f);
        }
        fclose(f);
    }
    snprintf(path, sizeof path, "desync-%u-P%d.txt", (unsigned)frame, n.me + 1);
    f = fopen(path, "w");
    if (f) {
        fprintf(f, "frame %u P%d combined %08x\n", (unsigned)frame, n.me + 1, (unsigned)combined_hash(&s->rep));
        for (int i = 0; i < s->rep.count; i++)
            fprintf(f, "%-24s %8u %08x%s\n", sec_name[i], (unsigned)s->size[i], (unsigned)s->rep.hash[i],
                    differs && differs[i] ? " DIFFERS" : "");
        fclose(f);
    }
    say("DUMP desync-%u-P%d.state", (unsigned)frame, n.me + 1);
}

/* "RNG, OVERWORLD" for the sections marked in `differs`. */
static const char *differs_list(const bool *differs, int count) {
    static char s[512];
    s[0] = '\0';
    for (int i = 0; i < count && i < sec_count; i++) {
        if (!differs[i])
            continue;
        size_t len = strlen(s);
        snprintf(s + len, sizeof s - len, "%s%s", len ? ", " : "", sec_name[i]);
    }
    return s;
}

/* ---- Host ---- */

/* Remote machines live in n.peer[1..MAX_PEERS] (slot 0 is unused). */
#define MAX_PEERS (PLATFORM_MAX_PLAYERS - 1)

static bool peer_active(int s) {
    return n.peer[s].state == P_JOINING || n.peer[s].state == P_IN;
}

/* The 1-based number of machine s's first Player, for messages. */
static int peer_pnum(int s) {
    return n.peer[s].player[0] + 1;
}

static uint8_t peer_mask(int s) {
    uint8_t m = 0;
    for (int k = 0; k < n.peer[s].nplayers; k++)
        m |= (uint8_t)(1u << n.peer[s].player[k]);
    return m;
}

/* The machine whose connection holds endpoint `a` (joining, in or leaving), or -1. */
static int peer_by_addr(const NetAddr *a) {
    for (int s = 1; s <= MAX_PEERS; s++)
        if (n.peer[s].state != P_FREE && udp_addr_equal(&n.peer[s].addr, a))
            return s;
    return -1;
}

/* Players nobody holds: not the Host's and not any machine's (a leaving machine
 * keeps its Players until its EV_LEAVE). */
static uint8_t free_players(void) {
    uint8_t m = 0;
    for (int p = n.nlocal; p < PLATFORM_MAX_PLAYERS; p++)
        m |= (uint8_t)(1u << p);
    for (int s = 1; s <= MAX_PEERS; s++)
        if (n.peer[s].state != P_FREE)
            m &= (uint8_t)~peer_mask(s);
    return m;
}

static void join_reset(void) {
    free(join.blob);
    join.blob = NULL;
    join.phase = J_NONE;
    join.peer = -1;
    n.hold = false;
}

/* Stop waiting for machine s. In the Session, its Players leave (EV_LEAVE) on the
 * next frame the Host confirms; their pads are 0 from now on. */
static void host_drop(int s, const char *why) {
    Peer *pe = &n.peer[s];
    if (pe->state == P_IN) {
        pe->state = P_LEAVING;
        say("DROP P%d %s", peer_pnum(s), why);
        fprintf(stderr, "netplay: P%d %s; they leave the game\n", peer_pnum(s), why);
    } else if (pe->state == P_JOINING) {
        say("DROP P%d %s (while joining)", peer_pnum(s), why);
        if (join.peer == s) {
            if (join.phase == J_CAPTURING)
                join.peer = -1; /* the capture callback releases the hold */
            else
                join_reset();
        }
        pe->state = P_FREE;
    }
}

/* Auto input delay: enough frames to cover the slowest round trip (the machines in
 * the Session, plus `joiner`), plus one, and never under the LAN default. The Host
 * changes it only where no join is in flight (a joiner starts sending at J + the
 * delay its state carries): when a capture starts and when a machine leaves. The
 * others take it from FRAMES; net_frame's sampling copes with any change. */
static void host_auto_delay(int joiner) {
    if (!n.auto_delay)
        return;
    uint32_t worst = 0;
    for (int s = 1; s <= MAX_PEERS; s++)
        if ((n.peer[s].state == P_IN || s == joiner) && n.peer[s].rtt_known && n.peer[s].rtt > worst)
            worst = n.peer[s].rtt;
    int d = (int)((worst * 60u + 999u) / 1000u) + 1;
    if (d < NET_DEFAULT_INPUT_DELAY)
        d = NET_DEFAULT_INPUT_DELAY;
    if (d > AUTO_DELAY_MAX)
        d = AUTO_DELAY_MAX;
    if (d != n.delay) {
        say("DELAY %d (slowest round trip %u ms)", d, (unsigned)worst);
        n.delay = d;
    }
}

/* Whether machine s may be captured for its join now. With the auto delay the
 * Host first waits for its round trip (it decides the delay), or RTT_WAIT_MS. */
static bool join_ripe(int s, uint32_t g) {
    const Peer *pe = &n.peer[s];
    if (pe->state != P_JOINING || pe->retry_at > g)
        return false;
    return !n.auto_delay || pe->rtt_known || now_ms() - pe->hello_ms >= RTT_WAIT_MS;
}

/* The session event for frame g, if any (Host). */
static void host_pick_event(uint32_t g, FrameSet *fs) {
    if (n.end_frame && g >= n.end_frame) {
        fs->ev = EV_END;
        n.end_emitted = true;
        return;
    }
    if (join.phase == J_READY && join.peer > 0) {
        Peer *pe = &n.peer[join.peer];
        fs->ev = EV_JOIN;
        fs->ev_mask = peer_mask(join.peer);
        pe->state = P_IN;
        pe->first_frame = g + (uint32_t)n.delay;
        pe->sent_end = g;
        pe->ack = g;
        join_reset();
        return;
    }
    for (int s = 1; s <= MAX_PEERS; s++) {
        if (n.peer[s].state == P_LEAVING) {
            fs->ev = EV_LEAVE;
            fs->ev_mask = peer_mask(s);
            n.peer[s].state = P_FREE;
            if (join.phase == J_NONE)
                host_auto_delay(-1);
            return;
        }
    }
    if (join.phase != J_NONE)
        return;
    for (int s = 1; s <= MAX_PEERS; s++) {
        if (join_ripe(s, g)) {
            host_auto_delay(s);
            fs->ev = EV_CAPTURE;
            fs->ev_mask = peer_mask(s);
            join.phase = J_CAPTURING;
            join.peer = s;
            join.nonce = n.peer[s].nonce;
            join.started = now_ms();
            n.hold = true;
            n.hold_frame = g;
            return;
        }
    }
}

/* --net-wait-players (tests): while fewer Players are in, only frames that move a
 * join or a leave along (EV_CAPTURE / EV_JOIN / EV_LEAVE) are confirmed, so the
 * game waits on that frame. It holds again after a leave, until the rejoin. */
static bool host_waiting_ok(uint32_t g) {
    int in = n.nlocal;
    for (int s = 1; s <= MAX_PEERS; s++) {
        if (n.peer[s].state == P_IN)
            in += n.peer[s].nplayers;
        if (n.peer[s].state == P_LEAVING)
            return true;
    }
    if (in >= n.wait_players)
        return true;
    if (join.phase == J_READY)
        return true;
    if (join.phase != J_NONE)
        return false;
    for (int s = 1; s <= MAX_PEERS; s++)
        if (join_ripe(s, g))
            return true;
    return false;
}

/* Confirm every frame whose pads are all here. */
static void host_confirm(void) {
    while (!n.end_emitted) {
        uint32_t g = n.set_end;
        if (g >= n.local_end || g >= n.frame + RING / 2)
            break;
        if (n.hold && g > n.hold_frame)
            break;
        if (n.wait_players && !host_waiting_ok(g))
            break;
        FrameSet fs;
        memset(&fs, 0, sizeof fs);
        for (int k = 0; k < n.nlocal; k++)
            fs.pad[k] = n.local[g % RING][k];
        bool ready = true;
        for (int s = 1; s <= MAX_PEERS && ready; s++) {
            Peer *pe = &n.peer[s];
            if (pe->state != P_IN || g < pe->first_frame)
                continue;
            if (pe->in_tag[g % RING] != g + 1) {
                ready = false;
                break;
            }
            for (int k = 0; k < pe->nplayers; k++)
                fs.pad[pe->player[k]] = pe->in[g % RING][k];
        }
        if (!ready)
            break;
        host_pick_event(g, &fs);
        n.set[g % RING] = fs;
        n.set_end = g + 1;
    }
}

/* FRAMES to machine s. Over UDP: every set from its ack on (a lost packet is covered
 * by the next). Over the relay, which loses nothing: each set once, from where the
 * last FRAMES stopped (sent_end). */
static void host_send_frames(int s, uint64_t t) {
    Peer *pe = &n.peer[s];
    if (pe->ack + RING <= n.set_end) {
        host_drop(s, "fell too far behind");
        return;
    }
    uint32_t from = tp_reliable() ? pe->sent_end : pe->ack;
    uint32_t first = from < n.set_end ? from : n.set_end;
    uint32_t cnt = n.set_end - first;
    if (cnt > MAX_SEND_FRAMES)
        cnt = MAX_SEND_FRAMES;
    Pkt pk;
    pkt_begin(&pk, MSG_FRAMES, pe->nonce);
    put16(&pk, ping_stamp());
    put16(&pk, pe->rtt_known ? pe->rtt : 0);
    put8(&pk, (uint32_t)n.delay);
    put32(&pk, first);
    put8(&pk, cnt);
    for (uint32_t g = first; g < first + cnt; g++) {
        const FrameSet *fs = &n.set[g % RING];
        for (int k = 0; k < PLATFORM_MAX_PLAYERS; k++)
            put16(&pk, fs->pad[k]);
        put8(&pk, fs->ev);
        put8(&pk, fs->ev_mask);
    }
    send_pkt(&pe->addr, &pk);
    pe->last_send = t;
    pe->sent_end = tp_reliable() ? first + cnt : n.set_end;
}

/* FRAMES to every machine in the Session: new frames at once, unacknowledged ones
 * every RESEND_MS (not over the relay, which loses nothing), a keepalive every
 * KEEPALIVE_MS. */
static void host_broadcast(uint64_t t) {
    for (int s = 1; s <= MAX_PEERS; s++) {
        const Peer *pe = &n.peer[s];
        if (pe->state != P_IN)
            continue;
        bool fresh = pe->sent_end < n.set_end;
        bool lagging = !tp_reliable() && pe->ack < n.set_end && t - pe->last_send >= RESEND_MS;
        if (fresh || lagging || t - pe->last_send >= KEEPALIVE_MS)
            host_send_frames(s, t);
    }
}

static void build_stop(Pkt *pk, uint32_t nonce, int reason, uint32_t frame, int player, const bool *differs) {
    pkt_begin(pk, MSG_STOP, nonce);
    put8(pk, (uint32_t)reason);
    put32(pk, frame);
    put8(pk, (uint32_t)player);
    uint8_t cnt = 0;
    uint8_t idx[MAX_SECTIONS] = { 0 };
    for (int i = 0; differs && i < sec_count; i++)
        if (differs[i])
            idx[cnt++] = (uint8_t)i;
    put8(pk, cnt);
    putn(pk, idx, cnt);
}

static void host_send_stop(int reason, uint32_t frame, int player, const bool *differs) {
    for (int rep = 0; rep < 5; rep++) {
        for (int s = 1; s <= MAX_PEERS; s++) {
            if (!peer_active(s))
                continue;
            Pkt pk;
            build_stop(&pk, n.peer[s].nonce, reason, frame, player, differs);
            send_pkt(&n.peer[s].addr, &pk);
        }
        udp_sleep(20);
    }
}

/* Compare machine s's latest hash report with the Host's snapshot of that frame. */
static void host_check(int s) {
    Peer *pe = &n.peer[s];
    if (n.shutting || pe->state != P_IN || !pe->has_report || pe->report.frame == pe->checked)
        return;
    Snapshot *sn = find_snapshot(pe->report.frame);
    if (!sn)
        return; /* not hashed here yet (the client runs up to D frames ahead) */
    pe->checked = pe->report.frame;
    bool differs[MAX_SECTIONS] = { false };
    bool any = pe->report.count != sn->rep.count;
    for (int i = 0; i < sn->rep.count && i < pe->report.count; i++)
        if (pe->report.hash[i] != sn->rep.hash[i])
            differs[i] = any = true;
    if (!any)
        return;
    uint32_t frame = sn->frame;
    const char *list = differs_list(differs, sn->rep.count);
    say("DESYNC f=%u P1 P%d sections=%s", (unsigned)frame, peer_pnum(s), list);
    write_dump(frame, differs);
    host_send_stop(STOP_DESYNC, frame, pe->player[0], differs);
    fatal(3, "desync at frame %u: P1 and P%d disagree on %s (dumps: desync-%u-P*.state/.txt)", (unsigned)frame,
          peer_pnum(s), list, (unsigned)frame);
}

static void host_send_chunks(uint64_t t) {
    if (join.phase != J_TRANSFER)
        return;
    if (t - join.started > JOIN_TIMEOUT_MS) {
        int s = join.peer;
        say("JOIN P%d timed out", peer_pnum(s));
        join_reset();
        n.peer[s].state = P_FREE;
        return;
    }
    Peer *pe = &n.peer[join.peer];
    int sent = 0;
    for (uint16_t i = 0; i < join.chunks && sent < CHUNKS_PER_TICK; i++) {
        if (join.acked[i] || (join.sent_ms[i] && (tp_reliable() || t - join.sent_ms[i] < CHUNK_RESEND_MS)))
            continue; /* acked, or sent and not due again (never, over the relay) */
        uint32_t off = (uint32_t)i * CHUNK_BYTES;
        uint32_t len = join.len - off < CHUNK_BYTES ? join.len - off : CHUNK_BYTES;
        Pkt pk;
        pkt_begin(&pk, MSG_CHUNK, join.nonce);
        put32(&pk, join.len);
        put16(&pk, i);
        put16(&pk, join.chunks);
        put16(&pk, len);
        putn(&pk, join.blob + off, len);
        send_pkt(&pe->addr, &pk);
        join.sent_ms[i] = t;
        sent++;
    }
}

static void host_send_welcome(int s, const NetAddr *to) {
    Pkt pk;
    pkt_begin(&pk, MSG_WELCOME, n.peer[s].nonce);
    put8(&pk, n.peer[s].nplayers);
    for (int k = 0; k < n.peer[s].nplayers; k++)
        put8(&pk, n.peer[s].player[k]);
    put8(&pk, (uint32_t)n.delay);
    put16(&pk, ping_stamp());
    send_pkt(to, &pk);
}

static void host_reject(const NetAddr *to, uint32_t nonce, int reason) {
    Pkt pk;
    pkt_begin(&pk, MSG_REJECT, nonce);
    put8(&pk, (uint32_t)reason);
    if (reason == STOP_BUILD)
        put_fp(&pk, &my_fp);
    if (reason == STOP_LOCALE)
        put8(&pk, my_fp.locale);
    send_pkt(to, &pk);
}

/* A HELLO: admit a new machine, or repeat a lost WELCOME. It never touches an
 * open connection: everything is validated first, and a new process at the same
 * endpoint waits (STOP_BUSY) until the old connection's BYE or silence drop. */
static void host_hello(const NetAddr *from, uint32_t nonce, Rd *r, uint64_t t) {
    Fingerprint fp;
    get_fp(r, &fp);
    uint32_t want = get8(r);
    if (!r->ok)
        return;
    int s = peer_by_addr(from);
    if (s > 0 && n.peer[s].nonce == nonce) {
        if (peer_active(s)) { /* our WELCOME was lost (or this is the joiner's keepalive): repeat it */
            take_echo(&n.peer[s], r);
            n.peer[s].last_recv = t;
            host_send_welcome(s, from);
        }
        return;
    }
    if (fp.locale != my_fp.locale) { /* before fp_diff: the asset hashes differ too */
        say("REJECT %s plays in %s", tp_addr_str(from), locale_name((Locale)fp.locale));
        host_reject(from, nonce, STOP_LOCALE);
        return;
    }
    const char *diff = fp_diff(&my_fp, &fp, "client");
    if (*diff) {
        say("REJECT %s build differs: %s", tp_addr_str(from), diff);
        host_reject(from, nonce, STOP_BUILD);
        return;
    }
    if (s > 0) {
        if (n.peer[s].busy_nonce != nonce) {
            n.peer[s].busy_nonce = nonce;
            say("HELLO from %s waits: P%d's connection there is still open", tp_addr_str(from), peer_pnum(s));
        }
        host_reject(from, nonce, STOP_BUSY);
        return;
    }
    uint8_t avail = free_players();
    int nfree = 0;
    for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++)
        nfree += (avail >> p) & 1;
    for (s = 1; s <= MAX_PEERS && n.peer[s].state != P_FREE; s++) {
    }
    if (s > MAX_PEERS || want < 1 || (int)want > nfree) {
        host_reject(from, nonce, STOP_FULL);
        return;
    }
    Peer *pe = &n.peer[s];
    memset(pe, 0, sizeof *pe);
    pe->state = P_JOINING;
    pe->addr = *from;
    pe->nonce = nonce;
    pe->last_recv = t;
    pe->hello_ms = t;
    pe->checked = UINT32_MAX;
    for (int p = 0; p < PLATFORM_MAX_PLAYERS && pe->nplayers < want; p++)
        if ((avail >> p) & 1)
            pe->player[pe->nplayers++] = (uint8_t)p;
    say("HELLO P%d+%d from %s", peer_pnum(s), pe->nplayers - 1, tp_addr_str(from));
    host_send_welcome(s, from);
}

/* One datagram at the Host. `nonce` is the sender's connection epoch: anything
 * but a HELLO counts only if it matches the open connection at that endpoint. */
static void host_handle(const NetAddr *from, int type, uint32_t nonce, Rd *r, uint64_t t) {
    if (type == MSG_HELLO) {
        host_hello(from, nonce, r, t);
        return;
    }
    int s = peer_by_addr(from);
    if (s > 0 && (n.peer[s].nonce != nonce || !peer_active(s)))
        s = -1; /* an older connection's packet, or one that is leaving */
    switch (type) {
    case MSG_INPUT: {
        int player = (int)get8(r);
        if (s < 0) {
            /* Not (or no longer) in the Session: tell that connection to stop */
            Pkt pk;
            build_stop(&pk, nonce, STOP_KICKED, n.set_end, player, NULL);
            send_pkt(from, &pk);
            return;
        }
        Peer *pe = &n.peer[s];
        pe->last_recv = t;
        take_echo(pe, r);
        uint32_t ack = get32(r), first = get32(r), cnt = get8(r), k_pads = get8(r);
        if (!r->ok || k_pads != pe->nplayers)
            return;
        if (pe->state == P_JOINING) {
            /* The joiner's first INPUT says its game is loaded */
            if (join.phase == J_TRANSFER && join.peer == s && join.acked_count == join.chunks) {
                join.phase = J_READY;
                n.hold = false;
                say("READY P%d", peer_pnum(s));
            }
            return;
        }
        if (ack > pe->ack)
            pe->ack = ack;
        for (uint32_t i = 0; i < cnt; i++) {
            uint16_t pads[PLATFORM_MAX_PLAYERS];
            for (uint32_t k = 0; k < k_pads; k++)
                pads[k] = (uint16_t)get16(r);
            uint32_t g = first + i;
            if (r->ok && g >= n.set_end && g >= pe->first_frame && g < n.set_end + RING / 2) {
                memcpy(pe->in[g % RING], pads, k_pads * sizeof(uint16_t));
                pe->in_tag[g % RING] = g + 1;
            }
        }
        HashReport rep;
        if (get_report(r, &rep) && (!pe->has_report || rep.frame > pe->report.frame)) {
            pe->report = rep;
            pe->has_report = true;
            host_check(s);
        }
        return;
    }
    case MSG_CHUNK_ACK: {
        if (s < 0 || join.peer != s || join.phase != J_TRANSFER || nonce != join.nonce)
            return;
        n.peer[s].last_recv = t;
        uint32_t cnt = get16(r);
        if (!r->ok || cnt != join.chunks)
            return;
        for (uint32_t i = 0; i < cnt; i += 8) {
            uint32_t byte = get8(r);
            if (!r->ok)
                return;
            for (uint32_t k = 0; k < 8 && i + k < cnt; k++) {
                if ((byte >> k) & 1 && !join.acked[i + k]) {
                    join.acked[i + k] = 1;
                    join.acked_count++;
                }
            }
        }
        return;
    }
    case MSG_BYE:
        if (s > 0)
            host_drop(s, "quit");
        return;
    default:
        return;
    }
}

/* Root call of EV_CAPTURE on every machine; only the Host has work to do. */
static void capture_done(bool reached) {
    if (!n.host)
        return;
    int s = join.peer;
    if (s < 0 || n.peer[s].state != P_JOINING) {
        join_reset();
        return;
    }
    if (reached) {
        uint32_t J = n.frame; /* the frame everyone resumes on */
        size_t state_len = 0;
        const unsigned char *state = NULL;
        savestate_mem_enable(true);
        savestate_mem_clear();
        bool ok = state_dump_save_slots();
        for (int slot = 0; slot < 2 && !state; slot++)
            state = savestate_mem_data(slot, &state_len);
        static unsigned char sram[SRAM_MAX];
        size_t sram_len = ok && state ? platform_save_read(sram, 0, sizeof sram) : 0;
        if (ok && state && J == n.hold_frame + 1) {
            uint32_t len = 4 + 4 + 1 + 4 * PLATFORM_MAX_PLAYERS + 4 + 4 + (uint32_t)sram_len + (uint32_t)state_len;
            unsigned char *b = malloc(len);
            if (b && len <= MAX_CHUNKS * CHUNK_BYTES) {
                Pkt h; /* header via the packet writer */
                h.n = 0;
                put32(&h, BLOB_MAGIC);
                put32(&h, J);
                put8(&h, (uint32_t)n.delay); /* the joiner sends its pads from J + this */
                uint16_t pads[PLATFORM_MAX_PLAYERS], prev[PLATFORM_MAX_PLAYERS];
                platform_input_get_state(pads, prev);
                for (int k = 0; k < PLATFORM_MAX_PLAYERS; k++)
                    put16(&h, pads[k]);
                for (int k = 0; k < PLATFORM_MAX_PLAYERS; k++)
                    put16(&h, prev[k]);
                put32(&h, (uint32_t)sram_len);
                put32(&h, (uint32_t)state_len);
                memcpy(b, h.b, h.n);
                memcpy(b + h.n, sram, sram_len);
                memcpy(b + h.n + sram_len, state, state_len);
                savestate_mem_clear();
                savestate_mem_enable(false);
                join.blob = b;
                join.len = len;
                join.chunks = (uint16_t)((len + CHUNK_BYTES - 1) / CHUNK_BYTES);
                join.acked_count = 0;
                memset(join.acked, 0, sizeof join.acked);
                memset(join.sent_ms, 0, sizeof join.sent_ms);
                join.phase = J_TRANSFER;
                join.started = now_ms();
                say("CAPTURE P%d f=%u bytes=%u", peer_pnum(s), (unsigned)J, (unsigned)len);
                return;
            }
            free(b);
        }
        savestate_mem_clear();
        savestate_mem_enable(false);
        fprintf(stderr, "netplay: could not serialize the game for P%d\n", peer_pnum(s));
    }
    /* The game sat in an input wait (or the save failed): try again a bit later */
    join_reset();
    n.peer[s].retry_at = n.frame + JOIN_RETRY_FRAMES;
    say("JOIN P%d postponed: the game is busy, retrying in %u frames", peer_pnum(s), (unsigned)JOIN_RETRY_FRAMES);
    fprintf(stderr, "netplay: P%d is waiting to join (the game is busy; retrying)\n", peer_pnum(s));
}

/* ---- Client ---- */

static void client_send_input(void) {
    Pkt pk;
    pkt_begin(&pk, MSG_INPUT, n.nonce);
    put8(&pk, (uint32_t)n.me);
    put_echo(&pk);
    put32(&pk, n.set_end);
    uint32_t first = n.set_end > n.local_start ? n.set_end : n.local_start;
    uint32_t cnt = n.local_end > first ? n.local_end - first : 0;
    if (cnt > MAX_SEND_INPUTS)
        cnt = MAX_SEND_INPUTS;
    put32(&pk, first);
    put8(&pk, cnt);
    put8(&pk, (uint32_t)n.nlocal);
    for (uint32_t g = first; g < first + cnt; g++)
        for (int k = 0; k < n.nlocal; k++)
            put16(&pk, n.local[g % RING][k]);
    put_report(&pk, &n.my_report, n.have_report);
    send_pkt(&n.host_addr, &pk);
}

static void client_send_hello(void) {
    Pkt pk;
    pkt_begin(&pk, MSG_HELLO, n.nonce);
    put_fp(&pk, &my_fp);
    put8(&pk, (uint32_t)n.nlocal);
    put_echo(&pk);
    send_pkt(&n.host_addr, &pk);
}

static void client_send_chunk_ack(void) {
    Pkt pk;
    pkt_begin(&pk, MSG_CHUNK_ACK, n.nonce);
    put16(&pk, n.blob_chunks);
    for (uint32_t i = 0; i < n.blob_chunks; i += 8) {
        uint32_t byte = 0;
        for (uint32_t k = 0; k < 8 && i + k < n.blob_chunks; k++)
            byte |= (uint32_t)(n.chunk_have[i + k] != 0) << k;
        put8(&pk, byte);
    }
    send_pkt(&n.host_addr, &pk);
}

static const char *stop_reason(int reason) {
    switch (reason) {
    case STOP_KICKED: return "the Host dropped this machine from the Session";
    case STOP_FULL:   return "the Session has no room for this machine's Players (4 at most)";
    case STOP_BUILD:  return "the Host runs an incompatible build (both need the same commit, viewport, build options and ROM)";
    case STOP_LOCALE: return "the Host plays in another Language";
    default:          return "stopped by the Host";
    }
}

/* One datagram from the Host's address. Only this connection's (`nonce`) count:
 * a delayed packet meant for an earlier client process at this endpoint is ignored. */
static void client_handle(int type, uint32_t nonce, Rd *r, uint64_t t) {
    if (nonce != n.nonce)
        return;
    n.last_host_recv = t;
    switch (type) {
    case MSG_FRAMES: {
        uint16_t stamp = (uint16_t)get16(r), rtt = (uint16_t)get16(r);
        uint32_t delay = get8(r), first = get32(r), cnt = get8(r);
        if (!r->ok)
            return;
        n.host_stamp = stamp;
        n.host_stamp_ms = t;
        n.my_rtt = rtt;
        if (n.cstate != C_IN)
            return;
        if (delay >= 1 && delay <= MAX_DELAY)
            n.delay = (int)delay; /* the Host's auto delay; net_frame's sampling follows */
        for (uint32_t i = 0; i < cnt; i++) {
            FrameSet fs;
            for (int k = 0; k < PLATFORM_MAX_PLAYERS; k++)
                fs.pad[k] = (uint16_t)get16(r);
            fs.ev = (uint8_t)get8(r);
            fs.ev_mask = (uint8_t)get8(r);
            uint32_t g = first + i;
            if (!r->ok)
                break;
            if (g >= n.set_end && g < n.frame + RING) {
                n.set[g % RING] = fs;
                n.set_tag[g % RING] = g + 1;
            }
        }
        while (n.set_tag[n.set_end % RING] == n.set_end + 1)
            n.set_end++;
        return;
    }
    case MSG_CHUNK: {
        uint32_t total = get32(r), idx = get16(r), cnt = get16(r), len = get16(r);
        if (!r->ok || cnt == 0 || cnt > MAX_CHUNKS || idx >= cnt ||
            total > MAX_CHUNKS * CHUNK_BYTES || r->pos + len > r->n)
            return;
        if (n.cstate == C_WAIT_STATE) {
            if (!n.blob || n.blob_len != total || n.blob_chunks != cnt) {
                free(n.blob);
                n.blob = calloc(1, total ? total : 1);
                n.blob_len = total;
                n.blob_chunks = (uint16_t)cnt;
                n.blob_have = 0;
                memset(n.chunk_have, 0, sizeof n.chunk_have);
            }
            uint32_t off = idx * CHUNK_BYTES;
            if (!n.chunk_have[idx] && off + len <= total) {
                memcpy(n.blob + off, r->b + r->pos, len);
                n.chunk_have[idx] = 1;
                n.blob_have++;
            }
            if (n.blob_have == n.blob_chunks)
                n.cstate = C_LOADING;
        }
        client_send_chunk_ack();
        return;
    }
    case MSG_STOP: {
        int reason = (int)get8(r);
        uint32_t frame = get32(r);
        int player = (int)get8(r);
        uint32_t cnt = get8(r);
        bool differs[MAX_SECTIONS] = { false };
        for (uint32_t i = 0; i < cnt; i++) {
            uint32_t k = get8(r);
            if (k < MAX_SECTIONS)
                differs[k] = true;
        }
        if (!r->ok)
            return;
        if (reason == STOP_DESYNC) {
            const char *list = differs_list(differs, sec_count);
            say("DESYNC f=%u P1 P%d sections=%s", (unsigned)frame, player + 1, list);
            write_dump(frame, differs);
            fatal(3, "desync at frame %u: P1 and P%d disagree on %s (dumps: desync-%u-P*.state/.txt)",
                  (unsigned)frame, player + 1, list, (unsigned)frame);
        }
        fatal(2, "%s", stop_reason(reason));
    }
    case MSG_WELCOME: { /* repeated while this machine waits for the game: a fresh ping stamp */
        uint32_t cnt = get8(r);
        for (uint32_t k = 0; k < cnt; k++)
            get8(r);
        get8(r); /* delay: the game state carries the one that counts */
        uint16_t stamp = (uint16_t)get16(r);
        if (r->ok) {
            n.host_stamp = stamp;
            n.host_stamp_ms = t;
        }
        return;
    }
    case MSG_BYE:
        n.host_left = true; /* run the frames already here first: the last may be EV_END */
        return;
    default:
        return;
    }
}

/* Root call on the joiner: replace the local game with the Host's. */
static void load_done(bool reached) {
    if (!reached)
        return; /* the next net_frame asks again */
    Rd r = { n.blob, n.blob_len, 0, true };
    uint32_t magic = get32(&r), J = get32(&r), delay = get8(&r);
    uint16_t pads[PLATFORM_MAX_PLAYERS], prev[PLATFORM_MAX_PLAYERS];
    for (int k = 0; k < PLATFORM_MAX_PLAYERS; k++)
        pads[k] = (uint16_t)get16(&r);
    for (int k = 0; k < PLATFORM_MAX_PLAYERS; k++)
        prev[k] = (uint16_t)get16(&r);
    uint32_t sram_len = get32(&r), state_len = get32(&r);
    if (!r.ok || magic != BLOB_MAGIC || r.pos + sram_len + state_len != n.blob_len || delay < 1 || delay > MAX_DELAY)
        fatal(2, "the Host sent a malformed game state");
    n.delay = (int)delay;
    const unsigned char *sram = n.blob + r.pos, *state = sram + sram_len;

    /* The Host's save file: the game reads it on continue / file select */
    if (sram_len) {
        FILE *f = fopen(n.save_path, "wb");
        if (!f || fwrite(sram, 1, sram_len, f) != sram_len)
            fatal(2, "could not write %s", n.save_path);
        fclose(f);
    } else {
        remove(n.save_path);
    }

    savestate_mem_enable(true);
    savestate_mem_clear();
    bool ok = savestate_mem_put(0, state, state_len) && state_dump_load_slots();
    savestate_mem_clear();
    savestate_mem_enable(false);
    if (!ok)
        fatal(2, "could not load the Host's game state");
    audio_resync_after_load();
    platform_input_set_state(pads, prev);

    free(n.blob);
    n.blob = NULL;
    n.frame = J;
    n.set_end = J;
    memset(n.set_tag, 0, sizeof n.set_tag);
    n.local_start = n.local_end = J + (uint32_t)n.delay;
    n.cstate = C_IN;
    say("LOADED P%d f=%u", n.me + 1, (unsigned)J);
    client_send_input(); /* tells the Host the game is loaded */
}

/* ---- Both ---- */

/* Check a datagram's header; on success `r` reads its payload. */
static bool read_header(const uint8_t *buf, int len, Rd *r, uint32_t *nonce) {
    if (len < HEADER_BYTES || buf[0] != 'E' || buf[1] != 'N' || buf[2] != PROTO_VERSION)
        return false;
    *r = (Rd){ buf, (size_t)len, 4, true };
    *nonce = get32(r);
    return true;
}

static void service(void) {
    uint8_t buf[PKT_MAX + 64];
    NetAddr from;
    int len;
    uint64_t t = now_ms();
    while ((len = tp_recv(&from, buf, sizeof buf)) >= 0) {
        Rd r;
        uint32_t nonce;
        if (!read_header(buf, len, &r, &nonce))
            continue;
        if (n.host)
            host_handle(&from, buf[3], nonce, &r, t);
        else if (udp_addr_equal(&from, &n.host_addr))
            client_handle(buf[3], nonce, &r, t);
    }
    if (n.host) {
        static bool lost_said;
        if (tp_lost() && !lost_said) { /* the game goes on; the others time out and leave */
            lost_said = true;
            say("RELAY LOST %s", tp_lost());
            fprintf(stderr, "netplay: lost the relay (%s); nobody else can join\n", tp_lost());
        }
        for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++)
            if (peer_active(p) && t - n.peer[p].last_recv > TIMEOUT_MS)
                host_drop(p, "stopped responding");
        host_send_chunks(t);
        host_confirm();
        host_broadcast(t);
    } else if (n.host_left && n.cstate == C_IN && n.set_end <= n.frame && !n.ended) {
        fatal(2, "the Host ended the Session");
    } else if (n.host_left && n.cstate != C_IN) {
        fatal(2, "the Host ended the Session");
    } else if (tp_lost() && !n.host_left) {
        fatal(2, "lost the connection to the Host (%s)", tp_lost());
    } else if (t - n.last_host_recv > TIMEOUT_MS) {
        fatal(2, "lost the connection to the Host");
    }
}

static bool is_mine(int p) {
    for (int k = 0; k < n.nlocal; k++)
        if (n.mine[k] == p)
            return true;
    return false;
}

static void apply_event(uint32_t f, const FrameSet *fs) {
    switch (fs->ev) {
    case EV_CAPTURE:
        if (!host_request_root_call(capture_done))
            capture_done(false);
        break;
    case EV_JOIN:
        for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
            if (fs->ev_mask & (1u << p)) {
                coop_join(p);
                say("JOIN P%d f=%u", p + 1, (unsigned)f);
            }
        }
        break;
    case EV_LEAVE:
        for (int p = 0; p < PLATFORM_MAX_PLAYERS; p++) {
            if (!(fs->ev_mask & (1u << p)))
                continue;
            if (!n.host && is_mine(p))
                fatal(2, "%s", stop_reason(STOP_KICKED));
            coop_leave(p);
            say("LEAVE P%d f=%u", p + 1, (unsigned)f);
        }
        break;
    case EV_END:
        n.ended = true;
        say("END f=%u", (unsigned)f);
        platform_request_quit();
        break;
    default:
        break;
    }
}

/* A joiner before its game is the Host's: wait for the state, then load it at a root
 * boundary. The pads stay 0 and no net frame is consumed. */
static void client_pre_session(uint16_t pads[PLATFORM_MAX_PLAYERS], const NetInputHooks *hk) {
    memset(pads, 0, sizeof(uint16_t) * PLATFORM_MAX_PLAYERS);
    uint64_t last = 0;
    while (n.cstate == C_WAIT_STATE && !platform_input_quit_requested()) {
        uint64_t t = now_ms();
        if (t - last >= HELLO_MS) {
            client_send_hello(); /* keepalive; the Host repeats WELCOME */
            last = t;
        }
        tp_wait(2);
        service();
        hk->pump();
        static uint64_t drawn;
        if (hk->present && t - drawn >= 100) {
            hk->present();
            drawn = t;
        }
    }
    if (n.cstate == C_LOADING)
        host_request_root_call(load_done);
}

void net_frame(uint16_t pads[PLATFORM_MAX_PLAYERS], const NetInputHooks *hk) {
    if (!n.host && n.cstate != C_IN) {
        client_pre_session(pads, hk);
        return;
    }
    uint32_t f = n.frame;
    for (int i = 0; i < 8; i++) {
        if (n.shot_frame[i] && n.shot_frame[i] == f) {
            char path[64];
            snprintf(path, sizeof path, "net-%u.png", (unsigned)f);
            input_script_shot(path);
        }
    }
    if (f % HASH_INTERVAL == 0)
        hash_point(f);

    /* This machine's pad, for frame f + D. It fills every frame from local_end on:
     * when the delay grows, the frames it skips get this pad too; when it shrinks,
     * nothing is written until f + D passes the frames already sent. */
    uint32_t g = f + (uint32_t)n.delay;
    uint16_t local[PLATFORM_MAX_PLAYERS] = { 0 };
    hk->sample_local(local, n.nlocal);
    for (uint32_t h = n.local_end; h <= g; h++)
        memcpy(n.local[h % RING], local, sizeof local);
    if (g + 1 > n.local_end)
        n.local_end = g + 1;

    if (n.host) {
        service();
    } else {
        service();
        client_send_input();
    }
    uint64_t last = now_ms();
    while (n.set_end <= f) {
        if (platform_input_quit_requested()) {
            memset(pads, 0, sizeof(uint16_t) * PLATFORM_MAX_PLAYERS);
            return;
        }
        tp_wait(1);
        service();
        hk->pump();
        uint64_t t = now_ms();
        /* Resend while waiting; over the relay (which loses nothing) only a
         * keepalive, so a long wait (a join, --net-wait-players) isn't a timeout */
        if (!n.host && t - last >= (tp_reliable() ? KEEPALIVE_MS : RESEND_MS)) {
            client_send_input();
            last = t;
        }
    }
    const FrameSet *fs = &n.set[f % RING];
    memcpy(pads, fs->pad, sizeof fs->pad);
    n.frame = f + 1;
    apply_event(f, fs);
    if (n.test_desync_frame && f == n.test_desync_frame) {
        rng_state.a ^= 0x5A5A; /* test only: EB_NET_TEST_DESYNC */
        say("TEST perturbed the RNG at f=%u", (unsigned)f);
    }
}

bool net_active(void) {
    return n.active;
}

bool net_start(const NetConfig *cfg) {
    memset(&n, 0, sizeof n); /* the launcher may try again after a failure */
    const char *hi = getenv("EB_NET_HASH_INTERVAL");
    if (hi && atoi(hi) > 0)
        hash_interval = (uint32_t)atoi(hi);
    const char *sf = getenv("EB_NET_SHOT_FRAMES"); /* "F1,F2,..." */
    for (int i = 0; sf && *sf && i < 8; i++) {
        char *end;
        n.shot_frame[i] = (uint32_t)strtoul(sf, &end, 10);
        sf = *end == ',' ? end + 1 : "";
    }
    const char *td = getenv("EB_NET_TEST_DESYNC");
    n.test_desync_frame = td ? (uint32_t)strtoul(td, NULL, 10) : 0;
    n.auto_delay = cfg->input_delay == 0;
    n.delay = n.auto_delay ? NET_DEFAULT_INPUT_DELAY : cfg->input_delay;
    n.nlocal = cfg->local_players;
    if (n.nlocal < 1 || n.nlocal > PLATFORM_MAX_PLAYERS)
        return fail("--local-players takes 1-%d", PLATFORM_MAX_PLAYERS);
    if (n.delay < 1 || n.delay > MAX_DELAY)
        return fail("--input-delay takes 1-%d", MAX_DELAY);
    fingerprint_init();

    char err[512];
    char base[256] = "";
    if (cfg->host_room || cfg->join_room) {
        /* A bare relay is needed to host; a join takes it from the invite */
        if (cfg->host_room && !(cfg->relay && relay_base(cfg->relay, base, sizeof base)))
            return fail("no relay to host on (set one with --relay URL)");
    }

    if (cfg->host_port > 0 || cfg->host_room) {
        if (cfg->host_room) {
            char code[RELAY_CODE_LEN + 1];
            if (!tp_open_relay_host(base, code, err, sizeof err))
                return fail("%s", err);
            relay_invite(base, code, n.invite, sizeof n.invite);
        } else if (!tp_open_udp(cfg->host_port, err, sizeof err)) {
            return fail("%s", err);
        }
        n.host = true;
        n.me = 0;
        for (int k = 0; k < n.nlocal; k++)
            n.mine[k] = (uint8_t)k;
        n.end_frame = cfg->end_frame;
        n.wait_players = cfg->wait_players > 1 ? cfg->wait_players : 0;
        n.local_start = 0;
        n.local_end = (uint32_t)n.delay; /* frames 0..D-1: nobody's input yet */
        n.active = true;
        const char *delay_kind = n.auto_delay ? " (auto)" : "";
        if (cfg->host_room) {
            say("HOST room=%.*s invite=%s delay=%d%s build=%s %ux%u assets=%08x", RELAY_CODE_LEN,
                n.invite + strlen(n.invite) - RELAY_CODE_LEN, n.invite, n.delay, delay_kind, my_fp.revision,
                (unsigned)my_fp.width, (unsigned)my_fp.height, (unsigned)my_fp.assets);
            fprintf(stderr, "netplay: hosting room %s (input delay %d%s)\n", n.invite, n.delay, delay_kind);
        } else {
            say("HOST port=%d delay=%d%s build=%s %ux%u assets=%08x", cfg->host_port, n.delay, delay_kind,
                my_fp.revision, (unsigned)my_fp.width, (unsigned)my_fp.height, (unsigned)my_fp.assets);
            fprintf(stderr, "netplay: hosting on UDP port %d (input delay %d%s)\n", cfg->host_port, n.delay,
                    delay_kind);
        }
        return true;
    }

    /* Client: a relay room, or "ADDR[:PORT]" */
    const char *target = cfg->join_room ? cfg->join_room : cfg->join;
    if (cfg->join_room) {
        char code[RELAY_CODE_LEN + 1];
        if (!relay_parse_invite(cfg->join_room, cfg->relay, base, sizeof base, code))
            return fail("\"%s\" isn't an invite (it looks like relay.example.dev/K7QF2M)", cfg->join_room);
        if (!tp_open_relay_join(base, code, &n.host_addr, err, sizeof err))
            return fail("%s", err);
        relay_invite(base, code, n.invite, sizeof n.invite);
    } else {
        char host[256];
        snprintf(host, sizeof host, "%s", cfg->join);
        int port = NET_DEFAULT_PORT;
        char *colon = strrchr(host, ':');
        if (colon) {
            *colon = '\0';
            port = atoi(colon + 1);
        }
        if (!udp_init() || port <= 0 || port > 65535 || !udp_resolve(host, port, &n.host_addr))
            return fail("can't resolve %s", cfg->join);
        if (!tp_open_udp(0, err, sizeof err))
            return fail("%s", err);
    }
    /* The Host owns the save: this machine's SRAM is a temp file for the Session */
    const char *tmp = getenv("TMPDIR");
#ifdef _WIN32
    if (!tmp || !*tmp)
        tmp = getenv("TEMP");
#endif
    snprintf(n.save_path, sizeof n.save_path, "%s/earthbound-net-%d.srm", tmp && *tmp ? tmp : "/tmp", (int)getpid());

    n.nonce = (uint32_t)platform_timer_ticks() ^ ((uint32_t)getpid() << 16);
    if (n.nonce == 0)
        n.nonce = 1; /* 0 is what a zeroed spoof would carry */
    uint64_t start = now_ms(), last = 0;
    bool busy_said = false;
    for (;;) {
        uint64_t t = now_ms();
        if (t - start > CONNECT_MS)
            return fail("no answer from %s", target);
        if (tp_lost())
            return fail("%s", strcmp(tp_lost(), "no such room") == 0
                                  ? "no such room (the Host may have closed it)" : tp_lost());
        if (t - last >= HELLO_MS) {
            client_send_hello();
            last = t;
        }
        tp_wait(10);
        uint8_t buf[PKT_MAX + 64];
        NetAddr from;
        int len;
        while ((len = tp_recv(&from, buf, sizeof buf)) >= 0) {
            Rd r;
            uint32_t nonce;
            if (!read_header(buf, len, &r, &nonce) || !udp_addr_equal(&from, &n.host_addr) || nonce != n.nonce)
                continue;
            if (buf[3] == MSG_WELCOME) {
                int cnt = (int)get8(&r);
                bool bad = cnt != n.nlocal;
                for (int k = 0; k < cnt && k < PLATFORM_MAX_PLAYERS; k++) {
                    n.mine[k] = (uint8_t)get8(&r);
                    bad |= n.mine[k] < 1 || n.mine[k] >= PLATFORM_MAX_PLAYERS;
                }
                n.me = n.mine[0];
                n.delay = (int)get8(&r);
                n.host_stamp = (uint16_t)get16(&r);
                n.host_stamp_ms = now_ms();
                if (!r.ok || bad || n.delay < 1 || n.delay > MAX_DELAY)
                    continue;
                remove(n.save_path);
                platform_save_set_path(n.save_path);
                n.cstate = C_WAIT_STATE;
                n.last_host_recv = now_ms();
                n.active = true;
                client_send_hello(); /* echoes the stamp at once: the Host may wait for this ping */
                say("WELCOME P%d+%d delay=%d", n.me + 1, n.nlocal - 1, n.delay);
                fprintf(stderr, "netplay: joined %s as P%d; waiting for the game\n", target, n.me + 1);
                return true;
            }
            if (buf[3] == MSG_REJECT) {
                int reason = (int)get8(&r);
                if (reason == STOP_BUSY) {
                    if (!busy_said) /* this endpoint's last connection is still open there */
                        fprintf(stderr, "netplay: the Host still holds this machine's previous connection; "
                                        "waiting for it to time out (up to %u s)\n", TIMEOUT_MS / 1000);
                    busy_said = true;
                    continue;
                }
                if (reason == STOP_BUILD) {
                    Fingerprint host_fp;
                    get_fp(&r, &host_fp);
                    const char *diff = r.ok ? fp_diff(&host_fp, &my_fp, "this machine") : "";
                    return fail("%s%s%s", stop_reason(reason), *diff ? ". " : "", diff);
                }
                if (reason == STOP_LOCALE) {
                    Locale host = (Locale)get8(&r);
                    if (r.ok)
                        return fail("the Host plays in %s and this machine in %s (both need the same Language)",
                                    locale_name(host), locale_name(locale_get()));
                }
                return fail("%s", stop_reason(reason));
            }
        }
    }
}

/* The Session as the status overlay shows it. */
void net_status(NetStatus *st) {
    memset(st, 0, sizeof *st);
    st->active = n.active;
    st->host = n.host;
    st->delay = n.delay;
    st->relay_lost = n.host ? tp_lost() : NULL;
    snprintf(st->invite, sizeof st->invite, "%s", n.invite);
    if (!n.host) {
        st->joined = n.cstate == C_IN;
        st->peer[st->npeers].player = n.me;
        st->peer[st->npeers++].rtt = n.my_rtt;
        return;
    }
    for (int s = 1; s <= MAX_PEERS; s++) {
        if (n.peer[s].state != P_IN)
            continue;
        st->peer[st->npeers].player = n.peer[s].player[0];
        st->peer[st->npeers++].rtt = n.peer[s].rtt_known ? n.peer[s].rtt : 0;
    }
}

const char *net_error(void) {
    return n.err;
}

void net_shutdown(void) {
    if (!n.active || n.shutting)
        return;
    n.shutting = true;
    if (n.host && !n.stopped) {
        /* Let every Player collect the frames confirmed so far (the last one may
         * carry EV_END), then say goodbye. */
        uint64_t deadline = now_ms() + 3000;
        while (now_ms() < deadline) {
            bool behind = false;
            for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++)
                if (n.peer[p].state == P_IN && n.peer[p].ack < n.set_end)
                    behind = true;
            if (!behind)
                break;
            tp_wait(5);
            uint8_t buf[PKT_MAX + 64];
            NetAddr from;
            int len;
            uint64_t t = now_ms();
            while ((len = tp_recv(&from, buf, sizeof buf)) >= 0) {
                Rd r;
                uint32_t nonce;
                if (read_header(buf, len, &r, &nonce) && (buf[3] == MSG_INPUT || buf[3] == MSG_BYE))
                    host_handle(&from, buf[3], nonce, &r, t);
            }
            for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++)
                if (n.peer[p].state == P_IN && n.peer[p].ack < n.set_end &&
                    (tp_reliable() ? n.peer[p].sent_end < n.set_end : t - n.peer[p].last_send >= RESEND_MS))
                    host_send_frames(p, t);
        }
    }
    if (n.host && !n.stopped) { /* after a STOP, a BYE could overtake it */
        for (int rep = 0; rep < 3; rep++)
            for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++)
                if (n.peer[p].state != P_FREE)
                    send_bye(&n.peer[p].addr, n.peer[p].nonce);
    } else if (!n.host) {
        for (int rep = 0; rep < 3; rep++)
            send_bye(&n.host_addr, n.nonce);
        remove(n.save_path);
        char tmp[sizeof n.save_path + 8];
        snprintf(tmp, sizeof tmp, "%s.tmp", n.save_path);
        remove(tmp);
    }
    tp_close();
}

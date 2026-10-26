/*
 * Online co-op Session: the wire protocol, the Host relay, the client, joins,
 * disconnects and desync detection. Overview in net.h and docs/coop-online.md.
 *
 * Frames. Net frame f is the f-th call of net_frame() since the Host started (the
 * Host's local counter; a joiner starts at the frame it joins on). Each confirmed
 * frame carries all four pads and at most one session event:
 *
 *   EV_CAPTURE p  every machine requests a root call (host_request_root_call): the
 *                 same torn-safe unwind a savestate uses. At the root boundary the
 *                 Host serializes the game + SRAM for joiner p. The Host confirms
 *                 nothing past this frame until the join resolves, so everyone
 *                 waits at the next frame (J) while the joiner loads.
 *   EV_JOIN p     coop_join(p) on every machine; p's pad is 0 for frames J..J+D-1
 *                 and its own input from J+D on. The joiner resumes at J.
 *   EV_LEAVE p    coop_leave(p) on every machine. The Host stopped waiting for p's
 *                 input when it dropped p (pads are 0 from then on).
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
 * Wire format: little-endian; every datagram starts 'E' 'N' version type.
 */
#include "net/net.h"
#include "net/udp.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "coop/coop.h"
#include "core/math.h"
#include "core/state_dump.h"
#include "game/audio.h"
#include "game_main.h"

/* sdl2_savestate.c: memory-backed slots */
void savestate_mem_enable(bool on);
void savestate_mem_clear(void);
const unsigned char *savestate_mem_data(int slot, size_t *len);
bool savestate_mem_put(int slot, const void *data, size_t len);
/* sdl2_save.c */
void platform_save_set_path(const char *path);

#define PROTO_VERSION     1
#define RING              512u    /* frames of pad / confirmed-set history (power of 2) */
#define MAX_DELAY         60
#define HASH_INTERVAL     hash_interval
#define TIMEOUT_MS        10000u  /* silence before a Player is dropped / the Host is given up on */
#define CONNECT_MS        10000u
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

/* Frames between hash points: 60, or EB_NET_HASH_INTERVAL (debugging; every
 * machine must use the same value). */
static uint32_t hash_interval = 60;

enum {
    MSG_HELLO = 1,  /* C->H  u32 nonce, u32 layout id */
    MSG_WELCOME,    /* H->C  u32 nonce, u8 player, u8 input delay */
    MSG_REJECT,     /* H->C  u32 nonce, u8 reason (STOP_*) */
    MSG_INPUT,      /* C->H  u8 player, u32 ack, u32 first, u8 n, n x u16 pad, report */
    MSG_FRAMES,     /* H->C  u32 first, u8 n, n x (4 x u16 pad, u8 event, u8 event player) */
    MSG_CHUNK,      /* H->C  u32 nonce, u32 total, u16 index, u16 count, u16 len, bytes */
    MSG_CHUNK_ACK,  /* C->H  u32 nonce, u16 count, ceil(count/8) bitmap bytes */
    MSG_STOP,       /* H->C  u8 reason, u32 frame, u8 player, u8 n, n x u8 section index */
    MSG_BYE,        /* both  leaving */
};
/* report = u8 present, then u32 frame, u8 n, n x u32 section hash */

enum { STOP_DESYNC = 1, STOP_KICKED, STOP_FULL, STOP_BUILD };
enum { EV_NONE = 0, EV_CAPTURE, EV_JOIN, EV_LEAVE, EV_END };

typedef struct {
    uint16_t pad[PLATFORM_MAX_PLAYERS];
    uint8_t ev, ev_player;
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
static void putn(Pkt *p, const void *d, size_t n) {
    if (p->n + n <= PKT_MAX) {
        memcpy(p->b + p->n, d, n);
        p->n += n;
    }
}
static void pkt_begin(Pkt *p, int type) {
    p->n = 0;
    put8(p, 'E');
    put8(p, 'N');
    put8(p, PROTO_VERSION);
    put8(p, (uint32_t)type);
}

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

/* ---- State ---- */

enum { P_FREE, P_JOINING, P_IN, P_LEAVING };
typedef struct {
    int state;
    UdpAddr addr;
    uint32_t nonce;
    uint64_t last_recv, last_send;
    uint32_t ack;          /* the client holds the confirmed sets of frames < ack */
    uint32_t sent_end;     /* set_end when FRAMES were last sent to it */
    uint32_t first_frame;  /* its pad is 0 before this frame */
    uint32_t retry_at;     /* joining: capture no earlier than this frame */
    uint16_t in[RING];
    uint32_t in_tag[RING]; /* frame + 1 of in[] (0 = empty) */
    HashReport report;
    bool has_report;
    uint32_t checked;      /* report frame already compared */
} Peer;

enum { J_NONE, J_CAPTURING, J_TRANSFER, J_READY };
enum { C_WAIT_STATE, C_LOADING, C_IN };

static struct {
    bool active, host, shutting, ended, stopped;
    bool host_left;               /* client: the Host said goodbye (finish the frames held, then stop) */
    int fd;
    int delay;
    int me;                       /* this machine's Player (0 = P1) */
    uint32_t frame;               /* next net frame to run */
    uint32_t end_frame;           /* Host: EV_END on this frame (0 = never) */
    bool end_emitted;
    int wait_players;             /* Host: hold the game until this many Players are in (0 = don't) */
    FrameSet set[RING];
    uint32_t set_tag[RING];       /* client: frame + 1 held in set[] */
    uint32_t set_end;             /* confirmed sets are known for frames < set_end */
    uint16_t local[RING];
    uint32_t local_start;         /* first frame this machine contributes a pad to */
    uint32_t local_end;           /* local pads are recorded for frames < local_end */
    uint32_t test_desync_frame;   /* EB_NET_TEST_DESYNC: perturb the RNG on this frame */
    uint32_t shot_frame[8];       /* EB_NET_SHOT_FRAMES: screenshot at these frames (tests) */

    /* client */
    UdpAddr host_addr;
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
} n = { .fd = -1 };

static struct {
    int phase, player;
    uint32_t nonce;
    unsigned char *blob;
    uint32_t len;
    uint16_t chunks, acked_count;
    uint8_t acked[MAX_CHUNKS];
    uint64_t sent_ms[MAX_CHUNKS];
    uint64_t started;
} join = { .player = -1 };

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

static void send_pkt(const UdpAddr *to, const Pkt *p) {
    udp_send(n.fd, to, p->b, p->n);
}

static void send_bye(const UdpAddr *to) {
    Pkt p;
    pkt_begin(&p, MSG_BYE);
    put8(&p, (uint32_t)n.me);
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
    exit(code);
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

static bool peer_active(int p) {
    return n.peer[p].state == P_JOINING || n.peer[p].state == P_IN;
}

static int peer_by_addr(const UdpAddr *a) {
    for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++)
        if (peer_active(p) && udp_addr_equal(&n.peer[p].addr, a))
            return p;
    return -1;
}

static void join_reset(void) {
    free(join.blob);
    join.blob = NULL;
    join.phase = J_NONE;
    join.player = -1;
    n.hold = false;
}

/* Stop waiting for Player p. In the Session, p leaves (EV_LEAVE) on the next frame
 * the Host confirms; its pad is 0 from now on. */
static void host_drop(int p, const char *why) {
    Peer *pe = &n.peer[p];
    if (pe->state == P_IN) {
        pe->state = P_LEAVING;
        say("DROP P%d %s", p + 1, why);
        fprintf(stderr, "netplay: P%d %s; they leave the game\n", p + 1, why);
    } else if (pe->state == P_JOINING) {
        say("DROP P%d %s (while joining)", p + 1, why);
        if (join.player == p) {
            if (join.phase == J_CAPTURING)
                join.player = -1; /* the capture callback releases the hold */
            else
                join_reset();
        }
        pe->state = P_FREE;
    }
}

/* The session event for frame g, if any (Host). */
static void host_pick_event(uint32_t g, FrameSet *fs) {
    if (n.end_frame && g >= n.end_frame) {
        fs->ev = EV_END;
        n.end_emitted = true;
        return;
    }
    if (join.phase == J_READY && join.player > 0) {
        Peer *pe = &n.peer[join.player];
        fs->ev = EV_JOIN;
        fs->ev_player = (uint8_t)join.player;
        pe->state = P_IN;
        pe->first_frame = g + (uint32_t)n.delay;
        pe->sent_end = g;
        pe->ack = g;
        join_reset();
        return;
    }
    for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++) {
        if (n.peer[p].state == P_LEAVING) {
            fs->ev = EV_LEAVE;
            fs->ev_player = (uint8_t)p;
            n.peer[p].state = P_FREE;
            return;
        }
    }
    if (join.phase != J_NONE)
        return;
    for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++) {
        if (n.peer[p].state == P_JOINING && n.peer[p].retry_at <= g) {
            fs->ev = EV_CAPTURE;
            fs->ev_player = (uint8_t)p;
            join.phase = J_CAPTURING;
            join.player = p;
            join.nonce = n.peer[p].nonce;
            join.started = now_ms();
            n.hold = true;
            n.hold_frame = g;
            return;
        }
    }
}

/* --net-wait-players: until enough Players are in, only frames that move a join
 * along (EV_CAPTURE / EV_JOIN) are confirmed, so the game waits on that frame. */
static bool host_waiting_ok(uint32_t g) {
    int in = 1;
    for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++)
        in += n.peer[p].state == P_IN;
    if (in >= n.wait_players) {
        n.wait_players = 0;
        return true;
    }
    if (join.phase == J_READY)
        return true;
    if (join.phase != J_NONE)
        return false;
    for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++)
        if (n.peer[p].state == P_JOINING && n.peer[p].retry_at <= g)
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
        fs.pad[0] = n.local[g % RING];
        bool ready = true;
        for (int p = 1; p < PLATFORM_MAX_PLAYERS && ready; p++) {
            Peer *pe = &n.peer[p];
            if (pe->state != P_IN || g < pe->first_frame)
                continue;
            if (pe->in_tag[g % RING] != g + 1)
                ready = false;
            else
                fs.pad[p] = pe->in[g % RING];
        }
        if (!ready)
            break;
        host_pick_event(g, &fs);
        n.set[g % RING] = fs;
        n.set_end = g + 1;
    }
}

static void host_send_frames(int p, uint64_t t) {
    Peer *pe = &n.peer[p];
    if (pe->ack + RING <= n.set_end) {
        host_drop(p, "fell too far behind");
        return;
    }
    uint32_t first = pe->ack < n.set_end ? pe->ack : n.set_end;
    uint32_t cnt = n.set_end - first;
    if (cnt > MAX_SEND_FRAMES)
        cnt = MAX_SEND_FRAMES;
    Pkt pk;
    pkt_begin(&pk, MSG_FRAMES);
    put32(&pk, first);
    put8(&pk, cnt);
    for (uint32_t g = first; g < first + cnt; g++) {
        const FrameSet *fs = &n.set[g % RING];
        for (int k = 0; k < PLATFORM_MAX_PLAYERS; k++)
            put16(&pk, fs->pad[k]);
        put8(&pk, fs->ev);
        put8(&pk, fs->ev_player);
    }
    send_pkt(&pe->addr, &pk);
    pe->last_send = t;
    pe->sent_end = n.set_end;
}

/* FRAMES to every Player in the Session: new frames at once, unacknowledged ones
 * every RESEND_MS, a keepalive every KEEPALIVE_MS. */
static void host_broadcast(uint64_t t) {
    for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++) {
        Peer *pe = &n.peer[p];
        if (pe->state != P_IN)
            continue;
        bool fresh = pe->sent_end < n.set_end;
        bool lagging = pe->ack < n.set_end && t - pe->last_send >= RESEND_MS;
        if (fresh || lagging || t - pe->last_send >= KEEPALIVE_MS)
            host_send_frames(p, t);
    }
}

static void host_send_stop(int reason, uint32_t frame, int player, const bool *differs) {
    Pkt pk;
    pkt_begin(&pk, MSG_STOP);
    put8(&pk, (uint32_t)reason);
    put32(&pk, frame);
    put8(&pk, (uint32_t)player);
    uint8_t cnt = 0;
    uint8_t idx[MAX_SECTIONS];
    for (int i = 0; differs && i < sec_count; i++)
        if (differs[i])
            idx[cnt++] = (uint8_t)i;
    put8(&pk, cnt);
    putn(&pk, idx, cnt);
    for (int rep = 0; rep < 5; rep++) {
        for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++)
            if (peer_active(p))
                send_pkt(&n.peer[p].addr, &pk);
        udp_sleep(20);
    }
}

/* Compare Player p's latest hash report with the Host's snapshot of that frame. */
static void host_check(int p) {
    Peer *pe = &n.peer[p];
    if (n.shutting || pe->state != P_IN || !pe->has_report || pe->report.frame == pe->checked)
        return;
    Snapshot *s = find_snapshot(pe->report.frame);
    if (!s)
        return; /* not hashed here yet (the client runs up to D frames ahead) */
    pe->checked = pe->report.frame;
    bool differs[MAX_SECTIONS] = { false };
    bool any = pe->report.count != s->rep.count;
    for (int i = 0; i < s->rep.count && i < pe->report.count; i++)
        if (pe->report.hash[i] != s->rep.hash[i])
            differs[i] = any = true;
    if (!any)
        return;
    uint32_t frame = s->frame;
    const char *list = differs_list(differs, s->rep.count);
    say("DESYNC f=%u P1 P%d sections=%s", (unsigned)frame, p + 1, list);
    write_dump(frame, differs);
    host_send_stop(STOP_DESYNC, frame, p, differs);
    fatal(3, "desync at frame %u: P1 and P%d disagree on %s (dumps: desync-%u-P*.state/.txt)", (unsigned)frame,
          p + 1, list, (unsigned)frame);
}

static void host_send_chunks(uint64_t t) {
    if (join.phase != J_TRANSFER)
        return;
    if (t - join.started > JOIN_TIMEOUT_MS) {
        int p = join.player;
        say("JOIN P%d timed out", p + 1);
        join_reset();
        n.peer[p].state = P_FREE;
        return;
    }
    Peer *pe = &n.peer[join.player];
    int sent = 0;
    for (uint16_t i = 0; i < join.chunks && sent < CHUNKS_PER_TICK; i++) {
        if (join.acked[i] || (join.sent_ms[i] && t - join.sent_ms[i] < CHUNK_RESEND_MS))
            continue;
        uint32_t off = (uint32_t)i * CHUNK_BYTES;
        uint32_t len = join.len - off < CHUNK_BYTES ? join.len - off : CHUNK_BYTES;
        Pkt pk;
        pkt_begin(&pk, MSG_CHUNK);
        put32(&pk, join.nonce);
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

static void host_handle(const UdpAddr *from, int type, Rd *r, uint64_t t) {
    int p = peer_by_addr(from);
    switch (type) {
    case MSG_HELLO: {
        uint32_t nonce = get32(r), layout = get32(r);
        if (!r->ok)
            return;
        if (p > 0 && n.peer[p].nonce != nonce) {
            host_drop(p, "restarted"); /* same address, new process: the old one is gone */
            p = -1;
        }
        Pkt pk;
        if (p > 0) { /* our WELCOME was lost: repeat it */
            n.peer[p].last_recv = t;
            pkt_begin(&pk, MSG_WELCOME);
            put32(&pk, nonce);
            put8(&pk, (uint32_t)p);
            put8(&pk, (uint32_t)n.delay);
            send_pkt(from, &pk);
            return;
        }
        int reason = 0;
        if (layout != state_dump_layout_id()) {
            reason = STOP_BUILD;
        } else {
            for (p = 1; p < PLATFORM_MAX_PLAYERS && n.peer[p].state != P_FREE; p++) {
            }
            if (p == PLATFORM_MAX_PLAYERS)
                reason = STOP_FULL;
        }
        if (reason) {
            pkt_begin(&pk, MSG_REJECT);
            put32(&pk, nonce);
            put8(&pk, (uint32_t)reason);
            send_pkt(from, &pk);
            return;
        }
        Peer *pe = &n.peer[p];
        memset(pe, 0, sizeof *pe);
        pe->state = P_JOINING;
        pe->addr = *from;
        pe->nonce = nonce;
        pe->last_recv = t;
        pe->checked = UINT32_MAX;
        say("HELLO P%d from %s", p + 1, udp_addr_str(from));
        pkt_begin(&pk, MSG_WELCOME);
        put32(&pk, nonce);
        put8(&pk, (uint32_t)p);
        put8(&pk, (uint32_t)n.delay);
        send_pkt(from, &pk);
        return;
    }
    case MSG_INPUT: {
        int player = (int)get8(r);
        if (p < 0) {
            /* Not (or no longer) in the Session: tell it to stop */
            Pkt pk;
            pkt_begin(&pk, MSG_STOP);
            put8(&pk, STOP_KICKED);
            put32(&pk, n.set_end);
            put8(&pk, (uint32_t)player);
            put8(&pk, 0);
            send_pkt(from, &pk);
            return;
        }
        Peer *pe = &n.peer[p];
        pe->last_recv = t;
        uint32_t ack = get32(r), first = get32(r), cnt = get8(r);
        if (!r->ok || player != p)
            return;
        if (pe->state == P_JOINING) {
            /* The joiner's first INPUT says its game is loaded */
            if (join.phase == J_TRANSFER && join.player == p && join.acked_count == join.chunks) {
                join.phase = J_READY;
                n.hold = false;
                say("READY P%d", p + 1);
            }
            return;
        }
        if (ack > pe->ack)
            pe->ack = ack;
        for (uint32_t i = 0; i < cnt; i++) {
            uint16_t pad = (uint16_t)get16(r);
            uint32_t g = first + i;
            if (r->ok && g >= n.set_end && g >= pe->first_frame && g < n.set_end + RING / 2) {
                pe->in[g % RING] = pad;
                pe->in_tag[g % RING] = g + 1;
            }
        }
        HashReport rep;
        if (get_report(r, &rep) && (!pe->has_report || rep.frame > pe->report.frame)) {
            pe->report = rep;
            pe->has_report = true;
            host_check(p);
        }
        return;
    }
    case MSG_CHUNK_ACK: {
        if (p < 0 || join.player != p || join.phase != J_TRANSFER)
            return;
        n.peer[p].last_recv = t;
        uint32_t nonce = get32(r), cnt = get16(r);
        if (!r->ok || nonce != join.nonce || cnt != join.chunks)
            return;
        for (uint32_t i = 0; i < cnt; i++) {
            if (i % 8 == 0) {
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
        }
        return;
    }
    case MSG_BYE:
        if (p > 0)
            host_drop(p, "quit");
        return;
    default:
        return;
    }
}

/* Root call of EV_CAPTURE on every machine; only the Host has work to do. */
static void capture_done(bool reached) {
    if (!n.host)
        return;
    int p = join.player;
    if (p < 0 || n.peer[p].state != P_JOINING) {
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
        for (int s = 0; s < 2 && !state; s++)
            state = savestate_mem_data(s, &state_len);
        static unsigned char sram[SRAM_MAX];
        size_t sram_len = ok && state ? platform_save_read(sram, 0, sizeof sram) : 0;
        if (ok && state && J == n.hold_frame + 1) {
            uint32_t len = 4 + 4 + 4 * PLATFORM_MAX_PLAYERS + 4 + 4 + (uint32_t)sram_len + (uint32_t)state_len;
            unsigned char *b = malloc(len);
            if (b && len <= MAX_CHUNKS * CHUNK_BYTES) {
                Pkt h; /* header via the packet writer */
                h.n = 0;
                put32(&h, BLOB_MAGIC);
                put32(&h, J);
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
                say("CAPTURE P%d f=%u bytes=%u", p + 1, (unsigned)J, (unsigned)len);
                return;
            }
            free(b);
        }
        savestate_mem_clear();
        savestate_mem_enable(false);
        fprintf(stderr, "netplay: could not serialize the game for P%d\n", p + 1);
    }
    /* The game sat in an input wait (or the save failed): try again a bit later */
    join_reset();
    n.peer[p].retry_at = n.frame + JOIN_RETRY_FRAMES;
    say("JOIN P%d postponed: the game is busy, retrying in %u frames", p + 1, (unsigned)JOIN_RETRY_FRAMES);
    fprintf(stderr, "netplay: P%d is waiting to join (the game is busy; retrying)\n", p + 1);
}

/* ---- Client ---- */

static void client_send_input(void) {
    Pkt pk;
    pkt_begin(&pk, MSG_INPUT);
    put8(&pk, (uint32_t)n.me);
    put32(&pk, n.set_end);
    uint32_t first = n.set_end > n.local_start ? n.set_end : n.local_start;
    uint32_t cnt = n.local_end > first ? n.local_end - first : 0;
    if (cnt > MAX_SEND_INPUTS)
        cnt = MAX_SEND_INPUTS;
    put32(&pk, first);
    put8(&pk, cnt);
    for (uint32_t g = first; g < first + cnt; g++)
        put16(&pk, n.local[g % RING]);
    put_report(&pk, &n.my_report, n.have_report);
    send_pkt(&n.host_addr, &pk);
}

static void client_send_hello(void) {
    Pkt pk;
    pkt_begin(&pk, MSG_HELLO);
    put32(&pk, n.nonce);
    put32(&pk, state_dump_layout_id());
    send_pkt(&n.host_addr, &pk);
}

static void client_send_chunk_ack(void) {
    Pkt pk;
    pkt_begin(&pk, MSG_CHUNK_ACK);
    put32(&pk, n.nonce);
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
    case STOP_FULL:   return "the Session is full (4 Players)";
    case STOP_BUILD:  return "the Host runs a different build (both need the same game version and viewport)";
    default:          return "stopped by the Host";
    }
}

static void client_handle(int type, Rd *r, uint64_t t) {
    n.last_host_recv = t;
    switch (type) {
    case MSG_FRAMES: {
        uint32_t first = get32(r), cnt = get8(r);
        if (n.cstate != C_IN)
            return;
        for (uint32_t i = 0; i < cnt; i++) {
            FrameSet fs;
            for (int k = 0; k < PLATFORM_MAX_PLAYERS; k++)
                fs.pad[k] = (uint16_t)get16(r);
            fs.ev = (uint8_t)get8(r);
            fs.ev_player = (uint8_t)get8(r);
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
        uint32_t nonce = get32(r), total = get32(r), idx = get16(r), cnt = get16(r), len = get16(r);
        if (!r->ok || nonce != n.nonce || cnt == 0 || cnt > MAX_CHUNKS || idx >= cnt ||
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
    uint32_t magic = get32(&r), J = get32(&r);
    uint16_t pads[PLATFORM_MAX_PLAYERS], prev[PLATFORM_MAX_PLAYERS];
    for (int k = 0; k < PLATFORM_MAX_PLAYERS; k++)
        pads[k] = (uint16_t)get16(&r);
    for (int k = 0; k < PLATFORM_MAX_PLAYERS; k++)
        prev[k] = (uint16_t)get16(&r);
    uint32_t sram_len = get32(&r), state_len = get32(&r);
    if (!r.ok || magic != BLOB_MAGIC || r.pos + sram_len + state_len != n.blob_len)
        fatal(2, "the Host sent a malformed game state");
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

static void service(void) {
    uint8_t buf[PKT_MAX + 64];
    UdpAddr from;
    int len;
    uint64_t t = now_ms();
    while ((len = udp_recv(n.fd, &from, buf, sizeof buf)) >= 0) {
        if (len < 4 || buf[0] != 'E' || buf[1] != 'N' || buf[2] != PROTO_VERSION)
            continue;
        Rd r = { buf, (size_t)len, 4, true };
        if (n.host)
            host_handle(&from, buf[3], &r, t);
        else if (udp_addr_equal(&from, &n.host_addr))
            client_handle(buf[3], &r, t);
    }
    if (n.host) {
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
    } else if (t - n.last_host_recv > TIMEOUT_MS) {
        fatal(2, "lost the connection to the Host");
    }
}

static void apply_event(uint32_t f, const FrameSet *fs) {
    int p = fs->ev_player;
    switch (fs->ev) {
    case EV_CAPTURE:
        if (!host_request_root_call(capture_done))
            capture_done(false);
        break;
    case EV_JOIN:
        coop_join(p);
        say("JOIN P%d f=%u", p + 1, (unsigned)f);
        break;
    case EV_LEAVE:
        if (p == n.me)
            fatal(2, "%s", stop_reason(STOP_KICKED));
        coop_leave(p);
        say("LEAVE P%d f=%u", p + 1, (unsigned)f);
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
        udp_wait(n.fd, 2);
        service();
        hk->pump();
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

    /* This machine's pad, for frame f + D */
    uint32_t g = f + (uint32_t)n.delay;
    n.local[g % RING] = hk->sample_local();
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
        udp_wait(n.fd, 1);
        service();
        hk->pump();
        uint64_t t = now_ms();
        if (!n.host && t - last >= RESEND_MS) {
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
    if (!udp_init()) {
        fprintf(stderr, "netplay: socket init failed\n");
        return false;
    }
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
    n.delay = cfg->input_delay;
    if (n.delay < 1 || n.delay > MAX_DELAY) {
        fprintf(stderr, "--input-delay takes 1-%d\n", MAX_DELAY);
        return false;
    }

    if (cfg->host_port > 0) {
        n.fd = udp_open(cfg->host_port);
        if (n.fd < 0) {
            fprintf(stderr, "netplay: can't listen on UDP port %d (in use?)\n", cfg->host_port);
            return false;
        }
        n.host = true;
        n.me = 0;
        n.end_frame = cfg->end_frame;
        n.wait_players = cfg->wait_players > 1 ? cfg->wait_players : 0;
        n.local_start = 0;
        n.local_end = (uint32_t)n.delay; /* frames 0..D-1: nobody's input yet */
        n.active = true;
        say("HOST port=%d delay=%d", cfg->host_port, n.delay);
        fprintf(stderr, "netplay: hosting on UDP port %d (input delay %d)\n", cfg->host_port, n.delay);
        return true;
    }

    /* Client: "ADDR[:PORT]" */
    char host[256];
    snprintf(host, sizeof host, "%s", cfg->join);
    int port = NET_DEFAULT_PORT;
    char *colon = strrchr(host, ':');
    if (colon) {
        *colon = '\0';
        port = atoi(colon + 1);
    }
    if (port <= 0 || port > 65535 || !udp_resolve(host, port, &n.host_addr)) {
        fprintf(stderr, "netplay: can't resolve %s\n", cfg->join);
        return false;
    }
    n.fd = udp_open(0);
    if (n.fd < 0) {
        fprintf(stderr, "netplay: can't open a UDP socket\n");
        return false;
    }
    /* The Host owns the save: this machine's SRAM is a temp file for the Session */
    const char *tmp = getenv("TMPDIR");
    snprintf(n.save_path, sizeof n.save_path, "%s/earthbound-net-%d.srm", tmp && *tmp ? tmp : "/tmp", (int)getpid());
    remove(n.save_path);
    platform_save_set_path(n.save_path);

    n.nonce = (uint32_t)platform_timer_ticks() ^ ((uint32_t)getpid() << 16);
    uint64_t start = now_ms(), last = 0;
    for (;;) {
        uint64_t t = now_ms();
        if (t - start > CONNECT_MS) {
            fprintf(stderr, "netplay: no answer from %s\n", cfg->join);
            return false;
        }
        if (t - last >= HELLO_MS) {
            client_send_hello();
            last = t;
        }
        udp_wait(n.fd, 10);
        uint8_t buf[PKT_MAX + 64];
        UdpAddr from;
        int len;
        while ((len = udp_recv(n.fd, &from, buf, sizeof buf)) >= 0) {
            if (len < 4 || buf[0] != 'E' || buf[1] != 'N' || buf[2] != PROTO_VERSION ||
                !udp_addr_equal(&from, &n.host_addr))
                continue;
            Rd r = { buf, (size_t)len, 4, true };
            uint32_t nonce = get32(&r);
            if (buf[3] == MSG_WELCOME && nonce == n.nonce) {
                n.me = (int)get8(&r);
                n.delay = (int)get8(&r);
                if (!r.ok || n.me < 1 || n.me >= PLATFORM_MAX_PLAYERS || n.delay < 1 || n.delay > MAX_DELAY)
                    continue;
                n.cstate = C_WAIT_STATE;
                n.last_host_recv = now_ms();
                n.active = true;
                say("WELCOME P%d delay=%d", n.me + 1, n.delay);
                fprintf(stderr, "netplay: joined %s as P%d (input delay %d); waiting for the game\n", cfg->join,
                        n.me + 1, n.delay);
                return true;
            }
            if (buf[3] == MSG_REJECT && nonce == n.nonce) {
                fprintf(stderr, "netplay: %s\n", stop_reason((int)get8(&r)));
                return false;
            }
        }
    }
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
            udp_wait(n.fd, 5);
            uint8_t buf[PKT_MAX + 64];
            UdpAddr from;
            int len;
            uint64_t t = now_ms();
            while ((len = udp_recv(n.fd, &from, buf, sizeof buf)) >= 0) {
                if (len < 4 || buf[0] != 'E' || buf[1] != 'N' || buf[2] != PROTO_VERSION)
                    continue;
                Rd r = { buf, (size_t)len, 4, true };
                if (buf[3] == MSG_INPUT || buf[3] == MSG_BYE)
                    host_handle(&from, buf[3], &r, t);
            }
            for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++)
                if (n.peer[p].state == P_IN && n.peer[p].ack < n.set_end && t - n.peer[p].last_send >= RESEND_MS)
                    host_send_frames(p, t);
        }
    }
    if (n.host && !n.stopped) { /* after a STOP, a BYE could overtake it */
        for (int rep = 0; rep < 3; rep++)
            for (int p = 1; p < PLATFORM_MAX_PLAYERS; p++)
                if (n.peer[p].state != P_FREE)
                    send_bye(&n.peer[p].addr);
    } else if (!n.host) {
        for (int rep = 0; rep < 3; rep++)
            send_bye(&n.host_addr);
        remove(n.save_path);
        char tmp[sizeof n.save_path + 8];
        snprintf(tmp, sizeof tmp, "%s.tmp", n.save_path);
        remove(tmp);
    }
    udp_close(n.fd);
    n.fd = -1;
}

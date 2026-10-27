/* The relay WebSocket over libcurl, and invite parsing. See relay.h. */
#include "net/relay.h"

#include <ctype.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* ---- Invites (no libcurl needed) ---- */

static const char CODE_ALPHABET[] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

static bool starts_with(const char *s, const char *prefix) {
    return strncmp(s, prefix, strlen(prefix)) == 0;
}

bool relay_base(const char *relay, char *out, size_t cap) {
    while (*relay == ' ' || *relay == '\t')
        relay++;
    const char *scheme = "wss://";
    if (starts_with(relay, "wss://")) {
        relay += 6;
    } else if (starts_with(relay, "ws://")) {
        relay += 5;
        scheme = "ws://";
    } else if (starts_with(relay, "https://")) {
        relay += 8;
    } else if (starts_with(relay, "http://")) {
        relay += 7;
        scheme = "ws://";
    }
    size_t len = strlen(relay);
    while (len && (relay[len - 1] == '/' || isspace((unsigned char)relay[len - 1])))
        len--;
    if (!len)
        return false;
    snprintf(out, cap, "%s%.*s", scheme, (int)len, relay);
    return true;
}

bool relay_parse_invite(const char *invite, const char *fallback_relay, char *base, size_t cap,
                        char code[RELAY_CODE_LEN + 1]) {
    char s[512];
    snprintf(s, sizeof s, "%s", invite);
    size_t len = strlen(s);
    while (len && (s[len - 1] == '/' || isspace((unsigned char)s[len - 1])))
        s[--len] = '\0';
    char *slash = strrchr(s, '/');
    const char *tail = slash ? slash + 1 : s;
    while (*tail == ' ' || *tail == '\t')
        tail++;
    if (strlen(tail) != RELAY_CODE_LEN)
        return false;
    for (int i = 0; i < RELAY_CODE_LEN; i++) {
        char u = (char)toupper((unsigned char)tail[i]);
        if (!strchr(CODE_ALPHABET, u))
            return false;
        code[i] = u;
    }
    code[RELAY_CODE_LEN] = '\0';
    if (!slash)
        return fallback_relay && relay_base(fallback_relay, base, cap);
    *slash = '\0';
    /* A pasted join URL: "wss://x/join/CODE" */
    size_t blen = strlen(s);
    if (blen >= 5 && strcmp(s + blen - 5, "/join") == 0)
        s[blen - 5] = '\0';
    return relay_base(s, base, cap);
}

void relay_invite(const char *base, const char *code, char *out, size_t cap) {
    snprintf(out, cap, "%s/%s", starts_with(base, "wss://") ? base + 6 : base, code);
}

#ifdef EB_NET_RELAY

#include <curl/curl.h>

#ifdef _WIN32
#include <winsock2.h>
#else
#include <sys/select.h>
#endif

#define MSG_MAX 4096

static CURL *c;
static char lost[160];
static uint8_t msg[MSG_MAX];   /* the message being reassembled from frames */
static size_t msg_len;
static bool msg_drop;          /* it's bigger than MSG_MAX: read it to the end and drop it */

static void set_lost(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void set_lost(const char *fmt, ...) {
    if (lost[0])
        return; /* keep the first reason */
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(lost, sizeof lost, fmt, ap);
    va_end(ap);
}

/* libcurl's protocol list has "wss" (and "ws") only when built with WebSockets. */
static bool curl_has(const char *proto) {
    const curl_version_info_data *v = curl_version_info(CURLVERSION_NOW);
    for (const char *const *p = v->protocols; p && *p; p++)
        if (strcmp(*p, proto) == 0)
            return true;
    return false;
}

bool relay_supported(void) {
    return curl_has("wss");
}

static void wait_socket(bool write, int ms) {
    curl_socket_t fd = CURL_SOCKET_BAD;
    if (!c || curl_easy_getinfo(c, CURLINFO_ACTIVESOCKET, &fd) != CURLE_OK || fd == CURL_SOCKET_BAD)
        return;
    fd_set set;
    FD_ZERO(&set);
    FD_SET(fd, &set);
    struct timeval tv = { ms / 1000, (ms % 1000) * 1000 };
#ifdef _WIN32
    select(0, write ? NULL : &set, write ? &set : NULL, NULL, &tv); /* Winsock ignores nfds */
#else
    select(fd + 1, write ? NULL : &set, write ? &set : NULL, NULL, &tv);
#endif
}

bool relay_connect(const char *url, char *err, size_t cap) {
    static bool global;
    if (!global) {
        curl_global_init(CURL_GLOBAL_DEFAULT);
        global = true;
    }
    relay_close();
    lost[0] = '\0';
    msg_len = 0;
    msg_drop = false;
    if (!curl_has(starts_with(url, "ws://") ? "ws" : "wss")) {
        snprintf(err, cap, "this build's libcurl %s has no WebSocket support (8.14 or newer needed)",
                 curl_version_info(CURLVERSION_NOW)->version);
        return false;
    }
    c = curl_easy_init();
    if (!c) {
        snprintf(err, cap, "libcurl failed to start");
        return false;
    }
    curl_easy_setopt(c, CURLOPT_URL, url);
    curl_easy_setopt(c, CURLOPT_CONNECT_ONLY, 2L); /* the WebSocket upgrade, then hand the connection over */
    curl_easy_setopt(c, CURLOPT_CONNECTTIMEOUT_MS, 8000L);
    curl_easy_setopt(c, CURLOPT_TIMEOUT_MS, 10000L); /* the upgrade's answer too */
    curl_easy_setopt(c, CURLOPT_USERAGENT, "earthbound-coop");
    curl_easy_setopt(c, CURLOPT_NOSIGNAL, 1L);
    CURLcode rc = curl_easy_perform(c);
    curl_easy_setopt(c, CURLOPT_TIMEOUT_MS, 0L); /* the connection itself lasts the Session */
    long status = 0;
    curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &status);
    if (rc != CURLE_OK || (status && status != 101)) {
        if (status && status != 101)
            snprintf(err, cap, "the relay answered HTTP %ld%s", status,
                     status == 429 || status >= 500 ? " (a free Cloudflare relay may be over its daily limit)" : "");
        else
            snprintf(err, cap, "can't reach the relay: %s", curl_easy_strerror(rc));
        relay_close();
        return false;
    }
    return true;
}

bool relay_send(const void *buf, size_t n) {
    if (!c || lost[0])
        return false;
    const uint8_t *p = buf;
    size_t left = n;
    int waits = 0;
    while (left) {
        size_t sent = 0;
        /* A partial send continues the same frame: pass the rest on the next call.
         * CURLE_AGAIN may also have taken part of it. */
        CURLcode rc = curl_ws_send(c, p, left, &sent, 0, CURLWS_BINARY);
        if (rc == CURLE_OK || rc == CURLE_AGAIN) {
            p += sent < left ? sent : left;
            left -= sent < left ? sent : left;
        }
        if (rc == CURLE_OK)
            continue;
        if (rc == CURLE_AGAIN && waits++ < 200) { /* the socket buffer is full: up to ~2 s */
            wait_socket(true, 10);
            continue;
        }
        set_lost("lost the relay connection: %s", curl_easy_strerror(rc));
        return false;
    }
    return true;
}

/* The close frame's payload: a big-endian u16 status code, then the reason text. */
static void close_reason(const uint8_t *b, size_t n) {
    if (n > 2)
        set_lost("%.*s", (int)(n - 2), (const char *)b + 2);
    else
        set_lost("the relay closed the connection");
}

int relay_recv(void *buf, size_t cap, bool *text) {
    if (!c || lost[0])
        return -1;
    for (;;) {
        static uint8_t scratch[MSG_MAX];
        uint8_t *dst = msg_drop ? scratch : msg + msg_len;
        size_t room = msg_drop ? sizeof scratch : sizeof msg - msg_len;
        size_t got = 0;
        const struct curl_ws_frame *m = NULL;
        CURLcode rc = curl_ws_recv(c, dst, room, &got, &m);
        if (rc == CURLE_AGAIN)
            return -1;
        if (rc == CURLE_GOT_NOTHING) {
            set_lost("the relay closed the connection");
            return -1;
        }
        if (rc != CURLE_OK || !m) {
            set_lost("lost the relay connection: %s", curl_easy_strerror(rc));
            return -1;
        }
        if (m->flags & CURLWS_CLOSE) {
            close_reason(dst, got);
            return -1;
        }
        if (m->flags & (CURLWS_PING | CURLWS_PONG))
            continue; /* libcurl answers pings itself */
        if (!msg_drop) {
            msg_len += got;
            if (m->bytesleft > 0 && msg_len == sizeof msg)
                msg_drop = true; /* too big for any datagram: skip the rest */
        }
        if (m->bytesleft > 0 || (m->flags & CURLWS_CONT))
            continue; /* more of this message follows */
        bool dropped = msg_drop;
        size_t len = msg_len;
        msg_len = 0;
        msg_drop = false;
        if (dropped)
            continue;
        if (len > cap)
            len = cap;
        memcpy(buf, msg, len);
        *text = (m->flags & CURLWS_TEXT) != 0;
        return (int)len;
    }
}

void relay_wait(int ms) {
    wait_socket(false, ms);
}

const char *relay_lost(void) {
    return lost[0] ? lost : NULL;
}

void relay_close(void) {
    if (!c)
        return;
    if (!lost[0]) {
        size_t sent;
        curl_ws_send(c, "", 0, &sent, 0, CURLWS_CLOSE);
    }
    curl_easy_cleanup(c);
    c = NULL;
}

#else /* !EB_NET_RELAY */

bool relay_supported(void) {
    return false;
}

bool relay_connect(const char *url, char *err, size_t cap) {
    (void)url;
    snprintf(err, cap, "this build has no relay support (it needs libcurl 8.14+ with WebSockets at build time)");
    return false;
}

bool relay_send(const void *buf, size_t n) {
    (void)buf;
    (void)n;
    return false;
}

int relay_recv(void *buf, size_t cap, bool *text) {
    (void)buf;
    (void)cap;
    (void)text;
    return -1;
}

void relay_wait(int ms) {
    (void)ms;
}

const char *relay_lost(void) {
    return "no relay support";
}

void relay_close(void) {
}

#endif /* EB_NET_RELAY */

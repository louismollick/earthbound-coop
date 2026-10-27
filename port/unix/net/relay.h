#ifndef EB_NET_RELAY_H
#define EB_NET_RELAY_H

/*
 * The relay WebSocket (relay/README.md has the server and its protocol): one
 * connection to `wss://RELAY/host` or `wss://RELAY/join/CODE`, carrying one binary
 * message per netplay datagram. transport.c adds the seat framing; this file only
 * moves messages. Built on libcurl's WebSocket API (8.14+: earlier releases flag
 * message fragments differently) when EB_NET_RELAY is defined;
 * without it every call fails with "this build has no relay support".
 *
 * Also the invite helpers: an invite is "RELAY/CODE" (wss:// left out), the string
 * a Host hands out and a joiner pastes.
 */

#include <stdbool.h>
#include <stddef.h>

#define RELAY_CODE_LEN 6

/* Whether this build can reach a relay at all (the launcher hides online play otherwise). */
bool relay_supported(void);

/* Connect to `url` (ws:// or wss://). Blocks up to ~8 s. On failure, a reason in err. */
bool relay_connect(const char *url, char *err, size_t cap);
/* One binary message. False once the connection is lost. */
bool relay_send(const void *buf, size_t n);
/* One whole message into buf (truncated at cap), or -1 if none is waiting.
 * *text says whether it was a text message (relay control) or binary (a datagram). */
int relay_recv(void *buf, size_t cap, bool *text);
/* Wait up to `ms` for data to arrive. */
void relay_wait(int ms);
/* Why the connection ended (the relay's close reason, or the error), or NULL while it's up. */
const char *relay_lost(void);
void relay_close(void);

/* Normalize a relay address to a ws(s):// base without a trailing slash:
 * "x.workers.dev" and "https://x.workers.dev/" become "wss://x.workers.dev",
 * "http://127.0.0.1:8787" becomes "ws://127.0.0.1:8787". False if empty. */
bool relay_base(const char *relay, char *out, size_t cap);
/* Split an invite ("RELAY/CODE", a full ws(s)/http(s) URL ending in the code, or a
 * bare CODE with `fallback_relay`) into its relay base and upper-case code. */
bool relay_parse_invite(const char *invite, const char *fallback_relay, char *base, size_t cap,
                        char code[RELAY_CODE_LEN + 1]);
/* The invite for room `code` at relay `base`: "x.workers.dev/K7QF2M" (ws:// kept). */
void relay_invite(const char *base, const char *code, char *out, size_t cap);

#endif /* EB_NET_RELAY_H */

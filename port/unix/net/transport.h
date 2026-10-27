#ifndef EB_NET_TRANSPORT_H
#define EB_NET_TRANSPORT_H

/*
 * Where session.c's datagrams go: a UDP socket (--host PORT / --join ADDR) or a
 * relay WebSocket (--host-room / --join-room, relay.h). A peer is a NetAddr either
 * way: a UDP endpoint, or a relay seat (ip 0, port = seat; the Host is seat 0 to a
 * client). The relay keeps the Session's star: every client has its own seat, so
 * the Host still tells machines apart by address and session.c doesn't care which
 * transport it runs on, except that the relay is reliable (tp_reliable).
 */

#include <stdbool.h>
#include <stddef.h>

#include "net/relay.h"
#include "net/udp.h"

typedef UdpAddr NetAddr;

/* A UDP socket on `port` (0 = any free port). */
bool tp_open_udp(int port, char *err, size_t cap);
/* Host a room at relay `base` (relay_base): code receives the room's code. */
bool tp_open_relay_host(const char *base, char code[RELAY_CODE_LEN + 1], char *err, size_t cap);
/* Join room `code` at relay `base`; *host is the Host's address. */
bool tp_open_relay_join(const char *base, const char *code, NetAddr *host, char *err, size_t cap);
void tp_close(void);

/* The relay is TCP: nothing is lost or reordered, so resending only costs quota. */
bool tp_reliable(void);
bool tp_send(const NetAddr *to, const void *buf, size_t n);
/* One datagram into buf, or -1 if none is waiting. */
int tp_recv(NetAddr *from, void *buf, size_t cap);
/* Wait up to `ms` for a datagram to arrive. */
void tp_wait(int ms);
/* Relay only: why the relay connection ended, or NULL while it's up. */
const char *tp_lost(void);
const char *tp_addr_str(const NetAddr *a);

#endif /* EB_NET_TRANSPORT_H */

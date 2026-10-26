#ifndef EB_NET_UDP_H
#define EB_NET_UDP_H

/*
 * A thin non-blocking IPv4 UDP socket wrapper for netplay (session.c). Plain BSD
 * sockets; a Winsock port only needs the #ifdef _WIN32 branches in udp.c
 * (WSAStartup in udp_init, closesocket, ioctlsocket).
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint32_t ip;    /* network byte order */
    uint16_t port;  /* network byte order */
} UdpAddr;

bool udp_init(void);
/* Open a socket bound to `port` on every interface (0 = any free port). -1 on error. */
int udp_open(int port);
void udp_close(int fd);
/* Resolve "host" + port (DNS name or dotted quad). */
bool udp_resolve(const char *host, int port, UdpAddr *out);
bool udp_send(int fd, const UdpAddr *to, const void *buf, size_t n);
/* One datagram into buf, or -1 if none is waiting. */
int udp_recv(int fd, UdpAddr *from, void *buf, size_t cap);
/* Sleep `ms` milliseconds. */
void udp_sleep(int ms);
/* Wait up to `ms` milliseconds for a datagram to arrive. */
void udp_wait(int fd, int ms);
bool udp_addr_equal(const UdpAddr *a, const UdpAddr *b);
/* "a.b.c.d:port" in a static buffer. */
const char *udp_addr_str(const UdpAddr *a);

#endif /* EB_NET_UDP_H */

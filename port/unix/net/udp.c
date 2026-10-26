/* Non-blocking IPv4 UDP sockets for netplay. See udp.h. */
#include "net/udp.h"

#include <stdio.h>
#include <string.h>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
typedef int socklen_t;
_Static_assert(sizeof(SOCKET) == sizeof(UdpSocket) && INVALID_SOCKET == UDP_NO_SOCKET, "UdpSocket is SOCKET");
#else
#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

bool udp_init(void) {
#ifdef _WIN32
    WSADATA wsa;
    return WSAStartup(MAKEWORD(2, 2), &wsa) == 0;
#else
    return true;
#endif
}

UdpSocket udp_open(int port) {
    UdpSocket fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd == UDP_NO_SOCKET)
        return UDP_NO_SOCKET;
    struct sockaddr_in sa;
    memset(&sa, 0, sizeof sa);
    sa.sin_family = AF_INET;
    sa.sin_addr.s_addr = htonl(INADDR_ANY);
    sa.sin_port = htons((uint16_t)port);
    /* Room for a burst of join-transfer chunks */
    int buf = 1 << 20;
    setsockopt(fd, SOL_SOCKET, SO_RCVBUF, (const char *)&buf, sizeof buf);
    setsockopt(fd, SOL_SOCKET, SO_SNDBUF, (const char *)&buf, sizeof buf);
    if (bind(fd, (struct sockaddr *)&sa, sizeof sa) != 0) {
        udp_close(fd);
        return UDP_NO_SOCKET;
    }
#ifdef _WIN32
    u_long nb = 1;
    ioctlsocket(fd, FIONBIO, &nb);
#else
    fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) | O_NONBLOCK);
#endif
    return fd;
}

void udp_close(UdpSocket fd) {
    if (fd == UDP_NO_SOCKET)
        return;
#ifdef _WIN32
    closesocket(fd);
#else
    close(fd);
#endif
}

bool udp_resolve(const char *host, int port, UdpAddr *out) {
    struct addrinfo hints, *res = NULL;
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_DGRAM;
    if (getaddrinfo(host, NULL, &hints, &res) != 0 || !res)
        return false;
    out->ip = ((struct sockaddr_in *)res->ai_addr)->sin_addr.s_addr;
    out->port = htons((uint16_t)port);
    freeaddrinfo(res);
    return true;
}

bool udp_send(UdpSocket fd, const UdpAddr *to, const void *buf, size_t n) {
    struct sockaddr_in sa;
    memset(&sa, 0, sizeof sa);
    sa.sin_family = AF_INET;
    sa.sin_addr.s_addr = to->ip;
    sa.sin_port = to->port;
    return sendto(fd, (const char *)buf, (int)n, 0, (struct sockaddr *)&sa, sizeof sa) == (int)n;
}

int udp_recv(UdpSocket fd, UdpAddr *from, void *buf, size_t cap) {
    struct sockaddr_in sa;
    socklen_t len = sizeof sa;
    int n = (int)recvfrom(fd, (char *)buf, (int)cap, 0, (struct sockaddr *)&sa, &len);
    if (n < 0)
        return -1;
    from->ip = sa.sin_addr.s_addr;
    from->port = sa.sin_port;
    return n;
}

void udp_sleep(int ms) {
#ifdef _WIN32
    Sleep((DWORD)ms);
#else
    usleep((useconds_t)ms * 1000);
#endif
}

void udp_wait(UdpSocket fd, int ms) {
    fd_set set;
    FD_ZERO(&set);
    FD_SET(fd, &set);
    struct timeval tv = { ms / 1000, (ms % 1000) * 1000 };
#ifdef _WIN32
    select(0, &set, NULL, NULL, &tv); /* Winsock ignores nfds */
#else
    select(fd + 1, &set, NULL, NULL, &tv);
#endif
}

bool udp_addr_equal(const UdpAddr *a, const UdpAddr *b) {
    return a->ip == b->ip && a->port == b->port;
}

const char *udp_addr_str(const UdpAddr *a) {
    static char s[32];
    const uint8_t *ip = (const uint8_t *)&a->ip;
    snprintf(s, sizeof s, "%u.%u.%u.%u:%u", ip[0], ip[1], ip[2], ip[3], (unsigned)ntohs(a->port));
    return s;
}

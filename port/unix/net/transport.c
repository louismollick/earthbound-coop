/* UDP or relay datagrams behind one API. See transport.h. */
#include "net/transport.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define RELAY_MSG_MAX 2048 /* the relay drops bigger messages */

static enum { TP_NONE, TP_UDP, TP_RELAY_HOST, TP_RELAY_CLIENT } mode;
static UdpSocket fd = UDP_NO_SOCKET;

bool tp_open_udp(int port, char *err, size_t cap) {
    tp_close();
    if (!udp_init()) {
        snprintf(err, cap, "socket init failed");
        return false;
    }
    fd = udp_open(port);
    if (fd == UDP_NO_SOCKET) {
        if (port)
            snprintf(err, cap, "can't listen on UDP port %d (in use?)", port);
        else
            snprintf(err, cap, "can't open a UDP socket");
        return false;
    }
    mode = TP_UDP;
    return true;
}

bool tp_open_relay_host(const char *base, char code[RELAY_CODE_LEN + 1], char *err, size_t cap) {
    tp_close();
    char url[600];
    snprintf(url, sizeof url, "%s/host", base);
    if (!relay_connect(url, err, cap))
        return false;
    mode = TP_RELAY_HOST;
    /* The relay's first message names the room: "room CODE" */
    for (int waited = 0; waited < 10000; waited += 10) {
        char buf[64];
        bool text = false;
        int n = relay_recv(buf, sizeof buf - 1, &text);
        if (n < 0 && relay_lost())
            break;
        if (n < 0) {
            relay_wait(10);
            continue;
        }
        buf[n] = '\0';
        if (text && n == 5 + RELAY_CODE_LEN && strncmp(buf, "room ", 5) == 0) {
            memcpy(code, buf + 5, RELAY_CODE_LEN + 1);
            return true;
        }
    }
    snprintf(err, cap, "the relay didn't open a room%s%s", relay_lost() ? ": " : "", relay_lost() ? relay_lost() : "");
    tp_close();
    return false;
}

bool tp_open_relay_join(const char *base, const char *code, NetAddr *host, char *err, size_t cap) {
    tp_close();
    char url[600];
    snprintf(url, sizeof url, "%s/join/%s", base, code);
    if (!relay_connect(url, err, cap))
        return false;
    mode = TP_RELAY_CLIENT;
    memset(host, 0, sizeof *host);
    return true;
}

void tp_close(void) {
    if (mode == TP_UDP)
        udp_close(fd);
    else if (mode != TP_NONE)
        relay_close();
    fd = UDP_NO_SOCKET;
    mode = TP_NONE;
}

bool tp_reliable(void) {
    return mode == TP_RELAY_HOST || mode == TP_RELAY_CLIENT;
}

bool tp_send(const NetAddr *to, const void *buf, size_t n) {
    switch (mode) {
    case TP_UDP:
        return udp_send(fd, to, buf, n);
    case TP_RELAY_CLIENT:
        return relay_send(buf, n);
    case TP_RELAY_HOST: {
        /* To the relay: [seat][datagram] */
        uint8_t b[RELAY_MSG_MAX];
        if (n + 1 > sizeof b || to->port == 0 || to->port > 255)
            return false;
        b[0] = (uint8_t)to->port;
        memcpy(b + 1, buf, n);
        return relay_send(b, n + 1);
    }
    default:
        return false;
    }
}

int tp_recv(NetAddr *from, void *buf, size_t cap) {
    switch (mode) {
    case TP_UDP:
        return udp_recv(fd, from, buf, cap);
    case TP_RELAY_CLIENT:
    case TP_RELAY_HOST:
        for (;;) {
            uint8_t b[RELAY_MSG_MAX];
            bool text = false;
            int n = relay_recv(b, sizeof b, &text);
            if (n < 0)
                return -1;
            if (text)
                continue; /* relay control: nothing after "room CODE" yet */
            memset(from, 0, sizeof *from);
            const uint8_t *d = b;
            if (mode == TP_RELAY_HOST) { /* from the relay: [seat][datagram] */
                if (n < 1 || b[0] == 0)
                    continue;
                from->port = b[0];
                d++;
                n--;
            }
            if ((size_t)n > cap)
                n = (int)cap;
            memcpy(buf, d, (size_t)n);
            return n;
        }
    default:
        return -1;
    }
}

void tp_wait(int ms) {
    if (mode == TP_UDP)
        udp_wait(fd, ms);
    else if (mode != TP_NONE && !relay_lost())
        relay_wait(ms);
    else
        udp_sleep(ms);
}

const char *tp_lost(void) {
    return tp_reliable() ? relay_lost() : NULL;
}

const char *tp_addr_str(const NetAddr *a) {
    if (mode == TP_UDP)
        return udp_addr_str(a);
    static char s[32];
    snprintf(s, sizeof s, "relay seat %u", (unsigned)a->port);
    return s;
}

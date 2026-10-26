"""UDP proxy that puts a bad network between a netplay client and the Host.

Each :class:`Link` listens on a local port; the client sends there instead of to the
Host. Every datagram, in either direction, is delayed by ``latency`` +- ``jitter``
milliseconds (uniform) and dropped with probability ``loss``. Jitter reorders
packets: a datagram sent later can draw a shorter delay and overtake an earlier one.
All randomness comes from ``seed``, one stream per direction, so a run is
reproducible up to OS scheduling. One :class:`Proxy` thread serves every link.

    proxy = Proxy(seed=1)
    port = proxy.add_link(host_port=7744, latency=100, jitter=30, loss=0.02)
    proxy.start()            # the client joins 127.0.0.1:<port>
    ...
    proxy.link(port).blackhole = True   # drop everything (a pulled cable)
    proxy.stop(); print(proxy.stats())

Run standalone: ``python playtest/net/proxy.py --listen 7745 --host-port 7744 --latency 100``.
"""

import argparse
import heapq
import itertools
import random
import selectors
import socket
import threading
import time
from dataclasses import dataclass, field


@dataclass
class Link:
    """One client's path to the Host."""

    listen: socket.socket
    upstream: socket.socket
    host: tuple
    latency: float
    jitter: float
    loss: float
    rng_up: random.Random
    rng_down: random.Random
    client: tuple | None = None
    blackhole: bool = False
    sent: int = 0
    dropped: int = 0
    reordered: int = 0
    last_due: dict = field(default_factory=lambda: {"up": 0.0, "down": 0.0})


class Proxy:
    """A thread forwarding datagrams for any number of :class:`Link` s."""

    def __init__(self, seed=0):
        self.seed = seed
        self.links = {}
        self.sel = selectors.DefaultSelector()
        self.queue = []  # (due, seq, sock, data, addr, link)
        self.seq = itertools.count()
        self.lock = threading.Lock()
        self.running = False
        self.thread = None

    def add_link(self, host_port, latency=0.0, jitter=0.0, loss=0.0, host="127.0.0.1"):
        """Add a link to ``host:host_port``; returns the local port clients should join."""
        ls = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ls.bind(("127.0.0.1", 0))
        ls.setblocking(False)
        up = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        up.bind(("127.0.0.1", 0))
        up.setblocking(False)
        for s in (ls, up):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        n = len(self.links)
        link = Link(
            ls,
            up,
            (host, host_port),
            latency / 1000,
            jitter / 1000,
            loss,
            random.Random(f"{self.seed}-{n}-up"),  # noqa: S311 - simulated network, not crypto
            random.Random(f"{self.seed}-{n}-down"),  # noqa: S311
        )
        port = ls.getsockname()[1]
        with self.lock:
            self.links[port] = link
            self.sel.register(ls, selectors.EVENT_READ, (link, "up"))
            self.sel.register(up, selectors.EVENT_READ, (link, "down"))
        return port

    def link(self, port):
        return self.links[port]

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        for link in self.links.values():
            link.listen.close()
            link.upstream.close()

    def stats(self):
        """Packet counts per link: {local port: (forwarded, dropped, reordered)}."""
        return {p: (lk.sent, lk.dropped, lk.reordered) for p, lk in self.links.items()}

    def _schedule(self, link, direction, data, now):
        rng = link.rng_up if direction == "up" else link.rng_down
        if link.blackhole or rng.random() < link.loss:
            link.dropped += 1
            return
        delay = max(0.0, link.latency + rng.uniform(-link.jitter, link.jitter))
        due = now + delay
        if due < link.last_due[direction]:
            link.reordered += 1
        link.last_due[direction] = max(due, link.last_due[direction])
        if direction == "up":
            item = (due, next(self.seq), link.upstream, data, link.host, link)
        else:
            if link.client is None:
                return
            item = (due, next(self.seq), link.listen, data, link.client, link)
        heapq.heappush(self.queue, item)

    def _run(self):
        while self.running:
            now = time.monotonic()
            while self.queue and self.queue[0][0] <= now:
                _, _, sock, data, addr, link = heapq.heappop(self.queue)
                try:
                    sock.sendto(data, addr)
                    link.sent += 1
                except OSError:
                    pass
            timeout = 0.005
            if self.queue:
                timeout = max(0.0, min(timeout, self.queue[0][0] - now))
            with self.lock:
                events = self.sel.select(timeout)
            now = time.monotonic()
            for key, _ in events:
                link, direction = key.data
                while True:
                    try:
                        data, addr = key.fileobj.recvfrom(65536)
                    except (BlockingIOError, OSError):
                        break
                    if direction == "up":
                        link.client = addr
                    self._schedule(link, direction, data, now)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host-port", type=int, required=True)
    ap.add_argument("--latency", type=float, default=0, help="one-way delay per direction, ms")
    ap.add_argument("--jitter", type=float, default=0, help="+- ms, uniform")
    ap.add_argument("--loss", type=float, default=0, help="drop probability per datagram")
    ap.add_argument("--links", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    proxy = Proxy(seed=a.seed)
    ports = [proxy.add_link(a.host_port, a.latency, a.jitter, a.loss) for _ in range(a.links)]
    proxy.start()
    print("proxy ports:", " ".join(map(str, ports)), flush=True)
    try:
        while True:
            time.sleep(5)
            print(proxy.stats(), flush=True)
    except KeyboardInterrupt:
        proxy.stop()


if __name__ == "__main__":
    main()

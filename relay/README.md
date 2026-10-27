# earthbound-coop relay

A tiny WebSocket packet relay so a Host and friends can play online co-op without port forwarding. The Host opens a room with a 6-character code, and friends join it with the Host's invite. The relay forwards the game's small binary datagrams between them and never looks inside. Nothing is stored.

## Deploy to Cloudflare

[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/louismollick/earthbound-coop/tree/coop/relay)

Or from a terminal:

```
cd relay && npm install && npx wrangler login && npx wrangler deploy
```

You get a URL like `https://earthbound-coop-relay.<account>.workers.dev`. Paste it into the game's Host online screen (the game remembers it). The game then copies an invite like `earthbound-coop-relay.<account>.workers.dev/K7QF2M` to the clipboard: send that to your friends, who paste it into Join online. Only the Host needs the relay URL.

### Free plan limits

Rooms are Durable Objects (SQLite backed, so the free plan works). The free plan allows 100,000 requests per day. Incoming WebSocket messages count 1 request per 20 messages, outgoing messages are free. At about 60 packets per second per direction per Player that is roughly 4.5 hours per day with 2 Players and 1.5 hours per day with 4. Workers Paid ($5/month) removes the concern.

## Self-hosting on a VPS

Needs Node 24 (runs the TypeScript directly).

```
cd relay
npm ci
node node/server.ts --port 8787 --listen 127.0.0.1
```

It prints `relay listening on 127.0.0.1:8787`. Put Caddy in front for TLS (`wss://`):

```
relay.example.com {
	reverse_proxy 127.0.0.1:8787
}
```

systemd unit, `/etc/systemd/system/earthbound-relay.service`:

```
[Unit]
Description=earthbound-coop relay
After=network.target

[Service]
WorkingDirectory=/opt/earthbound-coop/relay
ExecStart=/usr/bin/node node/server.ts --port 8787 --listen 127.0.0.1
Restart=always
User=nobody

[Install]
WantedBy=multi-user.target
```

Then `systemctl enable --now earthbound-relay`. Players paste `https://relay.example.com` into the game.

## Protocol

Peers connect with WebSocket. Frames over 2048 bytes and text frames from peers are dropped.

| Request | Meaning |
| --- | --- |
| `GET /` | 200, `earthbound-coop relay` |
| `GET /host` | Create a room. First message is the text `room CODE`. |
| `GET /join/CODE` | Join a room (case-insensitive). |

- Host to relay: binary `[seat u8][datagram]`, forwarded without the seat byte to the client in that seat. Dropped if there is no such client.
- Relay to Host: binary `[seat u8][datagram]` for every client datagram.
- Client to relay: binary datagram. Relay to client: binary datagram, no prefix.
- Seats are 1 to 255, assigned in increasing order per room, never reused right away.
- Close codes: `4004 no such room`, `4009 room full` (7 clients max), `4000 host left` (sent to every client when the Host disconnects; the code is then free).
- Codes use the alphabet `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`.

## Development

```
npm run typecheck
npm test                                  # against the Node server
npm run dev                               # wrangler dev on :8787
RELAY_URL=ws://127.0.0.1:8787 npm test    # same tests against wrangler dev
```

`EB_RELAY_TEST_DELAY_MS=40` makes the Node server delay every forwarded message, to simulate latency in tests.

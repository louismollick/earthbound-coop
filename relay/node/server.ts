// Self-hosted relay, same protocol as src/worker.ts. Rooms live in memory.
//   node node/server.ts --port 8787 --listen 127.0.0.1
// EB_RELAY_TEST_DELAY_MS delays every forwarded message (tests only).
import { createServer } from "node:http";
import { parseArgs } from "node:util";
import type { Socket } from "node:net";
import WebSocket, { WebSocketServer } from "ws";
import {
  CLOSE_HOST_LEFT,
  CLOSE_NO_SUCH_ROOM,
  CLOSE_ROOM_FULL,
  MAX_CLIENTS,
  MAX_DATAGRAM,
  makeCode,
  nextFreeSeat,
  normalizeCode,
} from "../src/protocol.ts";

interface Room {
  host: WebSocket;
  clients: Map<number, WebSocket>;
  lastSeat: number;
}

const { values: args } = parseArgs({
  options: { port: { type: "string", default: "8787" }, listen: { type: "string", default: "127.0.0.1" } },
});
const delayMs = Number(process.env.EB_RELAY_TEST_DELAY_MS ?? 0);

const rooms = new Map<string, Room>();
/** A peer that stops reading is cut off once this much is queued for it (the Session can't skip packets). */
const MAX_BUFFERED = 1 << 20;
const wss = new WebSocketServer({ noServer: true, maxPayload: 1 << 20 });

/** Sends after the test delay; equal timers fire in order, so ordering is preserved. */
function forward(to: WebSocket, data: Uint8Array): void {
  const send = () => {
    if (to.readyState !== WebSocket.OPEN) return;
    if (to.bufferedAmount > MAX_BUFFERED) to.terminate();
    else to.send(data);
  };
  if (delayMs > 0) setTimeout(send, delayMs);
  else send();
}

function attachHost(ws: WebSocket): void {
  let code = makeCode();
  while (rooms.has(code)) code = makeCode();
  const room: Room = { host: ws, clients: new Map(), lastSeat: 0 };
  rooms.set(code, room);
  ws.send(`room ${code}`);

  ws.on("message", (raw: Buffer, isBinary: boolean) => {
    if (!isBinary || raw.length < 1 || raw.length > MAX_DATAGRAM) return;
    const target = room.clients.get(raw[0]);
    if (target) forward(target, raw.subarray(1));
  });
  ws.on("close", () => {
    rooms.delete(code);
    for (const c of room.clients.values()) c.close(CLOSE_HOST_LEFT, "host left");
    room.clients.clear();
  });
  ws.on("error", () => ws.terminate());
}

function attachClient(ws: WebSocket, code: string | null): void {
  const room = code ? rooms.get(code) : undefined;
  ws.on("error", () => ws.terminate());
  if (!room) return ws.close(CLOSE_NO_SUCH_ROOM, "no such room");
  const seat = room.clients.size < MAX_CLIENTS ? nextFreeSeat(room.lastSeat, (s) => room.clients.has(s)) : null;
  if (seat === null) return ws.close(CLOSE_ROOM_FULL, "room full");
  room.lastSeat = seat;
  room.clients.set(seat, ws);

  ws.on("message", (raw: Buffer, isBinary: boolean) => {
    if (!isBinary || raw.length > MAX_DATAGRAM) return;
    forward(room.host, Buffer.concat([Buffer.from([seat]), raw]));
  });
  ws.on("close", () => {
    if (room.clients.get(seat) === ws) room.clients.delete(seat);
  });
}

/** The request's path, or null for a target URL can't parse (it would throw). */
function pathOf(url: string | undefined): string | null {
  try {
    return new URL(url ?? "/", "http://x").pathname;
  } catch {
    return null;
  }
}

const server = createServer((req, res) => {
  const path = pathOf(req.url);
  if (path === null) {
    res.writeHead(400).end("bad request");
  } else if (path === "/") {
    res.writeHead(200, { "content-type": "text/plain" }).end("earthbound-coop relay");
  } else if (path === "/host" || path.startsWith("/join/")) {
    res.writeHead(426, { "content-type": "text/plain" }).end("upgrade required");
  } else {
    res.writeHead(404).end("not found");
  }
});

server.on("upgrade", (req, socket, head) => {
  const path = pathOf(req.url) ?? "";
  const join = /^\/join\/([^/]*)$/.exec(path);
  if (path !== "/host" && !join) {
    socket.end("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n");
    return;
  }
  (socket as Socket).setNoDelay(true);
  wss.handleUpgrade(req, socket, head, (ws) => {
    if (join) attachClient(ws, normalizeCode(join[1]));
    else attachHost(ws);
  });
});

function shutdown(): void {
  for (const ws of wss.clients) ws.terminate();
  server.close(() => process.exit(0));
  server.closeAllConnections();
}
process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);

server.listen(Number(args.port), args.listen, () => {
  const addr = server.address();
  const port = typeof addr === "object" && addr ? addr.port : args.port;
  console.log(`relay listening on ${args.listen}:${port}`);
});

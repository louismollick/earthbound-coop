import { DurableObject } from "cloudflare:workers";
import {
  CLOSE_HOST_LEFT,
  CLOSE_NO_SUCH_ROOM,
  CLOSE_ROOM_FULL,
  MAX_CLIENTS,
  MAX_DATAGRAM,
  makeCode,
  nextFreeSeat,
  normalizeCode,
} from "./protocol.ts";

interface Env {
  ROOMS: DurableObjectNamespace<Room>;
}

// Per-socket state, kept in the hibernation attachment (survives eviction).
// The host's `lastSeat` is the room's seat counter.
type Attachment = { role: "host"; lastSeat: number } | { role: "client"; seat: number };

const isUpgrade = (req: Request) => req.headers.get("Upgrade")?.toLowerCase() === "websocket";

/** Accepts the upgrade, then closes straight away with an application close code. */
function rejectSocket(code: number, reason: string): Response {
  const [client, server] = Object.values(new WebSocketPair());
  server.accept();
  server.close(code, reason);
  return new Response(null, { status: 101, webSocket: client });
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const path = new URL(req.url).pathname;
    if (path === "/") return new Response("earthbound-coop relay");

    const join = /^\/join\/([^/]*)$/.exec(path);
    if (path !== "/host" && !join) return new Response("not found", { status: 404 });
    if (!isUpgrade(req)) return new Response("upgrade required", { status: 426 });

    if (join) {
      const code = normalizeCode(join[1]);
      if (!code) return rejectSocket(CLOSE_NO_SUCH_ROOM, "no such room");
      return env.ROOMS.get(env.ROOMS.idFromName(code)).fetch(roomRequest(req, "client", code));
    }

    for (let tries = 0; tries < 8; tries++) {
      const code = makeCode();
      const res = await env.ROOMS.get(env.ROOMS.idFromName(code)).fetch(roomRequest(req, "host", code));
      if (res.status !== 409) return res;
    }
    return new Response("no free room code", { status: 503 });
  },
} satisfies ExportedHandler<Env>;

function roomRequest(req: Request, role: "host" | "client", code: string): Request {
  const fwd = new Request(req);
  fwd.headers.set("x-room-role", role);
  fwd.headers.set("x-room-code", code);
  return fwd;
}

/** One room: a host socket (tag "host") and clients (tags "client", "s<seat>"). */
export class Room extends DurableObject<Env> {
  override async fetch(req: Request): Promise<Response> {
    const code = req.headers.get("x-room-code") ?? "";
    const host = this.ctx.getWebSockets("host")[0];

    if (req.headers.get("x-room-role") === "host") {
      if (host) return new Response("room exists", { status: 409 });
      const [client, server] = Object.values(new WebSocketPair());
      this.ctx.acceptWebSocket(server, ["host"]);
      server.serializeAttachment({ role: "host", lastSeat: 0 } satisfies Attachment);
      server.send(`room ${code}`);
      return new Response(null, { status: 101, webSocket: client });
    }

    if (!host) return rejectSocket(CLOSE_NO_SUCH_ROOM, "no such room");
    if (this.ctx.getWebSockets("client").length >= MAX_CLIENTS) return rejectSocket(CLOSE_ROOM_FULL, "room full");

    const hostAtt = host.deserializeAttachment() as Attachment & { role: "host" };
    const seat = nextFreeSeat(hostAtt.lastSeat, (s) => this.ctx.getWebSockets(`s${s}`).length > 0);
    if (seat === null) return rejectSocket(CLOSE_ROOM_FULL, "room full");
    host.serializeAttachment({ role: "host", lastSeat: seat } satisfies Attachment);

    const [client, server] = Object.values(new WebSocketPair());
    this.ctx.acceptWebSocket(server, ["client", `s${seat}`]);
    server.serializeAttachment({ role: "client", seat } satisfies Attachment);
    return new Response(null, { status: 101, webSocket: client });
  }

  override webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): void {
    if (typeof message === "string" || message.byteLength > MAX_DATAGRAM) return;
    const att = ws.deserializeAttachment() as Attachment;
    const data = new Uint8Array(message);

    if (att.role === "host") {
      if (data.length === 0) return;
      this.trySend(this.ctx.getWebSockets(`s${data[0]}`)[0], data.subarray(1));
    } else {
      const out = new Uint8Array(data.length + 1);
      out[0] = att.seat;
      out.set(data, 1);
      this.trySend(this.ctx.getWebSockets("host")[0], out);
    }
  }

  override webSocketClose(ws: WebSocket): void {
    this.onGone(ws);
    // Complete the close handshake; the peer's code (1005/1006) may not be sendable.
    try {
      ws.close(1000, "bye");
    } catch {}
  }

  override webSocketError(ws: WebSocket): void {
    this.onGone(ws);
  }

  private onGone(ws: WebSocket): void {
    const att = ws.deserializeAttachment() as Attachment | null;
    if (att?.role !== "host") return;
    for (const c of this.ctx.getWebSockets("client")) {
      try {
        c.close(CLOSE_HOST_LEFT, "host left");
      } catch {}
    }
  }

  private trySend(ws: WebSocket | undefined, data: Uint8Array): void {
    try {
      ws?.send(data);
    } catch {}
  }
}

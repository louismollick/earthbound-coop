// Runs against the Node server (spawned on a free port), or against any running
// relay when RELAY_URL is set, e.g. `npx wrangler dev` on ws://127.0.0.1:8787.
import { spawn } from "node:child_process";
import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import WebSocket from "ws";

let base = process.env.RELAY_URL ?? "";
let child: ReturnType<typeof spawn> | undefined;

before(async () => {
  if (base) return;
  child = spawn(process.execPath, ["node/server.ts", "--port", "0"], { stdio: ["ignore", "pipe", "inherit"] });
  base = await new Promise<string>((resolve, reject) => {
    child!.once("exit", (code) => reject(new Error(`server exited early (${code})`)));
    child!.stdout!.on("data", (d: Buffer) => {
      const m = /relay listening on (\S+):(\d+)/.exec(d.toString());
      if (m) resolve(`ws://${m[1]}:${m[2]}`);
    });
  });
});

after(() => {
  child?.kill("SIGTERM");
});

type Msg = { data: Buffer; isBinary: boolean };

/** A connected socket with an awaitable message queue and close info. */
class Peer {
  ws: WebSocket;
  queue: Msg[] = [];
  closed?: { code: number; reason: string };
  private wake?: () => void;

  constructor(path: string) {
    this.ws = new WebSocket(base + path);
    this.ws.on("message", (data: Buffer, isBinary: boolean) => {
      this.queue.push({ data, isBinary });
      this.wake?.();
    });
    this.ws.on("close", (code: number, reason: Buffer) => {
      this.closed = { code, reason: reason.toString() };
      this.wake?.();
    });
    this.ws.on("error", () => {});
  }

  /** Resolves once the upgrade finished (or the socket already closed). */
  ready = () =>
    this.ws.readyState !== WebSocket.CONNECTING
      ? Promise.resolve(this)
      : new Promise<this>((r) => {
          this.ws.once("open", () => r(this));
          this.ws.once("close", () => r(this));
        });

  private async until<T>(pick: () => T | undefined, what: string): Promise<T> {
    const deadline = Date.now() + 5000;
    for (;;) {
      const v = pick();
      if (v !== undefined) return v;
      if (Date.now() > deadline) throw new Error(`timeout waiting for ${what}`);
      await new Promise<void>((r) => {
        this.wake = r;
        setTimeout(r, 50);
      });
    }
  }

  next = () => this.until(() => this.queue.shift(), "message");
  waitClosed = () => this.until(() => this.closed, "close");
  /** Asserts nothing else arrives within a short window. */
  async expectQuiet(ms = 300) {
    await new Promise((r) => setTimeout(r, ms));
    assert.equal(this.queue.length, 0, "unexpected message");
    assert.equal(this.closed, undefined, "unexpectedly closed");
  }
  send(...bytes: number[]) {
    this.ws.send(Buffer.from(bytes));
  }
  close() {
    this.ws.close();
  }
}

const connect = (path: string) => new Peer(path).ready();

async function openRoom() {
  const host = await connect("/host");
  const first = await host.next();
  assert.equal(first.isBinary, false);
  const m = /^room ([A-HJ-NP-Z2-9]{6})$/.exec(first.data.toString());
  assert.ok(m, `bad room message: ${first.data}`);
  return { host, code: m[1] };
}

test("GET / answers with the relay banner", async () => {
  const res = await fetch(base.replace(/^ws/, "http") + "/");
  assert.equal(res.status, 200);
  assert.equal(await res.text(), "earthbound-coop relay");
});

test("host/join without an upgrade is 426", async () => {
  for (const p of ["/host", "/join/ABCDEF"]) {
    const res = await fetch(base.replace(/^ws/, "http") + p);
    assert.equal(res.status, 426);
  }
});

test("client datagrams reach the host with a seat prefix; lowercase code works", async () => {
  const { host, code } = await openRoom();
  const a = await connect(`/join/${code}`);
  a.send(1, 2, 3);
  const m = await host.next();
  assert.ok(m.isBinary);
  assert.deepEqual([...m.data], [1, 1, 2, 3]);

  const b = await connect(`/join/${code.toLowerCase()}`);
  b.send(9);
  const mb = await host.next();
  assert.notEqual(mb.data[0], 1);
  assert.deepEqual([...mb.data.subarray(1)], [9]);
  for (const p of [host, a, b]) p.close();
});

test("host datagrams are routed by seat and the prefix is stripped", async () => {
  const { host, code } = await openRoom();
  const a = await connect(`/join/${code}`);
  const b = await connect(`/join/${code}`);
  a.send(0xa);
  b.send(0xb);
  // Arrival order can differ from connection order; tell clients apart by payload.
  const first = await host.next();
  const second = await host.next();
  const seatA = (first.data[1] === 0xa ? first : second).data[0];
  const seatB = (first.data[1] === 0xa ? second : first).data[0];
  assert.notEqual(seatA, seatB);

  host.send(seatA, 0xaa, 0xbb);
  host.send(seatB, 0xcc);
  const ma = await a.next();
  assert.ok(ma.isBinary);
  assert.deepEqual([...ma.data], [0xaa, 0xbb]);
  assert.deepEqual([...(await b.next()).data], [0xcc]);
  for (const p of [host, a, b]) p.close();
});

test("two clients get different seats", async () => {
  const { host, code } = await openRoom();
  const a = await connect(`/join/${code}`);
  const b = await connect(`/join/${code}`);
  a.send(1);
  b.send(2);
  const s1 = (await host.next()).data[0];
  const s2 = (await host.next()).data[0];
  assert.ok(s1 >= 1 && s2 >= 1 && s1 !== s2);
  for (const p of [host, a, b]) p.close();
});

test("unknown or malformed room closes with 4004", async () => {
  for (const code of ["ZZZZZZ", "abc", "ABCDE0", "ABCDEFG"]) {
    const c = await connect(`/join/${code}`);
    assert.deepEqual(await c.waitClosed(), { code: 4004, reason: "no such room" });
  }
});

test("room full closes with 4009", async () => {
  const { host, code } = await openRoom();
  const clients = await Promise.all(Array.from({ length: 7 }, () => connect(`/join/${code}`)));
  for (const c of clients) c.send(0);
  for (let i = 0; i < 7; i++) await host.next();
  const extra = await connect(`/join/${code}`);
  assert.deepEqual(await extra.waitClosed(), { code: 4009, reason: "room full" });
  for (const p of [host, ...clients]) p.close();
});

test("host disconnect closes clients with 4000 and frees the code", async () => {
  const { host, code } = await openRoom();
  const a = await connect(`/join/${code}`);
  const b = await connect(`/join/${code}`);
  a.send(0);
  b.send(0);
  await host.next();
  await host.next();
  host.close();
  assert.deepEqual(await a.waitClosed(), { code: 4000, reason: "host left" });
  assert.deepEqual(await b.waitClosed(), { code: 4000, reason: "host left" });
  const late = await connect(`/join/${code}`);
  assert.equal((await late.waitClosed()).code, 4004);
});

test("client leaving sends nothing to the host and the seat is not reused", async () => {
  const { host, code } = await openRoom();
  const a = await connect(`/join/${code}`);
  a.send(0);
  const seatA = (await host.next()).data[0];
  a.close();
  await a.waitClosed();
  await host.expectQuiet();
  const b = await connect(`/join/${code}`);
  b.send(0);
  assert.notEqual((await host.next()).data[0], seatA);
  host.close();
  b.close();
});

test("missing seats, empty frames, text and oversized frames are dropped quietly", async () => {
  const { host, code } = await openRoom();
  const a = await connect(`/join/${code}`);
  a.send(0);
  const seat = (await host.next()).data[0];

  host.send(200, 1, 2, 3); // no such seat
  host.ws.send(Buffer.alloc(0)); // empty
  host.ws.send("hello"); // text
  host.ws.send(Buffer.alloc(2049, seat)); // oversized
  a.ws.send("hello");
  a.ws.send(Buffer.alloc(2049));
  await new Promise((r) => setTimeout(r, 200));

  host.send(seat, 7);
  const m = await a.next();
  assert.deepEqual([...m.data], [7]);
  await a.expectQuiet();
  await host.expectQuiet();
  host.close();
  a.close();
});

test("max-size datagram passes both ways", async () => {
  const { host, code } = await openRoom();
  const a = await connect(`/join/${code}`);
  a.ws.send(Buffer.alloc(2048, 5));
  const up = await host.next();
  assert.equal(up.data.length, 2049);
  host.ws.send(Buffer.concat([Buffer.from([up.data[0]]), Buffer.alloc(2047, 6)]));
  assert.equal((await a.next()).data.length, 2047);
  host.close();
  a.close();
});

// Wire protocol shared by the Cloudflare Worker and the Node server.
//
//   GET /host        (WebSocket) create a room. First message: text "room CODE".
//                    host -> relay: binary [seat u8][datagram]; relay -> host: same.
//   GET /join/CODE   (WebSocket) join a room. Binary frames are bare datagrams;
//                    the relay adds/strips the seat byte on the host side.
//
// The relay never parses datagrams.

export const CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
export const CODE_LENGTH = 6;
export const MAX_CLIENTS = 7;
export const MAX_DATAGRAM = 2048;

export const CLOSE_HOST_LEFT = 4000;
export const CLOSE_NO_SUCH_ROOM = 4004;
export const CLOSE_ROOM_FULL = 4009;

/** Crypto-random room code. */
export function makeCode(): string {
  const bytes = new Uint8Array(CODE_LENGTH);
  crypto.getRandomValues(bytes);
  // 256 % 32 == 0, so the modulo is unbiased.
  return Array.from(bytes, (b) => CODE_ALPHABET[b % CODE_ALPHABET.length]).join("");
}

/** Decodes, uppercases and validates a code from a URL path segment; null if it can't be a room. */
export function normalizeCode(segment: string): string | null {
  let code: string;
  try {
    code = decodeURIComponent(segment).toUpperCase();
  } catch {
    return null;
  }
  return code.length === CODE_LENGTH && [...code].every((c) => CODE_ALPHABET.includes(c)) ? code : null;
}

/** Next seat after `last` in 1..255, skipping seats `inUse` reports taken. Null if all 255 are taken. */
export function nextFreeSeat(last: number, inUse: (seat: number) => boolean): number | null {
  let seat = last;
  for (let i = 0; i < 255; i++) {
    seat = seat >= 255 ? 1 : seat + 1;
    if (!inUse(seat)) return seat;
  }
  return null;
}

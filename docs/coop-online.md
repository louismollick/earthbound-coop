# Online co-op

Up to four Players share one game over the internet. Every machine runs the same game in lockstep, and only controller input crosses the network (ADR 0002). The Host owns the save file. A joining Player gets the Host's game state when they connect.

Everyone needs the same build: the same commit, the same CMake options (the viewport especially) and the US ROM. See [Limitations](#limitations).

## Through a relay (easiest)

A relay is a small server that passes the game's packets between the Host and everyone else. Nobody opens a port or changes a router. One person deploys it once, for free, on Cloudflare: see [`relay/README.md`](../relay/README.md).

Start the game in a window with no options. A launcher comes up before the game:

- **Play** starts the game as usual.
- **Host online** asks for the relay's URL (paste it with Ctrl+V, or Cmd+V on a Mac). The game remembers it. Enter opens a room, and the invite (for example `earthbound-coop-relay.you.workers.dev/K7QF2M`) goes to the clipboard. Send it to your friends. The room code stays in the top-left corner until someone joins.
- **Join online** asks for the invite. If you copied one, it's already filled in, otherwise it's the last one you used. Enter joins.

If something goes wrong (a wrong URL, a closed room, a different build), the launcher says why and you can try again. The relay and the last invite are kept in `online.cfg` in the working directory.

The same from the command line:

```
earthbound --host-room --relay earthbound-coop-relay.you.workers.dev
earthbound --join-room earthbound-coop-relay.you.workers.dev/K7QF2M
```

`--relay` is remembered in `online.cfg` like the launcher's, so later `--host-room` needs no URL. `--launcher` shows the launcher even with other options (tests use it headless).

The relay needs libcurl 8.14 or newer at build time (on a Mac, `brew install curl`; macOS's own libcurl can't do WebSockets). CMake prints `Relay support: libcurl ...` when it's found. A build without it has no launcher and only the direct connections below.

The relay runs over TCP, so a lost packet holds up the ones behind it until it's resent. On a bad Wi-Fi link that shows as an occasional hitch of a few frames. A free Cloudflare relay also has a daily limit (about 4.5 hours of 2-Player play a day): see the relay's README.

## Direct connection

The Host's UDP port must be reachable from every client: see [Networking](#networking).

### Host

```
port/unix/build/earthbound --host 7744
```

7744 is the default port; any free UDP port works. Players join and leave while the game runs. The Host is P1.

### Join

```
port/unix/build/earthbound --join 100.101.102.103:7744
```

The port defaults to 7744 when left out. Clients get P2 to P4 in the order they connect. A joining machine waits with a still window until the Host's game arrives. Then everyone pauses for a moment while the joiner loads, and the game carries on with the new Player in it.

The joiner's keyboard (or first controller) drives its Player. If the Host is in a text box or menu that waits for a button, the join waits too. It retries every two seconds and prints `JOIN ... postponed` until the game reaches a safe point.

## Several Players on one machine

`--local-players N` puts N Players on one machine. Their pads come in local order: the keyboard (arrows, X/Z) or the first controller first, then the IJKL layout or the second controller, then the third and fourth controllers.

- The Host takes P1 to PN.
- A client gets the next N free Players. If there aren't N free, the client is turned away.

```
earthbound --host 7744 --local-players 2              # P1 and P2 at the Host
earthbound --join host.example:7744                    # this machine is P3
```

## Input delay

The input delay is how many frames late each button press takes effect. Every machine waits for the Host's confirmed input, so a client's press makes a full round trip before it can take effect. Too low a delay makes the game stutter, because machines wait for input. Too high a delay makes the controls feel heavy.

By default the Host sets it from the pings: before each join it measures the joiner's round trip and sets the delay to cover the slowest machine in the Session (`ping / 16.7 + 1` frames, at least 3, at most 20). When a machine leaves, the delay drops back to what the others need. For example, a 50 ms ping gives 4 and a 120 ms ping gives 9.

`--input-delay N` (Host only; clients use the Host's value) fixes it instead. 3 (50 ms) suits a LAN.

## Status overlay

In a Session, the top-left corner shows the room code while nobody has joined, and a line when a Player joins or leaves. F4 adds each Player's ping and the current input delay (on a client, its own ping). The overlay is drawn over the game's picture, not into the game, so it never affects the game state.

## Networking

A direct connection has no matchmaking and no NAT traversal. The Host's UDP port must be reachable from every client (or use [a relay](#through-a-relay-easiest)):

- **Tailscale** (easiest): install it on every machine and join with the Host's Tailscale IP (`100.x.y.z`). Nothing needs to be opened on the router.
- **Port forwarding:** forward UDP port 7744 on the Host's router to the Host's machine, then join with the Host's public IP.
- **A Windows Host** also has to let the game through Windows Defender Firewall: allow it at the prompt the first `--host` shows, or see `docs/coop-windows.md`.

IPv4 only.

## Disconnects

- **A Player's connection drops:** everyone freezes. After 10 seconds without packets, the Host removes that Player and the game continues. To come back, they start the game again with `--join`. That is a fresh join, and they usually get the same Player number back.
- **A Player restarts their game while still connected** (a crash, or a quit the Host never heard about): the Host never lets a new connection replace an open one. If the restarted game reaches the Host from the same address and port as before (for example through the same NAT mapping), it prints `waiting for it to time out` and waits up to 10 seconds, until the Host drops the old connection. Then it joins as usual.
- **A Player quits normally:** they leave immediately.
- **The Host quits or disappears:** every client stops with `the Host ended the Session` or `lost the connection to the Host`. In a window, a message box says so before the game closes.
- **The Host loses the relay:** the Host plays on alone (`RELAY LOST` in the corner). The others time out after 10 seconds, and nobody can join until the Host starts a new room.

## Desyncs

Every 60 frames, each machine hashes its game state, one hash per section of the savestate. The Host compares the hashes. If any machine disagrees, the Session stops on every machine with a message like:

    netplay: desync at frame 4500: P1 and P2 disagree on RNG, OVERWORLD (dumps: desync-4500-P*.state/.txt)

Each machine writes these files to its working directory:

- `desync-<frame>-P<n>.state`: the raw state at that frame.
- `desync-<frame>-P<n>.txt`: one line per section with its size and hash. The sections that differ are marked `DIFFERS`.

To see where two dumps differ:

    python playtest/net/desync_diff.py desync-4500-P1.state desync-4500-P2.state

A desync is a bug, usually game state that lives outside the savestate. Please send the dumps from both machines.

## Limitations

- Every machine needs a compatible build. When a client connects, it sends a fingerprint of its build, and the Host turns away any difference with a message that names it, for example `viewport: Host 320x240, this machine 256x224`. The fingerprint covers:
  - the viewport size (`EB_VIEWPORT_WIDTH`/`HEIGHT`);
  - the build options that change game logic: audio, ROM verification, the battle letterbox and B-opens-menu (the smooth camera and frame skip don't matter);
  - the game revision: the git commit, plus a hash of any local changes under `src/`, `port/unix/` and `cmake/` (shown as `+dirty.<hash>`);
  - the game data: a hash of every embedded asset, so the ROM and any edited assets must match;
  - the savestate layout.

  The same commit built on macOS, Linux and Windows is compatible (checked Linux against Windows: 4 Players, 6000 frames, no desync).
- Only the Host's save file is used. Clients keep a temporary save for the Session, so their own `earthbound.srm` is never touched. `--save` is ignored when joining.
- F5 (debug), F6/F7 (savestates) and Tab (fast-forward) are disabled in a Session. F1 to F3 still work.
- There is no rollback, so the input delay is always felt.
- When someone joins, the Host's music restarts on the joining machine from the start of the track. Audio isn't part of the game state.
- A Session can't run past 2^32 frames (about 829 days at 60 fps without a break). The net frame counter would wrap.

## Testing

`playtest/net/` has a UDP proxy that adds latency, jitter, loss and reordering (`proxy.py`), and a launcher that runs a Host and clients as headless processes on localhost (`netrun.py`). With `relay=netrun.Relay(delay_ms=...)` the run goes through the Node relay (`relay/node/server.ts`, needs `npm ci` in `relay/`) instead of the proxy (`net_relay`). A peer can have its own link conditions (`net_auto_delay`). The proxy can also record a link's traffic and replay or spoof datagrams from the client's endpoint, for protocol tests (`net_rejoin`, `net_spoof_hello`). `netrun.py` run by hand exits non-zero unless every machine reached the end and they agreed on the hash points. The `net_*` scenarios in `playtest/coop/scenarios/` run under `playtest/coop/run_all.py`. `NET_LONG=1` turns `net_soak` into the 30-game-minute soak. Test-only switches:

- `--net-end-frame N`: every machine quits after frame N.
- `--net-wait-players N`: the Host holds the game while fewer than N Players are in, after a leave too.
- `EB_NET_TEST_DESYNC=F`: perturb this machine's RNG at frame F.
- `EB_NET_SHOT_FRAMES=F,...`: take screenshots at these frames.
- `EB_NET_HASH_INTERVAL=1`: hash every frame, to find the first frame that differs.
- `EB_NET_OVERLAY=1`: draw the status overlay in headless runs too (2: with the F4 lines). Off by default, because the scenarios compare every machine's screenshots.

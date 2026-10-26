# Online co-op

Up to four Players share one game over the internet. Every machine runs the same game in lockstep, and only controller input crosses the network (ADR 0002). The Host owns the save file. A joining Player gets the Host's game state when they connect.

## Host

```
port/unix/build/earthbound --host 7744
```

7744 is the default port; any free UDP port works. Players join and leave while the game runs. The Host is P1.

## Join

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

`--input-delay N` (Host only; clients use the Host's value) is how many frames late each button press takes effect. The default is 3 (50 ms), which suits a LAN.

On the internet, set it from your ping to the Host:

    N = ping / 16.7 + 1

For example, a 50 ms ping gives 4 and a 120 ms ping gives 8. Every machine waits for the Host's confirmed input. A client's press therefore makes a full round trip before it can take effect, so use the whole ping, not half of it. Too low a delay makes the game stutter, because machines wait for input. Too high a delay makes the controls feel heavy. With several clients, use the slowest one's ping.

## Networking

There is no matchmaking and no NAT traversal. The Host's UDP port must be reachable from every client:

- **Tailscale** (easiest): install it on every machine and join with the Host's Tailscale IP (`100.x.y.z`). Nothing needs to be opened on the router.
- **Port forwarding:** forward UDP port 7744 on the Host's router to the Host's machine, then join with the Host's public IP.

IPv4 only.

## Disconnects

- **A Player's connection drops:** everyone freezes. After 10 seconds without packets, the Host removes that Player and the game continues. To come back, they start the game again with `--join`. That is a fresh join, and they usually get the same Player number back.
- **A Player quits normally:** they leave immediately.
- **The Host quits or disappears:** every client stops with `the Host ended the Session` or `lost the connection to the Host`.

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

- Every machine needs the same build at the same viewport size (`EB_VIEWPORT_WIDTH`/`HEIGHT`) and the same ROM. A mismatched build is turned away when it connects.
- Only the Host's save file is used. Clients keep a temporary save for the Session, so their own `earthbound.srm` is never touched. `--save` is ignored when joining.
- F5 (debug), F6/F7 (savestates) and Tab (fast-forward) are disabled in a Session. F1 to F3 still work.
- There is no rollback, so the input delay is always felt.
- When someone joins, the Host's music restarts on the joining machine from the start of the track. Audio isn't part of the game state.

## Testing

`playtest/net/` has a UDP proxy that adds latency, jitter, loss and reordering (`proxy.py`), and a launcher that runs a Host and clients as headless processes on localhost (`netrun.py`). The `net_*` scenarios in `playtest/coop/scenarios/` run under `playtest/coop/run_all.py`. `NET_LONG=1` turns `net_soak` into the 30-game-minute soak. Test-only switches:

- `--net-end-frame N`: every machine quits after frame N.
- `--net-wait-players N`: the Host holds the game until N Players are in.
- `EB_NET_TEST_DESYNC=F`: perturb this machine's RNG at frame F.
- `EB_NET_SHOT_FRAMES=F,...`: take screenshots at these frames.
- `EB_NET_HASH_INTERVAL=1`: hash every frame, to find the first frame that differs.

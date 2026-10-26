# Shared World, with online play as input lockstep

All Players inhabit one simulation on one screen. Online play sends only controller input; every machine runs the same deterministic game and steps together, with a small input delay and no rollback at first. Independent exploration (sm64coopdx-style state sync) was rejected: it needs hand-written syncing of every NPC, enemy and story flag, which is months of work and a permanent source of Desyncs. EarthBound's one camera, scripted cutscenes and party-wide doors already assume a single Party.

## Consequences

- Every platform must compute bit-identical game state. Mac and Windows builds must match frame for frame, so cross-platform determinism is a release gate.
- Joining mid-game means the Host sends a savestate.

# Build on the BrianPugh/earthbound C port, not a ROM hack

We fork the C reimplementation (pinned at d32c421) instead of writing a 65816 ROM hack for an emulator. Co-op needs deep engine changes: a second walking Hero with its own collision, per-Player battle input, a camera for several Players. Those are tractable in C but slow and fiddly in assembly on a CPU that already lags. The port is also deterministic and ships a headless harness, savestates and golden-frame regressions. We accept the risks: the port has no license, changes daily upstream and is heavily AI-written.

## Considered Options

- ROM hack plus RetroArch netplay: online almost for free, but every engine change is in assembly. Multibound shows only that controller 2 can be read.
- Phase Distorter: a translated-assembly program running on an emulated SNES, so it has no advantage over an emulator.
- EarthBound Companion: a patch overlay on this same port, with nothing extra for co-op.

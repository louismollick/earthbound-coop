"""4 Players: three non-Leader Walkers spread out; the leash and camera cover all four."""

from _camera_np import spread_out


def run(ctx):
    spread_out(ctx, 4, {2: "UP+LEFT", 3: "RIGHT", 4: "DOWN+LEFT"})

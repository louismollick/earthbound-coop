"""3 Players: Paula walks LEFT, Jeff RIGHT; the leash caps the spread and the camera centres on the three Walkers."""

from _camera_np import spread_out


def run(ctx):
    spread_out(ctx, 3, {2: "UP+LEFT", 3: "RIGHT"})

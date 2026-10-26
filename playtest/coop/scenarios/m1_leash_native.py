"""256x224 (the native build, port/unix/build): the leash scales with the viewport (margin 1/8 of it)."""

from _leash import leash


def run(ctx):
    leash(ctx, binary=ctx.native_bin)

"""A savestate capture during a Select+Start hold doesn't reset the leave counter or fake a Start press."""

from lib import expect


def joined(p):
    return [n for n, pl in sorted(p.items()) if pl.joined]


def run(ctx):
    s = ctx.session(players=2)
    s.new_game()

    # 100 frames of the hold, a snap, 25 more: 125 >= 120, so P2 leaves
    s.do("hold P2 SELECT+START; 100 -")
    expect(joined(s.players()) == [1, 2], "P2 still joined after 100 held frames", joined(s.players()))
    out = s.do("snap mid")
    expect("SNAP mid ok" in out, "SNAP mid ok", out)
    s.do("25 -")
    expect(joined(s.players()) == [1], "P2 left after 100 + 25 held frames across a snap", joined(s.players()))

    # Still holding Start: another snap must not count as a fresh press and rejoin P2
    out = s.do("snap again; 10 -")
    expect("SNAP again ok" in out, "SNAP again ok", out)
    expect(joined(s.players()) == [1], "P2 not rejoined by a snap while Start stays held", joined(s.players()))

    # Release and press: a real press joins
    s.do("hold P2 -; 5 -; P2 press START")
    expect(joined(s.players()) == [1, 2], "P2 rejoined by a real Start press", joined(s.players()))
    ctx.shot(s, "rejoined after capture holds")

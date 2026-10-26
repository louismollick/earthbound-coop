"""Holding Select+Start for 2 s (120 frames) on P2's pad makes P2 leave; P1 can't leave."""

from lib import expect


def joined(p):
    return [n for n, pl in sorted(p.items()) if pl.joined]


def run(ctx):
    s = ctx.session(players=2)
    s.new_game()

    # Not long enough: 100 frames, then let go
    s.do("P2 100 SELECT+START; wait 5")
    p = s.players()
    expect(joined(p) == [1, 2], "P2 still joined after holding Select+Start for 100 frames", joined(p))

    s.do("P2 130 SELECT+START; wait 5")
    p = s.players()
    expect(joined(p) == [1], "P2 left after holding Select+Start for 130 frames", joined(p))
    ctx.shot(s, "P2 left")

    # Rejoin, then leave again with a sticky hold while P1 walks
    s.do("P2 press START")
    expect(joined(s.players()) == [1, 2], "P2 rejoined after 'P2 press START'", joined(s.players()))
    s.do("hold P2 SELECT+START; 130 LEFT; hold P2 -; wait 5")
    p = s.players()
    expect(joined(p) == [1], "P2 left via a sticky Select+Start hold", joined(p))

    # P1 can't leave
    s.do("200 SELECT+START; wait 5")
    p = s.players()
    expect(p[1].joined, "P1 still joined after holding Select+Start", p[1])

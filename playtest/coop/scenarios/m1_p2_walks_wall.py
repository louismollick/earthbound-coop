"""P2 walks Paula away from Ness with the Leader's movement code, then into a wall (the shore) and stops."""

from lib import expect


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    st = s.kraken_spot()
    lead, p2 = st.pos, st.players[2].pos
    expect(st.players[2].walker == "Paula", "P2 walks Paula", st.players[2])

    # A few tiles to the left; only P2's pad is pressed, so the Leader stays put
    s.do("P2 40 LEFT")
    st = s.state()
    a = st.players[2].pos
    expect(p2[0] - a[0] >= 40 and a[1] == p2[1], f"Paula moved left from {p2}", a)
    expect(st.pos == lead, f"the Leader still at {lead}", st.pos)
    expect(st.players[2].dir == "LEFT" and st.players[2].walk == 0, "Paula facing LEFT, walking style 0", st.players[2])
    ctx.shot(s, "P2 walked away")

    # Down into the shore: Paula moves until the water's edge, then stays put while P2 holds DOWN
    s.do("hold P2 DOWN; 90 -")
    b = s.state().players[2]
    s.do("20 -")
    st = s.state()
    c = st.players[2]
    s.do("release P2")
    expect(b.pos[1] - a[1] >= 50, f"Paula moved down from {a}", b.pos)
    expect(c.pos == b.pos, f"Paula stopped by the shore at {b.pos} while P2 holds DOWN", c.pos)
    expect(c.dir == "DOWN", "Paula facing DOWN into the shore", c)
    expect(st.pos == lead, f"the Leader still at {lead}", st.pos)
    ctx.shot(s, "P2 against the shore")

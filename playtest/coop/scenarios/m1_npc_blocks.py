"""P2 walks Paula into an NPC (the Summers sailor) and stops, like the Leader would."""

from lib import expect


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    st = s.kraken_spot("sailor")
    lead = st.pos
    expect("npc1065" in st.near, "the sailor npc1065 near the Party", st.near_line)
    dx, dy = st.near["npc1065"]
    sailor = (lead[0] + dx, lead[1] + dy)
    p2 = st.players[2].pos
    expect(p2[0] == sailor[0] and p2[1] < sailor[1], f"Paula above the sailor at {sailor}", p2)

    # Up a little, then down into the sailor
    s.do("P2 20 UP")
    a0 = s.state().players[2].pos
    s.do("hold P2 DOWN; 60 -")
    a = s.state().players[2]
    s.do("20 -")
    st = s.state()
    b = st.players[2]
    s.do("release P2")
    expect(a.pos[1] > a0[1], f"Paula moved down from {a0}", a.pos)
    expect(a.pos == b.pos, f"Paula stopped at {a.pos} while P2 holds DOWN", b.pos)
    # (the nook's wall nudges her a few px right on the way down)
    near = abs(b.pos[0] - sailor[0]) <= 12 and 0 < sailor[1] - b.pos[1] <= 12
    expect(near, f"Paula stopped just above the sailor {sailor}", b.pos)
    expect(b.dir == "DOWN", "Paula facing DOWN", b)
    expect(st.pos == lead, f"the Leader still at {lead}", st.pos)
    ctx.shot(s, "P2 blocked by the sailor")

"""P2 walks Paula diagonally: both axes change and she faces the diagonal."""

from lib import expect


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    st = s.kraken_spot()
    lead, p2 = st.pos, st.players[2].pos

    s.do("P2 24 UP+LEFT")
    st = s.state()
    a = st.players[2]
    expect(a.pos[0] < p2[0] - 15 and a.pos[1] < p2[1] - 15, f"Paula moved up-left from {p2}", a.pos)
    expect(a.dir == "UP_LEFT", "Paula facing UP_LEFT", a)
    expect(st.pos == lead, f"the Leader still at {lead}", st.pos)

    s.do("P2 24 DOWN+RIGHT")
    b = s.state().players[2]
    expect(b.pos[0] > a.pos[0] + 15 and b.pos[1] > a.pos[1] + 15, f"Paula moved down-right from {a.pos}", b.pos)
    expect(b.dir == "DOWN_RIGHT", "Paula facing DOWN_RIGHT", b)
    ctx.shot(s, "P2 diagonal")

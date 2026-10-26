"""4 Heroes, 2 Players: Poo (P2's) trails P2's Walker Paula; Jeff (P1's) stays with Ness."""

from lib import expect


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    st = s.kraken_spot()
    lead = st.pos

    s.do("P2 60 RIGHT")
    st = s.state()
    p, off = st.players, st.follow_offsets
    paula = p[2].pos
    poo = (lead[0] + off[4][0], lead[1] + off[4][1])
    jeff = (lead[0] + off[3][0], lead[1] + off[3][1])
    expect(st.pos == lead, f"the Leader still at {lead}", st.pos)
    expect(dist(paula, lead) >= 40, "Paula well away from Ness", paula)
    expect(dist(poo, paula) <= 20, f"Poo within 20 px of Paula {paula}", poo)
    expect(dist(jeff, lead) <= 30, f"Jeff within 30 px of Ness {lead}", jeff)
    expect(dist(poo, lead) >= 30, "Poo away from Ness", poo)
    ctx.shot(s, "Poo trails Paula, Jeff stays")

    # P1 walks the other way: Jeff follows Ness, Poo stays behind Paula
    s.do("40 LEFT")
    st = s.state()
    off = st.follow_offsets
    lead2 = st.pos
    expect(lead2[0] < lead[0] - 20, "Ness walked left", lead2)
    jeff = (lead2[0] + off[3][0], lead2[1] + off[3][1])
    poo2 = (lead2[0] + off[4][0], lead2[1] + off[4][1])
    expect(dist(jeff, lead2) <= 30, f"Jeff within 30 px of Ness {lead2}", jeff)
    expect(st.players[2].pos == paula, f"Paula still at {paula}", st.players[2].pos)
    expect(poo2 == poo, f"Poo still at {poo} (Paula didn't move)", poo2)
    ctx.shot(s, "Ness and Jeff walk, Paula and Poo wait")

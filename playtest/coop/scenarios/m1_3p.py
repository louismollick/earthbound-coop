"""3 Players: each non-Leader Walker moves in its own direction at once; the Leader ignores their input."""

from lib import expect


def run(ctx):
    s = ctx.session(save="27-Kraken", players=3)
    st = s.kraken_spot()
    lead, p = st.pos, st.players
    expect((p[2].walker, p[3].walker) == ("Paula", "Jeff"), "P2 walks Paula, P3 walks Jeff", st.players_line)
    a2, a3 = p[2].pos, p[3].pos

    s.do("hold P2 LEFT; hold P3 RIGHT; 30 -; hold P2 -; hold P3 -; 2 -")
    st = s.state()
    p = st.players
    expect(p[2].pos[0] < a2[0] - 15 and p[2].dir == "LEFT", f"Paula moved left from {a2}", p[2])
    expect(p[3].pos[0] > a3[0] + 15 and p[3].dir == "RIGHT", f"Jeff moved right from {a3}", p[3])
    expect(st.pos == lead, f"the Leader still at {lead}", st.pos)
    ctx.shot(s, "3 Players, two Walkers apart")

    # P1 walks down while the others hold still: only the Leader (and Poo, P1's) move
    s.do("12 DOWN")
    st2 = s.state()
    expect(st2.pos[1] > lead[1], "Ness moved down on P1's input", st2.pos)
    expect(st2.players[2].pos == p[2].pos and st2.players[3].pos == p[3].pos, "Paula and Jeff stay", st2.players_line)

"""4 Players: three non-Leader Walkers walk three ways at once with sticky holds; the Leader stays."""

from lib import expect


def run(ctx):
    s = ctx.session(save="27-Kraken", players=4)
    st = s.kraken_spot()
    lead, p = st.pos, st.players
    want = {2: "Paula", 3: "Jeff", 4: "Poo"}
    expect({n: p[n].walker for n in want} == want, f"Walkers {want}", st.players_line)
    a = {n: p[n].pos for n in want}

    s.do("hold P2 LEFT; hold P3 UP; hold P4 RIGHT; 30 -; hold P2 -; hold P3 -; hold P4 -; 2 -")
    st = s.state()
    p = st.players
    expect(p[2].pos[0] < a[2][0] - 15, f"Paula moved left from {a[2]}", p[2])
    expect(p[3].pos[1] < a[3][1] - 15, f"Jeff moved up from {a[3]}", p[3])
    expect(p[4].pos[0] > a[4][0] + 15, f"Poo moved right from {a[4]}", p[4])
    expect(st.pos == lead, f"the Leader still at {lead}", st.pos)
    ctx.shot(s, "4 Players, three Walkers apart")

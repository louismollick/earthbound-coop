"""With all four Heroes in the Party, ownership is dealt round-robin by join order and re-dealt on join/leave."""

from lib import expect


def owners(p):
    return {n: (pl.owns, pl.walker) for n, pl in sorted(p.items()) if pl.joined}


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    st = s.boot()
    expect("4:Poo" in st.party, "Ness, Paula, Jeff and Poo in the Party", st.party)
    want = {1: (["Ness", "Jeff"], "Ness"), 2: (["Paula", "Poo"], "Paula")}
    expect(owners(st.players) == want, f"2 Players: {want}", owners(st.players))

    # Walk so the followers spread out: P2's Walker position is Paula's entity
    s.do("40 DOWN; 40 LEFT")
    st = s.state()
    p, off = st.players, st.follow_offsets
    expect(p[1].pos == st.pos, f"P1's Walker (the Leader) at {st.pos}", p[1].pos)
    expect(2 in off and off[2] != (0, 0), "Paula trailing the Leader after walking", st.follow)
    paula = (st.pos[0] + off[2][0], st.pos[1] + off[2][1])
    expect(p[2].pos == paula, f"P2's Walker at Paula's position {paula}", p[2].pos)
    ctx.shot(s, "full Party, 2 Players")

    # P3 joins third: Ness P1, Paula P2, Jeff P3, Poo P1
    s.do("P3 press START")
    want = {1: (["Ness", "Poo"], "Ness"), 2: (["Paula"], "Paula"), 3: (["Jeff"], "Jeff")}
    expect(owners(s.players()) == want, f"3 Players: {want}", owners(s.players()))

    # P2 leaves: the join order is P1, P3, so Ness P1, Paula P3, Jeff P1, Poo P3
    s.do("P2 130 SELECT+START")
    want = {1: (["Ness", "Jeff"], "Ness"), 3: (["Paula", "Poo"], "Paula")}
    expect(owners(s.players()) == want, f"after P2 left: {want}", owners(s.players()))

    # Out-of-order joins with all four Heroes present: the deal follows join order,
    # not Player number. Join order P1, P3, P4, P2: Ness P1, Paula P3, Jeff P4, Poo P2.
    s = ctx.session(save="27-Kraken", name="order")
    s.boot()
    s.do("P3 press START; P4 press START; P2 press START")
    want = {1: (["Ness"], "Ness"), 2: (["Poo"], "Poo"), 3: (["Paula"], "Paula"), 4: (["Jeff"], "Jeff")}
    expect(owners(s.players()) == want, f"joins P3, P4, P2: {want}", owners(s.players()))

    # A middle Player leaves (order P1, P3, P2): Ness P1, Paula P3, Jeff P2, Poo P1
    s.do("P4 130 SELECT+START; 5 -")
    want = {1: (["Ness", "Poo"], "Ness"), 2: (["Jeff"], "Jeff"), 3: (["Paula"], "Paula")}
    expect(owners(s.players()) == want, f"after P4 left: {want}", owners(s.players()))

    # ...and rejoins at the end (order P1, P3, P2, P4): Ness P1, Paula P3, Jeff P2, Poo P4
    s.do("P4 press START")
    want = {1: (["Ness"], "Ness"), 2: (["Jeff"], "Jeff"), 3: (["Paula"], "Paula"), 4: (["Poo"], "Poo")}
    expect(owners(s.players()) == want, f"after P4 rejoined: {want}", owners(s.players()))

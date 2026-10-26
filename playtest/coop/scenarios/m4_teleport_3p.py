"""Edge case: PSI Teleport alpha with 3 Walkers spread out (24-Museum, the regress psi-teleport recipe).

P1 walks Ness (and Poo), P2 Paula, P3 Jeff. P2 and P3 walk apart, then P1 casts Teleport to Twoson.
The teleport takes the Party's ticks, so everyone regroups onto Ness's trail and runs with him;
everyone arrives in Twoson together in the vanilla arrival line, and then P2 and P3 walk on their own
again.
"""

from lib import expect

CAST = (
    "press A; until input 60; wait 10; press DOWN; press A; until input 300; wait 10; press A; until input 300; "
    "wait 10; press DOWN 2; wait 5; press A; until input 300; wait 10; press DOWN; press A"
)
TWOSON = (1412, 6560)


def run(ctx):
    s = ctx.session(save="24-Museum", players=3)
    s.boot()
    s.do("flag 11 1; teleport 4000 9300 6; wait 10; P2 30 UP; P3 30 DOWN")
    st = s.state()
    p = st.players
    start = st.pos
    expect(p[2].pos[1] < start[1] - 30 and p[3].pos[1] > start[1] + 30, "Paula up, Jeff down", st.players_line)
    ctx.shot(s, "before Teleport: 3 Walkers apart")

    # The run: Paula and Jeff fall in behind Ness on his trail at once
    s.do(f"{CAST}; wait 60")
    st = s.state()
    p = st.players
    expect("TELEPORT" in st.state and st.pos[0] < start[0] - 100, "Ness running the Teleport", st.state)
    for n, m in ((2, 2), (3, 3)):
        off = st.follow_offsets[m]
        expect(off[1] == 0 and 0 < off[0] <= 100, f"P{n}'s Walker running on Ness's trail", st.follow)
        expect(p[n].pos == (st.pos[0] + off[0], st.pos[1] + off[1]), f"PLAYERS P{n} where its sprite is", p[n])
    ctx.shot(s, "Teleport run: everyone on Ness's trail")

    s.do("until idle 2000")
    st = s.state()
    expect(st.pos == TWOSON and st.idle == "yes", f"arrived in Twoson at {TWOSON}", st.state)
    off = st.follow_offsets
    expect(all(o[1] == 0 and 0 < o[0] <= 100 for o in off.values()), "everyone in the arrival line", st.follow)
    ctx.shot(s, "Twoson: everyone arrived together")

    # Independence returns
    s.do("P2 20 DOWN; P3 30 RIGHT")
    st2 = s.state()
    p = st2.players
    expect(p[2].pos[1] > st.players[2].pos[1] + 15, "P2 walks Paula down", st2.players_line)
    expect(p[3].pos[0] > st.players[3].pos[0] + 20, "P3 walks Jeff right", st2.players_line)
    expect(st2.pos == TWOSON, "Ness stays", st2.pos)

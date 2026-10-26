"""Walkers follow the Party: while Paula is unconscious P2 walks Poo.

She trails the Leader as in vanilla, and when she revives P2 walks her again.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    st = s.kraken_spot()
    s.do("P2 40 RIGHT")

    s.do("status 2 1 1; 5 -")  # Paula unconscious
    st = s.state()
    lead, poo = st.pos, st.players[2].pos
    expect(st.players[2].walker == "Poo", "P2's Walker is Poo while Paula is unconscious", st.players_line)
    s.do("P2 30 DOWN")
    st = s.state()
    expect(st.players[2].pos[1] > poo[1] + 20 and st.pos == lead, f"Poo walks for P2 from {poo}", st.players_line)

    # Paula is on the Leader's trail now: she follows Ness
    s.do("40 LEFT")
    st = s.state()
    off = st.follow_offsets
    expect(st.pos[0] < lead[0] - 30, "Ness walked left", st.pos)
    expect(max(abs(off[2][0]), abs(off[2][1])) <= 30, "unconscious Paula trailing Ness", st.follow)
    ctx.shot(s, "P2 walks Poo, Paula trails Ness")

    s.do("status 2 1 0; 5 -")  # revived
    st = s.state()
    a = st.players[2]
    expect(a.walker == "Paula", "P2's Walker is Paula again after the revive", st.players_line)
    s.do("P2 20 UP")
    st = s.state()
    expect(st.players[2].pos[1] < a.pos[1] - 15, f"P2 walks Paula again from {a.pos}", st.players_line)

"""Unconscious (a): a Player whose Heroes are all unconscious is a plain Spectator.

27-Kraken, 2 Players: P2 owns Paula and Poo. With both knocked out P2 has no Walker and stands in for
nobody (they are still in the Party: not absent); P2's pad moves nothing and can't take the lock. Both
ghosts trail Ness. A revive gives P2 a Walker again.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    s.kraken_spot()
    s.do("P2 30 RIGHT; status 2 1 1; status 4 1 1; 5 -")
    st = s.state()
    p2 = st.players[2]
    expect(p2.owns == ["Paula", "Poo"], "P2 still owns Paula and Poo in the Party", st.players_line)
    expect(p2.spectator and not p2.standin and p2.walker is None, "P2 a plain Spectator", st.players_line)

    s.do("P2 30 LEFT; P2 press A; wait 20")
    st2 = s.state()
    expect(st2.idle == "yes" and st2.focus == "P1", "P2's A takes no lock", st2.players_line)
    expect(st2.follow_offsets == st.follow_offsets and st2.pos == st.pos, "P2's pad moves nothing", st2.follow)

    s.do("40 LEFT")
    st = s.state()
    off = st.follow_offsets
    expect(all(0 < off[m][0] <= 50 and off[m][1] == 0 for m in (2, 4)), "both ghosts on Ness's trail", st.follow)
    ctx.shot(s, "P2's Heroes KO'd: ghosts trail Ness, P2 spectates")

    s.do("status 4 1 0; 5 -")
    st = s.state()
    expect(st.players[2].walker == "Poo", "P2 walks Poo after the revive", st.players_line)
    s.do("P2 20 UP")
    st2 = s.state()
    expect(st2.players[2].pos[1] < st.players[2].pos[1] - 15, "P2 walks Poo", st2.players_line)

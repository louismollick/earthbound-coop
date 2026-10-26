"""Stand-in: in Winters (11-Winters, Party [Jeff, Bubble Monkey]) an absent Player walks the Monkey.

2 Players: P1 owns Ness and Jeff, P2 owns Paula and Poo, who are both away. P2 stands in for
Bubble Monkey: P2's pad walks him while Jeff stays put, and P2 can take the lock and open the menu.
3 Players: P3 owns Jeff (the Leader, so P3 has the focus); P1 and P2 are absent, and the first
absent Player in join order (P1) gets the only Guest. P2 has none left: a Spectator.
"""

from lib import expect

TOWN = "flag 11 1; warp winters; 30 -"  # open snow below the school gate


def run(ctx):
    s = ctx.session(save="11-Winters", players=2)
    s.boot()
    s.do(TOWN)
    st = s.state()
    p = st.players
    lead = st.pos
    expect(p[1].walker == "Jeff" and not p[1].standin, "P1 walks Jeff", st.players_line)
    expect(p[2].owns == [] and p[2].walker == "Bubble Monkey" and p[2].standin, "P2 stands in", st.players_line)
    expect(st.focus == "P1", "focus on the Leader's Owner P1", st.players_line)

    s.do("P2 40 RIGHT")
    st = s.state()
    monkey = st.players[2].pos
    expect(monkey[0] - lead[0] >= 30 and st.players[2].dir == "RIGHT", "the Monkey walked right", st.players_line)
    expect(st.pos == lead, f"Jeff still at {lead}", st.pos)
    expect(st.follow_offsets.get(9) == (monkey[0] - lead[0], monkey[1] - lead[1]), "his sprite there", st.follow)
    ctx.shot(s, "2P: P2 walks Bubble Monkey")

    # A Stand-in can take the lock and open the pause menu
    s.do("P2 press A; wait 20")
    st = s.state()
    expect(st.focus == "P2 locked" and st.idle != "yes", "P2 holds the lock with a menu open", st.players_line)
    s.do("P2 press B; wait 30")
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", "menu closed, focus back to P1", st.players_line)

    # 3 Players
    s3 = ctx.session("p3", save="11-Winters", players=3)
    s3.boot()
    s3.do(TOWN)
    st = s3.state()
    p = st.players
    lead = st.pos
    expect(p[3].walker == "Jeff" and st.focus == "P3", "P3 walks Jeff, the Leader, and has the focus", st.players_line)
    expect(p[1].owns == [] and p[1].walker == "Bubble Monkey" and p[1].standin, "P1 stands in", st.players_line)
    expect(p[2].spectator and not p[2].standin, "P2 a Spectator: no Guest left", st.players_line)

    s3.do("P1 40 RIGHT")
    st = s3.state()
    expect(st.players[1].pos[0] - lead[0] >= 30 and st.pos == lead, "P1 walks the Monkey, Jeff stays", st.players_line)
    s3.do("P3 30 LEFT")
    st2 = s3.state()
    expect(st2.pos[0] < lead[0] - 20, "P3 walks Jeff left", st2.pos)
    expect(st2.players[1].pos == st.players[1].pos, "the Monkey stays", st2.players_line)
    ctx.shot(s3, "3P: P3 Jeff, P1 Monkey, P2 spectates")

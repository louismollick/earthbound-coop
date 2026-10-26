"""The Leader's Owner's pad drives the Leader (Winters: Jeff and Bubble Monkey, Jeff P3's with 3 Players).

P1, who booted the file, can't move him (P1 stands in for the Monkey, P2 walks a Mr. Saturn Companion); P3 walks him and
opens and closes the menu, with no phantom presses from the pad switch after boot.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="11-Winters", players=3)
    st = s.boot()
    p = st.players
    expect(
        p[3].walker == "Jeff" and p[1].standin and p[2].companion,
        "P3 walks Jeff, P1 stands in for the Monkey, P2 walks the Companion",
        st.players_line,
    )
    lead = st.pos

    s.do("30 RIGHT")
    st = s.state()
    expect(st.pos == lead, f"P1's d-pad doesn't move the Leader from {lead}", st.pos)
    s.do("P3 30 RIGHT")
    st = s.state()
    expect(st.pos[0] > lead[0] + 8 and st.players[3].pos == st.pos, "P3's d-pad walks Jeff", st.players_line)
    ctx.shot(s, "P3 walks the Leader")

    # P3's A opens the pause menu (P2, a Companion, can't: its A only Checks from Mr. Saturn); P3
    # holds it, so P1's B doesn't close it
    s.do("P2 press A; wait 30")
    expect(s.state().idle == "yes", "P2's A opens no menu", s.state().state)
    s.do("P3 press A; wait 30")
    st = s.state()
    expect(st.idle == "modes" and st.focus == "P3 locked", "P3's A opened the menu", st.players_line)
    s.do("press B; wait 30")
    expect(s.state().idle == "modes", "P1's B doesn't close P3's menu", s.state().state)
    s.do("P3 press B; wait 30")
    expect(s.state().idle == "yes", "P3's B closed the menu", s.state().state)

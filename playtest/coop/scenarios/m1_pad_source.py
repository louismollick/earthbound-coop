"""The Leader's Owner's pad drives the Leader (Winters: Jeff alone, P3's with 3 Players).

P1, who booted the file, can't move him; P3 walks him and opens the menu, with no phantom presses
from the pad switch after boot.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="11-Winters", players=3)
    st = s.boot()
    p = st.players
    expect(
        p[3].walker == "Jeff" and p[1].spectator and p[2].spectator,
        "P3 walks Jeff, P1 and P2 spectate",
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

    # P3's A opens the pause menu (P1's doesn't). Inside menus the selection code still reads P1's
    # platform pad directly (window.c), so P1 closes it: menu focus is M3
    s.do("press A; wait 30")
    expect(s.state().idle == "yes", "P1's A opens nothing", s.state().state)
    s.do("P3 press A; wait 30")
    st = s.state()
    expect(st.idle == "modes", "P3's A opened the menu", st.state)
    s.do("press B; wait 30")
    expect(s.state().idle == "yes", "the menu closed", s.state().state)

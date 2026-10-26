"""P2 talks to an NPC its Walker faces (the Summers sailor) while the Leader stands 70 px away.

P2's A opens the pause menu and takes the lock; P1's presses do nothing while P2 holds it; Talk to
searches from Paula, not the Leader, and the sailor's text appears.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    st = s.kraken_spot("sailor")
    lead = st.pos
    dx, dy = st.near["npc1065"]
    sailor = (lead[0] + dx, lead[1] + dy)
    s.do("P2 40 DOWN; wait 4")
    st = s.state()
    paula = st.players[2]
    expect(paula.dir == "DOWN" and 0 < sailor[1] - paula.pos[1] <= 12, f"Paula right above the sailor {sailor}", paula)
    expect(abs(lead[0] - sailor[0]) > 40, f"the Leader at {lead}, out of talking range", sailor)
    expect(st.focus == "P1", "focus on the Leader's Owner before anyone presses", st.focus)

    s.do("P2 press A; wait 20")
    st = s.state()
    expect("PAUSE_MENU" in st.state and st.focus == "P2 locked", "P2's A opened the menu and locked", st.state)
    # P1 can't move the cursor or pick anything while P2 holds the lock
    s.do("press DOWN; wait 6; press A; wait 20")
    expect(s.menu() == (["Talk to", "Goods", "PSI", "Equip", "Check", "Status"], 0), "the menu as P2 left it", s.menu())
    expect("DISPLAY_TEXT" not in s.state().state, "P1's A picked nothing", s.state().state)

    said = s.said("P2 press A; until in:SELECTION_MENU 1500 P2 advance")
    expect("my wife wake up" in said, "the sailor's text after P2's Talk to", said)
    ctx.shot(s, "P2 talks to the sailor")
    st = s.state()
    expect(st.pos == lead and st.focus == "P2 locked", f"the Leader still at {lead}, P2 still locked", st.players_line)

    # P2 answers No; the lock ends with the text
    s.do("P2 press RIGHT; wait 6; P2 press A; until idle 900 P2 advance")
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", "idle again, focus back on P1", st.players_line)

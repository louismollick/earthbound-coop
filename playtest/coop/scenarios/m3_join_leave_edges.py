"""A join or a leave on the frame of a real press neither drops it nor replays it later (M3 review).

The new presses that menus read (coop_pad_new) must be this frame's on every frame, whatever the
Player count did on it: (a) P2 joining with START on the frame P1 presses A on the intro logo, the
A still skips the logo as in solo; (b) P2 leaving on the frame P1 moves the pause menu cursor down,
then rejoining a few frames later, the cursor doesn't move down a second time.
"""

from lib import expect


def run(ctx):
    # (a) simultaneous join and press
    s = ctx.session("join")
    s.do("300 -; hold P2 START; 1 A; release P2; 30 -")
    st = s.state()
    expect(st.players[2].joined, "P2 joined with START", st.players_line)
    expect("TITLE_SCREEN" in st.state, "P1's A on the join frame skipped the logo, as in solo", st.state)

    # (b) leave on a press, then rejoin
    s = ctx.session("leave", save="27-Kraken", players=2)
    s.kraken_spot()
    s.do("press A; wait 20")
    expect(s.menu() == (["Talk to", "Goods", "PSI", "Equip", "Check", "Status"], 0), "P1's menu, on Talk to", s.menu())
    s.do("hold P2 START+SELECT; 119 -; 1 DOWN; release P2; 8 -")
    st = s.state()
    expect(not st.players[2].joined, "P2 left on the 120th frame", st.players_line)
    expect(s.menu()[1] == 2, "P1's DOWN on the leave frame moved the cursor once (to PSI)", s.menu())
    s.do("P2 1 START; 10 -")
    st = s.state()
    expect(st.players[2].joined, "P2 rejoined", st.players_line)
    expect(s.menu()[1] == 2, "the rejoin replays no old DOWN: the cursor stays on PSI", s.menu())
    ctx.shot(s, "after leave and rejoin: cursor on PSI")
    s.do("press B; until idle 120")
    expect(s.state().idle == "yes", "P1 closed the menu", s.state().state)

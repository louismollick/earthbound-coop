"""M2: Auto Fight drives the whole Party (vanilla), and any Player can cancel it by holding B.

28-Scaraba, 2 Players. P1 picks Auto Fight on Ness's menu. Left alone, Auto Fight plays the battle out
with no menu (the control, from a snap). Holding B on P2's pad cancels it: after the round, Ness's menu
comes back, P1's.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="28-Scaraba", players=2)
    s.boot()
    s.do("teleport 1400 5600 4; until battle 1500 RIGHT|DOWN|LEFT|UP; until input 1500; wait 10")
    expect(s.title() == "Ness P1", "Ness's menu", s.windows())
    s.do("press RIGHT; wait 5; press RIGHT; wait 5")
    opts, sel = s.menu()
    expect(opts[sel] == "Auto Fight", "P1's cursor on Auto Fight", (opts, sel))
    s.do("snap af")

    # Control: nobody cancels, the battle plays out without another menu.
    s.do("press A; until idle 6000 advance")
    st = s.state()
    expect(st.idle == "yes" and "battle=0" in st.state, "Auto Fight played the battle out", st.state)

    s.do("restore af")
    said = s.said("press A; wait 30; hold P2 B; until in:SELECTION_MENU 3000; hold P2 -; wait 10")
    expect(said, "a round of Auto Fight text before the menu came back", said)
    st = s.state()
    expect("battle=0" not in st.state, "still in the battle", st.state)
    expect(s.title() == "Ness P1" and st.focus == "P1", "Ness's menu back, focus P1", (s.windows(), st.players_line))
    ctx.shot(s, "Auto Fight cancelled by P2")
    s.do("debug on; press SELECT+START; until idle 1500 advance")

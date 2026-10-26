"""Solo guard: with one Player the menus, Talk to, yes/no and Goods all work on P1 as in vanilla.

Ness alone above the Summers sailor: A, Talk to, the sailor's question, No; then Goods' "Who?"
starts on Ness. P2's pad is not joined and does nothing.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="27-Kraken")
    s.boot()
    s.do("flag 11 1; teleport 7264 2900 2; 30 -; 40 DOWN; wait 4")
    st = s.state()
    expect(st.near.get("npc1065", (0, 99))[1] <= 12, "Ness right above the sailor npc1065", st.near_line)
    expect(st.focus == "P1" and not st.players[2].joined, "solo: focus P1, P2 not joined", st.players_line)

    s.do("P2 press A; wait 20")
    expect(s.state().idle == "yes", "an unjoined P2's A opens nothing", s.state().state)
    s.do("press A; wait 20")
    expect(s.menu() == (["Talk to", "Goods", "PSI", "Equip", "Check", "Status"], 0), "P1's A: the menu", s.menu())
    said = s.said("press A; until in:SELECTION_MENU 1500 advance")
    expect("my wife wake up" in said, "the sailor talks", said)
    s.do("press RIGHT; wait 6")
    expect(s.menu() == (["Yes", "No"], 1), "P1 on No", s.menu())
    said = s.said("press A; until idle 900 advance")
    expect("I understand" in said, "the answer to No", said)

    out = s.do("press A; wait 20; press RIGHT; wait 6; press A; until input 300; text")
    expect(any(ln.startswith("WIN w2") and "[Ness]" in ln for ln in out), "Goods' Who? starts on Ness", out[-8:])
    ctx.shot(s, "solo Goods")
    s.do("press B; wait 10; press B; until idle 300")
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", "closed", st.players_line)

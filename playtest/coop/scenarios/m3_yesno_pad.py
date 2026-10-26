"""A yes/no prompt is answered by the Player who started the interaction (P2, with L), never P1.

P2 checks the Summers sailor with L (Check/Talk without the menu). At his "sail to Scaraba?"
prompt P1's RIGHT and A are ignored (a P1 A on Yes would start the voyage); P2 moves to No and
picks it.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    st = s.kraken_spot("sailor")
    money = st.money
    s.do("P2 40 DOWN; wait 4")
    said = s.said("P2 press L; until in:SELECTION_MENU 1500 P2 advance")
    expect("Scaraba" in said, "the sailor's question after P2's L", said)
    expect(s.menu() == (["Yes", "No"], 0), "Yes/No with the cursor on Yes", s.menu())
    expect(s.state().focus == "P2 locked", "P2 holds the lock", s.state().players_line)

    s.do("press RIGHT; wait 6; press A; wait 20")
    expect(s.menu() == (["Yes", "No"], 0), "P1's RIGHT and A ignored", s.menu())
    s.do("P2 press RIGHT; wait 6")
    expect(s.menu() == (["Yes", "No"], 1), "P2's RIGHT moved to No", s.menu())
    ctx.shot(s, "P2 on No")
    s.do("press A; wait 10")
    expect(s.menu() == (["Yes", "No"], 1), "P1's A still ignored", s.menu())

    said = s.said("P2 press A; until idle 900 P2 advance")
    expect("I understand" in said, "the sailor's answer to No", said)
    st = s.state()
    expect(st.money == money, f"no fare paid (${money})", st.money)
    expect(st.idle == "yes" and st.focus == "P1", "idle, focus back on P1", st.players_line)

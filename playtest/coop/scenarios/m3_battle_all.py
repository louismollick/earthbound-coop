"""A Spectator advances battle text, but the command menus are the Heroes' Owners' (M2).

Onett street, Ness alone (P2 a Spectator: its Companion sits out the battle). Ness's menu has focus P1: P2's presses change nothing, P1
picks Bash and the target, P2 reads the battle out (outside command menus the focus is ALL), with P1
still holding A: under ALL any one Player's press counts. Back on the overworld the focus is the
Leader's Owner's again.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="01-Start", players=2)
    s.boot()
    s.do("teleport 2660 440 4; until battle 500 DOWN|RIGHT|LEFT; until input 1500; wait 10")
    st = s.state()
    expect("BATTLE_MENU" in st.state and st.focus == "P1", "Ness's battle menu with focus P1", st.players_line)
    expect(st.players[2].companion, "P2 absent: a Companion (no command menu)", st.players[2])
    ctx.shot(s, "battle, focus P1")
    before = s.windows()
    s.do("P2 press A; wait 10")
    expect(s.windows() == before, "P2's A on Ness's menu changes nothing", s.windows())
    # P1 picks Bash, then confirms the target with an A they keep holding; P2's taps must still
    # advance every text prompt (under ALL a press is any one Player's press, M3 review)
    said = s.said("press A; until input 300; hold P1 A; until idle 3000 P2 advance")
    expect("Ness attacks" in said, "P1's A picked Bash and its target, P2 read it out", said)
    expect("gained" in said, "P2 advanced the victory text while P1 held A", said)
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", "back on the overworld, focus P1", st.players_line)
    s.do("release P1; 2 -")

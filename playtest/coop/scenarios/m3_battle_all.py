"""A Spectator advances battle text, but the command menus are the Heroes' Owners' (M2).

Onett street, Ness alone (P2 a Spectator). Ness's menu has focus P1: P2's presses change nothing, P1
picks Bash and the target, P2 reads the battle out (outside command menus the focus is ALL). Back on
the overworld the focus is the Leader's Owner's again.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="01-Start", players=2)
    s.boot()
    s.do("teleport 2660 440 4; until battle 500 DOWN|RIGHT|LEFT; until input 1500; wait 10")
    st = s.state()
    expect("BATTLE_MENU" in st.state and st.focus == "P1", "Ness's battle menu with focus P1", st.players_line)
    expect(st.players[2].spectator, "P2 a Spectator", st.players[2])
    ctx.shot(s, "battle, focus P1")
    before = s.windows()
    s.do("P2 press A; wait 10")
    expect(s.windows() == before, "P2's A on Ness's menu changes nothing", s.windows())
    said = s.said("press A; until input 300; press A; until idle 3000 P2 advance")
    expect("Ness attacks" in said, "P1's A picked Bash and its target, P2 read it out", said)
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", "back on the overworld, focus P1", st.players_line)

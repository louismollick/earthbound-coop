"""Until M2, a battle's focus is ALL: any joined Player picks commands and advances text.

Onett street, Ness alone (P2 a Spectator). Entering the battle sets focus=ALL; P2's A picks Bash and
the target and reads the battle out; back on the overworld the focus is the Leader's Owner's again.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="01-Start", players=2)
    s.boot()
    s.do("teleport 2660 440 4; until battle 500 DOWN|RIGHT|LEFT; until input 1500")
    st = s.state()
    expect("BATTLE_MENU" in st.state and st.focus == "ALL", "a battle menu with focus ALL", st.players_line)
    expect(st.players[2].spectator, "P2 a Spectator", st.players[2])
    ctx.shot(s, "battle, focus ALL")
    said = s.said("P2 press A; until input 300; P2 press A; until idle 3000 P2 advance")
    expect("Ness attacks" in said, "P2's A picked Bash and its target", said)
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", "back on the overworld, focus P1", st.players_line)

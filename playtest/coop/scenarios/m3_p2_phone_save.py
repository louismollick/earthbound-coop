"""P2 saves the game by calling Dad from the Scaraba desert cabin phone; a fresh process loads the save.

Ness (P1) walks away from the phone and Paula (P2) stays in front of it. P2 talks to the phone,
calls Dad and picks Record; P1's A at Dad's menu is ignored. The session's save.srm changes, and a
new process booting it starts where Ness stood when P2 saved.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="15-Desert", players=2)
    s.boot()
    s.do("30 LEFT; wait 4")
    st = s.state()
    saved_at = st.pos
    paula = st.players[2]
    expect(paula.dir == "UP" and st.near.get("npc751") is not None, "Paula facing the phone npc751", st.players_line)
    before = (s.dir / "save.srm").read_bytes()

    said = s.said("P2 press A; wait 20; P2 press A; until input 300 P2 advance")
    expect("picked up the receiver" in said, "the phone after P2's Talk to", said)
    said = s.said("P2 press A; until in:SELECTION_MENU 2000 P2 advance")
    expect("your dad" in said, "Dad answers", said)
    expect(s.menu() == (["Record", "Nothing, really"], 0), "Dad's menu", s.menu())
    s.do("press RIGHT; wait 6; press A; wait 20")
    expect(s.menu() == (["Record", "Nothing, really"], 0), "P1's RIGHT and A ignored", s.menu())

    said = s.said("P2 press A; until in:SELECTION_MENU 2000 P2 advance")
    expect("created a record" in said, "Dad saved the game", said)
    after = (s.dir / "save.srm").read_bytes()
    expect(after != before, "save.srm changed", "the same bytes")
    ctx.shot(s, "P2 saved with Dad")
    s.do("P2 press A; until idle 900 P2 advance")
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", "the call ended, focus back on P1", st.players_line)

    # A fresh process boots the new save: the Party starts where Ness stood when P2 saved
    t = ctx.session("reload", save=s.dir / "save.srm", players=2)
    st2 = t.boot()
    expect(st2.pos == saved_at, f"the reloaded Leader at {saved_at}", st2.pos)
    ctx.shot(t, "the reloaded save")

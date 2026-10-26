"""Unconscious (c): a Hero knocked out in battle; back on the overworld the Walkers are right.

28-Scaraba, 2 Players. Paula (P2's Walker) goes down in a desert battle; afterwards P2 walks Poo,
Paula's ghost trails Ness, and Ness stays P1's.
"""

from _ko import battle_ko
from lib import expect


def run(ctx):
    s, st = battle_ko(ctx, 2)
    p = st.players
    expect(p[1].walker == "Ness" and st.focus == "P1", "P1 walks Ness, the Leader", st.players_line)
    expect(p[2].walker == "Poo", "P2 walks Poo", st.players_line)
    lead = st.pos

    s.do("P2 30 UP")
    st = s.state()
    poo = st.players[2].pos
    expect(poo[1] < lead[1] - 20 and st.pos == lead, "P2 walks Poo up, Ness stays", st.players_line)
    s.do("30 LEFT")
    st = s.state()
    expect(st.pos[0] < lead[0] - 20, "Ness walks left", st.pos)
    expect(st.players[2].pos == poo, "Poo stays", st.players_line)
    expect(max(abs(v) for v in st.follow_offsets[2]) <= 40, "Paula's ghost trails Ness", st.follow)
    s.do("wait 90")  # past the post-battle blink, so the shot shows the Party
    ctx.shot(s, "Paula KO'd in battle: P2 walks Poo, her ghost trails Ness")

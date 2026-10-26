"""A Walker that becomes independent standing on an NPC can walk off it (4 Players, the Magicant wakeup).

Vanilla followers walk through NPCs, so a follower may stand on one. When the Party is laid out again after a
cutscene, that follower may be a Walker: here, 34-Magicant with 4 Players, the Flying Man joins, then the Nightmare
(debug win) and the montage wake the Party up in Saturn Valley with Poo (P4's Walker, 91 px behind Ness in the
arrival line) right on the wandering Mr. Saturn npc718 (where he stands then depends on the timing, so the
inputs are exactly these). The two block each other, so neither ever moves. The Walker step is the Leader's, whose NPC check found npc718 in every
direction, so P4 could never move again. Now an NPC the Walker already overlaps doesn't block its step out
(enemies still do), and once clear it blocks again.
"""

from lib import expect
from m4_solo_magicant import talk_to_flying_man

NIGHTMARE = (
    "teleport 496 9140 0; wait 10; press L; until battle 3000 advance; until input 1500 advance; "
    "debug on; 4 SELECT+START; until said:powers 6000 advance; debug off; until idle 8000 advance"
)


def run(ctx):
    s = ctx.session(save="34-Magicant", players=4)
    s.boot()
    s.do("flag 11 1")
    expect("joins" in talk_to_flying_man(s), "the Flying Man joined", "")
    s.do(NIGHTMARE, timeout=300)
    st = s.state()
    p4 = st.players[4]
    expect(st.idle == "yes" and p4.walker == "Poo", "awake in Saturn Valley, P4 walking Poo", st.players_line)
    dx, dy = st.near.get("npc718", (999, 999))
    npc = (st.pos[0] + dx, st.pos[1] + dy)
    expect(abs(npc[0] - p4.pos[0]) <= 4 and abs(npc[1] - p4.pos[1]) <= 8, f"Poo on npc718 at {npc}", p4)
    ctx.shot(s, "Poo (P4) woke up on a Mr. Saturn")

    s.do("P4 20 DOWN")
    st2 = s.state()
    expect(st2.players[4].pos[1] > p4.pos[1] + 10, "P4 walks Poo off the NPC", st2.players_line)
    expect(st2.pos == st.pos, "Ness stays", st2.pos)
    # Clear of it, npc718 blocks again: walking back up stops short of where Poo stood
    s.do("P4 40 UP")
    st3 = s.state()
    expect(st3.players[4].pos[1] > p4.pos[1] + 4, "npc718 blocks Poo again once he is off it", st3.players_line)
    ctx.shot(s, "P4 walked Poo off it")

"""Unconscious (b): the Leader is knocked out in battle; the new Leader's Owner walks it and has the focus.

28-Scaraba, 2 Players. Ness (P1's) goes down in a desert battle; afterwards the Party sorts him last, so
Paula (P2's) leads: P2 has the focus and walks the Leader, P1 walks Jeff on his own, and Ness's ghost
trails Paula.
"""

from _ko import battle_ko
from lib import expect


def run(ctx):
    s, st = battle_ko(ctx, 1)
    p = st.players
    expect(st.focus == "P2", "focus on P2, the new Leader's Owner", st.players_line)
    expect(p[2].walker == "Paula" and p[1].walker == "Jeff", "P2 walks Paula, P1 walks Jeff", st.players_line)
    lead = st.pos
    expect(p[2].pos == lead, "Paula is the Leader", st.players_line)

    s.do("P2 30 UP")
    st = s.state()
    expect(st.pos[1] < lead[1] - 20 and st.players[2].pos == st.pos, "P2's pad walks the Leader up", st.state)
    jeff = st.players[1].pos
    s.do("P1 30 LEFT")
    st2 = s.state()
    expect(st2.players[1].pos[0] < jeff[0] - 20, "P1 walks Jeff left", st2.players_line)
    expect(st2.pos == st.pos, "the Leader stays", st2.pos)
    expect(max(abs(v) for v in st2.follow_offsets[1]) <= 40, "Ness's ghost trails Paula", st2.follow)
    s.do("wait 90")  # past the post-battle blink, so the shot shows the Party
    ctx.shot(s, "Ness KO'd: P2 leads with Paula, P1 walks Jeff")

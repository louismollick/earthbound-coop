"""The Leader boards an escalator while P2 stands apart: Paula regroups onto Ness's trail and rides with him.

Upstairs she walks on her own again (18-DeptStore, 1F up escalator at 4888,6856).
"""

from lib import expect


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def run(ctx):
    s = ctx.session(save="18-DeptStore", players=2)
    s.boot()
    s.do("flag 11 1; teleport 4942 6853 6; 20 -; P2 40 RIGHT")
    st = s.state()
    lead, paula = st.pos, st.players[2].pos
    expect(paula[0] - lead[0] >= 40, f"Paula right of Ness {lead}", paula)

    s.do("40 LEFT")
    st = s.state()
    expect(st.idle == "escalator", "Ness on the escalator", st.state)
    expect(dist(st.players[2].pos, st.pos) <= 24, f"Paula regrouped behind Ness {st.pos}", st.players[2].pos)
    ctx.shot(s, "escalator: Paula rides behind Ness")

    s.do("until idle 600")
    st = s.state()
    expect(st.pos[1] < lead[1] - 100, "upstairs", st.pos)
    expect(dist(st.players[2].pos, st.pos) <= 48, "Paula arrived with Ness", st.players_line)
    s.do("P2 20 DOWN")
    st2 = s.state()
    expect(st2.players[2].pos[1] > st.players[2].pos[1] + 10, "Paula walks on her own upstairs", st2.players_line)
    expect(st2.pos == st.pos, "Ness stays", st2.pos)

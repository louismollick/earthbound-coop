"""Two absent Players walk two Mr. Saturns (07-InHappy: Ness alone, 3 Players).

P2 (Paula) and P3 (Jeff) are absent and there is no Guest: each walks a Mr. Saturn of their own, on
their own pad, and neither moves the Leader or the camera.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="07-InHappy", players=3)
    s.boot()
    s.do("flag 11 1; wait 10")
    st = s.state()
    p = st.players
    lead, cam = st.pos, st.camera
    expect(p[2].companion and p[3].companion, "P2 and P3 both walk a Companion", st.players_line)
    expect(p[2].pos and p[3].pos and p[2].pos != p[3].pos, "both out, on different spots", st.players_line)
    ctx.shot(s, "two Mr. Saturns appear")

    s.do("P2 25 RIGHT; P3 25 LEFT")
    st = s.state()
    a, b = st.players[2], st.players[3]
    expect(a.dir == "RIGHT" and a.pos[0] > p[2].pos[0] + 15, "P2's Mr. Saturn walked right", a)
    expect(b.dir == "LEFT" and b.pos[0] < p[3].pos[0] - 15, "P3's walked left", b)
    expect(st.pos == lead and st.camera == cam, "the Leader and camera stayed", st.camera_line)
    s.do("P3 10 RIGHT")
    st = s.state()
    expect(st.players[3].pos[0] > b.pos[0] and st.players[2].pos == a.pos, "P3 walks only its own", st.players_line)
    ctx.shot(s, "two Mr. Saturns")

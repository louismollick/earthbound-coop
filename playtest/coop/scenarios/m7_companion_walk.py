"""Companion: an absent Player walks Mr. Saturn (07-InHappy: Ness alone, in the drug store).

P2 owns Paula and Poo, who aren't in the Party, and no Guest is there to stand in for, so P2 walks a
Mr. Saturn. P2's pad moves it (the Leader and the camera stay put), its sprite faces the way it walks,
walls stop it, it is leashed to the view, and the Leader walking leaves it standing.
"""

from lib import expect, expect_in_leash


def run(ctx):
    s = ctx.session(save="07-InHappy", players=2)
    s.boot()
    s.do("flag 11 1; wait 10")
    st = s.state()
    p1, p2 = st.players[1], st.players[2]
    lead, cam = st.pos, st.camera
    expect(p1.walker == "Ness" and not p1.companion, "P1 walks Ness", st.players_line)
    expect(p2.owns == [] and p2.walker == "Mr. Saturn" and p2.companion, "P2 walks the Companion", st.players_line)
    expect(p2.pos and not p2.hidden and not p2.spectator, "Mr. Saturn out next to Ness", st.players_line)
    near = max(abs(p2.pos[0] - lead[0]), abs(p2.pos[1] - lead[1]))
    expect(near <= 24, f"Mr. Saturn appeared next to Ness {lead}", p2.pos)
    expect(st.focus == "P1", "the focus on the Leader's Owner", st.players_line)
    ctx.shot(s, "P2 Mr. Saturn next to Ness")

    s.do("P2 20 RIGHT")
    st = s.state()
    sat = st.players[2]
    expect(sat.pos[0] >= p2.pos[0] + 15 and sat.dir == "RIGHT", f"Mr. Saturn walked right from {p2.pos}", sat)
    expect(st.pos == lead and st.camera == cam, f"the Leader at {lead} and the camera at {cam}", st.camera_line)
    s.do("hold P2 UP; wait 9")
    ctx.shot(s, "walking up, frame A")
    s.do("wait 8")
    ctx.shot(s, "walking up, frame B")
    s.do("release P2")
    st = s.state()
    expect(st.players[2].dir == "UP" and st.players[2].pos[1] < sat.pos[1], "Mr. Saturn walked up", st.players[2])
    s.do("P2 10 LEFT")
    expect(s.state().players[2].dir == "LEFT", "facing left", s.state().players[2])
    # A diagonal shows a cardinal facing (the sprite has four)
    s.do("P2 6 UP+LEFT")
    expect(s.state().players[2].dir in ("UP", "LEFT"), "a diagonal collapsed to a cardinal", s.state().players[2])

    # Walls: the bottom wall of the shop stops it
    s.do("P2 60 DOWN")
    a = s.state().players[2].pos
    s.do("P2 20 DOWN")
    b = s.state().players[2].pos
    expect(a == b and a[1] <= lead[1] + 4, "the wall stopped Mr. Saturn", (a, b))

    # Leash: it stops inside the view, and nothing else moves
    s.do("P2 40 UP; P2 200 RIGHT")
    st = s.state()
    expect_in_leash(st, st.players[2].pos, "Mr. Saturn at the leash")
    expect(st.pos == lead and st.camera == cam, "the Leader and camera never moved", (st.pos, st.camera))
    ctx.shot(s, "Mr. Saturn at the leash")

    # The Leader walks, Mr. Saturn (no input) stays where it stood
    sat = st.players[2].pos
    s.do("20 LEFT")
    st = s.state()
    expect(
        st.pos[0] < lead[0] - 10 and st.players[2].pos == sat,
        f"Ness walked, Mr. Saturn stayed at {sat}",
        st.players_line,
    )

"""P2 leaves while walking away from the Leader (M1 review finding 2).

Solo play must go on as vanilla: within a few frames, with no input from P1, the camera is back on
the Leader and the followers stand in vanilla formation; then walking matches a solo session that
never had co-op, frame for frame (no camera cut, no follower yanked onto the Leader).
"""

from lib import expect

SPOT = "flag 11 1; teleport 1400 5520 4; 30 -"


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    s.boot()
    s.do(f"{SPOT}; P2 100 RIGHT")
    st = s.state()
    paula = st.players[2].pos
    expect(paula[0] - st.pos[0] > 100, "Paula walked well right of Ness", st.players_line)
    expect(st.camera != (st.pos[0], st.pos[1]), "the camera on the midpoint", st.camera_line)

    # P2 holds Select+Start (its Select opens the HP/PP window and P2 leaves); P1 closes the window
    s.do("P2 120 SELECT+START; press B; wait 20")
    st = s.state()
    expect(not st.players[2].joined, "P2 left", st.players_line)
    expect(st.idle == "yes", "solo play idle", st.state)
    expect(st.camera == st.pos, f"the camera back on the Leader {st.pos} without input", st.camera_line)
    off = st.follow_offsets
    expect(all(max(abs(dx), abs(dy)) <= 30 for dx, dy in off.values()), "the followers with Ness", st.follow)
    ctx.shot(s, "P2 left mid-spread: Party regrouped, camera on Ness")

    # A solo session that never had co-op, at the same spot, as the reference
    ref = ctx.session("solo", save="27-Kraken", players=1)
    ref.boot()
    ref.do(SPOT)
    r = ref.state()
    expect(r.follow_offsets == off, f"the same formation as solo {r.follow}", st.follow)
    # The regroup lays the followers at walking spacing on Ness's trail, where a fresh teleport has
    # them on his spot, so they trail by up to a pixel more at first and match exactly once walking
    for step, exact in [("1 RIGHT", False), ("20 RIGHT", False), ("30 DOWN+LEFT", True), ("10 UP", True)]:
        s.do(step)
        ref.do(step)
        a, b = s.state(), ref.state()
        expect(a.pos == b.pos, f"Ness walks as in solo ({step})", a.pos)
        expect(a.camera == a.pos and b.camera == b.pos, f"the camera on Ness as in solo ({step})", a.camera_line)
        fa, fb = a.follow_offsets, b.follow_offsets
        close = fa.keys() == fb.keys() and all(max(abs(fa[m][0] - fb[m][0]), abs(fa[m][1] - fb[m][1])) <= 1 for m in fa)
        expect(fa == fb if exact else close, f"the followers as in solo ({step}): {b.follow}", a.follow)
    ctx.shot(s, "after the leave, walking as in solo")

"""P2 walks Paula into a door while Ness stands 120 px away: the whole Party goes through together.

Summers promenade, door up and left of 7358,2870. The Party regroups behind the Leader for the fade.
"""

from lib import expect


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    s.boot()
    s.do("flag 11 1; teleport 7400 2870 6; 30 -; 60 RIGHT; P2 30 LEFT")
    st = s.state()
    lead, paula = st.pos, st.players[2].pos
    expect(lead[0] - paula[0] >= 100, f"Paula well left of Ness {lead}", paula)

    # P2 walks into the door: during the fade everyone stands in formation behind the Leader
    s.do("until in:DOOR_TRANSITION 80 P2 UP")
    st = s.state()
    expect("DOOR_TRANSITION" in st.state, "P2's step opened the door", st.state)
    expect(st.pos == lead, f"the Leader still at {lead}", st.pos)
    off = st.follow_offsets
    expect(all(dist(o, (0, 0)) <= 16 * (i + 1) for i, o in enumerate(off.values())), "everyone behind Ness", st.follow)
    expect(dist(st.players[2].pos, lead) <= 24, f"Paula regrouped behind Ness {lead}", st.players[2].pos)
    ctx.shot(s, "P2's door: regrouped for the fade")

    s.do("until idle 600")
    st = s.state()
    p = st.players[2]
    expect(dist(st.pos, lead) > 200, "the Party left the promenade", st.pos)
    expect(all(dist(o, (0, 0)) <= 24 for o in st.follow_offsets.values()), "everyone at the destination", st.follow)
    expect(st.camera == st.pos, "the camera on the Leader after the door", st.camera_line)
    ctx.shot(s, "after P2's door, all through")

    # Control is back: P2 walks Paula on her own again
    s.do("P2 20 DOWN")
    st2 = s.state()
    expect(st2.players[2].pos[1] > p.pos[1] + 10, f"Paula walked down from {p.pos}", st2.players[2].pos)
    expect(st2.pos == st.pos, f"the Leader still at {st.pos}", st2.pos)

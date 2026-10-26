"""The game takes control and P2's chain snaps; afterwards P2 walks independently again.

P1 walks through a door: the whole Party transitions with P2's chain on the Leader's trail. A window
only pauses P2's Walker (no snap).
"""

from lib import expect


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    s.boot()
    # Summers promenade, open paving with a building door up and to the left of (7358,2870)
    s.do("flag 11 1; teleport 7400 2870 6; 30 -")
    s.do("P2 40 RIGHT")
    st = s.state()
    lead, paula = st.pos, st.players[2].pos
    expect(paula[0] - lead[0] >= 40, f"Paula walked right of Ness {lead}", paula)

    # A window (B: the HP/PP display) pauses Walkers: P2 holding LEFT doesn't move Paula, and her
    # chain stays where it is (no snap)
    s.do("press B; wait 20; hold P2 LEFT; 30 -; release P2")
    st = s.state()
    expect("HPPP" in st.state, "the HP/PP window open", st.state)
    expect(st.players[2].pos == paula, f"Paula held at {paula} while the window is open", st.players[2].pos)
    s.do("press B; wait 20")
    st = s.state()
    expect(st.idle == "yes", "back to plain overworld control", st.state)

    # P1 walks into the door: the game takes over and everyone goes through
    s.do("30 LEFT; until in:DOOR_TRANSITION 60 UP; until idle 600")
    st = s.state()
    p = st.players[2]
    expect(dist(st.pos, lead) > 200, f"the Party left the promenade (Leader was at {lead})", st.pos)
    expect(dist(p.pos, st.pos) <= 24, f"Paula with the Leader {st.pos} after the door", p.pos)
    ctx.shot(s, "after the door, Paula regrouped")

    # Control is back: P2 walks Paula on her own again
    s.do("P2 20 DOWN")
    st2 = s.state()
    expect(st2.players[2].pos[1] > p.pos[1] + 10, f"Paula walked down from {p.pos}", st2.players[2].pos)
    expect(st2.pos == st.pos, f"the Leader still at {st.pos}", st2.pos)
    ctx.shot(s, "P2 walks again after the door")

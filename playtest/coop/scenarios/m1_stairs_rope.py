"""Surfaces for P2's Walker: stairs are a wall, a rope works.

The Leader takes the stairs (P2's chain snaps meanwhile); P2 climbs the rope with the climbing style,
and the door at its top takes the whole Party.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    s.boot()

    # Stairs (door type 4) at (5232,3560), straight above
    s.do("flag 11 1; teleport 5232 3580 0; 20 -")
    lead = s.state().pos
    s.do("P2 30 UP")
    a = s.state().players[2]
    s.do("P2 20 UP")
    st = s.state()
    b = st.players[2]
    expect(a.pos[1] < lead[1] and b.pos == a.pos, f"Paula stopped below the stairs (from {lead})", f"{a.pos} {b.pos}")
    expect(b.walk == 0 and st.pos == lead, "Paula not on the stairs, the Leader unmoved", st.players_line)
    ctx.shot(s, "P2 blocked by stairs")

    # The Leader takes them: the game moves the party, P2's chain trails the Leader meanwhile
    s.do("30 UP")
    st = s.state()
    expect(st.idle == "stairs", "the Leader on the stairs", st.state)
    p2 = st.players[2]
    expect(
        max(abs(p2.pos[0] - st.pos[0]), abs(p2.pos[1] - st.pos[1])) <= 24,
        f"Paula on the Leader's trail near {st.pos}",
        p2,
    )
    s.do("until idle 900 RIGHT")
    st = s.state()
    s.do("P2 20 DOWN")
    st2 = s.state()
    expect(
        st2.players[2].pos[1] > st.players[2].pos[1] + 10, "Paula walks on her own after the stairs", st2.players_line
    )

    # A rope at (1184,2576..2608): Paula climbs down with the rope style, the Leader stays
    s.do("teleport 1184 2576 4; 20 -")
    st = s.state()
    lead, a = st.pos, st.players[2].pos
    s.do("P2 20 DOWN")
    st = s.state()
    b = st.players[2]
    expect(b.walk == 8 and b.pos[1] > a[1] and st.pos == lead, f"Paula climbing down the rope from {a}", b)
    ctx.shot(s, "P2 on a rope")

    # Up the rope into the hole at its top: the whole Party goes through
    s.do("until in:DOOR_TRANSITION 200 P2 UP; until idle 600")
    st = s.state()
    expect(abs(st.pos[1] - lead[1]) > 500, f"the Party moved through the rope's door (Leader was at {lead})", st.pos)
    ctx.shot(s, "the Party through the rope's door")

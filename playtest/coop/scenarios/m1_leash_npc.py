"""The leash never slides a Walker into an NPC (M1 review finding 1).

A diagonal step clears the NPC, then the leash reverts its widening axis; the position that is left
(the other axis only) must be checked too. Onett's npc170 stands still at (1968,1504). The sliding
Walker starts up and left of it, 11 px left and 8 px above (hitboxes touch, no overlap), at the
leash's x limit from the other Walker, and holds DOWN+LEFT: LEFT is leashed, and moving DOWN alone
would overlap the NPC. Checked for the Leader's step and for a non-Leader Walker's step.
"""

from lib import expect

NPC = "npc170"
NPC_POS = (1968, 1504)  # it stands still
SPOT = (1957, 1496)  # 11 px left of and 8 px above npc170


def overlaps(off):
    """Whether npc_collision_check counts offset ``off`` (npc170 minus the Walker) as an overlap.

    Measured in solo play for a Hero facing up, down or diagonally: walking straight down past
    npc170 is blocked at |dx| <= 11 and stops at dy = 8.
    """
    return abs(off[0]) < 12 and -8 < off[1] < 8


def slide(s, who, step):
    """Run ``step`` (one frame) 25 times; fail if ``who`` (a function of the State) overlaps npc170."""
    for i in range(25):
        s.do(step)
        st = s.state()
        pos = who(st)
        rel = (NPC_POS[0] - pos[0], NPC_POS[1] - pos[1])
        expect(not overlaps(rel), f"no overlap with {NPC} at {NPC_POS} (frame {i + 1})", f"Walker at {pos}")
    return st


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    s.boot()
    s.do(f"flag 11 1; teleport {SPOT[0]} {SPOT[1]} 4; 20 -; snap spot")
    st = s.state()
    expect(st.near.get(NPC) == (11, 8), f"{NPC} 11 px right of and 8 px below Ness", st.near_line)
    cap = st.view[0] - 2 * (st.view[0] // 8)

    # The Leader: P2 walks Paula to the leash's x limit on the right, then Ness slides
    s.do("P2 300 RIGHT; 2 -")
    st = s.state()
    expect(st.players[2].pos[0] - st.pos[0] == cap, f"Paula {cap} px right of Ness (the leash)", st.players_line)
    st = slide(s, lambda t: t.pos, "1 DOWN+LEFT")
    expect(st.pos[0] == SPOT[0], "the leash held Ness's x", st.pos)
    ctx.shot(s, "Leader leashed beside an NPC, no overlap")

    # A non-Leader Walker: Ness walks to the leash's x limit on the right, then Paula slides
    s.do("restore spot; 300 RIGHT; 2 -")
    st = s.state()
    expect(st.pos[0] - st.players[2].pos[0] == cap, f"Ness {cap} px right of Paula (the leash)", st.players_line)
    st = slide(s, lambda t: t.players[2].pos, "P2 1 DOWN+LEFT")
    expect(st.players[2].pos[0] == SPOT[0], "the leash held Paula's x", st.players_line)
    ctx.shot(s, "Walker leashed beside an NPC, no overlap")

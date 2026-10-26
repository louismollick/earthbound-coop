"""A real cutscene with two Walkers apart: the Kraken voyage (27-Kraken, the Summers pier).

P2 walks Paula off to the side, P1 talks to the sailor and says Yes: the game walks the Party onto the boat, so
Paula's chain snaps into Ness's trail and the camera eases to Ness. After the Kraken battle (debug win) and the
landing in Scaraba, both Players walk independently again.
"""

from lib import expect


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    s.boot()
    s.do("flag 11 1; teleport 7264 2940 0; 20 -; P2 30 LEFT; P2 30 DOWN")
    st = s.state()
    lead, paula = st.pos, st.players[2].pos
    expect(dist(paula, lead) >= 20, f"Paula apart from Ness {lead}", paula)
    expect(st.camera == ((lead[0] + paula[0]) // 2, (lead[1] + paula[1]) // 2), "camera on the midpoint", st.camera)

    # Talk to the sailor, Yes: the boarding cutscene starts
    s.do("press L; until said:Kraken 5000 advance; until input 300 advance; press A")
    s.do("until in:ACTIONSCRIPT_WAIT 300 advance; 30 -")
    st = s.state()
    expect("ACTIONSCRIPT_WAIT" in st.state, "the boarding cutscene running", st.state)
    expect(dist(st.players[2].pos, st.pos) <= 24, f"Paula snapped behind Ness {st.pos}", st.players[2].pos)
    expect(st.camera == st.pos, "the camera on Ness during the cutscene", st.camera_line)
    ctx.shot(s, "cutscene: Paula on Ness's trail")

    # The voyage, the Kraken (debug win) and the landing
    s.command_menu(8000)
    s.do("debug on; press SELECT+START; until idle 8000 advance", timeout=300)
    st = s.state()
    expect(st.idle == "yes" and st.pos[1] < 5000, "landed in Scaraba with control back", st.state)
    land = st.pos
    expect(all(dist(o, (0, 0)) <= 32 for o in st.follow_offsets.values()), "the Party together", st.follow)

    # Both recover: P2 and P1 walk apart, each on their own pad
    s.do("P2 30 RIGHT")
    st = s.state()
    expect(st.players[2].pos[0] > land[0] + 30 and st.pos == land, "Paula walks right, Ness stays", st.players_line)
    s.do("30 LEFT")
    st2 = s.state()
    expect(st2.pos[0] < land[0] - 20, "Ness walks left", st2.pos)
    expect(st2.players[2].pos == st.players[2].pos, "Paula stays", st2.players_line)
    ctx.shot(s, "Scaraba: both walk again")

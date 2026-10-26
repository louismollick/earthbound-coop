"""Shared body of m1_leash_edge (320x240) and m1_leash_native (256x224)."""

from lib import expect, expect_in_leash, leash_margin


def leash(ctx, binary=None):
    s = ctx.session(save="27-Kraken", players=2, binary=binary)
    st = s.kraken_spot()
    lead = st.pos
    (w, h) = st.view
    mx, _ = leash_margin(st.view)
    cap = w - 2 * mx

    # P2 walks right until the leash stops Paula: the spread is the cap, the view centres on the
    # midpoint and Paula stands the margin inside the right edge
    s.do("P2 300 RIGHT")
    st = s.state()
    paula = st.players[2].pos
    expect(st.pos == lead, f"the Leader still at {lead}", st.pos)
    expect(paula[0] - lead[0] == cap, f"Paula stopped {cap} px right of Ness (the leash)", paula)
    expect(st.camera == ((lead[0] + paula[0]) // 2, lead[1]), "the camera on the midpoint", st.camera_line)
    expect(st.on_screen(paula)[0] == w - mx, f"Paula {mx} px inside the right edge", st.on_screen(paula))
    expect_in_leash(st, paula, "Paula")
    expect_in_leash(st, lead, "Ness")
    ctx.shot(s, f"{w}x{h}: leash stops P2 at the right edge")

    # The leash holds the Leader too: walking away from Paula, Ness stays put
    s.do("60 LEFT")
    st = s.state()
    expect(st.pos == lead, f"Ness held at {lead} by the leash", st.pos)

    # Walking toward Paula frees the leash: Ness moves right, then Paula can go further right
    s.do("30 RIGHT")
    st = s.state()
    lead2 = st.pos
    expect(lead2[0] > lead[0] + 20, f"Ness walked right from {lead}", lead2)
    s.do("P2 60 RIGHT")
    st = s.state()
    paula2 = st.players[2].pos
    expect(paula2[0] - lead2[0] == cap, f"Paula again {cap} px right of Ness {lead2}", paula2)
    expect_in_leash(st, paula2, "Paula")
    expect_in_leash(st, st.pos, "Ness")
    ctx.shot(s, f"{w}x{h}: the leash moves with the Party")

"""P2's Walker slows down in shallow water exactly like the Leader (Deep Darkness swamp)."""

from lib import expect


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    st = s.kraken_spot()
    x0 = st.players[2].pos[0]
    s.do("P2 30 LEFT")
    land = x0 - s.state().players[2].pos[0]
    expect(land >= 35, "Paula walked 35+ px left on sand in 30 frames", land)

    # The Deep Darkness swamp: shallow water everywhere around (5600,7712)
    s.do("teleport 5600 7712 4; 30 -")
    st = s.state()
    expect("shallow-water" in st.state, "the Leader in shallow water", st.state)
    x0 = st.players[2].pos[0]
    s.do("P2 30 LEFT")
    st = s.state()
    water = x0 - st.players[2].pos[0]
    expect(water > 0 and water * 10 <= land * 6, f"Paula slowed down in the water (sand: {land} px)", water)
    ctx.shot(s, "P2 wading")

    # Ness takes the same 30 frames from the same spot on the vanilla path: the same distance
    lx = st.pos[0]
    s.do("30 LEFT")
    ness = lx - s.state().pos[0]
    expect(ness == water, f"Ness waded as far as Paula ({water} px)", ness)

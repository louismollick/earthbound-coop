"""The camera centres on the midpoint of two Walkers apart.

At the top edge of the map (Onett, above the meteorite) the camera is still the midpoint: vanilla's CENTER_SCREEN
never clamps to the map, and the midpoint's view never reaches further past the edge than vanilla would with either
Walker leading.
"""

from lib import expect, expect_in_leash


def midpoint(a, b):
    return ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    st = s.kraken_spot()
    expect(st.camera == st.pos, "the camera on the Party before anyone walks", st.camera_line)

    s.do("hold P2 UP+RIGHT; 50 LEFT; hold P2 -; 2 -")
    st = s.state()
    lead, paula = st.pos, st.players[2].pos
    expect(paula[0] > lead[0] + 60 and paula[1] < lead[1] - 30, f"Paula up and right of Ness {lead}", paula)
    expect(st.camera == midpoint(lead, paula), f"the camera on the midpoint of {lead} and {paula}", st.camera_line)
    expect_in_leash(st, lead, "Ness")
    expect_in_leash(st, paula, "Paula")
    ctx.shot(s, "camera on the midpoint")

    # A window doesn't move the camera
    s.do("press B; wait 20")
    expect(s.state().camera == midpoint(lead, paula), "the camera unmoved with a window open", st.camera_line)
    s.do("press B; wait 20")

    # The map's top edge: the camera stays on the midpoint (no clamp, as vanilla)
    s2 = ctx.session("edge", save="35-Onett", players=2)
    s2.boot()
    s2.do("flag 11 1; teleport 2075 128 4; 30 -; P2 200 UP; P2 100 LEFT")
    st = s2.state()
    lead, paula = st.pos, st.players[2].pos
    _, h = st.view
    expect(paula[1] < 100, "Paula near the top edge of the map", paula)
    expect(st.camera == midpoint(lead, paula), f"the camera on the midpoint of {lead} and {paula}", st.camera_line)
    top = st.camera[1] - h // 2
    expect(top >= min(lead[1], paula[1]) - h // 2, "the view no further past the edge than vanilla's", top)
    expect_in_leash(st, paula, "Paula")
    ctx.shot(s2, "midpoint at the map edge")

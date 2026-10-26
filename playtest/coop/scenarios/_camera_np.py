"""Shared body of m1_camera_3p and m1_camera_4p: Walkers spread out in the Scaraba desert (27-Kraken)."""

from lib import expect, expect_in_leash, leash_margin


def spread_out(ctx, players, holds):
    """``holds``: {player: direction} held at once for 300 frames while P1 stands still."""
    s = ctx.session(save="27-Kraken", players=players)
    st = s.kraken_spot()
    lead = st.pos
    s.do("; ".join(f"hold P{p} {d}" for p, d in holds.items()) + "; 300 -; " + "; ".join(f"hold P{p} -" for p in holds))
    s.do("2 -")
    st = s.state()
    p = st.players
    walkers = [st.pos] + [p[n].pos for n in holds]
    (w, h), (mx, my) = st.view, leash_margin(st.view)
    xs, ys = [q[0] for q in walkers], [q[1] for q in walkers]
    expect(st.pos == lead, f"the Leader still at {lead}", st.pos)
    expect(max(xs) - min(xs) == w - 2 * mx, f"the leash holds the x spread at {w - 2 * mx}", walkers)
    expect(max(ys) - min(ys) <= h - 2 * my, f"the y spread within {h - 2 * my}", walkers)
    centre = ((min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2)
    expect(st.camera == centre, f"the camera on the Walkers' box centre {centre}", st.camera_line)
    for q, name in zip(walkers, ["Leader"] + [p[n].walker for n in holds]):
        expect_in_leash(st, q, name)
    ctx.shot(s, f"{players} Players spread to the leash")

    # The Leader is leashed too: walking away from the right-most Walker is stopped
    s.do("60 LEFT")
    st2 = s.state()
    expect(st2.pos[0] >= max(xs) - (w - 2 * mx), "Ness can't stretch the Party past the leash", st2.pos)
    for n in holds:
        expect_in_leash(st2, st2.players[n].pos, st2.players[n].walker)

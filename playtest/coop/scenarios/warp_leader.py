"""Y+R held for a second (COOP_WARP_FRAMES) on the free overworld warps a Player to the Leader.

- 27-Kraken, Summers promenade, 2 Players: P2 walks Paula away. Y+R for 59 frames does nothing; for 60
  Paula's chain regroups behind Ness, and P2 walks her on from there. Y+R held under the HP/PP window
  does nothing, then or after it closes.
- 02-Sharks hotel (P2 the Companion): Mr. Saturn across the lobby is next to Ness after Y+R.
"""

from lib import expect


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    s.boot()
    s.do("flag 11 1; teleport 7400 2870 6; 30 -")
    s.do("P2 60 RIGHT")
    st = s.state()
    lead, paula = st.pos, st.players[2].pos
    expect(dist(paula, lead) >= 50, f"Paula walked away from Ness {lead}", paula)

    s.do("P2 59 Y+R; P2 2 -")
    expect(s.state().players[2].pos == paula, "59 frames of Y+R: no warp", s.state().players_line)
    s.do("P2 60 Y+R; P2 2 -")
    st = s.state()
    expect(
        st.pos == lead and dist(st.players[2].pos, lead) <= 24, f"60 frames: Paula next to Ness {lead}", st.players_line
    )
    ctx.shot(s, "Y+R: Paula back with Ness")
    back = st.players[2].pos
    s.do("P2 30 RIGHT")
    expect(s.state().players[2].pos[0] > back[0] + 10, "and P2 walks her on", s.state().players_line)

    # Not under a window
    s.do("P2 40 RIGHT")
    paula = s.state().players[2].pos
    s.do("press B; wait 20; P2 90 Y+R")
    expect(
        "HPPP" in s.state().state and s.state().players[2].pos == paula,
        "no warp under the HP/PP window",
        s.state().players_line,
    )
    s.do("press B; wait 20; P2 2 -")
    st = s.state()
    expect(st.idle == "yes" and st.players[2].pos == paula, "nor once it closed", st.players_line)

    # Mr. Saturn
    c = ctx.session("companion", save="02-Sharks", players=2)
    c.boot()
    c.do("flag 11 1; wait 4")
    lead = c.state().pos
    c.do(f"companion 2 {lead[0] + 100} {lead[1] + 8} 6; wait 2")
    expect(dist(c.state().players[2].pos, lead) >= 90, "Mr. Saturn across the lobby", c.state().players[2])
    c.do("P2 60 Y+R; P2 2 -")
    sat = c.state().players[2]
    expect(not sat.hidden and dist(sat.pos, lead) <= 24, f"Y+R: Mr. Saturn next to Ness {lead}", sat)
    ctx.shot(c, "Y+R: Mr. Saturn next to Ness")

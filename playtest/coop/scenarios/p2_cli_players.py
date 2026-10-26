"""--players 2 auto-joins P2 at startup: the same state as pressing Start, from frame 0."""

from lib import expect


def run(ctx):
    s = ctx.session(players=2)
    st = s.state("boot")
    p = st.players
    expect(p[1].joined and p[2].joined, "P1 and P2 joined right after start with --players 2", st.players_line)
    expect(not p[3].joined and not p[4].joined, "P3 and P4 not joined", st.players_line)

    st = s.new_game()
    p = st.players
    expect(p[2].joined and p[2].owns == [] and p[2].spectator, "P2 joined as a Spectator in the bedroom", p[2])
    expect(p[1].owns == ["Ness"] and p[1].walker == "Ness", "P1 owns and walks Ness", p[1])
    ctx.shot(s, "bedroom --players 2")

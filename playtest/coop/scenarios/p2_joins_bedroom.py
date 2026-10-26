"""P2 presses Start in Ness's bedroom: P2 joins as a Spectator (Paula and Poo aren't in the Party)."""

from lib import expect


def run(ctx):
    s = ctx.session()
    st = s.new_game()
    p = st.players
    expect(p[1].joined and not any(p[n].joined for n in (2, 3, 4)), "only P1 joined in the bedroom", st.players_line)
    expect(p[1].owns == ["Ness"] and p[1].walker == "Ness", "P1 owns and walks Ness", p[1])
    expect(p[1].pos == st.pos, f"P1's Walker at the Leader's position {st.pos}", p[1].pos)
    ctx.shot(s, "bedroom solo")

    s.do("P2 press START")
    p = s.players()
    expect(p[2].joined, "P2 joined after 'P2 press START'", p[2])
    expect(p[2].owns == [] and p[2].walker is None and p[2].spectator, "P2 owns no Hero and spectates", p[2])
    expect(p[1].owns == ["Ness"] and p[1].walker == "Ness", "P1 still owns and walks Ness", p[1])
    expect(not p[3].joined and not p[4].joined, "P3 and P4 not joined", f"{p[3]} {p[4]}")

    # P2 holding a direction doesn't move anyone yet (M0), and nobody leaves or joins by idling
    before = s.state().pos
    s.do("hold P2 RIGHT; wait 300; release P2")
    st = s.state()
    expect(st.pos == before, f"Ness still at {before} while only P2 held RIGHT", st.pos)
    p = st.players
    expect(sum(pl.joined for pl in p.values()) == 2, "still 2 Players after 300 frames", st.players_line)
    ctx.shot(s, "P2 joined")

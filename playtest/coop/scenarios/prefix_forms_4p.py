"""Every Player-prefix form joins P3 and P4; ownership deals Heroes round-robin by join order."""

from lib import expect


def run(ctx):
    s = ctx.session()
    s.new_game()
    s.do("press P3 START")
    p = s.players()
    expect(p[3].joined and not p[2].joined, "P3 joined by 'press P3 START', P2 not", f"{p[2]} {p[3]}")

    # until with a Player after MAX: P4 taps START while nothing is printed
    out = s.do("until text 60 P4 START*")
    expect(any(ln.startswith("UNTIL TIMEOUT") for ln in out), "UNTIL TIMEOUT", out)
    p = s.players()
    expect(p[4].joined, "P4 joined by 'until text 60 P4 START*'", p[4])

    s.do("P2 10 START")
    p = s.players()
    expect(all(p[n].joined for n in (1, 2, 3, 4)), "all four Players joined", [str(x) for x in p.values()])
    # Join order P1, P3, P4, P2: Ness -> P1, Paula -> P3, Jeff -> P4, Poo -> P2
    expect(p[1].owns == ["Ness"] and p[1].walker == "Ness", "P1 owns Ness", p[1])
    for n in (2, 3, 4):
        expect(p[n].owns == [] and p[n].spectator, f"P{n} a Spectator (no owned Hero in the Party)", p[n])

    # Plain commands still mean P1: Ness walks
    before = s.state().pos
    s.do("20 LEFT")
    after = s.state().pos
    expect(after[0] < before[0], f"Ness moved left from {before} on a plain '20 LEFT'", after)
    ctx.shot(s, "4 Players joined")

"""M2: Run Away is the Leader's Owner's: it is on the turn's first command menu, which reads its Owner.

Vanilla puts Run Away only on the first command menu of the turn. Menus are claimed (M7), so Run Away is on the
first menu claimed.

12-Zombies, 2 Players (P1: Ness, Jeff; P2: Paula). P1 claims Ness's menu; P2 steers to Run Away on it and
presses A: nothing happens. P1 picks it: the Party tries to get away and nobody else gets a menu (vanilla).
With Ness asleep, P2 claims first: Paula's menu carries Run Away, and P2 picks it (decisions, PLAN.md).
"""

from lib import expect

BATTLE = "teleport 4000 9300 4; until battle 900 DOWN|DOWN|LEFT; until input 1500; wait 10"
TO_RUN = "press RIGHT; wait 5; press RIGHT; wait 5; press DOWN; wait 5"


def run(ctx):
    s = ctx.session(save="12-Zombies", players=2)
    s.boot()
    s.do(BATTLE)
    s.do("press A; until input 300; wait 10")  # P1 claims
    expect(s.title() == "Ness P1", "Ness's menu first", s.windows())
    before = s.windows()
    s.do(TO_RUN.replace("press", "P2 press") + "; P2 press A; wait 10")
    expect(s.windows() == before, "P2's Run Away attempt on Ness's menu changes nothing", s.windows())
    s.do(TO_RUN)
    opts, sel = s.menu()
    expect(opts[sel] == "Run Away", "P1's cursor on Run Away", (opts, sel))
    ctx.shot(s, "P1 on Run Away")
    said = s.said("press A; until input 3000 P2 advance")
    expect("tried to get away" in said, "the Party tries to run", said)
    expect("Pray" not in said, "no Paula menu after the run", said)

    # Ness asleep: Paula's menu comes first and carries Run Away, so P2 runs.
    s = ctx.session("asleep", save="12-Zombies", players=2)
    s.boot()
    s.do("status 1 3 1; " + BATTLE)
    expect(s.state().choose == [1, 2], "Ness asleep: P1 (Jeff) and P2 (Paula) may claim", s.state().players_line)
    s.do("P2 press A; until input 300; wait 10")
    st = s.state()
    expect(s.title() == "Paula P2" and st.focus == "P2", "Paula's menu first, focus P2", (s.windows(), st.players_line))
    opts, _ = s.menu()
    expect("Run Away" in opts, "Run Away on Paula's (first) menu", opts)
    before = s.windows()
    s.do("press RIGHT; wait 5; press RIGHT; wait 5; press A; wait 10")
    expect(s.windows() == before, "P1's presses on Paula's menu change nothing", s.windows())
    s.do("P2 press DOWN; wait 5; P2 press RIGHT; wait 5; P2 press RIGHT; wait 5")
    opts, sel = s.menu()
    expect(opts[sel] == "Run Away", "P2's cursor on Run Away", (opts, sel))
    ctx.shot(s, "Ness asleep: P2 on Run Away")
    said = s.said("P2 press A; until input 3000 advance")
    expect("tried to get away" in said, "P2 made the Party try to run", said)

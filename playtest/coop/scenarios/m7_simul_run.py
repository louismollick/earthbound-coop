"""M7: with claimed menus Run Away stays with the Leader's Owner, whatever order the menus are claimed in.

28-Scaraba, 2 Players (P1: Ness, Jeff; P2: Paula, Poo). P2 claims first: Paula's menu has no Run Away or
Auto Fight. P2 defends. P1 then claims Ness's menu, which has both, and picks Run Away: the Party tries to get
away, and Paula's Defend is discarded (nobody else acts for the Party this turn, as after a vanilla Run).
"""

from _claims import SCARABA_BATTLE, at_menu, claim, defend, option, waiting
from lib import expect


def run(ctx):
    s = ctx.session(save="28-Scaraba", players=2)
    s.boot()
    s.do(SCARABA_BATTLE)
    waiting(s, [1, 2])
    claim(s, 2)
    at_menu(s, "Paula P2", 2)
    opts, _ = s.menu()
    expect("Run Away" not in opts and "Auto Fight" not in opts, "no Run Away or Auto Fight on Paula's menu", opts)
    ctx.shot(s, "P2 claimed first: Paula's menu, no Run Away")
    defend(s, 2)

    waiting(s, [1, 2])
    claim(s, 1)
    at_menu(s, "Ness P1", 1)
    opts, _ = s.menu()
    expect("Run Away" in opts and "Auto Fight" in opts, "Run Away and Auto Fight on Ness's later menu", opts)
    option(s, 1, ["RIGHT", "RIGHT", "DOWN"], "Run Away")
    ctx.shot(s, "P1 on Run Away, Ness claimed second")
    said = s.said("press A; until input 3000 P2 advance; wait 10")
    expect("tried to get away" in said, "the Party tries to run", said)
    expect("is on guard" not in said, "Paula's Defend discarded by the run", said)
    for wrong in ("Paula attacks", "Jeff attacks", "Poo attacks"):
        expect(wrong not in said, f"no '{wrong}' after the run", said)

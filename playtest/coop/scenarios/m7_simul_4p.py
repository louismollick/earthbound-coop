"""M7: simultaneous battle input, 4 Players claiming in a scrambled order. Every Hero gets its Owner's command.

28-Scaraba, one Hero per Player. P3 claims first (Jeff's menu has no Run Away: it stays on Ness's, the
Leader's), and P1 presses A while it is open, which queues P1: Ness's menu opens right after Jeff's with no further press. Then the battle waits for
P2 and P4; P4 claims Poo, and Paula's menu opens by itself for P2. Jeff and Poo defend, Ness and Paula attack,
and the round's text says exactly that. Every other Player's presses on each menu change nothing.
"""

from _claims import SCARABA_BATTLE, at_menu, attack, claim, defend, ignored, waiting
from lib import expect


def run(ctx):
    s = ctx.session(save="28-Scaraba", players=4)
    s.boot()
    s.do(SCARABA_BATTLE)
    waiting(s, [1, 2, 3, 4])
    ctx.shot(s, "waiting on all four")
    claim(s, 3)
    at_menu(s, "Jeff P3", 3)
    expect("Run Away" not in s.menu()[0], "no Run Away on Jeff's menu, though claimed first", s.menu())
    ignored(s, [1, 2, 4], "P1, P2 and P4 on Jeff's menu")
    ignored(s, [1], "P1's A on Jeff's menu (it queues P1)", buttons=("A",))
    defend(s, 3)

    at_menu(s, "Ness P1", 1)
    expect("Run Away" in s.menu()[0], "Run Away on Ness's (the Leader's) menu, claimed second", s.menu())
    ignored(s, [2, 3, 4], "P2, P3 and P4 on Ness's menu")
    attack(s, 1)

    waiting(s, [2, 4])
    ctx.shot(s, "waiting on P2 and P4")
    claim(s, 4)
    at_menu(s, "Poo P4", 4)
    ignored(s, [1, 2, 3], "P1, P2 and P3 on Poo's menu")
    defend(s, 4)

    at_menu(s, "Paula P2", 2)  # the last Player with a Hero left: no claim needed
    ctx.shot(s, "Paula P2, opened by itself")
    ignored(s, [1, 3, 4], "P1, P3 and P4 on Paula's menu")
    said = attack(s, 2, reader=1)
    for want in ("Jeff is on guard", "Ness attacks", "Poo is on guard", "Paula attacks"):
        expect(want in said, f"'{want}' in the round's text", said)
    for wrong in ("Jeff attacks", "Ness is on guard", "Poo attacks", "Paula is on guard"):
        expect(wrong not in said, f"no '{wrong}'", said)
    waiting(s, [1, 2, 3, 4])
    s.do("debug on; press A; until input 300; press SELECT+START; until idle 1500 advance")
    expect(s.state().idle == "yes", "the battle ends", s.state().state)

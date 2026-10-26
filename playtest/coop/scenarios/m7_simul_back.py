"""M7: B on a claimed command menu goes back to that Player's previous Hero, never to another Player's.

28-Scaraba, 2 Players (P1: Ness, Jeff; P2: Paula, Poo).
- P1 claims Ness (the first menu, with Run Away); B there reopens Ness's menu. P1 attacks.
- P2 claims Paula; B at P2's first Hero reopens Paula's, not Ness's (P1's choice stays). P2 defends.
- P2 claims Poo; B goes back to Paula, P2's previous Hero. P2 re-picks Paula's attack, claims Poo, defends.
- Jeff's menu opens by itself; P1's B goes back to Ness (no Run Away now: Paula has chosen). Ness defends,
  then Jeff attacks.
The round's text shows the final choices: Ness on guard, Paula attacks, Poo on guard, Jeff attacks.
"""

from _claims import SCARABA_BATTLE, at_menu, attack, claim, defend, waiting
from lib import expect


def back(s, p):
    s.do(f"{'P2 ' if p == 2 else ''}press B; until input 300; wait 10")


def run(ctx):
    s = ctx.session(save="28-Scaraba", players=2)
    s.boot()
    s.do(SCARABA_BATTLE)
    waiting(s, [1, 2])
    claim(s, 1)
    at_menu(s, "Ness P1", 1)
    back(s, 1)
    at_menu(s, "Ness P1", 1)
    expect("Run Away" in s.menu()[0], "Ness's menu still the first, with Run Away", s.menu())
    attack(s, 1)

    waiting(s, [1, 2])
    claim(s, 2)
    at_menu(s, "Paula P2", 2)
    back(s, 2)
    at_menu(s, "Paula P2", 2)
    ctx.shot(s, "P2's B at its first Hero: Paula again")
    defend(s, 2)

    waiting(s, [1, 2])
    claim(s, 2)
    at_menu(s, "Poo P2", 2)
    back(s, 2)
    at_menu(s, "Paula P2", 2)
    attack(s, 2)
    waiting(s, [1, 2])
    claim(s, 2)
    at_menu(s, "Poo P2", 2)
    defend(s, 2)

    at_menu(s, "Jeff P1", 1)
    back(s, 1)
    at_menu(s, "Ness P1", 1)
    expect("Run Away" not in s.menu()[0], "Ness reopened as a later menu: no Run Away", s.menu())
    ctx.shot(s, "P1's B from Jeff: Ness again")
    defend(s, 1)
    at_menu(s, "Jeff P1", 1)
    said = attack(s, 1, reader=2)
    for want in ("Ness is on guard", "Paula attacks", "Poo is on guard", "Jeff attacks"):
        expect(want in said, f"'{want}' in the round's text", said)
    for wrong in ("Ness attacks", "Paula is on guard"):
        expect(wrong not in said, f"no '{wrong}'", said)

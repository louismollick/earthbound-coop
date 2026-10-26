"""M7: simultaneous battle input, 2 Players. Whoever presses A first gets the next command menu.

28-Scaraba (P1: Ness, Jeff; P2: Paula, Poo), Scaraba desert encounter. Session "p2first": P2 claims first and
picks Paula's attack before Ness's menu has opened; that first menu carries Run Away and Auto Fight, Ness's
doesn't. P1 then claims Ness, P2 Poo, and Jeff's menu opens by itself (only P1 has a Hero left). Session
"p1first" picks the same attacks in vanilla order. Both rounds tell the attacks in the same order: initiative
decides who acts, not who chose first.
"""

from _claims import SCARABA_BATTLE, actors, at_menu, attack, claim, ignored, waiting
from lib import expect

MENUS = {
    "p2first": [(2, "Paula"), (1, "Ness"), (2, "Poo"), (1, "Jeff")],
    "p1first": [(1, "Ness"), (2, "Paula"), (1, "Jeff"), (2, "Poo")],
}


def run(ctx):
    orders = {}
    for name, menus in MENUS.items():
        s = ctx.session(name, save="28-Scaraba", players=2)
        s.boot()
        s.do(SCARABA_BATTLE)
        said = ""
        for i, (p, hero) in enumerate(menus):
            other = 3 - p
            left = sorted({q for q, _ in menus[i:]})
            if len(left) > 1:
                waiting(s, left)
                if i == 0 and name == "p2first":
                    ctx.shot(s, "waiting for a claim: P1 P2")
                claim(s, p)
            at_menu(s, f"{hero} P{p}", p)
            opts, _ = s.menu()
            expect(("Run Away" in opts) == (i == 0), f"Run Away only on the turn's first menu ({hero})", opts)
            if name == "p2first" and i == 0:
                ctx.shot(s, "P2 claimed first: Paula P2 with Run Away")
            ignored(s, [other], f"P{other} on {hero}'s menu")
            said = attack(s, p, reader=other if i == len(menus) - 1 else None)
        orders[name] = actors(said)
        expect(len(orders[name]) == 4, f"{name}: all four Heroes attack", said)
        st = s.state()
        expect(st.choose == [1, 2], f"{name}: round 2 waits for a claim again", st.players_line)
        s.do("debug on; press A; until input 300; press SELECT+START; until idle 1500 advance")
    expect(orders["p2first"] == orders["p1first"], "the same attack order whoever chose first", orders)

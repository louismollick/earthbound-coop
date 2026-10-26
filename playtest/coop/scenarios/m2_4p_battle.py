"""M2: in a 4-Player battle each Owner's input decides their own Hero's command.

28-Scaraba (Ness, Paula, Jeff, Poo), one Hero per Player. Scaraba desert encounter. On each Hero's menu
the three other Players press buttons and nothing changes; the Owner then picks: Ness and Poo Bash,
Paula and Jeff Defend, and the round's text shows exactly those. Jeff's Goods window reads only P3.

Menus are claimed (M7): P1's A opens Ness's menu, and the others' A presses on it queue them in Party order.
P2's B on Paula's menu, its first Hero, reopens Paula's menu: it never goes back to P1's Ness.
"""

from lib import expect

PLAYERS = (1, 2, 3, 4)


def menu_turn(s, title, owner):
    st = s.state()
    expect(s.title() == title and st.focus == f"P{owner}", f"the {title} command menu, focus P{owner}", st.players_line)
    before = s.windows()
    s.do("; ".join(f"P{p} press A; wait 8; P{p} press DOWN; wait 8" for p in PLAYERS if p != owner))
    after = s.windows()
    expect(after == before, f"the other Players' presses on {title}'s menu change nothing", f"{before} -> {after}")


def pick(s, owner, moves, option):
    s.do("; ".join(f"P{owner} press {m}; wait 5" for m in moves))
    opts, sel = s.menu()
    expect(opts[sel] == option, f"P{owner}'s cursor on {option}", (opts, sel))
    s.do(f"P{owner} press A; until input 300; wait 10")


def run(ctx):
    s = ctx.session(save="28-Scaraba", players=4)
    s.boot()
    s.do("teleport 1400 5600 4; until battle 1500 RIGHT|DOWN|LEFT|UP; until input 1500; wait 10")
    s.do("press A; until input 300; wait 10")  # P1 claims the first menu

    menu_turn(s, "Ness P1", 1)
    pick(s, 1, [], "Bash")
    s.do("P1 press A; until input 300; wait 10")  # the target
    menu_turn(s, "Paula P2", 2)
    s.do("P2 press B; until input 300; wait 10")  # back at P2's first Hero: Paula's menu again
    menu_turn(s, "Paula P2", 2)
    pick(s, 2, ["RIGHT", "DOWN"], "Defend")
    menu_turn(s, "Jeff P3", 3)
    ctx.shot(s, "Jeff's menu, tag P3")
    # Goods: Jeff's inventory reads only P3; P3's B closes it
    s.do("P3 press RIGHT; wait 5; P3 press A; until input 300; wait 10")
    goods = s.windows()
    expect(s.title() != "Jeff P3" and len(goods) > 3, "Jeff's Goods open", goods)
    s.do("; ".join(f"P{p} press DOWN; wait 8; P{p} press A; wait 8; P{p} press B; wait 8" for p in (1, 2, 4)))
    expect(s.windows() == goods, "the other Players' presses in Jeff's Goods change nothing", s.windows())
    s.do("P3 press B; until input 300; wait 10")
    expect(s.title() == "Jeff P3", "P3's B back to Jeff's menu", s.windows())
    pick(s, 3, ["DOWN"], "Defend")
    menu_turn(s, "Poo P4", 4)
    ctx.shot(s, "Poo's menu, tag P4")
    pick(s, 4, [], "Bash")
    said = s.said("P4 press A; until input 3000 P3 advance")
    for want in ("Ness attacks", "Paula is on guard", "Jeff is on guard", "Poo attacks"):
        expect(want in said, f"'{want}' in the round's text", said)

    expect(s.state().choose == [1, 2, 3, 4], "round 2 waits for a claim", s.state().players_line)
    s.do("press A; until input 300; wait 10")
    menu_turn(s, "Ness P1", 1)
    s.do("debug on; press SELECT+START; until idle 1500 advance")
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", "back on the overworld, focus P1", st.players_line)

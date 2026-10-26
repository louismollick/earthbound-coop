"""M2: in a 2-Player battle each Hero's commands come from its Owner's pad, and nobody else's.

28-Scaraba (Ness, Paula, Jeff, Poo): P1 owns Ness and Jeff, P2 owns Paula and Poo. Scaraba desert
encounter. Each command menu is titled with its Owner's tag and the focus is that Owner's; the other
Player's presses change nothing on screen (command menu, PSI menus, the "Whom?" ally select, the enemy
target select). Ness casts Lifeup on Paula, Paula and Poo defend, Jeff shoots, and the battle text says
so. Any Player advances it.
"""

from lib import expect


def unchanged(s, presses, what):
    """Run ``presses`` (another Player's) and check no window, title or cursor changed."""
    before = s.windows()
    s.do(presses)
    after = s.windows()
    expect(after == before, f"{what}: nothing changes", f"{before} -> {after}")


def menu_turn(s, title, focus):
    st = s.state()
    expect(s.title() == title and st.focus == focus, f"the {title} command menu, focus={focus}", st.players_line)


def defend(s, player):
    s.do(f"P{player} press RIGHT; wait 5; P{player} press DOWN; wait 5")
    opts, sel = s.menu()
    expect(opts[sel] == "Defend", f"P{player}'s cursor on Defend", (opts, sel))
    return s.said(f"P{player} press A; until input 300; wait 10")


def run(ctx):
    s = ctx.session(save="28-Scaraba", players=2)
    s.boot()
    s.do("teleport 1400 5600 4; until battle 1500 RIGHT|DOWN|LEFT|UP; until input 1500; wait 10")

    # Ness (P1): PSI > Recover > Lifeup > Whom? Paula. P2 can't touch any of it.
    menu_turn(s, "Ness P1", "P1")
    ctx.shot(s, "Ness's menu, tag P1")
    unchanged(s, "P2 press DOWN; wait 10; P2 press A; wait 10; P2 press B; wait 10", "P2 on Ness's menu")
    s.do("press DOWN; wait 5; press A; until input 300; wait 10")
    unchanged(s, "P2 press DOWN; wait 10; P2 press A; wait 10", "P2 on Ness's PSI menu")
    s.do("press DOWN; wait 5; press A; until input 300; wait 10; press A; until input 300; wait 10")
    expect(s.menu() == (["Ness", "Paula", "Jeff", "Poo"], 0), "Ness's Lifeup asking Whom?", s.windows())
    unchanged(s, "P2 press RIGHT; wait 10; P2 press A; wait 10", "P2 on Whom?")
    s.do("press RIGHT; wait 5; press A; until input 300; wait 10")

    # Paula (P2): Defend. P1's presses do nothing.
    menu_turn(s, "Paula P2", "P2")
    ctx.shot(s, "Paula's menu, tag P2")
    unchanged(s, "press RIGHT; wait 10; press DOWN; wait 10; press A; wait 10; press B; wait 10", "P1 on Paula's menu")
    defend(s, 2)

    # Jeff (P1): Shoot at the first enemy; P2 can't move the enemy target.
    menu_turn(s, "Jeff P1", "P1")
    unchanged(s, "P2 press A; wait 10; P2 press DOWN; wait 10", "P2 on Jeff's menu")
    s.do("press A; until input 300; wait 10")
    expect(any(ln.startswith("WIN w49*| To ") for ln in s.windows()), "Jeff's enemy target select", s.windows())
    unchanged(s, "P2 press RIGHT; wait 10; P2 press A; wait 10", "P2 on the enemy target select")
    s.do("press A; until input 300; wait 10")

    # Poo (P2): Defend.
    menu_turn(s, "Poo P2", "P2")
    unchanged(s, "press A; wait 10; press DOWN; wait 10", "P1 on Poo's menu")
    said = defend(s, 2)  # the round starts: defending goes first
    said += s.said("until input 3000 P2 advance")
    for want in ("Ness tried", "Paula is on guard", "Jeff attacks", "Poo is on guard"):
        expect(want in said, f"'{want}' in the round's text", said)

    # Round 2 is back on Ness's menu, P1's again; the debug instant win exits.
    menu_turn(s, "Ness P1", "P1")
    s.do("debug on; press SELECT+START; until idle 1500")
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", "back on the overworld, focus P1 (unlocked)", st.players_line)

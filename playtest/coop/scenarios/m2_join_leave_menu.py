"""M2 review: a join or leave while a battle menu is open moves that menu to the Hero's new Owner at once.

28-Scaraba (Ness, Paula, Jeff, Poo), Scaraba desert encounter. Ownership follows the join order, so a join or
leave can hand an open menu (or its Goods/PSI/target child) to another Player:

- 2 Players, Poo's menu (P2's): P3 joins, Poo becomes P1's. Tag "Poo P1", focus P1, P2 can't touch it.
- Solo, Paula's Goods open: P2 joins, Paula becomes P2's. Only P2 moves the Goods cursor, and B back shows
  "Paula P2".
Menus are claimed (M7): each menu here is opened by its Owner's A.

- 4 Players, Jeff's menu (P3's): P2 leaves, so the deal shifts and Jeff becomes P4's. Tag "Jeff P4", focus
  P4, P3 can't touch it any more. (P3 can't be the one leaving: its Select+Start, held on its own menu,
  backs out of the menu as in vanilla.)
"""

from lib import expect

BATTLE = "teleport 1400 5600 4; until battle 1500 RIGHT|DOWN|LEFT|UP; until input 1500; wait 10"


def at_menu(s, title, focus):
    st = s.state()
    expect(
        s.title() == title and st.focus == focus, f"the '{title}' menu, focus {focus}", (s.windows(), st.players_line)
    )


def ignored(s, presses, what):
    before = s.windows()
    s.do(presses)
    expect(s.windows() == before, f"{what}: nothing changes", s.windows())


def obeys(s, presses, what):
    before = s.windows()
    s.do(presses)
    expect(s.windows() != before, f"{what}: the menu moves", s.windows())


def defend(s, player):
    """P``player`` picks Defend on the open menu (RIGHT, DOWN on every first-row layout)."""
    pre = f"P{player} " if player > 1 else ""
    s.do(f"{pre}press RIGHT; wait 5; {pre}press DOWN; wait 5")
    opts, sel = s.menu()
    expect(opts[sel] == "Defend", f"P{player}'s cursor on Defend", (opts, sel))
    s.do(f"{pre}press A; until input 300; wait 10")


def run(ctx):
    # 2 Players, Poo's menu: P3 joins
    s = ctx.session("join2p", save="28-Scaraba", players=2)
    s.boot()
    s.do(BATTLE)
    for title, owner in (("Ness P1", 1), ("Paula P2", 2), ("Jeff P1", 1)):
        s.do(f"{'P2 ' if owner == 2 else ''}press A; until input 300; wait 10")  # claim
        at_menu(s, title, f"P{owner}")
        defend(s, owner)
    at_menu(s, "Poo P2", "P2")  # the last Player with a Hero left: no claim
    s.do("P3 press START; wait 10")
    expect(s.state().players[3].joined, "P3 joined", s.state().players_line)
    at_menu(s, "Poo P1", "P1")
    ctx.shot(s, "P3 joined on Poo's menu: Poo P1")
    ignored(s, "P2 press RIGHT; wait 8; P2 press DOWN; wait 8", "P2 on Poo's menu after the join")
    obeys(s, "press RIGHT; wait 8", "P1 on Poo's menu")

    # Solo, Paula's Goods: P2 joins
    s = ctx.session("join_solo", save="28-Scaraba")
    s.boot()
    s.do(BATTLE)
    at_menu(s, "Ness", "P1")
    defend(s, 1)
    at_menu(s, "Paula", "P1")
    s.do("press RIGHT; wait 5; press A; until input 300; wait 10")
    goods = s.windows()
    expect(any(ln.startswith("WIN w2*") for ln in goods), "Paula's Goods open", goods)
    s.do("P2 press START; wait 10")
    st = s.state()
    expect(st.players[2].joined and st.focus == "P2", "P2 joined, focus P2 in Paula's Goods", st.players_line)
    ignored(s, "press DOWN; wait 8; press RIGHT; wait 8", "P1 in Paula's Goods after the join")
    obeys(s, "P2 press DOWN; wait 8", "P2 in Paula's Goods")
    s.do("P2 press B; until input 300; wait 10")
    at_menu(s, "Paula P2", "P2")

    # 4 Players, Jeff's menu: P2 leaves
    s = ctx.session("leave4p", save="28-Scaraba", players=4)
    s.boot()
    s.do(BATTLE)
    for title, owner in (("Ness P1", 1), ("Paula P2", 2), ("Jeff P3", 3)):
        s.do(f"{f'P{owner} ' if owner > 1 else ''}press A; until input 300; wait 10")  # claim
        at_menu(s, title, f"P{owner}")
        if owner < 3:
            defend(s, owner)
    s.do("hold P2 SELECT+START; wait 130; release P2; wait 10")
    expect(not s.state().players[2].joined, "P2 left", s.state().players_line)
    at_menu(s, "Jeff P4", "P4")
    ctx.shot(s, "P2 left on Jeff's menu: Jeff P4")
    ignored(s, "P3 press RIGHT; wait 8; P3 press DOWN; wait 8", "P3 on Jeff's menu after the leave")
    obeys(s, "P4 press RIGHT; wait 8", "P4 on Jeff's menu")

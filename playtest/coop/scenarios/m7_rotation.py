"""M7: Battle rotation. In a Solo Chapter battle the solo Hero's menu goes round the Players, one turn each.

34-Magicant (Ness alone). Every Player but Ness's Owner (P1) is absent, so turn 1 is P1's, turn 2 P2's, and so
on, round and round. Each turn the menu is titled with the rotation Player's tag, the focus is theirs, and the
other Players' presses change nothing. Whoever holds the menu may pick Run Away. The rotation carries into the
next battle instead of restarting at the Owner. A turn whose menu is skipped (the enemies' surprise opening)
still uses up its Player's place.
"""

from lib import expect

# Pink maze: an enemy group a few steps in (Electro Swoosh + French Kiss of Death)
FIRST_BATTLE = "teleport 5160 3673 4; until battle 300 DOWN"
WIN = "debug on; press SELECT+START; until idle 1500 advance; debug off"


def in_battle(s):
    """In a battle, or about to be (an enemy touched, the swirl running)."""
    st = s.state().state
    return "BATTLE" in st or "idle=battle" in st


def battle(s, route):
    """Walk ``route`` (then back and forth) until a battle starts; wait for the first command menu.

    Returns the number of turns that went by without a menu: 1 after the enemies' surprise opening, else 0.
    """
    s.do(route)
    for d in ("LEFT", "RIGHT", "UP", "DOWN") * 6:
        if in_battle(s):
            break
        s.do(f"until battle 120 {d}")
    expect(in_battle(s), "a battle", s.state().state)
    return int("opening attack" in s.said("until input 1500; wait 10"))


def turn(s, players, holder):
    """Ness's menu belongs to P``holder``: tag, focus, and nobody else's presses count."""
    st = s.state()
    title = f"Ness P{holder}"
    expect(s.title() == title and st.focus == f"P{holder}", f"the '{title}' menu, focus P{holder}", st.players_line)
    before = s.windows()
    s.do("; ".join(f"P{p} press RIGHT; wait 8; P{p} press A; wait 8" for p in players if p != holder))
    expect(s.windows() == before, f"the other Players' presses on P{holder}'s turn change nothing", s.windows())


def defend(s, holder, players):
    s.do(f"P{holder} press RIGHT; wait 5; P{holder} press DOWN; wait 5")
    opts, sel = s.menu()
    expect(opts[sel] == "Defend", f"P{holder}'s cursor on Defend", (opts, sel))
    other = next(p for p in players if p != holder)  # a Player who can't touch the menu reads the text out
    said = s.said(f"P{holder} press A; until input 3000 P{other} advance; wait 10")
    expect("Ness is on guard" in said, f"P{holder}'s Defend ran", said)


def run(ctx):
    # 2 Players: P1, P2, P1; P2 tries Run Away on its turn
    s = ctx.session(save="34-Magicant", players=2)
    s.boot()
    battle(s, FIRST_BATTLE)
    turn(s, (1, 2), 1)
    ctx.shot(s, "2P turn 1: Ness P1")
    defend(s, 1, (1, 2))
    turn(s, (1, 2), 2)
    ctx.shot(s, "2P turn 2: Ness P2, an absent Player")
    s.do("P2 press RIGHT; wait 5; P2 press RIGHT; wait 5; P2 press DOWN; wait 5")
    opts, sel = s.menu()
    expect(opts[sel] == "Run Away", "P2's cursor on Run Away", (opts, sel))
    said = s.said("P2 press A; until input 3000 P1 advance; wait 10")
    expect("tried to get away" in said, "P2 made Ness try to run", said)
    turns = 2
    if in_battle(s):  # the run failed: turn 3 is P1's again; win it
        turn(s, (1, 2), 1)
        s.do(WIN)
        turns = 3
    expect(s.state().idle == "yes", "back on the overworld", s.state().state)
    turns += battle(s, FIRST_BATTLE)
    next_holder = turns % 2 + 1  # the next battle's first menu is turn turns + 1
    turn(s, (1, 2), next_holder)
    ctx.shot(s, f"2P next battle: rotation carried, Ness P{next_holder}")

    # 3 Players: P1, P2, P3, P1; then the next battle opens on P2
    s = ctx.session("3p", save="34-Magicant", players=3)
    s.boot()
    battle(s, FIRST_BATTLE)
    for holder in (1, 2, 3):
        turn(s, (1, 2, 3), holder)
        if holder == 3:
            ctx.shot(s, "3P turn 3: Ness P3")
        defend(s, holder, (1, 2, 3))
    turn(s, (1, 2, 3), 1)
    s.do(WIN)
    turns = 4 + battle(s, FIRST_BATTLE)
    turn(s, (1, 2, 3), turns % 3 + 1)

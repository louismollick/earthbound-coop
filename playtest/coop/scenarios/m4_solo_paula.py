"""Solo Chapter: Paula's kidnapping, from the Dept Store blackout to her rejoining at Monotoli, at 2 and 4 Players.

Not a one-Hero chapter: the Party drops to Ness and Jeff, so Paula's Owner (P2) is absent and walks a Mr. Saturn
(with 4 Players P4, Poo's Owner, already does: Poo hasn't joined yet) and there is no Battle rotation.

- START, 18-DeptStore: the store door (TEXT_DOOR_556) arms hotspot 11; the 1F escalator to 2F crosses it and arms
  hotspot 10; a teleport back to 1F (hotspots survive it) and a walk right across x 5040 runs the blackout
  (MSG_EVT2_FOUR_DEPT_PAULA_KIDNAP). P2 walks Paula away from Ness just before it, so her chain is independent
  when she is taken. After it P2 walks a Mr. Saturn, P1 (and P3 with Jeff) walk their own Heroes.
- A dark-store battle (teleport to 2F, walk into Musica / Mystical Record): each Hero's command menu goes to its
  Owner, absent Players are never offered one and their presses change nothing.
- END, 21-Monotoli (Ness, Jeff; the Moonside to Monotoli stretch in between isn't played): the "Stop!" scene, then
  Monotoli's confession (Check from 5620,6010) adds Paula back. Her Owner walks her again and the Mr. Saturn is
  gone; Poo's Owner (4 Players) keeps his.
"""

from _claims import at_menu, claim, ignored, option, waiting
from _solo import expect_companions_walk, expect_party, expect_walk_apart, owner
from lib import expect

STORE_DOOR = "teleport 3588 4323 0; wait 5; 30 UP+RIGHT; until idle 300"  # Fourside street -> store 1F
ESCALATOR_2F = "teleport 4984 6858 6; wait 5; 60 LEFT; until idle 600"  # 1F escalator -> 2F, through hotspot 11
F2 = (4715, 6704)


def turn(s, n, label):
    """One battle turn: Ness's menu is P1's, Jeff's his Owner's; absent Players get nothing. Both Defend."""
    jeff = owner("Jeff", n)
    absent = [q for q in range(1, n + 1) if q not in (1, jeff)]
    if jeff != 1:  # two Players with Heroes left: the battle waits for a claim, never from an absent Player
        waiting(s, [1, jeff])
        claim(s, 1)
    at_menu(s, "Ness P1", 1)
    ignored(s, list(range(2, n + 1)), f"{label}: everyone else on Ness's menu")
    option(s, 1, ["RIGHT", "DOWN"], "Defend")
    s.do("press A; until input 300; wait 10")
    at_menu(s, f"Jeff P{jeff}", jeff)  # the last Player with a Hero left: opens by itself
    ignored(s, [q for q in range(1, n + 1) if q != jeff], f"{label}: everyone else on Jeff's menu")
    option(s, jeff, ["RIGHT", "DOWN"], "Defend")
    reader = absent[0]  # an absent Player can still read the round's text out
    said = s.said(f"hp 1 999; hp 3 999; P{jeff} press A; until input 3000 P{reader} advance; wait 10")
    for hero in ("Ness", "Jeff"):
        expect(f"{hero} is on guard" in said, f"{label}: '{hero} is on guard'", said)
    expect("Paula" not in said and "Poo" not in said, f"{label}: no absent Hero acts", said)


def kidnap(ctx, n):
    s = ctx.session(f"store{n}p", save="18-DeptStore", players=n)
    s.boot()
    expect_party(s.state(), n, ("Ness", "Paula", "Jeff"))
    s.do(STORE_DOOR)
    s.do(ESCALATOR_2F)
    expect(s.state().pos == F2, f"the 2F escalator top {F2}", s.state().pos)
    s.do("teleport 4984 6845 2; wait 5; P2 10 DOWN")
    st = s.state()
    paula = st.players[2].pos
    expect(paula[1] > st.pos[1] + 5, "P2 walked Paula away from Ness", st.players_line)

    # START: the blackout takes Paula
    s.do("until text 200 RIGHT")
    said = s.said("until idle 3000 advance")
    st = s.state()
    expect("Gwaaaa" in said and st.idle == "yes", "the blackout ran and control is back", said + st.state)
    expect(
        st.party.startswith("PARTY 1:Ness") and st.party.count("|") == 1 and "3:Jeff" in st.party,
        "Ness, Jeff",
        st.party,
    )
    expect("2:" not in st.follow, "no Paula sprite left behind", st.follow)
    expect_party(st, n, ("Ness", "Jeff"))
    s.do("wait 2")
    expect_companions_walk(s, "Ness", n, "20 DOWN")
    if n >= 3:
        expect_walk_apart(s, n, {3: "20 LEFT"})
    ctx.shot(s, f"{n}P: Paula taken, P2 walks a Mr. Saturn")

    # A dark-store battle
    s.do(f"teleport {F2[0]} {F2[1]} 6; wait 5; until battle 1500 LEFT|UP|LEFT|DOWN; until input 1500 advance; wait 10")
    expect("BATTLE" in s.state().state, "a dark-store battle", s.state().state)
    turn(s, n, "turn 1")
    if owner("Jeff", n) != 1:
        ctx.shot(s, f"{n}P: battle waits on P1 and P{owner('Jeff', n)} only")
    turn(s, n, "turn 2")
    if owner("Jeff", n) != 1:
        waiting(s, [1, owner("Jeff", n)])
        claim(s, 1)
    s.do("debug on; press SELECT+START; until idle 1500 advance; debug off")
    st = s.state()
    expect(st.idle == "yes" and "BATTLE" not in st.state, "back on the overworld after the win", st.state)
    expect_party(st, n, ("Ness", "Jeff"))


def rejoin(ctx, n):
    s = ctx.session(f"monotoli{n}p", save="21-Monotoli", players=n)
    s.boot()
    expect_party(s.state(), n, ("Ness", "Jeff"))
    s.do("teleport 5632 6040 0; wait 5; until text 120 UP; until idle 3000 advance")
    # END: Monotoli's confession. Ness's Owner Checks him and holds the lock throughout
    s.do("teleport 5620 6010 2; wait 5; press L")
    s.do("until in:SELECTION_MENU 8000 advance", timeout=300)
    st = s.state()
    expect("2:Paula" in st.party, "Paula back in the Party during the talk", st.party)
    expect(st.focus == "P1 locked", "P1 holds the lock", st.players_line)
    before = s.windows()
    s.do("; ".join(f"P{q} press RIGHT; wait 5; P{q} press A; wait 10" for q in range(2, n + 1)))
    expect(s.windows() == before, "nobody else answers Monotoli", s.windows())
    said = s.said("press RIGHT; wait 5; press A; until idle 3000 advance; wait 2")
    st = s.state()
    expect("goodbye" in said and st.idle == "yes", "the talk ends with control", said + st.state)
    expect_party(st, n, ("Ness", "Paula", "Jeff"))
    expect(st.players[2].walker == "Paula" and not st.players[2].companion, "P2's Mr. Saturn gone", st.players_line)
    moves = {2: "20 DOWN", 1: "20 LEFT"} if n == 2 else {2: "20 DOWN", 3: "20 UP"}
    expect_walk_apart(s, n, moves)
    ctx.shot(s, f"{n}P: Paula rejoined, P2 walks her again")


def run(ctx):
    for n in (2, 4):
        kidnap(ctx, n)
        rejoin(ctx, n)

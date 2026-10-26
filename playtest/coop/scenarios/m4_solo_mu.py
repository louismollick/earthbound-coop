"""Solo Chapter: Poo's Mu training, from the Magic Cake dream to Poo joining at the Summers beach, at 2 and 4 Players.

23-Summers (Ness, Paula, Jeff). The cake (npc1069) replaces the Party with Poo in the Dalaam palace: Poo's Owner
(P2 of 2, P4 of 4) walks him and has the focus, every other Player walks a Mr. Saturn. The dream has enemies off
(flag 11), so for the battle the scenario turns them on and teleports Poo into the Magicant pink maze (a cheat; the
dream itself has no battle): Battle rotation gives Poo's menu to each Player in turn,
round to the Owner again. Back in the dream, the Mu training (rope top 4988,3840: four Yes answers, from Poo's
Owner only) and the Master's talk (npc1089) end the chapter: the Party is restored on the Summers beach, the
Companions are gone and everyone walks their own Hero again.
"""

from _solo import (
    advance_until,
    expect_companions_walk,
    expect_restored,
    expect_solo,
    expect_walk_apart,
    find_battle,
    owner,
    rotation_battle,
)
from lib import expect

CAKE = "flag 617 1; teleport 6000 2000 0; wait 30; teleport 5184 2884 0; wait 30; 20 LEFT; 20 UP; 20 RIGHT"
PALACE = (6848, 8288)


def play(ctx, n):
    s = ctx.session(f"{n}p", save="23-Summers", players=n)
    s.boot()
    o = owner("Poo", n)

    # START: the cake dream. Ness's Owner (P1) talks to the baker and reads the dream out
    s.do(f"{CAKE}; press A; until input 300; press A")
    out = s.do("until idle 8000 advance", timeout=300)
    st = s.state()
    expect(any(ln.startswith("UNTIL met") for ln in out) and st.idle == "yes", "the dream ends with control", st.state)
    expect(st.pos == PALACE and st.party.startswith("PARTY 4:Poo") and "|" not in st.party, "Poo alone", st.party)
    expect_solo(st, "Poo", n)
    s.do("wait 2")
    expect_companions_walk(s, "Poo", n, "20 DOWN")
    ctx.shot(s, f"{n}P: Poo's Owner P{o} and the Mr. Saturns in the palace")
    s.do(f"P{o} 20 DOWN")
    expect(s.state().pos != PALACE, f"P{o} walks Poo", s.state().pos)

    # A battle: the dream has no enemies (flag 11), so turn them on and take Poo to the Magicant pink maze; after
    # the win, enemies off again and back to the dream's Mu rope
    find_battle(s, f"flag 11 0; teleport 5160 3673 4; wait 5; until battle 300 P{o} DOWN", o)
    st = rotation_battle(ctx, s, "Poo", n, f"{n}P")
    expect_solo(st, "Poo", n)
    s.do("flag 11 1")

    # The Mu training: only Poo's Owner answers
    s.do(f"teleport 4988 3840 0; wait 5; until text 120 P{o} UP; until in:SELECTION_MENU 4000 P{o} advance")
    expect_solo(s.state(), "Poo", n)
    others = "; ".join(f"P{q} press A; wait 10" for q in range(1, n + 1) if q != o)
    before = s.windows()
    s.do(others)
    expect(s.windows() == before, "nobody but Poo's Owner answers the spirit", s.windows())
    for _ in range(3):
        s.do(f"wait 10; P{o} press A; until in:SELECTION_MENU 4000 P{o} advance")
    said = s.said(f"wait 10; P{o} press A; until idle 4000 P{o} advance")
    expect("completed your" in said, "the training completed", said)
    expect_solo(s.state(), "Poo", n)

    # END: the Master sends Poo to Ness; the Party is restored on the Summers beach
    s.do(f"teleport 6841 8296 0; wait 5; P{o} press A; until input 300 P{o}; P{o} press A")
    s.do(f"until said:might 5000 P{o} advance; until in:TELEPORT_TO 1000 P{o} advance")
    # Back on the beach Ness leads: the arrival's text goes to whoever has the focus
    _, said = advance_until(s, "idle", 3000)
    st = s.state()
    expect("Poo joined you" in said and st.idle == "yes", "Poo joined at the beach", said + st.state)
    expect(st.party.count("|") == 3, "Ness, Paula, Jeff, Poo", st.party)
    expect_restored(st, n)
    expect("companion" not in st.players_line, "every Companion despawned", st.players_line)
    moves = {q: m for q, m in {2: "20 DOWN", 3: "20 RIGHT", 4: "20 UP"}.items() if q <= n}
    if n == 2:
        moves[1] = "20 LEFT"
    expect_walk_apart(s, n, moves)
    ctx.shot(s, f"{n}P: Poo joined, everyone walks their own Hero")


def run(ctx):
    play(ctx, 2)
    play(ctx, 4)

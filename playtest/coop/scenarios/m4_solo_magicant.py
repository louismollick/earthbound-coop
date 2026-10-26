"""Solo Chapter: Magicant, from the Fire Spring sanctuary to waking up in Saturn Valley, at 2 and 4 Players.

33-FireSpring. Carbon Dog (debug win; flag 185, the Pink Cloud melody this relay save skipped, set so all eight
melodies are there), the door to the sanctuary and the walk onto its hotspot. The melody and the flashback take
the Party into Magicant with Ness alone: P1 walks him, every other Player walks a Mr. Saturn. The first Flying Man
(npc1313, his house teleported to) joins as a Guest, so the first absent Player stops walking Mr. Saturn and
stands in for him. Battle rotation runs in the Nightmare fight (Ness's menu goes round every Player; Ness at
999 HP per turn so the test is about who picks), then a debug win plays the montage and the wakeup: the Party is
back (Ness, Paula, Jeff, Poo), the Flying Man and the Companions are gone and everyone walks their own Hero.
"""

from _solo import expect_companions_walk, expect_restored, expect_solo, expect_walk_apart, rotation_battle
from lib import expect

CARBON_DOG = (
    "flag 185 1; teleport 3344 6410 0; wait 5; 30 UP; press A; until input 300; press A; "
    "until battle 3000 advance; until input 2000 advance; press A; until input 300; "
    "debug on; press SELECT+START; until idle 6000 advance; debug off"
)
# The door behind Carbon Dog, then the walk onto the sanctuary hotspot (6128,9831). Every other Walker takes the same
# steps (``hold``), so the leash (192 px of spread at 256x224) never holds Ness back
DOOR = "until in:DOOR_TRANSITION 120 UP; until idle 600"
SANCTUARY_WALK = [
    (30, "DOWN"), (100, "DOWN+LEFT"), (100, "LEFT"), (200, "UP"), (28, "DOWN"), (7, "UP"), (17, "DOWN+LEFT"),
    (9, "UP+LEFT"), (2, "UP"), (12, "DOWN"), (15, "DOWN+LEFT"), (4, "DOWN+LEFT"), (39, "DOWN+LEFT"), (22, "UP+LEFT"),
    (7, "UP"), (28, "UP+LEFT"), (9, "UP+LEFT"), (2, "UP"), (38, "UP+LEFT"), (32, "UP"), (200, "UP"),
]  # fmt: skip


def sanctuary(n):
    """The walk as commands: P1 steps until text shows, with P2..Pn holding the same direction."""
    cmds = []
    for frames, d in SANCTUARY_WALK:
        cmds += [f"hold P{q} {d}" for q in range(2, n + 1)]
        cmds.append(f"until text {frames} {d}")
    return "; ".join(cmds + [f"release P{q}" for q in range(2, n + 1)])


MAGICANT = (6000, 4440)
NIGHTMARE = "teleport 496 9140 0; wait 10; press L; until battle 3000 advance"


def talk_to_flying_man(s):
    """Talk to the first Flying Man (npc1313) from right below him.

    He walks up to whoever enters, so where he stands a few frames after the (re)load varies a little: try a few
    spots.
    """
    said = ""
    for x, y in ((8080, 8172), (8080, 8168), (8086, 8172), (8080, 8176)):
        said = s.said(f"teleport {x} {y} 0; wait 1; press A; until input 300; press A; until idle 2000 advance")
        if "joins" in said:
            break
    return said


def play(ctx, n):
    s = ctx.session(f"{n}p", save="33-FireSpring", players=n)
    s.boot()

    # START: Carbon Dog, the sanctuary, the melody and the flashback
    s.do(CARBON_DOG)
    s.do(DOOR)
    s.do(sanctuary(n))
    st = s.state()
    expect("PROCESS_INTERACTION" in st.state, "the sanctuary's event running", st.state)
    s.do("until idle 9000 advance; until idle 9000 advance", timeout=300)
    st = s.state()
    expect(st.idle == "yes" and st.pos == MAGICANT, f"Magicant with control at {MAGICANT}", st.state)
    expect(st.party.startswith("PARTY 1:Ness") and "|" not in st.party, "Ness alone", st.party)
    expect_solo(st, "Ness", n)
    expect_companions_walk(s, "Ness", n, "20 DOWN")
    ctx.shot(s, f"{n}P: Magicant, Ness and the Mr. Saturns")

    # A Flying Man joins: the first absent Player stands in for him instead of walking Mr. Saturn
    s.do("flag 11 1")
    said = talk_to_flying_man(s)
    expect("Flying Man joins" in said, "the Flying Man joined", said)
    s.do(f"teleport {MAGICANT[0]} {MAGICANT[1]} 4; wait 5")
    st = s.state()
    expect_solo(st, "Ness", n, guests=("Flying Man",))
    s.do("P2 20 DOWN")
    st2 = s.state()
    expect(st2.players[2].pos[1] > st.players[2].pos[1] + 10 and st2.pos == st.pos, "P2 walks him", st2.players_line)
    ctx.shot(s, f"{n}P: P2 stands in for the Flying Man")

    # The Nightmare: Battle rotation (the Flying Man is a Guest, so Ness is still the only Hero)
    s.do(NIGHTMARE)
    rotation_battle(ctx, s, "Ness", n, f"{n}P Nightmare", win=False)

    # END: debug win, the Sanctuary montage, the wakeup in Saturn Valley
    s.do("heal; debug on; 4 SELECT+START; until said:powers 6000 advance; debug off", timeout=300)
    out = s.do("until idle 8000 advance", timeout=300)
    st = s.state()
    expect(any(ln.startswith("UNTIL met") for ln in out) and st.idle == "yes", "awake with control", st.state)
    expect(st.party.count("|") == 3, "Ness, Paula, Jeff, Poo", st.party)
    expect_restored(st, n)
    expect("companion" not in st.players_line and "standin" not in st.players_line, "no Companion", st.players_line)
    moves = {q: m for q, m in {2: "20 DOWN", 3: "20 RIGHT", 4: "20 UP"}.items() if q <= n}
    expect_walk_apart(s, n, moves)
    ctx.shot(s, f"{n}P: awake in Saturn Valley, everyone walks their own Hero")


def run(ctx):
    play(ctx, 2)
    play(ctx, 4)

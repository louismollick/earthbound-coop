"""Solo Chapter: Jeff in Winters, from Paula's prayer to the Sky Runner crash in Threed, at 2 and 4 Players.

START (10-ToThreed, Ness and Paula): `warp threed` and a teleport into the Threed jail skip the bus and the
hotel zombie trap (the jail's cell door, npc479, only checks flags 14 and 541). Ness's Owner Checks the cell
door: Paula's prayer replaces the Party with Jeff in his Snow Wood room (EEVENT1 MSG_WINS_POLANESS). Jeff's
Owner (P1 of 2, P3 of 4) walks him, everyone else walks a Mr. Saturn.

Middle and END (11-Winters, Jeff and Bubble Monkey): the first absent Player stands in for the Monkey. A
battle with the Cave Boy at 182,4340: Battle rotation gives Jeff's menu to each Player in turn, round to the
Owner, who wins it (debug). In Dr. Andonuts' lab (teleport to the lab door; Jeff's Owner
Checks Andonuts at his spawn point, donut No, Stonehenge Yes) everyone spreads out, then Jeff walks into the
Sky Runner (npc623's area, 7824,2872): everyone regroups for the ride, the flight crashes in Threed and the
Party is Ness and Paula in the jail (plus the Monkey), each walked by their Owner; the cutscene's focus moves
from Jeff's Owner to Ness's with the Leader. Jeff joins (Yes): every
Player walks their own Hero again, and the Companions of Players whose Heroes are back are gone (at 4 Players
P4 keeps one: Poo hasn't joined yet).
"""

from _solo import (
    advance_until,
    expect_companions_walk,
    expect_party,
    expect_solo,
    expect_walk_apart,
    find_battle,
    owner,
    rotation_battle,
)
from lib import expect

JEFF_ROOM = (7232, 1880)
JAIL = (6752, 10064)


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def play_start(ctx, n):
    """10-ToThreed: Paula's prayer in the Threed jail hands the story to Jeff alone."""
    s = ctx.session(f"start{n}p", save="10-ToThreed", players=n)
    s.boot()
    o = owner("Jeff", n)
    s.do("warp threed; wait 5; teleport 6864 10035 0; wait 3; press L; until text 60")
    out = s.do("until idle 8000 advance", timeout=300)
    st = s.state()
    expect(any(ln.startswith("UNTIL met") for ln in out) and st.idle == "yes", "the prayer ends with control", st.state)
    expect(st.pos == JEFF_ROOM and st.party.startswith("PARTY 3:Jeff") and "|" not in st.party, "Jeff alone", st.party)
    expect_solo(st, "Jeff", n)
    s.do("wait 2")
    expect_companions_walk(s, "Jeff", n, "20 RIGHT")
    ctx.shot(s, f"{n}P: Jeff's Owner P{o} wakes in Snow Wood, Mr. Saturns around")
    s.do(f"P{o} 16 DOWN")
    expect(s.state().pos != JEFF_ROOM, f"P{o} walks Jeff", s.state().pos)


def talk_andonuts(s, o):
    """Jeff's Owner Checks Dr. Andonuts where he spawns (he wanders off quickly); read up to the donut question."""
    for _ in range(5):
        said = s.said(f"teleport 7987 2908 0; P{o} press L; until in:SELECTION_MENU 600 P{o} advance")
        if "donut" in said:
            return
        s.do(f"until idle 600 P{o} advance; wait 30")
    raise AssertionError("never reached Dr. Andonuts")


def play_sky_runner(ctx, n):
    """11-Winters: the Monkey's Stand-in, Battle rotation, the Sky Runner ride and the crash that ends the chapter."""
    s = ctx.session(f"sky{n}p", save="11-Winters", players=n)
    st = s.boot()
    o = owner("Jeff", n)
    standin = next(q for q in range(1, n + 1) if q != o)
    expect_solo(st, "Jeff", n, guests=("Bubble Monkey",))

    # A battle with the Cave Boy, won by Jeff's Owner (debug); the Monkey's Stand-in is unchanged afterwards
    find_battle(s, f"flag 11 0; teleport 182 4380 0; wait 5; until battle 600 P{o} UP|DOWN", o)
    st = rotation_battle(ctx, s, "Jeff", n, f"{n}P Cave Boy")
    expect_solo(st, "Jeff", n, guests=("Bubble Monkey",))
    s.do("flag 11 1")

    # The lab: Andonuts offers the Sky Runner; only Jeff's Owner answers
    s.do(f"teleport 320 4930 0; wait 3; until text 300 P{o} UP")
    talk_andonuts(s, o)
    s.do(f"P{o} press RIGHT; P{o} press A; until in:SELECTION_MENU 3000 P{o} advance")
    said = s.said(f"P{o} press A; until idle 3000 P{o} advance")
    st = s.state()
    expect("Get in" in said and st.idle == "yes", "Andonuts offers the Sky Runner", said[-100:] + st.state)
    expect_solo(st, "Jeff", n, guests=("Bubble Monkey",))

    # Everyone spreads out; Jeff walks into the Sky Runner (no teleport: it would drop npc623's area check)
    s.do(f"P{standin} 30 DOWN; P{standin} 20 RIGHT")
    for q in range(1, n + 1):
        if q not in (o, standin):
            s.do(f"P{q} 20 RIGHT")
    s.do(f"P{o} 8 DOWN; P{o} 111 LEFT")
    st = s.state()
    monkey = st.players[standin].pos
    expect(dist(monkey, st.pos) > 100, "the Monkey far from Jeff before boarding", st.players_line)
    ctx.shot(s, f"{n}P: lab, the Monkey's Stand-in P{standin} away from Jeff")
    s.do(f"until text 120 P{o} UP")
    st = s.state()
    expect("PROCESS_INTERACTION" in st.state, "the Sky Runner boarding", st.state)
    expect(dist(st.players[standin].pos, st.pos) <= 16, "the Monkey regrouped onto Jeff", st.players_line)

    # The flight and the crash: Ness and Paula (plus the Monkey) in the Threed jail, Jeff's question
    met, _ = advance_until(s, "in:SELECTION_MENU", 12000)
    st = s.state()
    expect(met, "the crash cutscene reaches Jeff's question", st.state)
    expect(st.party.count("|") == 1 and "Ness" in st.party and "Paula" in st.party, "Ness and Paula", st.party)
    expect(st.pos == JAIL, f"Ness in the jail at {JAIL}", st.state)
    for q in range(1, n + 1):
        w = st.players[q]
        if w.pos:
            expect(dist(w.pos, JAIL) <= 24, f"P{q}'s {w.walker} landed with the Party", w)
    ctx.shot(s, f"{n}P: the Sky Runner crashed, Ness and Paula in the jail")

    # END: Jeff joins
    expect(st.focus == "P1", "the focus on P1, Ness's Owner, for Jeff's question", st.players_line)
    said = s.said("P1 press A; until idle 3000 P1 advance")
    st = s.state()
    expect("Jeff joined you" in said and st.idle == "yes", "Jeff joined", said[-80:] + st.state)
    expect(st.party.count("|") == 2, "Ness, Paula, Jeff", st.party)
    party = ("Ness", "Paula", "Jeff")
    expect_party(st, n, party)
    if n == 2:
        expect("companion" not in st.players_line, "every Companion despawned", st.players_line)
    moves = {q: m for q, m in {2: "20 RIGHT", 3: "20 DOWN"}.items() if q <= n}
    if n == 2:
        moves[1] = "20 UP"  # P1 walks Ness, the Leader; Jeff trails him
    expect_walk_apart(s, n, moves)
    ctx.shot(s, f"{n}P: Jeff joined, everyone walks their own Hero")


def run(ctx):
    play_start(ctx, 2)
    play_start(ctx, 4)
    play_sky_runner(ctx, 2)
    play_sky_runner(ctx, 4)

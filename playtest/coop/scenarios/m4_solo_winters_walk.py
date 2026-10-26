"""Solo Chapter: Jeff's Winters handoffs played through, from Paula's prayer to the Tessie ride, at 2 and 4 Players.

One session per Player count from 10-ToThreed, the Party changing four times on the way: Jeff alone, Tony joins,
Tony leaves, Bubble Monkey joins. Jeff's Owner (P1 of 2, P3 of 4) walks Jeff; the first absent Player in join
order (P2 of 2, P1 of 4) stands in for whichever Guest is there and walks a Mr. Saturn in between; every other
absent Player walks a Mr. Saturn throughout.

Shortcuts (each skips a walk, never a handoff):
- `warp threed` and a teleport into the Threed jail skip the bus and the hotel zombie trap (as m4_solo_winters).
- `give 36 3` hands Jeff the Pop gun, skipping Maxwell's key and the locker room; the gate only checks the item.
- `teleport 344 3380 0` skips the walk from the Winters drugstore to the Tessie watchers' camp on Lake Tess.
- `teleport 662 3384 4` skips the walk from the cook's tent to the shore; the hotspots the stew armed survive it.

Played: Tony wakes as Jeff leaves his room and joins (the Stand-in walks Tony); the dorm corridor, the stairs and
the front door (TEXT_DOOR_389 arms the gate hotspot) with everyone walking along; at the gate Tony leaves while his
Stand-in has walked him away, and Jeff climbs over on his back; the drugstore, where Nancy sells the gum (only
Jeff's Owner answers) and Bubble Monkey joins; the cook's stew and the night; then, with the Monkey's Stand-in
walked away and holding a direction throughout, Jeff walks into the shore hotspot and the Monkey's gum calls Tessie,
who carries the Party across Lake Tess. Everyone lands together and walks their own Walker again.
"""

from _solo import advance_until, expect_companions_walk, expect_solo, owner, talk_to, walk_to
from lib import expect

JEFF_ROOM = (7232, 1880)
LAKE_NORTH = (864, 4240)  # where Tessie drops the Party


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def moved_toward(a, b, d):
    """``b`` is ``a`` moved in pad direction ``d`` (at least 4 px that way, at most 2 px across)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    want = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}[d]
    along = dx * want[0] + dy * want[1]
    across = abs(dx * want[1]) + abs(dy * want[0])
    return along >= 4 and across <= 2


def standin_walks(s, q, guest, dirs=("UP", "LEFT", "DOWN", "RIGHT"), tries=12):
    """P``q`` walks the Guest it stands in for (it moves the way P``q`` presses); the Leader stays put.

    Bubble Monkey may be off on his own for a while (hiding, distracted, running back: his vanilla tick runs
    whenever his chain is snapped, after a ride or a door), and his Stand-in only gets him back when he is back
    in his normal mode, so the presses are retried with a pause in between.
    """
    for i in range(tries):
        d = dirs[i % len(dirs)]
        st = s.state()
        s.do(f"P{q} 20 {d}")
        st2 = s.state()
        w = st2.players[q]
        expect(w.walker == guest and w.standin, f"P{q} stands in for {guest}", st2.players_line)
        if moved_toward(st.players[q].pos, w.pos, d):
            expect(st2.pos == st.pos, f"the Leader stays while P{q} walks {guest}", st2.state)
            return st2
        s.do("wait 30")
    expect(False, f"P{q} walks {guest}", st2.players_line)


def play(ctx, n):
    o = owner("Jeff", n)
    sub = next(q for q in range(1, n + 1) if q != o)  # the first absent Player: the Stand-in
    s = ctx.session(f"winters{n}p", save="10-ToThreed", players=n)
    s.boot()

    # Paula's prayer: Jeff alone in his room
    s.do("warp threed; wait 5; teleport 6864 10035 0; wait 3; press L; until text 60")
    met, _ = advance_until(s, "idle", 8000)
    st = s.state()
    expect(met and st.pos == JEFF_ROOM and st.party == "PARTY 3:Jeff L1 HP 30/30 PP 0/0", "Jeff alone", st.party)
    expect_solo(st, "Jeff", n)

    # Tony wakes as Jeff heads for the door, and joins: the Stand-in walks him
    s.do(f"until text 400 P{o} RIGHT")
    met, said = advance_until(s, "idle", 3000)
    expect(met and "Tony joined you" in said, "Tony joined", said[-120:])
    st = s.state()
    expect_solo(st, "Jeff", n, guests=("Tony",))
    standin_walks(s, sub, "Tony")
    ctx.shot(s, f"{n}P: Tony joined, P{sub} stands in for him")

    # Out of the room, down the stairs and out the front door, everyone walking along
    s.do(f"P{o} 16 DOWN; until in:DOOR_TRANSITION 300 P{o} RIGHT; until idle 300")
    walk_to(s, 7760, 3076, o, n)
    s.do(f"until in:DOOR_TRANSITION 120 P{o} LEFT; until idle 300")
    st = s.state()
    expect(st.pos == (7736, 2568), "the dorm's ground floor", st.state)
    s.do("give 36 3")  # the Pop gun (shortcut)
    st = walk_to(s, 8000, 2568, o, n)
    s.do(f"until in:DOOR_TRANSITION 60 P{o} RIGHT; until idle 300")
    st = s.state()
    expect(st.pos == (504, 2192), "outside the dorm, by the gate", st.state)
    expect_solo(st, "Jeff", n, guests=("Tony",))

    # The gate: Tony leaves while his Stand-in has walked him away, then Jeff climbs over on his back
    s.do(f"P{sub} 30 LEFT")
    st = s.state()
    expect(dist(st.players[sub].pos, st.pos) >= 24, "Tony walked away from Jeff", st.players_line)
    s.do(f"P{o} 240 DOWN; wait 30")  # the gate hotspot: Tony steps out of the Party, no text
    st = s.state()
    expect(st.idle == "yes" and st.pos == (504, 2272), "Jeff at the gate", st.state)
    expect("Tony" not in st.players_line and "8:" not in st.follow, "Tony gone from the Party", st.players_line)
    expect_solo(st, "Jeff", n)
    said = s.said(f"P{o} press L; until text 120")
    met, more = advance_until(s, "idle", 3000)
    expect(met and "climb over the gate" in said + more, "Jeff climbed over the gate", said + more)
    st = s.state()
    expect(st.pos[1] > 2300, "Jeff over the gate", st.state)
    expect_solo(st, "Jeff", n)
    s.do("wait 2")
    expect_companions_walk(s, "Jeff", n, "20 LEFT")
    ctx.shot(s, f"{n}P: over the gate, Tony gone, P{sub} walks a Mr. Saturn")

    # The drugstore: Nancy's gum (only Jeff's Owner answers), then Bubble Monkey joins
    walk_to(s, 631, 2318, o, n)
    s.do(f"P{o} 20 DOWN")
    walk_to(s, 694, 2345, o, n)
    s.do(f"until in:DOOR_TRANSITION 120 P{o} UP; until idle 300")
    expect(s.state().pos == (7624, 2536), "in the drugstore", s.state().state)
    s.do(f"P{o} 16 DOWN")
    walk_to(s, 7556, 2552, o, n)
    walk_to(s, 7556, 2521, o, n)
    walk_to(s, 7523, 2521, o, n)
    s.do(f"P{o} 8 UP; P{o} press L")
    met, said = advance_until(s, "in:SELECTION_MENU", 900)
    expect(met and "do you want him" in said, "Nancy offers the monkey", said[-100:])
    before = s.windows()
    s.do("; ".join(f"P{q} press DOWN; wait 5; P{q} press A; wait 10" for q in range(1, n + 1) if q != o))
    expect(s.windows() == before, "nobody else answers Nancy", s.windows())
    said = s.said(f"P{o} press A; until idle 1500 P{o} advance")
    expect("bubble gum" in said, "Jeff got the gum", said)
    said = talk_to(s, "npc609", o)
    met, more = advance_until(s, "idle", 1500)
    expect(met and "Bubble Monkey joins" in said + more, "Bubble Monkey joined", (said + more)[-100:])
    st = s.state()
    expect_solo(st, "Jeff", n, guests=("Bubble Monkey",))
    standin_walks(s, sub, "Bubble Monkey", ("LEFT", "DOWN", "UP", "RIGHT"))
    ctx.shot(s, f"{n}P: Bubble Monkey joined, P{sub} stands in for him")

    # The cook's stew and the night (the watchers' camp: shortcut)
    s.do(f"teleport 344 3380 0; wait 2; until in:DOOR_TRANSITION 120 P{o} UP; until idle 300")
    said = talk_to(s, "npc612", o)
    met, more = advance_until(s, "in:SELECTION_MENU", 900)
    expect(met and "stew" in said + more, "the cook offers stew", said + more)
    s.do(f"P{o} press A")
    met, said = advance_until(s, "idle", 6000)
    st = s.state()
    expect(met and "Defense spray" in said and st.idle == "yes", "the night passed", said[-100:] + st.state)
    expect_solo(st, "Jeff", n, guests=("Bubble Monkey",))
    s.do(f"P{o} 20 UP+RIGHT; until in:DOOR_TRANSITION 60 P{o} RIGHT; until idle 300")
    expect(s.state().pos == (352, 3352), "out of the tent", s.state().state)

    # The shore (shortcut): the Monkey walked away, Jeff walks into the hotspot, Tessie carries everyone over
    s.do("teleport 662 3384 4; wait 2")
    s.do(f"P{sub} 40 LEFT; P{sub} 20 UP")
    st = s.state()
    expect(dist(st.players[sub].pos, st.pos) >= 40, "the Monkey away from Jeff", st.players_line)
    ctx.shot(s, f"{n}P: the shore, the Monkey's Stand-in P{sub} away from Jeff")
    s.do(f"until text 200 P{o} DOWN")
    s.do(f"hold P{sub} RIGHT")  # the Stand-in leans on the d-pad through the whole ride
    met, said = advance_until(s, "idle", 9000)
    s.do(f"release P{sub}")
    st = s.state()
    expect(met and "take care of everything" in said, "the Monkey called Tessie", said[-120:])
    expect(st.pos == LAKE_NORTH, f"the Party across Lake Tess at {LAKE_NORTH}", st.state)
    # The Monkey lands with the Party, though not always on his trail spot: his own tick (vanilla) may have him
    # hiding or running to catch up (walk=14) when the ride ends
    monkey = st.players[sub].pos
    expect(dist(monkey, st.pos) <= 48, "the Monkey landed with Jeff", st.players_line)
    expect_solo(st, "Jeff", n, guests=("Bubble Monkey",))
    ctx.shot(s, f"{n}P: across Lake Tess, the Monkey landed with Jeff")
    standin_walks(s, sub, "Bubble Monkey", ("LEFT", "DOWN", "RIGHT", "UP"))
    s.do("wait 2")
    expect_companions_walk(s, "Jeff", n, "20 RIGHT")
    st = s.state()
    s.do(f"P{o} 20 UP")
    expect(s.state().pos != st.pos, f"P{o} walks Jeff on", s.state().state)


def run(ctx):
    play(ctx, 2)
    play(ctx, 4)

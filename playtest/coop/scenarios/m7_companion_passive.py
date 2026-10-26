"""Companion: Mr. Saturn is passive. Doors are walls for it, enemies don't fight it, NPCs don't stop it.

- 05-Twoson hotel lobby (Ness alone, P2 the Companion): Mr. Saturn walks into the arch door to the
  side room and stays in the lobby; Ness walking the same line goes through.
- 34-Magicant (Ness alone): the creature npc1325 blocks Ness, Mr. Saturn walks through it.
- 17-GoldMine with 4 Players (Ness, Paula, Jeff; P4 the Companion): Mr. Saturn walks through an
  overworld enemy in the desert and no battle starts.
"""

import re

from lib import expect

DOOR = (7470, 7272)  # just right of the lobby's arch door, at the height it opens


def enemies(st):
    """The NEAR line's overworld enemies: [(name, (x, y)) world positions]."""
    lead = st.pos
    out = []
    for name, dx, dy in re.findall(r"enemy ([^(|]+?) \(([+-]\d+),([+-]\d+)\)", st.near_line):
        out.append((name, (lead[0] + int(dx), lead[1] + int(dy))))
    return out


def run(ctx):
    # Doors are walls for Mr. Saturn
    s = ctx.session(save="05-Twoson", players=2)
    s.boot()
    s.do("flag 11 1; 60 DOWN; 40 LEFT")
    st = s.state()
    lead = st.pos
    s.do(f"companion 2 {DOOR[0]} {DOOR[1]} 6; wait 1; P2 40 LEFT; wait 30")
    st = s.state()
    sat = st.players[2]
    expect("modes=[OVERWORLD]" in st.state and st.pos == lead, f"no door transition, Ness still at {lead}", st.state)
    expect(sat.pos[1] == DOOR[1] and DOOR[0] - 30 < sat.pos[0] < DOOR[0], "Mr. Saturn stopped at the door", sat)
    ctx.shot(s, "Mr. Saturn stopped by the door")
    s.do(f"teleport {DOOR[0]} {DOOR[1]} 6; wait 2; 40 LEFT; until idle 300", met=True)
    st = s.state()
    expect(abs(st.pos[1] - lead[1]) > 500, "the same walk takes Ness through the door", st.pos)

    # NPCs don't stop it
    m = ctx.session("magicant", save="34-Magicant", players=2)
    m.boot()
    m.do("teleport 5760 4690 6; 8 DOWN; 110 LEFT; 200 UP")
    st = m.state()
    dx, dy = st.near["npc1325"]
    npc = (st.pos[0] + dx, st.pos[1] + dy)
    m.do("snap npc")
    m.do(f"companion 2 {npc[0] + 40} {npc[1] - 2} 6; wait 1; P2 50 LEFT")
    st = m.state()
    expect(st.players[2].pos[0] < npc[0] - 12, f"Mr. Saturn walked through npc1325 at {npc}", st.players[2])
    ctx.shot(m, "Mr. Saturn walked through the creature")
    m.do(f"restore npc; teleport {npc[0] + 40} {npc[1] - 2} 6; wait 1; 50 LEFT")
    st = m.state()
    expect(st.pos[0] > npc[0] + 12, f"npc1325 at {npc} stops Ness", st.pos)

    # Enemies don't fight it
    g = ctx.session("goldmine", save="17-GoldMine", players=4)
    g.boot()
    g.do("teleport 3424 9312; wait 1")
    st = g.state()
    expect(st.players[4].companion and st.players[4].pos, "P4 walks the Companion", st.players_line)
    foes = enemies(st)
    expect(foes, "overworld enemies around", st.near_line)
    name, foe = min(foes, key=lambda e: abs(e[1][0] - st.pos[0]) + abs(e[1][1] - st.pos[1]))
    # Start right of the nearest enemy and walk through it
    g.do(f"companion 4 {foe[0] + 14} {foe[1]} 6; wait 1")
    passed = False
    for _ in range(12):
        g.do("P4 2 LEFT")
        st = g.state()
        expect(st.state and " battle=0" in st.state, "no battle while Mr. Saturn walks through an enemy", st.state)
        expect(not any(ln.startswith("CONTACT") for ln in st.extra), "no enemy contact", st.extra)
        sat = st.players[4].pos
        here = [e for n, e in enemies(st) if n == name]
        if not passed and any(abs(sat[0] - e[0]) <= 4 and abs(sat[1] - e[1]) <= 8 for e in here):
            passed = True
            ctx.shot(g, "Mr. Saturn on an enemy, no battle")
    expect(passed, f"Mr. Saturn reached the {name}", (sat, enemies(st)))

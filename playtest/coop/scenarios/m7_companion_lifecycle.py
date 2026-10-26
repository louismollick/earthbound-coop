"""Companion lifecycle: hidden through a door and a battle, back next to the Leader after; savestates keep it.

- 05-Twoson hotel lobby: Ness takes the arch door; Mr. Saturn hides for the transition and reappears next
  to Ness in the side room. Its Player then walks it again.
- 17-GoldMine, 4 Players (P4 the Companion): Ness walks into an enemy; Mr. Saturn hides from the touch
  through the battle and is back next to Ness after the win.
- A snap/restore in the same process and a restore in a fresh process bring it back where it stood.
"""

import shutil

from lib import expect

DOOR = (7470, 7272)  # just right of the lobby's arch door, at the height it opens


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def run(ctx):
    s = ctx.session(save="05-Twoson", players=2)
    s.boot()
    s.do("flag 11 1; 60 DOWN; 40 LEFT; P2 30 RIGHT")
    st = s.state()
    before = st.players[2].pos
    expect(before and dist(before, st.pos) > 30, "Mr. Saturn away from Ness", st.players_line)

    # A door: hidden for the transition, next to the Leader after
    s.do(f"teleport {DOOR[0]} {DOOR[1]} 6; wait 2; until in:DOOR_TRANSITION 60 LEFT")
    st = s.state()
    expect("DOOR_TRANSITION" in st.state, "Ness took the door", st.state)
    expect(st.players[2].companion and st.players[2].hidden, "Mr. Saturn hidden during the transition", st.players_line)
    ctx.shot(s, "door transition: no Mr. Saturn")
    s.do("until idle 600")
    st = s.state()
    sat = st.players[2]
    expect(abs(st.pos[1] - DOOR[1]) > 500, "the side room", st.pos)
    expect(not sat.hidden and dist(sat.pos, st.pos) <= 24, f"Mr. Saturn back next to Ness {st.pos}", sat)
    ctx.shot(s, "after the door: next to Ness")
    s.do("P2 20 DOWN")
    st2 = s.state()
    expect(st2.players[2].pos != sat.pos and st2.pos == st.pos, "P2 walks it again, Ness stays", st2.players_line)

    # Savestates: in-process, then cold in a fresh process
    out = s.do("snap comp")
    expect("SNAP comp ok" in out, "SNAP comp ok", out)
    saved = st2.players[2].pos
    s.do("P2 20 LEFT")
    expect(s.state().players[2].pos != saved, "it moved after the snap", s.state().players_line)
    out = s.do("restore comp; wait 1")
    expect("RESTORE comp ok" in out, "RESTORE comp ok", out)
    st3 = s.state()
    expect(st3.players[2].pos == saved and not st3.players[2].hidden, f"restored at {saved}", st3.players_line)
    t = ctx.session("fresh")
    (t.dir / "snaps").mkdir()
    for f in (s.dir / "snaps").glob("comp.*"):
        shutil.copy(f, t.dir / "snaps" / f.name)
    out = t.do("restore comp; wait 1")
    expect("RESTORE comp ok" in out, "RESTORE comp ok in a fresh process", out)
    st4 = t.state()
    expect(st4.players[2].companion and st4.players[2].pos == saved, f"cold-restored at {saved}", st4.players_line)
    t.do("P2 20 RIGHT")
    expect(t.state().players[2].pos[0] > saved[0] + 10, "and P2 walks it", t.state().players_line)
    ctx.shot(t, "cold restore: Mr. Saturn walks")

    # A battle: hidden from the touch to the end, back next to the Leader after
    g = ctx.session("goldmine", save="17-GoldMine", players=4)
    g.boot()
    g.do("teleport 3424 9312; wait 1; P4 10 RIGHT; until battle 600 LEFT; wait 2")
    st = g.state()
    expect(st.idle == "battle", "an enemy touched the Party", st.state)
    expect(st.players[4].hidden, "Mr. Saturn hidden from the touch", st.players_line)
    g.do("until in:BATTLE 600")
    st = g.state()
    expect("BATTLE" in st.state and st.players[4].hidden, "hidden in the battle", st.state + st.players_line)
    g.do("until in:BATTLE_MENU 3000; debug on; press SELECT+START; until idle 3000 advance")
    st = g.state()
    sat = st.players[4]
    expect(st.idle == "yes" and not sat.hidden, "the battle is over and Mr. Saturn is back", st.players_line)
    expect(dist(sat.pos, st.pos) <= 24, f"next to Ness {st.pos}", sat)
    ctx.shot(g, "after the battle: next to Ness")

"""Companion vs the game's own entities: vanilla NPCs always win, and lookups never find Mr. Saturn.

02-Sharks, Hotel Onett lobby (Ness alone). A script's lookup by sprite (``find sprite 171``, MR_SATURN) finds
no entity with P2's Mr. Saturn out. Then text-script NPC spawns (``npc 58``: create_prepared_entity_npc, the
hotel clerk's sprite) fill every NPC slot: with P2 walking a Companion the game gets exactly the slots it gets
solo, the last spawn takes the Companion's slot (it is removed), and it stays hidden while there is no room.
A teleport (map reload, the NPCs gone) brings it back next to Ness.
"""

from lib import ScenarioError, expect


def fill(s):
    """Spawn hotel-clerk NPCs at Ness until one fails; return the slots they got."""
    slots = []
    for _ in range(32):
        out = [ln for ln in s.do("npc 58") if ln.startswith("NPC ")]
        expect(out, "an NPC line", out)
        slot = int(out[0].split("slot=")[1])
        if slot < 0:
            return slots
        slots.append(slot)
    raise ScenarioError("expected the NPC slots to run out within 32 spawns")


def run(ctx):
    solo = ctx.session("solo", save="02-Sharks")
    solo.boot()
    solo.do("flag 11 1; wait 4")
    want = fill(solo)

    s = ctx.session(save="02-Sharks", players=2)
    s.boot()
    s.do("flag 11 1; wait 4")
    st = s.state()
    sat = st.players[2]
    expect(sat.companion and not sat.hidden, "P2's Mr. Saturn out", st.players_line)
    out = s.do("find sprite 171")
    expect("FIND sprite 171 = -1" in out, "no MR_SATURN entity for a script's sprite lookup", out)

    got = fill(s)
    expect(got == want, f"the game's NPCs get the solo slots {want}", got)
    st = s.state()
    expect(st.players[2].hidden, "Mr. Saturn removed for the last NPC", st.players_line)
    s.do("wait 90")
    st = s.state()
    expect(st.players[2].hidden, "and it stays hidden while every slot is taken", st.players_line)
    ctx.shot(s, "every NPC slot the game's: no Mr. Saturn")

    s.do("teleport 7999 1488 0; wait 30")
    st = s.state()
    sat = st.players[2]
    near = max(abs(sat.pos[0] - st.pos[0]), abs(sat.pos[1] - st.pos[1])) if sat.pos else None
    expect(not sat.hidden and near is not None and near <= 24, f"Mr. Saturn back next to Ness {st.pos}", sat)
    out = s.do("find sprite 171")
    expect("FIND sprite 171 = -1" in out, "still no MR_SATURN entity for a sprite lookup", out)

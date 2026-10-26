"""Any Walker touching an overworld enemy starts the battle for the whole Party.

17-GoldMine desert (`teleport 3424 9312`, six enemies around). The touched Walker is the target and first strike is
judged by its facing; afterwards Paula is back where she stood and walks on her own.
"""

from lib import expect, expect_in_leash

PAULA_SLOT = 25  # party entity 24 + Paula's party_characters index


def contact(st):
    line = next((ln for ln in st.extra if ln.startswith("CONTACT")), "")
    return dict(kv.split("=") for kv in line.split()[1:]) if line else {}


def run(ctx):
    # P2 walks Paula UP+RIGHT into a Crested Booka while Ness stands still: her touch starts the battle
    s = ctx.session(save="17-GoldMine", players=2)
    s.boot()
    s.do("teleport 3424 9312; 1 -")
    lead = s.state().pos
    s.do("until battle 40 P2 UP+RIGHT")
    st = s.state()
    c = contact(st)
    paula = st.players[2].pos
    expect(st.idle == "battle", "an enemy touched within 40 frames", st.state)
    expect(c.get("target") == str(PAULA_SLOT), f"the enemy targets Paula (entity {PAULA_SLOT})", c)
    expect(st.pos == lead, f"Ness never moved from {lead}", st.pos)
    expect(paula != lead, "Paula away from Ness", paula)
    ctx.shot(s, "P2 touched an enemy")

    s.do("until in:BATTLE_MENU 900 advance")
    st = s.state()
    expect("BATTLE" in st.state, "the whole Party in battle", st.state)
    expect(st.party.count("|") == 2, "three Heroes in the battle", st.party)
    ctx.shot(s, "battle after P2's touch")

    # Win (debug SELECT+START): Paula is back where she stood, and walks on her own
    s.do("debug on; press SELECT+START; until idle 3000 advance")
    st = s.state()
    expect(st.players[2].pos == paula, f"Paula back at {paula} after the battle", st.players[2].pos)
    expect(st.pos == lead, f"Ness back at {lead}", st.pos)
    expect_in_leash(st, paula, "Paula")
    s.do("P2 20 DOWN")
    st2 = s.state()
    expect(st2.players[2].pos[1] > paula[1] + 10, "Paula walks after the battle", st2.players[2].pos)
    s.do("120 -")  # past the post-battle blink, so the shot shows the Party
    ctx.shot(s, "after the battle, P2 walks")

    # First strike is judged by the touched Walker: Ness faces UP (away from the enemy that comes from below),
    # Paula walks DOWN toward it. Judged by Ness that is enemies first (2); judged by Paula it is normal (0).
    s2 = ctx.session("first_strike", save="17-GoldMine", players=2)
    s2.boot()
    s2.do("teleport 3424 9312; 1 UP")
    s2.do("until battle 40 P2 DOWN")
    st = s2.state()
    c = contact(st)
    expect(c.get("target") == str(PAULA_SLOT), f"the enemy targets Paula (entity {PAULA_SLOT})", c)
    expect(st.dir == "UP" and st.players[2].dir == "DOWN", "Ness faces UP, Paula DOWN", st.players_line)
    s2.do("20 -")
    c = contact(s2.state())
    expect(c.get("initiative") == "0", "normal initiative (Paula faces the enemy), not enemies first", c)

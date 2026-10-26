"""Edge case: P2 joins while Ness rides the bicycle (05-Twoson, Ness alone).

No forced dismount: a join never changes the Party, so the bicycle stays legal. P2 joins as a Companion (hidden while Ness rides)
(no Walker), Ness keeps riding, and the ride matches a solo session frame for frame (P2's pad does
nothing).
"""

from lib import expect

# Twoson street; the Bicycle (item 0xB0) from Goods (last entry: 7th row, right column), Use
RIDE = (
    "flag 11 1; give 176 1; warp twoson; 30 -; press A; wait 20; press RIGHT; wait 5; press A; wait 30; "
    "press DOWN 6; press RIGHT; wait 5; press A; wait 20; press A; until idle 300"
)
BICYCLE = 3  # WALKING_STYLE_BICYCLE


def ride(ctx, name):
    s = ctx.session(name, save="05-Twoson", players=1)
    s.boot()
    s.do(RIDE)
    st = s.state()
    expect(st.idle == "yes" and f"walk={BICYCLE}" in st.state, "Ness on the bicycle", st.state)
    return s


def run(ctx):
    s = ride(ctx, "coop")
    ref = ride(ctx, "solo")

    s.do("P2 press START; wait 5")
    ref.do("P2 press SELECT; wait 5")  # the same frames; an unjoined pad's SELECT does nothing
    st, r = s.state(), ref.state()
    p2 = st.players[2]
    expect(
        p2.joined and p2.companion and p2.hidden, "P2 joined as a Companion, hidden while Ness rides", st.players_line
    )
    expect(f"walk={BICYCLE}" in st.state and st.players[1].walk == BICYCLE, "Ness still riding", st.state)
    expect(st.pos == r.pos, f"Ness where solo Ness is {r.pos}", st.pos)

    # P2's pad does nothing: no Walker, and nobody takes the lock on the bicycle (solo: P2 unjoined)
    for step, solo in [("30 LEFT", "30 LEFT"), ("P2 30 RIGHT", "30 -"), ("P2 press A; wait 20", "P2 press A; wait 20")]:
        s.do(step)
        ref.do(solo)
        st, r = s.state(), ref.state()
        expect(st.pos == r.pos and st.dir == r.dir, f"Ness rides as in solo ({step}): {r.pos} {r.dir}", st.state)
        expect(f"walk={BICYCLE}" in st.state and st.idle == "yes", f"still riding, no menu ({step})", st.state)
        expect(st.focus == "P1", "focus P1", st.players_line)
    ctx.shot(s, "P2 joined, Ness keeps riding")

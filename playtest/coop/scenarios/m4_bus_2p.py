"""Edge case: the Runaway Five bus to Threed with several Walkers (10-ToThreed, the regress `bus` recipe).

The Party is Ness and Paula (and a Teddy Bear, member 16). 2 Players: P1 walks Ness, P2 Paula. 3 Players: P3
also walks a Mr. Saturn Companion. P1 talks to the band (npc at 2224,6585) and holds the lock: the other Players'
A does nothing at the Yes/No or at the ride's button prompts. Paula (and Mr. Saturn) walk away, then Ness walks
into the strip under the bus: the boarding event takes the Party, so Paula snaps onto Ness's spot and the
Companion hides. The ride runs (frames advance, the bus moves, the mode stack changes) and arrives in Threed at
(5533,9388) with the vanilla follower line (Paula -14, the Teddy Bear -27: the same as solo). Mr. Saturn comes
back next to Ness, and every non-Leader Player walks on their own again while Ness stays.
"""

from lib import expect

BAND = "flag 11 1; teleport 2224 6600 0; 12 UP; press A; until input 60; press A; until in:SELECTION_MENU 3000 advance"
THREED = (5533, 9388)
SOLO_LINE = {2: (-14, 0), 16: (-27, 0)}  # FOLLOW after the solo ride


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def ignored(s, players, what):
    """Presses of A by ``players`` change no window (the text belongs to someone else)."""
    before = s.windows()
    s.do("; ".join(f"P{p} press A; wait 10" for p in players))
    st = s.state()
    expect(s.windows() == before, f"{what}: P{players} pressing A changes nothing", s.windows())
    return st


def ride(ctx, n):
    s = ctx.session(f"{n}p", save="10-ToThreed", players=n)
    s.boot()
    others = list(range(2, n + 1))

    # The band: P1 talks and holds the lock; nobody else answers the Yes/No
    s.do(f"{BAND}; wait 10")
    st = s.state()
    expect("SELECTION_MENU" in st.state and st.focus == "P1 locked", "P1's Yes/No for the ride", st.state)
    ignored(s, others, "the band's Yes/No")
    s.do("press A; until idle 3000 advance")

    # Walkers spread out before boarding
    s.do("P2 40 RIGHT" + ("; P3 30 DOWN" if n >= 3 else ""))
    s.do("8 DOWN; 40 LEFT")
    st = s.state()
    p = st.players
    expect(dist(p[2].pos, st.pos) >= 30 and not p[2].companion, "Paula walked away from Ness", st.players_line)
    if n >= 3:
        expect(p[3].companion and dist(p[3].pos, st.pos) >= 30, "Mr. Saturn away from Ness", st.players_line)
    ctx.shot(s, f"{n}P: Walkers apart before boarding")

    # Boarding: Ness walks into the strip under the bus; the event takes the Party
    out = s.do("until text 600 UP")
    st = s.state()
    p = st.players
    expect(any(ln.startswith("UNTIL met") for ln in out) and st.idle == "modes", "the boarding event", st.state)
    expect(st.follow_offsets.get(2) == (0, 0) and p[2].pos == st.pos, "Paula boarded with Ness", st.follow)
    if n >= 3:
        expect(p[3].companion and p[3].hidden, "Mr. Saturn hidden for the ride", st.players_line)
    ctx.shot(s, f"{n}P: boarded")

    # The ride: the band's button prompts are P1's; then the bus drives off
    frame = int(st.state.split("frame=")[1].split()[0])
    out = s.do("until input 3000")
    st = s.state()
    expect(any(ln.startswith("UNTIL met") for ln in out) and "TEXT_PROMPT" in st.state, "a ride prompt", st.state)
    st = ignored(s, others, "the ride's prompt")
    before = st.pos
    said = s.said("until said:sidewalk 6000 advance; wait 30")
    st = s.state()
    p = st.players
    expect("sidewalk" in said and st.idle == "modes", "the bus on the road", said + st.state)
    expect(int(st.state.split("frame=")[1].split()[0]) > frame + 100, "the ride's frames advance", st.state)
    expect(st.pos[0] > before[0] + 100, "the bus drives off with Ness", st.state)
    off = st.follow_offsets[2]
    expect(p[2].pos == (st.pos[0] + off[0], st.pos[1] + off[1]), "PLAYERS Paula on her follower spot", st.players_line)
    ctx.shot(s, f"{n}P: the bus on its way")

    # Threed: everyone arrived in the vanilla line
    out = s.do("until idle 8000 advance")
    st = s.state()
    p = st.players
    expect(any(ln.startswith("UNTIL met") for ln in out) and st.pos == THREED, f"arrived at {THREED}", st.state)
    expect(st.follow_offsets == SOLO_LINE, f"the solo arrival line {SOLO_LINE}", st.follow)
    expect(p[2].walker == "Paula" and p[2].pos == (THREED[0] - 14, THREED[1]), "P2's Paula in the line", p[2])
    if n >= 3:
        expect(not p[3].hidden and dist(p[3].pos, st.pos) <= 24, "Mr. Saturn back next to Ness", p[3])
    expect(st.focus == "P1", "the focus back on P1", st.players_line)
    ctx.shot(s, f"{n}P: arrived in Threed together")

    # Independent again
    s.do("P2 30 DOWN" + ("; P3 30 LEFT" if n >= 3 else ""))
    st2 = s.state()
    p2 = st2.players
    expect(p2[2].pos[1] >= p[2].pos[1] + 20, "P2 walks Paula down", st2.players_line)
    if n >= 3:
        expect(p2[3].pos[0] <= p[3].pos[0] - 20, "P3 walks Mr. Saturn left", st2.players_line)
    expect(st2.pos == THREED, "Ness stays", st2.pos)
    ctx.shot(s, f"{n}P: walking apart in Threed")


def run(ctx):
    ride(ctx, 2)
    ride(ctx, 3)

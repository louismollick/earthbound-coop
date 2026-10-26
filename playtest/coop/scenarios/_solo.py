"""Shared checks for the m4_solo_* scenarios: Solo Chapters played with 2 to 4 Players.

With ``--players n`` the Players join in order P1..Pn, so Hero h (Ness 0, Paula 1, Jeff 2, Poo 3) belongs to
P(h mod n + 1). In a Solo Chapter the solo Hero's Owner walks it; every other Player is absent and either stands
in for a free Guest (k-th absent Player in join order, k-th eligible Guest in Party order) or walks a Mr. Saturn
Companion. Battle rotation hands the solo Hero's command menu to the Owner, then every other Player in join order.
"""

from lib import expect

HEROES = ("Ness", "Paula", "Jeff", "Poo")


def owner(hero, n):
    """The Player (1-based) who owns ``hero`` with ``n`` Players joined in order."""
    return HEROES.index(hero) % n + 1


def rotation_order(hero, n):
    """Battle rotation: the Owner, then every other Player in join order."""
    o = owner(hero, n)
    return [o] + [p for p in range(1, n + 1) if p != o]


def expect_solo(st, hero, n, guests=()):
    """(a) The Party is ``hero`` (plus ``guests``) and its Owner walks it.

    The absent Players stand in for the Guests in order and the rest walk a Companion. Nobody else walks a Hero
    (no stale Walker).
    """
    p = st.players
    o = owner(hero, n)
    expect(p[o].walker == hero and not p[o].standin and not p[o].companion, f"P{o} walks {hero}", st.players_line)
    expect(p[o].owns == [hero], f"P{o} owns only {hero} in the Party", st.players_line)
    absent = [q for q in range(1, n + 1) if q != o]
    for k, q in enumerate(absent):
        expect(p[q].joined and p[q].owns == [], f"P{q} joined with no Hero in the Party", st.players_line)
        if k < len(guests):
            expect(p[q].standin and p[q].walker == guests[k], f"P{q} stands in for {guests[k]}", st.players_line)
        else:
            expect(p[q].companion and not p[q].standin, f"P{q} walks a Mr. Saturn Companion", st.players_line)
    for q in range(n + 1, 5):
        expect(not p[q].joined, f"P{q} not joined", st.players_line)
    expect(st.focus in (f"P{o}", f"P{o} locked"), f"the focus on P{o}, the Leader's Owner", st.players_line)


def expect_party(st, n, party):
    """Every Player with a Hero in ``party`` walks their first one; every other Player walks a Mr. Saturn.

    Nobody walks a Hero outside ``party`` (no stale Walker), nobody stands in, and the focus is on the Leader's
    Owner.
    """
    p = st.players
    for q in range(1, n + 1):
        mine = [h for h in party if owner(h, n) == q]
        expect(p[q].owns == mine, f"P{q} owns {mine} in the Party", st.players_line)
        if mine:
            expect(p[q].walker == mine[0] and not p[q].companion and not p[q].standin, f"P{q} walks {mine[0]}", p[q])
        else:
            expect(p[q].companion and not p[q].standin, f"P{q} walks a Mr. Saturn", p[q])
    lead = owner(party[0], n)
    expect(st.focus in (f"P{lead}", f"P{lead} locked"), f"the focus on P{lead}", st.players_line)


def expect_restored(st, n, party=HEROES):
    """(c) The Party is back: every Player walks their own first Hero in ``party`` order.

    A Player with no Hero in it walks a Mr. Saturn; nobody stands in.
    """
    expect_party(st, n, party)


def expect_walk_apart(s, n, moves, leader=1):
    """(c) Each Player in ``moves`` ({player: "20 DOWN"}) walks their own Walker; the Leader stays put.

    A step into a wall is no test, so another direction is tried when the given one doesn't move the Walker.
    """
    st = s.state()
    for q, m in moves.items():
        frames, first = m.split()
        for d in [first] + [d for d in ("DOWN", "RIGHT", "UP", "LEFT") if d != first]:
            s.do(f"P{q} {frames} {d}")
            st2 = s.state()
            if st2.players[q].pos != st.players[q].pos:
                break
        expect(st2.players[q].pos != st.players[q].pos, f"P{q} walks its {st.players[q].walker}", st2.players_line)
        if q != leader:
            expect(st2.pos == st.pos, f"the Leader stays at {st.pos} while P{q} walks", st2.state)
        st = st2
    return st


def expect_companions_walk(s, hero, n, move="20 DOWN"):
    """(a) The solo Hero's Owner walks it and every Companion's Player walks their Mr. Saturn."""
    st = s.state()
    for q in range(1, n + 1):
        if not st.players[q].companion:
            continue
        expect(not st.players[q].hidden, f"P{q}'s Mr. Saturn shown", st.players_line)
        s.do(f"P{q} {move}")
        st2 = s.state()
        expect(st2.players[q].pos != st.players[q].pos, f"P{q} walks its Mr. Saturn ({move})", st2.players_line)
        expect(st2.pos == st.pos, f"{hero} stays while P{q} walks", st2.state)
        st = st2
    return st


def advance_until(s, cond, frames):
    """Read text out with the focused Player's A until ``cond``: (met within ``frames``, the text printed).

    A cutscene nobody started holds no lock, so its focus is the Leader's Owner, and the Leader can change mid-way
    (Jeff to Ness at the Sky Runner crash, Poo to Ness when Poo arrives at the Summers beach).
    """
    said = []
    for _ in range(frames // 300):
        f = s.state().focus or "P1"
        out = s.do(f"until {cond} 300 {f.split()[0]} advance")
        said += [ln[5:] for ln in out if ln.startswith("TEXT ")]
        if any(ln.startswith("UNTIL met") for ln in out):
            return True, " ".join(said)
    return False, " ".join(said)


def find_battle(s, route, player=1):
    """Walk ``route``, then back and forth as P``player``, until a battle starts.

    Where enemies spawn depends on the viewport, so a fixed walk isn't enough at both sizes.
    """
    s.do(route)
    for d in ("LEFT", "RIGHT", "UP", "DOWN") * 6:
        st = s.state().state
        if "BATTLE" in st or "idle=battle" in st:
            return
        if "idle=yes" not in st:  # walked into someone's text: read it out
            s.do(f"until idle 1500 P{player} advance")
        s.do(f"until battle 120 P{player} {d}")
    st = s.state().state
    expect("BATTLE" in st or "idle=battle" in st, "a battle", st)


def rotation_turn(s, hero, holder, n):
    """(b) ``hero``'s command menu belongs to P``holder``: tag, focus, and nobody else's presses count."""
    st = s.state()
    title = f"{hero} P{holder}"
    expect(s.title() == title and st.focus == f"P{holder}", f"the '{title}' menu, focus P{holder}", st.players_line)
    before = s.windows()
    s.do("; ".join(f"P{p} press RIGHT; wait 8; P{p} press A; wait 8" for p in range(1, n + 1) if p != holder))
    expect(s.windows() == before, f"the other Players' presses on P{holder}'s turn change nothing", s.windows())


def defend(s, hero, holder, n):
    """P``holder`` picks Defend for ``hero``; the text is read out to the next turn's menu.

    HP 999 first: a lone low-level Hero must survive the turns (the test is about who picks, not the fight).
    """
    s.do(f"hp {HEROES.index(hero) + 1} 999; P{holder} press RIGHT; wait 5; P{holder} press DOWN; wait 5")
    opts, sel = s.menu()
    expect(opts[sel] == "Defend", f"P{holder}'s cursor on Defend", (opts, sel))
    other = next(p for p in range(1, n + 1) if p != holder)  # a Player who can't touch the menu reads the text out
    said = s.said(f"P{holder} press A; until input 3000 P{other} advance; wait 10")
    expect(f"{hero} is on guard" in said, f"P{holder}'s Defend ran", said)


def rotation_battle(ctx, s, hero, n, label, win=True):
    """(b) A battle is starting: every Player in rotation order gets one turn (Defend), then the first again.

    The Owner then wins it (debug) if ``win``. Returns the overworld state after the battle (or the battle's,
    without ``win``).
    """
    order = rotation_order(hero, n)
    said = s.said(f"until input 1500 P{order[0]} advance; wait 10")
    if "opening attack" in said:  # the enemies' surprise turn used up the first Player's place
        order = order[1:] + order[:1]
    for i, holder in enumerate(order):
        rotation_turn(s, hero, holder, n)
        if i == 1:
            ctx.shot(s, f"{label}: {hero} P{holder}'s turn")
        defend(s, hero, holder, n)
    rotation_turn(s, hero, order[0], n)
    if not win:
        return s.state()
    # Healed and cured first, so poison can't knock a lone Hero out on the way back
    s.do(
        f"heal; status {HEROES.index(hero) + 1} 1 0; debug on; P{order[0]} press SELECT+START; until idle 1500 P{order[0]} advance; debug off"
    )
    st = s.state()
    expect(st.idle == "yes" and "BATTLE" not in st.state, "back on the overworld after the win", st.state)
    return st

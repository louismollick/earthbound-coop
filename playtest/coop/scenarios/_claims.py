"""Shared steps for the simultaneous battle input scenarios (m7_simul_*): claimed command menus.

In a co-op battle no command menu opens until a Player with Heroes left to choose for presses A (the PLAYERS
line then ends ``| choose=P1,P2``); a press while someone else's menu is open queues for the next one, and once
only one Player has Heroes left their menus open by themselves.
"""

import re

from lib import expect

SCARABA_BATTLE = "teleport 1400 5600 4; until battle 1500 RIGHT|DOWN|LEFT|UP; until input 1500; wait 10"


def pre(p):
    return f"P{p} " if p > 1 else ""


def waiting(s, players):
    """No command menu yet: the battle waits for one of ``players`` to claim one."""
    st = s.state()
    expect(st.choose == list(players) and st.focus == "ALL", f"waiting for a claim from {players}", st.players_line)


def claim(s, p):
    s.do(f"{pre(p)}press A; until input 300; wait 10")


def at_menu(s, title, p):
    st = s.state()
    expect(
        s.title() == title and st.focus == f"P{p}", f"the '{title}' menu, focus P{p}", (s.windows(), st.players_line)
    )


def ignored(s, players, what, buttons=("RIGHT", "DOWN", "B")):
    """``players`` press ``buttons``: no window, title or cursor changes."""
    before = s.windows()
    s.do("; ".join(f"{pre(p)}press {b}; wait 8" for p in players for b in buttons))
    expect(s.windows() == before, f"{what}: nothing changes", f"{before} -> {s.windows()}")


def option(s, p, moves, want):
    s.do("; ".join(f"{pre(p)}press {m}; wait 5" for m in moves))
    opts, sel = s.menu()
    expect(opts[sel] == want, f"P{p}'s cursor on {want}", (opts, sel))


def defend(s, p):
    option(s, p, ["RIGHT", "DOWN"], "Defend")
    s.do(f"{pre(p)}press A; until input 300; wait 10")


def attack(s, p, reader=None):
    """Bash/Shoot the first enemy.

    With ``reader`` (a Player), this is the turn's last menu: return the round's text, read out by ``reader``.
    """
    s.do(f"{pre(p)}press A; until input 300; wait 10")
    expect(any(ln.startswith("WIN w49*| To ") for ln in s.windows()), f"P{p}'s enemy target select", s.windows())
    if reader is None:
        s.do(f"{pre(p)}press A; until input 300; wait 10")
        return ""
    return s.said(f"{pre(p)}press A; until input 3000 {pre(reader)}advance; wait 10")


def actors(said):
    """The Heroes' attacks in the order the round's text tells them."""
    return re.findall(r"(Ness|Paula|Jeff|Poo) attacks", said)

"""The overworld lock: who takes it, that the Leader never walks on the locker's pad, and its release.

Open Scaraba desert, 2 Players (P1 Ness, P2 Paula). P2 holds RIGHT while pressing A: the menu opens
on P2's lock and Ness doesn't move, not even on the frame the menu closes. Once the menu is closed
the focus is P1's again: P2's RIGHT walks only Paula, P1's walks Ness. On a frame where both press
A, P1 (lower number) takes the lock, and only P1 can close that menu.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    st = s.kraken_spot()
    lead = st.pos
    expect(st.focus == "P1", "unlocked focus on the Leader's Owner", st.players_line)

    s.do("hold P2 RIGHT; 10 -")
    p2 = s.state().players[2].pos
    s.do("P2 press A; wait 20")
    st = s.state()
    expect(st.focus == "P2 locked" and "PAUSE_MENU" in st.state, "P2's A (with RIGHT held) took the lock", st.state)
    expect(st.pos == lead, f"Ness still at {lead} with P2's RIGHT held into the menu", st.pos)
    s.do("press B; wait 10")
    expect("PAUSE_MENU" in s.state().state, "P1's B doesn't close P2's menu", s.state().state)
    s.do("P2 press B; wait 2")
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", "P2's B closed it, focus back on P1", st.players_line)
    s.do("12 -; release P2; 2 -")
    st = s.state()
    expect(st.pos == lead, f"Ness still at {lead}: P2's RIGHT never steered the Leader", st.pos)
    expect(st.players[2].pos[0] > p2[0] + 8, f"P2's RIGHT walks Paula on from {p2}", st.players[2])
    ctx.shot(s, "after P2's menu: Ness stayed, Paula walked")

    s.do("10 RIGHT; 2 -")
    st = s.state()
    expect(st.pos[0] > lead[0] + 8, "P1's RIGHT walks Ness", st.pos)

    # Both press A on the same frame: P1 wins
    s.do("hold P2 A; press A; release P2; wait 20")
    st = s.state()
    expect(st.focus == "P1 locked" and "PAUSE_MENU" in st.state, "P1 took the lock on a shared frame", st.players_line)
    s.do("P2 press B; wait 10")
    expect("PAUSE_MENU" in s.state().state, "P2's B doesn't close P1's menu", s.state().state)
    s.do("press B; until idle 120")
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", "P1 closed it, unlocked", st.players_line)

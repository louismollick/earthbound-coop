"""Closing a locker's menu onto a stair or escalator entry: the game's scripted walk still runs (M3 review).

P2 opens the pause menu (P2 locked) while P1 holds the Leader one step short of an entry. P1 keeps
holding the d-pad as P2 closes the menu, so Ness steps onto the entry and the game replays its
approach walk (demo playback) with the lock still held. The Leader's step must take that scripted
pad, not P1's live one: Ness reaches the stairs (and P1 then walks them) or rides the escalator up,
and the lock is released once the Party is idle again.
"""

from lib import expect


def until_idle_is(s, want, frames):
    """Step one frame at a time (no input) until the harness idle reason is ``want``; return that state."""
    for _ in range(frames):
        st = s.state()
        if st.idle == want:
            return st
        s.do("1 -")
    return s.state()


def run(ctx):
    # Stairs (door type 4) at (5232,3560) on 27-Kraken: Ness at (5232,3568), one UP from the entry
    s = ctx.session("stairs", save="27-Kraken", players=2)
    s.boot()
    s.do("flag 11 1; teleport 5232 3580 0; 20 -; P2 30 UP; P2 20 UP; 9 UP; 2 -")
    st = s.state()
    expect(st.idle == "yes" and st.pos == (5232, 3568), "Ness idle just below the stairs", st.state)
    s.do("P2 press A; wait 20")
    expect(s.state().focus == "P2 locked", "P2's A took the lock", s.state().players_line)
    s.do("hold P1 UP; P2 2 B; release P1; 1 -")
    st = until_idle_is(s, "stairs", 120)
    expect(st.idle == "stairs", "the approach walk put Ness on the stairs", st.state)
    s.do("until idle 900 RIGHT")
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", "off the stairs, the lock released", st.players_line)
    expect(st.pos[0] > 5232 + 16, "P1's RIGHT walked Ness along the stairs", st.pos)
    ctx.shot(s, "stairs walked after P2's menu")

    # 18-DeptStore 1F up escalator: Ness at (4908,6856), one LEFT from the entry
    s = ctx.session("escalator", save="18-DeptStore", players=2)
    s.boot()
    s.do("flag 11 1; teleport 4942 6853 6; 20 -; P2 40 RIGHT; 26 LEFT")
    st = s.state()
    expect(st.idle == "yes" and st.pos == (4908, 6856), "Ness idle just right of the escalator", st.state)
    s.do("P2 press A; wait 20")
    expect(s.state().focus == "P2 locked", "P2's A took the lock", s.state().players_line)
    s.do("hold P1 LEFT; P2 2 B; release P1; 1 -")
    st = until_idle_is(s, "escalator", 120)
    expect(st.idle == "escalator", "the approach walk put Ness on the escalator", st.state)
    s.do("until idle 900")
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", "off the escalator, the lock released", st.players_line)
    # Solo with the same steps ends at (4715,6704); the live-pad override stopped the exit walk 21 px short
    expect(st.pos == (4715, 6704), "upstairs where the exit walk ends in solo", st.pos)
    ctx.shot(s, "escalator ridden after P2's menu")

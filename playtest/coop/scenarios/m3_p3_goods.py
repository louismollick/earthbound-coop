"""P3 feeds Jeff (its Walker) a Cookie from Goods; the "Who?" cursor starts on Jeff.

3 Players at the Scaraba desert cabin: P1 Ness, P2 Paula, P3 Jeff. P3's A opens the menu, Goods'
"Who?" starts on Jeff, P1's A there is ignored, and the Cookie's HP lands on Jeff only.
"""

from lib import expect

COOKIE = 88  # COOKIE = $58 (include/constants/items.asm)


def run(ctx):
    s = ctx.session(save="15-Desert", players=3)
    s.boot()
    out = s.do(f"give {COOKIE} 3; hp 3 40; P3 30 DOWN; wait 30")
    expect(any("Cookie) -> char 3 Jeff" in ln for ln in out), "a Cookie for Jeff", out)
    st = s.state()
    expect(st.players[3].walker == "Jeff" and st.hp(3) == 40, "P3 walks Jeff, Jeff at 40 HP", st.party)
    hp = {m: st.hp(m) for m in (1, 2)}

    out = s.do("P3 press A; wait 20; P3 press RIGHT; wait 6; P3 press A; until input 300; text")
    expect(s.state().focus == "P3 locked", "P3 holds the lock", s.state().players_line)
    expect(
        any(ln.startswith("WIN w2") and "[Jeff]" in ln for ln in out),
        "Goods' Who? starts on Jeff (P3's Walker)",
        out[-8:],
    )
    ctx.shot(s, "Who? starts on Jeff")
    s.do("press A; wait 10; press LEFT; wait 10")
    expect("CHAR_SELECT" in s.state().state, "P1's A and LEFT ignored at Who?", s.state().state)

    s.do("P3 press A; until input 300")
    opts, sel = s.menu()
    expect(opts[-1] == "Cookie", "Jeff's Goods end with the Cookie", opts)
    s.do("P3 press UP; wait 6; P3 press LEFT; wait 6")
    opts, sel = s.menu()
    expect(opts[sel] == "Cookie", "P3 on the Cookie", (opts, sel))
    s.do("P3 press A; until input 300; P3 press A; until input 300")
    opts, sel = s.menu()
    expect(opts == ["Ness", "Paula", "Jeff"], "Whom?", opts)
    s.do(f"P3 press RIGHT {opts.index('Jeff')}; wait 6")
    said = s.said("P3 press A; until idle 900 P3 advance; wait 60")
    expect("Jeff ate" in said, "Jeff ate the Cookie", said)
    st = s.state()
    expect(st.hp(3) > 40, "Jeff's HP went up", st.party)
    expect({m: st.hp(m) for m in (1, 2)} == hp, "Ness's and Paula's HP unchanged", st.party)
    expect(st.focus == "P1", "focus back on the Leader's Owner", st.players_line)

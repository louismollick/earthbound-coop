"""P2 buys a Thick fry pan at the Scaraba desert cabin shop; P1's presses during the shop are ignored.

Paula (P2's Walker) faces the clerk while Ness stands at the phone. The money drops by $198, the
"Which of you will carry this?" select starts on Paula, and her Goods list shows the pan afterwards.
"""

from lib import expect

PAN = "Thick fry pan"


def run(ctx):
    s = ctx.session(save="15-Desert", players=2)
    st = s.boot()
    money = st.money
    s.do("P2 26 LEFT; P2 4 UP; wait 4")
    st = s.state()
    expect(st.players[2].dir == "UP" and st.near.get("npc747"), "Paula facing up at the clerk npc747", st.players_line)

    said = s.said("P2 press A; wait 20; P2 press A; until input 300 P2 advance")
    expect("How may I help you" in said, "the clerk greets after P2's Talk to", said)
    s.do("P2 press A; until input 300; P2 press A; until in:SELECTION_MENU 300; wait 60")
    opts, sel = s.menu()
    expect(PAN in opts and sel == 0, "the shop list, cursor on the first item", (opts, sel))
    # P1 can't scroll or buy
    s.do("press DOWN; wait 10; press A; wait 20")
    expect(s.menu() == (opts, 0), "P1's DOWN and A ignored in the shop list", s.menu())
    expect(s.state().money == money, f"nothing bought by P1 (${money})", s.state().money)

    s.do(f"P2 press DOWN {opts.index(PAN)}; wait 10")
    expect(s.menu() == (opts, opts.index(PAN)), f"P2 on the {PAN}", s.menu())
    out = s.do("P2 press A; until input 300 P2 advance; text")
    expect(
        any(ln.startswith("WIN w2") and "[Paula]" in ln for ln in out),
        "the carry select starts on Paula (P2's Walker)",
        out[-8:],
    )
    ctx.shot(s, "who carries it: Paula")
    s.do("press RIGHT; wait 6; press A; wait 10")
    expect("CHAR_SELECT" in s.state().state, "P1's A didn't pick a carrier", s.state().state)
    s.do("P2 press A; until in:SELECTION_MENU 600 P2 advance")
    st = s.state()
    expect(st.money == money - 198, f"${money} - $198 after the purchase", st.money)

    # Don't equip it; nothing else; leave
    s.do("P2 press RIGHT; wait 6; P2 press A; until in:SELECTION_MENU 600 P2 advance")
    s.do("P2 press RIGHT; wait 6; P2 press A; until idle 900 P2 advance")
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", "out of the shop, focus back on P1", st.players_line)

    # The pan is in Paula's Goods; the Goods "Who?" starts on Paula too
    out = s.do("P2 press A; wait 20; P2 press RIGHT; wait 6; P2 press A; until input 300; text")
    expect(
        any(ln.startswith("WIN w2") and "[Paula]" in ln for ln in out) and PAN in s.menu()[0],
        f"Paula's Goods list with the {PAN}",
        out[-8:],
    )
    ctx.shot(s, "Paula's Goods")
    s.do("P2 press B; wait 10; P2 press B; until idle 300")
    expect(s.state().focus == "P1", "menu closed, focus back on P1", s.state().players_line)

"""Companion interactions: Look-only texts show, anything else is a Mr. Saturn sound with no text.

02-Sharks, Hotel Onett (Ness alone, P2 the Companion). P2's A takes the lock and Checks/Talks from
Mr. Saturn (never the pause menu):
- the porter npc59 (MSG_ONET_HOTEL_PORTER, only text) talks, and turns to face Mr. Saturn;
- the clerk npc58 (a hotel: money, a night) and the phone npc60 (calls, saving) give SFX 114
  (MYSTERIOUS_2) and no text and no window on any frame;
- outside, the hotel sign npc191 (an OBJECT, only text) reads with L;
- the trash can npc1410 (an ITEM_BOX that gives something, flag 803) gives the sound, and its flag,
  the money and Ness's goods stay as they were.
After every interaction that gets the sound, money, the PARTY line and every Hero's goods (``goods``) are as
before.
"""

from lib import expect

MUTE_SFX = "SFX 114"


def control(s, spot, button, what):
    """Ness standing on Mr. Saturn's ``spot`` (x, y, dir) and pressing ``button`` reaches the target."""
    s.do("snap ctl")
    said = s.said(f"teleport {spot[0]} {spot[1]} {spot[2]}; wait 30; press {button}; until text 120", met=True)
    expect(said and "No pro" not in said, f"Ness on the same spot reaches {what}", said)
    s.do("restore ctl")


def muted(ctx, s, cmd, what):
    """Run ``cmd`` (P2 presses at a target that isn't Look-only); check sound, no text, no window."""
    before, goods = s.state(), s.goods()
    out = s.do(f"{cmd}; wait 1")
    expect(MUTE_SFX in out, f"the Mr. Saturn sound for {what}", out)
    expect(not any(ln.startswith("TEXT") for ln in out), f"no text for {what}", out)
    for _ in range(12):
        expect(s.windows() == [], f"no window on any frame for {what}", s.windows())
        s.do("wait 1")
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1", f"idle again after {what}, focus back to P1", st.players_line)
    expect(st.money == before.money and st.party == before.party, f"money and Party unchanged by {what}", st.party)
    expect(s.goods() == goods, f"every Hero's goods unchanged by {what} {goods}", s.goods())
    return st


def run(ctx):
    s = ctx.session(save="02-Sharks", players=2)
    s.boot()
    s.do("flag 11 1; wait 4")
    st = s.state()
    near = st.near
    lead = st.pos
    clerk = (lead[0] + near["npc58"][0], lead[1] + near["npc58"][1])
    porter = (lead[0] + near["npc59"][0], lead[1] + near["npc59"][1])
    phone = (lead[0] + near["npc60"][0], lead[1] + near["npc60"][1])

    # The clerk: no text, no window, a sound; the pause menu never opens
    spot = (clerk[0] - 5, clerk[1] + 16, 0)
    control(s, spot, "L", "the clerk")
    s.do(f"companion 2 {spot[0]} {spot[1]} {spot[2]}; wait 2")
    st = muted(ctx, s, "P2 press A", "the hotel clerk")
    ctx.shot(s, "clerk: only a sound")

    # The phone, with L
    spot = (phone[0], phone[1] + 16, 0)
    control(s, spot, "L", "the phone")
    s.do(f"companion 2 {spot[0]} {spot[1]} {spot[2]}; wait 2")
    muted(ctx, s, "P2 press L", "the phone")

    # The porter: his line shows, he faces Mr. Saturn, and nothing else happens
    s.do(f"companion 2 {porter[0] - 16} {porter[1]} 2; wait 2")
    out = s.do("P2 press A; wait 1")
    expect(MUTE_SFX not in out, "no Mr. Saturn sound for the porter", out)
    s.do("until text 120", met=True)
    st = s.state()
    expect(st.focus == "P2 locked" and "PAUSE_MENU" not in st.state, "P2 Talks (no pause menu)", st.state)
    ctx.shot(s, "porter talks to Mr. Saturn")
    said = s.said("until idle 1500 P2 advance", met=True)
    expect(said or s.state().idle == "yes", "the porter's text", said)
    st = s.state()
    expect(st.idle == "yes" and st.focus == "P1" and st.money == 829, "done, nothing changed", st.state)

    # Outside: the sign reads, the trash can doesn't
    s.do("teleport 2110 1452 2; wait 30")
    s.do("companion 2 2008 1452 0; wait 2")
    out = s.do("P2 press L; wait 1")
    expect(MUTE_SFX not in out, "no Mr. Saturn sound for the sign", out)
    said = s.said("until text 120; until idle 1500 P2 advance", met=True)
    expect("35 dollars per night" in said, "the hotel sign's text", said)
    out = s.do("flag 803")
    expect("FLAG 803 = 0" in out, "the trash can not searched yet", out)
    control(s, (2208, 1420, 0), "L", "the trash can")
    s.do("companion 2 2208 1420 0; wait 2")
    muted(ctx, s, "P2 press A", "the trash can")
    out = s.do("flag 803")
    expect("FLAG 803 = 0" in out, "the trash can's flag untouched", out)
    ctx.shot(s, "trash can: only a sound")

"""The dialogue window's title names the Player driving it, in co-op only.

- 27-Kraken, 2 Players: P2's Paula talks to the Summers sailor (Talk to from P2's pause menu): the text
  window is titled ``P2``; P1 talking to him is ``P1``.
- 02-Sharks, 2 Players (P2 the Companion): Mr. Saturn talks to the hotel porter: ``P2``.
- 02-Sharks solo: Ness talks to the porter and the window has no title (vanilla).
"""

import re

from lib import expect


def text_title(s):
    """The standard text window's (w1) title, '' when it has none, None when it isn't open."""
    for ln in s.windows():
        m = re.match(r"WIN w1\*?( \[([^\]]*)\])?\|", ln)
        if m:
            return m.group(2) or ""
    return None


def run(ctx):
    s = ctx.session(save="27-Kraken", players=2)
    st = s.kraken_spot("sailor")
    s.do("P2 40 DOWN; wait 4; P2 press A; wait 20; P2 press A; until text 300 P2 -", met=True)
    expect(text_title(s) == "P2", "P2's Talk to: the text window says P2", s.windows())
    ctx.shot(s, "P2 talks: P2 on the text window")
    s.do("until in:SELECTION_MENU 1500 P2 advance", met=True)
    expect(text_title(s) == "P2", "still P2 at his question", s.windows())
    s.do("P2 press RIGHT; wait 6; P2 press A; until idle 900 P2 advance", met=True)
    expect(text_title(s) is None, "the text window closed", s.windows())
    # P1 walks up to the sailor and talks
    lead = st.pos
    dx, dy = st.near["npc1065"]
    s.do(f"teleport {lead[0] + dx} {lead[1] + dy - 12} 4; wait 4; press L; until text 300", met=True)
    expect(text_title(s) == "P1", "P1 talks: the text window says P1", s.windows())
    s.do("until in:SELECTION_MENU 1500 advance; press RIGHT; wait 6; press A; until idle 900 advance", met=True)

    c = ctx.session("companion", save="02-Sharks", players=2)
    c.boot()
    c.do("flag 11 1; wait 4")
    st = c.state()
    porter = (st.pos[0] + st.near["npc59"][0], st.pos[1] + st.near["npc59"][1])
    c.do(f"companion 2 {porter[0] - 16} {porter[1]} 2; wait 2; P2 press A; until text 120", met=True)
    expect(text_title(c) == "P2", "Mr. Saturn talks: P2", c.windows())
    ctx.shot(c, "Mr. Saturn talks: P2")
    c.do("until idle 1500 P2 advance", met=True)

    solo = ctx.session("solo", save="02-Sharks", players=1)
    solo.boot()
    solo.do("flag 11 1; wait 4")
    st = solo.state()
    porter = (st.pos[0] + st.near["npc59"][0], st.pos[1] + st.near["npc59"][1])
    solo.do(f"teleport {porter[0] - 16} {porter[1]} 2; wait 4; press L; until text 120", met=True)
    expect(text_title(solo) == "", "solo: no title on the text window", solo.windows())

"""M7: no Battle rotation with more than one Hero in the Party: Owners pick, every turn.

12-Zombies (Ness, Paula, Jeff), 4 Players: P1 Ness, P2 Paula, P3 Jeff, P4 absent. Two turns in a row, each
Hero's menu is its Owner's, and P4 never gets one.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="12-Zombies", players=4)
    s.boot()
    s.do("teleport 4000 9300 4; until battle 900 DOWN|DOWN|LEFT; until input 1500; wait 10")
    for turn in (1, 2):
        for title, owner, moves in (
            ("Ness P1", 1, "RIGHT DOWN"),
            ("Paula P2", 2, "RIGHT DOWN"),
            ("Jeff P3", 3, "RIGHT DOWN"),
        ):
            st = s.state()
            expect(
                s.title() == title and st.focus == f"P{owner}",
                f"turn {turn}: the {title} menu, focus P{owner}",
                (s.windows(), st.players_line),
            )
            before = s.windows()
            s.do("P4 press RIGHT; wait 8; P4 press A; wait 8")
            expect(s.windows() == before, f"turn {turn}: P4's presses on {title}'s menu change nothing", s.windows())
            s.do("; ".join(f"P{owner} press {m}; wait 5" for m in moves.split()))
            opts, sel = s.menu()
            expect(opts[sel] == "Defend", f"P{owner}'s cursor on Defend", (opts, sel))
            if owner == 3:
                said = s.said("P3 press A; until input 3000 P4 advance; wait 10")
                for want in ("Ness is on guard", "Paula is on guard", "Jeff is on guard"):
                    expect(want in said, f"'{want}' in turn {turn}'s text", said)
            else:
                s.do(f"P{owner} press A; until input 300; wait 10")
    s.do("debug on; press SELECT+START; until idle 1500 advance")
    expect(s.state().idle == "yes", "the battle ends", s.state().state)

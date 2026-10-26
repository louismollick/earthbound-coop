"""M2: every way out of a co-op battle returns the focus to normal with no stuck lock.

- Win: 12-Zombies, 2 Players, debug instant win from Ness's menu.
- Flee: 01-Start (Ness; P2 a Spectator), the Onett crow's surprise opening makes Run Away certain.
- Game over: 12-Zombies, every Hero's HP set to 0; "another shot?" Yes reloads the last save.

After each, the Party is idle with focus=P1 (the Leader's Owner, unlocked), and P2 (joined, with a Walker:
Paula is revived after the game over, which brings back only Ness) can still take the overworld lock by
opening the pause menu (then let it go).
"""

from lib import expect


def back_to_normal(s, what):
    st = s.state()
    expect(st.idle == "yes" and "battle=0" in st.state and st.focus == "P1", f"{what}: idle, focus P1", st.players_line)


def p2_can_lock(s, what):
    st = s.state()
    expect(st.players[2].joined and st.players[2].walker, f"{what}: P2 joined with a Walker", st.players_line)
    s.do("P2 press A; wait 20")
    st = s.state()
    expect(st.focus == "P2 locked" and "PAUSE_MENU" in st.state, f"{what}: P2 opens the menu on its lock", st.state)
    s.do("P2 press B; wait 2")
    back_to_normal(s, what)


def run(ctx):
    s = ctx.session("win", save="12-Zombies", players=2)
    s.boot()
    s.do("teleport 4000 9300 4; until battle 900 DOWN|DOWN|LEFT; until input 1500; wait 10")
    expect(s.state().focus == "P1", "Ness's menu, focus P1", s.state().players_line)
    s.do("debug on; press SELECT+START; until idle 1500; debug off")
    back_to_normal(s, "win")
    p2_can_lock(s, "win")

    s = ctx.session("flee", save="01-Start", players=2)
    s.boot()
    s.do("teleport 2660 440 4; until battle 500 DOWN|RIGHT|LEFT; until input 1500; wait 10")
    s.do("press RIGHT; wait 5; press RIGHT; wait 5; press DOWN; wait 5")
    opts, sel = s.menu()
    expect(opts[sel] == "Run Away", "the cursor on Run Away", (opts, sel))
    said = s.said("press A; until idle 3000 P2 advance")
    expect("and did!" in said, "the Party got away", said)
    back_to_normal(s, "flee")
    ctx.shot(s, "after fleeing")

    s = ctx.session("gameover", save="12-Zombies", players=2)
    s.boot()
    s.do("teleport 4000 9300 4; until battle 900 DOWN|DOWN|LEFT; until input 1500; wait 10")
    s.do("hp 1 0; hp 2 0; hp 3 0; press A; until input 300; wait 10; press A")
    said = s.said("until said:lost 1500 P2 advance; until input 3000 advance; wait 10")
    expect("lost the battle" in said and "another shot" in said, "the game-over prompt", said)
    expect(s.menu() == (["Yes", "No"], 0), "Yes/No with the cursor on Yes", s.windows())
    ctx.shot(s, "game over prompt")
    s.do("press A; until idle 3000 advance")
    back_to_normal(s, "game over")
    # "Another shot" brings back only Ness: Paula stays unconscious, so P2 has no Walker until she is revived
    st = s.state()
    expect(st.players[2].joined and st.players[2].spectator, "game over: P2 joined, Paula still down", st.players_line)
    s.do("status 2 1 0; heal; wait 10")
    p2_can_lock(s, "game over")

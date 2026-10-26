"""M2: a solo battle is vanilla: P1 picks every command and the menu titles carry no Player tag.

12-Zombies, one Player. Ness, Paula and Jeff's menus are titled with just their names.
"""

from lib import expect


def run(ctx):
    s = ctx.session(save="12-Zombies")
    s.boot()
    s.do("teleport 4000 9300 4; until battle 900 DOWN|DOWN|LEFT; until input 1500; wait 10")
    expect(s.title() == "Ness", "Ness's menu titled 'Ness'", s.windows())
    ctx.shot(s, "solo: Ness's menu, no tag")
    s.do("press A; until input 300; wait 10; press A; until input 300; wait 10")
    expect(s.title() == "Paula", "Paula's menu titled 'Paula'", s.windows())
    s.do("press RIGHT; wait 5; press DOWN; wait 5; press A; until input 300; wait 10")
    expect(s.title() == "Jeff", "Jeff's menu titled 'Jeff'", s.windows())
    said = s.said("press A; until input 300; wait 10; press A; until input 3000 advance")
    expect("Ness attacks" in said and "Paula is on guard" in said, "P1's commands ran", said)
    expect(s.state().focus == "P1", "focus P1", s.state().players_line)
    s.do("debug on; press SELECT+START; until idle 1500 advance")
    expect(s.state().idle == "yes", "the battle ends", s.state().state)

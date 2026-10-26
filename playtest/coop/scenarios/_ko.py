"""Shared body of the m4_ko_* scenarios: a Scaraba desert battle (28-Scaraba) with a Hero knocked out in it."""

from lib import expect

# The recipe from the playtest skill: walk the desert until an enemy touches the Party
BATTLE = "teleport 1400 5600 4; until battle 1500 RIGHT|DOWN|LEFT|UP; until input 1500"


def battle_ko(ctx, member, players=2):
    """Start a desert battle, knock party member ``member`` out in it, win (debug) and return to the overworld."""
    s = ctx.session(save="28-Scaraba", players=players)
    s.boot()
    s.do(BATTLE)
    st = s.state()
    expect("BATTLE" in st.state, "a desert battle", st.state)
    s.do(f"status {member} 1 1; debug on; press SELECT+START; until idle 3000 advance")
    st = s.state()
    expect(st.idle == "yes" and "BATTLE" not in st.state, "back on the overworld", st.state)
    expect(f"{member}:" in st.party and "unconscious" in st.party, f"member {member} unconscious", st.party)
    return s, st

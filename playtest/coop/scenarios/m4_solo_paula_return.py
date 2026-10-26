"""Solo Chapter: the last steps before Paula rejoins, played through at 2 and 4 Players.

21-Monotoli (Ness and Jeff; Paula's Owner P2 walks a Mr. Saturn, and so does P4, Poo's Owner, with 4 Players).

Shortcut: a teleport into the Monotoli Building's 48F Clumsy Robot room (`teleport 6080 5992 6`) skips the walk from
the Monotoli Grand Hotel through the lobby, 47F, 48F and the Sentry Robots. Everything after it is played:
- The Clumsy Robot battle (P1 claims Ness's menu and picks Auto Fight) and its scripted end: the Runaway Five
  arrive and finish the robot.
- The walk to the office door with everyone walking along, and through it.
- The office: Jeff's Owner walks Jeff away (4 Players: P3) and the Mr. Saturns spread out, then Ness walks into
  Monotoli's "Stop!" scene. Ness's Owner talks to Paula (npc873, not in the Party yet), then to Monotoli (npc872):
  his confession adds Paula back. Nobody else answers him. Afterwards every Player walks their own Hero and P2's
  Mr. Saturn is gone.

Not played: Moonside, Fourside and Talah Rama between the kidnapping (m4_solo_paula) and this room; the Party is
Ness and Jeff throughout that stretch, which the soak plays from 19-Moonside and 20-TarahRama.
"""

from _solo import advance_until, expect_companions_walk, expect_party, expect_walk_apart, owner, talk_to, walk_to
from lib import expect

OFFICE = (5656, 5984)  # the office door's landing


def play(ctx, n):
    jeff = owner("Jeff", n)
    s = ctx.session(f"return{n}p", save="21-Monotoli", players=n)
    s.boot()
    expect_party(s.state(), n, ("Ness", "Jeff"))

    # The Clumsy Robot (shortcut to its room), Auto Fight, the Runaway Five's rescue
    s.do("teleport 6080 5992 6; wait 5; 10 UP; 40 LEFT; press L; until text 60")
    expect(any(ln.startswith("UNTIL met") for ln in s.do("until command 3000 advance")), "the battle", s.state())
    if jeff != 1:  # two Players with Heroes: the battle waits for a claim
        expect(s.state().choose == [1, jeff], f"a claim from P1 or P{jeff}", s.state().players_line)
        s.do("press A; until in:BATTLE_MENU 300", met=True)
    s.do("wait 10; press RIGHT; wait 5; press RIGHT; wait 5")
    opts, sel = s.menu()
    expect(s.title() == "Ness P1" and opts[sel] == "Auto Fight", "P1 on Ness's Auto Fight", (s.windows(), opts, sel))
    said = s.said("press A; until idle 12000 advance", timeout=300, met=True)
    st = s.state()
    expect("BATTLE" not in st.state and st.idle == "yes", "the battle and the rescue ended", st.state)
    expect_party(st, n, ("Ness", "Jeff"))
    ctx.shot(s, f"{n}P: the Runaway Five rescued Ness and Jeff from the Clumsy Robot")

    # To the office door, everyone walking along
    s.do("20 RIGHT; 30 DOWN")
    walk_to(s, 5896, 6008, 1, n)
    s.do("until in:DOOR_TRANSITION 60 UP; until idle 300", met=True)
    st = s.state()
    expect(st.pos == OFFICE, f"in Monotoli's office at {OFFICE}", st.state)
    expect_party(st, n, ("Ness", "Jeff"))

    # Everyone spreads out, then Ness walks into the "Stop!" scene
    s.do("wait 2")
    expect_companions_walk(s, "Ness", n, "20 RIGHT")
    if jeff != 1:
        expect_walk_apart(s, n, {jeff: "30 RIGHT"})
    ctx.shot(s, f"{n}P: Monotoli's office, everyone spread out")
    out = s.do("until text 200 DOWN", met=True)
    met, said = advance_until(s, "idle", 3000)
    st = s.state()
    expect(met and "Stop!" in " ".join(out) + said, "Monotoli's 'Stop!'", said)
    expect_party(st, n, ("Ness", "Jeff"))

    # Ness's Owner talks to Paula (still not in the Party), then to Monotoli: his confession adds her back
    said = talk_to(s, "npc873", 1)
    met, more = advance_until(s, "idle", 3000)
    expect(met and "listen to" in said + more, "Paula asks Ness to listen to Monotoli", (said + more)[-120:])
    expect_party(s.state(), n, ("Ness", "Jeff"))
    said = talk_to(s, "npc872", 1)
    met, more = advance_until(s, "in:SELECTION_MENU", 8000)
    st = s.state()
    expect(met and "2:Paula" in st.party, "Paula back in the Party during the talk", (said + more)[-120:] + st.party)
    expect(st.focus == "P1 locked", "P1 holds the lock", st.players_line)
    before = s.windows()
    s.do("; ".join(f"P{q} press RIGHT; wait 5; P{q} press A; wait 10" for q in range(2, n + 1)))
    expect(s.windows() == before, "nobody else answers Monotoli", s.windows())
    said = s.said("press RIGHT; wait 5; press A; until idle 3000 advance; wait 2", met=True)
    st = s.state()
    expect("goodbye" in said and st.idle == "yes", "the talk ends with control", said[-100:] + st.state)
    expect_party(st, n, ("Ness", "Paula", "Jeff"))
    expect(st.players[2].walker == "Paula" and not st.players[2].companion, "P2's Mr. Saturn gone", st.players_line)
    moves = {2: "20 DOWN", 1: "20 LEFT"} if n == 2 else {2: "20 DOWN", 3: "20 UP"}
    expect_walk_apart(s, n, moves)
    ctx.shot(s, f"{n}P: Paula rejoined in the office, P2 walks her")


def run(ctx):
    play(ctx, 2)
    play(ctx, 4)

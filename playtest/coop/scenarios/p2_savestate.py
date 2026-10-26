"""P2's join survives a savestate: in-process snap/restore, and a restore in a fresh process."""

import shutil

from lib import expect


def joined(p):
    return [n for n, pl in sorted(p.items()) if pl.joined]


def run(ctx):
    s = ctx.session()
    s.new_game()
    s.do("P2 press START")
    expect(joined(s.players()) == [1, 2], "P2 joined", joined(s.players()))
    out = s.do("snap coop")
    expect("SNAP coop ok" in out, "SNAP coop ok", out)

    s.do("P2 130 SELECT+START; wait 5")
    expect(joined(s.players()) == [1], "P2 left before the restore", joined(s.players()))
    out = s.do("restore coop")
    expect("RESTORE coop ok" in out, "RESTORE coop ok", out)
    st = s.state()
    expect(joined(st.players) == [1, 2], "P2 joined again after restoring the snap", st.players_line)
    ctx.shot(s, "restored")

    # A fresh solo process restores the same slot: P2 comes back with it
    t = ctx.session("fresh")
    (t.dir / "snaps").mkdir()
    for f in (s.dir / "snaps").glob("coop.*"):
        shutil.copy(f, t.dir / "snaps" / f.name)
    expect(joined(t.players()) == [1], "only P1 joined in the fresh process", joined(t.players()))
    out = t.do("restore coop; wait 1")
    expect("RESTORE coop ok" in out, "RESTORE coop ok in the fresh process", out)
    st2 = t.state()
    expect(joined(st2.players) == [1, 2], "P2 joined after the cold restore", st2.players_line)
    expect(st2.pos == st.pos, f"the restored Leader at {st.pos}", st2.pos)
    p = st2.players
    expect(p[2].owns == [] and p[2].spectator, "P2 a Spectator after the cold restore", p[2])

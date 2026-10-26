# EarthBound Co-op

Local, then online, multiplayer for EarthBound on PC. Several players share one game world and play the original campaign together.

## Language

### People and characters

**Player**:
A human with a controller, local or remote. Numbered P1 to P4.
_Avoid_: user, client, peer (when meaning the person)

**Hero**:
One of the four story characters: Ness, Paula, Jeff, Poo.
_Avoid_: character, party member (too broad), PC

**Guest**:
A temporary party member who is not a Hero (Pokey, Picky, King, Tony, Bubble Monkey, Dungeon Man, Flying Man). The game controls Guests unless a Stand-in claims one.
_Avoid_: NPC party member, companion

**Owner**:
The Player bound to a Hero for the whole campaign. Heroes are dealt round-robin by join order (Hero *i* belongs to Player *i* mod *N*), so with two Players P1 owns Ness and Jeff and P2 owns Paula and Poo. A Player owns one or more Heroes.
_Avoid_: controller of, seat

**Walker**:
The one Party member a Player moves on the map: their first owned Hero present in the Party, or the Guest they stand in for. Their other owned members trail behind their Walker.
_Avoid_: avatar, active character

**Stand-in**:
A Player whose Hero is not in the Party, temporarily controlling a Guest.

**Spectator**:
A Player whose Hero is not in the Party and who has no Guest to stand in for. During a Solo Chapter they walk the Companion and take Battle rotation turns.

**Companion**:
Mr. Saturn, walked on the overworld by a Spectator during a Solo Chapter. Overworld only: sits out battles, has no stats, and is never part of the Party.
_Avoid_: cat, pet, co-op character

**Look-only interaction**:
A Talk to / Check whose text script, followed through its jumps and calls, only prints text, waits and reads flags (no flag writes, items, money, battles, Party changes or events). The Companion may trigger only these; anything else gets a Mr. Saturn sound and no text.

**Battle rotation**:
In a Solo Chapter battle, the solo Hero's command is picked by its Owner, then each Spectator in join order, one turn each, round and round.

### World

**Party**:
The Heroes and Guests currently travelling together.
_Avoid_: team, group

**Leader**:
The first conscious member of the Party. Party-wide actions (saving at a phone, the bicycle, Teleport, running from battle) belong to the Leader.

**Shared World**:
The rule that all Players are in one game world on one screen, with no independent exploration.
_Avoid_: split screen, open co-op

**Solo Chapter**:
A story stretch where the game replaces the Party with a single Hero (Jeff in Winters, Poo's Mu training, Magicant, Paula's kidnapping). That Hero's Owner plays; everyone else is a Spectator or Stand-in.

### Input

**Focus**:
Whose pad the game reads right now: one Player, or ALL (every joined Player's pad combined). On the overworld it is the Leader's Owner unless someone holds the Lock.
_Avoid_: active player, controller

**Lock**:
On the overworld, the Player who opened a menu, text box or interaction holds the Focus until the Party is idle again.

### Online

**Host**:
The Player whose machine owns the save file and admits others into the Session.

**Session**:
One online play-through joined by up to four Players, all running the same game in step.

**Desync**:
Any frame where two machines in a Session disagree about game state.

## Flagged ambiguities

- "Co-op character" was used for both Guests and the co-op-only Solo Chapter character. Guests are story characters; the co-op-only one is the Companion (Mr. Saturn, formerly planned as a cat).

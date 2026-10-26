#ifndef EB_COOP_COOP_COMPANION_H
#define EB_COOP_COOP_COMPANION_H

/*
 * Local co-op Companion (M7, vocabulary in CONTEXT.md, design in
 * docs/coop-design/party-changes.md "Companion").
 *
 * Every absent Player who isn't a Stand-in (coop_companion) walks their own
 * Mr. Saturn on the overworld: an NPC-slot entity (sprite MR_SATURN, the
 * static NPC script EVENT_44) moved with the same borrowed Leader step as a
 * Walker (coop_walk_internal.h), so walls, water, ladders and ropes work;
 * doors, door text, stairs and escalators are walls for it. Its hitbox is off,
 * so it walks through NPCs, no NPC or enemy ever bumps into it, and it never
 * starts a battle. It doesn't move the camera; it is leashed to the view
 * instead (a step that would take it further than the leash margin out of the
 * view is reverted on that axis), and if the view leaves it behind anyway it
 * reappears next to the Leader.
 *
 * Lifetime: spawned on the first free overworld frame (retried while entity
 * slots or sprite VRAM are full), in the highest free NPC slot so scripts that
 * look entities up by sprite find a real Mr. Saturn first. A map load
 * (clear_map_entities) wipes it and it respawns next to the Leader. It hides
 * when an enemy touches the Party, for the battle, and when the game moves the
 * Party (doors, stairs, escalators, the bicycle, teleport, cutscene camera
 * moves), and reappears next to the Leader once the Party is free again. It is
 * removed when its Player stops being a Companion (their Hero rejoined, a
 * Guest to stand in for arrived, they left).
 *
 * Its Player may take the overworld lock with A or L only, and both act as L
 * (Check/Talk, never the pause menu): see coop_input.h.
 *
 * All state is in CoopState.companions (serialized); the entity itself is in
 * the serialized entity tables.
 */

#include "coop/coop_walk_internal.h"
#include "core/types.h"

/* From coop_walk_leader_tick, after the camera moved: spawn, despawn, step,
 * hide and show every Player's Companion for this frame. */
void coop_companion_tick(WalkControl control);

/* Once per game frame (coop_tick): from an enemy touch to the end of the
 * battle no entity ticks, so this hides every Companion then. */
void coop_companion_watch(void);

/* The Party regroups (a door's fade, PSI Teleport) or the Leader's trail was
 * reset (map load): every Companion hides, to reappear next to the Leader. */
void coop_companion_hide_all(void);

/* Player p's Companion entity slot if it is out and visible, else -1. */
int16_t coop_companion_entity(int player);

/* coop_interact for a Companion's Player: run `fn` (talk_to or check_action)
 * searching from Mr. Saturn, who then faces what it found. */
uint32_t coop_companion_interact(int player, uint32_t (*fn)(void));

#endif /* EB_COOP_COOP_COMPANION_H */

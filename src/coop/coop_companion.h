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
 * doors, door text, stairs and escalators are walls for it. NPCs block it
 * (its hitbox is on only for its own step), enemies don't: no NPC or enemy ever
 * bumps into it, and it never starts a battle. It doesn't move the camera; it is leashed to the view
 * instead (a step that would take it further than the leash margin out of the
 * view is reverted on that axis), and if the view leaves it behind anyway it
 * reappears next to the Leader.
 *
 * Lifetime: spawned on the first free overworld frame (retried while entity
 * slots or sprite VRAM are full), in the highest free NPC slot. Hidden means
 * removed: it has an entity only while it is out. It hides when an enemy
 * touches the Party, for the battle, at a door's fade or PSI Teleport, and
 * under game control once the game moves the Party (stairs, escalators, the
 * bicycle, boarding a bus, a cutscene walk) or the view leaves it behind; it
 * reappears next to the Leader once the Party is free again. A freeze alone
 * (most NPC dialogue) leaves it standing where it is. A map load (clear_map_entities) wipes it and it respawns the same
 * way. It is removed for good when its Player stops being a Companion (their
 * Hero rejoined, a Guest to stand in for arrived, they left).
 *
 * The game's own entities always win: when create_entity / entity_init would
 * fail, they remove every Companion and retry (coop_companion_reclaim), and
 * the Companions come back once there is room. Lookups by sprite or NPC id
 * (find_entity_by_sprite_id, find_entity_by_npc_id) skip them.
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

/* Once per game frame (coop_tick), entity ticks frozen or not: hides every
 * Companion while a battle is coming or on, and any the view left behind while
 * the game controls movement. */
void coop_companion_watch(void);

/* The Party regroups (a door's fade, PSI Teleport) or the Leader's trail was
 * reset (map load): every Companion hides, to reappear next to the Leader. */
void coop_companion_hide_all(void);

/* The Player's warp (coop_walk_leader_tick): their Mr. Saturn, if out, moves
 * next to the Leader. */
void coop_companion_warp(int player);

/* Player p's Companion entity slot if it is out (visible), else -1. */
int16_t coop_companion_entity(int player);

/* Some Companion is out (has an entity). Never true without co-op. */
bool coop_companion_spawned(void);

/* The game needs room (entity_init, create_entity): remove every Companion's
 * entity; they respawn next to the Leader when there is room. True if it
 * removed any. */
bool coop_companion_reclaim(void);

/* Entity `e` is a Companion's Mr. Saturn (lookups by sprite / NPC id skip it). */
bool coop_companion_slot(int16_t e);

/* coop_interact for a Companion's Player: run `fn` (talk_to or check_action)
 * searching from Mr. Saturn, who then faces what it found. */
uint32_t coop_companion_interact(int player, uint32_t (*fn)(void));

#endif /* EB_COOP_COOP_COMPANION_H */

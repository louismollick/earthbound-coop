# Walkers, trails, camera, contact, interaction (M1): design memo

Research memo, 2026-10-26. Line numbers are against d32c421 and drift.

**As built (M1 ownership + independent walking):** `src/coop/coop_walk.{h,c}`. It follows the recommended design below, with three differences: a window or text box only pauses Walkers (no snap); unsnap lays each chain's trail through its members' current positions instead of copying the Leader's ring; and the Leader's Owner's pad feeds `core.pad1` (`coop_pad1_feed`). Interaction is built in `src/coop/coop_input.c` (`coop_interact`, see input-focus.md). The camera, leash, contact and regroup sections are still to do.

## How the Leader moves
- **Pad.** `memory_update_joypad` (`memory.c:38-69`) is fed by `host_process_frame`. Demo playback can override it (`overworld.c:2280-2300`).
- **Per-frame path.** The init entity (slot 23) ticks `update_overworld_frame` (`overworld.c:1237`), which calls `update_leader_movement` (`position_buffer.c:1547`):
  1. saves and clears `leader_moved`;
  2. syncs the Leader's `position_index` to the write head;
  3. dispatches on `camera_mode` and walking style (`:1579-1595`);
  4. reads surface flags (`:1600`);
  5. writes the trail (`:1609`);
  6. calls `center_screen` only if the Leader moved (`:1624`).
- **Leader state.** `game_state.leader_x/y_frac`, `leader_x/y_coord`, `leader_direction`, `trodden_tile_type`, `walking_style`, `leader_moved`, `current_party_members` (the Leader's entity slot).
- **Walking step.** `update_overworld_player_input` (`position_buffer.c:1365-1538`), in order:
  1. mushroom remap;
  2. `map_input_to_direction`, which reads `core.pad1_held` and returns -1 while `ow.pending_interactions` is set (`:977-996`);
  3. swirl countdown;
  4. stairs forcing;
  5. `adjust_position`, for water and Skip Sandwich speeds (reads `game_state.walking_style`);
  6. collision: `check_directional_collision` (`map_loader.c:3096`, with wall-slide re-aim), or `get_collision_at_pixel` when `player_movement_flags & 2`;
  7. NPC blocking: `npc_collision_check` (`overworld_collision.c:428`), which writes `entities.collided_objects[23]`;
  8. ladder, rope and door tiles: `process_door_at_tile` (`door.c:608`):
     - type 1: ladder or rope
     - type 2: door, through `try_activate_door`, which queues interaction 2
     - type 3: escalator
     - type 4: stairs
  9. hotspots: `check_hotspot_exit` (`:1514-1520`);
  10. ladder X snap (`:1524`).
- **Collision grid.** 64×64 tiles centred on the camera (`map_loader.c:612`).
- **Enemy contact.** `HANDLE_ENEMY_CONTACT` (`callroutine.c:1859`) calls `check_entity_enemy_collision` (`overworld_collision.c:69`). It fires when `collided_objects[23] ==` the enemy, or when the enemy bumped slots 24-29.
  - The target is 24 for a Leader touch, otherwise the bumped slot (`callroutine.c:1913-1917`).
  - First strike is judged in `initiate_enemy_encounter` (`overworld_spawn.c:709`). It uses `game_state.leader_direction` (`:757`).

## Followers
- **The trail.** One 256-entry ring, `pb.player_position_buffer`, with head `game_state.position_buffer_index`.
- **Party entities.**
  - `var[0]` = char id; `var[1]` = `party_characters` index = slot − 24.
  - Slots 24-27 are the Heroes; 28 and 29 are Guests.
- **Follower tick.** `update_follower_state` (`:1648-1746`) reads `ring[position_index]`.
  - Spacing is measured against the previous member in `party_order` (`get_previous_position_index` `:321`, `adjust_party_member_visibility` `:388`).
  - A follower only moves when `game_state.leader_moved` is set (`:1673`). `update_party_entity_graphics` picks walking or standing frames from the same flag (`:261`).
- **Screen position.** `UPDATE_PARTY_SPRITE_POSITION` (`callbacks.c:146-159`) skips recomputing screen coordinates for some followers. That assumes the camera moves with the Leader.

## Camera, spawns and despawns
- `center_screen` → `map_refresh_tilemaps` (`map_loader.c:2635`):
  - sets the BG scroll to camera − `EB_VIEWPORT_CENTER`;
  - streams NPC spawns, which are camera-relative ([-65, W+64) × [-65, H+96), `:2316-2343`);
  - refills tiles and collision.
- **Despawn is Leader-relative.** `IS_ENTITY_NEAR_LEADER` (`callroutine_screen.c:844-861`, `callroutine_sprite.c:270-281`) measures from the Leader. With a midpoint camera it must measure from the camera centre instead.
- The smooth camera only engages when the scroll equals Leader − centre (`smooth_camera.c:44`). Disable it in co-op.

## Talk to / Check
- **The A path.** A opens the pause menu, and L pushes `GAME_MODE_QUICK_CHECKTALK`. Its `QCT_TEXT` phase (`text.c:3459-3470`) calls `talk_to()` then `check_action()`.
- **Everything is measured from the Leader:**
  - `find_clear_direction_for_leader` (`overworld_collision.c:674`) and `check_collision_in_direction` (`:557`) probe at NEAR offsets.
  - Door lookups: `check_door_in_direction` and `check_door_near_leader` (`door.c:653`, `:690`).
  - `set_entity_direction_from_leader` (`overworld_interaction.c:306`) turns the NPC.

## When the game controls movement
- `camera_mode`: 1 = dolly, 2 = follow a focus entity, 3 = enemy shake.
- `ow.player_movement_flags`: set to 3 on stairs and escalators.
- Demo playback is active (`ow.demo_recording_flags & 0x4000`).
- The walking style is ESCALATOR, STAIRS or BICYCLE.
- `dr.using_door` or `ow.psi_teleport_destination` is set.
- `OBJECT_TICK_DISABLED` is set on slot 23 or on a party entity.
- A script has replaced a party entity's tick callback, so it is no longer `UPDATE_FOLLOWER_STATE`.

## Recommended design: reuse the Leader step under a state swap

### The Walker step

After the Leader's dispatch in `update_leader_movement`, run this for each non-Leader Walker. Skip it while the game controls movement, during the battle swirl, after an enemy touch, or in battle.

1. Save the Leader globals and load the Walker's values:
   - position, direction, trodden tile, walking style and `leader_moved`;
   - `current_party_members`, set to the Walker's slot;
   - `core.pad1_held`/`pressed`, set to that Player's pad;
   - the scratch fields: `ow.stairs_direction`, `final_movement_direction`, `not_moving_in_same_direction_faced`, `ladder_stairs_tile_x/y`, `checked_collision_*`, `dr.door_found`/`door_found_type`, `collided_objects[23]`.
2. Neutralise shared state for the call: set the mushroom flag to 0 and the hotspot modes to 0.
3. Call `update_overworld_player_input()`. Make it non-static.
4. Collect the results:
   - recompute the surface from `lookup_surface_flags`;
   - capture `collided_objects[23]` as the Walker's "touched";
   - apply the leash;
   - write the Walker's own trail ring;
   - if the Walker moved, set `ow.player_has_done_something_this_frame` (doors need it).
5. Restore the Leader globals.

### Side effects inside the step

| Side effect | Handling |
|---|---|
| Swirl, mushroom, hotspots | Suppressed |
| Ladder/rope | Kept |
| Door (type 2) | Kept: queues the transition for the whole Party |
| Event text | Kept |
| Escalator/stairs | Blocked as a wall for Walkers; the Leader takes them, and everyone snaps |
| Camera and Leader trail writes | Not called from the step |

The one hook inside `update_overworld_player_input`, at its `process_door_at_tile` call:

```c
can_move = coop_in_walker_step() ? coop_walker_door(x, y) : process_door_at_tile(x, y);
```

### Trails
- Each non-Leader Walker has its own ring plus a head.
- `update_follower_state` routes Walker-chain members to a co-op follower tick. The tick uses the same spacing table and the Walker's moved flag for animation.
- Leader-chain members run vanilla code.
- The memo's way to keep vanilla `party_order` predecessor lookups valid: keep each Walker-chain member's `position_index` as a shadow equal to the previous Leader-chain member's index.
- **Snap** = stop overriding, so everyone is on the Leader's trail.
- **Unsnap** = copy the Leader ring into each Walker ring, so the switch is seamless.
- **Resync** when the trail resets (`init_party_position_buffer`, `fill_party_position_buffer`) or when ownership changes.

### Camera and leash
- The camera is the centre of the Walkers' bounding box, clamped to the map. Apply it with `center_screen` on frames where something moved.
- **Leash:** per axis, the spread is capped at viewport − 2·(viewport/8). A move that would exceed the cap and widen the spread has that axis reverted. The Leader is leashed too.

### Contact
- `check_entity_enemy_collision` also matches any Walker's touched value.
- `HANDLE_ENEMY_CONTACT` targets the Walker's slot.
- First strike uses the target Walker's facing.

### Interaction
- P2-P4 pressing A or L opens the interaction with that Walker swapped into the Leader globals around `talk_to`/`check_action`.
- An NPC that turns to face someone turns toward the Walker.
- The text box pauses everyone already: `map_input_to_direction` returns -1.

## Hooks
1. `update_leader_movement`: begin, end-of-dispatch (leash + Walker steps), camera branch.
2. `update_overworld_player_input`: non-static, plus the door hook.
3. `update_follower_state` → co-op tick for Walker chains.
4. `init_party_position_buffer` / `fill_party_position_buffer` → `coop_on_trail_reset()`.
5. `callbacks.c:149`: always recompute screen positions in co-op.
6. Despawn checks measure from the camera centre.
7. Enemy contact: `overworld_collision.c:77`, `callroutine.c:1913`, `overworld_spawn.c:757`.
8. `text.c` `QCT_TEXT` / `game_main.c` `OWP_POST_INPUT` for Talk and Check.
9. `smooth_camera.c`: return false in co-op.

## Risks
- `refresh_party_entities` (`overworld.c:1679`) places Walker chains at their shadow positions after a battle. The next frame corrects it.
- Pursuit, flee, sector music, hotspots, footsteps and the Mini ghost stay Leader-only.
- The bicycle requires `party_count == 1`.
- Three Walker rings are about 7.7 KB. Size them by `PLATFORM_MAX_PLAYERS`.
- A Walker stuck behind a wall pins the Leader through the leash.
- The host must feed `core.pad1_*` from the Leader's Owner's pad during overworld walking, not an OR of every pad.

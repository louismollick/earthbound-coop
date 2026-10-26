# Serialization audit

Every writable global and static in libgame, checked against the savestate (`src/core/state_dump.c`).
Symbols passed straight to an `ADD(SECTION_...)` entry are serialized and not listed here.
`tests/test_mutable_globals.py` lists the debug build's symbols with `nm` and fails on any symbol that is neither
serialized nor named on a list line below (a backticked name, `fnmatch` pattern, `function.static`, or a whole
`file.c`). A new global goes in a section, or on a line here with its class.

Classes: (s) serialized by a pack/unpack section, (a) read-only ROM asset pointer or cache, (b) host, render
or transient state that is correctly not saved, (c) game state that was missing (now serialized), (d) unclear or
not fixed.

Rule for (a): no read may depend on which code path bound the table first. A savestate restored in a fresh
process (F7 after a restart, a netplay join) resumes the restored mode stack without running boot, `btl_begin`
or a menu's first open. Bind the table in `game_init` (via the module's `*_bind_asset_tables` or init function)
or re-ensure it at every read.

## (s) Serialized through pack/unpack sections

- `oval_window.c` all statics (SECTION_OVAL_WINDOW; `swirl_window_hdma_buffer`/`swirl_window2_hdma*` are rebuilt from the saved oval parameters, see the pack comment)
- `flyover.c` all statics (SECTION_FLYOVER)
- `overworld_tasks` `auto_movement_buffer` `auto_movement_index` `demo_read_ptr` `demo_initial_pad_state` (SECTION_OVERWORLD_DEFERRED)
- `escalator_new_x` `escalator_new_y` `stairs_new_x` `stairs_new_y` (SECTION_DOOR_TRANSITION)
- `background_colour_backup_ow` (SECTION_OW_PALETTE_BACKUP)
- `compare_equipment_mode` `character_for_equip_menu` `temporary_*` `overworld_selected_psi_user` `only_one_character_with_psi` (SECTION_TEXT_MENUS)
- `loaded_transformations` `item_transformations_loaded` `time_until_next_item_transformation_check` (SECTION_ITEM_TRANSFORM)
- `distort_30fps` `bg_state` `bg_distortion` (SECTION_BATTLE_BG)
- `frame_callback` (SECTION_FRAME_CALLBACK)
- `credits_*` `cast_text_row` `cast_tile_offset` `initial_cast_entity_sleep_frames` (SECTION_ENDING_CREDITS)

## (a) ROM asset pointers and caches

- `battle_action_table` `enemy_config_table` `battle_sprites_pointers_data` `btl_entry_ptr_table` `btl_entry_bg_table` `npc_ai_table` `consolation_item_table` `battle_psi_table` `battle_psi_table_size`: `battle_bind_asset_tables()` in game_init (was bound in `btl_begin`/`setup_battle_enemy_sprites`; fixed the continuity failure)
- `tilesetpalette_*` `tileset_table_*` `chunk_data` `chunk_size` `chunks_loaded` `sprite_placement_*` `npc_config_table*` `sector_attributes_*` `collision_arrangement_table*` `collision_pointers_blob*` `entity_collision_*` `event_control_ptr_table_*` `tile_event_data*` `per_sector_music_*` `event_music_*`: `map_loader_init()` in game_init (was bound by the first map load)
- `arrangement_*`: per-tileset arrangement, rebuilt by `map_loader_savestate_rebind()` after a load
- `border_anim_tiles_row1` `border_anim_tiles_row2` `load_border_anim_tiles.raw` `status_tile_table_*` `load_status_tile_tables.raw`: `window_bind_asset_tables()` in game_init (the border animation read NULL when resumed mid-animation)
- `flavour_palettes` `equip_text_data` `fonts`: `text_system_init()` in game_init
- `dialogue_blob*` `inline_string_table*` `status_window_text_*` `status_equip_text_data`: `display_text_init()` in game_init (the status window texts were bound by the status menu, so a restored reader of that text had no base)
- `store_table_*` `telephone_contacts_*` `status_equip_text_7*` `status_equip_text_14*` `phone_call_text_*`: `display_text_menus_bind_asset_tables()` from `display_text_init()`
- `item_config_*` `transform_table_*` `exp_table_*` `stats_growth_*` `stat_gain_mod_*` `psi_table_data_inv` `psi_table_size_inv`: `inventory_bind_asset_tables()` in game_init
- `sprite_grouping_*` `spritemap_config*` `spr_*` `sprite_banks` `sprite_bank_sizes`: `load_sprite_data()` in game_init
- `event_script_pointer_*` `event_ptr_table_buf` `bank_c0_scripts_buf` `bank_c4_scripts_buf` `script_banks` `script_bank_count` `naming_entities_*`: `load_event_script_data()` in game_init
- `map_enemy_placement_data` `enemy_placement_groups_*` `enemy_spawn_data_loaded`: `load_enemy_spawn_data()` in game_init
- `floating_sprite_table_*`: `floating_sprite_table_load()` in game_init
- `dataset_table` `dataset_table_count`: `audio_init()` at startup
- `psi_ability_table_*` `delivery_table` `for_sale_signs` `dt_size` `fs_size` `photographer_cfg_cr` `footstep_sound_table`: ensured at every read
- `dont_care_names_data` `hp_meter_speeds_data` `naming_prompts_data` `initial_stats_data`: `ensure_file_select_assets()` at every consumer (self-heal test)
- `photographer_cfg_*` `cast_seq_formatting_data` `staff_text_*` `party_cast_tile_ids_data` `guardian_text_data`: `ensure_ending_credits_assets()`, also in the credits unpack
- `attract_mode_text_addrs` `attract_mode_offsets_loaded`: loaded again at the read (was bound only by the scene prepare)
- `activate_hotspot.hotspot_data` `reload_hotspots.hotspot_data` `attempt_enemy_spawn.*` `check_enemy_should_flee.btl_ptr_tbl` `enemy_select_mode.*` `mode_step_battle_scripted.*` `initiate_enemy_encounter.*` `setup_battle_enemy_sprites.*` `load_attack_palette.attack_palettes` `load_battle_bg.bg_data_table` `update_battle_screen_effects.shake_amplitude_table` `generate_battlebg_frame.*`: function statics bound just before their read in the same function
- `entity_fade_entries`: was a pointer into `ert.buffer` cached by `init_entity_fade_states_buffer`, NULL in a fresh process (a crash when resumed mid-fade); now derived on each use, so no symbol remains

## (b) Host, render or transient state

- `game_main.c` all: host loop (frame pacing, fast-forward, FPS overlay, debug hotkeys, capture/root-action requests)
- `ppu_render.c` `platform_render.c`: renderer caches and per-frame scratch
- `smooth_camera_*` `sprite_queue_owner` `text_trace_hook` `s_known` `s_pack` `verbose_level`: presentation option, harness hook, savestate writer internals
- `apu` `sfx_queue*` `audio_effect_bit_flipper` `sfx_upper_bit_flipper`: live audio core and its queue; `audio_resync_after_load()` restarts music from the saved `audio_state`
- `pathfinding.c` all: per-call pathfinding scratch (results land in entity state)
- `g_mode_push_init` `g_asf_pending` `as_req` `sm_pending_cursor_text` `skip_adding_command_text` `s_lq_capture` `leader_pad_swapped` `leader_saved_*` `in_walker_step` `unpresented_*` `post_teleport_callback_wram_lo` `cr_bank_idx` `current_bank_idx` `new_sprite_tile_*` `photograph_map_loading_mode` `cur_photo_display` `temp_entity_surface_flags` `set_temp_entity_surface_flags`: set and consumed within one step or call, never across a frame yield
- `g_oam_y_backup` `g_oam_full_y_backup` `map_palette_backup` `bg_palette` `bg_palette_count` `instant_win_sorted_*` `stealable_item_candidates` `vwf_vram_next` `dummy_window` `resolve_text_addr.*` `display_equipment_menu.fallback` `*.slot_labels` `*.speed_names`: scratch rebuilt before each use
- `equip_preview_callbacks` `status_psi_category_names` `pm_build_item_action_menu.item_action_labels`: constant tables that are not const-qualified
- `escalator_stair_active` `window_gfx_loaded` `force_normal_font_for_length_calc` `text_prefix_base` `current_scene_index`: never read (write-only, like the asm's UNREAD_7E5DBA) or never written

## (c) Missing game state, now serialized

- `fastest_hppp_meter_speed` (SECTION_HPPP_METER_SPEED): set by `reset_hppp_rolling`, cleared when the meters settle; restored as 0 it rolled HP/PP at normal speed instead of fast
- `save_files_present` (SECTION_SAVE_FILES_PRESENT): the file-select menu's slot occupancy, read by its copy/delete submenus

## (d) Unclear or not fixed

- `title_script_bank*` `title_spritemap_data` `title_script_pointers` `title_spritemap_offsets` `script_bank_buf` `script_ptrs_buf` `spritemap_buf`: title-screen script bank, registered and freed by `load_title_screen_script_data`/`free_title_screen_script_data`; a savestate taken on the title screen restores without it (title sprites missing). Not fixed: binding it at init would change the script bank registry

## Added after the Companion merge

- `step_kind` (coop_walk.c): (b) set and cleared around one walker-step call in the same frame; never live across frames.
- `sfx_trace_hook` (audio.c): (b) harness test hook (prints SFX lines), set by the host, never game state.

## Monday 20 July
    # Archers
        > fixed arrows passing through enemies without hitting them.
            ... by changing the scope logic in physics.PHYSICS.get_objects to `if scope != 0:` than `if not scope:`.

## Tuesday 21 July
    # Enemy Sprites
        > fixed enemy sprite sheets not being converted to display format on load.
            ... by adding `.convert_alpha()` to the `pygame.image.load()` call in assets.py create_enemy_sprites(). Was forcing a pixel-format conversion on every blit, every frame, for every enemy on screen.

    # Caching
        > fixed CACHED_IMAGES and CACHED_ENTITY_IMAGES growing unbounded for the life of the process.
            ... by switching both from plain dict to OrderedDict in functions.py, with LRU eviction (_lru_touch()) - each cache now self-caps at MAX_CACHED_IMAGES / MAX_CACHED_ENTITY_IMAGES and drops the least-recently-used entry instead of growing forever.
        > fixed CACHED_ENTITY_IMAGES being fully wiped every frame once it passed just 10 entries (server.py).
            ... this was forcing every palette-swapped enemy sprite (a real per-pixel recolor via apply_pallete()) to be recomputed from scratch as soon as a level had more than ~10 enemy/color/state combos on screen. Removed the per-frame full-clear for CACHED_IMAGES, CACHED_ENTITY_IMAGES, and CACHED_RECTS['other'] in server.py since the LRU eviction in functions.py now handles all three on its own.
        > added LOW_SPEC_MODE to settings.py, auto-detected from os.cpu_count() (<=2 logical processors -> True).
            ... scales cache caps down (150/100 vs 500/350) and lowers the menu particle count (60 vs 200) on weaker machines automatically, no manual toggling needed.
        > replaced magic numbers in server.py's per-frame cache-handling block with named constants (PLAYER_WINS_RECT_CACHE_PER_PLAYER, ENTITY_ZOOM_CACHE_MAX_LEVELS, OBJECT_ZOOMED_IMAGES_MAX_PER_KEY, OBJECT_IMAGES_OTHER_CAP, OBJECT_IMAGES_ARROWS_CAP, FONTS_CACHE_CAP).

    # Menu Rendering
        > fixed parallax_bg() doing an unnecessary O(n log n) sort every frame just to iterate particles in reverse.
            ... by replacing sorted(enumerate(bg_particles), reverse=True) with reversed(list(enumerate(bg_particles))) in functions.py - same iteration order, O(n) instead.

    # Documentation
        > added PROJECT_STRUCTURE.md - a file-by-file guide to what every file in the project does, with a focus on game/, plus a "where do I look to change X" quick-reference table.

## Thursday 10 September
    # Level Selector
        > fixed the level-select screen's borrowed Enemy actors (Pawn/TNT/Archer/Torch) always silently failing to construct.
            ... Entity.personalise() unconditionally calls self.game.personalise(entity, times), but the fake _stage_game object level_select.py builds for its isolated art stage never defined that method, so every Enemy(...) call raised AttributeError and was swallowed by _build_stage_actors()'s broad except. No enemy has ever actually appeared on the level-select screen as a result. Fixed by giving _stage_game a no-op personalise() in level_select.py.
        > fixed Deco decorations (mushrooms, etc.) on 2/3 of the level cards silently never rendering.
            ... Deco._resolve_sprites() returns the whole name-keyed Assets.DECO_SPRITES dict (it has no per-instance frame list), but _draw_card_art indexed it with an integer frame number, which always raised KeyError and was caught by a bare except: pass. Fixed _blit_stage_actor in level_select.py to use the Deco's already-resolved .image for deco-type actors instead of indexing into the dict.
        > added Pumpkin/Scarecrow/Bone/Shrub Deco actors, a Torch enemy, and a second Treasure gem colour to the level-select stage roster, all still resolved exclusively through Assets.
        > added a real Pawn/Treasure/Arrow ambient scene in the header gap between the title and search box (skipped automatically when the screen is too narrow for it), and made the mascot vignette's chasing enemy vary with the selected level's difficulty.

## Thursday 10 September
    # Level Selector
        > removed all borrowed Enemy/Bomb/Arrow/Deco/Tree/Treasure entities from the level-select screen.
            ... _build_stage_actors, _blit_stage_actor, _stage_frames, _draw_mascot and _draw_header_scene are gone, along with the fake stage game/owner scaffolding and the entities/objects imports. The details panel now shows a plain static 'NO MAP PREVIEW' box, and level cards show just number/title/theme/difficulty -- no animated vignette, no card decoration, no header gap scene.

## Monday 26 October - WS-C0 + WS-A (ammo plumbing, purchasable minimap + target pointers)
    # Ammo plumbing (WS-C0)
        > New data/ammo.py: AMMO_BASE (arrows / fires / bombs per volley, player vs enemy) and BOMB_CAP.
        > mind.py: ACTIVITY.ammo_count(kind), bomb_cap(), live_bombs(). All hard-coded quantities in mind.py (fire x3, bomb x10, arrow x3) and controls.py (arrow x10) now go through ammo_count(). Shop bonuses (arrow_bonus / fire_bonus / bomb_bonus) apply to PLAYERS only.
        > bomb(): the dead bomb_limit is live again as a cap on bombs alive per owner (players 12 + bomb_cap upgrade, enemies 5).
        > NOTE: the gamepad "shoot arrows" button (controls.py ~L253) used to fire 10 arrows; it now fires ammo_count("arrow") (3 + upgrades), same as an Archer's normal volley. The debug K_b block (~L305) goes in WS-B.
        > shop_effects.py: new effect keys (minimap_level, pointer_level, arrow/fire/bomb bonus, bomb_cap, reload_cut, blast_radius, pierce, charm_*, dash_cd_cut, extra_jumps, luck) are stored in player.shop_stats (STAT_KEYS), rebuilt by apply_loadout and cleared by strip_loadout, so they never stack. New helpers owned_level(player, item_id) and stat(player, key).
    # Minimap + Target Pointers are now shop items (WS-A)
        > data/shop_items.py: minimap (emerald, 4 levels, 2/3/4/5) and target_pointers (ruby, 3 levels, 2/3/4). Vector icons added in ui/shop_icons.py.
        > A fresh run shows neither; buying shows it on the next frame; reset_run() removes it. Only the story shop sells them, so My Worlds / co-op / test maps never show them. Both are skipped when game.EDIT_WORLD.
        > New ui/minimap.py: terrain is rendered once per level into a static layer, then cropped + scaled each frame (no per-frame allocation); rounded mask, glow frame, level pips, scan sweep, facing arrow with blinking ring, other-player dots/edge arrows. L2 wider, L3 enemy dots (boss = big gold), L4 doors (portal colours) + treasure + edge arrow to a far exit. Tap/click toggles small/large. Placed under the MENU button so nothing is hidden. functions.draw_minimap() is now a thin wrapper.
        > entities/target_system.py rewritten: ring of chevrons (pre-rendered + cached), threat colours, fade with distance, pulse when close, nearest-N cap (4/6/8), range 900/1400/2000, L3 type badge. On-screen far enemies are skipped. The call used to sit BEFORE draw() so the world painted over it; it now runs after the world + lighting.
        > coloured entity RGB: combat_fx.rgb_of() made public (old minimap used the colour NAME as an RGB tuple).

## Monday 26 October - WS-F (camera)
    # New scripts/camera.py: Camera class, one per player (player.camera)
        > Player.camera_update() keeps its name/signature/call sites; it now sizes cam_rect for the zoom and calls Camera.update(). CACHED_RECTS / cam_rect_key logic is unchanged.
        > Smooth mode: dead-zone around the look target (closes when standing so the view re-centres), frame-rate independent chase (X faster than Y, Y faster while falling), look-ahead in the travel direction, falling bias down / standing bias up, hold DOWN/UP 0.6 s to peek, landing kick after hard falls, safe box so the player can never leave the screen (fast falls, dashes), state clamped to the world (a level smaller than the view is centred), only the FINAL position is rounded (no sprite shimmer).
        > Snap, never sweep: first frame, a level change, or a >700 px one-update jump (teleport/warp) snaps the camera.
        > Timing uses REAL time (pygame ticks), not the slow-mo scaled game.dt, so it will not go jelly during charm mode.
        > Focus hook for WS-B / WS-G / boss intros: player.camera.focus(target_or_point, weight=1.0, duration=None, zoom=None) and clear_focus(). snap() is there for door transitions.
        > Zoom: camera.zoom_mult (a little wider at speed / dash, focus can tighten) multiplies target_zoom; controls._zoom_goal() quantises the goal to 0.02 so the zoom-keyed sprite caches do not thrash. Manual zoom keys still work and the zoom_min/zoom_max clamps still apply.
    # Settings
        > Settings.CAMERA_MODE ("smooth" | "classic") and Settings.SCREEN_SHAKE (bool); both are toggle buttons in game settings. The existing shake system (shake_frames/shake_intensity, combat_fx) is untouched and is applied on top of the camera rect; SCREEN_SHAKE just gates apply_shake.
    # Not done yet in WS-F (left for later passes)
        > directional shake, combat-awareness bias toward threats, kill zoom punch, spectate/death drift (Windows.spectate has its own offset code), level-start intro pan, parallax check. Door whip-pan comes with WS-G.

## Monday 26 October - WS-B (Befriend Charms + bought dashes)
    # New files
        > data/charms.py (every tunable: 10 s base time, 0.15 slow-mo, penalties, leash, quick-buy x1.5, starter 3 dashes, caps), scripts/charm_mode.py (rules), ui/charm_ui.py (drawing).
    # Charm mode (story only: not MULTIPLAYER, level_folder == STORY, not EDIT_WORLD; TODO(multiplayer) - disabled online)
        > Keys: C = WASD player, B = arrow-keys player (Settings.CHARM_KEYS), pad button 4 (Settings.CHARM_JOY_BUTTON), on-screen charm button (click / tap). KEYDOWN edge events, never polling.
        > press -> 0 charms opens the quick-buy popup (confirm_dialog, game frozen, shop price x1.5, wallet shown; declining costs no time) -> ACTIVE: 10 REAL seconds (+2 per Long Charm level), world slow-mo eased with smooth_to via game._charm_slow (game.dt = raw_dt * game_speed * charm_mode.time_scale), camera focuses the selected target (camera.focus, zoom 1.12), the aiming player's movement is frozen.
        > Candidates: every living non-friend non-ally enemy within acquire_range + Wide Charm. Bosses and stronger enemies ARE selectable; the reticle turns red and says TOO STRONG / BOSS - IMMUNE; the label shows "HP 120 / yours 180 - OK".
        > Selection: arrows (B player) / WASD (C player) / D-pad / stick jump to the next candidate in that direction (angle-bucketed, +-70 deg); tap or click selects, tap/click the selected one (or ENTER / SPACE / pad A) confirms; ESC / pad B / the X button cancels. A tap's echoed mouse click is swallowed (150 ms) so select + confirm can not fire together.
        > Health gate (try_charm): boss = charm lost + max(35% max HP, 150) damage; target HP > yours = charm lost + clamp(25% of the gap, 10%..30% of max HP); otherwise friend. Penalties bypass Iron Skin, never go below 1 HP (CHARM_BOSS_CAN_KILL = False), shake the screen, flash red, and show the banner.
        > Cancel: refunded when under 1 s elapsed (misclick), otherwise lost. Timer expiry: CHARM LOST banner + red vignette + shard burst. Target dies / leaves range: auto-advance to the nearest, or end with a refund if none are left. Player dies: cancelled, no refund.
    # Friends
        > ONE code path: charm_mode.befriend / unfriend / release_all (windows.entity_info now calls it too). Friends use the engine's team rule (same colour = ally) so decide_kill and every projectile hit-test already treat them as allies; original_color is stored and a pink heart bobs over each friend. Bond (Strong Bond shop item) = +15% damage and -15% damage taken per level.
        > Following: the friend's patrol centre (spawn_point) is moved to the player every frame, so the existing patrol() walks them back past 260 px; they teleport next to the player beyond 1200 px (or 520 px above/below while 600+ away). They fight enemies with their normal AI.
        > Limit: base 1 friend, +1 per Entourage level. At the limit the OLDEST friend is released with a toast (the charm is never refused after being spent).
        > Friends stay in game.enemy_list so every system keeps updating them; objectives now count hostile_count(game) = len(enemy_list) - game.friend_count so "clear all" / exit locks / boss / survival ignore allies.
        > No friends remain: release_everyone() before every level load, release_all() on death and in reset_run().
    # Dashes are a bought consumable (story only; free and unlimited elsewhere, enemies and friends never pay)
        > controls.try_dash(game, player) -> charm_mode.try_dash is the ONE place a dash is paid for; called from the keyboard, joystick (button 5) and touch DASH button. Out of dashes = quick-buy popup (one dash at the premium price, bought then performed). Dash Master gives a chance a dash costs nothing. Starter stock: 3 dashes; carry cap 5 (+2 per Dash Pouch level). HUD badge next to the charm button, pulses red at 0.
    # Shop (WS-B items; the full WS-C list is still to come)
        > gold: Befriend Charm (40, 55, 75, 100, 130; cap 9), Dash Charges (stack of 3: 10, 12, 15, 18, 22; cap 5). New shop kind "charm": price rises with purchases this run, FULL when at the cap, row shows OWNED n/cap.
        > ruby: Long Charm (+2 s x3), Strong Bond (x3), Dash Master (x3). emerald: Wide Charm (+250 px x3), Dash Pouch (x3). pearl: Entourage (+1 friend x2). Icons added.
    # Other
        > The debug B arrow barrage is gone from B: it lives on F9 (Settings.DEBUG_ARROW_KEY) and only while Settings.DEBUGGING_MODE.
        > Counters for WS-D achievements: player.charms_used, dashes_used, quick_buys (no achievement hooks yet).
        > TODO(input): the gamepad button choice (4 charm, 0 confirm, 1 cancel, hat / stick select) and the touch layout are untested on real devices. Charm keys must be added to the Game Info controls page in WS-E.

## Monday 26 October - WS-C (shop expansion: items, 5 tabs, scrolling, readouts)
    # Shop UI
        > Tabs are now their own concept: data/shop_items.TABS = CONSUMABLES | UPGRADES | PERKS | RARE | ARSENAL. An item's optional "tab" field picks its tab (default: by currency); "currency" only sets the price. items_for_tab(); items_for(currency) kept. shop_screen no longer assumes tab index == currency (the wallet chips still show the four coins).
        > Rows scroll (mouse wheel, arrow keys follow the selection, eased) when a tab has more rows than fit; mouse hits ignore rows scrolled out of the panel.
        > Each row can show "Arrows per volley 3 > 4" (item "readout" field, rules.readout()), right-aligned on the name line, hidden at max level.
    # New items (all level items unless noted; prices are starting points)
        > ARSENAL: Bigger Quiver (+1 arrow, x5), Ember Stock (+1 fire, x5), Bomb Bag (+1 bomb, x5), Wide Blast (+10 px bomb reach, x3), Bomb Belt (+2 live bombs, x3), Quick Hands (-8% reload, x4), Piercing Tips (+1 enemy an arrow passes through, x3), Hot Coals (fire +1 s and +15% damage, x3), Homing Arrows (pearl, once).
        > UTILITY: Shield Bubble (gold, boost: swallows 3 hits next floor), Thorns (ruby x3: reflect 15% of melee), Lucky Clover (emerald x3: +10% coins from fallen enemies), Treasure Radar (emerald x3, needs the Minimap: L1 shows treasure, L2 arrows to the 3 nearest far ones, L3 pings close ones), Second Wind (pearl x2: a free half-health revive per level bought, before the defeat screen, not counted as a pearl revive), Cloud Step (pearl: +1 air jump).
    # Where each effect lives
        > Players only (enemies and friends never get shop bonuses): ACTIVITY.ammo_count / bomb_cap / reload_mult / can_jump in entities/mind.py; reload uses attack_delay * reload_mult() at the 4 call sites; the 3 jump checks in controls.py call player.can_jump().
        > Bomb.reset: _reach (Wide Blast) widens the hit box; Arrow.reset: pierce_left / pierced set / homing; Arrow._steer turns current_speed + y_vel toward the nearest enemy ahead (3 rad/s, gravity cancelled); Fire.reset: lifespan + heat (Hot Coals).
        > mind.hit(): Shield Bubble (shield_left, combat_fx.on_shield) and Thorns (melee only: not fire / lava / arrows / bombs).
        > entity_utils death drop: value + shop_effects.drop_bonus (Lucky Clover). death_rules.second_wind() runs before open_defeat. snapshot/restore now include charms, dashes, bought and second_winds_used so a floor restart gives back what you entered with.
    # Not done (left for a later pass)
        > Sticky Bombs (bombs currently explode on first contact, so "stick" needs a delayed-detonation design), Rally Horn, Door Key, Scout Flare (they need a use-key / HUD slot first) and the cosmetics (aura colour, trails, name plates, coin colours). Dash Master is a free-dash chance (WS-B) rather than -15% cooldown: dashes have no cooldown in this engine.
    # Tests
        > tests/test_charms.py and tests/test_shop_items.py: headless logic tests (stubbed pygame / UI) for the charm rules, shop purchases, caps, readouts, no-stacking, ammo / reload / jump rules. Run from the repo root.

## Monday 26 October - WS-D (achievements window + richer achievements)
    # Data (data/achievements.py)
        > Every entry now has category (Combat / Survival / Wealth / Allies / Exploration / Secrets), tier (bronze / silver / gold / pearl, TIER_COLORS), icon (a ui/shop_icons.py glyph) and optional hidden / counter + goal. 11 original feats kept (ids unchanged, so old saves still match) and 12 added: Sharpshooter, Pyromaniac, Demolition Crew, Arsenal, Big Spender, Unlucky Friend (first_friend), Entourage, Explorer, Deep Diver, Gambler, Last Second, Window Shopper. Pearl rewards stay rare.
    # Tracker (scripts/achievements.py)
        > Persisted counters (kills, fire_kills, bomb_kills, revives, revives_run, coins_spent, best_arrow_streak, friends_peak, door_kinds, shop_empty_streak) + unlocked_at timestamps + a "seen" list, all in achievements.json. Old saves load (kills carry over, nothing shows NEW). Counter feats unlock themselves when their goal is reached.
        > New API: progress(id) -> (current, goal), state(id), all_entries() (window-ready dicts), mark_seen(). New hooks: on_kill(player, kind) (fire / bomb kills), on_arrow(hit), on_spend, on_max_ammo_upgrade, on_friends, on_charm_gamble, on_charm_confirm, on_door, on_shop_visit, on_run_reset, plus the existing on_revive / on_level_complete (now also Deep Diver = clear floor 5 in the story).
        > Hook sites: mind.hit (kill kind), Arrow.attack / stick (hit vs miss), Door teleports + exit, shop_effects.buy / reset_run, charm_mode (friends, boss gamble, confirm timing, quick-buy spend), shop_screen (empty-visit streak).
        > Toasts: tier-coloured, drop in, and run on REAL time (game.real_dt) so a toast earned during slow-mo no longer crawls.
    # The window (ui/achievements_screen.py, open_achievements(game))
        > Opened from a new ACHIEVEMENTS button on the start menu (7th) and the pause menu (5th).
        > Completion ring + "X of Y", filter chips (ALL / UNLOCKED / IN PROGRESS / LOCKED), category tabs with per-tab counts, sort (NEWEST / CATEGORY / CLOSEST), scrolling cards with tier medal, progress bar ("63 / 100"), reward coins, CLAIMED stamp + date, NEW tag until viewed, "???" for hidden feats, a confetti burst when opened at 100%.
        > Cards are rendered once and cached (id, state, progress, size); only visible cards are drawn; selection glow, bar shimmer, medal shine and the NEW pulse are small per-frame draws on top.
        > Input: mouse (click, wheel, drag with inertia), keyboard (UP/DOWN/PGUP/PGDN/HOME/END, LEFT/RIGHT filter, [ ] or TAB category, S sort, ESC back), gamepad (hat/stick, B back, X sort, L1/R1 category). Touch uses the mouse events SDL synthesises.
    # Tests
        > tests/test_achievements.py (39 checks): data sanity, every new feat, once-only rewards, persistence round trip + old-save migration, hidden / NEW logic, and the window's filter / sort / completion functions.

## Monday 26 October - WS-E (Mode / Game Info / Author Info / Entity Info on one kit)
    # Shared kit: ui/window_kit.py
        > KitWindow owns the loop (own while + display.flip, like the old windows): live menu background dimmed + drifting embers, an animated frame (a light travelling round the border, wave-text title, close button), open / close scale + fade, and ONE input mapping -> Action.LEFT/RIGHT/UP/DOWN/CONFIRM/BACK/PREV/NEXT/CLICK/SCROLL/DRAG for keyboard (arrows or WASD, Enter/Space, Esc, Tab, [ ]), gamepad (hat, stick with repeat, A confirm, B back, L1/R1 tabs) and mouse / touch (SDL mouse events). Every navigation step plays menu._ui_tick.
        > Widgets: pill (hover glow), draw_card (eased lift + glow), stat_bar, key_glyph / pad_glyph (key caps and round pad buttons), tag, sprite_frames (the real character sprites recoloured with the game's own palette swap), cached text (txt / wrap / fit) and a cached panel() so nothing allocates a surface per frame. Only ui_theme.font is used (no SysFont).
    # Windows (ui/info_windows.py; Windows.modes / game_info / author_info / links_info / entity_info now just open them, the old private loops are gone)
        > MODE: a card carousel (Solo / Host / Join) with a live scene made of real character sprites, a short description, and yes/no feature rows (story, shop + charms, achievements, needs a network). Same flags as before (MULTIPLAYER, SERVER, CONNECTION_TYPE). The old window only switched Solo/Multiplayer and Host/Join, so the carousel presents those; the hero type / colour picker belongs to the in-game player editor and was not touched.
        > GAME INFO: six tabbed pages (How to play, Controls, Characters, Shop & coins, Charms & allies, Tips), rendered once per tab and scrolled (wheel, drag, arrows). Everything numeric is generated: version from settings.VERSION (the VERSION file that extras/bump_version.py writes), the Controls page from data/controls.py (charm keys come from Settings.CHARM_KEYS / CHARM_JOY_BUTTON, drawn as key caps and pad buttons), the Charms page from data/charms.py, the Shop page from data/shop_items.py, the Characters page with live animated sprites.
        > AUTHOR INFO: hero card (icon, animated name, version tag), link pills with hover glow (Enter / click opens the browser), and a looping credits roll parsed from docs/CREDITS.md (emoji stripped so the font can draw it; wheel / drag pauses it for 3 s).
        > ENTITY INFO: portrait with the real sprite in the entity's colour, stat bars (health, attack, speed, reach), kills, friends, ids, and a BEFRIEND / UNFRIEND button on the shared charm_mode code path. Outside the story it is free; in the story it says to use a charm in the game (the story rule: charms are the only way). The black-on-gradient text is replaced by cream on a dark panel.
    # Data
        > data/controls.py (the key table), data/info_pages.py (all page text, character table, mode cards, author links). Edit wording and bindings there.
    # Tests
        > tests/test_windows_data.py: the controls table follows Settings, page text formats from real data, the characters / coins / modes match the game, the credits parser on the real CREDITS.md, no SysFont and no private loops left in the four windows.

## Monday 26 October - WS-G (door effects)
    # New ui/door_fx.py (Door keeps all gameplay logic; this is the look)
        > Door.draw is now draw_back (glow / rays / ripples) -> the sprite -> draw_front (motes / runes / lock). Only visible doors are drawn (draw_funcs culls), and each door's animation advances inside draw, so off-screen doors cost nothing. Budgets: <= 16 particles per door, <= 24 world events; glow / ring / ray sprites are cached (ray widths in 4 px buckets). Off in the level editor. Real time (pygame ticks), never the slow-mo dt.
        > TELEPORT (violet): motes spiral inward, two pulsing ripples that speed up as you get close (proximity = 120 px, eased). Enter: a ghost of the traveller squashes toward the door while a ring collapses, violet screen flash. Arrive: pop ring + white inner ring + glow + sparkle burst.
        > WARP (cyan): a rotating rune ring (ticks) that spins faster and brighter when near, little sparks arcing up, and when near a dotted marching arrow toward each of its first 3 targets. Enter: a cyan streak runs along the path; arrive: ripple + burst + the camera WHIPS to the destination (Camera.whip, a fast eased pan; teleports snap with a flash instead).
        > EXIT (green): LOCKED = dim red glow, a pulsing red padlock, slow ember drip. OPEN = warm green glow, four god-rays (brighter / wider near), rising leaves of light. Unlock moment: a one-time double-ring burst, the screen brightens, every local camera focuses on the door for 1.5 s (the objective already shows the "EXIT IS OPEN" banner, so none is added). Enter: the door flares, rays converge, the whole screen brightens, and the level ends ~350 ms later (progression.level_won is now called by door_fx after the flare; the cleared card then starts from the flare because it snapshots the last frame). A second player on the same door cannot restart it.
        > Biome: each kind's portal colour is nudged 20% toward the brightest colour of the door's biome frame (data/palletes/doors.frame_swaps), so the kinds stay distinguishable in every biome.
        > Non-player travellers (enemies, bombs, arrows) get a smaller, cheaper version (no sparkles).
    # Other files touched
        > ui/lighting.py: door lights read door.light_preset (colour per kind; red when locked, green when open) instead of one fixed colour. scripts/camera.py: whip(). game.py: door_fx.draw_world(...) next to the charm layer. objects/objects.py: Door.draw / hooks only.
    # Not done
        > Subtle coin pull toward an open exit, a distinct warp sound (there is no extra sound asset and playit has no pitch shift, so warp reuses "teleport"), and a true sprite ghost for the suction (an outlined squashing ellipse of the traveller's size is used instead).
    # Tests
        > tests/test_doors_camera.py: colours per kind, unlock fires once, exit hand-off delay + no double-trigger, event caps and ageing (a frame hitch ages an effect by at most 50 ms), bounded particles per kind, no work in the editor, proximity easing, and the camera whip (first frame still near the door, sweeps and lands, versus a hard snap without it).

## Wednesday 29 October - clean base dir, one VERSION file, music director, landscape only, the shell
    # One path anchor (game/scripts/paths.py) instead of a BASE hack in every file
        > paths.BASE_DIR is the project folder (the one holding assets/, levels/, VERSION and game/). paths.asset("terrain", "Terrain2.png") builds an absolute path under assets/ and lower-cases the FOLDER parts (Linux is case sensitive), keeping the file name's case; paths.LEVELS_ROOT and paths.DOCS_DIR are absolute too. paths.enter_base_dir() is the ONE os.chdir in the game (called once by settings.py, for the few relative strings left). assets.py, file_loaders.py, main.py, level_editor.py, level_select.py, level_meta.py, windows.py, ui_theme.py, info_windows.py and settings.py no longer compute a BASE or chdir.
        > save_dir() on desktop is BASE_DIR (same place as before, so existing achievements.json / progress files are found).
    # ONE version: the VERSION file
        > VERSION (project root, "39.0.0") -> game/version.py (VERSION, VERSION_TAG, VERSION_TUPLE, NAME "Pixaby", TITLE "PIXEL ABYSS", WINDOW_TITLE). settings.py, the window title, Game Info, Author Info, pixaby.py, the level editor and the Android build (buildozer version.filename) all read it; there is no other version number in the code. extras/bump_version.py (patch / minor / major / exact) writes VERSION and keeps game.json in step. game.json now says id pixaby, entry pixaby.py.
    # Music director (the theme songs in assets/sounds/themes)
        > data/music.py: the tables (biome -> song file, objective -> biome, scene -> biome, fades, confidence threshold). scripts/music.py: choose() (pure) + Music (cross-fade, one decoded song cached besides the playing one, volume follows the MUSIC slider live, a missing / undecodable song falls back to the title song with one printed line). sounds.py lost its inline theme code; game.py calls music.scene("menu") at start and music.play_level(self) after every level load.
        > A level's song, first rule that applies: (1) metadata "theme" (biome id or file stem), (2) metadata "biome", (3) the blocks, when conclusive (a non-stone biome leads, or plain stone is >= 75% of biome blocks), (4) the level's TYPE: its tags (Ruins -> Dune Ruins, Maze -> Mossy Grove ...) then its objective (boss / final -> Void Choir), (5) the blocks anyway, else Abyss Stone. Story levels now: 1 Abyss Stone, 2 Rust Hollow, 3 Dune Ruins (was Abyss Stone), 4 Ember Forge, 5 Abyss Stone, 6 Frostbite, 7 Abyss Stone, 8 Frostbite, 9 Mossy Grove (was Abyss Stone), 10 Harvest Dusk. Only the music is chosen this way; the visual biome is unchanged.
        > The MUSIC slider (Settings.BG_SOUNDS_VOLUME) still starts at 0, as in your tree: raise it in Game Settings -> Volume to hear the songs.
    # Landscape only
        > Settings.WIDTH / HEIGHT are always (wide side, short side); the orientation attribute, both fix_orientation() methods (and their ~15 calls) and every VIDEORESIZE / WINDOWDISPLAYCHANGED / WINDOWSIZECHANGED branch are gone, including the six try/except blocks that were breaking the event chains (one of them made windows.py fail to compile). Nothing reacts to rotation or resize any more.
    # Entry points
        > pixaby.py and launch_level_editor.py are tidy and each has main(screen=None) for the shell. Z_launch_game.sh / Z_launch_editor.sh are real bash scripts now (they were Windows batch text) and work from any folder. extras/steps_to_package.py compiles (its docstring is raw).
    # Kept as found in your tree (test / performance values, not changed): data/charms.py (friend limit 111, 1111 starting dashes and charms, caps 1111), entity_utils.py (11110 of every coin), settings.py (FPS 30, LIGHTING / SHADOWS / FIREFLIES off, DEBUGGING_MODE off). Put the shipped values back before a release.
    # Tests (tests/, run from the repo root)
        > test_clean_setup.py (paths, version, bump_version, landscape, entry points, everything compiles), test_music.py (rule order, the real story levels, transport with a fake mixer, fallbacks); the older suites were adapted (charm tuning pinned, asset paths via paths.asset()).

## Sunday 8 November - Android removed, desktop only (Windows / Linux)
    # Android-specific code gone
        > paths.is_android() and the app-private save folder are removed: progress.json, achievements.json and levels/user_worlds always live in the project folder (paths.save_dir() is BASE_DIR; save_file() / folder_dir() keep their signatures). pixaby.py and launch_level_editor.py: main() no longer takes the shell\x27s screen argument. game.json lost the shell-only keys (touch_profile, orientation). Comments and docs no longer mention buildozer / the Android build.
    # Touch kept, and fixed
        > Touch used to be switched on by sys.platform == "linux", so a Linux desktop auto-joined as a touch player. It now follows the hardware: game/scripts/touch.py joins player 1 with the on-screen sticks only when SDL reports a touch device. Settings.TOUCH_CONTROLS = "auto" | "on" | "off", or set the PIXABY_TOUCH environment variable. The AUTO_SHOOT buttons follow the same switch (game.touch_enabled).
    # Renamed
        > level_select.py: the "mobile" layout flag is now "compact" (it is just the small-window layout, still used on small desktop windows).

## Sunday 8 November (2) - screen modes, story levels read-only
    # Three screen modes (Game Settings, bottom row)
        > FULLSCREEN, 800 x 600 and 1280 x 960 (scripts/screen_mode.py). The choice is remembered in display.json next to the game; the first run opens full screen. A window that does not fit the desktop (1280 x 960 on a 1366 x 768 laptop) is hidden, and a remembered mode that no longer fits falls back to full screen. Switching rewrites Settings.WIDTH / HEIGHT / window / window_rect and re-lays-out the viewports, the touch sticks, the menu backdrop and the start-screen title. RPGButton now follows the surface size (a menu built before a switch re-fits itself) and shrinks a label that would spill out of its button (needed at 800 x 600).
        > settings.py no longer opens a desktop-sized window; it opens the remembered mode.
    # Story levels are read-only unless Settings.DEBUGGING_MODE is on
        > editor_launch.story_editing_locked(folder) is checked in Level_Editor.edit_world (the one entry used by the in-game WORLD EDITOR button, the selector pencil and the standalone editor) and again in the editor save. The in-game WORLD EDITOR button is hidden on a story level. My Worlds and the co-op levels are not affected.

## Split Screen mode + Graphics settings
- **Mode -> SPLIT SCREEN** (new card, `data/info_pages.py`, `ui/info_windows.py`): local co-op on one machine. `Game.SPLIT_SCREEN` is set by the Mode window (Solo / Host / Join clear it). In this mode co-op worlds (`levels/multiplayer`) no longer switch the network client on (`windows.py`), so they play locally. `Level_Loader.max_local_players()` caps a co-op world at its own max players and `min_local_players()` keeps the join screen open until enough have joined; the join screen shows "N / min joined". The story stays a solo run.
- **Game Settings -> GRAPHICS** (`ui/graphics_window.py`): the screen modes moved here as cards with a monitor preview (active / too big tags), plus LIGHTING, SHADOWS and FIREFLIES switches with live previews. The switches are remembered in `graphics.json` (`scripts/graphics_prefs.py`, read by `settings.py`), next to `display.json`.

## Co-op loot: power-ups, hero milestones, Charm Crystals
Local co-op worlds (`levels/multiplayer`, Split Screen) have no shop, so loot comes from the world (all numbers in `data/coop_items.py`, rules in `scripts/coop_loot.py`):
- **Power-ups drop and lie around.** Fallen enemies sometimes drop a generic power-up (heal, vitality, might, swiftness, springs, magnet, lifesteal, shield bubble, war drum, iron skin ...) and a few more are scattered in random places when the level loads. They are `objects.Pickup` objects in `treasure_list` (glowing orb with the shop's own icon). A pick-up is applied like a shop purchase (`player.upgrades` / `boosts` + `apply_loadout`). Someone who could not use it (full HP, item maxed) does not take it: it stays for a teammate.
- **Hero upgrades are earned.** Arrows (Archer), fire (Torch), bombs (TNT), thorns / fang / heart (Warrior, Pawn) and `homing_arrows`, `quick_hands` come from kill milestones per hero (`MILESTONES`), with a "<HERO> MASTERY" banner. Never dropped.
- **Dashes are free forever** in co-op (`charm_mode.dash_rules_apply` is story-only; the HUD shows DASH FREE).
- **Charm Crystals** (Befriend Charm) exist only where you place them: Level Editor -> Treasure category -> `charm`. Charms start at 0 in co-op; with none, the charm key says "NO CHARMS - FIND A CHARM CRYSTAL" (no quick-buy popup). Charm mode now works in co-op worlds (`charm_mode.coop`).
- Local only: over the network (Host / Join) the extras are off and a placed crystal is skipped, because the network sync only knows coins.


## Editor debug-only, mode-locked tabs, map previews, maxed power-ups

- **Level editor only with `DEBUGGING_MODE`.** No WORLD EDITOR button, no pencil / NEW + in the level selector, and `Level_Editor.edit_world`, `save` and the standalone launcher refuse to run while the flag is off (`editor_launch.editor_available()`).
- **Maxed power-ups.** The Coin Magnet only pulls a power-up toward a player who can use it, so a maxed / full-health player no longer drags it along. Touching one you cannot use leaves it in place and shows a banner (item name + MAXED OUT / HEALTH IS FULL / CHARMS ARE FULL / ALREADY ACTIVE), at most every 2.5 s (`coop_loot.explain_unusable`, `data/coop_items.UNUSABLE_*`).
- **Mode-locked tabs** (`sources.play_mode`, `Source.mode_lock`). Solo story mode: CO-OP, MY WORLDS and COMMUNITY are locked ("Only open in split screen and online modes"). Split screen / online: STORY is locked, the rest open. The standalone editor is exempt, and with debug on the pencil still edits a locked tab.
- **Map previews.** A level may hold `{"type": "preview coordinates", "x": 0, "y": 0}` (the world point the preview is centred on). The selector draws the map around it (`level/preview.py`); no entry shows NO MAP PREVIEW. In the editor press **V** to set or remove it (`editor/preview_tools.py`). Shipped story, co-op and My Worlds levels are seeded at their start point.

## Real-sprite map previews on a light background, selector opens on CO-OP
- **Previews show the real thing.** `level/preview.py` no longer draws coloured dots for trees, decoration, doors, traps, gems, enemies and spawn points: it uses the game's own sprites (tree / deco biome palettes, door kinds, trap `on` frame, gem sheets, enemy idle frame with the colour swap, a spawn point shows its first entity faded), trimmed to their pixels and standing on the bottom-centre of their cell. Sprites are only looked up from `Assets` / `scripts.cache`, never loaded from disk here.
- **Whitish background** (paper white instead of the dark purple), lighter back-block tint, a thin light frame instead of the dark vignette.
- **CO-OP tab on entry.** In split screen and online play the level selector opens on the CO-OP tab (`LevelSelector.__init__`, using `sources.play_mode`). Solo and the standalone editor still start on tab 0.

## Wednesday 25 November - Entity Editor, shop effects on entities, Homing Arrow Traps
Full reference: `ENTITY_EDITOR.md`.
    # Entity Editor (level editor, MODIFY an enemy)
        > New `ui/entity_editor.py` (window), `data/entity_mods.py` (every field, category, boss kit and grantable shop item as data), `entities/mods.py` (what an enemy does with them). Clicking an enemy in MODIFY mode now opens it instead of the generic popup; a Homing Arrow Trap opens a smaller window (`edit_trap`).
        > Tweaks are grouped: Placement, Health, Combat, Arrows & Ammo, Movement & Dash, Homing Traps, Boss - plus the shop items it can be granted (Upgrades, Perks, Rare, Arsenal, Boosts) with level pips. Badges show how many values differ from the default; a dot resets a row; sliders, steppers, typed values, keyboard and wheel all work.
        > Saved sparsely under `"mods"` on the enemy entry (`fx` = raw shop effects, `items` = shop item levels). `object_edit.apply_entity` writes it; `level_loader` and `object_edit._construct` call `mods.apply` after the enemy is built.
        > Boss: `boss`, `boss_title`, health / damage multipliers and a "Fill in kit" button per enemy type (`entity_mods.BOSS_KITS`; the Archer kit = homing + extra arrows + pierce, evade dash, homing traps, regen, rage). The Boss objective prefers an enemy marked as boss (its own multipliers replace the objective's unless the level sets them), the boss bar shows the title, and the title is drawn over the boss's head.
    # Shop effects are no longer player-only
        > `mind.py`: ammo_count, reload, extra jumps, bomb cap, shield bubble and thorns read `shop_stats` for any entity. `objects.py`: Arrow.reset (pierce / homing), Bomb blast radius and Fire hot coals work for any owner; homing arrows fired by an enemy now steer to players.
        > `shop_effects.total_effects` adds `player.extra_effects` (raw effects from the editor), so `apply_loadout` gives an enemy exactly what the shop gives a player. New effect keys `trap_arrows`, `trap_time`.
        > Enemy-only extras from the editor (`entities/mods.py`): regeneration, rage, burn-over-time (arrow burn), Second Wind, crits (`combat_fx.bonus_damage` accepts an enemy with `crit_chance`), and a dash with its own AI (chase / evade / both, optional dodge i-frames via `combat_fx.dodged`).
    # Arrow properties
        > `arrow_trap.arrow_profile(entity)`: damage (attack power x arrow damage), knockback, pierce, homing, burn, speed, extra arrows. Entity arrows (`Arrow.reset`) and the traps the entity drops both derive from it. New per-entity fields: arrow damage / speed / knockback multipliers and arrow burn.
    # Homing Arrow Traps
        > New `objects/arrow_trap.py`: arrows steered toward a coordinate with a limited turn rate never arrive, so they keep revolving there and hurt whatever hostile passes (never the owner's colour). `WOBBLE` makes them sweep a flower, not a ring.
        > Level editor: Traps category, type `homing` (`TRAP_NAMES`, `editor_tools.add_homing_trap`, loader builds `ArrowTrap`). No owner: damage, knockback, burn, pierce, hit gap, arrows, radius, speed, who it hurts and lifetime are set by hand in MODIFY (`TRAP_FIELDS`); the last values are remembered for the next one placed.
        > Players: shop item `homing_trap` (Arsenal, ruby, stock in `player.traps`, cap 5) + `trap_mastery` (+1 arrow, +4 s per level). Drop with `Settings.TRAP_KEYS` (V arrow-keys player, E WASD player) or pad button `TRAP_JOY_BUTTON` = 3 (`arrow_trap.on_key / on_joy`, hooked in `game.py`).
        > Enemies: only those with "Drops homing traps" (modes ahead / target / ward / mixed, max out, cooldown, range). Owned traps credit kills to the owner (`credit_owner` in `Entity.hit`).
        > Not synced over the network: `server.py` skips `homing` traps.
    # Docs
        > Added `ENTITY_EDITOR.md`; updated README, PROJECT_STRUCTURE, DISCOVERIES. In code: the editor help panel (`EDITOR_HELP_SECTIONS`), and the headers of `shop_items.py`, `object_edit.py`, `data/traps.py`, `mind.py`.
    # Fix: projectiles crossing over between levels
        > `game.bombs.list` (every flying arrow / bomb / fire) is created once and `create_new_world` never emptied it, so homing arrows from the previous level kept flying in the next. `level_loader._clear_projectiles()` now returns them to their pools on every world (re)load.
    # Burning: a `Burn` class, drawn with the game's own fire sprites
        > New `entities/burn.py`. `Burn.apply(target, seconds, dps, by)` is what a burning arrow / homing trap arrow does on hit (the stronger / longer burn wins, kill credit goes to `by`); `Burn.touch(target)` is lava / fire contact (flames only - the hazard deals its own damage); `Burn.tick` does the damage over time from `mods.tick`; state lives on `entity.burn`.
        > `Burn.draw` (called from `Entity.draw` after the sprite) animates `Assets.FIRE_SPRITES["on"]`, cropped to the opaque pixels and scaled per flame. `SLOTS` (5) flames per body, each living 0.45-0.9 s, then reappearing at a random spot on the body at a random size (deterministic hash per entity, so no per-frame random calls); they flare up and die down; scaled images are cached on 4 px steps. If the sheet is missing it falls back to drawn flames.
        > Replaces the loose `_burn_left / _burn_dps / _burn_by` attributes in `objects.py`, `arrow_trap.py` and `entities/mods.py`.
    # Deco and trees burn too
        > `Burn.ignite_object(obj, by)` (entities/burn.py) sets scenery alight: deco (`FLAMMABLE`) burns for `BURN_TIME` (6 s) at 10 damage per second, so it burns away; trees burn (flames) but survive. Lit by fire patches, burning arrows (player, enemy and the entity's own), and lava.
        > Fire spreads: every 0.4 s a burning deco / tree / entity lights flammable scenery within `SPREAD_RADIUS` (70 px) with `SPREAD_CHANCE` (35%) each. Burning scenery ticks in `Deco` / `Tree.update_sprite`, flames are drawn from `Object.draw`. Destroying scenery gives no kill credit.


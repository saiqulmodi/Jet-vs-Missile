# Jet vs Missile

Python 3.12 + pygame-ce 2.5.8 arcade shooter, everything in `main.py`. Started 2026-10-02.

## Rules from the user (keep them)

- **One game, one name: "Jet vs Missile".** No other game or character names anywhere (text, drawings,
  code names, docs). The user's older game lives in its own separate repo and folder; never edit it from here.
- **Do only what is asked.** Don't add extras (banners, effects, renames) on your own; propose them first.
  Never remove an existing feature without asking.
- **No dance/celebration screens.** The milestone bonus (+HP, med-kit, decoy every 5th win) is given at the short round break.
- **Sound only on actions** (shots, hits, explosions). No music or decorative sounds.
- **Difficulty steps every 5 levels** (`level_step`): `level_power` (damage, both sides), `missile_pace`
  (missile and shot speed, x0.55 at level 1), `jet_pace` (x0.75 at level 1). Level 1 must feel slow.
- **The jet always flies.** Hands off the keys, `autopilot_velocity` flies cruise/climb/dive/loop/roll and
  dogfight break turns; the sprite points along the flight path and banks/rolls.
- **Launchers** (`launcher_count`: 1 at levels 1-10, +1 every 10 levels; one stretch of ground each) are destroyed by their 2nd hit (boss silo too; user, 2026-10-03), rebuilt every wave.
- **Missiles never fire** (user, 2026-10-02: "either it hit or destroy itself near to target"). Their only
  attack is the proximity fuse (`FUSE_RADIUS` 60, boss x1.4): within range the missile blows itself up and the
  jet crashes (`p1_hp = 0`); a held shield absorbs the blast. The onboard-ammunition system and the
  "Bullet Hell Surge" mutator were removed for this. (The duel's old flying P2 missile is gone: the duel is now jet vs launcher, see below.)
- After a crash, the next round's jet starts with full HP.
- **Ground crash** (user, 2026-10-03: "let jet crashes when it hit the ground"): no floor bounce any more; when the
  jet's centre comes within `JET_GROUND_CLEARANCE` (12 px) of the ground line (`jet_hits_ground`) it crashes
  (`p1_hp = 0`, shield doesn't help), campaign and duel. The top edge is open (sky escape, below); the autopilot pulls up near the ground.
- **Stealth key V** (user, 2026-10-02): 2 s (`STEALTH_DURATION`) invisible to missiles and launchers: missiles fly
  to the last seen spot, the proximity fuse ignores the jet (also P2 in the duel), missiles on launchers and
  RELOAD launches wait; 8 s recharge from activation. Separate from camouflage C (4 s fade, fuses still work).
- The user tests gameplay themselves: say what changed, let them play it, commit when they say so.

- **Phone version** (user, 2026-10-02): touch controls in `main.py` (`MOBILE = detect_mobile()`, `touch` dict,
  `finger_down/motion/up`, `draw_touch_controls`): thumb stick on the left half, FIRE (auto-aim via
  `touch_aim_target`) and SHIELD held, STEALTH/CAMO/FLARES/SQUAD/HEAL post the same keys as the keyboard,
  card taps, level-strip taps, MENU = Esc. Touch-made mouse events are ignored (`event.touch`). The canvas is
  fitted to the browser window (`fit_canvas_to_browser`, 4:3). Test on desktop with `JVM_MOBILE=1`.
- **Game controller**: d-pad (hat on desktop, buttons 12-15 in browsers) up = stealth, down = camouflage,
  left/right = previous/next level; any controller input hides the touch buttons.
- **Jet size** (user, 2026-10-02): small (`JET_BASE_SCALE` 0.62) and smaller the higher it flies
  (`jet_size_factor`, 0.6x at the top); `jet_fuse_radius` follows the drawn size (60 px low, ~42 px high).

- **Guns fire forward only** (user, 2026-10-02: "no fire toward back"): shots and lasers leave the nose, aim clamped
  to `FIRE_CONE` (30 deg) around the flight direction; phone auto-aim only picks targets inside the cone.
- **F = 10 flares** (user, 2026-10-02, replaces the 8 mirage jets; x1.15 = 12 vs the AI): `FLARE_COUNT` flares fan out behind the jet,
  slow and sink for `FLARE_LIFE` (4 s). Every missile chases its nearest flare (`e.decoyed`, its fuse then ignores
  the jet) and blows up within `FLARE_CATCH` of it, no points.

- **Missiles only come from launchers** (user, 2026-10-02): the old radar-cloak (missile vanishes at a purple
  hole and reappears at another) is removed (the duel's burrow holes went with the old P2 missile). Test: `test_missiles_never_vanish_or_teleport`.

- **One hit destroys a missile** (user, 2026-10-03), bosses included: a jet bullet or the laser touching it
  sets `e.hp = 0`. Only an active ECM pulse stops the hit (bullets bounce, the laser is jammed). Launchers
  need 2 hits (the armoured duel launcher: `p2_max_hp` 12).

- **Missile flight** (user, 2026-10-03): turn rate `MISSILE_TURN_DEG_PER_S` = 30 deg/s for every class
  (edge bounces excepted); after `MISSILE_FLIGHT_FRAMES` (20 s) a missile `expired`: no tracking, no fuse,
  engine off, it noses over and falls; on the ground it explodes (no points) and its launcher (or another free
  one) launches the next missile. Tests: `test_missile_turns_at_most_30_degrees_per_second`,
  `test_missile_gives_up_after_20_seconds_and_falls`.

- **Projectile flight** (user, 2026-10-03: "projectile movement, not like jet all aerobatic; fall far away from
  the launching pad"): no edge bounces, no weave, no ballistic speed surge, JINK and SPRINT removed from
  `AI_TACTICS`. A missile leaves the rail aimed at the target (>= `LAUNCH_MIN_ELEV` 15 deg), flies at steady speed,
  and when its 20 s end or it flies out past a side/the top, the motor cuts (`expired`) and it falls as a projectile
  (keeps forward speed, `MISSILE_GRAVITY`, terminal 10 px/frame), landing away from the launcher. The game loop
  retires missiles that hit the ground or leave the sky and launches the next one from a free launcher.

- **Expansion spec** (user, 2026-10-03; built in pygame inside `main.py`, not Unity/Godot):
  - `ARSENAL` (JSON-safe table): 8 nations (RUS 5, IRN 10, CHN 15, UKR 20, PRK 25, USA 30, GBR 35, DEU 40), each with
    2 ground launchers (SAM = 1 missile, MBML = salvo via `salvo_size`) and 2 jet munitions. Every 5 levels one nation
    unlocks: its launchers join the enemy pool (`reset_launchers` gives each truck a system; name + nation shown under it,
    missiles draw a smoke trail in the system's own colour) and its munitions join `jet_loadout`.
  - Jet ordnance (1P only): G = next munition, R / right click = launch, touch WPN/MSL. Physics in `MUNITION_ROLES`:
    rockets use `motor_step` (thrust / falling mass, quadratic drag, vmax) and `guidance_turn` (proportional navigation,
    pursuit when > 60 deg off, turn capped = G limit); IR uses `ir_pick_target` (seeker cone); bombs fall with gravity +
    drag, PGM/GLIDE steer gently. Radar missiles are blinded by enemy ECM, IR is not. Ammo refills every wave.
  - Level 10: generic IR heat-seeker, FLIR pod (X / touch FLIR: active scan drains energy; passive sees hot silos close
    below, `flir_sees`), and underground `SiloLauncher`s (`silo_count`: 2/4/6/8/10 at 10/20/30/40/50+),
    HIDDEN -> SPOOLING -> FIRING -> EXPOSED; hidden ones can't be seen or hit until FLIR finds them or they fire;
    2 hits destroy; they hold fire during stealth. A wave is won only when the silos have no shots left too.
  - Controller (user, 2026-10-03): `PAD_ORD_BUTTON` 7 (the only free button: R2 in browsers, Start on desktop
    Xbox pads). Tap = launch (fires on release); hold + d-pad left/right = previous/next munition, hold + d-pad up =
    FLIR. Without it held the d-pad keeps its old jobs.
  - `HUMAN_VS_AI_BUFF` 1.15 vs the computer (all aspects, see below); a human-vs-human duel stays 0%.
  - Missile rules above are unchanged (30 deg/s, 20 s, never fire, one hit kills). Silo missiles that hit the ground
    give their silo its shot back instead of launching from a truck.
- **Drones** (user, 2026-10-03; campaign, and from the duel launcher): `drone_level` 1..20 (= game level, capped at 20;
  drones per launcher `drones_per_launcher` 1-4), `drone_launcher_count` 1 at levels 1-10, +1 every 10 levels. Each
  `DroneLauncher` drives in its stretch, sends its drones one by one and from level 5 also carries 1 missile (`e.silo = dl`, given back if it falls).
  `Drone` speed = half the jet's top speed (`DRONE_SPEED_FACTOR`), 60 deg/s turns, 25 s fuel then glides down; on
  contact it costs HP (`DRONE_HIT_DMG` x level_power), shield blocks. Guns/laser/ordnance kill drones in one hit;
  drone launchers take 2 hits. Protective AUTO-GUN (`autogun_pick`): fires by itself, all round, with lead, at the
  nearest drone within `AUTOGUN_RANGE` 220 px (drones only, ring drawn while firing). A wave needs the drones done too.
- **Control modes** (user, 2026-10-03): start screen switches (click/tap, J / K, controller Square / Triangle on the
  start screen), saved in save.json (`load_control_modes`). JET AUTO (default) = autopilot when hands off + guns aim
  and fire by themselves at the nearest target in the cone (`touch_aim_target`); your own steering / firing overrides.
  JET MANUAL = no autopilot, no auto-fire (hands off it holds course). DUEL MISSILE MANUAL (default) = player 2;
  AUTO = computer flies P2 (homes with a weave, sidesteps ~60% of shots inside 160 px, burrows when shots are close).
- **Phones: always player vs AI** (user, 2026-10-03): with `MOBILE`, the duel missile is forced to AUTO and can't be
  switched; the card reads "DUEL vs AI".
- **+15% in all aspects vs the AI** (user, 2026-10-03): `human_buff(mode, missile_mode)` = 1.15 in the campaign and in
  a duel vs the AUTO missile (1.0 human vs human); `pbuff()` in the loop. It scales damage, gun / ordnance / auto-gun
  reload, bullet speed, jet speed, max HP, heal, med-kits, flares (12), squad charges and time, stealth and camo time
  (and their cooldowns shorter), shield drain/recharge, FLIR drain/recharge, auto-gun range, ordnance ammo. Drones stay
  at half the jet's un-boosted speed.
- **Names** (user, 2026-10-03: "keep all names duplicate adding m at the end so that no country can raise any issues";
  "includes jet also"): every weapon/launcher name in `ARSENAL` (and the generic IR seeker) ends in "-M" (R-77-M,
  PATRIOT PAC-3-M, ...). Never show a real system's exact name; new weapons, missiles, drones or jets get "-M" too.
  The jet has no real name (shown as "JET"). Test: `test_arsenal_has_2_launchers_and_2_munitions_per_nation_and_is_json`.
- **Improvements batch** (user, 2026-10-03: "do all 7"; "keep manual vs AI as simple as possible and more cognitive"):
  - Drone launchers carry their missile only from `DRONE_MISSILE_LEVEL` 5 (level 1 stays calm).
  - AI difficulty EASY / NORMAL (start-screen switch, H, controller L1 on the start screen; saved). `DIFFICULTY_FACTORS`:
    NORMAL = the tuned game (duel AI also leads the jet: aims where it will be); EASY = slower, wider-turning
    missiles, smaller fuse, slower/weaker/sparser drones, duel AI sees 25% of shots, no burrow, no lead.
    Never touches the player's stats. Applies to new missiles/waves (mid-wave switch = next wave).
  - Start screen: three switches (JET / DUEL MISSILE / AI) + one plain-words line saying what they mean right now.
  - Pause: Enter / Pause key, touch PAUSE (top centre), controller hold button 7 + d-pad down; any button / tap resumes;
    Esc still goes to the menu. While paused the loop only redraws the frozen frame.
  - First-time hints (`HINTS`, `hints_due`, `mark_hint_seen`): once ever, at level 5 (ordnance) and 10 (FLIR),
    worded for keys / touch / controller (`input_kind`). Saved in save.json `hints_seen`.
  - Continue: campaign card button "CONTINUE FROM LEVEL N" (best level reached), key 3, controller R1.
  - Phone speed: touch layer cached (`touch_cache`, redrawn only when its state changes), FLIR cone on a small
    surface, `create_jet_sprite` memoised (lru_cache; callers must only scale/rotate copies, never draw on it).
- **Full screen** (user, 2026-10-03: "it is not showing full screen display"): desktop starts `SCALED | FULLSCREEN`
  (`desktop_fullscreen_allowed`: not in the browser, not with the dummy driver, not with `JVM_WINDOWED=1`).
  User, 2026-10-03: "start it in full screen always": every start is full screen; only F11 switches to a window;
  Esc never leaves full screen; Alt+F4 closes (shown on the start screen). Browser: `docs/index.html` has a hand-added script before `</body>`
  (first finger tap -> requestFullscreen + landscape lock; mouse clicks ignored; iPhone Safari can't). When rebuilding
  with pygbag copy ONLY the .apk / .tar.gz into docs/, never pygbag's index.html (it would drop that script).
  `tools/make_stratos_box.py` copies docs/index.html into the Stratos box, so the script goes there too.
- **Wide screen** (user, 2026-10-03: "remove black bar to make it wider"): `pick_game_width()` sets the field width
  once at start from the screen shape (height always 600; 800..`MAX_W` 1334; phones use their long side; dummy
  driver = 800, `JVM_ASPECT` forces it). Layout was designed at `BASE_W` 800: centred screens shift by `XC`,
  right-hand touch buttons by `XR`; launch sites, burrow holes, P2 start spread over the width. New UI must use
  SCREEN_WIDTH / XC / XR, never a fixed 800-based x.
- **Phone link** (user, 2026-10-03): https://stratos-technologies-fzco.github.io/stratos-games-site/games/saiqulmodi/index.html?mobile
  (the box page itself, no site frame; `?mobile` forces touch mode). stratos.games does not serve it (404).
- **Launcher counts** (user, 2026-10-03: "make launcher 1,2,...10 for each 10 level up, similarly drone launcher
  also"): `launcher_count(level)` and `drone_launcher_count(level)` = 1 at levels 1-10, +1 every 10 levels, 10 from 91.
  The truck row is rebuilt every wave (`reset_launchers`, own stretch each); the boss silo is the middle one (`boss_site`).
  (Replaces the old fixed six launchers and the drone launchers' one-per-level count.)
- **Physics / ground** (user, 2026-10-03: "missile launchers are not in ground, it forgets rules of law of physics"):
  nothing launches from thin air. Duel tunnel holes are in the ground (P2 dives in and comes back up just above
  another hole, with a dust burst); hidden-silo missiles rise out of the hatch at ground level.
- **Phones never auto-fire** (user, 2026-10-03): JET AUTO's auto-aim/auto-fire is off with `MOBILE` / touch; there the
  jet fires only while FIRE is held (the drone auto-gun still works, it was asked for).
- **The user's older game** (squirrel vs viper) lives in its own repo `saiqulmodi/Stratos_squirrel_vs_viper`, live at
  https://saiqulmodi.github.io/Stratos_squirrel_vs_viper/. The Stratos site has ONE box per account (games/saiqulmodi/);
  a 2026-10-02 session replaced the squirrel game there with Jet vs Missile.
- **Duel = JET vs LAUNCHER** (user, 2026-10-03: "keep it simple man vs AI: jet will fly, missile and drone should fire
  from launcher only, launcher can move, AI or man playing as missile launcher"): P2 drives a ground launcher (arrows
  left/right, UP missile, DOWN drone; 2nd pad: stick, buttons 0/1; AUTO = AI drives, reads shot landing spots and
  sprints away). Armoured: `p2_max_hp` 12 hits (2 hits ended rounds in ~2 s). The flying P2 missile, burrow holes and
  P2 holograms are gone. Drones/auto-gun shared via `update_drones_and_autogun`. Campaign drone launchers drive too
  (trucks and drone launchers turn back before touching). On phones the duel launcher stays between stick and buttons.
- **Stratos boxes**: the user can have one box per game; Squirrel vs Viper restored in `games/saiqulmodi-squirrel-vs-viper/`.
- **Aerobatic flight + sky escape** (user, 2026-10-03): steered, the jet turns at `JET_TURN_PER_FRAME` and keeps its
  speed (`aerobatic_heading`; a reversal is a half loop, split-S near the top) -- no more skidding stop. It may fly out
  of the top of the screen (`sky_esc`): out of sight (missiles/drones head for where it vanished, fuses ignore it);
  after `SKY_RETURN` frames it dives back by itself (`sky_esc["ret"]` overrides keys and autopilot) so it is back
  within 3 s (`SKY_MAX_FRAMES` 180; measured max 129 frames holding UP); `SKY_CEILING` caps the climb. The autopilot
  uses an "escape" climb now and then (`esc_cd` 10 s). The old top-edge bounce is gone; side edges still bounce.
- **Player names** (user, 2026-10-03): two name boxes on the start screen (click/tap; phones use the browser's text
  prompt), saved in save.json `names`; per-name records `players` (high score, best level, duel wins) via
  `record_result`; the first rename of "PLAYER 1" takes over the old global record. Continue uses player 1's best.
  While a name is being typed no other key handler runs. HUD / round text use the names (P2 = "AI" on AUTO).
- **Launchers are rebuilt** (user, 2026-10-03: "allow 2 seconds time gap to revive again after destroying launchers,
  including drone launchers"): `LAUNCHER_REVIVE_FRAMES` 120. A destroyed truck comes back with full armour (its RELOADs
  stay lost; its riding missiles are gone); a drone launcher (`destroy` / `tick_revive`) comes back with the drones /
  missile it had left, and counts as pending while rebuilding. Wrecks show "REBUILD n.ns". Not silos, not the duel
  launcher (wrecking it wins the round).
- **SAFEGUARD** (user, 2026-10-03: "safe guard jet like patriot technology, one key for 3 seconds which will
  [destroy] entire fly objects except jet, and same key active after ten seconds"): key B, touch SAFE, controller hold
  7 + Cross. `SAFEGUARD_FRAMES` 180 on, `SAFEGUARD_COOLDOWN` 600 from activation (exact numbers asked: no +15%). Each
  frame `run_safeguard` downs every flying enemy missile (campaign + duel) and every drone, with interceptor trails and
  a dome; missiles on launchers are left. Own name, not the real system's. Timers pause with the round break / pause.
- **Upgrade batch** (user, 2026-10-03, pasted plan "see it, try it, implement"; plan keys that clashed with existing
  ones were remapped, nothing removed):
  - Biomes: `BIOMES` (10), `biome_index(level)` = ((level-1)//10) % 10 (levels 1-10 = the original grassland). Sky
    gradient + parallax far layer + ground detail; `set_biome` cross-fades 1.5 s. Duel = grassland. Ground blasts leave
    craters (`add_crater`, hooked in `draw_blasts`) and the newest 20 keep smoking until the biome changes / new duel round.
  - Jet paint: `jet_paint(level)` = 100 hues for levels 1-100 (+camo blotches), deeper shade after 100; passed as `paint=`
    to `create_jet_sprite`.
  - Laser: `LaserBattery`, key Z / touch LASER / controller hold 7 + Square; 5 s max, 10 s cooldown, slow recharge when
    released. The L laser tiers use the same battery; while it cools the fire button shoots the gun.
  - `SPECIAL_ORDNANCE` (in the G/R cycle): AIM-9 SIDEWINDER-M (10, IR, also hunts drones), AGM-65 MAVERICK-M + AGM-88
    HARM-M (15), CLUSTER CHUTE-M (25, Y: bursts into 8 bomblets on coloured chutes), BUNKER BUSTER-M (50, U: digs in,
    0.4 s, big blast, reveals/wrecks hidden silos, screen shake, strictly 10 s `BUSTER_COOLDOWN`), HYPERSONIC GLIDE-M +
    SWARM POD-M (75). Flares stay available from level 1 (plan said level 5; not changed).
  - Pilot ejection (user: "pilot coming out when aircraft crashes in the air with all seven colour parachute ... 10
    seconds during the new fighter jet revive"): `start_jet_crash` above `GROUND_Y - 80` adds a pilot; `draw_pilots`
    (crash, round break, play) floats it down under a 7-colour rainbow canopy, lands ~9 s, gone at `PILOT_FRAMES` 600.
- **You = launcher vs AI jet** (user, 2026-10-03: "I wanted launcher as man and fighter as AI"; "it should be always
  either way ... all levels displayed at the bottom, which I want to play is my choice"): `modes["side"]` JET /
  LAUNCHER (`DUEL_SIDES`, saved as `duel_side`; start-screen button in the duel card, key 4, controller Share on
  the start screen; in the duel 4 / touch SWAP swaps at any time and starts a fresh round). On LAUNCHER (`ai_jet()`):
  your keys drive the launcher (arrows / A D, UP / W / SPACE missile, DOWN / S drone, 1st pad stick + Cross / Circle,
  touch < > MISSILE DRONE); jet keys only take the AI's own presses (`post_key(k, ai=True)`). The AI jet: autopilot
  with "attack" dives at the launcher, auto-fire (also on phones), `ai_jet_brain` (flares, shield, heal, SAFEGUARD
  and stealth on NORMAL only; EASY reacts later and fires less). +15% goes to the human launcher (`launcher_buff`:
  reload, drive); the AI jet gets 1.0. Launcher wins are recorded for player 1.
  The duel now has the level strip (N / P / click / tap): `current_level` sets the duel's missiles, drones, biome
  and jet colour (replaces the fixed DUEL_LEVEL 30).
- **Campaign as the launchers** (user, 2026-10-03: "please do that, do not ask again"): the same side switch covers
  the campaign (`ai_jet()` in CAMPAIGN; 4 / touch SWAP mid-game restarts the level on the other side). The AI flies the
  jet (attack dives at the nearest ground target, `ai_jet_brain` also fires its ordnance). You drive the truck marked
  YOU (`cmd["sel"]`, TAB / E / pad Square or R1 / touch NEXT = next truck; arrows / A D / stick / touch < >) and fire
  your own wave stock (`command_missiles` / `command_drones`, x1.15) on top of the launchers' AI fire: UP / W / SPACE
  missile (salvo from your truck, `COMMAND_MISSILE_RELOAD`), DOWN / S drone. Unused stock keeps the wave open. Down
  the jet = next level (recorded for player 1); the jet clears the wave = same level again
  (`(break_winner == "P1") != ai_jet()`). Jet hints are hidden in this mode.
- **Manual launcher fixes** (user, 2026-10-03: "manual launcher is not working"): your truck drives along the WHOLE
  ground (not its own small stretch, which was ~85 px with 7 trucks) and shoulders other trucks / drone launchers
  aside; you never start in the fixed boss silo when a truck exists. The K switch is now **LAUNCHER: AI / YOU /
  FRIEND** (`launcher_who()`; YOU = side LAUNCHER, FRIEND = 2-player MANUAL; phones AI / YOU) -- the old
  "DUEL LAUNCHER: MANUAL" meant a second human and confused the user.
- **Launchers keep firing, +20%** (user, 2026-10-03: "if launcher is less powerful than jet increase its power to 20%
  instead of 15% for aspects; it is observed that launcher is not firing"): playing the launchers, `launcher_buff()` =
  `LAUNCHER_VS_AI_BUFF` 1.20 (the human jet keeps `HUMAN_VS_AI_BUFF` 1.15). Campaign: no stock -- your truck fires
  whenever reloaded, every other truck reloads and fires by itself (`auto_cd`), at most `COMMAND_SKY_CAP` 12 in the air;
  the AI jet wins by surviving `LAUNCHER_WAVE_FRAMES` (60 s, HUD countdown), you win by downing it. UP/DOWN that can't
  fire says why (RELOADING / TRUCK WRECKED / SKY FULL); duel launcher too (max missiles x1.2 = 4). Replaces the
  per-wave stock described below.
- **Half-speed AI jet + your multi-barrel launcher** (user, 2026-10-03: "let jet speed slower by 50% than current
  speed, also add multi barrel missile launcher with double speed than AI jet"): applied when you play the launchers
  (the human-flown jet keeps its speed). `AI_JET_SPEED_FACTOR` 0.5; the truck / duel launcher you drive is
  `YOUR_MBML` "THUNDER MBML-M": `mbml_salvo` fires `MBML_SALVO` 4 rippled missiles at `MBML_SPEED_VS_JET` x the AI jet's
  speed, reload `MBML_RELOAD` / 1.2; they lead the jet (`mbml_lead`); turn limit 30 deg/s unchanged. Duel cap 8.
  Balance (headless runs): the AI jet's SAFEGUARD wiped every salvo and its shield blocked every blast, so the AI now
  uses SAFEGUARD at most every 20 s with 5+ threats (`AI_SAFEGUARD_GAP`), flares every 6 s (`AI_FLARE_GAP`), and
  decides once per missile whether to shield (50%, EASY 25%). Result: levels 11+ the launchers win most waves;
  levels 1-10 (one truck) the jet usually survives the 60 s.
- **Phone, launcher side** (user, 2026-10-03: "missile launcher vs jet is not in mobile mode"): it works on phones (tap
  the bottom-middle LAUNCHER switch to YOU); with touch on, your campaign truck keeps to 230..W-270 so it never hides
  under MISSILE / DRONE, and TOUCH_SWAP sits under PAUSE. Phone flow test: scratchpad-style headless run with
  JVM_MOBILE=1 posting FINGERDOWN / FINGERUP events.
- **+15% power for the human side** (now 20% for the launcher side, see above) (user, 2026-10-03: "build power is 15% more than AI"): playing the launchers,
  `launcher_buff()` = 1.15: every missile of yours +15% speed and fuse reach, drones +15% hit, reload / driving / stock
  +15%, duel launcher armour 14 hits; the AI jet gets 1.0 (`pbuff`, `campaign_jet_buff`). The EASY/NORMAL switch then
  weakens only the AI jet (`ground_difficulty()` keeps your ground side NORMAL). The 30 deg/s missile turn limit and
  the drone speed rule are unchanged. Playing the jet, the old +15% for the jet stays.
- **Online 1v1 / 2v2: later** (user, 2026-10-03: "keep online 1vs1,2vs2 for future"). Not built. Plan when asked:
  server-authoritative simulation at 60 Hz, clients send inputs only, server sends snapshots at 20 Hz, clients
  interpolate 100 ms behind and predict their own jet; symmetric rules (`human_buff` = 1.0).

## Facts

- Venv: `venv/` (gitignored). Run: `venv\Scripts\pythonw.exe main.py` (no console window).
- Tests: `venv\Scripts\python.exe -m pytest -q` (`tests/test_game_rules.py`, dummy SDL drivers via `conftest.py`).
- Automated play-throughs were run with scripts in the session scratchpad against a COPY of the folder,
  because the game writes `save.json` (gitignored) in the working directory.
- Browser build: `docs/` (pygbag 0.9.3). The Stratos Games portal box is `games/saiqulmodi/` in
  `Stratos-Technologies-fzco/stratos-games-site` (clone `~/OneDrive/Desktop/stratos-games-site`);
  `tools/make_stratos_box.py` rebuilds it from `docs/` with the engine bundled. Only ever commit that folder there.

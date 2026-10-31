# Jet vs Missile - web 3D port plan

The pygame game (`../main.py`, 2,646 lines) stays as it is. This file is the inventory of what main.py
really contains (line numbers cited), and the phases that bring it to the web 3D build in `web/`.
Scale used by the port: 1 main.py px = 4 m on the ground, main.py speeds x3 (level 1 = 252 m/s cruise),
60 physics frames per second = main.py frames (main.py:2642). See `src/config.ts`.

## 1. World (main.py:22-33, 339-800)
| Item | main.py | Notes |
|---|---|---|
| Map | `WORLD_W, WORLD_H = 14000, 5000` px (main.py:26) | = 56 x 20 km |
| Altitudes | `CRUISE_ALT_FT 35000` (27), `ALT_MIN 3000` (165), climb/dive `ALT_RATE 70` ft/frame (166) | |
| Jet speed | `BASE_SPEED 0.35` px/frame + `SPEED_PER_LEVEL 0.01` (29-30), `level_speed()` (190) | level 100 = 1.35 px/frame |
| Terrain | mountains in the north (345-362), rivers + 4 tributaries (364-383), frontier with the eastern neighbour (385-397), western sea + coast `coast_x()` (481-483), south-east desert (485-487) | |
| Cities | `CITY_COUNT 12` "SECTOR-A..L", street grids, lit blocks (399-412), highways + railways between them (408-412) | |
| Airbases | 3, next to cities 2, 6, 9 (414-418) | runway, taxiway, apron (635) |
| Forests / villages | 70 forests, 240 villages (420-435) | |
| Clouds | `CLOUD_COUNT 110` at 6,000-28,000 ft, drift with `WIND (0.30,-0.10)` (176, 1354-1408) | clouds above the jet pass between it and the camera (2585) |
| Low-altitude detail | trees, highway traffic, boats below 1.5x zoom (168, 1466-1527) | camouflaged launchers spotted below `LOW_ALT_SPOT 15000` ft within 350 px (169-170, 2091-2095) |
| Ground war | artillery blasts along the front (2347-2354), 10 supply convoys on highways (1654-1658, 2355-2359) | cosmetic |
| Day / night | T key (2001); night = moonlit ground + city, highway, village, airbase lights (673-740), SAM radar beacons (2417), convoy headlights, jet nav lights (2522) | |

## 2. Threats (enemy side)
There is **no flak and no enemy interceptor aircraft** in main.py. Every threat is ground-launched or a drone.

### SAM batteries (main.py:55-61, 437-458, 830-860, 2229-2241)
| Stat | Value |
|---|---|
| Count | `SAM_SITE_COUNT 50`, `SAM_SPACING 420` px apart, away from cities and the river |
| Missiles | `SAM_MISSILES_PER_SITE 20` (1,000 in reserve) |
| HP | `SAM_SITE_HP 2` (bomb / AGM hits) |
| Engagement | jet inside `SAM_RANGE 650` px ground ring, launch chance `1/240` per frame (2239), reload `SAM_SITE_RELOAD 900` frames, first reload random (457) |
| Cap | `AUTO_SAM_CAP 4` self-launched SAMs airborne at once (61, 2216, 2236) |
| Look | concrete pad, phased-array radar dome with rotating face, 4 vertical canisters, ready light, launch flash (830-860) |

### TELs - mobile launchers (main.py:63-68, 460-475, 805-827)
| Stat | Value |
|---|---|
| Count | `TEL_COUNT 150`, `TEL_SPACING 180` px from every launcher |
| Missiles | `TEL_MISSILES 4`, HP 1 |
| Engagement | `TEL_RANGE 520` px, same launch rule and reload as SAM sites |
| Camouflage | `TEL_CAMOUFLAGED_SHARE 0.7` hidden until they fire; a launch reveals it for `TEL_REVEAL_FRAMES 1200` (20 s, main.py:1852); low flying (< 15,000 ft) spots hidden ones within 350 px (2091-2095) |
| Look | truck body, cab, raised twin-tube rack (805-827), no radar |

### Drones (main.py:89-93, 1003-1048, 2208-2227)
| Stat | Value |
|---|---|
| Count | `DRONE_COUNT 12`, altitude 9,000-16,000 ft |
| Speed | `DRONE_SPEED_VS_JET 0.5` of the level speed, turn `speed/30` rad/frame |
| Patrol | 3 waypoints at a time: 50% over a city, 50% open country (1020-1026) |
| Role | a drone within `DRONE_SPOT_RANGE 380` px of the jet cues the nearest armed launcher within 2,500 px to launch (counts toward the cap), then waits `DRONE_SPOT_RELOAD 900` |
| Losses | shot down by AAM; a replacement crosses the border after `DRONE_RESPAWN_FRAMES 1200` |
| Look | long straight wings, slim body, V-tail, sensor turret (976-984) |

### SAM missile (main.py:70-79, 1054-1137, 2276-2326)
| Stat | Value |
|---|---|
| Speed | `SAM_SPEED_VS_JET 2.2` x level speed; boost ramps 35% -> 100% over the climb (1106) |
| Climb | `SAM_CLIMB_FRAMES 420` to 35,000 ft, scaled by the target altitude, min 90 (1069) |
| Kinds | `SAM_GUIDED_SHARE 0.5`: guided or unguided at random (77, 1853) |
| Guided | homes 0.022 rad/frame (1120), `SAM_LIFE_FRAMES 2400` (40 s) then self-destructs (1099) |
| Unguided | aimed where the jet will be (1072-1078), motor = climb + `UNGUIDED_MOTOR_FRAMES 300`, then falls (1107-1112) |
| Fuse | `SAM_FUSE 22` px and within 3,000 ft of altitude (2312-2313) |
| Damage | `SAM_DAMAGE = JET_HP 300`: one hit = shot down (70-71) |
| Fuses only | once the missile is at 94% of its climb (2294) |
| Trails | guided (236,232,224), unguided (206,196,176) (1082) |

## 3. Countermeasures (main.py:946-953, 1955-1993, 2298-2310)
One key, **C** (pad Y / touch FLARE): flares when they are ready, otherwise the ECM jammer (1955-1957).
| | Flares | ECM jammer |
|---|---|---|
| Reload | `FLARE_RELOAD 300` (5 s) | `ECM_RELOAD 720` (12 s) |
| Range | `FLARE_RANGE 260` px | `ECM_RANGE 450` px |
| Chance | `FLARE_DECOY_CHANCE 0.85` per guided missile | `ECM_BREAK_CHANCE 0.6` per guided missile aimed at you |
| Rule | 6 flares behind the jet; works on guided SAMs past half their climb (1988) | the seeker takes a false track 400 px ahead +-150 px (1968) |
| After | decoyed missile turns 0.05 rad/frame toward the decoy and blows up within 20 px of it, or after 150 frames (1115-1117, 2288-2293) | same |
AI-flown jets pop flares at `AI_FLARE_DISTANCE 120` px, decoy chance 0.8, once per missile (946-947, 2296-2310).

## 4. The player's side
- **Squadron**: 10 jets (callsigns VIPER-1 .. OMEGA-10, 866), 4 flights ALPHA V / BRAVO echelon / CHARLIE line / DELTA trail (941),
  racetrack CAP 700 px, new station every 60 s, keep 2,200 px from your jet (943-945). TAB / LB / RB / minimap click switch jets (1936, 2048).
- **HP** `JET_HP 300`; a downed jet: `CrashingJet` spins (`CRASH_SPIN 0.09`) and falls (1195-1229), the pilot ejects under a
  7-colour chute (1232-1297); a replacement rejoins after `JET_REJOIN_FRAMES 180` (80, 2148-2162).
- **Weapons**: bomb SPACE (blast 45 px, falls with drag, impact marker, 1300-1334); AGM R (nearest visible launcher within
  `AGM_RANGE 1600`, speed 3x, turn 0.03); AAM F (nearest drone within `AAM_RANGE 1200`, speed 4x, turn 0.05);
  `JET_MISSILE_RELOAD 45` (83-87, 1139-1192, 1859-1875). Hits: 1 damage; SAM site 2 HP, TEL 1 HP (1877-1888).
- **Aerobatics** V: barrel roll 150 f, loop 260 f (60 px, 4,000 ft), victory rolls 150 f, with 3-colour display smoke (179-183, 2097-2133).
- **Manual SAM** M: the nearest battery launches at you (1994-2000).
- **Levels** 1-100, N / P / bottom-bar buttons: only the speed changes (190, 2026-2029).
- **2 players** (key 2): player 2 picks a launcher near the jet (`P2_PICK_RANGE 1400`) and fires guided (UP) or unguided (DOWN),
  `P2_FIRE_GAP 60` (47-52, 2003-2025, 2572-2583).
- Not in main.py: **scoring, waves, upgrades**. main.py does not read or write `save.json` (the file in the folder is left over).

## 5. Sounds (main.py:276-328) - all synthesised, no files
`snd_shoot` 840->260 Hz 0.08 s (bomb), `snd_explode` low-passed noise 0.45 s, `snd_ignite` 140->380 Hz 0.25 s (SAM launch, ECM),
`snd_switch` 600->980 Hz 0.1 s (jet switch, aerobatics), `snd_missile` 1200->500 Hz 0.18 s (AGM/AAM), `snd_flare` 2200->1400 Hz 0.12 s.
No music. main.py has no warning tones (the web RWR tones are new).

## 6. HUD (main.py:2506-2640)
Bracket round your jet (red flashing when locked), callsign + altitude tag, HP bar, flare and ECM reload bars, ECM ring;
missile warning: arrow toward the nearest threat, red screen border flashing, "MISSILE LOCK n + ROCKET n - distance", advice
line (flares ready / ECM ready / reloading - turn hard / unguided - turn out of its path); rocket warning for unguided rounds
within `ROCKET_WARN_RANGE 400` px on a crossing course (2516-2519); message log (5 lines, 3 s, 1704);
minimap (sites, TELs, drones, missiles, jets, view box, 2592-2613); bottom bar: controls, P2 controls, 1/2 players,
day/night, level prev/next, jet switch (2618-2639); range ring of launchers that have you in range (2469-2473); touch controls (147-161).

## 7. Controls (main.py:41-50, 101-161)
Keyboard: WASD fly, Q/E climb/dive, SPACE bomb, R AGM, F AAM, C flares/ECM, V aerobatics, M SAM, TAB jet, N/P level, T day/night, 2 players.
Pad: stick fly, R2/L2 climb/dive, A bomb, B AGM, X AAM, Y flares, LB/RB jet, Back/Start level, L3 aerobatics, R3 SAM, touchpad night.
Touch: stick + BOMB, AGM, AAM, FLARE, SAM, AERO, CLIMB, DIVE.

## Phases (stop after each, wait for "go")
1. **Done** - first playable: scaffold, energy-model flight, terrain, chase camera, SAM batteries, HUD, pooling.
2. **Threats + countermeasures**: proportional-navigation guided SAMs (boost, burnout, coast with drag and gravity), unguided
   rounds, full roster at main.py stats (50 SAM batteries, 150 TELs with camouflage/reveal/low-level spotting, 12 drones that
   cue launchers), flares (main.py 0.85, ~2 s burn), ECM (main.py 0.6, false track), notching for radar seekers, overshoot on a
   late break, RWR arrows with bearing / distance / closing speed, Web Audio search / lock / launch tones, flare + ECM controls.
   Seekers: battery missiles are radar-guided (the site carries the radar, main.py:843), TEL missiles heat-seeking (TELs have
   no radar, main.py:805-827). Flares fool heat seekers, ECM and notching fool radar seekers. Flares and ECM get a key each
   (C / X) instead of main.py's shared C key.
3. **World + visuals**: main.py map features in 3D (coast + sea, rivers, mountains, desert, 12 cities, highways, railways,
   3 airbases, forests, villages, front line, artillery, convoys), 110 clouds, atmosphere shader, contrails, day/night (T) with
   every main.py light, post-processing.
4. **Sound**: main.py's 6 synthesised sounds + engine, missile and blast sounds (actions only, no music).
5. **Squadron + weapons**: 10 jets in 4 flights, jet switching, bombs, AGM, AAM (drones can be shot down, respawn), destroying
   launchers, crash + ejection, aerobatics + display smoke, manual SAM (M), levels 1-100, 2-player launcher mode, minimap,
   message log, helicopters.
6. **Ship**: PWA (offline, install), GitHub Pages / Stratos box, size + performance pass on phones.

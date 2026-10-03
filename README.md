# Jet vs Missile

A sky-and-ground arcade shooter built with Python and [pygame-ce](https://pyga.me/).

You fly a stealth jet. Missile launchers drive along the ground and fire homing missiles at you,
and every few levels the missiles get faster, tougher and smarter.

## Play it

- **On your phone (phone mode, full page):**
  https://stratos-technologies-fzco.github.io/stratos-games-site/games/saiqulmodi/index.html?mobile
  Open it, turn the phone sideways and tap once: the game goes full screen.
- **On the Stratos Games site:** https://stratos-technologies-fzco.github.io/stratos-games-site/play/saiqulmodi/

The battlefield is as wide as your screen (16:9 computers, wider phones), so there are no black bars.

## How to play

| Key | Action |
|---|---|
| W A S D (or stick) | Fly. The jet turns in arcs and never stalls; reverse and it flies a half loop. Climb out of the top of the screen to escape an attack: it is out of sight up there and comes back within 3 s. Let go and the autopilot keeps flying: cruise, climbs, dives, loops, rolls, break turns and sky escapes (AUTO) |
| Mouse | Aim (the guns only fire forward, from the nose, up to 30 degrees off the flight path) |
| Left click / Space | Fire |
| E | Shield (a missile blowing up against it does no harm; energy runs down while held) |
| Q | Repair kit (+HP) |
| F | Flares (12 against the AI, 10 in a two-player duel): each missile chases its nearest flare and blows up on it |
| T | Triple jet squad |
| C | Camouflage: the jet fades for 4 s and missiles lose their lock |
| V | Stealth: 2 s invisible to missiles and launchers (no lock, fuses can't detect the jet, launchers hold fire); 8 s recharge |
| B | SAFEGUARD: for 3 s every enemy missile and drone in the air is shot down by the jet's interceptors; ready again 10 s after you switched it on (phone: SAFE button; controller: hold button 7 + Cross/A) |
| L | Switch to laser weapons |
| Z (hold) | Laser ray, separate from the guns: up to 5 s, then 10 s cooldown (phone: LASER; controller: hold button 7 + Square) |
| Y | Parachute cluster bomb (from level 25) |
| U | Bunker buster (from level 50, one every 10 s) |
| G | Next ordnance (nation missiles and bombs, from level 5) |
| R / right click | Launch the selected ordnance |
| X | FLIR pod: scan the ground for hidden silos (from level 10) |
| N / P, or click the level strip | Next / previous level |
| Enter / Pause | Pause and resume |
| Esc | Back to the mode menu |
| Start screen: click a name box | Type player 1 / player 2 names (Enter = done); each name keeps its own best level, high score and duel wins |
| Start screen: J / K / H | Jet AUTO-MANUAL / duel launcher AUTO-MANUAL / AI EASY-NORMAL |
| Start screen: 3 | Continue the campaign from your best level |
| Start screen: 4 (or the button in the duel card) | Duel: YOU PLAY THE JET, or YOU PLAY THE LAUNCHER against the AI jet |
| Duel or campaign: 4 / SWAP | Swap sides at any time: fly the jet, or play the launchers against the AI jet (the round / level restarts) |
| Campaign as launchers: TAB / E | Drive the next truck (marked YOU); arrows / A D drive it, UP / W / SPACE fires your missiles, DOWN / S your drones. Down the AI jet to reach the next level |
| Duel: N / P / level strip | Play the duel at any level you choose |

**Phone / tablet** (turn it sideways): drag your thumb on the left half to fly, hold **FIRE** (it aims
itself at the nearest missile, else a launcher), hold **SHIELD**, tap **STEALTH**, **CAMO**, **FLARES**,
**SQUAD**, **HEAL**; tap a mode card to start, tap a level number to jump, **MENU** goes back.
Phones are detected automatically (add `?mobile` to the link to force it).

**Game controller**: left stick flies, right stick aims, Cross/A or R1 fires, L1 shield, Triangle flares,
Share camouflage; d-pad up = stealth, down = camouflage, left/right = previous/next level.
Ordnance button (R2 in the browser, Start on desktop): tap = launch the selected ordnance; hold it and
press d-pad left/right = previous/next ordnance, d-pad up = FLIR pod on/off, d-pad down = pause (any
button resumes). On the start screen: Square / Triangle / L1 change the three switches, R1 continues.
Using a controller hides the touch buttons.

The jet is drawn smaller the higher it flies (further from the launchers), and the missiles'
detonation distance shrinks with it.

Modes: **1P Campaign** (jet vs AI missiles, levels 1-100, then endless overdrive) and **Jet vs Launcher**
(player 1 flies the jet; player 2 -- or the AI -- drives an armoured launcher along the ground and fires
missiles and drones from it: arrows left/right drive, UP fires a missile, DOWN sends a drone; 12 hits wreck it).
On phones the duel is always against the AI launcher.

## How the game grows

- Every 5 levels the game steps up: missiles and their shots get faster, both sides hit harder
  (power x1.0 at level 1, x2.0 at level 51, x3.0 from level 101) and the jet's max HP rises.
- Missile classes by level: short range (1-20), medium range (21-40), long-range cruise (41-60),
  ballistic (61-80), hypersonic glide vehicle (81+). Every 10th level is a boss launched from a silo.
- Missiles never fire. A missile's only job is to reach the jet: a direct hit, or it blows itself up
  right next to the jet (proximity fuse), and the jet crashes. Only the shield (E) survives the blast.
  Shoot them down before they get close; only missiles you shoot down score points.
- Missiles fly like projectiles, not aerobatic jets: they leave the launch rail angled at the jet and
  fly at a steady speed in smooth arcs. A missile that overshoots and leaves the sky, or dives into the
  ground, is gone, and its launcher fires the next one.
- The missile AI learns new tactics: flank (attack from different sides, level 20+), reload launches
  from surviving launchers (level 30+), ECM jamming (level 55+).
- A missile turns at most 30 degrees per second, so a sharp turn can shake it off. It tracks the jet
  for 20 seconds, then falls and explodes on the ground, and its launcher fires the next one: to clear
  a wave you have to shoot the missiles down, lure them onto flares, or destroy their launchers.
- Missile launchers on the ground: 1 at levels 1-10, one more every 10 levels, 10 from level 91. Each
  drives in its own stretch and is destroyed by its second hit (the boss silo too). A missile is destroyed
  by a single hit. Missiles and drones only ever come from launchers on the ground.
  A destroyed launcher (truck or drone launcher) is rebuilt 2 seconds later.
- Every 5 levels a nation's arsenal unlocks (Russia 5, Iran 10, China 15, Ukraine 20, North Korea 25,
  United States 30, United Kingdom 35, Germany 40): its two ground launchers join the enemy side (each
  labelled, with its own trail colour; multi-barrel launchers fire salvos) and its two jet munitions
  (air-to-air, air-to-ground, guided, glide or free-fall bombs) join your ordnance.
- From level 10: heat-seeking missiles, the FLIR pod, and underground silos (2 at level 10, up to 10 from
  level 50) that stay invisible until they fire or your FLIR finds them.
- Drones: drone launchers drive on the ground too (1 at levels 1-10, one more every 10 levels, up to 10)
  and send out attack drones (stronger each level up to drone level 20); from level 5 each also holds one
  missile. Drones fly at half the jet's speed and cost HP when they reach you. Your jet's protective
  auto-gun shoots by itself at any drone that comes within range.
- Against the AI your jet gets +15% in everything (damage, reload, speed, HP, shield, flares, stealth,
  ammo, auto-gun range...); a 2-player duel between two people stays even.
- Control modes on the start screen: **JET AUTO / MANUAL** (AUTO: autopilot + guns that aim and fire by
  themselves -- on phones only FIRE fires; MANUAL: you fly and shoot everything) and **DUEL LAUNCHER AUTO /
  MANUAL** (AUTO: the computer drives the launcher). Keys J / K. On phones the duel is always you vs the AI.
- AI difficulty on the start screen: **EASY** (slower, simpler missiles and drones) or **NORMAL**.
- Hints appear once when a new feature unlocks; the campaign card can continue from your best level.
- All weapon and launcher names are the game's own "-M" versions (for example R-77-M, PATRIOT PAC-3-M).
- The ground changes every 10 levels through 10 landscapes (grassland, deep ocean, sea shore, desert, mud,
  red canyon, arctic, volcanic, jungle, city), and every level paints the jet in its own colour.
  Explosions leave smoking craters until the landscape changes.
- Extra jet weapons: Sidewinder-M (level 10, also hunts drones), Maverick-M and HARM-M (15), cluster bomb on
  parachutes (25), bunker buster (50), hypersonic glide missile and swarm pod (75).
- A jet shot down in the air ejects its pilot, who floats down under a rainbow parachute for 10 seconds.
- When the jet is brought down it falls burning and explodes on the ground; a fresh jet with full HP
  starts the next round.

## Run it

```
py -3.12 -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe main.py
```

## Tests

```
venv\Scripts\python.exe -m pytest -q
```

## Browser build

`docs/` holds the WebAssembly build (pygbag). To rebuild: copy only `main.py` into an empty folder
named `jet_vs_missile`, run `python -m pygbag --title "Jet vs Missile" --build <that folder>`, and copy
its `build/web/*` into `docs/`.

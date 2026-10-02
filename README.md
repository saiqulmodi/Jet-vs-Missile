# Jet vs Missile

A sky-and-ground arcade shooter built with Python and [pygame-ce](https://pyga.me/).

You fly a stealth jet. Missile launchers drive along the ground and fire homing missiles at you,
and every few levels the missiles get faster, tougher and smarter.

## How to play

| Key | Action |
|---|---|
| W A S D (or stick) | Fly. Let go and the autopilot keeps the jet flying: cruise, climb, dive, loops, barrel rolls and dogfight break turns |
| Mouse | Aim |
| Left click / Space | Fire |
| E | Shield (a missile blowing up against it does no harm; energy runs down while held) |
| Q | Repair kit (+HP) |
| F | Flares + 8 mirage jets (missiles chase the decoys) |
| T | Triple jet squad |
| C | Camouflage: the jet fades for 4 s and missiles lose their lock |
| V | Stealth: 2 s invisible to missiles and launchers (no lock, fuses can't detect the jet, launchers hold fire); 8 s recharge |
| L | Switch to laser weapons |
| N / P, or click the level strip | Next / previous level |
| Esc | Back to the mode menu |

Modes: **1P Campaign** (jet vs AI missiles, levels 1-100, then endless overdrive) and **2P Duel**
(player 1 flies the jet, player 2 flies a hypersonic missile with no guns that wins by ramming the jet).

## How the game grows

- Every 5 levels the game steps up: missiles and their shots get faster, both sides hit harder
  (power x1.0 at level 1, x2.0 at level 51, x3.0 from level 101) and the jet's max HP rises.
- Missile classes by level: short range (1-20), medium range (21-40), long-range cruise (41-60),
  ballistic (61-80), hypersonic glide vehicle (81+). Every 10th level is a boss launched from a silo.
- Missiles never fire. A missile's only job is to reach the jet: a direct hit, or it blows itself up
  right next to the jet (proximity fuse), and the jet crashes. Only the shield (E) survives the blast.
  Shoot them down before they get close; only missiles you shoot down score points.
- The missile AI learns new tactics: jink (dodges your shots, level 8+), flank (level 20+),
  reload launches from surviving launchers (level 30+), sprint (level 35+), ECM jamming (level 55+).
- Six launchers cover the ground; each needs at least two hits to destroy (the boss silo four).
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

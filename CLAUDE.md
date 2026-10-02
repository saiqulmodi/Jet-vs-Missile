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
- **Launchers** (6, one stretch of ground each) need at least 2 hits (boss silo 4), rebuilt every wave.
- The user tests gameplay themselves: say what changed, let them play it, commit when they say so.

## Facts

- Venv: `venv/` (gitignored). Run: `venv\Scripts\pythonw.exe main.py` (no console window).
- Tests: `venv\Scripts\python.exe -m pytest -q` (`tests/test_game_rules.py`, dummy SDL drivers via `conftest.py`).
- Automated play-throughs were run with scripts in the session scratchpad against a COPY of the folder,
  because the game writes `save.json` (gitignored) in the working directory.
- Browser build: `docs/` (pygbag 0.9.3). The Stratos Games portal box is `games/saiqulmodi/` in
  `Stratos-Technologies-fzco/stratos-games-site` (clone `~/OneDrive/Desktop/stratos-games-site`);
  `tools/make_stratos_box.py` rebuilds it from `docs/` with the engine bundled. Only ever commit that folder there.

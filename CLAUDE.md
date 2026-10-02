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
- **Missiles never fire** (user, 2026-10-02: "either it hit or destroy itself near to target"). Their only
  attack is the proximity fuse (`FUSE_RADIUS` 60, boss x1.4): within range the missile blows itself up and the
  jet crashes (`p1_hp = 0`); a held shield absorbs the blast. The onboard-ammunition system and the
  "Bullet Hell Surge" mutator were removed for this. In the 2P duel, P2's missile has no guns and wins by ramming.
- After a crash, the next round's jet starts with full HP.
- **Stealth key V** (user, 2026-10-02): 2 s (`STEALTH_DURATION`) invisible to missiles and launchers: missiles fly
  to the last seen spot, the proximity fuse ignores the jet (also P2 in the duel), missiles on launchers and
  RELOAD launches wait; 8 s recharge from activation. Separate from camouflage C (4 s fade, fuses still work).
- The user tests gameplay themselves: say what changed, let them play it, commit when they say so.

## Facts

- Venv: `venv/` (gitignored). Run: `venv\Scripts\pythonw.exe main.py` (no console window).
- Tests: `venv\Scripts\python.exe -m pytest -q` (`tests/test_game_rules.py`, dummy SDL drivers via `conftest.py`).
- Automated play-throughs were run with scripts in the session scratchpad against a COPY of the folder,
  because the game writes `save.json` (gitignored) in the working directory.
- Browser build: `docs/` (pygbag 0.9.3). The Stratos Games portal box is `games/saiqulmodi/` in
  `Stratos-Technologies-fzco/stratos-games-site` (clone `~/OneDrive/Desktop/stratos-games-site`);
  `tools/make_stratos_box.py` rebuilds it from `docs/` with the engine bundled. Only ever commit that folder there.

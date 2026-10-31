// Game values taken from ../main.py (the pygame game), scaled to 3D. 1 Three.js unit = 1 metre.
// main.py is a 2D top-down game in pixels and frames at 60 FPS (main.py:2642 clock.tick(60)).
// The web build steps its physics at the same 60 Hz, so frame counts are used as they are.

export const STEP = 1 / 60; // one main.py frame (main.py:2642)
export const FT = 0.3048; // metres per foot

/** 1 main.py ground pixel = 4 m (so the 22 px SAM fuse is 88 m). */
export const PX_M = 4;
/** main.py level 1 is deliberately "10x slower than arcade speed" (main.py:29); x3 turns it into a real jet cruise. */
export const TIME_SCALE = 3;
/** main.py px/frame -> m/s */
export const pxFrameToMps = (v: number): number => v * PX_M * 60 * TIME_SCALE;

// ---- Altitudes ----
export const CRUISE_ALT_FT = 35000; // main.py:27, the start altitude too (main.py:882)
export const ALT_MIN_FT = 3000; // main.py:165, lowest altitude in main.py; here it is the "PULL UP" warning height above ground
// main.py:166 ALT_RATE (70 ft/frame) is replaced by the energy model: climb rate now comes from thrust minus drag.

// ---- Jet ----
export const BASE_SPEED_PX = 0.35; // main.py:29, px/frame at level 1
export const JET_CRUISE_MPS = pxFrameToMps(BASE_SPEED_PX); // = 252 m/s, the start speed
export const JET_HP = 300; // main.py:70
export const CRASH_SPIN = 0.09; // main.py:72, rad/frame roll of a falling wreck
export const JET_REJOIN_FRAMES = 180; // main.py:80, a downed jet's replacement after 3 s -> restart allowed after 3 s

// ---- SAM batteries ----
export const SAM_SITE_COUNT_PHASE1 = 16; // main.py:55 has 50 over the whole country; Phase 1 places 16 near the start
export const SAM_MISSILES_PER_SITE = 20; // main.py:56
export const SAM_SPACING_M = 420 * PX_M; // main.py:57, 420 px minimum gap = 1,680 m
export const SAM_SITE_HP = 2; // main.py:58 (no jet weapons in Phase 1, kept for Phase 5)
export const SAM_RANGE_M = 650 * PX_M; // main.py:59, 650 px ground ring = 2,600 m
export const SAM_SITE_RELOAD = 900; // main.py:60, frames (15 s)
export const AUTO_SAM_CAP = 4; // main.py:61, at most 4 self-launched SAMs airborne
export const SAM_LAUNCH_CHANCE = 1 / 240; // main.py:2239, per frame while the jet is inside the ring

// ---- SAM missile ----
export const SAM_DAMAGE = JET_HP; // main.py:71, one hit = shot down
export const SAM_FUSE_M = 22 * PX_M; // main.py:73, 22 px = 88 m proximity fuse (a sphere in 3D)
export const SAM_SPEED_VS_JET = 2.2; // main.py:74
export const SAM_SPEED_MPS = SAM_SPEED_VS_JET * JET_CRUISE_MPS; // = 554 m/s
export const SAM_CLIMB_FRAMES = 420; // main.py:75, boost phase length for a 35,000 ft target
export const SAM_CLIMB_MIN_FRAMES = 90; // main.py:1069
export const SAM_BOOST_START = 0.35; // main.py:1106, speed starts at 35% and ramps to 100% over the climb
export const SAM_LIFE_FRAMES = 2400; // main.py:76, 40 s of motor, then it self-destructs
export const SAM_TURN_PER_FRAME = 0.022; // main.py:1120, rad/frame (kept per frame, not time-scaled: 1.32 rad/s)
export const SAM_GUIDED_SHARE = 0.5; // main.py:77, each launch is guided or unguided at random
export const UNGUIDED_MOTOR_FRAMES = 300; // main.py:78, unguided: 5 s of motor after the climb, then it falls

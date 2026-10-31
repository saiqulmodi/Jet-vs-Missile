# Jet vs Missile - Web 3D port plan

Goal: move Jet vs Missile from the flat, software-rendered 2D pygame loop (`../main.py`) to a
GPU-accelerated 3D browser game, total download under 20 MB. The pygame game stays as it is.

## Stack
- Three.js (WebGL), TypeScript, Vite.
- Custom deterministic arcade-aerodynamics, fixed 60 Hz step inside the requestAnimationFrame loop.
- Web Audio API procedural sound (0 byte audio files).

## Asset budget (< 20 MB target)
| Asset | Technology / format | Footprint |
|---|---|---|
| Engine + code | Three.js + post-processing + game logic (gzip) | ~700 KB |
| Aircraft models | 4 low-poly LOD GLB meshes (fighter, drone, SAM TEL, radar) | ~2.5 MB |
| Terrain heights | 2048x2048 16-bit PNG elevation + normal map | ~4.0 MB |
| Ground splats | 1K albedo/roughness (grass, rock, desert, urban), KTX2 | ~5.0 MB |
| Sky + atmosphere | procedural Rayleigh/Mie GLSL | ~15 KB |
| SFX + voice | procedural Web Audio + compact Opus radio comms | ~1.5 MB |
| Reserve | UI fonts, particle atlas, minimap icons | ~1.5 MB |
| **Total** | | **~15.2 MB** |

## Visuals
- Atmosphere shader (Preetham/Bruneton): azure low, deep stratospheric indigo at 35,000 ft, horizon fog.
- Volumetric cloud deck 12,000-20,000 ft (raymarched Worley + Perlin), whiteout when punching through.
- Contrails / ribbon trails as GPU triangle strips with soft alpha falloff.
- Post: bloom (missile burns, flares, night lights), speed vignette + chromatic aberration at Mach 1.2+ /
  high G, heat haze behind nozzles.

## Flight dynamics + weapons
- Energy model: Lift = CL(a) q S, Drag = (CD0 + k CL^2) q S, q = 1/2 rho(h) v^2, rho falls exponentially
  with altitude (crisp low, sluggish high). Hard turns bleed speed unless diving or on afterburner.
- G-LOC: sustained > 8 G darkens the screen.
- SAM guidance: true proportional navigation a_n = N Vc dLambda/dt (N 3-5); boost, burnout, ballistic
  descent; notching (90 deg aspect) breaks Doppler lock.
- RWR: search / lock / launch tones, bearing, closure, suggested countermeasure (notch, flares, ECM).
- Countermeasures: flares (cooling decoy probability), ECM jamming that breaks radar lock.
- Procedural audio: engine rumble (pink noise + resonant low-pass on throttle), missile whoosh + doppler,
  flare pop, explosion rumble, RWR tones.

## Deployment
- Vite + terser; KTX2 / Basis textures.
- GitHub Pages (or Cloudflare Pages / Vercel).
- PWA: manifest + service worker so it installs and runs offline.

## Phases (stop after each, wait for "go")
1. **First playable** (this phase): Vite + TS + Three.js scaffold in `web/`; fixed 60 Hz physics + render
   loop (`src/main.ts`); `core/Input.ts` (keyboard, Gamepad API, touch stick); `flight/JetPhysics.ts`
   (lift/drag, induced drag in turns, thrust + afterburner, density with altitude, G, stall);
   `world/Terrain.ts` (procedural heightfield, no texture downloads); `camera/ChaseCamera.ts` (lag,
   FOV widening on afterburner); `threats/SamSite.ts` + `threats/Missile.ts` (one SAM type, simple pursuit);
   `ui/Hud.ts` (speed, altitude, heading, G, health, missile warning); `core/Pool.ts` (object pooling).
   Values from main.py, scaled to 3D, each commented with its main.py line. Keyboard layout on the start screen.
   Done when: fly, get shot at by a SAM, dodge or get hit, restart; 60 FPS; zero console errors.
2. Proportional-navigation SAMs, unguided rounds, RWR, flares + ECM.
3. Atmosphere shader, clouds, contrails, post-processing.
4. Procedural Web Audio engine.
5. Rest of main.py content (squadron, TELs, drones, cities, jet weapons), PWA + deploy.

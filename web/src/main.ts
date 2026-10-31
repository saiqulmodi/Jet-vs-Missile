// Jet vs Missile - web 3D, Phase 1. Game loop: fixed 60 Hz physics step + one render per display frame.
import './style.css';
import { Color, DirectionalLight, HemisphereLight, Quaternion, Scene, Vector3, WebGLRenderer } from 'three';
import { ChaseCamera } from './camera/ChaseCamera';
import { JET_REJOIN_FRAMES, SAM_DAMAGE, SAM_FUSE_M, SAM_GUIDED_SHARE, SAM_SITE_COUNT_PHASE1, SAM_SPACING_M, STEP } from './config';
import { Input } from './core/Input';
import { Pool } from './core/Pool';
import { JetModel } from './flight/JetModel';
import { JetPhysics } from './flight/JetPhysics';
import { Explosions } from './fx/Explosions';
import { Smoke } from './fx/Smoke';
import { Missile } from './threats/Missile';
import { SamSite } from './threats/SamSite';
import { Hud } from './ui/Hud';
import { Sky } from './world/Sky';
import { Terrain, heightAt } from './world/Terrain';

type State = 'start' | 'flying' | 'down';
const MAX_STEPS = 5; // physics steps per display frame at most (after a stall, the game slows rather than spirals)
const MISSILE_POOL = 8;

// ---------- renderer + scene ----------
const app = document.getElementById('app') as HTMLDivElement;
const renderer = new WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
app.appendChild(renderer.domElement);

const scene = new Scene();
scene.background = new Color(0x87b4e6);
const sky = new Sky();
scene.fog = sky.fog;
scene.add(sky.mesh);
scene.add(new HemisphereLight(0xdfeaff, 0x4a5a3a, 1.1));
const sun = new DirectionalLight(0xfff4e0, 2.2);
sun.position.set(0.5, 1, 0.3);
scene.add(sun);

const terrain = new Terrain();
scene.add(terrain.mesh);

const camera = new ChaseCamera(window.innerWidth / window.innerHeight);
const input = new Input(app);
const hud = new Hud(app);
const jet = new JetPhysics();
const jetModel = new JetModel();
scene.add(jetModel.group);
const smoke = new Smoke();
scene.add(smoke.mesh);
const blasts = new Explosions(scene);
const missiles = new Pool<Missile>(MISSILE_POOL, () => {
  const m = new Missile();
  scene.add(m.mesh);
  return m;
});

// ---------- SAM batteries ----------
let seed = (Date.now() & 0x7fffffff) | 1;
function rand(): number {
  // mulberry32
  seed = (seed + 0x6d2b79f5) | 0;
  let t = seed;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

const sites: SamSite[] = [];
function placeSites(): void {
  for (const s of sites) scene.remove(s.mesh);
  sites.length = 0;
  let tries = 0;
  while (sites.length < SAM_SITE_COUNT_PHASE1 && tries++ < 4000) {
    // most batteries ahead of the start (north = -Z), some all round
    const ahead = sites.length < 10;
    const x = (rand() * 2 - 1) * (ahead ? 9000 : 22000);
    const z = ahead ? -6000 - rand() * 26000 : (rand() * 2 - 1) * 22000;
    if (Math.hypot(x, z) < 5000) continue;
    let ok = true;
    for (const s of sites) if (Math.hypot(s.x - x, s.z - z) < SAM_SPACING_M) ok = false; // main.py:57
    if (!ok) continue;
    const y = heightAt(x, z);
    if (y <= 0.5) continue; // not in the water
    const s = new SamSite(sites.length, x, y, z);
    s.reset(rand);
    sites.push(s);
    scene.add(s.mesh);
  }
}

// ---------- state ----------
let state: State = 'start';
let downFrames = 0;
let simTime = 0;
const prevPos = new Vector3();
const prevQuat = new Quaternion();
const drawPos = new Vector3();
const drawQuat = new Quaternion();
let wreckVisible = true;

const startScreen = document.getElementById('start') as HTMLDivElement;
const downScreen = document.getElementById('down') as HTMLDivElement;
const downTitle = document.getElementById('down-title') as HTMLDivElement;
const downHint = document.getElementById('down-hint') as HTMLDivElement;
const fpsNode = document.getElementById('fps') as HTMLDivElement;
document.getElementById('start-btn')!.addEventListener('click', () => input.queueStart());
document.getElementById('restart-btn')!.addEventListener('click', () => input.queueStart());

function resetWorld(): void {
  jet.reset(0, 0, 0);
  prevPos.copy(jet.pos);
  prevQuat.copy(jet.quat);
  missiles.items.forEach((m) => m.hide());
  smoke.clear();
  blasts.clear();
  placeSites();
  wreckVisible = true;
  jetModel.group.visible = true;
  camera.snap(jet.pos, jet.quat);
}

function startFlight(): void {
  resetWorld();
  state = 'flying';
  startScreen.style.display = 'none';
  downScreen.style.display = 'none';
  hud.show(true);
  input.setTouchVisible(true);
}

function jetDown(reason: string, onGround: boolean): void {
  state = 'down';
  downFrames = 0;
  jet.alive = false;
  if (onGround) {
    blasts.spawn(jet.pos.x, jet.pos.y, jet.pos.z, 60, 2.2);
    wreckVisible = false;
    jetModel.group.visible = false;
  } else {
    jet.crashing = true;
  }
  downTitle.textContent = reason;
  downHint.textContent = '';
  downScreen.style.display = 'flex';
  input.setTouchVisible(false);
}

// ---------- one 60 Hz physics frame ----------
let trailFrame = 0;
function fixedStep(): void {
  input.update(STEP);
  const wantsStart = input.consumeStart();
  if (state === 'start') {
    if (wantsStart) startFlight();
    else {
      jet.step(STEP, null); // idles in level flight behind the menu
      if (jet.pos.z < -30000) jet.reset(0, 0, 0);
    }
    return;
  }
  if (state === 'down') {
    downFrames++;
    if (downFrames >= JET_REJOIN_FRAMES) {
      downHint.textContent = input.touchMode ? 'Tap RESTART' : 'Press Enter (or A / Start on a controller) to restart';
      if (wantsStart) {
        startFlight();
        return;
      }
    }
  }

  prevPos.copy(jet.pos);
  prevQuat.copy(jet.quat);
  if (wreckVisible) {
    jet.step(STEP, state === 'flying' ? input : null);
    const ground = heightAt(jet.pos.x, jet.pos.z);
    if (jet.pos.y <= ground + 1.5) {
      jet.pos.y = ground + 1.5;
      if (state === 'flying') jetDown('CRASHED INTO THE GROUND', true);
      else {
        blasts.spawn(jet.pos.x, jet.pos.y, jet.pos.z, 60, 2.2);
        wreckVisible = false;
        jetModel.group.visible = false;
      }
    }
    if (jet.crashing && wreckVisible) smoke.emit(jet.pos.x, jet.pos.y, jet.pos.z, 4, 3, 14, 0.15);
  }

  // batteries
  const target = state === 'flying' ? jet.pos : null;
  let airborne = missiles.countActive();
  for (let i = 0; i < sites.length; i++) {
    const s = sites[i];
    if (s.step(target, airborne, rand)) {
      const m = missiles.acquire();
      if (m && target) {
        m.launch(s.x, s.y + 12, s.z, target, jet.vel, rand() < SAM_GUIDED_SHARE); // main.py:77
        airborne++;
      }
    }
  }

  // missiles
  trailFrame++;
  const items = missiles.items;
  for (let i = 0; i < items.length; i++) {
    const m = items[i];
    if (!m.active) continue;
    const end = m.step(state === 'flying' ? jet.pos : null, heightAt);
    if (end !== 'none') {
      blasts.spawn(m.pos.x, m.pos.y, m.pos.z, end === 'ground' ? 40 : 30, 1.2);
      m.hide();
      continue;
    }
    if (trailFrame % 2 === 0 && m.motorOn) smoke.emit(m.pos.x, m.pos.y, m.pos.z, 6, 2, 9, m.trailGrey);
    if (state === 'flying' && m.pos.distanceTo(jet.pos) < SAM_FUSE_M) {
      // main.py:2312-2323 proximity fuse: one SAM hit = shot down
      blasts.spawn(m.pos.x, m.pos.y, m.pos.z, 70, 1.6);
      m.hide();
      jet.hp = Math.max(0, jet.hp - SAM_DAMAGE);
      if (jet.hp === 0) jetDown('SHOT DOWN BY A SAM', false);
    }
  }

  smoke.update(STEP);
  blasts.update(STEP);
  simTime += STEP;
}

// ---------- frame loop ----------
let last = performance.now();
let acc = 0;
let fpsFrames = 0;
let fpsTime = 0;

function frame(now: number): void {
  requestAnimationFrame(frame);
  const dt = Math.min(0.25, (now - last) / 1000);
  last = now;
  acc += dt;
  let steps = 0;
  while (acc >= STEP && steps < MAX_STEPS) {
    fixedStep();
    acc -= STEP;
    steps++;
  }
  if (steps === MAX_STEPS) acc = 0;

  // draw between the last two physics states
  const a = acc / STEP;
  if (state === 'start') {
    drawPos.copy(jet.pos);
    drawQuat.copy(jet.quat);
  } else {
    drawPos.copy(prevPos).lerp(jet.pos, a);
    drawQuat.copy(prevQuat).slerp(jet.quat, a);
  }
  jetModel.group.position.copy(drawPos);
  jetModel.group.quaternion.copy(drawQuat);
  jetModel.setFlame(jet.throttle, jet.afterburner, simTime);
  for (const m of missiles.items) if (m.active) m.syncMesh();

  camera.update(dt, drawPos, drawQuat, jet.afterburner);
  const cp = camera.camera.position;
  sky.update(cp.x, cp.y, cp.z);
  terrain.follow(drawPos.x, drawPos.z);
  if (state !== 'start') hud.update(jet, heightAt(jet.pos.x, jet.pos.z), camera.camera, sites, missiles.items, window.innerWidth, window.innerHeight);

  renderer.render(scene, camera.camera);

  fpsFrames++;
  fpsTime += dt;
  if (fpsTime >= 0.5) {
    fpsNode.textContent = `${Math.round(fpsFrames / fpsTime)} FPS`;
    fpsFrames = 0;
    fpsTime = 0;
  }
}

window.addEventListener('resize', () => {
  renderer.setSize(window.innerWidth, window.innerHeight);
  camera.resize(window.innerWidth / window.innerHeight);
});

if (import.meta.env.DEV) (window as unknown as Record<string, unknown>).__jvm = {
    scene, renderer, camera: camera.camera, jet, sites, missiles,
    /** dev only: run n physics frames now (tests in a throttled browser window) */
    advance: (n: number) => { for (let i = 0; i < n; i++) fixedStep(); },
    state: () => state,
  };

resetWorld();
hud.show(false);
requestAnimationFrame(frame);

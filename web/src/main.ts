// Jet vs Missile - web 3D. Game loop: fixed 60 Hz physics step + one render per display frame.
import './style.css';
import { Color, DirectionalLight, HemisphereLight, Quaternion, Scene, Vector3, WebGLRenderer } from 'three';
import { RwrAudio } from './audio/RwrAudio';
import { ChaseCamera } from './camera/ChaseCamera';
import { JET_REJOIN_FRAMES, pxToX, pyToZ, SAM_DAMAGE, START_X_PX, START_Y_PX, STEP } from './config';
import { Input } from './core/Input';
import { JetModel } from './flight/JetModel';
import { JetPhysics } from './flight/JetPhysics';
import { Explosions } from './fx/Explosions';
import { Smoke } from './fx/Smoke';
import { ThreatSystem } from './threats/ThreatSystem';
import { Hud } from './ui/Hud';
import { Sky } from './world/Sky';
import { Terrain, heightAt } from './world/Terrain';

type State = 'start' | 'flying' | 'down';
const MAX_STEPS = 5; // physics steps per display frame at most (after a stall, the game slows rather than spirals)
const START_X = pxToX(START_X_PX); // main.py:1603 the lead jet starts here ...
const START_Z = pyToZ(START_Y_PX);
const START_HEADING = Math.PI / 2; // ... heading east (main.py:874 heading 0 = +x)

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
const rwr = new RwrAudio();
const jet = new JetPhysics();
const jetModel = new JetModel();
scene.add(jetModel.group);
const smoke = new Smoke();
scene.add(smoke.mesh);
const blasts = new Explosions(scene);
const threats = new ThreatSystem(scene);
threats.onBlast = (x, y, z, r, life) => blasts.spawn(x, y, z, r, life);

// ---------- state ----------
let state: State = 'start';
let downFrames = 0;
let simTime = 0;
let launchesSinceFrame = 0;
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
  jet.reset(START_X, START_Z, START_HEADING);
  prevPos.copy(jet.pos);
  prevQuat.copy(jet.quat);
  threats.reset((Date.now() & 0x7fffffff) | 1);
  smoke.clear();
  blasts.clear();
  hud.clearLog();
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
  const wantsFlare = input.consumeFlare();
  const wantsEcm = input.consumeEcm();
  if (state === 'start') {
    if (wantsStart) startFlight();
    else {
      jet.step(STEP, null); // idles in level flight behind the menu
      if (jet.pos.x > START_X + 30000) jet.reset(START_X, START_Z, START_HEADING);
      threats.step(null, false);
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
  const flying = state === 'flying';
  if (wreckVisible) {
    jet.step(STEP, flying ? input : null);
    const ground = heightAt(jet.pos.x, jet.pos.z);
    if (jet.pos.y <= ground + 1.5) {
      jet.pos.y = ground + 1.5;
      if (flying) jetDown('CRASHED INTO THE GROUND', true);
      else {
        blasts.spawn(jet.pos.x, jet.pos.y, jet.pos.z, 60, 2.2);
        wreckVisible = false;
        jetModel.group.visible = false;
      }
    }
    if (jet.crashing && wreckVisible) smoke.emit(jet.pos.x, jet.pos.y, jet.pos.z, 4, 3, 14, 0.15);
  }

  // countermeasures (main.py:1955-1993 messages)
  if (state === 'flying') {
    const cm = threats.cm;
    if (wantsFlare) {
      if (cm.fireFlares(jet.pos, jet.vel)) hud.say('FLARES');
      else hud.say(`FLARES RELOADING ${(cm.flareCd / 60).toFixed(1)} s`);
    }
    if (wantsEcm) {
      const broken = cm.fireEcm(jet.pos, threats.missiles.items, threats.rand);
      if (broken < 0) hud.say(`ECM RELOADING ${(cm.ecmCd / 60).toFixed(1)} s`);
      else hud.say(broken ? `ECM - ${broken} LOCK BROKEN` : 'ECM');
    }
  }

  threats.step(state === 'flying' ? jet : null, state === 'flying');
  launchesSinceFrame += threats.launchedThisFrame;
  if (threats.decoyedThisFrame > 0) hud.say(`FLARES - ${threats.decoyedThisFrame} SAM DECOYED`); // main.py:1993
  if (state === 'flying' && threats.hitThisFrame) {
    // main.py:2312-2323 proximity fuse: one SAM hit = shot down
    jet.hp = Math.max(0, jet.hp - SAM_DAMAGE);
    if (jet.hp === 0) jetDown('SHOT DOWN BY A SAM', false);
  }

  // trails: missiles while the motor burns, flares while hot
  trailFrame++;
  if (trailFrame % 2 === 0) {
    const items = threats.missiles.items;
    for (let i = 0; i < items.length; i++) {
      const m = items[i];
      if (m.active && m.motorOn) smoke.emit(m.pos.x, m.pos.y, m.pos.z, 6, 2, 9, m.trailGrey);
    }
    const fl = threats.cm.flares.items;
    for (let i = 0; i < fl.length; i++) {
      const f = fl[i];
      if (f.active && f.heat > 0.2 && trailFrame % 4 === 0) smoke.emit(f.pos.x, f.pos.y, f.pos.z, 2.5, 1.5, 5, 0.95);
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
  threats.syncMeshes();

  camera.update(dt, drawPos, drawQuat, jet.afterburner);
  const cp = camera.camera.position;
  sky.update(cp.x, cp.y, cp.z);
  terrain.follow(drawPos.x, drawPos.z);
  if (state !== 'start') hud.update(jet, heightAt(jet.pos.x, jet.pos.z), camera.camera, threats, window.innerWidth, window.innerHeight);
  rwr.update(state === 'flying' ? threats.painting : 0, Hud.lockCount(threats), launchesSinceFrame, state === 'flying');
  launchesSinceFrame = 0;

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

if (import.meta.env.DEV)
  (window as unknown as Record<string, unknown>).__jvm = {
    scene,
    renderer,
    camera: camera.camera,
    jet,
    threats,
    /** dev only: run n physics frames now (tests in a throttled browser window) */
    advance: (n: number) => {
      for (let i = 0; i < n; i++) fixedStep();
    },
    state: () => state,
  };

resetWorld();
hud.show(false);
requestAnimationFrame(frame);

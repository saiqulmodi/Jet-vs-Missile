// Jet vs Missile - web 3D. Game loop: fixed 60 Hz physics step + one render per display frame.
import './style.css';
import { Color, DirectionalLight, HemisphereLight, Quaternion, Scene, Vector3, WebGLRenderer } from 'three';
import { RwrAudio } from './audio/RwrAudio';
import { SFX } from './audio/Sfx';
import { ChaseCamera } from './camera/ChaseCamera';
import { Showcase } from './camera/Showcase';
import { JET_REJOIN_FRAMES, pxToX, pyToZ, SAM_DAMAGE, START_X_PX, START_Y_PX, STEP } from './config';
import { Input } from './core/Input';
import { JetModel } from './flight/JetModel';
import { JetPhysics } from './flight/JetPhysics';
import { Contrail } from './fx/Contrail';
import { Explosions } from './fx/Explosions';
import { PostFx } from './fx/PostFx';
import { Smoke } from './fx/Smoke';
import { ThreatSystem } from './threats/ThreatSystem';
import { Hud } from './ui/Hud';
import { Intro } from './ui/Intro';
import { Clouds } from './world/Clouds';
import { GroundWar } from './world/GroundWar';
import { makeMapTextures } from './world/MapTexture';
import { Sky } from './world/Sky';
import { Terrain, heightAt } from './world/Terrain';
import { addWorldProps } from './world/WorldProps';

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
const hemi = new HemisphereLight(0xdfeaff, 0x4a5a3a, 1.1);
scene.add(hemi);
const sun = new DirectionalLight(0xfff4e0, 2.2);
sun.position.copy(sky.sunDir);
scene.add(sun);

const maps = makeMapTextures();
const terrain = new Terrain(maps.day, maps.night);
terrain.material.uniforms.uSunDir.value.copy(sky.sunDir);
scene.add(terrain.mesh);
addWorldProps(scene);
const clouds = new Clouds();
scene.add(clouds.mesh);
const groundWar = new GroundWar(scene);

const camera = new ChaseCamera(window.innerWidth / window.innerHeight);
const post = new PostFx(renderer, scene, camera.camera);
const input = new Input(app);
const hud = new Hud(app);
const rwr = new RwrAudio();
const jet = new JetPhysics();
const jetModel = new JetModel();
scene.add(jetModel.group);
const contrail = new Contrail();
scene.add(contrail.mesh);
const smoke = new Smoke();
scene.add(smoke.mesh);
const blasts = new Explosions(scene);
const threats = new ThreatSystem(scene);
threats.onBlast = (x, y, z, r, life) => blasts.spawn(x, y, z, r, life);
const blast = (x: number, y: number, z: number, r: number, life: number): void => blasts.spawn(x, y, z, r, life);
const camDist = (p: Vector3): number => p.distanceTo(camera.camera.position);

// ---------- day / night (main.py:1717, 2001: T); the showcase can show night for one shot ----------
let night = false;
let demoNight = false;
const tu = terrain.material.uniforms;
const isNight = (): boolean => night || demoNight;
function applyNight(): void {
  if (isNight()) {
    // moonlight: the ground darkened to main.py's NIGHT_SHADE (66, 82, 100), every light added on top
    sun.color.set(0x8090c0);
    sun.intensity = 0.3;
    hemi.intensity = 0.18;
    tu.uSunColor.value.setRGB(0.035, 0.05, 0.08);
    tu.uSkyLight.value.setRGB(0.03, 0.045, 0.07);
    tu.uGroundLight.value.setRGB(0.01, 0.012, 0.018);
    tu.uNightMix.value = 1;
  } else {
    sun.color.set(0xfff4e0);
    sun.intensity = 2.2;
    hemi.intensity = 1.1;
    tu.uSunColor.value.setRGB(1, 0.95, 0.85).multiplyScalar(1.6);
    tu.uSkyLight.value.setRGB(0.55, 0.62, 0.75);
    tu.uGroundLight.value.setRGB(0.2, 0.22, 0.16);
    tu.uNightMix.value = 0;
  }
  post.setNight(isNight());
}

// ---------- state ----------
let state: State = 'start';
let downFrames = 0;
let simTime = 0;
let frameNo = 0;
let launchesSinceFrame = 0;
const prevPos = new Vector3();
const prevQuat = new Quaternion();
const drawPos = new Vector3();
const drawQuat = new Quaternion();
let wreckVisible = true;

const downScreen = document.getElementById('down') as HTMLDivElement;
const downTitle = document.getElementById('down-title') as HTMLDivElement;
const downHint = document.getElementById('down-hint') as HTMLDivElement;
const fpsNode = document.getElementById('fps') as HTMLDivElement;
document.getElementById('restart-btn')!.addEventListener('click', () => input.queueStart());
const intro = new Intro(() => input.queueStart());

const showcase = new Showcase({
  jet,
  threats,
  start: { x: START_X, z: START_Z, heading: START_HEADING },
  setDemoNight: (on) => {
    if (demoNight === on) return;
    demoNight = on;
    applyNight();
  },
  clearFx: () => {
    smoke.clear();
    blasts.clear();
    contrail.clear();
  },
  snapChase: () => camera.snap(jet.pos, jet.quat),
  snapTerrain: (x, z) => terrain.snapTo(x, z),
});

function resetWorld(): void {
  jet.reset(START_X, START_Z, START_HEADING);
  prevPos.copy(jet.pos);
  prevQuat.copy(jet.quat);
  threats.reset((Date.now() & 0x7fffffff) | 1);
  smoke.clear();
  blasts.clear();
  contrail.clear();
  hud.clearLog();
  wreckVisible = true;
  jetModel.group.visible = true;
  terrain.snapTo(jet.pos.x, jet.pos.z);
  camera.snap(jet.pos, jet.quat);
}

function startFlight(): void {
  showcase.end();
  intro.hide();
  resetWorld();
  state = 'flying';
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
    SFX.play('explode'); // main.py:2337
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
function fixedStep(): void {
  frameNo++;
  input.update(STEP);
  const wantsStart = input.consumeStart();
  const wantsFlare = input.consumeFlare();
  const wantsEcm = input.consumeEcm();
  if (input.consumeNight()) {
    night = !night;
    applyNight();
    if (state === 'flying') hud.say(night ? 'NIGHT VIEW' : 'DAY VIEW');
  }
  groundWar.step(jet.pos.x, jet.pos.z, blast);

  if (state === 'start') {
    if (wantsStart) {
      startFlight();
      return;
    }
    // the showcase behind the logo
    showcase.step();
    jet.step(STEP, null);
    contrail.record(jet.pos, frameNo);
    threats.step(showcase.tracking ? jet : null, false);
  } else {
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
          SFX.play('explode', camDist(jet.pos)); // main.py:2336-2337 the wreck hits the ground
          wreckVisible = false;
          jetModel.group.visible = false;
        }
      }
      if (jet.crashing && wreckVisible) smoke.emit(jet.pos.x, jet.pos.y, jet.pos.z, 4, 3, 14, 0.15);
      if (flying) contrail.record(jet.pos, frameNo);
    }

    // countermeasures (main.py:1955-1993 messages and sounds)
    if (flying) {
      const cm = threats.cm;
      if (wantsFlare) {
        if (cm.fireFlares(jet.pos, jet.vel)) {
          hud.say('FLARES');
          SFX.play('flare'); // main.py:1978
        } else hud.say(`FLARES RELOADING ${(cm.flareCd / 60).toFixed(1)} s`);
      }
      if (wantsEcm) {
        const broken = cm.fireEcm(jet.pos, threats.missiles.items, threats.rand);
        if (broken < 0) hud.say(`ECM RELOADING ${(cm.ecmCd / 60).toFixed(1)} s`);
        else {
          hud.say(broken ? `ECM - ${broken} LOCK BROKEN` : 'ECM');
          SFX.play('ignite'); // main.py:1961
        }
      }
    }

    threats.step(flying ? jet : null, flying);
    launchesSinceFrame += threats.launchedThisFrame;
    if (flying && threats.launchedThisFrame > 0) SFX.play('ignite', 2000); // main.py:1857 launch
    if (threats.decoyedThisFrame > 0) hud.say(`FLARES - ${threats.decoyedThisFrame} SAM DECOYED`); // main.py:1993
    if (flying && threats.hitThisFrame) {
      // main.py:2312-2323 proximity fuse: one SAM hit = shot down
      SFX.play('explode'); // main.py:2317
      jet.hp = Math.max(0, jet.hp - SAM_DAMAGE);
      if (jet.hp === 0) jetDown('SHOT DOWN BY A SAM', false);
    }
  }

  // trails: missiles while the motor burns, flares while hot
  if (frameNo % 2 === 0) {
    const items = threats.missiles.items;
    for (let i = 0; i < items.length; i++) {
      const m = items[i];
      if (m.active && m.motorOn) smoke.emit(m.pos.x, m.pos.y, m.pos.z, 6, 2, 9, m.trailGrey);
    }
    const fl = threats.cm.flares.items;
    for (let i = 0; i < fl.length; i++) {
      const f = fl[i];
      if (f.active && f.heat > 0.2 && frameNo % 4 === 0) smoke.emit(f.pos.x, f.pos.y, f.pos.z, 2.5, 1.5, 5, 0.95);
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
  jetModel.setNight(isNight(), frameNo);
  threats.syncMeshes(isNight());
  groundWar.sync(isNight());

  if (!(state === 'start' && showcase.camera(camera.camera, dt))) camera.update(dt, drawPos, drawQuat, jet.afterburner);
  const cp = camera.camera.position;
  const nightMix = isNight() ? 1 : 0;
  sky.update(cp.x, cp.y, cp.z, nightMix);
  clouds.update(simTime, nightMix);
  contrail.update(cp, drawPos, frameNo, nightMix);
  terrain.follow(state === 'start' ? cp.x : drawPos.x, state === 'start' ? cp.z : drawPos.z);
  if (state !== 'start') hud.update(jet, heightAt(jet.pos.x, jet.pos.z), camera.camera, threats, window.innerWidth, window.innerHeight);
  rwr.update(state === 'flying' ? threats.painting : 0, state === 'flying' ? Hud.lockCount(threats) : 0, launchesSinceFrame, state === 'flying');
  launchesSinceFrame = 0;

  post.render();

  fpsFrames++;
  fpsTime += dt;
  if (fpsTime >= 0.5) {
    fpsNode.textContent = state === 'start' ? '' : `${Math.round(fpsFrames / fpsTime)} FPS`; // the intro shows only the logo
    fpsFrames = 0;
    fpsTime = 0;
  }
}

window.addEventListener('resize', () => {
  renderer.setSize(window.innerWidth, window.innerHeight);
  post.resize(window.innerWidth, window.innerHeight);
  camera.resize(window.innerWidth / window.innerHeight);
});

if (import.meta.env.DEV)
  (window as unknown as Record<string, unknown>).__jvm = {
    scene,
    renderer,
    camera: camera.camera,
    jet,
    threats,
    post,
    /** dev only: run n physics frames now (tests in a throttled browser window) */
    advance: (n: number) => {
      for (let i = 0; i < n; i++) fixedStep();
    },
    state: () => state,
    setNight: (on: boolean) => {
      night = on;
      applyNight();
    },
  };

applyNight();
resetWorld();
hud.show(false);
showcase.begin();
requestAnimationFrame(frame);

// SAM missile, after main.py's SAMMissile (main.py:1054-1123). One SAM type, launched either way, at random:
//  - guided: simple pursuit, the nose turns toward the jet at a capped rate every frame, 40 s of motor.
//  - unguided: aimed at where the jet will be if it flies on as it is (main.py:1072-1078), flies straight,
//    and when the motor burns out it arcs over and falls (main.py:1107-1112). Turning away escapes it.
// Speed ramps up over the boost/climb phase (main.py:1106).
import { CylinderGeometry, Group, Mesh, MeshBasicMaterial, MeshLambertMaterial, Quaternion, SphereGeometry, Vector3 } from 'three';
import {
  CRUISE_ALT_FT,
  FT,
  SAM_BOOST_START,
  SAM_CLIMB_FRAMES,
  SAM_CLIMB_MIN_FRAMES,
  SAM_LIFE_FRAMES,
  SAM_SPEED_MPS,
  SAM_TURN_PER_FRAME,
  STEP,
  UNGUIDED_MOTOR_FRAMES,
} from '../config';
import type { Poolable } from '../core/Pool';
import { airDensity } from '../flight/JetPhysics';

const RHO0 = 1.225;
const G0 = 9.81;
/** Seeker gimbal: a jet more than 50 deg off the missile's nose is lost for good (the missile flies on blind). */
const SEEKER_GIMBAL = (50 * Math.PI) / 180;
/** Fins need air: the turn cap shrinks with air density, but never below this share of main.py's value. */
const MIN_TURN_SHARE = 0.25;
const COAST_DRAG = 0.996; // main.py:1111, unguided round loses speed every frame after burnout
const FALL_MAX = 400; // m/s, terminal fall speed of a spent round (main.py:1109 caps its fall too)

const _to = new Vector3();
const _axis = new Vector3();
const _aim = new Vector3();
const _fwd = new Vector3(0, 1, 0);
const _q = new Quaternion();

const bodyGeo = new CylinderGeometry(0.25, 0.25, 5.5, 8);
const flameGeo = new SphereGeometry(0.7, 8, 6);
const guidedMat = new MeshLambertMaterial({ color: 0xebebe6 }); // main.py:1129 body colours
const unguidedMat = new MeshLambertMaterial({ color: 0xc8c8a8 });
const flameMat = new MeshBasicMaterial({ color: 0xffa040 });

export type MissileEnd = 'none' | 'expired' | 'ground';

export class Missile implements Poolable {
  active = false;
  guided = true;
  readonly pos = new Vector3();
  readonly dir = new Vector3(0, 1, 0);
  /** unguided rounds after burnout: ballistic velocity */
  readonly vel = new Vector3();
  readonly mesh = new Group();
  age = 0; // frames
  speed = 0;
  climbFrames = SAM_CLIMB_MIN_FRAMES;
  burnout = 0; // frames, unguided only
  /** true once the seeker has lost the jet */
  lockLost = false;
  private body: Mesh;
  private flame: Mesh;

  constructor() {
    this.body = new Mesh(bodyGeo, guidedMat);
    this.mesh.add(this.body);
    this.flame = new Mesh(flameGeo, flameMat);
    this.flame.position.y = -3;
    this.flame.scale.set(1, 2.2, 1);
    this.mesh.add(this.flame);
    this.mesh.visible = false;
  }

  /** Trail grey level: main.py:1082 (guided 236/232/224, unguided 206/196/176). */
  get trailGrey(): number {
    return this.guided ? 0.92 : 0.78;
  }

  get motorOn(): boolean {
    return this.guided || this.age <= this.burnout;
  }

  launch(x: number, y: number, z: number, target: Vector3, targetVel: Vector3, guided: boolean): void {
    this.guided = guided;
    this.body.material = guided ? guidedMat : unguidedMat;
    this.pos.set(x, y + 3, z);
    this.age = 0;
    this.speed = SAM_SPEED_MPS * SAM_BOOST_START;
    // main.py:1069 boost/climb time scales with the target's altitude, at least 90 frames
    this.climbFrames = Math.max(SAM_CLIMB_MIN_FRAMES, (SAM_CLIMB_FRAMES * (target.y / FT)) / CRUISE_ALT_FT);
    this.lockLost = false;
    if (guided) {
      // leaves the rail steeply, leaning toward the jet
      _to.copy(target).sub(this.pos);
      _to.y = 0;
      _to.normalize();
      this.dir.set(_to.x * 0.35, 1, _to.z * 0.35).normalize();
    } else {
      // main.py:1073-1078 aim off: where the jet will be when the round gets there (it flies on as it is now)
      let t = this.climbFrames;
      for (let i = 0; i < 8; i++) {
        _aim.copy(target).addScaledVector(targetVel, t * STEP);
        t = this.framesToCover(_aim.distanceTo(this.pos));
      }
      this.dir.copy(_aim).sub(this.pos).normalize();
      // main.py:1079 motor = climb to the jet's height + 5 s; in 3D the climb is the flight to the aim point
      this.burnout = t + UNGUIDED_MOTOR_FRAMES;
    }
    this.mesh.visible = true;
    this.flame.visible = true;
    this.syncMesh();
  }

  /** main.py:1087-1095 frames the motor needs to fly `dist`: speed ramps 35% -> 100% over the climb, then holds. */
  private framesToCover(dist: number): number {
    const c = this.climbFrames;
    const v = SAM_SPEED_MPS * STEP;
    const climbDist = v * (0.35 * c + (0.65 * c) / 2);
    if (dist >= climbDist) return c + (dist - climbDist) / v;
    const a = (0.65 * v) / (2 * c);
    const b = 0.35 * v;
    return (-b + Math.sqrt(b * b + 4 * a * dist)) / (2 * a);
  }

  /** One 60 Hz frame. Returns why it ended, if it did. */
  step(target: Vector3 | null, groundAt: (x: number, z: number) => number): MissileEnd {
    this.age++;
    if (this.guided && this.age > SAM_LIFE_FRAMES) return 'expired'; // main.py:1099, 40 s of motor then self-destructs

    if (!this.guided && this.age > this.burnout) {
      // motor out: a projectile now, losing speed and falling (main.py:1107-1112)
      if (this.age === this.burnout + 1) this.vel.copy(this.dir).multiplyScalar(this.speed);
      // main.py:1111 speed loss applies to the forward motion; gravity pulls it down (main.py:1109 falls faster and faster)
      this.vel.x *= COAST_DRAG;
      this.vel.z *= COAST_DRAG;
      this.vel.y = Math.max(-FALL_MAX, this.vel.y - G0 * STEP);
      this.speed = this.vel.length();
      this.dir.copy(this.vel).divideScalar(Math.max(1e-3, this.speed));
      this.flame.visible = false;
    } else {
      const climb = Math.min(1, this.age / this.climbFrames);
      this.speed = SAM_SPEED_MPS * (SAM_BOOST_START + (1 - SAM_BOOST_START) * climb); // main.py:1106
    }

    if (this.guided && target && !this.lockLost) {
      _to.copy(target).sub(this.pos).normalize();
      const cos = Math.min(1, Math.max(-1, this.dir.dot(_to)));
      const ang = Math.acos(cos);
      // main.py:1120 turn cap per frame, scaled by air density: thin air at 35,000 ft = wide turns
      const turn = SAM_TURN_PER_FRAME * Math.max(MIN_TURN_SHARE, airDensity(this.pos.y) / RHO0);
      if (this.age > this.climbFrames && ang > SEEKER_GIMBAL) {
        this.lockLost = true; // overshot: the jet broke out of the seeker's view
      } else if (ang <= turn) {
        this.dir.copy(_to);
      } else {
        _axis.crossVectors(this.dir, _to);
        if (_axis.lengthSq() < 1e-10) _axis.set(1, 0, 0);
        _axis.normalize();
        this.dir.applyAxisAngle(_axis, turn);
      }
    }
    this.pos.addScaledVector(this.dir, this.speed * STEP);
    if (this.age > 30 && this.pos.y <= groundAt(this.pos.x, this.pos.z)) return 'ground'; // main.py:1112 landed
    return 'none';
  }

  syncMesh(): void {
    this.mesh.position.copy(this.pos);
    _q.setFromUnitVectors(_fwd, this.dir);
    this.mesh.quaternion.copy(_q);
  }

  hide(): void {
    this.active = false;
    this.mesh.visible = false;
  }
}

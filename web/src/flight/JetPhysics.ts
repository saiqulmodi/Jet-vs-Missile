// Energy-model flight physics for the jet.
//   Lift = CL(alpha) q S, Drag = (CD0 + k CL^2) q S, q = 1/2 rho(h) v^2
//   rho falls exponentially with altitude: controls are crisp low and sluggish high.
//   The fly-by-wire stick commands load factor (G); hard turns raise CL, so induced drag bleeds speed
//   unless you dive or light the afterburner. Too little speed for the lift asked = stall.
import { Matrix4, Quaternion, Vector3 } from 'three';
import { CRASH_SPIN, CRUISE_ALT_FT, FT, JET_CRUISE_MPS, JET_HP, LEVEL_MULT, PLAYER_EDGE } from '../config';
import type { Input } from '../core/Input';

const G0 = 9.81;
const RHO0 = 1.225; // kg/m^3 at sea level
const H_SCALE = 8500; // m, density scale height
const MASS = 10000; // kg
const WING_S = 38; // m^2
const CD0 = 0.022;
const K_IND = 0.12; // induced drag factor
const CL_ALPHA = 5.0; // per radian
const ALPHA_STALL = 0.28; // rad (16 deg): CL max = 1.4
const ALPHA_LIMIT = 0.27; // rad: the fly-by-wire AoA limiter keeps the wing just under the stall
const ALPHA_DEEP = 0.42; // rad (24 deg): where the wing goes when the jet is too slow to hold 1 G
const ALPHA_MIN = -0.2;
const G_MAX = 9;
const G_MIN = -3;
const MIL_THRUST0 = 45000; // N at sea level, full military power (x PLAYER_EDGE at use)
const AB_THRUST0 = 160000; // (x PLAYER_EDGE at use) N extra with afterburner: ~1 G of push at 35,000 ft, top ~Mach 2.3 (escape speed)
const THRUST_LAPSE = 0.5; // thrust ~ (rho / rho0)^0.5
const Q_REF = 20000; // Pa: full control authority at and above this dynamic pressure
const PITCH_SLEW = 0.9; // rad/s alpha change at full authority (x PLAYER_EDGE at use)
const ROLL_RATE = 3.6; // rad/s at full authority (x PLAYER_EDGE at use)
const YAW_RATE = 0.22; // rad/s velocity turn from the rudder at full authority
const THROTTLE_RATE = 0.5; // per second

/** Throttle that holds the main.py level 1 cruise speed in level flight at 35,000 ft. */
const START_THROTTLE = 0.49; // divided by PLAYER_EDGE at reset: the same 490 kt cruise with the stronger engine

const _vhat = new Vector3();
const _right = new Vector3();
const _nose = new Vector3();
const _bodyUp = new Vector3();
const _acc = new Vector3();
const _m = new Matrix4();

export const airDensity = (altM: number): number => RHO0 * Math.exp(-Math.max(0, altM) / H_SCALE);
export const speedOfSound = (altM: number): number => Math.max(295, 340.3 - 0.0039 * Math.max(0, altM));

export class JetPhysics {
  readonly pos = new Vector3();
  readonly vel = new Vector3();
  /** lift axis: unit vector perpendicular to the velocity (the wings' "up" around the flight path) */
  readonly liftUp = new Vector3(0, 1, 0);
  /** body orientation for drawing */
  readonly quat = new Quaternion();
  readonly nose = new Vector3(0, 0, -1);
  readonly bodyUp = new Vector3(0, 1, 0);

  alpha = 0;
  throttle = START_THROTTLE;
  afterburner = false;
  gLoad = 1;
  stalled = false;
  mach = 0;
  hp = JET_HP;
  alive = true;
  /** true while a shot-down wreck is falling */
  crashing = false;
  /** ft per frame the wreck is falling (main.py:1206) */
  private crashFall = 20;

  reset(x: number, z: number, headingRad: number): void {
    this.pos.set(x, CRUISE_ALT_FT * FT, z); // start airborne at 35,000 ft (main.py:882)
    this.vel.set(Math.sin(headingRad), 0, -Math.cos(headingRad)).multiplyScalar(JET_CRUISE_MPS * LEVEL_MULT); // main.py:190 the level's speed
    this.liftUp.set(0, 1, 0);
    this.alpha = 0.03;
    this.throttle = START_THROTTLE / PLAYER_EDGE;
    this.afterburner = false;
    this.gLoad = 1;
    this.stalled = false;
    this.hp = JET_HP;
    this.alive = true;
    this.crashing = false;
    this.crashFall = 20;
    this.updateBody();
  }

  /** A shot-down wreck (main.py:1209-1216): keeps flying on, 0.5% slower a frame, spins, falls faster and faster. */
  stepCrash(dt: number): void {
    this.vel.x *= 0.995;
    this.vel.z *= 0.995;
    this.crashFall = Math.min(200, this.crashFall + 1.2); // main.py:1215
    this.vel.y = -(this.crashFall * FT) / dt;
    this.pos.x += this.vel.x * dt;
    this.pos.z += this.vel.z * dt;
    this.pos.y -= this.crashFall * FT;
    const v = Math.max(1, this.vel.length());
    _vhat.copy(this.vel).divideScalar(v);
    this.liftUp.applyAxisAngle(_vhat, CRASH_SPIN); // main.py:1214
    this.liftUp.addScaledVector(_vhat, -this.liftUp.dot(_vhat)).normalize();
    this.alpha = 0;
    this.afterburner = false;
    this.throttle = 0;
    this.gLoad = 0;
    this.updateBody();
  }

  get speed(): number {
    return this.vel.length();
  }

  /** compass heading 0..360, 0 = north (-Z) */
  get headingDeg(): number {
    const h = (Math.atan2(this.vel.x, -this.vel.z) * 180) / Math.PI;
    return (h + 360) % 360;
  }

  step(dt: number, input: Input | null): void {
    const v = Math.max(1, this.vel.length());
    _vhat.copy(this.vel).divideScalar(v);
    const h = this.pos.y;
    const rho = airDensity(h);
    const q = 0.5 * rho * v * v;
    const auth = Math.min(1, q / Q_REF);

    let pitchIn = 0;
    let rollIn = 0;
    let yawIn = 0;
    if (input && !this.crashing) {
      pitchIn = input.pitch;
      rollIn = input.roll;
      yawIn = input.yaw;
      this.throttle = Math.min(1, Math.max(0, this.throttle + input.throttle * THROTTLE_RATE * dt));
      this.afterburner = input.afterburner;
    }
    if (this.crashing) {
      this.throttle = 0;
      this.afterburner = false;
    }

    // --- pitch: the stick asks for a load factor; the wing gives the alpha (CL) that makes it ---
    let alphaCmd = 0;
    if (!this.crashing) {
      const nCmd = pitchIn >= 0 ? 1 + pitchIn * (G_MAX - 1) : 1 + pitchIn * (1 - G_MIN);
      const clReq = (nCmd * MASS * G0) / Math.max(1, q * WING_S);
      // too slow for 1 G even at max lift = stall: the limiter cannot help, the wing goes past the stall
      const slow = MASS * G0 > CL_ALPHA * ALPHA_STALL * q * WING_S;
      const top = slow && pitchIn > 0.2 ? ALPHA_DEEP : ALPHA_LIMIT;
      alphaCmd = Math.min(top, Math.max(ALPHA_MIN, clReq / CL_ALPHA));
    }
    const slew = PITCH_SLEW * PLAYER_EDGE * Math.max(0.25, auth) * dt;
    this.alpha += Math.max(-slew, Math.min(slew, alphaCmd - this.alpha));

    const cl = liftCoefficient(this.alpha);
    let lift = cl * q * WING_S;
    const liftLimit = G_MAX * MASS * G0;
    if (lift > liftLimit) lift = liftLimit;
    if (lift < G_MIN * MASS * G0) lift = G_MIN * MASS * G0;
    this.stalled = Math.abs(this.alpha) > ALPHA_STALL;

    // --- drag: parasite + induced + wave drag near Mach 1 + extra when stalled ---
    const a = speedOfSound(h);
    this.mach = v / a;
    const wave = this.mach > 0.9 ? 0.015 * Math.min(1, (this.mach - 0.9) / 0.25) : 0;
    let cd = CD0 + wave + K_IND * cl * cl;
    if (this.stalled) cd += 0.25 * (Math.abs(this.alpha) - ALPHA_STALL) * 4;
    const drag = cd * q * WING_S;

    // --- thrust ---
    const lapse = Math.pow(rho / RHO0, THRUST_LAPSE);
    const thrust = (MIL_THRUST0 * (this.afterburner ? 1 : this.throttle) + (this.afterburner ? AB_THRUST0 : 0)) * lapse * PLAYER_EDGE * LEVEL_MULT * LEVEL_MULT; // level: drag grows with v^2, so thrust x m^2 = speeds x m

    // --- roll around the flight path, rudder yaws the flight path ---
    if (this.crashing) {
      this.liftUp.applyAxisAngle(_vhat, -CRASH_SPIN * 60 * dt); // main.py:72 wreck spin, per frame -> per second
    } else {
      this.liftUp.applyAxisAngle(_vhat, rollIn * ROLL_RATE * PLAYER_EDGE * Math.max(0.3, auth) * dt);
    }

    _nose.copy(_vhat).multiplyScalar(Math.cos(this.alpha)).addScaledVector(this.liftUp, Math.sin(this.alpha));
    _acc.set(0, -G0, 0);
    _acc.addScaledVector(this.liftUp, lift / MASS);
    _acc.addScaledVector(_vhat, -drag / MASS);
    _acc.addScaledVector(_nose, thrust / MASS);
    this.vel.addScaledVector(_acc, dt);
    if (yawIn !== 0 && !this.crashing) this.vel.applyAxisAngle(this.liftUp, -yawIn * YAW_RATE * Math.max(0.3, auth) * dt);
    this.pos.addScaledVector(this.vel, dt);

    this.gLoad = lift / (MASS * G0);

    // keep the lift axis perpendicular to the new flight path (parallel transport)
    const nv = Math.max(1, this.vel.length());
    _vhat.copy(this.vel).divideScalar(nv);
    this.liftUp.addScaledVector(_vhat, -this.liftUp.dot(_vhat));
    if (this.liftUp.lengthSq() < 1e-8) this.liftUp.set(0, 1, 0);
    this.liftUp.normalize();
    this.updateBody();
  }

  private updateBody(): void {
    const v = Math.max(1, this.vel.length());
    _vhat.copy(this.vel).divideScalar(v);
    const ca = Math.cos(this.alpha);
    const sa = Math.sin(this.alpha);
    this.nose.copy(_vhat).multiplyScalar(ca).addScaledVector(this.liftUp, sa);
    this.bodyUp.copy(this.liftUp).multiplyScalar(ca).addScaledVector(_vhat, -sa);
    _right.crossVectors(this.nose, this.bodyUp).normalize();
    _bodyUp.copy(this.bodyUp);
    // three.js objects look down -Z: columns are right, up, -forward
    _m.makeBasis(_right, _bodyUp, _nose.copy(this.nose).negate());
    this.quat.setFromRotationMatrix(_m);
  }
}

function liftCoefficient(alpha: number): number {
  const s = Math.sign(alpha);
  const a = Math.abs(alpha);
  if (a <= ALPHA_STALL) return CL_ALPHA * alpha;
  const clMax = CL_ALPHA * ALPHA_STALL;
  return s * Math.max(0.7, clMax - (a - ALPHA_STALL) * 3.5); // lift falls away past the stall
}

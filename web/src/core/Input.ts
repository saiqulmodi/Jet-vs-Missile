// Keyboard + Gamepad API + on-screen touch stick, merged into one set of flight controls.

const STICK_RADIUS = 80; // main.py:150, touch stick radius in px
const STICK_DEADZONE = 0.18; // main.py:151
const PAD_DEADZONE = 0.15; // analog flight needs a smaller dead zone than main.py's d-pad style 0.35 (main.py:114)
const KEY_RAMP = 4; // keyboard pitch/roll/yaw move toward full deflection at this rate per second

const PREVENT = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space', 'Tab']);

const clamp1 = (v: number): number => (v < -1 ? -1 : v > 1 ? 1 : v);
const dead = (v: number, dz: number): number => {
  const a = Math.abs(v);
  if (a < dz) return 0;
  return Math.sign(v) * ((a - dz) / (1 - dz));
};

export class Input {
  /** -1 push (nose down) .. +1 pull (nose up) */
  pitch = 0;
  /** -1 roll left .. +1 roll right */
  roll = 0;
  /** -1 yaw left .. +1 yaw right */
  yaw = 0;
  /** -1 .. +1 throttle change request */
  throttle = 0;
  afterburner = false;
  /** true when the controls in use are a touch screen */
  touchMode = false;

  private keys = new Set<string>();
  private kPitch = 0;
  private kRoll = 0;
  private kYaw = 0;
  private startQueued = false;
  private flareQueued = false;
  private ecmQueued = false;
  private padFlareWasDown = false;
  private padEcmWasDown = false;
  private padConnected = false;
  private padStartWasDown = false;

  // touch state
  private stickId = -1;
  private stickCx = 0;
  private stickCy = 0;
  private stickX = 0;
  private stickY = 0;
  private touchThrUp = false;
  private touchThrDown = false;
  private touchAb = false;
  private stickBase!: HTMLDivElement;
  private stickKnob!: HTMLDivElement;
  private touchLayer!: HTMLDivElement;

  constructor(root: HTMLElement) {
    window.addEventListener('keydown', (e) => {
      if (PREVENT.has(e.code)) e.preventDefault();
      if (!e.repeat && (e.code === 'Enter' || e.code === 'NumpadEnter')) this.startQueued = true;
      if (!e.repeat && e.code === 'KeyC') this.flareQueued = true; // main.py:1973 C = flares
      if (!e.repeat && e.code === 'KeyX') this.ecmQueued = true; // ECM gets its own key here (main.py shares C)
      this.keys.add(e.code);
      this.touchMode = false;
      this.showTouch(false);
    });
    window.addEventListener('keyup', (e) => this.keys.delete(e.code));
    window.addEventListener('blur', () => this.keys.clear());
    window.addEventListener('gamepadconnected', () => (this.padConnected = true));
    window.addEventListener('gamepaddisconnected', () => {
      const pads = navigator.getGamepads();
      this.padConnected = false;
      for (const p of pads) if (p) this.padConnected = true;
    });
    this.buildTouch(root);
    if (navigator.maxTouchPoints > 0 || 'ontouchstart' in window) {
      this.touchMode = true;
      this.showTouch(true);
    }
  }

  /** Enter / gamepad A or Start / a tap on a start or restart button. */
  queueStart(): void {
    this.startQueued = true;
  }

  consumeFlare(): boolean {
    const s = this.flareQueued;
    this.flareQueued = false;
    return s;
  }

  consumeEcm(): boolean {
    const s = this.ecmQueued;
    this.ecmQueued = false;
    return s;
  }

  consumeStart(): boolean {
    const s = this.startQueued;
    this.startQueued = false;
    return s;
  }

  /** Read every device once per physics step. */
  update(dt: number): void {
    const k = this.keys;
    const tp = (k.has('KeyS') || k.has('ArrowDown') ? 1 : 0) - (k.has('KeyW') || k.has('ArrowUp') ? 1 : 0);
    const tr = (k.has('KeyD') || k.has('ArrowRight') ? 1 : 0) - (k.has('KeyA') || k.has('ArrowLeft') ? 1 : 0);
    const ty = (k.has('KeyE') ? 1 : 0) - (k.has('KeyQ') ? 1 : 0);
    this.kPitch = ramp(this.kPitch, tp, KEY_RAMP * dt);
    this.kRoll = ramp(this.kRoll, tr, KEY_RAMP * dt);
    this.kYaw = ramp(this.kYaw, ty, KEY_RAMP * dt);

    let pitch = this.kPitch;
    let roll = this.kRoll;
    let yaw = this.kYaw;
    let thr = (k.has('KeyR') ? 1 : 0) - (k.has('KeyF') ? 1 : 0);
    let ab = k.has('Space');

    if (this.padConnected) {
      const pads = navigator.getGamepads();
      for (let i = 0; i < pads.length; i++) {
        const p = pads[i];
        if (!p || !p.connected) continue;
        const ax = p.axes;
        const lx = dead(ax[0] ?? 0, PAD_DEADZONE);
        const ly = dead(ax[1] ?? 0, PAD_DEADZONE);
        const rx = dead(ax[2] ?? 0, PAD_DEADZONE);
        if (lx !== 0 || ly !== 0 || rx !== 0) {
          roll += lx;
          pitch += ly; // stick back (down on the axis) = pull up
          yaw += rx;
          this.touchMode = false;
          this.showTouch(false);
        }
        const b = p.buttons;
        const rt = b[7] ? b[7].value : 0;
        const lt = b[6] ? b[6].value : 0;
        if (rt > 0.1) thr += rt;
        if (lt > 0.1) thr -= lt;
        if ((b[0] && b[0].pressed) || (b[5] && b[5].pressed)) ab = true; // A or RB
        const startDown = !!((b[9] && b[9].pressed) || (b[0] && b[0].pressed));
        if (startDown && !this.padStartWasDown) this.startQueued = true;
        this.padStartWasDown = startDown;
        const flareDown = !!(b[3] && b[3].pressed); // Y = flares (main.py:132)
        if (flareDown && !this.padFlareWasDown) this.flareQueued = true;
        this.padFlareWasDown = flareDown;
        const ecmDown = !!(b[4] && b[4].pressed); // LB = ECM
        if (ecmDown && !this.padEcmWasDown) this.ecmQueued = true;
        this.padEcmWasDown = ecmDown;
        break;
      }
    }

    if (this.stickId >= 0) {
      roll += this.stickX;
      pitch += this.stickY;
    }
    if (this.touchThrUp) thr += 1;
    if (this.touchThrDown) thr -= 1;
    if (this.touchAb) ab = true;

    this.pitch = clamp1(pitch);
    this.roll = clamp1(roll);
    this.yaw = clamp1(yaw);
    this.throttle = clamp1(thr);
    this.afterburner = ab;
  }

  setTouchVisible(playing: boolean): void {
    this.touchLayer.style.display = this.touchMode && playing ? 'block' : 'none';
  }

  private showTouch(on: boolean): void {
    if (!on) this.touchLayer.style.display = 'none';
  }

  private buildTouch(root: HTMLElement): void {
    const layer = document.createElement('div');
    layer.className = 'touch-layer';
    layer.style.display = 'none';
    const base = document.createElement('div');
    base.className = 'stick-base';
    base.style.width = base.style.height = `${STICK_RADIUS * 2}px`;
    const knob = document.createElement('div');
    knob.className = 'stick-knob';
    base.appendChild(knob);
    layer.appendChild(base);
    this.stickBase = base;
    this.stickKnob = knob;

    const zone = document.createElement('div');
    zone.className = 'stick-zone';
    layer.insertBefore(zone, base);
    zone.addEventListener('pointerdown', (e) => {
      if (this.stickId >= 0) return;
      this.stickId = e.pointerId;
      this.stickCx = e.clientX;
      this.stickCy = e.clientY;
      zone.setPointerCapture(e.pointerId);
      this.placeStick();
      this.moveStick(e.clientX, e.clientY);
    });
    zone.addEventListener('pointermove', (e) => {
      if (e.pointerId === this.stickId) this.moveStick(e.clientX, e.clientY);
    });
    const end = (e: PointerEvent): void => {
      if (e.pointerId !== this.stickId) return;
      this.stickId = -1;
      this.stickX = this.stickY = 0;
      this.stickKnob.style.transform = 'translate(-50%, -50%)';
      this.stickBase.classList.remove('live');
    };
    zone.addEventListener('pointerup', end);
    zone.addEventListener('pointercancel', end);

    const btn = (label: string, cls: string, set: (v: boolean) => void): void => {
      const b = document.createElement('div');
      b.className = `touch-btn ${cls}`;
      b.textContent = label;
      b.addEventListener('pointerdown', (e) => {
        b.setPointerCapture(e.pointerId);
        set(true);
        b.classList.add('held');
      });
      const off = (): void => {
        set(false);
        b.classList.remove('held');
      };
      b.addEventListener('pointerup', off);
      b.addEventListener('pointercancel', off);
      layer.appendChild(b);
    };
    btn('THR +', 'thr-up', (v) => (this.touchThrUp = v));
    btn('THR -', 'thr-down', (v) => (this.touchThrDown = v));
    btn('AB', 'ab', (v) => (this.touchAb = v));
    btn('FLARE', 'flare', (v) => {
      if (v) this.flareQueued = true;
    });
    btn('ECM', 'ecm', (v) => {
      if (v) this.ecmQueued = true;
    });

    root.appendChild(layer);
    this.touchLayer = layer;
    window.addEventListener('pointerdown', (e) => {
      if (e.pointerType === 'touch') this.touchMode = true;
    });
  }

  private placeStick(): void {
    this.stickBase.style.left = `${this.stickCx - STICK_RADIUS}px`;
    this.stickBase.style.top = `${this.stickCy - STICK_RADIUS}px`;
    this.stickBase.style.bottom = 'auto';
    this.stickBase.classList.add('live');
  }

  private moveStick(x: number, y: number): void {
    let dx = (x - this.stickCx) / STICK_RADIUS;
    let dy = (y - this.stickCy) / STICK_RADIUS;
    const len = Math.hypot(dx, dy);
    if (len > 1) {
      dx /= len;
      dy /= len;
    }
    this.stickKnob.style.transform = `translate(calc(-50% + ${dx * STICK_RADIUS}px), calc(-50% + ${dy * STICK_RADIUS}px))`;
    this.stickX = dead(dx, STICK_DEADZONE);
    this.stickY = dead(dy, STICK_DEADZONE); // finger pulled down = pull up
  }
}

function ramp(cur: number, target: number, maxStep: number): number {
  // springs back to centre twice as fast as it deflects
  const step = target === 0 ? maxStep * 2 : maxStep;
  if (cur < target) return Math.min(target, cur + step);
  if (cur > target) return Math.max(target, cur - step);
  return cur;
}

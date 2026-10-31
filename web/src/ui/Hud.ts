// HUD: speed, altitude, heading, G, throttle, health, missile warning, plus screen markers for
// SAM batteries and incoming missiles. DOM text is only rewritten when a value changes.
import { type PerspectiveCamera, Vector3 } from 'three';
import { ALT_MIN_FT, FT, JET_HP } from '../config';
import type { JetPhysics } from '../flight/JetPhysics';

const MS_TO_KT = 1.943844;
const MARK_SITES = 16;
const MARK_MISSILES = 8;

export interface HudMissile {
  active: boolean;
  guided: boolean;
  pos: Vector3;
}
export interface HudSite {
  x: number;
  y: number;
  z: number;
}

const _p = new Vector3();
const _rel = new Vector3();

function el(parent: HTMLElement, cls: string, text = ''): HTMLDivElement {
  const d = document.createElement('div');
  d.className = cls;
  d.textContent = text;
  parent.appendChild(d);
  return d;
}

class Text {
  private last = '';
  constructor(readonly node: HTMLElement) {}
  set(s: string): void {
    if (s !== this.last) {
      this.node.textContent = s;
      this.last = s;
    }
  }
}

export class Hud {
  readonly root: HTMLDivElement;
  private spd: Text;
  private mach: Text;
  private alt: Text;
  private agl: Text;
  private hdg: Text;
  private g: Text;
  private thr: Text;
  private hpText: Text;
  private hpFill: HTMLDivElement;
  private warn: Text;
  private warnNode: HTMLDivElement;
  private caution: Text;
  private siteMarks: HTMLDivElement[] = [];
  private missileMarks: HTMLDivElement[] = [];
  private missileText: Text[] = [];
  private lastHp = -1;
  private tick = 0;

  constructor(parent: HTMLElement) {
    const r = el(parent, 'hud');
    this.root = r;
    const left = el(r, 'hud-box hud-left');
    el(left, 'hud-label', 'SPEED');
    this.spd = new Text(el(left, 'hud-big'));
    this.mach = new Text(el(left, 'hud-small'));
    const right = el(r, 'hud-box hud-right');
    el(right, 'hud-label', 'ALTITUDE');
    this.alt = new Text(el(right, 'hud-big'));
    this.agl = new Text(el(right, 'hud-small'));
    const top = el(r, 'hud-top');
    this.hdg = new Text(el(top, 'hud-hdg'));
    const hp = el(top, 'hud-hp');
    const bar = el(hp, 'hud-hp-bar');
    this.hpFill = el(bar, 'hud-hp-fill');
    this.hpText = new Text(el(hp, 'hud-small'));
    const bl = el(r, 'hud-box hud-bl');
    this.g = new Text(el(bl, 'hud-mid'));
    this.thr = new Text(el(bl, 'hud-small'));
    this.warnNode = el(r, 'hud-warn');
    this.warn = new Text(this.warnNode);
    this.caution = new Text(el(r, 'hud-caution'));
    for (let i = 0; i < MARK_SITES; i++) {
      const m = el(r, 'mark mark-site', 'SAM');
      m.style.display = 'none';
      this.siteMarks.push(m);
    }
    for (let i = 0; i < MARK_MISSILES; i++) {
      const m = el(r, 'mark mark-missile');
      m.style.display = 'none';
      this.missileMarks.push(m);
      this.missileText.push(new Text(m));
    }
  }

  show(on: boolean): void {
    this.root.style.display = on ? 'block' : 'none';
  }

  update(jet: JetPhysics, groundM: number, cam: PerspectiveCamera, sites: readonly HudSite[], missiles: readonly HudMissile[], w: number, h: number): void {
    this.tick++;
    const slow = this.tick % 4 === 0; // numbers at 15 Hz, markers every frame
    const v = jet.speed;
    if (slow) {
      this.spd.set(`${Math.round(v * MS_TO_KT)} KT`);
      this.mach.set(`M ${jet.mach.toFixed(2)}`);
      const altFt = jet.pos.y / FT;
      this.alt.set(`${(Math.round(altFt / 10) * 10).toLocaleString('en-US')} FT`);
      this.agl.set(`AGL ${Math.round(Math.max(0, jet.pos.y - groundM) / FT).toLocaleString('en-US')} FT`);
      this.hdg.set(`HDG ${String(Math.round(jet.headingDeg) % 360).padStart(3, '0')}`);
      this.g.set(`${jet.gLoad.toFixed(1)} G`);
      this.thr.set(jet.afterburner ? 'THR AB' : `THR ${Math.round(jet.throttle * 100)}%`);
    }
    if (jet.hp !== this.lastHp) {
      this.lastHp = jet.hp;
      this.hpFill.style.width = `${(100 * jet.hp) / JET_HP}%`;
      this.hpText.set(`HP ${jet.hp} / ${JET_HP}`);
    }

    // missile warning: nearest active missile, as a clock bearing
    let nearest = -1;
    let nd = Infinity;
    for (let i = 0; i < missiles.length; i++) {
      const m = missiles[i];
      if (!m.active) continue;
      const d = m.pos.distanceTo(jet.pos);
      if (d < nd) {
        nd = d;
        nearest = i;
      }
    }
    if (jet.alive && nearest >= 0) {
      if (slow) {
        _rel.copy(missiles[nearest].pos).sub(jet.pos);
        const mb = Math.atan2(_rel.x, -_rel.z);
        const jb = Math.atan2(jet.vel.x, -jet.vel.z);
        let rel = ((mb - jb) * 180) / Math.PI;
        rel = ((rel % 360) + 360) % 360;
        const clock = Math.round(rel / 30) % 12 || 12;
        const hi = _rel.y > 300 ? ' HIGH' : _rel.y < -300 ? ' LOW' : '';
        // main.py:79 warns about unguided rounds as ROCKET: turning away escapes those
        const kind = missiles[nearest].guided ? 'MISSILE' : 'ROCKET - TURN AWAY';
        this.warn.set(`${kind}  ${clock} O'CLOCK${hi}  ${(nd / 1000).toFixed(1)} KM`);
      }
      this.warnNode.style.visibility = (this.tick >> 3) % 2 === 0 || nd < 3000 ? 'visible' : 'hidden';
    } else {
      this.warn.set('');
    }

    if (slow) {
      let c = '';
      if (jet.alive && jet.stalled) c = 'STALL';
      else if (jet.alive && jet.pos.y - groundM < ALT_MIN_FT * FT && jet.vel.y < -20) c = 'PULL UP';
      this.caution.set(c);
    }

    // markers
    const maxSiteDist = 25000;
    for (let i = 0; i < this.siteMarks.length; i++) {
      const m = this.siteMarks[i];
      const s = sites[i];
      if (!s) {
        m.style.display = 'none';
        continue;
      }
      _p.set(s.x, s.y, s.z);
      const d = _p.distanceTo(jet.pos);
      if (d > maxSiteDist || !this.place(m, _p, cam, w, h)) m.style.display = 'none';
    }
    for (let i = 0; i < this.missileMarks.length; i++) {
      const m = this.missileMarks[i];
      const ms = missiles[i];
      if (!ms || !ms.active || !this.place(m, ms.pos, cam, w, h)) {
        m.style.display = 'none';
        continue;
      }
      if (slow) this.missileText[i].set(`${(ms.pos.distanceTo(jet.pos) / 1000).toFixed(1)}`);
    }
  }

  private place(m: HTMLDivElement, world: Vector3, cam: PerspectiveCamera, w: number, h: number): boolean {
    _p.copy(world).project(cam);
    if (_p.z > 1 || _p.z < -1 || Math.abs(_p.x) > 1.05 || Math.abs(_p.y) > 1.05) return false;
    const x = (_p.x * 0.5 + 0.5) * w;
    const y = (-_p.y * 0.5 + 0.5) * h;
    m.style.display = 'block';
    m.style.transform = `translate(${x.toFixed(0)}px, ${y.toFixed(0)}px) translate(-50%, -50%)`;
    return true;
  }
}

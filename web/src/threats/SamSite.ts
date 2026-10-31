// SAM battery: engages the jet by itself when the jet is inside its ground ring (main.py:2229-2241).
import { BoxGeometry, CylinderGeometry, Group, Mesh, MeshLambertMaterial, type Vector3 } from 'three';
import { AUTO_SAM_CAP, SAM_LAUNCH_CHANCE, SAM_MISSILES_PER_SITE, SAM_RANGE_M, SAM_SITE_HP, SAM_SITE_RELOAD } from '../config';

const truckGeo = new BoxGeometry(3, 2.5, 9);
const tubeGeo = new CylinderGeometry(0.45, 0.45, 7, 8);
const radarGeo = new BoxGeometry(4, 3, 1);
const truckMat = new MeshLambertMaterial({ color: 0x6b6f4a });
const tubeMat = new MeshLambertMaterial({ color: 0x8a8d6a });
const radarMat = new MeshLambertMaterial({ color: 0x555a40 });

export class SamSite {
  readonly mesh = new Group();
  cooldown = 0; // frames
  missiles = SAM_MISSILES_PER_SITE;
  hp = SAM_SITE_HP;

  constructor(
    readonly index: number,
    readonly x: number,
    readonly y: number,
    readonly z: number,
  ) {
    const truck = new Mesh(truckGeo, truckMat);
    truck.position.y = 1.6;
    this.mesh.add(truck);
    for (let i = 0; i < 4; i++) {
      const t = new Mesh(tubeGeo, tubeMat);
      t.position.set(i % 2 === 0 ? -0.6 : 0.6, 4 + (i < 2 ? 0 : 1), 1);
      t.rotation.x = -0.9;
      this.mesh.add(t);
    }
    const radar = new Mesh(radarGeo, radarMat);
    radar.position.set(0, 5, -4);
    this.mesh.add(radar);
    this.mesh.scale.setScalar(3); // big enough to see from a few km
    this.mesh.position.set(x, y, z);
  }

  reset(rand: () => number): void {
    this.cooldown = Math.floor(rand() * SAM_SITE_RELOAD); // main.py:457 random first reload
    this.missiles = SAM_MISSILES_PER_SITE;
    this.hp = SAM_SITE_HP;
  }

  /** One 60 Hz frame. True when this battery launches now. */
  step(jet: Vector3 | null, airborne: number, rand: () => number): boolean {
    if (this.cooldown > 0) {
      this.cooldown--;
      return false;
    }
    if (!jet || this.hp <= 0 || this.missiles <= 0 || airborne >= AUTO_SAM_CAP) return false;
    const dx = jet.x - this.x;
    const dz = jet.z - this.z;
    if (dx * dx + dz * dz > SAM_RANGE_M * SAM_RANGE_M) return false; // main.py:2238 ground ring, any altitude
    if (rand() >= SAM_LAUNCH_CHANCE) return false; // main.py:2239
    this.cooldown = SAM_SITE_RELOAD; // main.py:1851
    this.missiles--;
    return true;
  }
}

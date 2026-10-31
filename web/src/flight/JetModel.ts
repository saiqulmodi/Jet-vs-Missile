// Low-poly jet built from a few primitives (no model download). Nose points down -Z.
import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  ConeGeometry,
  CylinderGeometry,
  DoubleSide,
  Group,
  Mesh,
  MeshBasicMaterial,
  MeshLambertMaterial,
  SphereGeometry,
} from 'three';

function tri(points: number[]): BufferGeometry {
  const g = new BufferGeometry();
  g.setAttribute('position', new BufferAttribute(new Float32Array(points), 3));
  g.computeVertexNormals();
  return g;
}

export class JetModel {
  readonly group = new Group();
  private flame: Mesh;
  private flameMat: MeshBasicMaterial;
  private nav: Mesh[] = [];
  private strobe: Mesh;

  constructor() {
    const skin = new MeshLambertMaterial({ color: 0x8c97a3 });
    const dark = new MeshLambertMaterial({ color: 0x5d6670, side: DoubleSide });
    const glass = new MeshLambertMaterial({ color: 0x1d2a3a, emissive: 0x0a1626 });

    const body = new Mesh(new CylinderGeometry(0.75, 0.9, 12, 10), skin);
    body.rotation.x = Math.PI / 2;
    this.group.add(body);
    const nose = new Mesh(new ConeGeometry(0.75, 4, 10), skin);
    nose.rotation.x = -Math.PI / 2;
    nose.position.z = -8;
    this.group.add(nose);
    const canopy = new Mesh(new SphereGeometry(0.6, 10, 8), glass);
    canopy.scale.set(1, 0.8, 2.4);
    canopy.position.set(0, 0.7, -4.2);
    this.group.add(canopy);

    // delta wings (both sides in one geometry, two-sided material)
    const wing = tri([
      -0.6, 0, -3, -5.2, 0, 3.4, -0.6, 0, 4, // left
      0.6, 0, -3, 0.6, 0, 4, 5.2, 0, 3.4, // right
    ]);
    const wings = new Mesh(wing, dark);
    this.group.add(wings);
    const tail = new Mesh(tri([0, 0.6, 2.5, 0, 4.2, 5.8, 0, 0.6, 6]), dark);
    this.group.add(tail);
    const stab = new Mesh(tri([-0.5, 0, 4.4, -2.6, 0, 6.3, -0.5, 0, 6.3, 0.5, 0, 4.4, 0.5, 0, 6.3, 2.6, 0, 6.3]), dark);
    this.group.add(stab);

    this.flameMat = new MeshBasicMaterial({ color: 0xffa040, transparent: true, opacity: 0.85, blending: AdditiveBlending, depthWrite: false });
    this.flame = new Mesh(new ConeGeometry(0.65, 4, 10, 1, true), this.flameMat);
    this.flame.rotation.x = Math.PI / 2; // tip points backwards (+Z)
    this.flame.position.z = 8;
    this.group.add(this.flame);

    // navigation lights, shown at night: red port wingtip, green starboard, white tail strobe (main.py:2522-2528)
    const lamp = (hex: number, x: number, y: number, z: number): Mesh => {
      const m = new MeshBasicMaterial({ color: hex });
      m.color.multiplyScalar(1.4);
      const s = new Mesh(new SphereGeometry(0.25, 8, 6), m);
      s.position.set(x, y, z);
      s.visible = false;
      this.group.add(s);
      return s;
    };
    this.nav.push(lamp(0xff3228, -5.2, 0.1, 3.4), lamp(0x28ff5a, 5.2, 0.1, 3.4));
    this.strobe = lamp(0xffffff, 0, 4.3, 5.8);
  }

  setNight(night: boolean, frame: number): void {
    for (const n of this.nav) n.visible = night;
    this.strobe.visible = night && frame % 60 < 5; // main.py:2527
  }

  /** 0 = engine idle glow, 1 = full afterburner plume */
  setFlame(throttle: number, afterburner: boolean, t: number): void {
    const len = afterburner ? 1.6 + 0.15 * Math.sin(t * 40) : 0.25 + 0.35 * throttle;
    this.flame.scale.set(afterburner ? 1.1 : 0.8, len, afterburner ? 1.1 : 0.8);
    this.flame.position.z = 6 + 2 * len;
    this.flameMat.color.setHex(afterburner ? 0xff9a3a : 0xff7040).multiplyScalar(afterburner ? 3 : 1.5); // bright: blooms
    this.flameMat.opacity = afterburner ? 0.9 : 0.5;
  }
}

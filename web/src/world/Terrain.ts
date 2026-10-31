// Procedural heightfield: no texture downloads. One grid mesh follows the jet; when the jet has moved
// far from its centre the heights are rebuilt around the new centre a few rows per frame (no hitch).
import { BufferAttribute, BufferGeometry, Mesh, MeshLambertMaterial } from 'three';

const SIZE = 90000; // m, side of the terrain mesh
const SEG = 256; // grid cells per side
const CELL = SIZE / SEG;
const RECENTER = SIZE / 8; // rebuild once the jet is this far from the centre
const ROWS_PER_FRAME = 24;

// ---- value noise ----
function hash(ix: number, iz: number): number {
  let h = (ix * 374761393 + iz * 668265263) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h & 0xffffff) / 0xffffff;
}
function noise(x: number, z: number): number {
  const ix = Math.floor(x);
  const iz = Math.floor(z);
  const fx = x - ix;
  const fz = z - iz;
  const ux = fx * fx * (3 - 2 * fx);
  const uz = fz * fz * (3 - 2 * fz);
  const a = hash(ix, iz);
  const b = hash(ix + 1, iz);
  const c = hash(ix, iz + 1);
  const d = hash(ix + 1, iz + 1);
  return a + (b - a) * ux + (c - a) * uz + (a - b - c + d) * ux * uz;
}

/** Ground height in metres at world (x, z). Same function for drawing, collisions and placing sites. */
export function heightAt(x: number, z: number): number {
  const sx = x / 14000;
  const sz = z / 14000;
  let f = 0;
  let amp = 1;
  let freq = 1;
  for (let o = 0; o < 5; o++) {
    f += amp * noise(sx * freq + o * 17.3, sz * freq - o * 9.1);
    amp *= 0.5;
    freq *= 2.03;
  }
  f /= 1.9375; // 0..1
  // ridged mountains where a slow mask is high
  const mask = noise(x / 40000 + 3.7, z / 40000 - 1.2);
  const ridge = 1 - Math.abs(noise(x / 6000 - 5.1, z / 6000 + 2.3) * 2 - 1);
  let hgt = (f - 0.32) * 1500 + Math.max(0, mask - 0.45) * ridge * ridge * 4200;
  if (hgt < 0) hgt = 0; // sea / lakes
  return hgt;
}

export class Terrain {
  readonly mesh: Mesh;
  private geo: BufferGeometry;
  private pos: BufferAttribute;
  private col: BufferAttribute;
  private stagingY: Float32Array;
  private stagingC: Float32Array;
  private centerX = 0;
  private centerZ = 0;
  private jobX = 0;
  private jobZ = 0;
  private jobRow = -1;

  constructor() {
    const n = SEG + 1;
    const positions = new Float32Array(n * n * 3);
    const colors = new Float32Array(n * n * 3);
    for (let r = 0; r < n; r++) {
      for (let c = 0; c < n; c++) {
        const i = (r * n + c) * 3;
        positions[i] = -SIZE / 2 + c * CELL;
        positions[i + 2] = -SIZE / 2 + r * CELL;
      }
    }
    const index = new Uint32Array(SEG * SEG * 6);
    let k = 0;
    for (let r = 0; r < SEG; r++) {
      for (let c = 0; c < SEG; c++) {
        const a = r * n + c;
        const b = a + 1;
        const d = a + n;
        const e = d + 1;
        index[k++] = a;
        index[k++] = d;
        index[k++] = b;
        index[k++] = b;
        index[k++] = d;
        index[k++] = e;
      }
    }
    this.geo = new BufferGeometry();
    this.pos = new BufferAttribute(positions, 3);
    this.col = new BufferAttribute(colors, 3);
    this.geo.setAttribute('position', this.pos);
    this.geo.setAttribute('color', this.col);
    this.geo.setIndex(new BufferAttribute(index, 1));
    this.stagingY = new Float32Array(n * n);
    this.stagingC = new Float32Array(n * n * 3);
    this.mesh = new Mesh(this.geo, new MeshLambertMaterial({ vertexColors: true }));
    this.mesh.frustumCulled = false;
    this.mesh.matrixAutoUpdate = true;
    this.buildNow(0, 0);
  }

  /** Call once per frame with the jet position. */
  follow(x: number, z: number): void {
    if (this.jobRow < 0) {
      if (Math.abs(x - this.centerX) > RECENTER || Math.abs(z - this.centerZ) > RECENTER) {
        this.jobX = Math.round(x / CELL) * CELL; // snap to the grid: vertices stay on the same world points
        this.jobZ = Math.round(z / CELL) * CELL;
        this.jobRow = 0;
      }
      return;
    }
    const end = Math.min(SEG + 1, this.jobRow + ROWS_PER_FRAME);
    this.fillRows(this.jobX, this.jobZ, this.jobRow, end);
    this.jobRow = end;
    if (end >= SEG + 1) {
      this.jobRow = -1;
      this.swap(this.jobX, this.jobZ);
    }
  }

  private buildNow(cx: number, cz: number): void {
    this.fillRows(cx, cz, 0, SEG + 1);
    this.swap(cx, cz);
  }

  private fillRows(cx: number, cz: number, r0: number, r1: number): void {
    const n = SEG + 1;
    const ys = this.stagingY;
    const cs = this.stagingC;
    for (let r = r0; r < r1; r++) {
      const wz = cz - SIZE / 2 + r * CELL;
      for (let c = 0; c < n; c++) {
        const wx = cx - SIZE / 2 + c * CELL;
        const h = heightAt(wx, wz);
        const i = r * n + c;
        ys[i] = h;
        // slope from two neighbours (cheap)
        const slope = Math.abs(heightAt(wx + CELL, wz) - h) / CELL;
        groundColor(h, slope, hash(Math.round(wx / CELL), Math.round(wz / CELL)), cs, i * 3);
      }
    }
  }

  private swap(cx: number, cz: number): void {
    const n = SEG + 1;
    const p = this.pos.array as Float32Array;
    const c = this.col.array as Float32Array;
    for (let i = 0; i < n * n; i++) p[i * 3 + 1] = this.stagingY[i];
    c.set(this.stagingC);
    this.pos.needsUpdate = true;
    this.col.needsUpdate = true;
    this.geo.computeVertexNormals();
    this.mesh.position.set(cx, 0, cz);
    this.centerX = cx;
    this.centerZ = cz;
  }
}

function groundColor(h: number, slope: number, jitter: number, out: Float32Array, o: number): void {
  let r: number, g: number, b: number;
  if (h <= 0.5) {
    r = 0.12; g = 0.3; b = 0.52; // water
  } else if (h < 40) {
    r = 0.66; g = 0.6; b = 0.42; // sand
  } else if (slope > 0.55 || h > 2600) {
    if (h > 2900) {
      r = 0.93; g = 0.94; b = 0.97; // snow
    } else {
      r = 0.45; g = 0.41; b = 0.37; // rock
    }
  } else if (h < 500) {
    r = 0.28; g = 0.47; b = 0.19; // grassland
  } else if (h < 1600) {
    r = 0.18; g = 0.36; b = 0.15; // forest
  } else {
    r = 0.4; g = 0.42; b = 0.3; // alpine meadow
  }
  const j = 0.9 + jitter * 0.2;
  out[o] = r * j;
  out[o + 1] = g * j;
  out[o + 2] = b * j;
}

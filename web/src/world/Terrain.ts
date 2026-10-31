// Terrain: one grid mesh that follows the jet; heights from Height.ts (main.py's map). Inside the map the ground
// shows main.py's painted tiles (MapTexture); beyond it, plain procedural colour. Night: the ground darkened to
// moonlight (main.py:39 NIGHT_SHADE) with every main.py light added on top (main.py:2413-2415).
import { BufferAttribute, BufferGeometry, Color, Mesh, ShaderMaterial, type Texture, UniformsLib, UniformsUtils, Vector3 } from 'three';
import { PX_M, WORLD_H_PX, WORLD_W_PX } from '../config';
import { heightAt, noise } from './Height';

export { heightAt } from './Height';

const SIZE = 90000; // m, side of the terrain mesh
const SEG = 384; // grid cells per side (234 m)
const CELL = SIZE / SEG;
const RECENTER = SIZE / 8; // rebuild once the jet is this far from the centre
const ROWS_PER_FRAME = 24;

const vertexShader = /* glsl */ `
  attribute vec3 color;
  varying vec3 vColor;
  varying vec3 vNormal;
  varying vec2 vWorld;
  #include <fog_pars_vertex>
  void main() {
    vColor = color;
    vNormal = normal;
    vec4 world = modelMatrix * vec4(position, 1.0);
    vWorld = world.xz;
    vec4 mvPosition = viewMatrix * world;
    gl_Position = projectionMatrix * mvPosition;
    #include <fog_vertex>
  }`;

const fragmentShader = /* glsl */ `
  uniform sampler2D uDay;
  uniform sampler2D uNight;
  uniform float uNightMix;
  uniform vec3 uSunDir;
  uniform vec3 uSunColor;
  uniform vec3 uSkyLight;
  uniform vec3 uGroundLight;
  uniform vec2 uMapSize; // metres
  varying vec3 vColor;
  varying vec3 vNormal;
  varying vec2 vWorld;
  #include <fog_pars_fragment>
  float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  void main() {
    vec2 uv = vWorld / uMapSize + 0.5;
    vec3 albedo = vColor;
    float inMap = step(0.0, uv.x) * step(uv.x, 1.0) * step(0.0, uv.y) * step(uv.y, 1.0);
    if (uv.x < 0.0) albedo = vec3(0.0048, 0.0159, 0.0782); // the ocean goes on (main.py 14,34,78)
    vec3 lights = vec3(0.0);
    if (inMap > 0.5) {
      albedo = texture2D(uDay, uv).rgb;
      lights = texture2D(uNight, uv).rgb;
    }
    // a little ground texture up close
    albedo *= 0.94 + 0.12 * hash(floor(vWorld / 30.0));
    vec3 n = normalize(vNormal);
    vec3 light = uSunColor * max(dot(n, uSunDir), 0.0) + mix(uGroundLight, uSkyLight, n.y * 0.5 + 0.5);
    vec3 col = albedo * light + lights * uNightMix * 1.8;
    gl_FragColor = vec4(col, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
    #include <fog_fragment>
  }`;

export class Terrain {
  readonly mesh: Mesh;
  readonly material: ShaderMaterial;
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

  constructor(day: Texture, night: Texture) {
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
    this.material = new ShaderMaterial({
      vertexShader,
      fragmentShader,
      fog: true,
      uniforms: UniformsUtils.merge([
        UniformsLib.fog,
        {
          uDay: { value: null },
          uNight: { value: null },
          uNightMix: { value: 0 },
          uSunDir: { value: new Vector3(0.5, 1, 0.3).normalize() },
          uSunColor: { value: new Color(1, 0.95, 0.85).multiplyScalar(1.6) },
          uSkyLight: { value: new Color(0.55, 0.62, 0.75) },
          uGroundLight: { value: new Color(0.2, 0.22, 0.16) },
          uMapSize: { value: { x: WORLD_W_PX * PX_M, y: WORLD_H_PX * PX_M } },
        },
      ]),
    });
    this.material.uniforms.uDay.value = day;
    this.material.uniforms.uNight.value = night;
    this.mesh = new Mesh(this.geo, this.material);
    this.mesh.frustumCulled = false;
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

  /** Jump straight to a new centre (start / restart). */
  snapTo(x: number, z: number): void {
    this.jobRow = -1;
    this.buildNow(Math.round(x / CELL) * CELL, Math.round(z / CELL) * CELL);
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
        const slope = Math.abs(heightAt(wx + CELL, wz) - h) / CELL;
        groundColor(h, slope, noise(wx / 700, wz / 700), cs, i * 3);
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

/** colours beyond main.py's map (linear RGB) */
function groundColor(h: number, slope: number, jitter: number, out: Float32Array, o: number): void {
  let r: number, g: number, b: number;
  if (h <= 0.5) {
    r = 0.005; g = 0.016; b = 0.078; // sea
  } else if (slope > 0.5 || h > 2600) {
    r = 0.1; g = 0.09; b = 0.07; // rock
  } else {
    r = 0.045; g = 0.15; b = 0.025; // grassland, main.py:520 (60,108,42)
  }
  const j = 0.85 + jitter * 0.3;
  out[o] = r * j;
  out[o + 1] = g * j;
  out[o + 2] = b * j;
}

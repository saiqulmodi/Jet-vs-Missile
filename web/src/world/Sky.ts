// Sky dome: a cheap single-scattering look. Light azure low down turning to deep stratospheric indigo at
// 35,000 ft, a sun disk with its glow and a brighter horizon toward the sun; at night a navy sky with stars
// (main.py:1696 night haze: deep navy). Fog takes the horizon colour so the far ground melts into it.
import { BackSide, Color, Fog, Mesh, ShaderMaterial, SphereGeometry, Vector3 } from 'three';
import { CRUISE_ALT_FT, FT } from '../config';

const LOW_ZENITH = new Color('#5a8fd8');
const HIGH_ZENITH = new Color('#141c5c');
const LOW_HORIZON = new Color('#bcd6ee');
const HIGH_HORIZON = new Color('#8aaee0');
const NIGHT_ZENITH = new Color('#03050f');
const NIGHT_HORIZON = new Color('#1a2246'); // main.py:1697 (26,34,70)

export class Sky {
  readonly mesh: Mesh;
  readonly fog = new Fog(0xbfd6ee, 16000, 42000);
  readonly sunDir = new Vector3(0.55, 0.62, 0.35).normalize();
  private mat: ShaderMaterial;
  private zenith = new Color();
  private horizon = new Color();
  private tmp = new Color();

  constructor() {
    this.mat = new ShaderMaterial({
      side: BackSide,
      depthWrite: false,
      fog: false,
      uniforms: {
        uZenith: { value: this.zenith },
        uHorizon: { value: this.horizon },
        uSunDir: { value: this.sunDir },
        uNight: { value: 0 },
      },
      vertexShader: /* glsl */ `
        varying vec3 vDir;
        void main() {
          vDir = normalize(position);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: /* glsl */ `
        uniform vec3 uZenith;
        uniform vec3 uHorizon;
        uniform vec3 uSunDir;
        uniform float uNight;
        varying vec3 vDir;
        float hash(vec3 p) { return fract(sin(dot(p, vec3(12.9898, 78.233, 37.719))) * 43758.5453); }
        void main() {
          vec3 d = normalize(vDir);
          float t = clamp(d.y, 0.0, 1.0);
          vec3 c = mix(uHorizon, uZenith, pow(t, 0.5));
          float mu = max(dot(d, uSunDir), 0.0);
          // Mie glow round the sun, warmer horizon toward it, the disk itself (by day)
          float day = 1.0 - uNight;
          c += vec3(1.0, 0.85, 0.6) * (pow(mu, 8.0) * 0.25 + pow(mu, 120.0) * 0.6) * day;
          c += vec3(1.0, 0.8, 0.55) * pow(1.0 - t, 6.0) * pow(mu, 3.0) * 0.25 * day;
          c += vec3(1.0, 0.97, 0.9) * smoothstep(0.9993, 0.9996, mu) * 6.0 * day;
          // night: stars, and a pale moon where the sun was
          if (uNight > 0.0 && d.y > 0.0) {
            vec3 cell = floor(d * 420.0);
            float s = step(0.9975, hash(cell));
            c += vec3(0.8, 0.85, 1.0) * s * uNight * (0.4 + 0.6 * hash(cell + 3.1)) * smoothstep(0.0, 0.15, d.y);
            c += vec3(0.75, 0.8, 0.9) * smoothstep(0.9990, 0.9994, mu) * 1.5 * uNight;
          }
          if (d.y < 0.0) c = uHorizon;
          gl_FragColor = vec4(c, 1.0);
          #include <colorspace_fragment>
        }`,
    });
    this.mesh = new Mesh(new SphereGeometry(50000, 32, 16), this.mat);
    this.mesh.renderOrder = -1;
    this.mesh.frustumCulled = false;
  }

  update(camX: number, camY: number, camZ: number, night: number): void {
    const t = Math.min(1, Math.max(0, camY / (CRUISE_ALT_FT * FT)));
    this.zenith.copy(LOW_ZENITH).lerp(HIGH_ZENITH, t).lerp(NIGHT_ZENITH, night);
    this.horizon.copy(LOW_HORIZON).lerp(HIGH_HORIZON, t);
    this.tmp.copy(NIGHT_HORIZON);
    this.horizon.lerp(this.tmp, night);
    this.fog.color.copy(this.horizon);
    this.mat.uniforms.uNight.value = night;
    this.mesh.position.set(camX, camY, camZ);
  }
}

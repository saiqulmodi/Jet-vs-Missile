// Gradient sky dome + fog that turn from light azure low down to deep indigo at 35,000 ft.
import { BackSide, Color, Fog, Mesh, ShaderMaterial, SphereGeometry } from 'three';
import { CRUISE_ALT_FT, FT } from '../config';

const LOW_ZENITH = new Color(0.33, 0.56, 0.86);
const HIGH_ZENITH = new Color(0.07, 0.11, 0.36);
const LOW_HORIZON = new Color(0.74, 0.84, 0.93);
const HIGH_HORIZON = new Color(0.52, 0.66, 0.86);

export class Sky {
  readonly mesh: Mesh;
  readonly fog = new Fog(0xbfd6ee, 14000, 36000);
  private mat: ShaderMaterial;
  private zenith = new Color();
  private horizon = new Color();

  constructor() {
    this.mat = new ShaderMaterial({
      side: BackSide,
      depthWrite: false,
      fog: false,
      uniforms: {
        uZenith: { value: this.zenith },
        uHorizon: { value: this.horizon },
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
        varying vec3 vDir;
        void main() {
          float t = clamp(vDir.y, 0.0, 1.0);
          vec3 c = mix(uHorizon, uZenith, pow(t, 0.55));
          if (vDir.y < 0.0) c = uHorizon;
          gl_FragColor = vec4(c, 1.0);
        }`,
    });
    this.mesh = new Mesh(new SphereGeometry(50000, 24, 12), this.mat);
    this.mesh.renderOrder = -1;
    this.mesh.frustumCulled = false;
  }

  update(camX: number, camY: number, camZ: number): void {
    const t = Math.min(1, Math.max(0, camY / (CRUISE_ALT_FT * FT)));
    this.zenith.copy(LOW_ZENITH).lerp(HIGH_ZENITH, t);
    this.horizon.copy(LOW_HORIZON).lerp(HIGH_HORIZON, t);
    this.fog.color.copy(this.horizon);
    this.mesh.position.set(camX, camY, camZ);
  }
}

// Post-processing: bloom on the bright things only (afterburner, missile motors, flares, blasts, night lights),
// computed at half resolution to stay cheap, then the sRGB output pass.
import { type Camera, type Scene, Vector2, type WebGLRenderer } from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';

const DAY_STRENGTH = 0.55;
const NIGHT_STRENGTH = 0.9;

export class PostFx {
  private composer: EffectComposer;
  private bloom: UnrealBloomPass;

  constructor(renderer: WebGLRenderer, scene: Scene, camera: Camera) {
    const size = renderer.getSize(new Vector2());
    this.composer = new EffectComposer(renderer);
    this.composer.addPass(new RenderPass(scene, camera));
    this.bloom = new UnrealBloomPass(new Vector2(size.x / 2, size.y / 2), DAY_STRENGTH, 0.45, 0.92);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());
  }

  setNight(night: boolean): void {
    this.bloom.strength = night ? NIGHT_STRENGTH : DAY_STRENGTH;
  }

  resize(w: number, h: number): void {
    this.composer.setSize(w, h);
    this.bloom.resolution.set(w / 2, h / 2);
  }

  render(): void {
    this.composer.render();
  }
}

// An illustrative black hole: light rays are bent on their way to the eye, so the far side of the glowing disc
// arches over the shadow and a thin ring of light hugs its edge. One camera-facing quad; each pixel follows one
// ray through a Schwarzschild-like field (r_s = 1) and collects the disc wherever it crosses the disc plane.
// It teaches the look of lensing. It is not a simulation of any real object: the disc, its colours and its
// speed are drawn, and the scale is not physical.
import { Mesh, NormalBlending, PlaneGeometry, ShaderMaterial } from 'three'
import type { Quality } from '../quality'

/** Apparent radius of the shadow as a fraction of the quad's half-size (set by the shader's camera). */
export const SHADOW_FRACTION = .31

export class BlackHole extends Mesh<PlaneGeometry, ShaderMaterial> {
  constructor(quality: Quality = 'medium') {
    super(new PlaneGeometry(2, 2), new ShaderMaterial({
      transparent: true, depthWrite: false, depthTest: false, blending: NormalBlending,
      defines: { STEPS: quality === 'low' ? 70 : quality === 'medium' ? 110 : 150 },
      uniforms: { uTime: { value: 0 }, uTilt: { value: .2 } },
      vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: `
        varying vec2 vUv;
        uniform float uTime, uTilt;
        const float R_IN = 1.5, R_OUT = 4.4;
        float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
        float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
          return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
        float fbm(vec2 p){ float a = .5, s = 0.0; for (int i = 0; i < 4; i++) { s += a * noise(p); p = p * 2.03 + 11.7; a *= .5; } return s; }
        float stars(vec3 d){
          vec2 q = vec2(atan(d.z, d.x), asin(clamp(d.y, -1.0, 1.0))) * 34.0;
          vec2 c = floor(q), f = fract(q) - .5;
          float h = hash(c), r = length(f + (vec2(hash(c + 3.1), hash(c + 7.7)) - .5) * .6);
          return step(.92, h) * smoothstep(.12, 0.0, r) * (.4 + .6 * hash(c + 1.3));
        }
        void main(){
          vec2 uv = (vUv - .5) * 2.0;
          vec3 ro = vec3(0.0, sin(uTilt), -cos(uTilt)) * 11.0;
          vec3 fw = normalize(-ro), rt = normalize(cross(vec3(0.0, 1.0, 0.0), fw)), up = cross(fw, rt);
          vec3 p = ro, v = normalize(fw * 1.3 + rt * uv.x + up * uv.y);
          vec3 h = cross(p, v); float h2 = dot(h, h);
          vec3 col = vec3(0.0); float through = 1.0, fell = 0.0;
          for (int i = 0; i < STEPS; i++) {
            float r2 = dot(p, p);
            if (r2 < 1.0) { fell = 1.0; break; }
            float dt = clamp(.045 * r2, .03, .5);
            vec3 np = p + v * dt;
            if (p.y * np.y < 0.0) {
              vec3 c = mix(p, np, p.y / (p.y - np.y)); float r = length(c.xz);
              if (r > R_IN && r < R_OUT) {
                float spin = uTime * 2.2 / pow(r, 1.5), cs = cos(spin), sn = sin(spin);
                vec2 q = mat2(cs, -sn, sn, cs) * c.xz;
                float streak = fbm(vec2(length(q) * 3.4, atan(q.y, q.x) * 2.0)) * .55 + fbm(q * 1.7) * .45;
                float body = smoothstep(R_IN, R_IN + .3, r) * pow(1.0 - (r - R_IN) / (R_OUT - R_IN), 1.5);
                float beam = pow(1.0 + .4 * c.x / r, 3.0);                 // the side turning towards the eye is brighter
                float e = body * (.35 + 1.05 * streak) * beam;
                vec3 hot = mix(vec3(1.0, .34, .07), vec3(1.0, .9, .72), clamp(body * 1.25 * beam * .5, 0.0, 1.0));
                col += through * hot * e * 1.15;
                through *= 1.0 - clamp(e * .75, 0.0, .92);
              }
            }
            v += -1.5 * h2 * p / pow(r2, 2.5) * dt;
            p = np;
            if (r2 > 260.0 && dot(p, v) > 0.0) break;
          }
          float edge = smoothstep(1.0, .8, length(uv));
          // far stars, seen through the bent rays: they smear into arcs close to the shadow
          float sky = fell > .5 ? 0.0 : stars(normalize(v)) * through;
          float halo = (1.0 - fell) * .05 / (.05 + pow(max(0.0, length(uv) - ${SHADOW_FRACTION.toFixed(2)}), 2.0) * 40.0);
          col += vec3(.85, .9, 1.0) * sky + vec3(1.0, .55, .2) * halo * .35;
          float alpha = max(max(fell, 1.0 - through), max(sky, halo * .35));
          gl_FragColor = vec4(col, alpha * edge);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`,
    }))
    this.name = 'illustrative-black-hole-not-a-simulation'
    this.renderOrder = 5
  }
  /** shadowRadius: how large the dark disc should look, in scene units. */
  update(shadowRadius: number, seconds: number): void {
    this.scale.setScalar(shadowRadius / SHADOW_FRACTION)
    this.material.uniforms.uTime.value = seconds
  }
}

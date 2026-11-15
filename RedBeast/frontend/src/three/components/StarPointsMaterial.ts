import { AdditiveBlending, BufferGeometry, Float32BufferAttribute, Points, ShaderMaterial } from 'three'
import type { Vec3 } from '../types'
export interface StarPoint { position: Vec3; color: Vec3; intensity: number; sizePx: number }
export function buildStarPointsGeometry(stars: StarPoint[]): BufferGeometry {
  const geometry = new BufferGeometry()
  geometry.setAttribute('position', new Float32BufferAttribute(stars.flatMap((star) => star.position), 3))
  geometry.setAttribute('color', new Float32BufferAttribute(stars.flatMap((star) => star.color), 3))
  geometry.setAttribute('intensity', new Float32BufferAttribute(stars.map((star) => star.intensity), 1))
  geometry.setAttribute('sizePx', new Float32BufferAttribute(stars.map((star) => star.sizePx), 1))
  return geometry
}
export class StarPointsMaterial extends ShaderMaterial {
  constructor(pixelRatio = 1) {
    super({ transparent: true, depthWrite: false, blending: AdditiveBlending, vertexColors: true,
      uniforms: { uPixelRatio: { value: pixelRatio } },
      vertexShader: `
        attribute float intensity;
        attribute float sizePx;
        uniform float uPixelRatio;
        varying vec3 vColor;
        varying float vIntensity;
        void main() {
          vColor = color; vIntensity = intensity;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = max(1.5, sizePx) * uPixelRatio;
        }`,
      fragmentShader: `
        varying vec3 vColor;
        varying float vIntensity;
        void main() {
          float radius = length(gl_PointCoord * 2.0 - 1.0);
          if (radius > 1.0) discard;
          float core = exp(-0.5 * radius * radius / (0.22 * 0.22));
          float wing = 0.08 * exp(-0.5 * radius * radius / (0.5 * 0.5));
          gl_FragColor = vec4(vColor * vIntensity, (core + wing) * smoothstep(1.0, 0.8, radius));
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }` })
  }
}
export function buildStarPoints(stars: StarPoint[], ratio = 1): Points<BufferGeometry, StarPointsMaterial> {
  return new Points(buildStarPointsGeometry(stars), new StarPointsMaterial(ratio))
}

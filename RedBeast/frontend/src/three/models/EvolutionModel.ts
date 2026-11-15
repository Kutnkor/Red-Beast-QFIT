import { AdditiveBlending, BufferGeometry, Color, Float32BufferAttribute, Group, Points, ShaderMaterial } from 'three'
import type { Camera } from 'three'
import type { Quality } from '../quality'
import { StarSurface } from '../components/StarSurface'
import { evolutionDisplayRadius, type EvolutionSample } from '../science/evolution'
import { molecularEnvelope } from './structures'
import { LifecycleEffects } from './LifecycleEffects'

/** Tabulated global stellar properties; the surface and outflow are illustrations. */
export class EvolutionModel extends Group {
  readonly surface: StarSurface
  readonly wind: Points<BufferGeometry, ShaderMaterial>
  readonly envelope: Group
  readonly effects: LifecycleEffects
  private temperature = -1
  constructor(quality: Quality) {
    super()
    this.name = 'published-evolution-model'
    this.effects=new LifecycleEffects(quality);this.add(this.effects)
    this.surface = new StarSurface(quality); this.add(this.surface)
    this.envelope = molecularEnvelope(1, new Color(), quality)
    this.add(this.envelope)
    const positions: number[] = [], phases: number[] = []
    const count = quality === 'low' ? 500 : 1600
    for (let i = 0; i < count; i++) {
      const y = 1 - 2 * (i + .5) / count, r = Math.sqrt(1 - y * y), angle = i * Math.PI * (3 - Math.sqrt(5))
      positions.push(r * Math.cos(angle), y, r * Math.sin(angle)); phases.push((i * .61803398875) % 1)
    }
    const geometry = new BufferGeometry()
    geometry.setAttribute('position', new Float32BufferAttribute(positions, 3))
    geometry.setAttribute('aPhase', new Float32BufferAttribute(phases, 1))
    this.wind = new Points(geometry, new ShaderMaterial({ transparent: true, depthWrite: false, blending: AdditiveBlending,
      uniforms: { uTime: { value: 0 }, uRadius: { value: 1 }, uDensity: { value: 0 }, uPixelRatio: { value: 1 }, uColor: { value: new Color() } },
      vertexShader: `attribute float aPhase; uniform float uTime,uRadius,uPixelRatio; varying float vFade;
        void main(){float p=fract(aPhase+uTime*.035); vec3 point=position*uRadius*(1.1+p*2.2);
          vFade=sin(p*3.14159)*(1.0-p);gl_Position=projectionMatrix*modelViewMatrix*vec4(point,1.0);gl_PointSize=2.2*uPixelRatio;}`,
      fragmentShader: `uniform vec3 uColor; uniform float uDensity; varying float vFade;
        void main(){float r=length(gl_PointCoord*2.0-1.0);if(r>1.0)discard;
          gl_FragColor=vec4(uColor,exp(-r*r*5.0)*vFade*uDensity);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`,
    }))
    this.wind.frustumCulled = false
    this.wind.userData.classification = 'illustrative_mass_loss_tracers_not_hydrodynamics'
    this.add(this.wind)
  }
  update(sample: EvolutionSample, seconds: number, surroundings: boolean, showEffects = true) {
    const radius = evolutionDisplayRadius(sample.radius)
    this.surface.scale.setScalar(radius)
    // Quantize colour computation to 10 K while metrics retain interpolated precision.
    const temperature=Math.max(10, Math.round(sample.temperature / 10) * 10)
    if(temperature!==this.temperature){this.temperature=temperature;this.surface.setTemperature(temperature)}
    this.surface.setKind(sample.phase === -3 ? 'clouds' : sample.phase===-1?'accreting':sample.phase>=2&&sample.phase<=5?'giant':'photosphere')
    this.surface.setVisualTime(seconds)
    this.surface.surface.rotation.y=seconds*.018
    this.effects.update(sample.phase===-1?'protostar':sample.phase===0?'main_sequence':sample.phase===6?'planetary_nebula':'none',radius,seconds,0,surroundings&&showEffects)
    this.envelope.visible = surroundings && sample.radius > 20 && sample.phase >= 2 && sample.phase <= 5
    this.envelope.scale.setScalar(radius)
    this.envelope.traverse(object => {
      const material = (object as typeof object & { material?: ShaderMaterial }).material
      if (material?.uniforms.uColor) material.uniforms.uColor.value.copy(this.surface.surface.material.uniforms.uColor.value)
      if (material?.uniforms.uTime) material.uniforms.uTime.value = seconds
    })
    this.wind.visible = surroundings && sample.massLoss > 0
    const uniforms = this.wind.material.uniforms
    uniforms.uRadius.value = radius; uniforms.uTime.value = seconds
    uniforms.uDensity.value = Math.min(.35, Math.log10(1 + sample.massLoss / 1e-10) * .055)
    uniforms.uColor.value.copy(this.surface.surface.material.uniforms.uColor.value)
    this.userData.sample = sample
  }
  faceCamera(camera: Camera) { this.surface.faceCamera(camera) }
}

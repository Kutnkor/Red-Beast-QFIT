import { AdditiveBlending, BufferGeometry, Color, DoubleSide, Float32BufferAttribute, Group, Line, LineDashedMaterial, Mesh, Points, RingGeometry, ShaderMaterial, SphereGeometry, Vector3 } from 'three'
import type { ModelPhenomenon, StellarProfile, Vec3 } from '../types'
import type { LabelSpec } from '../labels'
import type { Quality } from '../quality'
import { temperatureToLinear } from '../science/blackbody'
import { hasPhenomenon, parameter } from '../science/models'
import { tokenColor } from '../tokens'
import { translate } from '../../i18n'

/** Schematic density/flow tracers, never a measured image or fitted fluid simulation. */
function buildFlow(kind: 'wind' | 'jet' | 'disk', radius: number, color: Color, quality: Quality): Points<BufferGeometry, ShaderMaterial> {
  const count = quality === 'low' ? 180 : 620
  const positions: number[] = [], phases: number[] = []
  const goldenAngle = Math.PI * (3 - Math.sqrt(5))
  for (let i = 0; i < count; i++) {
    const y = 1 - 2 * (i + .5) / count, r = Math.sqrt(1 - y * y), a = i * goldenAngle
    positions.push(Math.cos(a) * r, y, Math.sin(a) * r)
    phases.push((i * .6180339887498949) % 1)
  }
  const geometry = new BufferGeometry()
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3))
  geometry.setAttribute('aPhase', new Float32BufferAttribute(phases, 1))
  const material = new ShaderMaterial({ transparent: true, depthWrite: false, blending: AdditiveBlending,
    uniforms: { uTime: { value: 0 }, uRadius: { value: radius }, uColor: { value: color }, uKind: { value: { wind: 0, jet: 1, disk: 2 }[kind] }, uPixelRatio: { value: 1 } },
    vertexShader: `attribute float aPhase; uniform float uTime; uniform float uRadius; uniform float uKind; uniform float uPixelRatio;
      varying float vFade; void main() {
        float phase=fract(aPhase+uTime*0.045); vec3 p;
        if(uKind<0.5) { p=position*uRadius*(1.15+phase*2.5); vFade=sin(phase*3.14159)*(1.0-phase)*0.16; }
        else if(uKind<1.5) { float signY=position.y<0.0?-1.0:1.0;
          float distance=0.9+phase*3.5; float width=0.025+distance*0.085;
          p=vec3(position.x*width,signY*distance,position.z*width)*uRadius;
          vFade=(1.0-phase)*0.85; }
        else { float r=1.35+aPhase*1.9; float a=atan(position.z,position.x)+uTime*0.35/pow(r,1.5);
          p=vec3(cos(a)*r,position.y*0.035,sin(a)*r)*uRadius; vFade=0.3+0.4*(1.0-aPhase); }
        gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.0);
        gl_PointSize=(uKind>0.5&&uKind<1.5?3.0:2.0)*uPixelRatio;
      }`,
    fragmentShader: `uniform vec3 uColor; varying float vFade; void main() {
      float r=length(gl_PointCoord*2.0-1.0); if(r>1.0) discard;
      gl_FragColor=vec4(uColor,exp(-r*r*4.5)*vFade);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
    }`,
  })
  const points = new Points(geometry, material)
  points.frustumCulled = false
  return points
}

function buildAtmosphere(radius: number, color: Color, opacity: number): Mesh<SphereGeometry, ShaderMaterial> {
  return new Mesh(new SphereGeometry(radius, 64, 40), new ShaderMaterial({ transparent: true, depthWrite: false, blending: AdditiveBlending,
    uniforms: { uColor: { value: color }, uOpacity: { value: opacity } },
    vertexShader: `varying vec3 vNormal; varying vec3 vView; void main(){vec4 p=modelViewMatrix*vec4(position,1.0);vNormal=normalize(normalMatrix*normal);vView=-p.xyz;gl_Position=projectionMatrix*p;}`,
    fragmentShader: `uniform vec3 uColor; uniform float uOpacity; varying vec3 vNormal; varying vec3 vView; void main(){
      float mu=max(0.0,dot(normalize(vNormal),normalize(vView)));
      float density=pow(1.0-mu,2.0);
      gl_FragColor=vec4(uColor,uOpacity*density);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
    }`,
  }))
}

function buildDisk(radius: number, color: Color, dust: boolean): Mesh<RingGeometry, ShaderMaterial> {
  const geometry = new RingGeometry(radius * 1.25, radius * 3.25, 160, 16)
  const material = new ShaderMaterial({ transparent: true, depthWrite: false, side: DoubleSide,
    uniforms: { uColor: { value: color }, uRadius: { value: radius }, uTime: { value: 0 }, uDust: { value: dust ? 1 : 0 } },
    vertexShader: `varying vec2 vDisk; void main(){vDisk=position.xy;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    fragmentShader: `varying vec2 vDisk; uniform vec3 uColor; uniform float uRadius; uniform float uTime; uniform float uDust;
      void main(){float r=length(vDisk)/uRadius;float a=atan(vDisk.y,vDisk.x);
      float bands=0.77+0.13*sin(r*34.0+0.4*sin(a*3.0))+0.1*sin(r*63.0-a*2.0);
      float edge=smoothstep(1.25,1.5,r)*(1.0-smoothstep(2.8,3.25,r));
      float falloff=pow(1.25/r,0.75);float clump=0.5+0.5*sin(a*2.0-uTime*0.08+r*1.4);
      vec3 c=mix(uColor,vec3(0.1),uDust*0.55*clump);
      gl_FragColor=vec4(c*falloff,edge*bands*(0.34+uDust*clump*0.18));
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
    }`,
  })
  const mesh = new Mesh(geometry, material)
  mesh.rotation.x = -Math.PI / 2
  return mesh
}

export class StarEnvironment extends Group {
  readonly labels: LabelSpec[] = []
  readonly extent: number
  readonly animated: boolean
  readonly phenomenonIds: string[]
  private timeMaterials: ShaderMaterial[] = []
  constructor(profile: StellarProfile, radius: number, temperature: number | null, quality: Quality, lang: 'tr' | 'en', labelPrefix = 'environment') {
    super()
    this.phenomenonIds = profile.phenomena.filter((item) => item.enabled).map((item) => item.id)
    const physicalColor = new Color(...temperatureToLinear(temperature))
    const tracerColor = physicalColor.clone().lerp(tokenColor('--fg'), .45)
    this.animated = hasPhenomenon(profile, 'wind', 'outflow', 'dust_outflow', 'jets', 'bipolar_jets', 'disk', 'accretion_disk', 'pulsation', 'clouds', 'cloud_bands', 'atmosphere')
    let extent = radius * 1.2
    const label = (id: string, text: string, vector: Vec3, priority = 4) => {
      this.labels.push({ id: `${labelPrefix}-${id}`, text, position: () => this.localToWorld(new Vector3(...vector)), priority, kind: 'representative' })
    }
    const flow = (kind: 'wind' | 'jet' | 'disk') => {
      const points = buildFlow(kind, radius, tracerColor, quality)
      this.timeMaterials.push(points.material)
      this.add(points)
    }
    if (hasPhenomenon(profile, 'corona', 'magnetic_activity')) {
      const shell = buildAtmosphere(radius * 1.2, tracerColor, .13)
      this.add(shell)
      label('corona', translate(lang, 'sky.modelCorona'), [radius * 1.25, radius * .7, 0])
    }
    if (hasPhenomenon(profile, 'clouds', 'cloud_bands', 'atmosphere')) {
      this.add(buildAtmosphere(radius * 1.045, tracerColor, .07))
      label('clouds', translate(lang, 'sky.modelClouds'), [radius * 1.2, radius * .2, 0])
    }
    if (hasPhenomenon(profile, 'wind', 'outflow', 'dust_outflow')) {
      flow('wind')
      extent = Math.max(extent, radius * 3.7)
      if (hasPhenomenon(profile, 'dust_outflow')) {
        this.add(buildAtmosphere(radius * 2.15, physicalColor, .035), buildAtmosphere(radius * 2.75, physicalColor, .025))
      }
      label('wind', translate(lang, 'sky.modelWind'), [radius * 2.5, radius * .4, 0])
    }
    if (hasPhenomenon(profile, 'disk', 'accretion_disk')) {
      const disk = buildDisk(radius, physicalColor, hasPhenomenon(profile, 'dust', 'dust_extinction', 'dust_obscuration'))
      this.timeMaterials.push(disk.material)
      this.add(disk)
      flow('disk')
      extent = Math.max(extent, radius * 3.4)
      label('disk', translate(lang, 'sky.modelDisk'), [radius * 2.8, 0, radius * .6])
    }
    if (hasPhenomenon(profile, 'jets', 'bipolar_jets')) {
      flow('jet')
      extent = Math.max(extent, radius * 4.5)
      label('jet', translate(lang, 'sky.modelJets'), [radius * .5, radius * 3.7, 0])
    }
    if (hasPhenomenon(profile, 'pulsation')) {
      label('pulsation', translate(lang, 'sky.modelPulsation'), [radius * .8, radius * 1.2, 0], 5)
    }
    // Measurement reference is only supplied when a physical radius is available.
    if (parameter(profile, 'radius_solar') !== null) {
      const reference: Vec3[] = Array.from({ length: 97 }, (_, i) => [Math.cos(i * Math.PI / 48), Math.sin(i * Math.PI / 48), 0])
      const guide = new Line(new BufferGeometry().setFromPoints(reference.map(point => new Vector3(...point))), new LineDashedMaterial({ color: tokenColor('--fg-3'), transparent: true, opacity: .65, dashSize: .06, gapSize: .04 }))
      guide.name = 'solar-radius-reference'; guide.position.x = radius + 1.6; guide.computeLineDistances(); this.add(guide)
      label('sun-reference', translate(lang, 'sky.sunRadiusReference'), [radius + 1.6, -1.1, 0], 3)
      extent = Math.max(extent, radius + 2.6)
    }
    this.extent = extent
  }
  setVisualTime(seconds: number): void {
    for (const material of this.timeMaterials) material.uniforms.uTime.value = seconds
  }
}

export function enabledPhenomena(profile: StellarProfile | null): ModelPhenomenon[] {
  return profile?.phenomena.filter((phenomenon) => phenomenon.enabled) ?? []
}

import { Color, DataTexture, Group, Line, LineDashedMaterial, Mesh, Quaternion, RGBAFormat, ShaderMaterial, SphereGeometry, Sprite, SpriteMaterial, BufferGeometry, Vector3 } from 'three'
import type { Camera } from 'three'
import type { Quality } from '../quality'
import { temperatureToLinear } from '../science/blackbody'
import { tokenColor } from '../tokens'
import type { SurfaceKind } from '../science/models'
// Illustrative amplitude only; this is not a fitted temperature history.
const SCHEMATIC_TEMPERATURE_FRACTION = .04
export function buildSurfaceGeometry(quality: Quality): SphereGeometry {
  return new SphereGeometry(1, quality === 'low' ? 64 : 128, quality === 'low' ? 48 : 96)
}
function haloTexture(): DataTexture {
  const size = 64, data = new Uint8Array(size * size * 4)
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const i = (y * size + x) * 4, r = Math.hypot((x + .5) / size * 2 - 1, (y + .5) / size * 2 - 1)
    data[i] = data[i + 1] = data[i + 2] = 255
    data[i + 3] = Math.round(255 * Math.exp(-r * r / .22) * Math.max(0, 1 - r))
  }
  const texture = new DataTexture(data, size, size, RGBAFormat)
  texture.needsUpdate = true
  return texture
}
export class StarSurface extends Group {
  readonly surface: Mesh<SphereGeometry, ShaderMaterial>
  readonly outline: Line
  readonly halo: Sprite
  private quality: Quality
  private baseStrength = 1
  private lastTemperature: number | null | undefined = undefined
  constructor(quality: Quality) {
    super()
    this.quality = quality
    this.surface = new Mesh(buildSurfaceGeometry(quality), new ShaderMaterial({
      uniforms: { uColor: { value: new Color(.35, .35, .35) }, uCoolColor: { value: new Color(.35, .35, .35) }, uHotColor: { value: new Color(.35, .35, .35) }, uThermalPhase: { value: 0 }, uStrength: { value: 1 }, uBaseStrength: { value: 1 }, uGranulation: { value: quality === 'high' ? .22 : .16 }, uKind: { value: 0 }, uTime: { value: 0 } },
      vertexShader: `uniform float uKind; varying vec3 vNormal; varying vec3 vView; varying vec3 vLocal;
        void main() { float deformation = uKind > 2.5 ? 0.012*sin(position.x*13.0+sin(position.y*11.0))*cos(position.z*9.0) : 0.0;
          vec4 p=modelViewMatrix*vec4(position*(1.0+deformation),1.0); vNormal=normalize(normalMatrix*normal);
          vView=-p.xyz; vLocal=position; gl_Position=projectionMatrix*p; }`,
      fragmentShader: `uniform vec3 uColor; uniform vec3 uCoolColor; uniform vec3 uHotColor; uniform float uThermalPhase; uniform float uStrength; uniform float uGranulation; uniform float uKind; uniform float uTime;
        varying vec3 vNormal; varying vec3 vView; varying vec3 vLocal;
        float hash(vec3 p) { return fract(sin(dot(p,vec3(127.1,311.7,74.7)))*43758.5453); }
        float noise(vec3 p) { vec3 i=floor(p),f=fract(p); f=f*f*(3.0-2.0*f);
          return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),
            mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z); }
        float fbm(vec3 p) { float a=.5, s=0.0; for (int i=0;i<5;i++) { s+=a*noise(p); p=p*2.03+vec3(17.1,3.7,9.2); a*=.5; } return s; }
        void main() { float mu=max(0.0,dot(normalize(vNormal),normalize(vView)));
          float limb=.22+.78*pow(mu,.6);
          vec3 drift=vec3(0.0,uTime*0.045,uTime*0.018);
          vec3 warp=vec3(fbm(vLocal*2.6+drift),fbm(vLocal*2.6+drift+7.3),fbm(vLocal*2.6-drift+13.1))-.5;
          vec3 cells=vLocal*8.5+warp*2.6;
          float convection=fbm(cells+drift);
          float fine=fbm(cells*3.3+drift*0.65);
          float lane=1.0-smoothstep(0.36,0.52,convection);
          float grain=(convection*.62+fine*.38)*2.0-1.0;
          float structure=1.0+uGranulation*grain*1.7-lane*0.2+.2*pow(max(0.0,fine-.6)*2.6,2.0);
          if (uKind > 0.5 && uKind < 1.5) {
            vec3 cloud = vLocal; float angle = uTime*0.025;
            cloud.xz = mat2(cos(angle),-sin(angle),sin(angle),cos(angle))*cloud.xz;
            float bands = sin(cloud.y*29.0 + 3.0*noise(cloud*7.0));
            float haze = noise(cloud*20.0)*0.65 + noise(cloud*42.0)*0.35;
            structure = 0.91 + 0.12*bands + 0.08*(haze-0.5);
          } else if (uKind > 1.5 && uKind < 2.5) {
            float latitude = abs(vLocal.y);
            float polar = smoothstep(0.66,0.88,latitude)*(0.5+0.5*sin(atan(vLocal.z,vLocal.x)*3.0));
            structure += polar*0.11;
          } else if (uKind > 2.5) {
            float giantCells = noise(vLocal*6.0+drift*.3)*.7+noise(vLocal*13.0+drift*.2)*.3;
            structure = 0.64+0.52*giantCells+grain*0.06;
          }
          vec3 thermalColor = uThermalPhase >= 0.0 ? mix(uColor,uHotColor,uThermalPhase) : mix(uColor,uCoolColor,-uThermalPhase);
          thermalColor*=mix(vec3(1.0,.74,.52),vec3(1.0),pow(mu,.55));
          gl_FragColor=vec4(thermalColor*uStrength*limb*structure,1.0);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`,
    }))
    this.add(this.surface)
    this.surface.name = 'photosphere'
    const circle = Array.from({ length: 129 }, (_, i) => new Vector3(Math.cos(i / 128 * Math.PI * 2) * 1.13, Math.sin(i / 128 * Math.PI * 2) * 1.13, 0))
    this.outline = new Line(new BufferGeometry().setFromPoints(circle), new LineDashedMaterial({ color: tokenColor('--fg-3'), dashSize: .06, gapSize: .045, depthWrite: false }))
    this.outline.computeLineDistances()
    this.outline.name = 'surface-outline'
    this.outline.visible = false
    this.add(this.outline)
    this.halo = new Sprite(new SpriteMaterial({ map: haloTexture(), transparent: true, opacity: .22, depthWrite: false }))
    this.halo.scale.set(2.5, 2.5, 1)
    this.halo.renderOrder = -1
    this.add(this.halo)
  }
  setTemperature(temperature: number | null): void {
    if(this.lastTemperature===temperature)return
    this.lastTemperature=temperature
    const color = new Color(...temperatureToLinear(temperature))
    this.surface.material.uniforms.uColor.value.copy(color)
    this.surface.material.uniforms.uCoolColor.value.setRGB(...temperatureToLinear(temperature === null ? null : temperature * (1 - SCHEMATIC_TEMPERATURE_FRACTION)))
    this.surface.material.uniforms.uHotColor.value.setRGB(...temperatureToLinear(temperature === null ? null : temperature * (1 + SCHEMATIC_TEMPERATURE_FRACTION)))
    const cold = temperature !== null && temperature < 1000
    this.baseStrength = cold ? .08 : 1
    this.surface.material.uniforms.uBaseStrength.value = this.baseStrength
    this.surface.material.uniforms.uStrength.value = this.baseStrength
    ;(this.halo.material as SpriteMaterial).color.copy(color)
    ;(this.halo.material as SpriteMaterial).opacity = cold ? .016 : .22
  }
  setQuality(quality: Quality): void {
    if (quality === this.quality) return
    this.quality = quality
    this.surface.geometry.dispose()
    this.surface.geometry = buildSurfaceGeometry(quality)
    this.surface.material.uniforms.uGranulation.value = quality === 'high' ? .22 : .16
  }
  setKind(kind: SurfaceKind): void {
    this.surface.material.uniforms.uKind.value = { photosphere: 0, clouds: 1, accreting: 2, giant: 3 }[kind]
  }
  setVisualTime(seconds: number): void { this.surface.material.uniforms.uTime.value = seconds }
  setPulsation(thermalPhase: number): void {
    const phase = Math.max(-1, Math.min(1, thermalPhase))
    this.surface.material.uniforms.uThermalPhase.value = phase
    this.surface.material.uniforms.uStrength.value = this.baseStrength * (1 + SCHEMATIC_TEMPERATURE_FRACTION * phase) ** 4
  }
  faceCamera(camera: Camera): void {
    this.outline.quaternion.copy(this.getWorldQuaternion(new Quaternion()).invert()).multiply(camera.getWorldQuaternion(new Quaternion()))
  }
}

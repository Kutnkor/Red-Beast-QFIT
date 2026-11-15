import { AdditiveBlending, BufferGeometry, Color, Float32BufferAttribute, Group, InstancedMesh, LineBasicMaterial, LineSegments, Matrix4, Points, PointsMaterial, ShaderMaterial, SphereGeometry, Vector3 } from 'three'
import type { BufferAttribute } from 'three'
import type { MotionStar, Vec3 } from '../types'
import type { LabelSpec } from '../labels'
import { position } from '../science/astrometry'
import { temperatureToLinear } from '../science/blackbody'
import { absMag, displayIntensity } from '../science/photometry'
import { buildStarPoints } from './StarPointsMaterial'
import { buildGlowLine } from './lines'
import { translate } from '../../i18n'
export function buildNeighbourhoodPoints(stars: MotionStar[], year: number) {
  return stars.map((star) => {
    const absolute = star.magnitude === undefined ? null : absMag(star.magnitude, star.parallax)
    const intensity = absolute === null ? .06 : displayIntensity(absolute, .0001)
    return { position: position(star, year), color: temperatureToLinear(star.teff_k), intensity: .16 + intensity * .9, sizePx: 12 + intensity * 22, radius: .1 + intensity * .19 }
  })
}
function sphereMaterial(): ShaderMaterial {
  return new ShaderMaterial({
    vertexShader: `varying vec3 vN; varying vec3 vV; varying vec3 vC; varying vec3 vL; varying float vSeed;
      void main() { vec4 mv = modelViewMatrix * instanceMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * mat3(instanceMatrix) * normal); vV = -mv.xyz; vL = position;
        vSeed = fract(dot(instanceMatrix[3].xyz, vec3(12.9898, 78.233, 37.719)) * .37) * 40.0;
        #ifdef USE_INSTANCING_COLOR
          vC = instanceColor;
        #else
          vC = vec3(1.0);
        #endif
        gl_Position = projectionMatrix * mv; }`,
    // An illustrative photosphere: warped granulation, a few darker spots, limb darkening and a thin bright rim.
    fragmentShader: `varying vec3 vN; varying vec3 vV; varying vec3 vC; varying vec3 vL; varying float vSeed;
      float hash(vec3 p) { return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
      float noise(vec3 p) { vec3 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
        return mix(mix(mix(hash(i), hash(i + vec3(1,0,0)), f.x), mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
          mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x), mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y), f.z); }
      float fbm(vec3 p) { float a = .5, s = 0.0; for (int i = 0; i < 4; i++) { s += a * noise(p); p = p * 2.03 + vec3(17.1, 3.7, 9.2); a *= .5; } return s; }
      void main() { float mu = max(0.0, dot(normalize(vN), normalize(vV)));
        vec3 q = vL * 3.2 + vSeed;
        float warp = fbm(q * .8);
        float grain = fbm(q * 2.4 + warp * 2.2);
        float spots = smoothstep(.6, .74, fbm(q * .9 + 5.0));
        float surface = (.72 + .62 * grain) * (1.0 - .5 * spots);
        float limb = .2 + .8 * pow(mu, .62);
        vec3 c = vC * vC * surface * limb * 1.05 + vC * pow(1.0 - mu, 3.0) * .28;
        gl_FragColor = vec4(c, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  })
}
export class Neighbourhood extends Group {
  readonly points: ReturnType<typeof buildStarPoints>
  readonly labels: LabelSpec[]
  readonly stars: MotionStar[]
  private year: number
  private stalks: LineSegments<BufferGeometry, LineBasicMaterial>
  // Each star is a small lit sphere (it grows as you fly in); the point sprite behind it is its glow and the pick target.
  private spheres: InstancedMesh<SphereGeometry, ShaderMaterial>
  private radii: number[]
  private feet: Points<BufferGeometry, PointsMaterial>
  constructor(stars: MotionStar[], year: number, lang: 'en' | 'tr') {
    super()
    this.stars = stars
    this.year = year
    const built = buildNeighbourhoodPoints(stars, year)
    this.points = buildStarPoints(built)
    this.add(this.points)
    this.radii = built.map(b => b.radius)
    this.spheres = new InstancedMesh(new SphereGeometry(1, 32, 20), sphereMaterial(), stars.length + 1)
    built.forEach((b, i) => this.spheres.setColorAt(i, new Color(b.color[0], b.color[1], b.color[2])))
    this.spheres.setColorAt(stars.length, new Color(...temperatureToLinear(5772)))
    this.spheres.frustumCulled = false
    this.add(this.spheres)
    this.add(buildStarPoints([{ position: [0, 0, 0], color: temperatureToLinear(5772), intensity: .42, sizePx: 40 }, { position: [0, 0, 0], color: temperatureToLinear(5772), intensity: .14, sizePx: 92 }]))
    this.labels = [{ id: 'sun', text: translate(lang, 'sky.sun'), position: () => new Vector3(), priority: 13, side: 'left' }]
    // A stalk drops from every star to the reference plane, so height above or below the plane can be read at a glance.
    // drawn as light that thins out towards the plane, with a small foot where it lands
    this.stalks = new LineSegments(new BufferGeometry(), new LineBasicMaterial({ vertexColors: true, transparent: true, depthWrite: false, blending: AdditiveBlending }))
    this.stalks.geometry.setAttribute('position', new Float32BufferAttribute(new Float32Array(stars.length * 6), 3))
    this.stalks.geometry.setAttribute('color', new Float32BufferAttribute(stars.flatMap(() => [.075, .095, .15, 0, 0, 0]), 3))
    this.feet = new Points(new BufferGeometry(), new PointsMaterial({ color: 0x9cb2ee, size: 2.5, sizeAttenuation: false, transparent: true, opacity: .4, depthWrite: false }))
    this.feet.geometry.setAttribute('position', new Float32BufferAttribute(new Float32Array(stars.length * 3), 3))
    this.feet.frustumCulled = false
    this.add(this.feet)
    this.stalks.frustumCulled = false
    this.add(this.stalks)
    this.placeStalks()
    // Stars people know by name are labelled; catalogue-number stars show their name on hover.
    stars.filter(star => !/^(Gaia|2MASS|WISE|LP|LHS|GJ|G )/.test(star.name) && star.distancePc <= 6.5).sort((a, b) => a.distancePc - b.distancePc).slice(0, 1)
      .forEach((star, i) => this.labels.push({ id: `name-${star.id}`, text: star.name, position: () => new Vector3(...position(star, this.year)), priority: 6 - i * .2 }))
    // Which way is the centre of the galaxy from here (ICRS 17h45.6m, -28.94 deg): the link back to the Milky Way view.
    const ra = 266.405 * Math.PI / 180, dec = -28.936 * Math.PI / 180, toCentre = new Vector3(Math.cos(dec) * Math.cos(ra), Math.sin(dec), Math.cos(dec) * Math.sin(ra))
    // a tapering arc that lifts off the plane and ends in an arrowhead, instead of a ruler-straight line
    const lift = new Vector3(0, 1, 0).addScaledVector(toCentre, -toCentre.y).normalize(), a0 = toCentre.clone().multiplyScalar(8.5), a2 = toCentre.clone().multiplyScalar(16.5)
    const a1 = toCentre.clone().multiplyScalar(12.5).addScaledVector(lift, 1.5), curve: Vec3[] = [], glow: Vec3[] = []
    for (let k = 0; k <= 48; k++) { const t = k / 48, u = 1 - t; curve.push(a0.clone().multiplyScalar(u * u).addScaledVector(a1, 2 * u * t).addScaledVector(a2, t * t).toArray() as Vec3); const f = Math.pow(t, 1.4); glow.push([1 * f, .42 * f, .1 * f]) }
    const tangent = a2.clone().sub(a1).normalize(), side = lift.clone().addScaledVector(tangent, -lift.dot(tangent)).normalize()
    const barb = (sign: number) => a2.clone().addScaledVector(tangent, -.8).addScaledVector(side, sign * .36).toArray() as Vec3
    this.add(buildGlowLine(curve, glow, 3), buildGlowLine([barb(1), a2.toArray() as Vec3, barb(-1)], [[1, .42, .1], [1, .42, .1], [1, .42, .1]], 3))
    this.labels.push({ id: 'to-centre', text: lang === 'tr' ? 'Gökada merkezi yönü' : 'Towards the galactic centre', position: () => toCentre.clone().multiplyScalar(16.5), priority: 8, kind: 'representative' })
    for (const radius of [5, 10, 15]) {
      const points: Vec3[] = Array.from({ length: 129 }, (_, i) => [Math.cos(i / 128 * Math.PI * 2) * radius, 0, Math.sin(i / 128 * Math.PI * 2) * radius])
      this.add(buildGlowLine(points, points.map(() => [.035, .045, .08] as Vec3), 1.2))
      if (radius === 10) this.labels.push({ id: `radius-${radius}`, text: lang === 'tr' ? `${Math.round(radius * 3.26156)} ışık yılı` : `${Math.round(radius * 3.26156)} light-years`, position: () => new Vector3(radius, 0, 0), priority: 3 })
    }
  }
  private placeStalks(): void {
    const line = this.stalks.geometry.getAttribute('position') as BufferAttribute, foot = this.feet.geometry.getAttribute('position') as BufferAttribute
    this.stars.forEach((star, index) => { const [x, y, z] = position(star, this.year); line.setXYZ(index * 2, x, y, z); line.setXYZ(index * 2 + 1, x, 0, z); foot.setXYZ(index, x, 0, z) })
    line.needsUpdate = true; foot.needsUpdate = true
    const m = new Matrix4()
    this.stars.forEach((star, index) => { const [x, y, z] = position(star, this.year), r = this.radii[index]; this.spheres.setMatrixAt(index, m.makeScale(r, r, r).setPosition(x, y, z)) })
    this.spheres.setMatrixAt(this.stars.length, m.makeScale(.3, .3, .3).setPosition(0, 0, 0))
    this.spheres.instanceMatrix.needsUpdate = true
  }
  setYear(year: number): void {
    this.year = year
    this.placeStalks()
    const positions = this.points.geometry.getAttribute('position') as BufferAttribute
    this.stars.forEach((star, index) => positions.setXYZ(index, ...position(star, year)))
    positions.needsUpdate = true
    this.points.geometry.computeBoundingSphere()
  }
}

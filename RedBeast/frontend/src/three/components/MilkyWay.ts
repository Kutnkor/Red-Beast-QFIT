// A face-on picture of the Milky Way drawn with particles, so the Sky view starts from something everyone
// recognises. It is an ILLUSTRATION: arms are logarithmic spirals placed after the usual four-arm, barred
// picture (pitch about 12.5 degrees, Sun 8.2 kpc from the centre, between the Sagittarius and Perseus arms).
// Only the target positions drawn on top of it come from catalogue data. 1 scene unit = 1 kiloparsec.
import { AdditiveBlending, BufferGeometry, Color, Float32BufferAttribute, Group, Mesh, MeshBasicMaterial, Points, RingGeometry, ShaderMaterial, Vector3 } from 'three'
import type { PerspectiveCamera } from 'three'
import type { MotionStar, Vec3 } from '../types'
import type { LabelSpec } from '../labels'
import { position } from '../science/astrometry'
import { tokenColor } from '../tokens'
import { buildGlowLine } from './lines'

export const SUN_KPC = 8.2
export const LY_PER_KPC = 3261.56
/** The Sun sits below the centre on screen, as in the familiar top-down picture. */
export const SUN_AT: Vec3 = [0, 0, SUN_KPC]

const K = Math.tan(12.5 * Math.PI / 180), R_IN = 3, R_OUT = 15.5
// Radius of arm j at the Sun's azimuth is 7.0 * exp(K * j * 90deg): 3.5 / 4.9 / 7.0 / 9.9 (and 14 for j = -2 one turn later).
const ARMS = [
  { id: 'scutum', j: -1, weight: 1.25, tr: 'Kalkan–Erboğa Kolu', en: 'Scutum–Centaurus Arm', labelR: 6.3 },
  { id: 'perseus', j: 1, weight: 1.25, tr: 'Perseus Kolu', en: 'Perseus Arm', labelR: 11.3 },
  { id: 'sagittarius', j: 0, weight: .8, tr: 'Yay Kolu', en: 'Sagittarius Arm', labelR: 6.1 },
  { id: 'norma', j: -2, weight: .8, tr: 'Cetvel ve Dış Kol', en: 'Norma and Outer Arm', labelR: 13.2 },
] as const
const armPhi = (r: number, j: number) => Math.log(r / 7) / K - Math.PI / 2 - j * Math.PI / 2
/** Screen angle is counter-clockwise from screen-right when seen from above: the Sun is at -90 degrees. */
const at = (r: number, phi: number, y = 0): Vec3 => [r * Math.cos(phi), y, -r * Math.sin(phi)]

// ICRS -> Galactic rotation (IAU 1958 system, J2000 axes). Input is the scene's Y-up vector (x, z, y).
const G = [[-.0548755604, -.8734370902, -.4838350155], [.4941094279, -.44482963, .7469822445], [-.867666149, -.1980763734, .4559837762]]
/** Catalogue position (parsec, scene axes) to a point on the galaxy map (kiloparsec). */
export function galacticMapPosition(pc: Vec3): Vec3 {
  const e = [pc[0], pc[2], pc[1]]
  const g = G.map(row => (row[0] * e[0] + row[1] * e[1] + row[2] * e[2]) / 1000)
  // towards the centre is up the screen (-z), longitude 90 degrees is to the left (-x), north pole is +y
  return [SUN_AT[0] - g[1], SUN_AT[1] + g[2], SUN_AT[2] - g[0]]
}

function generator(seed: number) {
  let a = seed >>> 0
  const next = () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }
  const normal = () => Math.sqrt(-2 * Math.log(1 - next())) * Math.cos(2 * Math.PI * next())
  return { next, normal }
}

class GalaxyMaterial extends ShaderMaterial {
  constructor() {
    super({ transparent: true, depthWrite: false, depthTest: false, blending: AdditiveBlending, vertexColors: true,
      uniforms: { uPixelRatio: { value: 1 }, uScale: { value: 700 }, uFade: { value: 1 } },
      vertexShader: `
        attribute float size;
        attribute float alpha;
        uniform float uPixelRatio;
        uniform float uScale;
        uniform float uFade;
        varying vec3 vColor;
        varying float vAlpha;
        void main() {
          vColor = color; vAlpha = alpha * uFade;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = clamp(size * uScale * uPixelRatio / max(.001, -mv.z), 1.6 * uPixelRatio, 300.0 * uPixelRatio);
        }`,
      fragmentShader: `
        varying vec3 vColor;
        varying float vAlpha;
        void main() {
          vec2 p = gl_PointCoord * 2.0 - 1.0;
          float d = dot(p, p);
          if (d > 1.0) discard;
          gl_FragColor = vec4(vColor, vAlpha * exp(-d * 3.6) * (1.0 - d));
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }` })
  }
}

function buildParticles(density: number): Points<BufferGeometry, GalaxyMaterial> {
  const rng = generator(20261115), positions: number[] = [], colors: number[] = [], sizes: number[] = [], alphas: number[] = []
  const warm = new Color('#ffbf78'), cream = new Color('#ffe9c4'), cool = new Color('#a9c2ff'), blue = new Color('#6f97ff'), pink = new Color('#ff86a8'), haze = new Color('#4d78f0'), tmp = new Color()
  const put = (p: Vec3, c: Color, size: number, alpha: number) => { positions.push(p[0], p[1], p[2]); colors.push(c.r, c.g, c.b); sizes.push(size); alphas.push(alpha) }
  const n = (count: number) => Math.round(count * density)

  // thin disc: an exponential fall-off that carries the warm-to-cool colour gradient
  for (let i = 0; i < n(24000); i++) {
    const r = Math.min(16.5, -3.4 * Math.log(1 - rng.next() * .992)), phi = rng.next() * Math.PI * 2
    put(at(r, phi, rng.normal() * .12), tmp.copy(warm).lerp(cool, Math.min(1, r / 9)), .1 + rng.next() * .12, .07 + rng.next() * .08)
  }
  // a soft glow under the disc so the arms read as light, not as loose dots
  for (let i = 0; i < n(700); i++) {
    const r = Math.min(14, -3 * Math.log(1 - rng.next() * .98)), phi = rng.next() * Math.PI * 2
    put(at(r, phi), tmp.copy(warm).lerp(haze, Math.min(1, r / 7)), 1.6 + rng.next() * 1.6, .016)
  }
  // bulge and the long bar; the near end of the bar points down-left, towards positive longitude
  for (let i = 0; i < n(8000); i++) put([rng.normal() * 1.05, rng.normal() * .55, rng.normal() * 1.05], tmp.copy(cream).lerp(warm, rng.next()), .13 + rng.next() * .16, .1 + rng.next() * .09)
  const bar = -117 * Math.PI / 180
  for (let i = 0; i < n(8000); i++) {
    const along = Math.max(-4.6, Math.min(4.6, rng.normal() * 2)), across = rng.normal() * .5
    put([along * Math.cos(bar) - across * Math.sin(bar), rng.normal() * .3, -(along * Math.sin(bar) + across * Math.cos(bar))], tmp.copy(cream).lerp(warm, rng.next()), .12 + rng.next() * .14, .09 + rng.next() * .08)
  }
  // spiral arms: stars scattered about each spiral, with bright knots of young clusters and pink gas clouds
  for (const arm of ARMS) {
    const knots = Array.from({ length: 26 }, () => R_IN + rng.next() * (R_OUT - R_IN))
    for (let i = 0; i < n(520 * arm.weight); i++) {
      const r = R_IN + rng.next() * (R_OUT - R_IN) + rng.normal() * .2
      put(at(r, armPhi(r, arm.j) + rng.normal() * .015), haze, .9 + rng.next() * .9, .05 * arm.weight * Math.exp(-(r - R_IN) / 10))
    }
    for (let i = 0; i < n(9500 * arm.weight); i++) {
      const knot = rng.next() < .34 ? knots[Math.floor(rng.next() * knots.length)] : null
      const r0 = knot === null ? R_IN + rng.next() * (R_OUT - R_IN) : knot + rng.normal() * .28
      if (r0 < R_IN - .4 || r0 > R_OUT + .4 || rng.next() > Math.exp(-(r0 - R_IN) / 9)) continue
      const width = knot === null ? .26 + .034 * r0 : .16
      const r = r0 + rng.normal() * width, phi = armPhi(r0, arm.j) + rng.normal() * .02
      const pick = rng.next()
      if (knot !== null && pick < .08) put(at(r, phi, rng.normal() * .06), pink, .22 + rng.next() * .26, .34 * arm.weight)
      else if (pick < .36) put(at(r, phi, rng.normal() * .07), blue, .14 + rng.next() * .14, (.24 + rng.next() * .2) * arm.weight)
      else put(at(r, phi, rng.normal() * .09), tmp.copy(cool).lerp(cream, rng.next() * .45), .1 + rng.next() * .1, (.13 + rng.next() * .14) * arm.weight)
    }
  }
  // the Orion Spur: the short local arm the Sun sits in
  for (let i = 0; i < n(2600); i++) {
    const u = rng.next(), phi = (-132 + u * 80) * Math.PI / 180, r = 7.55 + u * 1.25 + rng.normal() * .2
    put(at(r, phi, rng.normal() * .07), rng.next() < .3 ? blue : tmp.copy(cool).lerp(cream, rng.next() * .5), .08 + rng.next() * .1, (.2 + rng.next() * .16) * Math.sin(Math.PI * Math.min(1, Math.max(0, u))) + .04)
  }
  // glow of the centre
  put([0, 0, 0], warm, 9.5, .1); put([0, 0, 0], warm, 4.6, .14); put([0, 0, 0], cream, 2, .26)

  const geometry = new BufferGeometry()
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3))
  geometry.setAttribute('color', new Float32BufferAttribute(colors, 3))
  geometry.setAttribute('size', new Float32BufferAttribute(sizes, 1))
  geometry.setAttribute('alpha', new Float32BufferAttribute(alphas, 1))
  const points = new Points(geometry, new GalaxyMaterial())
  points.frustumCulled = false
  points.renderOrder = 1
  return points
}

export class MilkyWay extends Group {
  readonly particles: ReturnType<typeof buildParticles>
  private here = new Group()
  private overlay = new Group()
  private targets: { star: MotionStar; at: Vector3 }[] = []
  private reach = 0
  constructor(density = 1) {
    super()
    this.particles = buildParticles(density)
    const orange = tokenColor('--orange'), ring = new Mesh(new RingGeometry(.3, .37, 48), new MeshBasicMaterial({ color: orange, transparent: true, depthTest: false }))
    const dot = new Mesh(new RingGeometry(0, .11, 24), new MeshBasicMaterial({ color: orange, transparent: true, depthTest: false }))
    this.here.add(ring, dot)
    this.here.position.set(...SUN_AT)
    this.here.renderOrder = 20; ring.renderOrder = 20; dot.renderOrder = 21
    this.add(this.particles, this.overlay, this.here)
  }
  /** Draws the catalogue targets at their real places and a ring that holds all of them. */
  setTargets(stars: MotionStar[], year: number): void {
    this.targets = stars.map(star => ({ star, at: new Vector3(...galacticMapPosition(position(star, year))) }))
    const sun = new Vector3(...SUN_AT), reach = Math.max(.25, ...this.targets.map(t => t.at.distanceTo(sun))) * 1.12
    if (Math.abs(reach - this.reach) < 1e-4 && this.overlay.children.length) return
    this.reach = reach
    for (const child of [...this.overlay.children]) { this.overlay.remove(child); (child as unknown as { geometry?: { dispose(): void }; material?: { dispose(): void } }).geometry?.dispose(); (child as unknown as { material?: { dispose(): void } }).material?.dispose() }
    // The Sun's path round the centre: a soft arc that is brightest at the Sun and fades behind it, with an arrowhead
    // ahead (the disc turns clockwise seen from above, so the Sun is heading to the left here).
    const arc: Vec3[] = [], glow: Vec3[] = [], steps = 120, from = -90 + 170, to = -90 - 62
    for (let k = 0; k <= steps; k++) {
      const deg = from + (to - from) * k / steps, behind = deg > -90, t = Math.min(1, Math.abs((deg + 90) / (behind ? 170 : 62)))
      const fade = behind ? Math.pow(1 - t, 1.6) * .9 : .9 * (1 - .6 * t)
      arc.push(at(SUN_KPC, deg * Math.PI / 180)); glow.push([.3 * fade, .36 * fade, .52 * fade])
    }
    const tip = at(SUN_KPC, (to - 3) * Math.PI / 180)
    const chevron = [at(SUN_KPC + .42, (to + 4) * Math.PI / 180), tip, at(SUN_KPC - .42, (to + 4) * Math.PI / 180)]
    const ring = Array.from({ length: 129 }, (_, k) => [SUN_AT[0] + Math.cos(k / 128 * Math.PI * 2) * reach, SUN_AT[1], SUN_AT[2] + Math.sin(k / 128 * Math.PI * 2) * reach] as Vec3)
    this.overlay.add(buildGlowLine(arc, glow, 2), buildGlowLine(chevron, chevron.map(() => [.13, .16, .23] as Vec3), 2),
      buildGlowLine(ring, ring.map(() => [.05, .055, .07] as Vec3), 4.5), buildGlowLine(ring, ring.map(() => [.36, .38, .44] as Vec3), 1.2))
    const mark = new MeshBasicMaterial({ color: tokenColor('--fg'), transparent: true, depthTest: false })
    this.targets.forEach((t, i) => { const m = new Mesh(new RingGeometry(0, .055, 16), mark); m.position.copy(t.at); m.renderOrder = 15; m.userData.target = i; this.overlay.add(m) })
  }
  /** Keeps the markers facing the viewer and the particle size right for the canvas. */
  beforeRender(camera: PerspectiveCamera, viewportHeightPx: number): void {
    this.particles.material.uniforms.uScale.value = viewportHeightPx / (2 * Math.tan(camera.fov * Math.PI / 360))
    this.here.quaternion.copy(camera.quaternion)
    for (const child of this.overlay.children) if (child.userData.target !== undefined) child.quaternion.copy(camera.quaternion)
  }
  set fade(value: number) {
    this.particles.material.uniforms.uFade.value = value
    this.overlay.visible = this.here.visible = value > .5
  }
  labels(lang: 'tr' | 'en', selectedId: string | null, format: (value: number, digits?: number) => string): LabelSpec[] {
    const tr = lang === 'tr', sun = new Vector3(...SUN_AT), reachLy = Math.round(this.reach * LY_PER_KPC / 100) * 100
    const list: LabelSpec[] = [
      { id: 'mw-here', text: tr ? 'Buradayız: Güneş' : 'You are here: the Sun', position: () => sun, priority: 20, kind: 'here' },
      { id: 'mw-path', text: tr ? 'Güneş’in yolu' : 'The Sun’s path', position: () => new Vector3(...at(SUN_KPC, 20 * Math.PI / 180)), priority: 7, kind: 'representative' },
      { id: 'mw-centre', text: tr ? 'Gökada merkezi' : 'Galactic centre', position: () => new Vector3(0, 0, 0), priority: 12, kind: 'representative', side: 'left' },
      // only the two arms on either side of the Sun are named on the map; the rest are in the text beside it
      ...ARMS.filter(arm => arm.id === 'sagittarius' || arm.id === 'perseus').map(arm => ({ id: `mw-${arm.id}`, text: tr ? arm.tr : arm.en, position: () => new Vector3(...at(arm.labelR, armPhi(arm.labelR, arm.j))), priority: 8, kind: 'representative' as const })),
      { id: 'mw-reach', text: tr ? `Beş hedefin hepsi bu halkanın içinde (${format(reachLy, 0)} ışık yılı)` : `All five targets are inside this ring (${format(reachLy, 0)} ly)`,
        position: () => new Vector3(SUN_AT[0] - this.reach * .72, 0, SUN_AT[2] + this.reach * .72), priority: 11, kind: 'computed', side: 'left' },
    ]
    const chosen = this.targets.find(t => t.star.id === selectedId)
    if (chosen && chosen.at.distanceTo(sun) > .12) list.push({ id: 'mw-target', text: `${chosen.star.name} · ${format(chosen.star.distancePc * 3.26156, 0)} ${tr ? 'ışık yılı' : 'ly'}`, position: () => chosen.at, priority: 15, kind: 'computed' })
    return list
  }
}

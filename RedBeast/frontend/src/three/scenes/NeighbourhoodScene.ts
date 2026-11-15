import { Group, Mesh, MeshBasicMaterial, PerspectiveCamera, RingGeometry, Scene, Vector3 } from 'three'
import type { Engine } from '../engine'
import { Controls } from '../controls'
import { tokenColor } from '../tokens'
import { disposeTree } from '../dispose'
import { pickPoint } from '../picking'
import type { LabelSpec } from '../labels'
import type { SceneData, SceneState, Vec3 } from '../types'
import { selectedStar, uniqueCatalogueStars } from '../types'
import { distanceLy, position } from '../science/astrometry'
import { CelestialSphere } from '../components/CelestialSphere'
import { Neighbourhood } from '../components/Neighbourhood'
import { MilkyWay, SUN_AT } from '../components/MilkyWay'
import { buildGlowLine } from '../components/lines'
import type { SkyScene } from './types'
import { translate } from '../../i18n'
/** From the Sun towards a point: faint at the Sun, brighter at the far end. */
function ray(to: Vector3) {
  const points: Vec3[] = [], colors: Vec3[] = []
  for (let k = 0; k <= 24; k++) { const t = k / 24, f = .03 + .3 * t * t; points.push(to.clone().multiplyScalar(t).toArray() as Vec3); colors.push([f * .8, f * .9, f * 1.2]) }
  return buildGlowLine(points, colors, 1.6)
}
export class NeighbourhoodScene implements SkyScene {
  readonly scene = new Scene()
  readonly camera = new PerspectiveCamera(46, 1, .02, 1800)
  controls: Controls | null = null
  private engine: Engine | null = null
  private sky: CelestialSphere | null = null
  private stars: Neighbourhood | null = null
  private ring = new Mesh(new RingGeometry(.4, .44, 64), new MeshBasicMaterial({ color: tokenColor('--fg'), depthTest: false, transparent: true, opacity: .9 }))
  private direction = new Group()
  private state: SceneState | null = null
  private data: SceneData = { catalogue: null, sequence: null, track: null }
  private lastCatalogue: SceneData['catalogue'] = null
  private language = ''
  private active = false
  private hovered: number | null = null
  private removeFrame: (() => void) | null = null
  private pointerDown: [number, number] = [0, 0]
  // Two scales share this scene: the drawn galaxy (1 unit = 1 kpc) and the measured neighbourhood (1 unit = 1 pc).
  private galaxy: MilkyWay | null = null
  private level: 'galaxy' | 'local' | null = null
  private flight: { to: 'galaxy' | 'local'; t: number; swapped: boolean } | null = null
  /** Home pose of the galaxy view. On a wide canvas it is aimed left of the centre so the galaxy sits clear of the
   *  text column; on a tall (phone) canvas it is centred and pulled back until the disc fits the width. */
  private galaxyHome(): { target: Vector3; position: Vector3 } {
    const el = this.engine?.renderer.domElement, aspect = el && el.clientHeight ? el.clientWidth / el.clientHeight : 2
    const wide = aspect > 1.45, target = wide ? new Vector3(-3.4, 0, 1.8) : new Vector3(0, 0, 2.4)
    const distance = wide ? 33.2 : Math.min(74, 13.5 / (Math.tan(23 * Math.PI / 180) * aspect))
    return { target, position: target.clone().add(new Vector3(0, .832, .555).multiplyScalar(distance)) }
  }
  private static readonly LOCAL_HOME = new Vector3(13, 10, 17)
  mount(engine: Engine): void {
    this.engine = engine
    this.scene.background = null
    this.sky = new CelestialSphere(engine.invalidate)
    this.galaxy = new MilkyWay(engine.quality === 'low' ? .45 : engine.quality === 'medium' ? .7 : 1)
    this.scene.add(this.sky, this.ring, this.direction, this.galaxy)
    this.camera.position.set(13, 10, 17)
    this.controls = new Controls(engine, this.camera, 3, 70)
    this.controls.orbit.update()
    this.controls.orbit.saveState()
    this.controls.activate(false)
    this.ring.renderOrder = 500
    engine.renderer.domElement.addEventListener('pointermove', this.pointerMove)
    engine.renderer.domElement.addEventListener('pointerdown', this.pointerStart)
    engine.renderer.domElement.addEventListener('pointerup', this.pointerEnd)
    this.removeFrame = engine.onFrame((_time, delta) => {
      if (!this.active) return
      this.galaxy?.beforeRender(this.camera, engine.renderer.domElement.height / engine.renderer.getPixelRatio() || 640)
      const flying = this.fly(delta)
      this.sky?.beforeRender(this.camera, engine.renderer.getPixelRatio())
      this.ring.quaternion.copy(this.camera.quaternion)
      if (this.stars) this.stars.points.material.uniforms.uPixelRatio.value = engine.renderer.getPixelRatio()
      return flying
    })
  }
  setData(data: SceneData): void { this.data = data }
  update(state: SceneState): void {
    const targetChanged=this.state?.targetId!==state.targetId
    this.state = state
    if (!this.engine || !this.sky) return
    this.sky.update(state, this.data.catalogue, this.data.sequence)
    if (this.lastCatalogue !== this.data.catalogue || this.language !== state.lang) {
      this.lastCatalogue = this.data.catalogue
      this.language = state.lang
      if (this.stars) { this.scene.remove(this.stars); disposeTree(this.stars) }
      const unique = uniqueCatalogueStars(this.data.catalogue).filter(star => star.distancePc <= 15)
      this.stars = new Neighbourhood(unique, state.year, state.lang)
      this.scene.add(this.stars)
    }
    this.stars?.setYear(state.year)
    this.ring.visible = false
    const star = selectedStar(this.data, state)
    const number = (value: number, digits = 2) => new Intl.NumberFormat(state.lang === 'tr' ? 'tr-TR' : 'en-US', { maximumFractionDigits: digits }).format(value)
    disposeTree(this.direction)
    this.galaxy?.setTargets(this.data.catalogue?.targets ?? [], state.year)
    if (this.level && !this.flight) this.show(this.level)
    if (this.level === null) this.land(state.skyScale)
    else if (state.skyScale !== this.level && state.skyScale !== this.flight?.to) {
      if (!this.active || state.reducedMotion || window.matchMedia('(prefers-reduced-motion: reduce)').matches) { this.flight = null; this.land(state.skyScale) }
      else { this.flight = { to: state.skyScale, t: 0, swapped: false }; this.controls?.activate(false); this.engine.labels.set([]); this.engine.invalidate() }
    }
    if (this.flight) return
    if (this.level === 'galaxy') {
      if (this.active) { this.engine.labels.set(this.galaxy?.labels(state.lang, state.targetId, number) ?? []); this.engine.invalidate() }
      return
    }
    const labels: LabelSpec[] = [...this.sky.labels(state, this.data.sequence), ...(this.stars?.labels ?? [])]
    if (star) {
      const p = new Vector3(...position(star, state.year))
      if (p.length() <= 15) {
        this.ring.position.copy(p)
        this.ring.visible = true
        labels.push({ id: 'selected', text: `${star.name} · ${number(distanceLy(star, state.year))} ly`, position: () => p, priority: 14 })
      } else {
        p.setLength(12.5)
        this.direction.add(ray(p))
        labels.push({ id: 'selected-direction', text: `${star.name} · ${translate(state.lang, 'sky.directionOnly')} · ${number(distanceLy(star, state.year), 1)} ly`, position: () => p, priority: 10 })
      }
    } else if (this.data.sequence) {
      const center = this.data.sequence.meta.center, ra = center.ra_deg * Math.PI / 180, dec = center.dec_deg * Math.PI / 180
      const p = new Vector3(Math.cos(dec) * Math.cos(ra), Math.sin(dec), Math.cos(dec) * Math.sin(ra)).multiplyScalar(12.5)
      this.direction.add(ray(p))
      labels.push({ id: 'search-direction', text: `${translate(state.lang, 'sky.thisSearch')} · RA ${number(center.ra_deg, 3)}° · Dec ${number(center.dec_deg, 3)}°`, position: () => p, priority: 10 })
    }
    if (this.hovered !== null && this.stars?.stars[this.hovered]) {
      const hovered = this.stars.stars[this.hovered]
      labels.push({ id: 'hovered', text: `${hovered.name} · ${number(distanceLy(hovered, state.year))} ly · ${hovered.spectralType || '—'}`,
        position: () => new Vector3(...position(hovered, state.year)), priority: 11 })
    }
    if (this.active) { this.engine.labels.set(labels);if(targetChanged)this.focusTarget(); this.engine.invalidate() }
  }
  /** Shows one scale at its home pose. */
  private land(level: 'galaxy' | 'local'): void {
    if (!this.controls || !this.galaxy) return
    this.level = level
    const galaxy = level === 'galaxy', orbit = this.controls.orbit
    this.show(level)
    this.galaxy.fade = 1
    orbit.minDistance = galaxy ? 7 : 3; orbit.maxDistance = galaxy ? 78 : 70
    const home = this.galaxyHome()
    orbit.target.copy(galaxy ? home.target : new Vector3())
    this.camera.position.copy(galaxy ? home.position : NeighbourhoodScene.LOCAL_HOME)
    orbit.update(); orbit.saveState()
    this.controls.activate(this.active)
  }
  private show(level: 'galaxy' | 'local'): void {
    const galaxy = level === 'galaxy'
    if (this.galaxy) this.galaxy.visible = galaxy
    if (this.sky) this.sky.visible = !galaxy
    if (this.stars) this.stars.visible = !galaxy
    this.direction.visible = !galaxy
    if (galaxy) this.ring.visible = false
  }
  /** One camera move between the two scales: dive at the Sun, swap what is drawn, settle. Returns true while it runs. */
  private fly(delta: number): boolean {
    const f = this.flight
    if (!f || !this.controls || !this.galaxy || !this.state) return false
    f.t = Math.min(1, f.t + delta / 1.7)
    const ease = (x: number) => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2, mix = (a: number, b: number, x: number) => a + (b - a) * x
    const sun = new Vector3(...SUN_AT), orbit = this.controls.orbit, home = this.galaxyHome()
    const galaxyPart = f.to === 'local' ? Math.min(1, f.t / .62) : Math.max(0, (f.t - .38) / .62)      // 0 = home pose, 1 = right above the Sun
    const localPart = f.to === 'local' ? Math.max(0, (f.t - .62) / .38) : Math.min(1, f.t / .38)       // 0 = far out, 1 = home pose (reversed below)
    const showGalaxy = f.to === 'local' ? f.t < .62 : f.t >= .38
    if (showGalaxy) {
      const x = ease(f.to === 'local' ? galaxyPart : 1 - galaxyPart)
      this.show('galaxy')
      orbit.target.copy(home.target).lerp(sun, x)
      const offset = home.position.clone().sub(home.target).multiplyScalar(Math.exp(mix(0, Math.log(.035), x)))
      this.camera.position.copy(orbit.target).add(offset)
      this.galaxy.fade = 1 - Math.max(0, (x - .72) / .28)
    } else {
      const x = ease(f.to === 'local' ? localPart : 1 - localPart)
      this.show('local')
      orbit.target.set(0, 0, 0)
      this.camera.position.copy(NeighbourhoodScene.LOCAL_HOME).multiplyScalar(mix(2.6, 1, x))
    }
    this.camera.lookAt(orbit.target)
    if (f.t >= 1) { this.flight = null; this.land(f.to); this.update(this.state) }
    return true
  }
  faceOn(): void {
    if (!this.controls || this.flight) return
    const orbit = this.controls.orbit, distance = this.camera.position.distanceTo(orbit.target)
    this.camera.position.copy(orbit.target).add(new Vector3(0, distance, distance * .002))
    orbit.update(); this.engine?.invalidate()
  }
  focusTarget(): void {
    if (!this.state || !this.controls || this.level !== 'local' || this.flight) return
    const star = selectedStar(this.data, this.state)
    if (!star) return
    const point = new Vector3(...position(star, this.state.year))
    if (point.length() > 15) point.setLength(12.5)
    const direction = this.camera.position.clone().sub(this.controls.orbit.target).normalize()
    this.controls.orbit.target.copy(point)
    this.camera.position.copy(point).addScaledVector(direction, 7)
    this.controls.orbit.update(); this.engine?.invalidate()
  }
  private pointerMove = (event: PointerEvent): void => {
    if (!this.active || !this.stars || !this.engine || event.buttons || this.level !== 'local' || this.flight) return
    const next = pickPoint(this.stars.points, this.camera, this.engine.renderer.domElement, event.clientX, event.clientY)
    if (next !== this.hovered) { this.hovered = next; if (this.state) this.update(this.state) }
    this.engine.renderer.domElement.style.cursor = next === null ? 'grab' : 'pointer'
  }
  private pointerStart = (event: PointerEvent): void => { this.pointerDown = [event.clientX, event.clientY] }
  private pointerEnd = (event: PointerEvent): void => {
    if (!this.active || !this.stars || !this.engine || this.level !== 'local' || this.flight || Math.hypot(event.clientX - this.pointerDown[0], event.clientY - this.pointerDown[1]) > 5) return
    const index = pickPoint(this.stars.points, this.camera, this.engine.renderer.domElement, event.clientX, event.clientY)
    if (index !== null) this.data.onSelectTarget?.(this.stars.stars[index].id)
  }
  activate(active: boolean): void {
    this.active = active
    this.controls?.activate(active && !this.flight)
    if (active) { this.engine?.setActive(this.scene, this.camera); if (this.state) this.update(this.state) }
  }
  summary(lang: 'tr' | 'en'): string {
    const count = this.data.catalogue?.stars.length ?? 0
    if (this.level === 'galaxy') return translate(lang, 'sky.ariaGalaxy')
    return `${translate(lang, 'sky.ariaNeighbors', { count })}. ${translate(lang, 'sky.pointEncoding')}.`
  }
  unmount(): void {
    this.removeFrame?.()
    this.controls?.dispose()
    if (this.engine) {
      this.engine.renderer.domElement.removeEventListener('pointermove', this.pointerMove)
      this.engine.renderer.domElement.removeEventListener('pointerdown', this.pointerStart)
      this.engine.renderer.domElement.removeEventListener('pointerup', this.pointerEnd)
    }
    this.sky?.dispose()
    disposeTree(this.scene)
  }
}

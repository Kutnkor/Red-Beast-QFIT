import { Group, Matrix4, PerspectiveCamera, Quaternion, Scene, Vector3 } from 'three'
import type { Engine } from '../engine'
import { Controls } from '../controls'
import { disposeTree } from '../dispose'
import type { SceneData, SceneState, StellarProfile } from '../types'
import { selectedStar } from '../types'
import { angularShift, compass, displacement, tangentBasis } from '../science/astrometry'
import { CelestialSphere } from '../components/CelestialSphere'
import { MotionTrail } from '../components/MotionTrail'
import { createStellarModel, StellarModel } from '../models/StellarModel'
import type { SkyScene } from './types'
import { translate } from '../../i18n'
import { EvolutionModel } from '../models/EvolutionModel'
import { evolutionAt, evolutionTrack, evolutionDisplayRadius } from '../science/evolution'
import { fitDistance, parameter } from '../science/models'

export class StarScene implements SkyScene {
  readonly scene = new Scene()
  readonly camera = new PerspectiveCamera(43, 1, .02, 1800)
  controls: Controls | null = null
  private engine: Engine | null = null
  private sky: CelestialSphere | null = null
  private model: StellarModel | null = null
  private evolution: EvolutionModel | null = null
  private viewKey = ''
  private framingExtent = 1
  private modelAnchor = new Group()
  private trail: MotionTrail | null = null
  private profile: StellarProfile | null = null
  private centre = new Vector3()
  private visualTime = 0
  private reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  private state: SceneState | null = null
  private data: SceneData = { catalogue: null, sequence: null, track: null }
  private contentKey = ''
  private active = false
  private removeFrame: (() => void) | null = null
  private removeResize: (() => void) | null = null
  private fittedAspect = 1
  mount(engine: Engine): void {
    this.engine = engine
    this.scene.background = null
    this.sky = new CelestialSphere(engine.invalidate)
    this.scene.add(this.sky, this.modelAnchor)
    this.camera.position.set(0, 1, 7)
    this.controls = new Controls(engine, this.camera, 2.2, 16)
    this.controls.activate(false)
    this.removeResize = engine.onResize(() => {
      if (!this.active || !this.model || !this.controls || this.fittedAspect === this.camera.aspect) return
      const previous = fitDistance(this.framingExtent, this.camera.fov, this.fittedAspect)
      const next = fitDistance(this.framingExtent, this.camera.fov, this.camera.aspect)
      const offset = this.camera.position.clone().sub(this.controls.orbit.target).multiplyScalar(next / previous)
      this.camera.position.copy(this.controls.orbit.target).add(offset)
      this.controls.orbit.maxDistance = Math.max(16, next * 2.5)
      this.controls.orbit.saveState()
      this.fittedAspect = this.camera.aspect
    })
    this.removeFrame = engine.onFrame((_time, delta) => {
      if (!this.active) return
      this.sky?.beforeRender(this.camera, engine.renderer.getPixelRatio())
      const evolving = this.state?.stellarMode === 'evolution'
      const animated = !!(evolving ? this.state?.evolutionPlaying : this.state?.surfacePlaying) && !this.reducedMotion && !this.state?.reducedMotion
      if (animated) this.visualTime += delta
      this.model?.update(this.visualTime, this.state?.layers.environment !== false)
      this.model?.faceCamera(this.camera, engine.renderer.getPixelRatio())
      if (evolving && this.evolution && this.state) {
        this.evolution.update(evolutionAt(evolutionTrack(this.state.evolutionTrack), this.state.evolutionProgress), this.visualTime, this.state.layers.environment)
        this.evolution.faceCamera(this.camera)
      }
      return animated
    })
  }
  setData(data: SceneData): void { this.data = data }
  update(state: SceneState): void {
    this.state = state
    if (!this.engine || !this.sky || !this.controls) return
    const star = selectedStar(this.data, state)
    this.sky.update(state, this.data.catalogue, this.data.sequence)
    if (!star) {
      disposeTree(this.modelAnchor)
      this.model = null
      this.evolution = null
      if (this.trail) { this.scene.remove(this.trail); disposeTree(this.trail); this.trail = null }
      this.contentKey = ''
      this.profile = null
      if (this.active) { this.engine.labels.set(this.sky.labels(state, this.data.sequence)); this.engine.invalidate() }
      return
    }
    const sequence = this.data.sequence && (this.data.sequence.params.target_id === star.id || this.data.sequence.meta.target_id === star.id)
      ? this.data.sequence : null
    const profile = this.data.models?.profiles.find(item => item.target_id === star.id) ?? null
    const key = `${star.id}:${sequence?.id}:${state.lang}:${state.quality}:${parameter(profile, 'radius_solar')}:${parameter(profile, 'teff_k')}`
    if (key !== this.contentKey || profile !== this.profile) {
      const targetChanged = !this.contentKey.startsWith(`${star.id}:`) || this.profile !== profile
      if (targetChanged) this.viewKey = ''
      this.contentKey = key
      this.profile = profile
      if (this.trail) { this.scene.remove(this.trail); disposeTree(this.trail) }
      this.trail = new MotionTrail(star, sequence, state.lang)
      this.scene.add(this.trail)
      disposeTree(this.modelAnchor)
      this.model = createStellarModel(star, profile, state.quality, state.lang)
      this.evolution = null
      this.modelAnchor.add(this.model)
      const local = tangentBasis(star.ra, star.dec)
      this.modelAnchor.quaternion.copy(new Quaternion().setFromRotationMatrix(new Matrix4().makeBasis(new Vector3(...local.east), new Vector3(...local.north), new Vector3(...local.radial).negate())))
      if (targetChanged) this.visualTime = 0
    }
    const evolving = state.stellarMode === 'evolution'
    this.model!.visible = !evolving
    if (evolving && !this.evolution) { this.evolution = new EvolutionModel(state.quality); this.modelAnchor.add(this.evolution) }
    if (this.evolution) this.evolution.visible = evolving
    this.model!.traverse(object => { if (object.name === 'solar-radius-reference') object.visible = state.layers.environment && state.sceneFraming === 'context' })
    const viewKey = `${star.id}:${state.stellarMode}:${state.sceneFraming}:${evolving ? state.evolutionTrack : ''}`
    if (viewKey !== this.viewKey) {
      this.viewKey = viewKey
      const track = evolutionTrack(state.evolutionTrack)
      this.framingExtent = evolving ? Math.max(...track.rows.map(row => evolutionDisplayRadius(row[2]))) * 1.2
        : state.sceneFraming === 'context' ? this.model!.extent : this.model!.detailExtent
      const p = new Vector3(...displacement(star, state.year)), local = tangentBasis(star.ra, star.dec)
      this.fittedAspect = this.camera.aspect
      const distance = fitDistance(this.framingExtent, this.camera.fov, this.camera.aspect)
      this.controls.orbit.minDistance = evolving ? .9 : Math.max(.2, this.model!.radius * 1.25)
      this.controls.orbit.maxDistance = Math.max(16, distance * 3)
      this.camera.position.copy(p).addScaledVector(new Vector3(...local.radial), -distance)
      this.camera.up.set(...local.north)
      this.centre.copy(p)
      this.controls.orbit.target.copy(p)
      this.camera.lookAt(p); this.controls.orbit.update(); this.controls.orbit.saveState()
    }
    const next = new Vector3(...displacement(star, state.year))
    const delta = next.clone().sub(this.centre)
    this.centre.copy(next)
    this.camera.position.add(delta)
    this.controls.orbit.target.add(delta)
    this.modelAnchor.position.copy(next)
    this.model!.update(this.visualTime, state.layers.environment !== false)
    this.trail!.visible = state.layers.trail && !evolving && state.sceneFraming === 'context'
    this.trail!.guides.position.copy(next)
    if (this.active) {
      this.engine.labels.set([
        ...(!evolving && state.sceneFraming === 'context' ? this.sky.labels(state, this.data.sequence) : []),
        ...(this.trail!.visible ? this.trail!.labels : []),
        ...(!evolving && state.layers.environment && state.sceneFraming === 'context' ? this.model!.labels : []),
        ...(!evolving && state.sceneFraming === 'context' ? [{ id: 'surface', text: translate(state.lang, 'sky.representativeSurface'), position: () => this.model!.primary.getWorldPosition(new Vector3()).addScaledVector(this.camera.up, -this.model!.radius * 1.25), priority: 10, kind: 'representative' as const },
        { id: 'current-year', text: new Intl.NumberFormat(state.lang === 'tr' ? 'tr-TR' : 'en-US', { maximumFractionDigits: 1, useGrouping: false }).format(state.year), position: () => this.centre.clone().addScaledVector(this.camera.up, this.model!.radius * 1.3), priority: 9, kind: 'computed' as const }] : []),
      ])
      this.engine.invalidate()
    }
  }
  activate(active: boolean): void {
    this.active = active
    this.controls?.activate(active)
    if (active) {
      this.engine?.setActive(this.scene, this.camera)
      if (this.state) this.update(this.state)
    }
  }
  summary(lang: 'tr' | 'en'): string {
    if (!this.state) return ''
    const star = selectedStar(this.data, this.state)
    if (!star) return translate(lang, 'shell.motionLoading')
    const shift = angularShift(star, 2026, this.state.year)
    const number = (value: number) => new Intl.NumberFormat(lang === 'tr' ? 'tr-TR' : 'en-US', { maximumFractionDigits: 2 }).format(value)
    return translate(lang, 'sky.ariaStar', { name: star.name, year: number(this.state.year), shift: number(shift.arcsec), direction: compass(shift.bearingDeg, lang) })
  }
  unmount(): void {
    this.removeFrame?.()
    this.removeResize?.()
    this.controls?.dispose()
    this.sky?.dispose()
    disposeTree(this.scene)
  }
}

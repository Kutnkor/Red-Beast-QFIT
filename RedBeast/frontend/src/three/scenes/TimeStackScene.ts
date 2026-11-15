import { PerspectiveCamera, Scene } from 'three'
import type { Engine } from '../engine'
import { Controls } from '../controls'
import { pickObject } from '../picking'
import type { SceneData, SceneState } from '../types'
import { TimeStack } from '../components/TimeStack'
import type { SkyScene } from './types'
import { translate } from '../../i18n'
export class TimeStackScene implements SkyScene {
  readonly scene = new Scene()
  readonly camera = new PerspectiveCamera(43, 1, .01, 100)
  controls: Controls | null = null
  private engine: Engine | null = null
  private stack: TimeStack | null = null
  private state: SceneState | null = null
  private data: SceneData = { catalogue: null, sequence: null, track: null }
  private active = false
  private pointerDown: [number, number] = [0, 0]
  mount(engine: Engine): void {
    this.engine = engine
    this.scene.background = null
    const radius = 3.25, az = 35 * Math.PI / 180, elevation = 25 * Math.PI / 180
    this.camera.position.set(radius * Math.sin(az) * Math.cos(elevation), radius * Math.sin(elevation), radius * Math.cos(az) * Math.cos(elevation) - .8)
    this.controls = new Controls(engine, this.camera, .6, 12)
    this.controls.orbit.target.set(0, 0, -.8)
    this.controls.orbit.update()
    this.controls.orbit.saveState()
    this.controls.activate(false)
    engine.renderer.domElement.addEventListener('pointerdown', this.pointerStart)
    engine.renderer.domElement.addEventListener('pointerup', this.pointerEnd)
  }
  setData(data: SceneData): void { this.data = data }
  update(state: SceneState): void {
    this.state = state
    if (!this.engine) return
    if (this.stack?.sequence.id !== this.data.sequence?.id) {
      if (this.stack) { this.scene.remove(this.stack); this.stack.dispose(); this.stack = null }
      if (this.data.sequence?.frames.length) {
        this.stack = new TimeStack(this.data.sequence, this.engine.invalidate)
        this.scene.add(this.stack)
      }
    }
    this.stack?.update(state, this.data.track, this.data.marks)
    if (this.active) { this.engine.labels.set(this.stack?.labels(state) ?? []); this.engine.invalidate() }
  }
  activate(active: boolean): void {
    this.active = active
    this.controls?.activate(active)
    if (active) { this.engine?.setActive(this.scene, this.camera); if (this.state) this.update(this.state) }
  }
  faceOn(): void {
    const z = this.stack?.depths[this.state?.frameIndex ?? 0] ?? 0
    this.camera.up.set(0, 1, 0)
    this.camera.position.set(0, 0, z + 1.8)
    this.controls?.orbit.target.set(0, 0, z)
    this.controls?.orbit.update()
    this.engine?.invalidate()
  }
  private pointerStart = (event: PointerEvent): void => { this.pointerDown = [event.clientX, event.clientY] }
  private pointerEnd = (event: PointerEvent): void => {
    if (!this.active || !this.stack || !this.engine || Math.hypot(event.clientX - this.pointerDown[0], event.clientY - this.pointerDown[1]) > 5) return
    const object = pickObject(this.stack.planes.filter((plane) => plane.visible), this.camera, this.engine.renderer.domElement, event.clientX, event.clientY)
    if (object) this.data.onSelectFrame?.(object.userData.frameIndex as number)
  }
  summary(lang: 'tr' | 'en'): string {
    const n = this.data.sequence?.frames.length ?? 0
    return `${translate(lang, 'sky.ariaFrames', { count: n })}. ${translate(lang, 'sky.stackLegend')}.`
  }
  unmount(): void {
    this.controls?.dispose()
    if (this.engine) {
      this.engine.renderer.domElement.removeEventListener('pointerdown', this.pointerStart)
      this.engine.renderer.domElement.removeEventListener('pointerup', this.pointerEnd)
    }
    this.stack?.dispose()
  }
}

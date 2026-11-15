import { Engine } from './engine'
import type { Quality } from './quality'
import type { SceneData, SceneState } from './types'
import type { SkyScene } from './scenes/types'
type SceneKey = 'star' | 'neighbors' | 'timestack'
export class SkyRuntime {
  readonly engine: Engine
  private scenes = new Map<SceneKey, SkyScene>()
  private current: SkyScene | null = null
  private currentKey: SceneKey | null = null
  private state: SceneState
  private data: SceneData
  private version = 0
  private disposed = false
  private onError: (error: string) => void
  private onStatus: (status:'ready'|'lost')=>void
  private removeFrame: () => void
  constructor(canvas: HTMLCanvasElement, labels: HTMLElement, state: SceneState, data: SceneData,
    onStatus: (status: 'ready' | 'lost') => void, onError: (error: string) => void,
    onQuality?: (quality: Quality) => void) {
    this.state = state
    this.data = data
    this.onError = onError
    this.onStatus=onStatus
    this.engine = new Engine(canvas, labels, state.quality, onStatus, onQuality)
    this.removeFrame = this.engine.onAfterFrame(() => {
      const host = canvas.parentElement
      if (host) {
        host.dataset.renderedFrames = String(this.engine.renderedFrames)
        host.dataset.geometries = String(this.engine.renderer.info.memory.geometries)
        host.dataset.textures = String(this.engine.renderer.info.memory.textures)
        host.dataset.quality = this.engine.quality
        host.dataset.scene = this.currentKey ?? 'none'
      }
    })
    window.addEventListener('blinkspace:camera', this.cameraCommand)
    void this.update(state, data)
  }
  async update(state: SceneState, data = this.data): Promise<void> {
    this.state = state
    this.data = data
    if (this.disposed) return
    this.engine.setQuality(state.quality)
    const key: SceneKey | null = state.mode === 'observations' ? (state.stageView === 'timestack' ? 'timestack' : null) : state.mode
    if (key === this.currentKey && this.current) {
      this.current.setData(data)
      if(this.current.controls)this.current.controls.orbit.enableDamping=!state.reducedMotion&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches
      this.current.update(state)
      return
    }
    const version = ++this.version
    this.current?.activate(false)
    this.current = null
    this.currentKey = key
    this.engine.setActive(null, null)
    if (!key) return
    try {
      let scene = this.scenes.get(key)
      if (!scene) {
        if (key === 'star') { const { StarScene } = await import('./scenes/StarScene'); scene = new StarScene() }
        else if (key === 'neighbors') { const { NeighbourhoodScene } = await import('./scenes/NeighbourhoodScene'); scene = new NeighbourhoodScene() }
        else { const { TimeStackScene } = await import('./scenes/TimeStackScene'); scene = new TimeStackScene() }
        if (this.disposed || version !== this.version) return
        scene.mount(this.engine)
        this.scenes.set(key, scene)
      }
      if (this.disposed || version !== this.version) return
      this.current = scene
      scene.setData(this.data)
      scene.update(this.state)
      scene.activate(true)
      this.onStatus('ready')
      this.engine.renderer.domElement.dataset.ready = 'true'
      this.engine.renderer.domElement.parentElement?.setAttribute('data-scene-ready', key)
    } catch (error) { if (!this.disposed&&version===this.version) this.onError(error instanceof Error ? error.message : String(error)) }
  }
  private cameraCommand = (event: Event): void => {
    const { action } = (event as CustomEvent<{ action: string }>).detail
    const controls = this.current?.controls
    if (!controls) return
    if (action === 'zoom-in') controls.zoom(.8)
    else if (action === 'zoom-out') controls.zoom(1.25)
    else if (action === 'reset') controls.reset()
    else if (action === 'up') controls.incline(-.12)
    else if (action === 'down') controls.incline(.12)
    else if (action === 'face-on') this.current?.faceOn?.()
    else if (action === 'focus') this.current?.focusTarget?.()
  }
  dispose(): void {
    this.disposed = true
    this.version++
    window.removeEventListener('blinkspace:camera', this.cameraCommand)
    this.removeFrame()
    this.scenes.forEach((scene) => scene.unmount())
    this.scenes.clear()
    this.engine.dispose()
  }
}

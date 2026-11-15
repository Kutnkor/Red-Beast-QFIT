import { ACESFilmicToneMapping, PerspectiveCamera, SRGBColorSpace, Vector2, WebGLRenderer } from 'three'
import type { Camera, Scene } from 'three'
import { Labels } from './labels'
import { forcedQuality, qualityDpr, QualityMonitor } from './quality'
import type { Quality } from './quality'

type FrameCallback = (time: number, deltaSeconds: number) => boolean | void
export class Engine {
  readonly renderer: WebGLRenderer
  readonly labels: Labels
  readonly size = new Vector2(1, 1)
  quality: Quality
  scene: Scene | null = null
  camera: Camera | null = null
  active = true
  renderedFrames = 0
  private frame = 0
  private lastTime = 0
  private disposed = false
  private lost = false
  private callbacks = new Set<FrameCallback>()
  private afterFrameCallbacks = new Set<() => void>()
  private resizeCallbacks = new Set<() => void>()
  private observer: ResizeObserver
  private monitor = new QualityMonitor()
  private forced = forcedQuality()
  private onStatus: (status: 'ready' | 'lost') => void
  private onQuality?: (quality: Quality) => void
  constructor(canvas: HTMLCanvasElement, labelHost: HTMLElement, quality: Quality,
    onStatus: (status: 'ready' | 'lost') => void, onQuality?: (quality: Quality) => void) {
    // alpha: the scene has no backdrop of its own, so there is no dark rectangle against the page behind it
    this.renderer = new WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance', alpha: true })
    this.renderer.setClearColor(0x000000, 0)
    this.renderer.outputColorSpace = SRGBColorSpace
    this.renderer.toneMapping = ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1
    this.labels = new Labels(labelHost)
    this.quality = this.forced ?? quality
    this.onStatus = onStatus
    this.onQuality = onQuality
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, qualityDpr[this.quality]))
    this.observer = new ResizeObserver(() => this.resize())
    this.observer.observe(canvas.parentElement!)
    canvas.addEventListener('webglcontextlost', this.contextLost)
    canvas.addEventListener('webglcontextrestored', this.contextRestored)
    document.addEventListener('visibilitychange',this.visibilityChanged)
    this.resize()
  }
  private visibilityChanged=()=>{this.lastTime=0;if(!document.hidden)this.invalidate()}
  private contextLost = (event: Event) => {
    event.preventDefault()
    this.lost = true
    cancelAnimationFrame(this.frame)
    this.frame = 0
    this.onStatus('lost')
  }
  private contextRestored = () => {
    this.lost = false
    this.onStatus('ready')
    this.resize()
    this.invalidate()
  }
  private resize(): void {
    const bounds = this.renderer.domElement.parentElement!.getBoundingClientRect()
    const width = Math.max(1, Math.round(bounds.width)), height = Math.max(1, Math.round(bounds.height))
    this.size.set(width, height)
    this.renderer.setSize(width, height, false)
    if (this.camera instanceof PerspectiveCamera) {
      this.camera.aspect = width / height
      this.camera.updateProjectionMatrix()
    }
    this.resizeCallbacks.forEach((callback) => callback())
    this.invalidate()
  }
  setQuality(quality: Quality): void {
    const next = this.forced ?? quality
    if (this.quality === next) return
    this.quality = next
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, qualityDpr[next]))
    this.resize()
  }
  setActive(scene: Scene | null, camera: Camera | null): void {
    this.scene = scene
    this.camera = camera
    this.active = !!scene && !!camera
    this.labels.clear()
    this.resize()
  }
  invalidate = (): void => {
    if (this.frame || this.disposed || this.lost || !this.active) return
    this.frame = requestAnimationFrame(this.render)
  }
  private render = (time: number): void => {
    this.frame = 0
    if (this.disposed || this.lost || !this.active || !this.scene || !this.camera || document.hidden) return
    const gap = this.lastTime ? time - this.lastTime : 0
    const delta = Math.min(.1, gap / 1000)
    const quality = this.forced ? null : this.monitor.sample(gap)
    if (quality && qualityDpr[quality] < qualityDpr[this.quality]) {
      this.setQuality(quality)
      this.onQuality?.(quality)
    }
    this.lastTime = time
    let keepDrawing = false
    this.callbacks.forEach((callback) => { if (callback(time, delta)) keepDrawing = true })
    this.scene.updateMatrixWorld()
    this.camera.updateMatrixWorld()
    this.scene.traverse((object) => {
      const uniforms = (object as typeof object & { material?: { uniforms?: Record<string, { value: unknown }> } }).material?.uniforms
      if (uniforms?.uPixelRatio) uniforms.uPixelRatio.value = this.renderer.getPixelRatio()
    })
    this.renderer.render(this.scene, this.camera)
    this.labels.render(this.camera, this.size.x, this.size.y)
    this.renderedFrames++
    this.afterFrameCallbacks.forEach((callback) => callback())
    if (keepDrawing) this.invalidate()
  }
  onFrame(callback: FrameCallback): () => void { this.callbacks.add(callback); return () => this.callbacks.delete(callback) }
  onAfterFrame(callback: () => void): () => void { this.afterFrameCallbacks.add(callback); return () => this.afterFrameCallbacks.delete(callback) }
  onResize(callback: () => void): () => void { this.resizeCallbacks.add(callback); return () => this.resizeCallbacks.delete(callback) }
  dispose(): void {
    this.disposed = true
    cancelAnimationFrame(this.frame)
    this.observer.disconnect()
    document.removeEventListener('visibilitychange',this.visibilityChanged)
    this.callbacks.clear()
    this.afterFrameCallbacks.clear()
    this.resizeCallbacks.clear()
    this.labels.clear()
    this.renderer.domElement.removeEventListener('webglcontextlost', this.contextLost)
    this.renderer.domElement.removeEventListener('webglcontextrestored', this.contextRestored)
    this.renderer.dispose()
  }
}

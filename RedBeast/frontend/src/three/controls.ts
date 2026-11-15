import { Spherical, Vector3 } from 'three'
import type { PerspectiveCamera } from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import type { Engine } from './engine'
export class Controls {
  readonly orbit: OrbitControls
  private removeFrame: () => void
  private engine: Engine
  constructor(engine: Engine, camera: PerspectiveCamera, minDistance: number, maxDistance: number) {
    this.engine = engine
    this.orbit = new OrbitControls(camera, engine.renderer.domElement)
    this.orbit.enableDamping = !window.matchMedia('(prefers-reduced-motion: reduce)').matches
    this.orbit.dampingFactor = .14
    this.orbit.minDistance = minDistance
    this.orbit.maxDistance = maxDistance
    this.orbit.enablePan = true
    this.orbit.addEventListener('change', engine.invalidate)
    this.removeFrame = engine.onFrame(() => this.orbit.enabled ? this.orbit.update() : false)
  }
  activate(active: boolean): void { this.orbit.enabled = active }
  zoom(factor: number): void {
    const offset = this.orbit.object.position.clone().sub(this.orbit.target)
    offset.setLength(Math.min(this.orbit.maxDistance, Math.max(this.orbit.minDistance, offset.length() * factor)))
    this.orbit.object.position.copy(this.orbit.target).add(offset)
    this.orbit.update()
    this.engine.invalidate()
  }
  incline(radians: number): void {
    const offset = this.orbit.object.position.clone().sub(this.orbit.target)
    const sphere = new Spherical().setFromVector3(offset)
    sphere.phi = Math.max(.05, Math.min(Math.PI - .05, sphere.phi + radians))
    this.orbit.object.position.copy(this.orbit.target).add(new Vector3().setFromSpherical(sphere))
    this.orbit.update()
    this.engine.invalidate()
  }
  reset(): void { this.orbit.reset(); this.engine.invalidate() }
  dispose(): void { this.removeFrame(); this.orbit.removeEventListener('change', this.engine.invalidate); this.orbit.dispose() }
}

import { Group, Vector3 } from 'three'
import type { Camera } from 'three'
import type { Sequence } from '../../lib/types'
import { pixelToSky } from '../../lib/wcs'
import type { LabelSpec } from '../labels'
import { disposeTree } from '../dispose'
import type { MotionCatalogue, SceneState, Vec3 } from '../types'
import { referenceNumber } from '../types'
import { eclipticPoints, graticule, raDecToVector } from '../science/sky'
import { srgbDecode } from '../science/blackbody'
import { displayIntensity } from '../science/photometry'
import { buildLine } from './lines'
import { buildStarPoints } from './StarPointsMaterial'
import type { StarPoint } from './StarPointsMaterial'

const RADIUS = 600
let brightPromise: Promise<Float32Array> | null = null
function loadBrightSky(): Promise<Float32Array> {
  brightPromise ??= fetch('/api/sky/bright.bin').then(async (response) => {
    if (!response.ok) throw new Error(`Hipparcos ${response.status}`)
    const bytes = await response.arrayBuffer()
    if (bytes.byteLength % 28 !== 0) throw new Error('Invalid Hipparcos stride')
    return new Float32Array(bytes)
  }).catch((error: unknown) => { brightPromise = null; throw error })
  return brightPromise
}

export class CelestialSphere extends Group {
  readonly grid = new Group()
  readonly starGroup = new Group()
  readonly footprint = new Group()
  loadedCount = 0
  error: string | null = null
  private binary: Float32Array | null = null
  private quality = ''
  private obliquity: number | null = null
  private sequenceId: string | null = null
  private disposed = false
  private invalidate: () => void
  constructor(invalidate: () => void) {
    super()
    this.invalidate = invalidate
    this.add(this.grid, this.starGroup, this.footprint)
    loadBrightSky().then((data) => {
      if (this.disposed) return
      this.binary = data
      this.buildStars(this.quality || 'high')
      this.invalidate()
    }).catch((error: unknown) => { this.error = String(error); this.invalidate() })
  }
  private buildStars(quality: string): void {
    disposeTree(this.starGroup)
    if (!this.binary) return
    const points: StarPoint[] = []
    for (let i = 0; i < this.binary.length; i += 7) {
      const mag = this.binary[i + 3]
      if (quality === 'low' && mag >= 5) continue
      const intensity = displayIntensity(mag, .003)
      points.push({ position: [this.binary[i] * RADIUS, this.binary[i + 1] * RADIUS, this.binary[i + 2] * RADIUS],
        color: [srgbDecode(this.binary[i + 4]), srgbDecode(this.binary[i + 5]), srgbDecode(this.binary[i + 6])],
        intensity: .18 + intensity * 2.1, sizePx: 2.2 + intensity * 9 })
    }
    const stars = buildStarPoints(points)
    // Transparent renderOrder alone cannot put the sky behind opaque surfaces.
    stars.material.depthTest = true
    stars.material.vertexShader = stars.material.vertexShader.replace(
      'gl_PointSize =', 'gl_Position.z = gl_Position.w * 0.999999;\n          gl_PointSize =')
    stars.renderOrder = -1000
    stars.frustumCulled = false
    this.starGroup.add(stars)
    this.loadedCount = points.length
  }
  private buildGrid(obliquity: number | null): void {
    disposeTree(this.grid)
    for (const points of graticule()) {
      const line = buildLine(points.map((p) => p.map((v) => v * RADIUS) as Vec3), '--rule', 1, .35)
      line.material.depthTest = true
      line.renderOrder = -1001
      this.grid.add(line)
    }
    const equator = Array.from({ length: 181 }, (_, index) => raDecToVector(index * 2, 0).map((v) => v * RADIUS) as Vec3)
    const line = buildLine(equator, '--fg-3', 1, .35)
    line.material.depthTest = true
    line.renderOrder = -1001
    this.grid.add(line)
    if (obliquity !== null) {
      const ecliptic = buildLine(eclipticPoints(obliquity).map((p) => p.map((v) => v * RADIUS) as Vec3), '--fg-3', 1, .3, true)
      ecliptic.material.dashSize = 6
      ecliptic.material.gapSize = 4
      ecliptic.material.depthTest = true
      ecliptic.renderOrder = -1001
      this.grid.add(ecliptic)
    }
  }
  update(state: SceneState, catalogue: MotionCatalogue | null, sequence: Sequence | null): void {
    this.starGroup.visible = state.layers.sky
    this.grid.visible = state.layers.grid
    if (this.quality !== state.quality) { this.quality = state.quality; this.buildStars(state.quality) }
    const obliquity = referenceNumber(catalogue, ['obliquity_j2000_deg'])
    if (!this.grid.children.length || this.obliquity !== obliquity) {
      this.obliquity = obliquity
      this.buildGrid(obliquity)
    }
    if (this.sequenceId !== (sequence?.id ?? null)) {
      this.sequenceId = sequence?.id ?? null
      disposeTree(this.footprint)
      if (sequence) {
        const g = sequence.meta.grid
        const corners = [[-.5, -.5], [g.nx - .5, -.5], [g.nx - .5, g.ny - .5], [-.5, g.ny - .5], [-.5, -.5]]
        const points = corners.map(([x, y]) => {
          const p = pixelToSky(g, x, y)
          return raDecToVector(p.ra, p.dec).map((v) => v * RADIUS) as Vec3
        })
        const edge = buildLine(points, '--fg', 1, .75)
        edge.material.depthTest = true
        edge.renderOrder = -999
        this.footprint.add(edge)
      }
    }
  }
  beforeRender(camera: Camera, pixelRatio: number): void {
    this.position.copy(camera.position)
    this.starGroup.children.forEach((child) => {
      const material = (child as ReturnType<typeof buildStarPoints>).material
      material.uniforms.uPixelRatio.value = pixelRatio
    })
  }
  labels(state: SceneState, sequence: Sequence | null): LabelSpec[] {
    const labels: LabelSpec[] = []
    if (state.layers.grid) {
      const entries: [string, number, number][] = [['0h', 0, 0], ['6h', 90, 0], ['12h', 180, 0], ['18h', 270, 0], ['+30°', 0, 30], ['−30°', 0, -30], ['NCP', 0, 90], ['SCP', 0, -90]]
      for (const [text, ra, dec] of entries) {
        const vector = new Vector3(...raDecToVector(ra, dec)).multiplyScalar(RADIUS)
        labels.push({ id: `sky-${text}`, text, position: () => vector.clone().add(this.position), priority: 0 })
      }
    }
    if (sequence) {
      const centre = new Vector3(...raDecToVector(sequence.meta.center.ra_deg, sequence.meta.center.dec_deg)).multiplyScalar(RADIUS)
      labels.push({ id: 'sky-footprint', text: `SPHEREx · ${(sequence.meta.grid.nx * sequence.meta.grid.pixscale_arcsec / 60).toFixed(1)}′`,
        position: () => centre.clone().add(this.position), priority: 1 })
    }
    return labels
  }
  dispose(): void { this.disposed = true; disposeTree(this) }
}

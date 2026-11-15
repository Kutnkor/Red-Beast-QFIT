import { DoubleSide, Group, Mesh, MeshBasicMaterial, NearestFilter, PlaneGeometry, SRGBColorSpace, TextureLoader, Vector3 } from 'three'
import type { Mark, Sequence } from '../../lib/types'
import type { LabelSpec } from '../labels'
import type { SceneState, SequenceTrack, Vec3 } from '../types'
import { frameDepth, skyToPlane } from '../science/timestack'
import { tokenColor } from '../tokens'
import { buildLine } from './lines'
import { buildStarPoints } from './StarPointsMaterial'
import { disposeTree } from '../dispose'

export class TimeStack extends Group {
  readonly planes: Mesh<PlaneGeometry, MeshBasicMaterial>[] = []
  readonly depths: number[] = []
  readonly labelSpecs: LabelSpec[] = []
  readonly tracks = new Group()
  readonly sequence: Sequence
  private borders: ReturnType<typeof buildLine>[] = []
  private disposed = false
  private lastTrack: SequenceTrack | null = null
  private lastMarks: Mark[] | undefined
  constructor(sequence: Sequence, invalidate: () => void) {
    super()
    this.sequence = sequence
    const { nx, ny } = sequence.meta.grid, height = ny / nx
    const dates = sequence.frames.map((frame) => frame.mjd_avg)
    const first = Math.min(...dates), last = Math.max(...dates)
    const loader = new TextureLoader()
    sequence.frames.forEach((frame, index) => {
      const z = frameDepth(frame.mjd_avg, first, last)
      this.depths[index] = z
      const material = new MeshBasicMaterial({ color: tokenColor('--fg'), transparent: true, opacity: .18, depthWrite: false, side: DoubleSide, toneMapped: false, alphaTest: .005 })
      const plane = new Mesh(new PlaneGeometry(1, height), material)
      plane.position.z = z
      plane.userData.frameIndex = index
      plane.renderOrder = 10
      this.planes.push(plane)
      this.add(plane)
      loader.load(frame.image_url, (texture) => {
        if (this.disposed) { texture.dispose(); return }
        texture.minFilter = texture.magFilter = NearestFilter
        texture.generateMipmaps = false
        texture.colorSpace = SRGBColorSpace
        texture.needsUpdate = true
        material.map = texture
        material.needsUpdate = true
        invalidate()
      }, undefined, () => { plane.userData.imageError = true; invalidate() })
      const border = buildLine([[-.5, -height / 2, z], [.5, -height / 2, z], [.5, height / 2, z], [-.5, height / 2, z], [-.5, -height / 2, z]], '--rule', 1, .8)
      border.renderOrder = 100
      this.borders.push(border)
      this.add(border)
      const p = new Vector3(-.5, height / 2 + .025, z)
      this.labelSpecs.push({ id: `frame-${index}`, text: `#${index + 1} · ${frame.date_avg.slice(0, 10)} · ${frame.lam_um.toFixed(3)} µm · D${frame.detector}`, position: () => p, priority: 3 })
    })
    this.add(this.tracks)
  }
  update(state: SceneState, track: SequenceTrack | null, marks?: Mark[]): void {
    this.planes.forEach((plane, index) => {
      plane.material.opacity = index === state.frameIndex ? 1 : .18
      plane.visible = state.quality !== 'low' || Math.abs(index - state.frameIndex) <= 1
      this.borders[index].visible = plane.visible
      this.borders[index].material.color.copy(tokenColor(index === state.frameIndex ? '--signal' : '--rule'))
      this.borders[index].material.linewidth = index === state.frameIndex ? 1.5 : 1
      this.labelSpecs[index].priority = index === state.frameIndex ? 10 : 3
      const frame = this.sequence.frames[index]
      const wavelength = new Intl.NumberFormat(state.lang === 'tr' ? 'tr-TR' : 'en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(frame.lam_um)
      this.labelSpecs[index].text = `#${index + 1} · ${frame.date_avg.slice(0, 10)} · ${wavelength} µm · D${frame.detector}`
    })
    if (this.lastTrack !== track || this.lastMarks !== marks) {
      this.lastTrack = track
      this.lastMarks = marks
      this.buildTracks(track, marks)
    }
    this.tracks.visible = state.layers.predicted
  }
  private buildTracks(track: SequenceTrack | null, marks?: Mark[]): void {
    disposeTree(this.tracks)
    const grid = this.sequence.meta.grid
    const predicted: Vec3[] = [], measured: { position: Vec3; color: Vec3; intensity: number; sizePx: number }[] = []
    const white = tokenColor('--fg').toArray() as Vec3
    const points = track?.frames ?? this.sequence.frames.map((frame, index) => ({ index, predicted: frame.target_predicted ?? null, measured: null }))
    for (const point of points) {
      const z = this.depths[point.index]
      if (z === undefined) continue
      if (point.predicted) {
        const p = skyToPlane(grid, point.predicted.ra, point.predicted.dec, z)
        if (p) predicted.push(p)
      }
      if (point.measured) {
        const p = skyToPlane(grid, point.measured.ra, point.measured.dec, z + .002)
        if (!p) continue
        measured.push({ position: p, color: white, intensity: 1.5, sizePx: 5 })
        const error = point.measured.err_arcsec
        if (error !== null && error !== undefined && error > 0) {
          const radius = error / grid.pixscale_arcsec / grid.nx
          const ring: Vec3[] = Array.from({ length: 49 }, (_, i) => [p[0] + Math.cos(i / 48 * Math.PI * 2) * radius, p[1] + Math.sin(i / 48 * Math.PI * 2) * radius, p[2]])
          this.tracks.add(buildLine(ring, '--fg', 1, .9))
        }
      }
    }
    if (predicted.length > 1) this.tracks.add(buildLine(predicted, '--signal', 2))
    if (predicted.length === 1) this.tracks.add(buildStarPoints([{ position: predicted[0], color: tokenColor('--signal').toArray() as Vec3, intensity: 1, sizePx: 5 }]))
    if (measured.length) this.tracks.add(buildStarPoints(measured))
    const groups = new Map<string, Mark[]>()
    for (const mark of marks ?? []) if (mark.track_id) groups.set(mark.track_id, [...(groups.get(mark.track_id) ?? []), mark])
    for (const group of groups.values()) {
      const positions = group.sort((a, b) => a.frame_index - b.frame_index).map((mark) =>
        skyToPlane(grid, mark.ra_deg, mark.dec_deg, this.depths[mark.frame_index] ?? 0)).filter((p): p is Vec3 => p !== null)
      if (positions.length > 1) this.tracks.add(buildLine(positions, '--fg', 1, .85, true))
    }
    this.tracks.traverse((child) => { child.renderOrder = 150 })
  }
  labels(state: SceneState): LabelSpec[] {
    return this.labelSpecs.filter((_, index) => state.quality !== 'low' || Math.abs(index - state.frameIndex) <= 1)
  }
  dispose(): void { this.disposed = true; disposeTree(this) }
}

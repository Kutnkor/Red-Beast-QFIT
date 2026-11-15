import { Group, Vector3 } from 'three'
import type { Sequence } from '../../lib/types'
import type { LabelSpec } from '../labels'
import type { MotionStar, Vec3 } from '../types'
import { displacement, mjdToYear, tangentBasis } from '../science/astrometry'
import { buildGlowLine, buildLine } from './lines'
import { buildStarPoints } from './StarPointsMaterial'
import { tokenColor } from '../tokens'
import { translate } from '../../i18n'

export function buildMotionPositions(star: MotionStar): Vec3[] {
  return Array.from({ length: 101 }, (_, index) => displacement(star, 2000 + index))
}
export class MotionTrail extends Group {
  readonly labels: LabelSpec[] = []
  readonly measurements = new Group()
  readonly guides = new Group()
  constructor(star: MotionStar, sequence: Sequence | null, lang: 'tr' | 'en') {
    super()
    const path = buildMotionPositions(star)
    this.add(buildGlowLine(path, path.map((_, k) => { const f = .25 + .75 * k / Math.max(1, path.length - 1); return [1 * f, .42 * f, .1 * f] as Vec3 }), 2.6))
    const basis = tangentBasis(star.ra, star.dec)
    const tick = new Vector3(...basis.east).multiplyScalar(.04)
    for (let year = 2000; year <= 2100; year += 10) {
      const position = new Vector3(...displacement(star, year))
      this.add(buildLine([position.clone().sub(tick).toArray() as Vec3, position.clone().add(tick).toArray() as Vec3], '--signal', 1, .8))
      if (year === 2000 || year === 2050 || year === 2100) this.labels.push({ id: `trail-${year}`, text: `${year}`, position: () => position, priority: 3, kind: 'computed' })
    }
    if (sequence?.frames.length) {
      const color = tokenColor('--fg').toArray() as Vec3
      const ordered = [...sequence.frames].sort((a, b) => a.mjd_avg - b.mjd_avg)
      const points = ordered.map((frame) => ({ position: displacement(star, mjdToYear(frame.mjd_avg)), color, intensity: 1.5, sizePx: 4 }))
      this.measurements.add(buildStarPoints(points))
      if (points.length > 1) this.measurements.add(buildLine([points[0].position, points.at(-1)!.position], '--fg', 3))
      this.labels.push({ id: 'trail-spherex',
        text: `SPHEREx · ${translate(lang, 'sky.frameCount', { count: points.length })} · ${ordered[0].date_avg.slice(0, 7)} → ${ordered.at(-1)!.date_avg.slice(0, 7)}`,
        position: () => new Vector3(...points[0].position), priority: 8 })
      this.add(this.measurements)
    }
    const sun = new Vector3(...basis.radial).multiplyScalar(-1.8)
    this.guides.add(buildLine([[0, 0, 0], sun.toArray() as Vec3], '--fg-3', 1, .65, true))
    this.labels.push({ id: 'toward-sun', text: translate(lang, 'sky.towardSun'), position: () => sun.clone().add(this.guides.position), priority: 1 })
    const north = new Vector3(...basis.north).multiplyScalar(1.65)
    const east = new Vector3(...basis.east).multiplyScalar(1.65)
    this.guides.add(buildLine([[0, 0, 0], north.toArray() as Vec3], '--fg-3', 1, .45), buildLine([[0, 0, 0], east.toArray() as Vec3], '--fg-3', 1, .45))
    this.add(this.guides)
    this.labels.push({ id: 'north', text: 'N', position: () => north.clone().add(this.guides.position), priority: 4 }, { id: 'east', text: 'E', position: () => east.clone().add(this.guides.position), priority: 4 })
  }
}

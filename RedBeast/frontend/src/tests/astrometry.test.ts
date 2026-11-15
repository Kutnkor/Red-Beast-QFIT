import { describe, expect, it } from 'vitest'
import golden from './golden/motion.json'
import type { MotionStar } from '../three/types'
import { angularShift, compass, displacement, distanceLy, mjdToYear, position } from '../three/science/astrometry'

function star(id: string): MotionStar {
  return { ...golden.stars.find((entry) => entry.id === id)!.input, teff_k: null, teff_source: 'none' } as MotionStar
}
describe('independent Astropy Cartesian-motion references', () => {
  for (const entry of golden.stars) for (const reference of entry.positions) {
    it(`${entry.id} J${reference.year} matches Astropy to <1e-9 pc`, () => {
      const result = position(star(entry.id), reference.year)
      result.forEach((value, axis) => expect(Math.abs(value - reference.three_pc[axis])).toBeLessThan(1e-9))
    })
  }
  it('Barnard 2026–2100 is 773.5937 arcsec in the specified Cartesian model', () => {
    const shift = angularShift(star('barnard'), 2026, 2100)
    // Independent spherical separation of Astropy golden positions. The plan's ~769″
    // approximation omits the perspective term introduced by the measured radial velocity.
    expect(shift.arcsec).toBeCloseTo(773.5937236354325, 7)
    expect(shift.bearingDeg).toBeGreaterThan(350)
    expect(shift.bearingDeg).toBeLessThan(360)
    expect(shift.eastArcsec).toBeLessThan(0)
    expect(shift.northArcsec).toBeGreaterThan(760)
    expect(compass(shift.bearingDeg)).toBe('north')
  })
  it('the two slow variables move less than 10 arcsec in 100 years', () => {
    for (const id of ['rw-aur', 'r-dra']) expect(angularShift(star(id), 2000, 2100).arcsec).toBeLessThan(10)
  })
  it('does not invent radial velocities', () => {
    const source = star('wise-0855')
    expect(source.hasRadialVelocity).toBe(false)
    expect(position({ ...source, radialVelocity: 500 }, 2100)).toEqual(position(source, 2100))
  })
  it('keeps identical-year displacement zero, exact Julian-year conversion, distance positive', () => {
    expect(displacement(star('barnard'), 2026)).toEqual([0, 0, 0])
    expect(angularShift(star('barnard'), 2026, 2026).arcsec).toBe(0)
    expect(mjdToYear(51544.5)).toBe(2000)
    expect(distanceLy(star('barnard'))).toBeGreaterThan(5.9)
  })
})

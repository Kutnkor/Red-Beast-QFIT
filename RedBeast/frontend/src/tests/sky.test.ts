import { describe, expect, it } from 'vitest'
import { eclipticPoints, graticule, raDecToVector } from '../three/science/sky'
import { absMag, displayIntensity, flux } from '../three/science/photometry'
import { teffFromBV } from '../three/science/teff'
import { frameDepth, pixelToPlane, skyToPlane } from '../three/science/timestack'
import { qualityForAverage } from '../three/quality'
import type { Grid } from '../lib/types'
import { pixelToSky } from '../lib/wcs'

describe('scientific sky geometry', () => {
  it('maps the ICRS poles to Y and equinox to X', () => {
    const north = raDecToVector(45, 90), zero = raDecToVector(0, 0), six = raDecToVector(90, 0)
    expect(north[1]).toBeCloseTo(1, 14)
    expect(zero).toEqual([1, 0, 0])
    expect(six[2]).toBeCloseTo(1, 14)
  })
  it('ecliptic uses the supplied obliquity and crosses both equinoxes', () => {
    const obliquity = 23.439279444444445, points = eclipticPoints(obliquity, 90)
    expect(points[0]).toEqual([1, 0, 0])
    expect(points[1][1]).toBeCloseTo(Math.sin(obliquity * Math.PI / 180), 14)
    expect(points[2][0]).toBeCloseTo(-1, 14)
    for (const point of points) expect(Math.hypot(...point)).toBeCloseTo(1, 14)
  })
  it('graticule points are unit vectors, not a decorative random field', () => {
    expect(graticule()).toHaveLength(23)
    for (const line of graticule()) for (const p of line) expect(Math.hypot(...p)).toBeCloseTo(1, 12)
  })
})
describe('photometric display and temperature', () => {
  it('five magnitudes correspond to a factor of 100 in flux', () => expect(flux(0) / flux(5)).toBeCloseTo(100, 10))
  it('asinh display intensity is bounded and monotone', () => {
    const values = [-5, 0, 5, 10, 15, 20].map((magnitude) => displayIntensity(magnitude))
    values.forEach((value) => { expect(value).toBeGreaterThanOrEqual(0); expect(value).toBeLessThanOrEqual(1) })
    for (let i = 1; i < values.length; i++) expect(values[i]).toBeLessThanOrEqual(values[i - 1])
    expect(absMag(6, 100)).toBe(6)
    expect(absMag(6, 10)).toBe(1)
  })
  it('Ballesteros BV=0.65 is about 5778 K; unknown data remain null', () => {
    expect(teffFromBV(.65)).toBeCloseTo(5778.423731066208, 8)
    expect(teffFromBV(null)).toBeNull()
    expect(teffFromBV(NaN)).toBeNull()
  })
})
describe('time-stack geometry and image orientation', () => {
  const grid: Grid = { projection: 'TAN', nx: 80, ny: 40, crval: [269.4, 4.7], crpix: [40.5, 20.5], cdelt: [-6.15 / 3600, 6.15 / 3600], pixscale_arcsec: 6.15 }
  it('keeps unequal observing intervals proportional to depth', () => {
    expect(frameDepth(60000, 60000, 60100)).toBe(0)
    expect(frameDepth(60025, 60000, 60100)).toBe(-.4)
    expect(frameDepth(60100, 60000, 60100)).toBe(-1.6)
    expect(frameDepth(60000, 60000, 60000)).toBe(0)
  })
  it('fits pixel centres, non-square aspect, west-right and north-up', () => {
    expect(pixelToPlane(grid, 39.5, 19.5, -.8)).toEqual([0, 0, -.8])
    expect(pixelToPlane(grid, -.5, -.5, 0)).toEqual([-.5, -.25, 0])
    const east = skyToPlane(grid, 269.401, 4.7, 0)!
    const north = skyToPlane(grid, 269.4, 4.701, 0)!
    expect(east[0]).toBeLessThan(0)
    expect(north[1]).toBeGreaterThan(0)
    const knownSky = pixelToSky(grid, 12, 34)
    const point = skyToPlane(grid, knownSky.ra, knownSky.dec, 0)!
    const expected = pixelToPlane(grid, 12, 34, 0)
    point.forEach((value, axis) => expect(value).toBeCloseTo(expected[axis], 10))
  })
  it('drops quality only at the specified thresholds', () => {
    expect(qualityForAverage(16)).toBe('high')
    expect(qualityForAverage(22.1)).toBe('medium')
    expect(qualityForAverage(33.1)).toBe('low')
  })
})

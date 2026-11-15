import { describe, expect, it } from 'vitest'
import { evolutionAt, evolutionDisplayRadius, evolutionTracks } from '../three/science/evolution'
import { angularSeparation, parseSkyQuery, position, skyCoordinates } from '../three/science/astrometry'
import catalogue from '../../../backend/blinkspace/resources/motion_catalogue.json'

describe('published stellar evolution tables', () => {
  it.each(evolutionTracks)('$id has chronological, finite physical samples consistent with Stefan–Boltzmann', track => {
    expect(track.rows.length).toBeGreaterThan(10)
    track.rows.forEach((row, i) => {
      if (i) expect(row[0]).toBeGreaterThan(track.rows[i - 1][0])
      for (const value of row.slice(0, 5)) expect(value).toBeGreaterThan(0)
      // Different published solar reference constants and rounded BHAC radii permit ~3%.
      expect(Math.abs(row[3] / (row[2] ** 2 * (row[1] / 5772) ** 4) - 1)).toBeLessThan(.035)
    })
  })
  it.each(evolutionTracks)('$id respects both endpoints and preserves intermediate physical bounds', track => {
    expect(evolutionAt(track, -1).age).toBeCloseTo(track.rows[0][0], 3)
    expect(evolutionAt(track, 2).radius).toBeCloseTo(track.rows.at(-1)![2], 10)
    for (let i = 0; i < track.rows.length - 1; i += 7) {
      const sample = evolutionAt(track, (i + .5) / (track.rows.length - 1))
      expect(sample.temperature).toBeGreaterThanOrEqual(Math.min(track.rows[i][1], track.rows[i + 1][1]) - 1e-8)
      expect(sample.temperature).toBeLessThanOrEqual(Math.max(track.rows[i][1], track.rows[i + 1][1]) + 1e-8)
    }
  })
  it('keeps low-mass and brown dwarf sequences out of giant/explosion phases', () => {
    for (const track of evolutionTracks.filter(t => t.mass < .2)) expect(track.rows.every(r => r[5] < 0)).toBe(true)
    const cold = evolutionTracks.find(t => t.id === 'atmo-0.005')!
    expect(cold.rows.some(r => r[1] < 250)).toBe(true)
    expect(cold.rows.every(r => r[1] < 2000)).toBe(true)
    expect(evolutionDisplayRadius(.01)).toBeLessThan(evolutionDisplayRadius(1))
    expect(evolutionDisplayRadius(1)).toBeLessThan(evolutionDisplayRadius(200))
  })
})
describe('position search uses the same astrometry as the 3D scene', () => {
  it('round-trips 3D positions into RA/Dec at both catalogue and future epochs', () => {
    for (const star of catalogue.targets) for (const year of [star.epoch, 2026, 2100]) {
      const c = skyCoordinates(star, year), p = position(star, year), r = Math.PI / 180
      const back = [Math.cos(c.dec*r)*Math.cos(c.ra*r), Math.sin(c.dec*r), Math.cos(c.dec*r)*Math.sin(c.ra*r)]
      back.forEach((v, i) => expect(v*c.distancePc).toBeCloseTo(p[i], 9))
    }
  })
  it('handles RA wrap, poles and invalid coordinate searches', () => {
    expect(angularSeparation({ra:359.9,dec:0},{ra:.1,dec:0})).toBeCloseTo(.2, 10)
    expect(angularSeparation({ra:20,dec:90},{ra:120,dec:90})).toBeCloseTo(0, 10)
    expect(parseSkyQuery('269.4463, +4.7682')).toEqual({ra:269.4463,dec:4.7682})
    for (const text of ['360, 0','1, 91','-1,0','NaN,0','Barnard']) expect(parseSkyQuery(text)).toBeNull()
  })
})

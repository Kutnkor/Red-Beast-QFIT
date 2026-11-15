import { describe, expect, it } from 'vitest'
import { roundTiesEven, srgbDecode, srgbEncode, temperatureToRgb } from '../three/science/blackbody'
// Exact fixtures from the supplied stellar-lifecycle/contract/golden/cases.json: colour only.
const cases: [number, number[]][] = [[500, [255, 48, 0]], [1000, [255, 48, 0]], [2000, [255, 141, 21]],
  [3660, [255, 204, 148]], [5772, [255, 241, 234]], [10000, [205, 217, 255]], [40000, [158, 184, 255]], [1e6, [158, 184, 255]]]
describe('Planck × Wyman CMF → sRGB Python golden port', () => {
  for (const [temperature, rgb] of cases) it(`${temperature} K matches every 8-bit channel exactly`, () => {
    expect(temperatureToRgb(temperature)).toEqual(rgb)
  })
  it('uses Python ties-to-even, not JavaScript ties upward', () => {
    expect([.5, 1.5, 2.5, 3.5].map(roundTiesEven)).toEqual([0, 2, 2, 4])
  })
  it('rejects invalid temperatures', () => {
    for (const temperature of [NaN, Infinity, 0, -1]) expect(() => temperatureToRgb(temperature)).toThrow()
  })
  it('decodes physical sRGB data before the rendering colour pipeline', () => {
    for (const value of [0, .01, .2, .8, 1]) expect(srgbEncode(srgbDecode(value))).toBeCloseTo(value, 10)
  })
})

import { describe, expect, it } from 'vitest'
import { SUN_AT, SUN_KPC, galacticMapPosition } from '../three/components/MilkyWay'
import type { Vec3 } from '../three/types'

/** Scene axes are ICRS with Y up: (cos d cos a, sin d, cos d sin a). */
const direction = (raDeg: number, decDeg: number, pc: number): Vec3 => {
  const a = raDeg * Math.PI / 180, d = decDeg * Math.PI / 180
  return [pc * Math.cos(d) * Math.cos(a), pc * Math.sin(d), pc * Math.cos(d) * Math.sin(a)]
}
const close = (got: Vec3, want: Vec3) => got.forEach((v, i) => expect(v).toBeCloseTo(want[i], 2))

describe('Milky Way map placement', () => {
  it('puts a point at the Sun’s distance towards the galactic centre on the centre of the map', () => {
    close(galacticMapPosition(direction(266.405, -28.936, SUN_KPC * 1000)), [0, 0, 0])
  })
  it('puts the north galactic pole straight above the Sun', () => {
    close(galacticMapPosition(direction(192.859, 27.128, 1000)), [SUN_AT[0], SUN_AT[1] + 1, SUN_AT[2]])
  })
  it('puts galactic longitude 90 degrees to the left of the Sun, as in the usual top-down picture', () => {
    close(galacticMapPosition(direction(318.004, 48.33, 1000)), [SUN_AT[0] - 1, SUN_AT[1], SUN_AT[2]])
  })
  it('keeps nearby stars next to the Sun', () => {
    const barnard = galacticMapPosition(direction(269.45, 4.74, 1.83))
    expect(Math.hypot(barnard[0] - SUN_AT[0], barnard[1] - SUN_AT[1], barnard[2] - SUN_AT[2])).toBeCloseTo(.00183, 5)
  })
})

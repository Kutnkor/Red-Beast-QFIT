import type { Grid } from '../../lib/types'
import { skyToPixel } from '../../lib/wcs'
import type { Vec3 } from '../types'
export function frameDepth(mjd: number, first: number, last: number): number {
  return last > first && mjd !== first ? -1.6 * (mjd - first) / (last - first) : 0
}
/** FITS pixel centres; north is +y, east is -x. Plane height is ny/nx. */
export function pixelToPlane(grid: Pick<Grid, 'nx' | 'ny'>, x: number, y: number, z: number): Vec3 {
  return [(x + .5) / grid.nx - .5, ((y + .5) / grid.ny - .5) * grid.ny / grid.nx, z]
}
export function skyToPlane(grid: Grid, ra: number, dec: number, z: number): Vec3 | null {
  const pixel = skyToPixel(grid, ra, dec)
  return pixel ? pixelToPlane(grid, pixel.x, pixel.y, z) : null
}

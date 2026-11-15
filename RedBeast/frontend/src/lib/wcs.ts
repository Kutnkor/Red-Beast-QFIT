// Exact gnomonic (TAN) projection for the common BlinkSpace grid.
//
// Conventions
//   FITS pixel  : 0-based (x, y), fractional. x grows WEST (cdelt1 < 0), y grows NORTH. No rotation.
//                 crpix is 1-based, so the reference pixel is (crpix - 1) in 0-based coordinates.
//   PNG pixel   : continuous image space, origin at the top-left corner of the image; the first row is NORTH.
//                 Column c covers [c, c+1), row r covers [r, r+1).
//                 centre of FITS pixel (x, y)  ->  png (x + 0.5, ny - 0.5 - y)

export interface WcsGrid {
  crval: [number, number]
  crpix: [number, number]
  cdelt: [number, number]
  nx: number
  ny: number
}

export interface Sky {
  ra: number
  dec: number
}

export interface Pixel {
  x: number
  y: number
}

const D2R = Math.PI / 180
const R2D = 180 / Math.PI

export function normalizeRa(ra: number): number {
  const r = ra % 360
  return r < 0 ? r + 360 : r
}

/** Sky (deg) -> 0-based fractional FITS pixel. Returns null on the far hemisphere (not projectable). */
export function skyToPixel(grid: WcsGrid, ra: number, dec: number): Pixel | null {
  const ra0 = grid.crval[0] * D2R
  const dec0 = grid.crval[1] * D2R
  const a = ra * D2R
  const d = dec * D2R
  const da = a - ra0
  const sinD = Math.sin(d)
  const cosD = Math.cos(d)
  const sinD0 = Math.sin(dec0)
  const cosD0 = Math.cos(dec0)
  const cosDa = Math.cos(da)
  const cosc = sinD0 * sinD + cosD0 * cosD * cosDa
  if (!(cosc > 1e-12)) return null
  const xi = ((cosD * Math.sin(da)) / cosc) * R2D
  const eta = ((cosD0 * sinD - sinD0 * cosD * cosDa) / cosc) * R2D
  return {
    x: grid.crpix[0] - 1 + xi / grid.cdelt[0],
    y: grid.crpix[1] - 1 + eta / grid.cdelt[1],
  }
}

/** 0-based fractional FITS pixel -> sky (deg), RA normalised to [0, 360). */
export function pixelToSky(grid: WcsGrid, x: number, y: number): Sky {
  const ra0 = grid.crval[0] * D2R
  const dec0 = grid.crval[1] * D2R
  const xi = (x - (grid.crpix[0] - 1)) * grid.cdelt[0] * D2R
  const eta = (y - (grid.crpix[1] - 1)) * grid.cdelt[1] * D2R
  const sinD0 = Math.sin(dec0)
  const cosD0 = Math.cos(dec0)
  const denom = cosD0 - eta * sinD0
  const ra = ra0 + Math.atan2(xi, denom)
  const dec = Math.atan2(sinD0 + eta * cosD0, Math.hypot(xi, denom))
  return { ra: normalizeRa(ra * R2D), dec: dec * R2D }
}

export function pixelToPng(grid: WcsGrid, x: number, y: number): Pixel {
  return { x: x + 0.5, y: grid.ny - 0.5 - y }
}

export function pngToPixel(grid: WcsGrid, px: number, py: number): Pixel {
  return { x: px - 0.5, y: grid.ny - 0.5 - py }
}

export function skyToPng(grid: WcsGrid, ra: number, dec: number): Pixel | null {
  const p = skyToPixel(grid, ra, dec)
  return p ? pixelToPng(grid, p.x, p.y) : null
}

export function pngToSky(grid: WcsGrid, px: number, py: number): Sky {
  const p = pngToPixel(grid, px, py)
  return pixelToSky(grid, p.x, p.y)
}

/** Great-circle separation in arcseconds (haversine; stable for small angles). */
export function separationArcsec(a: Sky, b: Sky): number {
  const d1 = a.dec * D2R
  const d2 = b.dec * D2R
  const dd = d2 - d1
  const da = (b.ra - a.ra) * D2R
  const h = Math.sin(dd / 2) ** 2 + Math.cos(d1) * Math.cos(d2) * Math.sin(da / 2) ** 2
  return 2 * Math.asin(Math.min(1, Math.sqrt(h))) * R2D * 3600
}

export function pixscaleArcsec(grid: WcsGrid): number {
  return Math.abs(grid.cdelt[1]) * 3600
}

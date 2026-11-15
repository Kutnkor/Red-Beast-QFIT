import { describe, expect, it } from 'vitest'
import { pixelToPng, pixelToSky, pngToPixel, pngToSky, separationArcsec, skyToPixel, skyToPng, type WcsGrid } from '../lib/wcs'

const S = 6.15 / 3600

function grid(ra0: number, dec0: number, n = 59): WcsGrid {
  return { crval: [ra0, dec0], crpix: [(n + 1) / 2, (n + 1) / 2], cdelt: [-S, S], nx: n, ny: n }
}

// the real Barnard's Star grid served by the backend
const BARNARD = grid(269.446269, 4.768204)

describe('TAN projection', () => {
  it('maps the reference pixel to crval and back', () => {
    const sky = pixelToSky(BARNARD, 29, 29)
    expect(sky.ra).toBeCloseTo(269.446269, 12)
    expect(sky.dec).toBeCloseTo(4.768204, 12)
    const px = skyToPixel(BARNARD, 269.446269, 4.768204)
    expect(px?.x).toBeCloseTo(29, 10)
    expect(px?.y).toBeCloseTo(29, 10)
  })

  it('+1 pixel in y is one pixel scale to the north', () => {
    const a = pixelToSky(BARNARD, 29, 29)
    const b = pixelToSky(BARNARD, 29, 30)
    expect(b.dec).toBeGreaterThan(a.dec)
    expect((b.dec - a.dec) * 3600).toBeCloseTo(6.15, 6)
    expect(b.ra).toBeCloseTo(a.ra, 9)
  })

  it('+1 pixel in x is one pixel scale to the west (RA decreases)', () => {
    const a = pixelToSky(BARNARD, 29, 29)
    const b = pixelToSky(BARNARD, 30, 29)
    expect(b.ra).toBeLessThan(a.ra)
    expect(separationArcsec(a, b)).toBeCloseTo(6.15, 6)
    // on the sky the RA step is scaled by 1/cos(dec)
    expect(((a.ra - b.ra) * 3600 * Math.cos((a.dec * Math.PI) / 180))).toBeCloseTo(6.15, 4)
  })

  it('reproduces positions computed by the backend (astropy) for automatic candidates', () => {
    // /api/sequences/<barnard>/candidates?a=0&b=5: pixel (x, y) and sky (ra, dec) pairs, rounded to 1e-6 deg
    const cases: [number, number, number, number][] = [
      [30.69, 33.87, 269.443372, 4.776524],
      [45.0, 7.5, 269.418842, 4.731474],
      [7.0, 19.52, 269.483982, 4.752008],
      [58.0, 32.0, 269.396555, 4.773327],
    ]
    for (const [x, y, ra, dec] of cases) {
      const sky = pixelToSky(BARNARD, x, y)
      expect(Math.abs(sky.ra - ra)).toBeLessThan(1.5e-6)
      expect(Math.abs(sky.dec - dec)).toBeLessThan(1.5e-6)
    }
  })

  it('round-trips to better than 1e-9 degrees across the field', () => {
    for (const g of [BARNARD, grid(133.759765, -7.242186), grid(40, 80), grid(200, -80), grid(10, 0, 293)]) {
      for (const [x, y] of [
        [0, 0],
        [g.nx - 1, 0],
        [0, g.ny - 1],
        [g.nx - 1, g.ny - 1],
        [12.3, 44.7],
        [-3.5, g.ny + 2.25],
      ]) {
        const sky = pixelToSky(g, x, y)
        const back = skyToPixel(g, sky.ra, sky.dec)
        expect(back).not.toBeNull()
        // 1e-9 deg expressed in pixels
        expect(Math.abs((back as { x: number }).x - x) * S).toBeLessThan(1e-9)
        expect(Math.abs((back as { y: number }).y - y) * S).toBeLessThan(1e-9)
        const again = pixelToSky(g, (back as { x: number }).x, (back as { y: number }).y)
        expect(Math.abs(again.dec - sky.dec)).toBeLessThan(1e-9)
        const dra = Math.abs(again.ra - sky.ra)
        expect(Math.min(dra, 360 - dra)).toBeLessThan(1e-9)
      }
    }
  })

  it('works across the RA = 0/360 wrap', () => {
    const g = grid(0.001, 20)
    const west = pixelToSky(g, g.nx - 1, 29) // west of centre: RA wraps below zero
    const east = pixelToSky(g, 0, 29)
    expect(west.ra).toBeGreaterThan(359.9)
    expect(west.ra).toBeLessThan(360)
    expect(east.ra).toBeGreaterThan(0.001)
    expect(east.ra).toBeLessThan(0.1)
    const pw = skyToPixel(g, west.ra, west.dec)
    expect(pw?.x).toBeCloseTo(g.nx - 1, 8)
    // the same position given as a negative RA projects identically
    const pn = skyToPixel(g, west.ra - 360, west.dec)
    expect(pn?.x).toBeCloseTo(g.nx - 1, 8)
    const g2 = grid(359.9995, -35)
    const p = pixelToSky(g2, 0, 10)
    expect(p.ra).toBeGreaterThanOrEqual(0)
    expect(p.ra).toBeLessThan(1)
    expect(skyToPixel(g2, p.ra, p.dec)?.x).toBeCloseTo(0, 8)
  })

  it('stays exact at |dec| ~ 80 degrees', () => {
    for (const dec0 of [80, -80]) {
      const g = grid(123.456, dec0)
      const c = pixelToSky(g, 29, 29)
      const n1 = pixelToSky(g, 29, 30)
      const w1 = pixelToSky(g, 30, 29)
      expect(separationArcsec(c, n1)).toBeCloseTo(6.15, 6)
      expect(separationArcsec(c, w1)).toBeCloseTo(6.15, 6)
      expect(n1.dec).toBeGreaterThan(c.dec)
      // one pixel west is a much larger RA step near the pole
      expect((c.ra - w1.ra) * 3600).toBeCloseTo(6.15 / Math.cos((dec0 * Math.PI) / 180), 1)
      const corner = pixelToSky(g, 0, g.ny - 1)
      const back = skyToPixel(g, corner.ra, corner.dec)
      expect(back?.x).toBeCloseTo(0, 7)
      expect(back?.y).toBeCloseTo(g.ny - 1, 7)
    }
  })

  it('returns null for positions on the far hemisphere', () => {
    expect(skyToPixel(BARNARD, 269.446269 + 180, -4.768204)).toBeNull()
    expect(skyToPixel(BARNARD, 269.446269 + 120, 0)).toBeNull()
  })
})

describe('PNG space', () => {
  it('first PNG row is north, first column is east', () => {
    // centre of FITS pixel (0, ny-1) is the centre of the top-left PNG pixel
    expect(pixelToPng(BARNARD, 0, BARNARD.ny - 1)).toEqual({ x: 0.5, y: 0.5 })
    expect(pixelToPng(BARNARD, BARNARD.nx - 1, 0)).toEqual({ x: BARNARD.nx - 0.5, y: BARNARD.ny - 0.5 })
    const top = pngToSky(BARNARD, 29.5, 0.5)
    const bottom = pngToSky(BARNARD, 29.5, 58.5)
    expect(top.dec).toBeGreaterThan(bottom.dec)
    const left = pngToSky(BARNARD, 0.5, 29.5)
    const right = pngToSky(BARNARD, 58.5, 29.5)
    expect(left.ra).toBeGreaterThan(right.ra) // east is left
  })

  it('PNG row r corresponds to FITS y = ny - 1 - r', () => {
    for (const r of [0, 10, 58]) {
      const p = pngToPixel(BARNARD, 7 + 0.5, r + 0.5)
      expect(p.x).toBeCloseTo(7, 12)
      expect(p.y).toBeCloseTo(BARNARD.ny - 1 - r, 12)
    }
  })

  it('sky -> png -> sky round trip', () => {
    const png = skyToPng(BARNARD, 269.44, 4.77)
    expect(png).not.toBeNull()
    const sky = pngToSky(BARNARD, (png as { x: number }).x, (png as { y: number }).y)
    expect(sky.ra).toBeCloseTo(269.44, 10)
    expect(sky.dec).toBeCloseTo(4.77, 10)
    // image centre is crval
    const c = pngToSky(BARNARD, 29.5, 29.5)
    expect(c.ra).toBeCloseTo(269.446269, 10)
    expect(c.dec).toBeCloseTo(4.768204, 10)
  })
})

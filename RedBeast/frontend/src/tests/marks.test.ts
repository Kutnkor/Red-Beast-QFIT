import { describe, expect, it } from 'vitest'
import {
  addMark,
  deleteMark,
  makeMark,
  markScreen,
  marksForSave,
  MAX_MARKS,
  moveMark,
  newId,
  sanitizeMarks,
  screenRadiusToArcsec,
  screenToSky,
  tracksOf,
  updateMark,
} from '../lib/marks'
import { decodeView, encodeView, DEFAULT_LAYERS } from '../lib/savedView'
import type { Grid, Mark } from '../lib/types'
import { clampView, defaultView, panBy, pngToScreen, scaleOf, screenToPng, zoomAt, type Size, type View } from '../lib/view'
import { separationArcsec } from '../lib/wcs'

const S = 6.15 / 3600
const GRID: Grid = {
  projection: 'TAN',
  crval: [269.446269, 4.768204],
  crpix: [30, 30],
  cdelt: [-S, S],
  nx: 59,
  ny: 59,
  pixscale_arcsec: 6.15,
}
// real Barnard frame dates (MJD)
const MJD = [60912.7148, 60917.6746, 61114.0357, 61270.8678, 61273.7889, 61305.6287]

describe('marks model', () => {
  it('creates point and region marks with schema-valid ids', () => {
    const { marks, mark } = addMark([], { ra_deg: 269.44, dec_deg: 4.77, frame_index: 2, classification: 'unsure' })
    expect(marks).toHaveLength(1)
    expect(mark?.kind).toBe('point')
    expect(mark?.radius_arcsec).toBeNull()
    expect(mark?.id).toMatch(/^[A-Za-z0-9_-]{1,40}$/)
    expect(mark?.frame_index).toBe(2)

    const region = makeMark({ ra_deg: 370, dec_deg: 4.77, frame_index: 0, classification: 'possible_artifact', radius_arcsec: 30 })
    expect(region.kind).toBe('region')
    expect(region.radius_arcsec).toBe(30)
    expect(region.ra_deg).toBeCloseTo(10, 10) // RA is normalised into [0, 360)
    expect(makeMark({ ra_deg: 1, dec_deg: 1, frame_index: 0, classification: 'unsure', radius_arcsec: 5000 }).radius_arcsec).toBe(900)
    expect(new Set(Array.from({ length: 200 }, () => newId())).size).toBe(200)
  })

  it('edits classification, note and position without changing the frame', () => {
    let { marks } = addMark([], { ra_deg: 269.44, dec_deg: 4.77, frame_index: 3, classification: 'unsure' })
    const id = marks[0].id
    marks = updateMark(marks, id, { classification: 'possible_brightness_change', note: 'x'.repeat(700) })
    expect(marks[0].classification).toBe('possible_brightness_change')
    expect(marks[0].note).toHaveLength(500)
    marks = moveMark(marks, id, 269.45, 4.78)
    expect(marks[0].ra_deg).toBe(269.45)
    expect(marks[0].dec_deg).toBe(4.78)
    expect(marks[0].frame_index).toBe(3)
    marks = updateMark(marks, id, { radius_arcsec: 12 })
    expect(marks[0].kind).toBe('region')
    marks = updateMark(marks, id, { radius_arcsec: null })
    expect(marks[0].kind).toBe('point')
    expect(updateMark(marks, 'nope', { note: 'a' })).toEqual(marks)
  })

  it('deletes marks and enforces the limit', () => {
    let marks: Mark[] = []
    for (let i = 0; i < MAX_MARKS; i++) marks = addMark(marks, { ra_deg: 1, dec_deg: 1, frame_index: 0, classification: 'unsure' }).marks
    expect(marks).toHaveLength(MAX_MARKS)
    const over = addMark(marks, { ra_deg: 1, dec_deg: 1, frame_index: 0, classification: 'unsure' })
    expect(over.mark).toBeNull()
    expect(over.marks).toHaveLength(MAX_MARKS)
    const gone = deleteMark(marks, marks[5].id)
    expect(gone).toHaveLength(MAX_MARKS - 1)
    expect(gone.find((m) => m.id === marks[5].id)).toBeUndefined()
  })

  it('orders track points by the observation date of their frame, never merging them', () => {
    const mk = (frame: number, track: string | null, id: string) =>
      makeMark({ id, ra_deg: 269.44 + frame * 1e-4, dec_deg: 4.77, frame_index: frame, classification: 'possible_motion', track_id: track })
    // inserted out of time order
    const marks = [mk(5, 'tA', 'a5'), mk(0, 'tA', 'a0'), mk(3, 'tA', 'a3'), mk(2, 'tB', 'b2'), mk(1, 'tB', 'b1'), mk(4, null, 'solo')]
    const tracks = tracksOf(marks, MJD)
    expect(tracks).toHaveLength(2)
    const a = tracks.find((t) => t.id === 'tA')
    const b = tracks.find((t) => t.id === 'tB')
    expect(a?.points.map((m) => m.id)).toEqual(['a0', 'a3', 'a5'])
    expect(b?.points.map((m) => m.id)).toEqual(['b1', 'b2'])
    // every point keeps its own frame
    expect(a?.points.map((m) => m.frame_index)).toEqual([0, 3, 5])
    // frames listed out of date order still sort by date, not index
    const shuffled = tracksOf([mk(0, 't', 'x'), mk(1, 't', 'y')], [61000, 60000])
    expect(shuffled[0].points.map((m) => m.id)).toEqual(['y', 'x'])
  })

  it('strips server-only fields for saving and rejects malformed stored marks', () => {
    const m = { ...makeMark({ ra_deg: 269.44, dec_deg: 4.77, frame_index: 1, classification: 'unsure', note: 'n' }), date: '2025-08-30T16:11:26Z', obs_id: 'x' }
    const out = marksForSave([m])[0]
    expect(Object.keys(out).sort()).toEqual(['classification', 'dec_deg', 'frame_index', 'id', 'kind', 'note', 'ra_deg'])
    const region = marksForSave([makeMark({ ra_deg: 1, dec_deg: 2, frame_index: 0, classification: 'unsure', radius_arcsec: 12.345, track_id: 't1' })])[0]
    expect(region.radius_arcsec).toBe(12.35)
    expect(region.track_id).toBe('t1')

    const clean = sanitizeMarks(
      [
        m,
        { ...m, id: 'dup' },
        { ...m, id: 'dup' },
        { ...m, id: 'bad id!' },
        { ...m, id: 'f', frame_index: 9 },
        { ...m, id: 'c', classification: 'confirmed_discovery' },
        { ...m, id: 'n', ra_deg: 'x' },
        null,
        'str',
      ],
      6,
    )
    expect(clean.map((x) => x.id)).toEqual([m.id, 'dup'])
    expect(sanitizeMarks('nope', 6)).toEqual([])
  })
})

describe('sky <-> screen', () => {
  const mark = makeMark({ ra_deg: 269.4502, dec_deg: 4.7641, frame_index: 0, classification: 'unsure', radius_arcsec: 24.6 })
  const views: View[] = [defaultView(GRID), { zoom: 3, cx: 20, cy: 40 }, { zoom: 11.5, cx: 31.2, cy: 28.9 }]
  const sizes: Size[] = [
    { w: 600, h: 600 },
    { w: 375, h: 300 },
    { w: 1280, h: 720 },
  ]

  it('a mark stays on the same sky position under zoom, pan and resize', () => {
    for (const size of sizes) {
      for (const view of views) {
        const s = markScreen(mark, GRID, view, size)
        expect(s).not.toBeNull()
        const sky = screenToSky(GRID, view, size, (s as { x: number }).x, (s as { y: number }).y)
        expect(separationArcsec(sky, { ra: mark.ra_deg, dec: mark.dec_deg })).toBeLessThan(1e-6)
        // the drawn radius converts back to the stored radius
        expect(screenRadiusToArcsec(GRID, view, size, (s as { r: number }).r)).toBeCloseTo(24.6, 9)
      }
    }
  })

  it('creating a mark from a click and drawing it again lands on the click', () => {
    const size = { w: 640, h: 480 }
    let view = zoomAt(defaultView(GRID), size, GRID, 4, 200, 150)
    view = panBy(view, size, GRID, -37, 22)
    const sky = screenToSky(GRID, view, size, 412, 233)
    const m = makeMark({ ra_deg: sky.ra, dec_deg: sky.dec, frame_index: 1, classification: 'possible_motion' })
    const s = markScreen(m, GRID, view, size)
    expect(s?.x).toBeCloseTo(412, 6)
    expect(s?.y).toBeCloseTo(233, 6)
    // after further zooming and panning the mark moves with the image
    const view2 = panBy(zoomAt(view, size, GRID, 2.5, 100, 400), size, GRID, 15, -60)
    const png = screenToPng(view, size, GRID, 412, 233)
    const expected = pngToScreen(view2, size, GRID, png.x, png.y)
    const s2 = markScreen(m, GRID, view2, size)
    expect(s2?.x).toBeCloseTo(expected.x, 6)
    expect(s2?.y).toBeCloseTo(expected.y, 6)
  })

  it('two panes of different size sharing one view show the same sky point at their centres', () => {
    const view = { zoom: 5, cx: 18.25, cy: 33.5 }
    const a = screenToSky(GRID, view, { w: 500, h: 500 }, 250, 250)
    const b = screenToSky(GRID, view, { w: 320, h: 410 }, 160, 205)
    expect(separationArcsec(a, b)).toBeLessThan(1e-9)
  })

  it('zoomAt keeps the anchor fixed and clampView keeps the image in view', () => {
    const size = { w: 590, h: 590 }
    const v0 = { zoom: 2, cx: 25, cy: 30 }
    const before = screenToPng(v0, size, GRID, 400, 120)
    const v1 = zoomAt(v0, size, GRID, 3, 400, 120)
    const after = screenToPng(v1, size, GRID, 400, 120)
    expect(after.x).toBeCloseTo(before.x, 9)
    expect(after.y).toBeCloseTo(before.y, 9)
    expect(scaleOf(v1, size, GRID)).toBeCloseTo(scaleOf(v0, size, GRID) * 3, 9)
    expect(clampView({ zoom: 0.2, cx: -50, cy: 500 }, GRID)).toEqual({ zoom: 1, cx: 29.5, cy: 29.5 })
    const far = clampView({ zoom: 4, cx: 1000, cy: -1000 }, GRID)
    expect(far.cx).toBeLessThanOrEqual(GRID.nx)
    expect(far.cy).toBeGreaterThanOrEqual(0)
    expect(zoomAt(v0, size, GRID, 1e6).zoom).toBe(32)
  })
})

describe('saved view', () => {
  it('round-trips through the JSON stored with an observation', () => {
    const state = { view: { zoom: 4, cx: 20.5, cy: 41.25 }, cur: 5, ref: 0, mode: 'side' as const, layers: { ...DEFAULT_LAYERS, gaia: true, mask: true } }
    const saved = encodeView(state, GRID)
    expect(JSON.stringify(saved).length).toBeLessThan(400)
    const back = decodeView(JSON.parse(JSON.stringify(saved)), GRID, 6)
    expect(back.cur).toBe(5)
    expect(back.ref).toBe(0)
    expect(back.mode).toBe('side')
    expect(back.layers).toEqual(state.layers)
    expect(back.view.zoom).toBeCloseTo(4, 6)
    expect(back.view.cx).toBeCloseTo(20.5, 2)
    expect(back.view.cy).toBeCloseTo(41.25, 2)
  })

  it('falls back safely on junk', () => {
    for (const junk of [null, undefined, 'x', { z: 'big', f: 99, m: 'weird', l: 'no' }, { f: -1, r: 2.5 }]) {
      const v = decodeView(junk, GRID, 6)
      expect(v.cur).toBe(0)
      expect(v.ref).toBe(0)
      expect(v.mode).toBe('single')
      expect(v.view).toEqual(defaultView(GRID))
      expect(v.layers).toEqual(DEFAULT_LAYERS)
    }
    expect(decodeView({ m: 'diff' }, GRID, 1).mode).toBe('single')
  })
})

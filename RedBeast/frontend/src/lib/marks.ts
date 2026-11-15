// User marks: stored in sky coordinates, bound to the frame (and therefore the date) they were made on.
// Pure functions only; persistence lives in storage.ts, drawing in viewer/Pane.tsx.

import type { Classification, Mark } from './types'
import { pngToScreen, scaleOf, screenToPng, type Size, type View } from './view'
import { normalizeRa, pixscaleArcsec, pngToSky, skyToPng, type WcsGrid } from './wcs'

export const MAX_MARKS = 200
export const MAX_NOTE = 500
export const MAX_RADIUS_ARCSEC = 900
const ID_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'

export function newId(prefix = 'm', rand: () => number = Math.random): string {
  let s = prefix
  for (let i = 0; i < 9; i++) s += ID_CHARS[Math.floor(rand() * ID_CHARS.length) % ID_CHARS.length]
  return s
}

export interface MarkInput {
  ra_deg: number
  dec_deg: number
  frame_index: number
  classification: Classification
  radius_arcsec?: number | null
  note?: string
  track_id?: string | null
  id?: string
}

function clampRadius(r: number): number {
  return Math.min(MAX_RADIUS_ARCSEC, Math.max(0.1, r))
}

/** Build a mark. A radius makes it a region; without one it is a point. */
export function makeMark(input: MarkInput): Mark {
  const region = typeof input.radius_arcsec === 'number' && input.radius_arcsec > 0
  return {
    id: input.id ?? newId(),
    kind: region ? 'region' : 'point',
    classification: input.classification,
    ra_deg: normalizeRa(input.ra_deg),
    dec_deg: Math.min(90, Math.max(-90, input.dec_deg)),
    radius_arcsec: region ? clampRadius(input.radius_arcsec as number) : null,
    frame_index: Math.max(0, Math.round(input.frame_index)),
    note: (input.note ?? '').slice(0, MAX_NOTE),
    track_id: input.track_id ?? null,
  }
}

export function addMark(marks: Mark[], input: MarkInput): { marks: Mark[]; mark: Mark | null } {
  if (marks.length >= MAX_MARKS) return { marks, mark: null }
  const mark = makeMark(input)
  return { marks: [...marks, mark], mark }
}

export type MarkPatch = Partial<Pick<Mark, 'classification' | 'note' | 'ra_deg' | 'dec_deg' | 'radius_arcsec' | 'track_id'>>

export function updateMark(marks: Mark[], id: string, patch: MarkPatch): Mark[] {
  return marks.map((m) => {
    if (m.id !== id) return m
    const next: Mark = { ...m, ...patch }
    if (patch.note !== undefined) next.note = patch.note.slice(0, MAX_NOTE)
    if (patch.ra_deg !== undefined) next.ra_deg = normalizeRa(patch.ra_deg)
    if (patch.dec_deg !== undefined) next.dec_deg = Math.min(90, Math.max(-90, patch.dec_deg))
    if (patch.radius_arcsec !== undefined) {
      const region = typeof patch.radius_arcsec === 'number' && patch.radius_arcsec > 0
      next.kind = region ? 'region' : 'point'
      next.radius_arcsec = region ? clampRadius(patch.radius_arcsec as number) : null
    }
    return next
  })
}

/** Moving a mark changes only its sky position; the frame (date) it belongs to is never changed. */
export function moveMark(marks: Mark[], id: string, ra: number, dec: number): Mark[] {
  return updateMark(marks, id, { ra_deg: ra, dec_deg: dec })
}

export function deleteMark(marks: Mark[], id: string): Mark[] {
  return marks.filter((m) => m.id !== id)
}

export interface Track {
  id: string
  points: Mark[]
}

/**
 * Group marks sharing a track_id, each track ordered by the observation date of the frame the point
 * was made on (ties: frame index, then insertion order). `frameMjd[i]` is the MJD of frame i.
 */
export function tracksOf(marks: Mark[], frameMjd: number[]): Track[] {
  const byId = new Map<string, { m: Mark; order: number }[]>()
  marks.forEach((m, order) => {
    if (!m.track_id) return
    const list = byId.get(m.track_id) ?? []
    list.push({ m, order })
    byId.set(m.track_id, list)
  })
  const when = (m: Mark) => frameMjd[m.frame_index] ?? Number.POSITIVE_INFINITY
  return [...byId.entries()].map(([id, list]) => ({
    id,
    points: list
      .sort((p, q) => when(p.m) - when(q.m) || p.m.frame_index - q.m.frame_index || p.order - q.order)
      .map((p) => p.m),
  }))
}

/** Strip everything the server does not accept (it fills date/obs_id itself). */
export function marksForSave(marks: Mark[]): Mark[] {
  return marks.slice(0, MAX_MARKS).map((m) => {
    const out: Mark = {
      id: m.id,
      kind: m.kind,
      classification: m.classification,
      ra_deg: Number(normalizeRa(m.ra_deg).toFixed(7)),
      dec_deg: Number(m.dec_deg.toFixed(7)),
      frame_index: m.frame_index,
      note: m.note.slice(0, MAX_NOTE),
    }
    if (m.kind === 'region' && m.radius_arcsec) out.radius_arcsec = Number(m.radius_arcsec.toFixed(2))
    if (m.track_id) out.track_id = m.track_id
    return out
  })
}

/** Accept marks from storage or the server; drop anything malformed. */
export function sanitizeMarks(input: unknown, nFrames: number): Mark[] {
  if (!Array.isArray(input)) return []
  const classes: string[] = ['possible_motion', 'possible_brightness_change', 'possible_artifact', 'unsure']
  const out: Mark[] = []
  const seen = new Set<string>()
  for (const raw of input) {
    if (typeof raw !== 'object' || raw === null) continue
    const r = raw as Record<string, unknown>
    if (typeof r.id !== 'string' || !/^[A-Za-z0-9_-]{1,40}$/.test(r.id) || seen.has(r.id)) continue
    if (typeof r.ra_deg !== 'number' || typeof r.dec_deg !== 'number') continue
    if (!Number.isFinite(r.ra_deg) || !Number.isFinite(r.dec_deg)) continue
    if (typeof r.frame_index !== 'number' || r.frame_index < 0 || r.frame_index >= nFrames) continue
    if (typeof r.classification !== 'string' || !classes.includes(r.classification)) continue
    seen.add(r.id)
    const mark = makeMark({
      id: r.id,
      ra_deg: r.ra_deg,
      dec_deg: r.dec_deg,
      frame_index: r.frame_index,
      classification: r.classification as Classification,
      radius_arcsec: typeof r.radius_arcsec === 'number' ? r.radius_arcsec : null,
      note: typeof r.note === 'string' ? r.note : '',
      track_id: typeof r.track_id === 'string' && /^[A-Za-z0-9_-]{1,40}$/.test(r.track_id) ? r.track_id : null,
    })
    if (typeof r.date === 'string') mark.date = r.date
    out.push(mark)
    if (out.length >= MAX_MARKS) break
  }
  return out
}

/** Screen position (and radius in screen pixels) of a mark for a given view and viewport. */
export function markScreen(
  mark: Pick<Mark, 'ra_deg' | 'dec_deg' | 'radius_arcsec'>,
  grid: WcsGrid,
  view: View,
  size: Size,
): { x: number; y: number; r: number } | null {
  const png = skyToPng(grid, mark.ra_deg, mark.dec_deg)
  if (!png) return null
  const p = pngToScreen(view, size, grid, png.x, png.y)
  const r = mark.radius_arcsec ? (mark.radius_arcsec / pixscaleArcsec(grid)) * scaleOf(view, size, grid) : 0
  return { x: p.x, y: p.y, r }
}

/** Sky position under a screen point. */
export function screenToSky(grid: WcsGrid, view: View, size: Size, sx: number, sy: number) {
  const png = screenToPng(view, size, grid, sx, sy)
  return pngToSky(grid, png.x, png.y)
}

/** Radius on the sky for a drag of `distPx` screen pixels. */
export function screenRadiusToArcsec(grid: WcsGrid, view: View, size: Size, distPx: number): number {
  return (distPx / scaleOf(view, size, grid)) * pixscaleArcsec(grid)
}

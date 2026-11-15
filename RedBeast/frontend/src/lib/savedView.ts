// The small `view` JSON stored with a shared observation, so its link reopens the same view.

import type { Grid, Layers, SavedView, ViewMode } from './types'
import { clampView, defaultView, type View } from './view'
import { pngToSky, skyToPng } from './wcs'

export const DEFAULT_LAYERS: Layers = {
  mask: false,
  gaia: false,
  allwise: false,
  predicted: false,
  candidates: false,
  marks: true,
}

const MODES: ViewMode[] = ['single', 'side', 'diff', 'stack', 'trackstack']
const LAYER_KEYS = Object.keys(DEFAULT_LAYERS) as (keyof Layers)[]

export interface ViewerState {
  view: View
  cur: number
  ref: number
  mode: ViewMode
  layers: Layers
}

export function encodeView(state: ViewerState, grid: Grid): SavedView {
  const centre = pngToSky(grid, state.view.cx, state.view.cy)
  return {
    z: Number(state.view.zoom.toFixed(3)),
    ra: Number(centre.ra.toFixed(6)),
    dec: Number(centre.dec.toFixed(6)),
    f: state.cur,
    r: state.ref,
    m: state.mode,
    l: LAYER_KEYS.filter((k) => state.layers[k]),
  }
}

/** Tolerant decode: anything missing or out of range falls back to the default view. */
export function decodeView(saved: unknown, grid: Grid, nFrames: number): ViewerState {
  const s = (typeof saved === 'object' && saved !== null ? saved : {}) as Record<string, unknown>
  const index = (v: unknown, fallback: number) =>
    typeof v === 'number' && Number.isInteger(v) && v >= 0 && v < nFrames ? v : fallback

  let view = defaultView(grid)
  if (typeof s.z === 'number' && Number.isFinite(s.z)) {
    view = { ...view, zoom: s.z }
    if (typeof s.ra === 'number' && typeof s.dec === 'number') {
      const p = skyToPng(grid, s.ra, s.dec)
      if (p && Number.isFinite(p.x) && Number.isFinite(p.y)) view = { ...view, cx: p.x, cy: p.y }
    }
    view = clampView(view, grid)
  }

  let mode: ViewMode = MODES.includes(s.m as ViewMode) ? (s.m as ViewMode) : 'single'
  if (nFrames < 2) mode = 'single'

  const layers: Layers = { ...DEFAULT_LAYERS }
  if (Array.isArray(s.l)) {
    for (const k of LAYER_KEYS) layers[k] = s.l.includes(k)
  }

  return { view, cur: index(s.f, 0), ref: index(s.r, 0), mode, layers }
}

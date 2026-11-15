// Zoom / pan model shared by every image pane.
//
// The view is stored in image (PNG) space so it is independent of the viewport size:
//   zoom : 1 = whole image fits the viewport
//   cx,cy: PNG-space point shown at the viewport centre

import type { WcsGrid } from './wcs'

export interface View {
  zoom: number
  cx: number
  cy: number
}

export interface Size {
  w: number
  h: number
}

export const MIN_ZOOM = 1
export const MAX_ZOOM = 32

export function defaultView(grid: Pick<WcsGrid, 'nx' | 'ny'>): View {
  return { zoom: 1, cx: grid.nx / 2, cy: grid.ny / 2 }
}

/** Screen pixels per image pixel. */
export function scaleOf(view: View, size: Size, grid: Pick<WcsGrid, 'nx' | 'ny'>): number {
  const fit = Math.min(size.w / grid.nx, size.h / grid.ny)
  return Math.max(fit, 1e-6) * view.zoom
}

export function pngToScreen(view: View, size: Size, grid: Pick<WcsGrid, 'nx' | 'ny'>, px: number, py: number) {
  const s = scaleOf(view, size, grid)
  return { x: size.w / 2 + (px - view.cx) * s, y: size.h / 2 + (py - view.cy) * s }
}

export function screenToPng(view: View, size: Size, grid: Pick<WcsGrid, 'nx' | 'ny'>, sx: number, sy: number) {
  const s = scaleOf(view, size, grid)
  return { x: view.cx + (sx - size.w / 2) / s, y: view.cy + (sy - size.h / 2) / s }
}

export function clampView(view: View, grid: Pick<WcsGrid, 'nx' | 'ny'>): View {
  const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, view.zoom))
  // keep the visible centre inside the image; at zoom 1 the image is simply centred
  const halfX = grid.nx / 2 / zoom
  const halfY = grid.ny / 2 / zoom
  const cx = Math.min(grid.nx - halfX, Math.max(halfX, view.cx))
  const cy = Math.min(grid.ny - halfY, Math.max(halfY, view.cy))
  return { zoom, cx, cy }
}

/** Zoom by `factor`, keeping the image point under screen position (sx, sy) fixed. */
export function zoomAt(
  view: View,
  size: Size,
  grid: Pick<WcsGrid, 'nx' | 'ny'>,
  factor: number,
  sx: number = size.w / 2,
  sy: number = size.h / 2,
): View {
  const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, view.zoom * factor))
  const anchor = screenToPng(view, size, grid, sx, sy)
  const s = scaleOf({ ...view, zoom }, size, grid)
  return clampView({ zoom, cx: anchor.x - (sx - size.w / 2) / s, cy: anchor.y - (sy - size.h / 2) / s }, grid)
}

/** Pan by a screen-space delta (dragging the image by dx,dy screen pixels). */
export function panBy(view: View, size: Size, grid: Pick<WcsGrid, 'nx' | 'ny'>, dx: number, dy: number): View {
  const s = scaleOf(view, size, grid)
  return clampView({ ...view, cx: view.cx - dx / s, cy: view.cy - dy / s }, grid)
}

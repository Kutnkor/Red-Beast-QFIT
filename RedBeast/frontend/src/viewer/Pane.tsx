// One image pane: the real frame (never smoothed), its quality mask, and an SVG overlay drawn in screen space
// from sky coordinates. Zoom/pan state comes from the parent so that several panes stay synchronised.

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { useI18n } from '../i18n'
import { fmtDay } from '../lib/format'
import { markScreen, screenRadiusToArcsec, screenToSky, type Track } from '../lib/marks'
import type { Candidate, Grid, Mark, Overlay } from '../lib/types'
import { panBy, pngToScreen, scaleOf, zoomAt, type Size, type View } from '../lib/view'
import { skyToPng, type Sky } from '../lib/wcs'

export interface PaneOverlays {
  gaia: Overlay | null
  allwise: Overlay | null
  predicted: { ra: number; dec: number } | null
  candidates: Candidate[] | null
}

export interface PaneProps {
  grid: Grid
  imageUrl: string | null
  /** other frame images kept decoded so switching frames never flashes */
  preload?: string[]
  maskUrl: string | null
  chip: string
  ariaLabel: string
  /** frame shown in this pane; null for products without a single date (stack) */
  frameIndex: number | null
  view: View
  onView: (view: View) => void
  overlays: PaneOverlays
  marks: Mark[]
  tracks: Track[]
  frameDates: string[]
  selectedId: string | null
  markMode: boolean
  readOnly: boolean
  busy?: boolean
  onSelect: (id: string | null) => void
  onCreate: (sky: Sky, radiusArcsec: number | null, frameIndex: number) => void
  onMove: (id: string, sky: Sky) => void
  onCursor: (sky: Sky | null) => void
}

type Gesture =
  | { kind: 'pan'; x0: number; y0: number; view0: View; moved: boolean }
  | { kind: 'mark'; x0: number; y0: number }
  | { kind: 'move'; id: string; x0: number; y0: number; moved: boolean }
  | { kind: 'pinch'; d0: number; mx: number; my: number; view0: View }

const CLICK_SLOP = 6

export function Pane(props: PaneProps) {
  const { grid, view, onView, frameIndex, markMode, readOnly } = props
  const { t } = useI18n()
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState<Size>({ w: 0, h: 0 })
  const pointers = useRef(new Map<number, { x: number; y: number }>())
  const gesture = useRef<Gesture | null>(null)
  const [region, setRegion] = useState<{ x: number; y: number; r: number } | null>(null)

  // latest values for native listeners
  const live = useRef({ view, size, onView })
  live.current = { view, size, onView }

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => {
      const r = el.getBoundingClientRect()
      const w = r.width || el.clientWidth || 320
      const h = r.height || el.clientHeight || 320
      setSize((s) => (s.w === w && s.h === h ? s : { w, h }))
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // wheel zoom needs a non-passive listener to stop the page from scrolling
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = el.getBoundingClientRect()
      const { view: v, size: s, onView: set } = live.current
      const unit = e.deltaMode === 1 ? 32 : 1
      const factor = Math.exp(-e.deltaY * unit * 0.0016)
      set(zoomAt(v, s, grid, factor, e.clientX - r.left, e.clientY - r.top))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [grid])

  const local = (e: PointerEvent) => {
    const r = ref.current?.getBoundingClientRect()
    return { x: e.clientX - (r?.left ?? 0), y: e.clientY - (r?.top ?? 0) }
  }

  const ready = size.w > 0 && size.h > 0
  const scale = scaleOf(view, size, grid)

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    const p = local(e)
    try {
      e.currentTarget.setPointerCapture(e.pointerId)
    } catch {
      /* not supported (tests) */
    }
    pointers.current.set(e.pointerId, p)
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()]
      gesture.current = {
        kind: 'pinch',
        d0: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)),
        mx: (a.x + b.x) / 2,
        my: (a.y + b.y) / 2,
        view0: view,
      }
      setRegion(null)
      return
    }
    if (pointers.current.size > 2 || (e.pointerType === 'mouse' && e.button !== 0)) return
    const markEl = (e.target as Element).closest?.('[data-mark]')
    const markId = markEl?.getAttribute('data-mark')
    if (markId) {
      props.onSelect(markId)
      gesture.current = readOnly ? null : { kind: 'move', id: markId, x0: p.x, y0: p.y, moved: false }
      return
    }
    if (markMode && !readOnly && frameIndex !== null) {
      gesture.current = { kind: 'mark', x0: p.x, y0: p.y }
      return
    }
    gesture.current = { kind: 'pan', x0: p.x, y0: p.y, view0: view, moved: false }
  }

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const p = local(e)
    if (ready) props.onCursor(screenToSky(grid, view, size, p.x, p.y))
    if (!pointers.current.has(e.pointerId)) return
    pointers.current.set(e.pointerId, p)
    const g = gesture.current
    if (!g) return
    if (g.kind === 'pinch') {
      if (pointers.current.size < 2) return
      const [a, b] = [...pointers.current.values()]
      const d = Math.max(1, Math.hypot(a.x - b.x, a.y - b.y))
      const mx = (a.x + b.x) / 2
      const my = (a.y + b.y) / 2
      const zoomed = zoomAt(g.view0, size, grid, d / g.d0, g.mx, g.my)
      onView(panBy(zoomed, size, grid, mx - g.mx, my - g.my))
      return
    }
    const dist = Math.hypot(p.x - g.x0, p.y - g.y0)
    if (g.kind === 'pan') {
      if (dist > CLICK_SLOP) g.moved = true
      if (g.moved) onView(panBy(g.view0, size, grid, p.x - g.x0, p.y - g.y0))
    } else if (g.kind === 'mark') {
      setRegion(dist > CLICK_SLOP ? { x: g.x0, y: g.y0, r: dist } : null)
    } else if (g.kind === 'move') {
      if (dist > CLICK_SLOP) g.moved = true
      if (g.moved) props.onMove(g.id, screenToSky(grid, view, size, p.x, p.y))
    }
  }

  const endPointer = (e: PointerEvent<HTMLDivElement>, cancelled: boolean) => {
    const p = local(e)
    pointers.current.delete(e.pointerId)
    const g = gesture.current
    if (!g) return
    if (g.kind === 'pinch') {
      if (pointers.current.size < 2) gesture.current = null
      return
    }
    gesture.current = null
    if (cancelled) {
      setRegion(null)
      return
    }
    if (g.kind === 'mark' && frameIndex !== null) {
      const dist = Math.hypot(p.x - g.x0, p.y - g.y0)
      const sky = screenToSky(grid, view, size, g.x0, g.y0)
      props.onCreate(sky, dist > CLICK_SLOP ? screenRadiusToArcsec(grid, view, size, dist) : null, frameIndex)
      setRegion(null)
    } else if (g.kind === 'pan' && !g.moved) {
      props.onSelect(null)
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' && markMode && !readOnly && frameIndex !== null && e.target === e.currentTarget) {
      e.preventDefault()
      props.onCreate(screenToSky(grid, view, size, size.w / 2, size.h / 2), null, frameIndex)
    }
  }

  const box = {
    left: size.w / 2 - view.cx * scale,
    top: size.h / 2 - view.cy * scale,
    width: grid.nx * scale,
    height: grid.ny * scale,
  }

  const urls = useMemo(() => {
    const set = new Set<string>(props.preload ?? [])
    if (props.imageUrl) set.add(props.imageUrl)
    return [...set]
  }, [props.preload, props.imageUrl])

  const toScreen = (ra: number, dec: number) => {
    const png = skyToPng(grid, ra, dec)
    return png ? pngToScreen(view, size, grid, png.x, png.y) : null
  }
  const visible = (p: { x: number; y: number } | null, pad = 12): p is { x: number; y: number } =>
    p !== null && p.x > -pad && p.y > -pad && p.x < size.w + pad && p.y < size.h + pad

  const { overlays } = props
  const markNumber = new Map(props.marks.map((m, i) => [m.id, i + 1]))

  return (
    <div
      ref={ref}
      className={`pane${markMode && !readOnly && frameIndex !== null ? ' pane-marking' : ''}`}
      tabIndex={0}
      role="application"
      aria-label={props.ariaLabel}
      aria-describedby="pane-help"
      aria-busy={props.busy || undefined}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={(e) => endPointer(e, false)}
      onPointerCancel={(e) => endPointer(e, true)}
      onPointerLeave={() => props.onCursor(null)}
      onKeyDown={onKeyDown}
      data-testid="pane"
    >
      {ready && (
        <div className="pane-image nodata" style={box}>
          {urls.map((u) => (
            <img
              key={u}
              src={u}
              alt=""
              draggable={false}
              className="px"
              style={{ visibility: u === props.imageUrl ? 'visible' : 'hidden' }}
            />
          ))}
          {props.maskUrl && <img src={props.maskUrl} alt="" draggable={false} className="px pane-mask" />}
        </div>
      )}

      {ready && (
        <svg className="pane-overlay" width={size.w} height={size.h} aria-hidden="true">
          {overlays.allwise?.sources.map((s) => {
            const p = toScreen(s.ra, s.dec)
            if (!visible(p)) return null
            return (
              <rect key={`w${s.id}`} className="cat cat-wise" x={p.x - 4} y={p.y - 4} width={8} height={8} transform={`rotate(45 ${p.x} ${p.y})`}>
                <title>{`AllWISE ${s.id}${s.mag !== null ? ` · W=${s.mag.toFixed(2)}` : ''}`}</title>
              </rect>
            )
          })}
          {overlays.gaia?.sources.map((s) => {
            const pos = frameIndex !== null && s.per_frame?.[frameIndex] ? s.per_frame[frameIndex] : [s.ra, s.dec]
            const p = toScreen(pos[0], pos[1])
            if (!visible(p)) return null
            return (
              <circle key={`g${s.id}`} className="cat cat-gaia" cx={p.x} cy={p.y} r={s.per_frame ? 6.5 : 4.5}>
                <title>{`Gaia DR3 ${s.id}${s.mag !== null ? ` · G=${s.mag.toFixed(2)}` : ''}${s.pm_masyr ? ` · ${s.pm_masyr} mas/yr` : ''}`}</title>
              </circle>
            )
          })}

          {overlays.predicted &&
            (() => {
              const p = toScreen(overlays.predicted.ra, overlays.predicted.dec)
              if (!visible(p, 30)) return null
              return (
                <g className="predicted">
                  <path d={`M${p.x - 16} ${p.y}h10M${p.x + 6} ${p.y}h10M${p.x} ${p.y - 16}v10M${p.x} ${p.y + 6}v10`} />
                  <text x={p.x + 12} y={p.y - 10} className="ovl-text">
                    {t('layer.predictedShort')}
                  </text>
                </g>
              )
            })()}

          {overlays.candidates?.map((c, i) => {
            const p = toScreen(c.ra, c.dec)
            if (!visible(p, 20)) return null
            const from = c.ra_from !== undefined && c.dec_from !== undefined ? toScreen(c.ra_from, c.dec_from) : null
            return (
              <g key={`c${i}`} className="cand">
                {from && <line x1={from.x} y1={from.y} x2={p.x} y2={p.y} />}
                <rect x={p.x - 9} y={p.y - 9} width={18} height={18} />
                <text x={p.x + 12} y={p.y + 13} className="ovl-text">
                  {i + 1}
                </text>
              </g>
            )
          })}

          {props.tracks.map((tr) => {
            const pts = tr.points.map((m) => toScreen(m.ra_deg, m.dec_deg)).filter((p): p is { x: number; y: number } => p !== null)
            if (pts.length < 2) return null
            return <polyline key={tr.id} className="track" points={pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')} />
          })}

          {props.marks.map((m) => {
            const s = markScreen(m, grid, view, size)
            if (!s) return null
            const r = m.kind === 'region' ? Math.max(4, s.r) : 8
            if (!visible(s, r + 12)) return null
            const own = frameIndex === null || m.frame_index === frameIndex
            const selected = m.id === props.selectedId
            const showDate = !own || Boolean(m.track_id)
            const label = `${markNumber.get(m.id)}${showDate ? ` · ${fmtDay(props.frameDates[m.frame_index])}` : ''}`
            return (
              <g
                key={m.id}
                data-mark={m.id}
                className={`mark${selected ? ' mark-selected' : ''}${own ? '' : ' mark-other'}`}
              >
                <circle className="mark-hit" cx={s.x} cy={s.y} r={Math.max(r, 14)} />
                <circle className="mark-ring" cx={s.x} cy={s.y} r={r} />
                {m.kind === 'point' && <circle className="mark-dot" cx={s.x} cy={s.y} r={1.6} />}
                <text x={s.x + r * 0.71 + 5} y={s.y - r * 0.71 - 4} className="ovl-text mark-text">
                  {label}
                </text>
              </g>
            )
          })}

          {region && <circle className="mark-draft" cx={region.x} cy={region.y} r={region.r} />}
          <path className="centre-cross" d={`M${size.w / 2 - 9} ${size.h / 2}h18M${size.w / 2} ${size.h / 2 - 9}v18`} />
        </svg>
      )}

      <div className="pane-chip">{props.chip}</div>
      {props.busy && <div className="pane-busy">{t('app.loading')}</div>}
    </div>
  )
}

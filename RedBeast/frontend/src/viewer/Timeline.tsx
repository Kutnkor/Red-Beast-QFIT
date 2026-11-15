// Timeline: every frame sits at its real observation date. Numbered handles are spread apart just enough
// to stay tappable and are tied to their true-date tick by a leader line.

import { useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'
import { useI18n } from '../i18n'
import { fmtDateUTC, fmtDay } from '../lib/format'
import { framePositions, monthTicks, nearestFrame, spreadLabels } from '../lib/timeline'

export interface TimelineFrame {
  mjd: number
  date: string
}

const PAD = 14
const HANDLE = 24

export function Timeline({
  frames,
  current,
  reference,
  showReference,
  onSelect,
}: {
  frames: TimelineFrame[]
  current: number
  reference: number
  showReference: boolean
  onSelect: (index: number) => void
}) {
  const { t } = useI18n()
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(320)
  const [hover, setHover] = useState<number | null>(null)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => {
      const w = el.clientWidth || el.getBoundingClientRect().width
      if (w > 0) setWidth(w)
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const inner = Math.max(40, width - 2 * PAD)
  const positions = useMemo(() => framePositions(frames.map((f) => f.mjd)), [frames])
  const trueX = positions.map((p) => PAD + p * inner)
  const handleX = useMemo(() => spreadLabels(positions.map((p) => p * inner), HANDLE + 2, inner).map((x) => PAD + x), [positions, inner])
  const gap = frames.length > 1 ? inner / (frames.length - 1) : HANDLE
  const handleW = Math.max(14, Math.min(HANDLE, gap - 2))
  const first = frames[0]
  const last = frames[frames.length - 1]
  const months = first && last ? monthTicks(first.mjd, last.mjd) : []
  const span = first && last ? last.mjd - first.mjd : 0
  // Instrument ticks along the axis: they rise under the pointer and under the current frame.
  const needleX = trueX[current] ?? PAD
  const minor = useMemo(() => {
    const count = Math.max(12, Math.round(inner / 11)); let d = ''
    for (let i = 0; i <= count; i++) {
      const x = PAD + (i / count) * inner, dn = Math.abs(x - needleX), dp = hover === null ? 1e4 : Math.abs(x - hover)
      let h = 5
      if (dn < 30) { const c = Math.cos((dn / 30) * Math.PI / 2); h += 6 * c * c }
      if (dp < 60) { const c = Math.cos((dp / 60) * Math.PI / 2); h += 11 * c * c }
      d += `M${x.toFixed(1)} 38v${(-h).toFixed(1)}`
    }
    return d
  }, [inner, needleX, hover])

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.shiftKey || e.altKey || e.ctrlKey || e.metaKey) return
    let next = current
    if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') next = Math.max(0, current - 1)
    else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') next = Math.min(frames.length - 1, current + 1)
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = frames.length - 1
    else return
    e.preventDefault()
    if (next !== current) onSelect(next)
  }

  const onTrackClick = (e: MouseEvent<HTMLDivElement>) => {
    if ((e.target as Element).closest('button')) return
    const r = e.currentTarget.getBoundingClientRect()
    const frac = ((e.clientX - r.left) / (r.width || 1) * width - PAD) / inner
    const i = nearestFrame(positions, Math.min(1, Math.max(0, frac)))
    if (i >= 0) onSelect(i)
  }

  return (
    <div className="timeline" role="group" aria-label={t('tl.label')}>
      <div
        ref={ref}
        className="timeline-track"
        role="slider"
        tabIndex={0}
        aria-label={t('tl.label')}
        aria-valuemin={1}
        aria-valuemax={Math.max(1, frames.length)}
        aria-valuenow={current + 1}
        aria-valuetext={frames[current] ? t('tl.frame', { i: current + 1, date: fmtDateUTC(frames[current].date) }) : ''}
        onKeyDown={onKeyDown}
        onClick={onTrackClick}
        onPointerMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); setHover((e.clientX - r.left) / (r.width || 1) * width) }}
        onPointerLeave={() => setHover(null)}
      >
        <svg className="timeline-svg" width={width} height={62} aria-hidden="true">
          <path className="tl-minor" d={minor} />
          <line className="tl-axis" x1={PAD} y1={38} x2={width - PAD} y2={38} />
          {months.map((m) => (
            <g key={m.label}>
              <line className="tl-month" x1={PAD + m.frac * inner} y1={38} x2={PAD + m.frac * inner} y2={44} />
              <text className="tl-month-text" x={PAD + m.frac * inner} y={57} textAnchor="middle">
                {m.label}
              </text>
            </g>
          ))}
          {frames.map((_f, i) => (
            <g key={i} className={i === current ? 'tl-tick tl-tick-current' : 'tl-tick'}>
              <line x1={handleX[i]} y1={24} x2={trueX[i]} y2={32} />
              <line x1={trueX[i]} y1={32} x2={trueX[i]} y2={42} />
            </g>
          ))}
        </svg>
        <div className="tl-needle" style={{ transform: `translateX(${needleX.toFixed(1)}px)` }} aria-hidden="true" />
        {frames.map((f, i) => {
          const cls = ['tl-handle']
          if (i === current) cls.push('tl-handle-current')
          if (showReference && i === reference) cls.push('tl-handle-ref')
          return (
            <button
              key={i}
              type="button"
              tabIndex={-1}
              className={cls.join(' ')}
              style={{ left: handleX[i] - handleW / 2, width: handleW }}
              aria-label={t('tl.frame', { i: i + 1, date: fmtDateUTC(f.date) })}
              aria-current={i === current ? 'true' : undefined}
              title={fmtDateUTC(f.date)}
              onClick={() => onSelect(i)}
              data-frac={positions[i].toFixed(4)}
            >
              {i + 1}
              {showReference && i === reference && <span className="tl-badge">{t('tl.ref')}</span>}
            </button>
          )
        })}
      </div>
      {first && last && (
        <div className="timeline-ends">
          <span className="mono">{fmtDay(first.date)}</span>
          <span className="muted">{t('tl.span', { d: span.toFixed(span < 10 ? 2 : 0) })}</span>
          <span className="mono">{fmtDay(last.date)}</span>
        </div>
      )}
    </div>
  )
}

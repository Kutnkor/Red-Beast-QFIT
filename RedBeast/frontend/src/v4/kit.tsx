// RedBeast V4 kit: the shared components behind every view (see kit.css for the visual rules).
// They only use transforms/opacity for motion and honour reduced motion through CSS.
import { useSheet } from './sheet'
import { useCallback, useEffect, useId, useLayoutEffect, useRef, type KeyboardEvent as RKeyboardEvent, type PointerEvent as RPointerEvent, type ReactNode } from 'react'

/* ------------------------------------------------------------------ icons
   The V4 icon family (20 px grid, 1.6 px round strokes, one solid dot each), inlined so the same drawing
   is available in the frame document, the viewer's shadow root and the top document. */
const ICONS: Record<string, string> = {
  search: '<circle cx="8.75" cy="8.75" r="5.25"/><path d="M12.7 12.7 17 17"/><circle cx="8.75" cy="8.75" r="1.35" fill="currentColor" stroke="none"/>',
  book: '<path d="M10 5.6C8.3 4.4 5.9 4.1 3.5 4.6v10.3c2.4-.5 4.8-.2 6.5 1 1.7-1.2 4.1-1.5 6.5-1V4.6c-2.4-.5-4.8-.2-6.5 1z"/><path d="M10 5.6v10.3"/><circle cx="13.3" cy="8.2" r=".95" fill="currentColor" stroke="none"/>',
  measure: '<circle cx="5.4" cy="13.8" r="2.6" fill="currentColor" stroke="none"/><path d="M7.5 11.7 11.4 7.2H17"/><path d="M12.6 11.6H17"/><path d="M11 15.8h6" opacity=".5"/>',
  stack: '<path d="M10 3.2 17 7l-7 3.8L3 7z"/><path d="M3.6 10.4 10 13.9l6.4-3.5" opacity=".7"/><path d="M3.6 13.5 10 17l6.4-3.5" opacity=".45"/><circle cx="10" cy="7" r="1" fill="currentColor" stroke="none"/>',
  frames: '<rect x="3" y="4.5" width="10.5" height="10.5" rx="2"/><path d="M6.5 15v1.2a1.3 1.3 0 0 0 1.3 1.3h7.9a1.3 1.3 0 0 0 1.3-1.3V8.3A1.3 1.3 0 0 0 15.7 7h-2.2" opacity=".6"/><circle cx="8.25" cy="9.75" r="1.3" fill="currentColor" stroke="none"/>',
  galaxy: '<path d="M10 10c0-1.5 2.3-1.5 2.3.3 0 2.5-4.8 2.7-4.8-.6 0-4.1 7.4-4.3 7.4.9 0 5.5-10 5.3-10-1.4"/><circle cx="10" cy="10" r=".9" fill="currentColor" stroke="none"/>',
  orbit: '<circle cx="10" cy="10" r="3.1" fill="currentColor" stroke="none"/><ellipse cx="10" cy="10" rx="8" ry="3.4" transform="rotate(-24 10 10)"/>',
  evolve: '<circle cx="5" cy="14" r="1.7" fill="currentColor" stroke="none"/><path d="M5 14c2.2-6.5 5.4-8.6 10.6-8.9"/><circle cx="15.4" cy="5.2" r="2.6"/>',
  arrow: '<path d="M4.5 10h11M11 5.5 15.5 10 11 14.5"/>',
  prev: '<path d="M6 5v10"/><path d="M15 5.2 8.6 10l6.4 4.8z" fill="currentColor"/>',
  next: '<path d="M14 5v10"/><path d="M5 5.2 11.4 10 5 14.8z" fill="currentColor"/>',
  plus: '<path d="M10 4.5v11M4.5 10h11"/>',
  minus: '<path d="M4.5 10h11"/>',
  reset: '<path d="M4.6 8.2A5.8 5.8 0 1 1 4.2 10"/><path d="M4.2 4.4v3.9h3.9"/>',
  mark: '<circle cx="10" cy="10" r="4.2"/><path d="M10 2.5v3M10 14.5v3M2.5 10h3M14.5 10h3"/><circle cx="10" cy="10" r="1.1" fill="currentColor" stroke="none"/>',
  swap: '<path d="M4 7h11M12 4l3 3-3 3"/><path d="M16 13H5M8 10l-3 3 3 3"/>',
  x: '<path d="M5.5 5.5l9 9M14.5 5.5l-9 9"/>',
  blink: '<rect x="2.8" y="5" width="9" height="9" rx="2"/><rect x="8.2" y="7.2" width="9" height="9" rx="2" opacity=".55"/><circle cx="7.3" cy="9.5" r="1.3" fill="currentColor" stroke="none"/>',
  info: '<circle cx="10" cy="10" r="7"/><path d="M10 9.3v4.2"/><circle cx="10" cy="6.5" r=".95" fill="currentColor" stroke="none"/>',
  keys: '<rect x="2.5" y="5.5" width="15" height="9" rx="2.2"/><path d="M6 12h8"/><circle cx="6" cy="8.7" r=".8" fill="currentColor" stroke="none"/><circle cx="10" cy="8.7" r=".8" fill="currentColor" stroke="none"/><circle cx="14" cy="8.7" r=".8" fill="currentColor" stroke="none"/>',
  surface: '<circle cx="10" cy="10" r="6.6"/><path d="M5.6 8.2c1.6 1 2.8-1 4.4 0s2.8-1 4.4 0M6.4 12.2c1.3.8 2.3-.8 3.6 0s2.3-.8 3.6 0" opacity=".7"/>',
  table: '<path d="M3.75 3.5v12.75H17"/><path d="M6 13c2-5.6 4.4-8 9.6-8.2"/><circle cx="11.2" cy="7.2" r="1.4" fill="currentColor" stroke="none"/>',
  learn: '<path d="M2.8 7.6 10 4l7.2 3.6L10 11.2z"/><path d="M5.6 9.4v3.5c1.2 1.2 2.7 1.8 4.4 1.8s3.2-.6 4.4-1.8V9.4" opacity=".7"/><circle cx="17.2" cy="11.6" r="1" fill="currentColor" stroke="none"/>',
}
export function KIcon({ name, size = 18 }: { name: string; size?: number }) {
  return <svg className="kx-ic" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" dangerouslySetInnerHTML={{ __html: ICONS[name] ?? ICONS.info }} />
}

/* ------------------------------------------------------------ glider tabs */
export interface TabItem<T extends string> { id: T; label: ReactNode; icon?: string; disabled?: boolean; title?: string }
export function Glider<T extends string>({ items, value, onChange, label, small, className = '', glass = true }: {
  items: TabItem<T>[]; value: T | null; onChange: (id: T) => void; label: string; small?: boolean; className?: string; glass?: boolean
}) {
  const root = useRef<HTMLDivElement>(null), pill = useRef<HTMLElement>(null), first = useRef(true)
  const place = useCallback(() => {
    const el = root.current, g = pill.current; if (!el || !g) return
    const on = el.querySelector<HTMLElement>('button[aria-pressed="true"]')
    if (!on || !on.offsetWidth) { g.style.opacity = '0'; return }
    if (first.current) { g.style.transition = 'none'; first.current = false; requestAnimationFrame(() => { if (pill.current) pill.current.style.transition = '' }) }
    g.style.width = on.offsetWidth + 'px'; g.style.height = on.offsetHeight + 'px'
    g.style.transform = `translate(${on.offsetLeft}px,${on.offsetTop}px)`; g.style.opacity = '1'
  }, [])
  useLayoutEffect(place)
  useEffect(() => {
    const el = root.current; if (!el) return
    const view = el.ownerDocument.defaultView
    const ro = view && 'ResizeObserver' in view ? new (view as unknown as { ResizeObserver: typeof ResizeObserver }).ResizeObserver(place) : null
    ro?.observe(el); el.ownerDocument.fonts?.ready.then(place).catch(() => {})
    return () => ro?.disconnect()
  }, [place])
  return <div ref={root} className={`kx kx-tabs ${glass ? 'kx-glass' : ''} ${small ? 'kx-sm' : ''} ${className}`} role="group" aria-label={label}>
    <i ref={pill} className="kx-glider" aria-hidden="true" />
    {items.map(it => <button key={it.id} type="button" aria-pressed={value === it.id} disabled={it.disabled} title={it.title} onClick={() => { if (value !== it.id) onChange(it.id) }}>
      {it.icon && <KIcon name={it.icon} size={16} />}{it.label}
    </button>)}
  </div>
}

/* --------------------------------------------------------------- ring play */
const RING = 2 * Math.PI * 34
export function RingPlay({ playing, onToggle, progress, segments = 1, labelPlay, labelPause, disabled }: {
  playing: boolean; onToggle: () => void; progress: number; segments?: number; labelPlay: string; labelPause: string; disabled?: boolean
}) {
  const f = Math.min(1, Math.max(0, progress)), gap = segments > 1 ? 5 : 0, id = 'kxr' + useId().replace(/[^a-zA-Z0-9]/g, '')
  const th = f * 2 * Math.PI
  return <div className={`kx kx-ring ${playing ? 'kx-playing' : ''}`}>
    <svg viewBox="0 0 76 76" aria-hidden="true"><g transform="rotate(-90 38 38)">
      <mask id={id}><circle cx="38" cy="38" r="34" fill="none" stroke="#fff" strokeWidth="5" strokeDasharray={`${(RING / segments - gap).toFixed(2)} ${gap}`} strokeDashoffset={(-gap / 2).toFixed(2)} /></mask>
      <g mask={`url(#${id})`}><circle className="kx-track" cx="38" cy="38" r="34" /><circle className="kx-prog" cx="38" cy="38" r="34" strokeDasharray={`${(f * RING).toFixed(2)} ${RING.toFixed(2)}`} /></g>
      <circle className="kx-tip" cx={(38 + 34 * Math.cos(th)).toFixed(2)} cy={(38 + 34 * Math.sin(th)).toFixed(2)} r="3.6" />
    </g></svg>
    <button type="button" className="kx-play" onClick={onToggle} disabled={disabled} aria-label={playing ? labelPause : labelPlay} title={playing ? labelPause : labelPlay}><span className="kx-pp"><i /><i /></span></button>
  </div>
}

/* -------------------------------------------------------------- wave ruler
   A slider drawn as instrument ticks. The ticks rise under the pointer and under the needle. */
export interface RulerMajor { at: number; label?: string }
export function WaveRuler({ value, min, max, onChange, majors, minorStep, label, valueText, tip, pageStep, step }: {
  value: number; min: number; max: number; onChange: (v: number, final: boolean) => void
  majors: RulerMajor[]; minorStep: number; label: string; valueText: string; tip?: (v: number) => string; pageStep?: number; step?: number
}) {
  const root = useRef<HTMLDivElement>(null), past = useRef<SVGPathElement>(null), fut = useRef<SVGPathElement>(null), needle = useRef<HTMLDivElement>(null), tipEl = useRef<HTMLDivElement>(null)
  const live = useRef({ w: 0, ptr: -1e4, bump: 0, bumpTo: 0, raf: 0, value, drag: false, intro: 0, tick: () => {} })
  useLayoutEffect(() => { live.current.value = value })
  const frac = (v: number) => (v - min) / (max - min)
  const draw = useCallback(() => {
    const s = live.current, w = s.w; if (!w || !past.current || !fut.current) return
    const head = frac(s.value) * w, B = 46, majorAt = new Set(majors.map(m => Math.round((m.at - min) / minorStep)))
    const n = Math.round((max - min) / minorStep); let a = '', b = ''
    for (let i = 0; i <= n; i++) {
      const x = i / n * w, dp = Math.abs(x - s.ptr), dh = Math.abs(x - head)
      let h = majorAt.has(i) ? 21 : 7
      if (s.bump > 0.01 && dp < 74) { const c = Math.cos(dp / 74 * Math.PI / 2); h += 16 * c * c * s.bump }
      if (dh < 30) { const c = Math.cos(dh / 30 * Math.PI / 2); h += 7 * c * c }
      if (s.intro < 1) h *= Math.min(1, Math.max(0, (s.intro * 1.5 - x / w) * 3.2))
      if (h < 0.3) continue
      const seg = `M${x.toFixed(1)} ${B}v${(-h).toFixed(1)}`
      if (x <= head + 0.5) a += seg; else b += seg
    }
    past.current.setAttribute('d', a); fut.current.setAttribute('d', b)
    if (needle.current) needle.current.style.transform = `translateX(${head.toFixed(2)}px)`
  }, [majors, max, min, minorStep]) // eslint-disable-line react-hooks/exhaustive-deps
  const loop = useCallback(() => {
    const s = live.current, view = root.current?.ownerDocument.defaultView; s.raf = 0
    let more = false
    if (Math.abs(s.bumpTo - s.bump) > 0.01) { s.bump += (s.bumpTo - s.bump) * 0.2; more = true } else s.bump = s.bumpTo
    if (s.intro < 1) { s.intro = Math.min(1, s.intro + 0.035); more = true }
    draw()
    if (more && view) s.raf = view.requestAnimationFrame(s.tick)
  }, [draw])
  useLayoutEffect(() => { live.current.tick = loop }, [loop])
  const kick = useCallback(() => { const s = live.current, view = root.current?.ownerDocument.defaultView; if (!s.raf && view) s.raf = view.requestAnimationFrame(loop) }, [loop])
  useLayoutEffect(() => {
    const el = root.current; if (!el) return
    // defaultView is null for a moment while the V4 frame swaps the node it portals into: draw once and wait for the next run
    const view = el.ownerDocument.defaultView, s = live.current
    if (!view) { s.intro = 1; s.w = el.clientWidth; draw(); return }
    const reduce = view.matchMedia?.('(prefers-reduced-motion: reduce)').matches || !!el.closest('.calm')
    if (reduce) s.intro = 1
    const measure = () => { s.w = el.clientWidth; draw() }
    measure(); kick()
    const RO = (view as unknown as { ResizeObserver?: typeof ResizeObserver }).ResizeObserver
    const ro = RO ? new RO(measure) : null; ro?.observe(el)
    return () => { ro?.disconnect(); if (s.raf) view.cancelAnimationFrame(s.raf); s.raf = 0 }
  }, [draw, kick])
  useLayoutEffect(draw)
  const at = (e: RPointerEvent) => { const r = root.current!.getBoundingClientRect(); return Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) }
  const snap = (v: number) => step ? Math.round(v / step) * step : v
  const move = (e: RPointerEvent) => {
    const s = live.current, f = at(e); s.ptr = f * s.w; s.bumpTo = 1
    const v = snap(min + f * (max - min))
    if (tipEl.current && tip) { tipEl.current.textContent = tip(v); tipEl.current.style.left = (f * s.w).toFixed(1) + 'px' }
    root.current!.classList.add('kx-hover')
    if (s.drag) onChange(v, false)
    kick()
  }
  const key = (e: RKeyboardEvent) => {
    const small = step ?? minorStep, big = pageStep ?? small * 10
    const d = e.key === 'ArrowRight' || e.key === 'ArrowUp' ? small : e.key === 'ArrowLeft' || e.key === 'ArrowDown' ? -small : e.key === 'PageUp' ? big : e.key === 'PageDown' ? -big : 0
    let v = value
    if (e.key === 'Home') v = min; else if (e.key === 'End') v = max; else if (d) v = Math.min(max, Math.max(min, value + d)); else return
    e.preventDefault(); e.stopPropagation(); onChange(v, true)
  }
  return <div ref={root} className="kx kx-ruler" role="slider" tabIndex={0} aria-label={label} aria-valuemin={min} aria-valuemax={max} aria-valuenow={value} aria-valuetext={valueText}
    onKeyDown={key}
    onPointerDown={e => { live.current.drag = true; root.current!.classList.add('kx-drag'); e.currentTarget.setPointerCapture?.(e.pointerId); move(e) }}
    onPointerMove={move}
    onPointerUp={e => { if (live.current.drag) { live.current.drag = false; root.current!.classList.remove('kx-drag'); onChange(snap(min + at(e) * (max - min)), true) } }}
    onPointerCancel={() => { live.current.drag = false; root.current?.classList.remove('kx-drag') }}
    onPointerLeave={() => { const s = live.current; s.bumpTo = 0; root.current?.classList.remove('kx-hover'); kick() }}>
    <svg aria-hidden="true"><path ref={fut} className="kx-fut" /><path ref={past} className="kx-past" /></svg>
    <div ref={needle} className="kx-needle" />
    {tip && <div ref={tipEl} className="kx-ruler-tip" aria-hidden="true" />}
  </div>
}
export function RulerLabels({ majors, min, max }: { majors: RulerMajor[]; min: number; max: number }) {
  return <div className="kx-ruler-labels" aria-hidden="true">{majors.filter(m => m.label).map(m => <span key={m.at} style={{ left: `${(m.at - min) / (max - min) * 100}%` }}>{m.label}</span>)}</div>
}

/* ---------------------------------------------------------------- odometer */
const REEL = '0123456789'.split('')
export function Odometer({ text, size, label, decorative, instant }: { text: string; size?: number; label?: string; decorative?: boolean; instant?: boolean }) {
  const chars = text.split('')
  // instant: while the value changes every frame (fast playback) the wheels snap, so the number stays readable
  return <span className={`kx kx-odo${instant ? ' kx-snap' : ''}`} style={size ? { fontSize: size } : undefined} {...(decorative ? { 'aria-hidden': true } : { role: 'img', 'aria-label': label ?? text })}>
    {chars.map((ch, i) => {
      const k = chars.length - i            // key from the right so each wheel keeps its identity while digits are added
      if (ch < '0' || ch > '9') return <span key={'s' + k} className="kx-sep">{ch === ' ' ? ' ' : ch}</span>
      return <span key={'r' + k} className="kx-reel"><span className="kx-strip" style={{ transform: `translateY(${-1.06 * Number(ch)}em)` }}>{REEL.map(d => <i key={d}>{d}</i>)}</span></span>
    })}
  </span>
}

/* ----------------------------------------------------------- panel (dialog) */
const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])'
export function Panel({ title, onClose, children, wide, closeLabel, head, place = 'bottom' }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean; closeLabel: string; head?: ReactNode; place?: 'bottom' | 'top' }) {
  const ref = useRef<HTMLDivElement>(null), { closing, close } = useSheet(ref, onClose, place)
  useEffect(() => { const previous = document.activeElement as HTMLElement | null; const first = ref.current?.querySelector<HTMLElement>('[data-autofocus]') ?? ref.current; first?.focus(); return () => previous?.focus?.() }, [])
  const onKeyDown = (e: RKeyboardEvent) => {
    if (e.key === 'Escape') { e.stopPropagation(); close(); return }
    if (e.key !== 'Tab' || !ref.current) return
    const items = Array.from(ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)); if (!items.length) return
    const a = items[0], z = items[items.length - 1]
    if (e.shiftKey && (document.activeElement === a || document.activeElement === ref.current)) { e.preventDefault(); z.focus() }
    else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus() }
  }
  return <div className="kx-scope kx-scrim" data-dialog data-place={place} data-closing={closing || undefined} onMouseDown={e => { if (e.target === e.currentTarget) close() }}>
    <div ref={ref} className={`kx kx-panel kx-glass kx-deep ${wide ? 'kx-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} onKeyDown={onKeyDown}>
      <header className="kx-panel-head">{head ?? <h2>{title}</h2>}<button type="button" className="kx-ibtn kx-press" onClick={close} aria-label={closeLabel}><KIcon name="x" /></button></header>
      <div className="kx-panel-body">{children}</div>
    </div>
  </div>
}

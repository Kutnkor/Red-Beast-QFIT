// Sheets, not pop-ups. A panel grows out of the control that opened it and settles where it lives
// (docked to the bottom edge, or under the search field); closing sends it back the same way.
// The last pointer position is remembered here so the opening move can start from it.
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'

let last: { x: number; y: number; at: number } | null = null
const note = (event: PointerEvent) => { last = { x: event.clientX, y: event.clientY, at: Date.now() } }

/** Call for every window whose clicks can open a sheet (the page itself and the V4 frame, which fills the page). */
export function watchSheetOrigin(view: Window | null | undefined): () => void {
  if (!view) return () => undefined
  view.addEventListener('pointerdown', note, true)
  return () => view.removeEventListener('pointerdown', note, true)
}
if (typeof window !== 'undefined') watchSheetOrigin(window)

/** place: where the sheet lives. 'bottom' rises from the bottom edge, 'top' drops from the search field. */
export function useSheet(ref: RefObject<HTMLElement | null>, onClose: () => void, place: 'bottom' | 'top' = 'bottom') {
  const [closing, setClosing] = useState(false), leaving = useRef(false)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const fresh = last && Date.now() - last.at < 900 ? last : null
    const fromX = fresh ? fresh.x : window.innerWidth / 2, fromY = fresh ? fresh.y : place === 'top' ? 42 : window.innerHeight + 60
    // layout box, not the animated one: offsets ignore the transform the opening animation starts with
    el.style.setProperty('--sx', `${Math.round(fromX - (el.offsetLeft + el.offsetWidth / 2))}px`)
    el.style.setProperty('--sy', `${Math.round(fromY - (el.offsetTop + el.offsetHeight / 2))}px`)
  }, [ref, place])
  const close = useCallback(() => {
    if (leaving.current) return
    const el = ref.current, name = el ? getComputedStyle(el).animationName : ''
    const animated = !!name && name !== 'none' && !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (!animated) { onClose(); return }
    leaving.current = true
    setClosing(true)
    window.setTimeout(onClose, 240)
  }, [onClose, ref])
  // Drag the header (the grabber) down to put the sheet away; a short drag springs back. Uses the separate
  // `translate` property, so it adds to the opening animation instead of fighting it.
  useEffect(() => {
    const el = ref.current, head = el?.querySelector<HTMLElement>('.kx-panel-head, .dialog-head')
    if (!el || !head || place === 'top') return
    let startY = 0, startT = 0, dy = 0, dragging = false
    const down = (e: PointerEvent) => {
      if (e.button !== 0 || (e.target as HTMLElement).closest('button, a, input, select, textarea')) return
      dragging = true; startY = e.clientY; startT = e.timeStamp; dy = 0
      head.setPointerCapture?.(e.pointerId); el.style.transition = 'none'; el.dataset.dragging = 'true'
    }
    const move = (e: PointerEvent) => {
      if (!dragging) return
      const raw = e.clientY - startY
      dy = raw > 0 ? raw : raw * .18
      el.style.translate = `0 ${Math.round(dy)}px`
      e.preventDefault()
    }
    const up = (e: PointerEvent) => {
      if (!dragging) return
      dragging = false; delete el.dataset.dragging
      const speed = dy / Math.max(1, e.timeStamp - startT)            // px per ms
      if (dy > Math.min(180, el.offsetHeight * .3) || (dy > 40 && speed > .7)) { close(); return }
      el.style.transition = 'translate 360ms cubic-bezier(.2,.9,.3,1.2)'
      el.style.translate = '0 0'
    }
    head.addEventListener('pointerdown', down); head.addEventListener('pointermove', move)
    head.addEventListener('pointerup', up); head.addEventListener('pointercancel', up)
    return () => { head.removeEventListener('pointerdown', down); head.removeEventListener('pointermove', move); head.removeEventListener('pointerup', up); head.removeEventListener('pointercancel', up) }
  }, [ref, place, close])
  return { closing, close }
}

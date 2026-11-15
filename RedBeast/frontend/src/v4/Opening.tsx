// The one orchestrated moment of the app: on the first load of a browser session the wordmark draws itself, the
// robin lands, and the curtain lifts onto the real observations. Any key or click skips it. It is skipped entirely
// with reduced motion, in capture mode (?clean=1) and under test.
import { useEffect, useState } from 'react'

const STROKES = [
  ['red', 'M6 13V27M6 20a7 7 0 0 1 7-7h1.2'], ['red', 'M20.5 20h14a7 7 0 1 0-1.64 4.5'], ['red', 'M57.1 20a7 7 0 1 0-14 0a7 7 0 1 0 14 0'], ['red', 'M57.1 3V27'],
  ['beast', 'M65.7 3V27'], ['beast', 'M79.7 20a7 7 0 1 0-14 0a7 7 0 1 0 14 0'], ['beast', 'M88.3 20h14a7 7 0 1 0-1.64 4.5'], ['beast', 'M124.9 20a7 7 0 1 0-14 0a7 7 0 1 0 14 0'],
  ['beast', 'M124.9 13V27'], ['beast', 'M143.03 15.02A5 3.5 0 1 0 138.5 20A5 3.5 0 1 1 133.97 24.98'], ['beast', 'M152.5 6V23a4 4 0 0 0 4 4h2M147.5 13h10.5'],
] as const

function shouldPlay(): boolean {
  if (import.meta.env.MODE === 'test' || typeof window === 'undefined') return false
  if (new URLSearchParams(window.location.search).has('clean') || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return false
  try { if (sessionStorage.getItem('rb.opened') === '1') return false; sessionStorage.setItem('rb.opened', '1') } catch { return false }
  return true
}

export function Opening({ lang }: { lang: 'tr' | 'en' }) {
  const [phase, setPhase] = useState<'play' | 'lift' | 'gone'>(() => shouldPlay() ? 'play' : 'gone')
  useEffect(() => {
    if (phase === 'gone') return
    const lift = () => setPhase(p => p === 'play' ? 'lift' : p)
    const a = window.setTimeout(lift, 2100), b = window.setTimeout(() => setPhase('gone'), 2800)
    window.addEventListener('keydown', lift); window.addEventListener('pointerdown', lift)
    return () => { window.clearTimeout(a); window.clearTimeout(b); window.removeEventListener('keydown', lift); window.removeEventListener('pointerdown', lift) }
  }, [phase === 'gone'])   // eslint-disable-line react-hooks/exhaustive-deps
  if (phase === 'gone') return null
  return <div className="rb-open" data-phase={phase} aria-hidden="true">
    <div className="rb-open-mark">
      <img src="/redbeast-bird.png" width="92" height="92" alt="" />
      <svg viewBox="0 0 164 33" fill="none" strokeWidth="5.4" strokeLinejoin="round">
        {STROKES.map(([part, d], i) => <path key={i} className={`rb-open-${part}`} d={d} pathLength={1} style={{ animationDelay: `${260 + i * 70}ms` }} />)}
      </svg>
    </div>
    <p>{lang === 'tr' ? 'Gökyüzünde ne değişti, kendin gör.' : 'See for yourself what changed in the sky.'}</p>
  </div>
}

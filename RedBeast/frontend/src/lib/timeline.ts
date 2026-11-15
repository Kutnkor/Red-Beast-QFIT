// Timeline geometry: frames sit at their real observation dates, never at uniform steps.

import { mjdToDate } from './format'

/** Fraction (0..1) of each frame along the real time axis. One frame, or identical dates, sit in the middle. */
export function framePositions(mjds: number[]): number[] {
  if (mjds.length === 0) return []
  const lo = Math.min(...mjds)
  const hi = Math.max(...mjds)
  const span = hi - lo
  if (!(span > 0)) return mjds.map(() => 0.5)
  return mjds.map((m) => (m - lo) / span)
}

/** Index of the frame closest in time to a position on the axis (earliest wins ties). */
export function nearestFrame(positions: number[], frac: number): number {
  let best = -1
  let bd = Infinity
  positions.forEach((p, i) => {
    const d = Math.abs(p - frac)
    if (d < bd) {
      bd = d
      best = i
    }
  })
  return best
}

/**
 * Place labels near their true x positions while keeping at least `minGap` between neighbours and staying
 * inside [0, width]. Order is preserved. Used for the numbered frame handles above the true-date ticks.
 */
export function spreadLabels(xs: number[], minGap: number, width: number): number[] {
  const n = xs.length
  if (n === 0) return []
  const gap = n > 1 ? Math.min(minGap, width / (n - 1)) : minGap
  const out = xs.map((x) => Math.min(width, Math.max(0, x)))
  for (let i = 1; i < n; i++) out[i] = Math.max(out[i], out[i - 1] + gap)
  if (out[n - 1] > width) {
    out[n - 1] = width
    for (let i = n - 2; i >= 0; i--) out[i] = Math.min(out[i], out[i + 1] - gap)
  }
  return out.map((x) => Math.min(width, Math.max(0, x)))
}

export interface AxisTick {
  frac: number
  label: string
}

/** Month (or year) boundaries inside [mjdFirst, mjdLast], thinned to at most `maxTicks`. */
export function monthTicks(mjdFirst: number, mjdLast: number, maxTicks = 7): AxisTick[] {
  const span = mjdLast - mjdFirst
  if (!(span > 0)) return []
  const start = mjdToDate(mjdFirst)
  const end = mjdToDate(mjdLast)
  const all: { t: number; y: number; m: number }[] = []
  let y = start.getUTCFullYear()
  let m = start.getUTCMonth() + 1
  for (let guard = 0; guard < 600; guard++) {
    if (m > 11) {
      m = 0
      y += 1
    }
    const t = Date.UTC(y, m, 1)
    if (t > end.getTime()) break
    all.push({ t, y, m })
    m += 1
  }
  if (all.length === 0) return []
  const step = Math.max(1, Math.ceil(all.length / maxTicks))
  // keep Januaries aligned when thinning so year changes stay visible
  const picked = all.filter((d) => (step === 1 ? true : d.m % step === 0))
  const t0 = start.getTime()
  const total = end.getTime() - t0
  return picked.map((d) => ({
    frac: (d.t - t0) / total,
    label: `${d.y}-${String(d.m + 1).padStart(2, '0')}`,
  }))
}

/** Days between two MJDs, formatted for humans ("5.0", "392.9"). */
export function daysBetween(a: number, b: number): number {
  return Math.abs(b - a)
}

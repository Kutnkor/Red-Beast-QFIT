import { describe, expect, it } from 'vitest'
import { framePositions, monthTicks, nearestFrame, spreadLabels } from '../lib/timeline'

// real Barnard's Star sequence: 2025-08-25, 2025-08-30, 2026-03-15, 2026-08-18, 2026-08-21, 2026-09-22
const MJD = [60912.714812798, 60917.674605726, 61114.035654152, 61270.86778171, 61273.788888342, 61305.628686803]

describe('timeline positions follow real observation dates', () => {
  const pos = framePositions(MJD)

  it('first and last frames sit at the ends', () => {
    expect(pos[0]).toBe(0)
    expect(pos[5]).toBe(1)
  })

  it('spacing is proportional to elapsed time, not to the frame number', () => {
    const span = MJD[5] - MJD[0]
    MJD.forEach((m, i) => expect(pos[i]).toBeCloseTo((m - MJD[0]) / span, 12))
    // 5 days out of 393: the second frame is almost on top of the first
    expect(pos[1]).toBeLessThan(0.02)
    // the 196-day gap dominates the axis
    expect(pos[2] - pos[1]).toBeGreaterThan(0.45)
    expect(pos[4] - pos[3]).toBeLessThan(0.01)
    // definitely not uniform
    expect(pos[1]).not.toBeCloseTo(1 / 5, 2)
  })

  it('handles single frames and identical dates', () => {
    expect(framePositions([])).toEqual([])
    expect(framePositions([61000])).toEqual([0.5])
    expect(framePositions([61000, 61000])).toEqual([0.5, 0.5])
  })

  it('positions are monotonic for sorted dates', () => {
    for (let i = 1; i < pos.length; i++) expect(pos[i]).toBeGreaterThan(pos[i - 1])
  })

  it('picks the frame nearest in time to a click', () => {
    expect(nearestFrame(pos, 0)).toBe(0)
    expect(nearestFrame(pos, 0.5)).toBe(2)
    expect(nearestFrame(pos, 0.93)).toBe(4)
    expect(nearestFrame(pos, 1)).toBe(5)
    expect(nearestFrame([], 0.3)).toBe(-1)
  })
})

describe('handle spreading', () => {
  it('keeps handles apart, ordered and inside the track', () => {
    const width = 600
    const xs = framePositions(MJD).map((p) => p * width)
    const out = spreadLabels(xs, 26, width)
    expect(out).toHaveLength(6)
    for (let i = 1; i < out.length; i++) expect(out[i] - out[i - 1]).toBeGreaterThanOrEqual(26 - 1e-9)
    expect(out[0]).toBeGreaterThanOrEqual(0)
    expect(out[5]).toBeLessThanOrEqual(width)
    // isolated frames are not moved at all
    expect(out[0]).toBe(xs[0])
    expect(out[2]).toBeCloseTo(xs[2], 9)
    expect(out[5]).toBe(xs[5])
  })

  it('shrinks the gap when there is not enough room (16 frames on a phone)', () => {
    const width = 315
    const xs = Array.from({ length: 16 }, (_, i) => (i < 8 ? i * 0.5 : width - (15 - i) * 0.5))
    const out = spreadLabels(xs, 26, width)
    const gap = width / 15
    for (let i = 1; i < out.length; i++) expect(out[i] - out[i - 1]).toBeGreaterThanOrEqual(gap - 1e-6)
    expect(Math.min(...out)).toBeGreaterThanOrEqual(-1e-6)
    expect(Math.max(...out)).toBeLessThanOrEqual(width + 1e-6)
  })

  it('leaves well separated positions untouched', () => {
    expect(spreadLabels([0, 100, 300], 26, 300)).toEqual([0, 100, 300])
    expect(spreadLabels([], 26, 300)).toEqual([])
  })
})

describe('month ticks', () => {
  it('marks month boundaries at their real position', () => {
    const ticks = monthTicks(MJD[0], MJD[5], 20)
    expect(ticks[0].label).toBe('2025-09')
    expect(ticks[ticks.length - 1].label).toBe('2026-09')
    expect(ticks).toHaveLength(13)
    // 2026-01-01 is MJD 61041
    const jan = ticks.find((t) => t.label === '2026-01')
    expect(jan?.frac).toBeCloseTo((61041 - MJD[0]) / (MJD[5] - MJD[0]), 6)
    for (const t of ticks) {
      expect(t.frac).toBeGreaterThanOrEqual(0)
      expect(t.frac).toBeLessThanOrEqual(1)
    }
  })

  it('thins long spans and returns nothing for a zero span', () => {
    expect(monthTicks(MJD[0], MJD[5], 7).length).toBeLessThanOrEqual(7)
    expect(monthTicks(MJD[0], MJD[5], 7).some((t) => t.label === '2026-01')).toBe(true)
    expect(monthTicks(61000, 61000)).toEqual([])
    expect(monthTicks(61000, 61003)).toEqual([])
  })
})

export type Quality = 'high' | 'medium' | 'low'
export const qualityDpr: Record<Quality, number> = { high: 2, medium: 1.5, low: 1 }
export function forcedQuality(): Quality | null {
  const value = new URLSearchParams(location.search).get('quality')
  return value === 'high' || value === 'medium' || value === 'low' ? value : null
}
export function qualityForAverage(milliseconds: number): Quality {
  return milliseconds > 33 ? 'low' : milliseconds > 22 ? 'medium' : 'high'
}
export class QualityMonitor {
  private samples: number[] = []
  sample(milliseconds: number): Quality | null {
    // Idle gaps are not frame timings. Measure only consecutive animation/interaction frames.
    if (this.samples.length >= 60 || milliseconds > 100 || milliseconds <= 0) return null
    this.samples.push(milliseconds)
    if (this.samples.length !== 60) return null
    return qualityForAverage(this.samples.reduce((sum, value) => sum + value, 0) / 60)
  }
}

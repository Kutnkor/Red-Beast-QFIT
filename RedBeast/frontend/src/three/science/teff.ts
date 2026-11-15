/** Ballesteros 2012, EPL 97 34008, https://doi.org/10.1209/0295-5075/97/34008 */
export function teffFromBV(bv: number | null | undefined): number | null {
  if (bv == null || !Number.isFinite(bv) || .92 * bv + .62 <= 0) return null
  const value = 4600 * (1 / (.92 * bv + 1.7) + 1 / (.92 * bv + .62))
  return value > 0 && Number.isFinite(value) ? value : null
}

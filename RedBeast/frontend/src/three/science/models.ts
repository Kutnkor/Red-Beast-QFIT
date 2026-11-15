import type { ModelComponent, StellarProfile, Vec3 } from '../types'

export function parameter(profile: StellarProfile | null, name: string): number | null {
  const value = profile?.parameters[name]?.value
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
export function componentParameter(component: ModelComponent | undefined, name: 'radius_solar' | 'teff_k'): number | null {
  const value = component?.parameters?.[name]?.value ?? component?.[name]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
export function hasPhenomenon(profile: StellarProfile | null, ...ids: string[]): boolean {
  return !!profile?.phenomena.some((phenomenon) => phenomenon.enabled && ids.includes(phenomenon.id))
}
/** An explicitly labelled square-root display scale: the Sun is one display unit. */
export function visualRadius(radiusSolar: number | null): number {
  return radiusSolar !== null && Number.isFinite(radiusSolar) && radiusSolar > 0 ? Math.sqrt(radiusSolar) : 1
}

/** Fit a bounding sphere in both dimensions, including narrow portrait viewports. */
export function fitDistance(radius: number, verticalFovDeg: number, aspect: number): number {
  const vertical = verticalFovDeg * Math.PI / 360
  const horizontal = Math.atan(Math.tan(vertical) * Math.max(.1, aspect))
  return radius * 1.08 / Math.sin(Math.min(vertical, horizontal))
}
export type SurfaceKind = 'photosphere' | 'clouds' | 'accreting' | 'giant'
export function surfaceKind(profile: StellarProfile | null): SurfaceKind {
  if (hasPhenomenon(profile, 'clouds', 'cloud_bands', 'atmosphere')) return 'clouds'
  if (hasPhenomenon(profile, 'disk', 'accretion_disk', 'accretion', 'hotspots')) return 'accreting'
  if (hasPhenomenon(profile, 'pulsation', 'dust_outflow')) return 'giant'
  return 'photosphere'
}

/** Relative Kepler ellipse, a=1. Orbital phase and node orientation remain illustrative. */
export function keplerEllipse(meanAnomaly: number, eccentricity: number, inclinationDeg: number): Vec3 {
  if (!Number.isFinite(meanAnomaly) || !Number.isFinite(eccentricity) || eccentricity < 0 || eccentricity >= 1 || !Number.isFinite(inclinationDeg)) throw new RangeError('Invalid orbital parameters')
  const mean = ((meanAnomaly % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)
  let eccentric = mean
  for (let iteration = 0; iteration < 12; iteration++) eccentric -= (eccentric - eccentricity * Math.sin(eccentric) - mean) / (1 - eccentricity * Math.cos(eccentric))
  const x = Math.cos(eccentric) - eccentricity
  const y = Math.sqrt(1 - eccentricity ** 2) * Math.sin(eccentric)
  const inclination = inclinationDeg * Math.PI / 180
  return [x, y * Math.cos(inclination), y * Math.sin(inclination)]
}

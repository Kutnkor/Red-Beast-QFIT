import type { MotionStar, Vec3 } from '../types'

// Exact angular conversion and the IAU Julian year / IAU parsec definition.
export const MAS_TO_RAD = Math.PI / (180 * 3600000)
export const KM_S_TO_PC_YR = 31557600 / 3.085677581491367e13
export const PC_TO_LY = 3.2615637771674333
export const AU_PER_PC = 648000 / Math.PI
export const MOTION_SCALE = 600
export const AU_PER_MOTION_UNIT = AU_PER_PC / MOTION_SCALE

/** Linear Cartesian space motion, no parallax or observer effect. ICRS -> Y-up (x,z,y). */
export function position(star: MotionStar, year: number): Vec3 {
  const ra = star.ra * Math.PI / 180
  const dec = star.dec * Math.PI / 180
  const cr = Math.cos(ra), sr = Math.sin(ra), cd = Math.cos(dec), sd = Math.sin(dec)
  const distance = star.distancePc
  const east = star.pmRa * MAS_TO_RAD * distance
  const north = star.pmDec * MAS_TO_RAD * distance
  const radial = star.hasRadialVelocity ? star.radialVelocity * KM_S_TO_PC_YR : 0
  const dt = year - star.epoch
  return [
    distance * cd * cr + dt * (-east * sr - north * sd * cr + radial * cd * cr),
    distance * sd + dt * (north * cd + radial * sd),
    distance * cd * sr + dt * (east * cr - north * sd * sr + radial * cd * sr),
  ]
}

export function displacement(star: MotionStar, year: number, originYear = 2026, scale = MOTION_SCALE): Vec3 {
  const p = position(star, year), origin = position(star, originYear)
  return [0, 1, 2].map((i) => (p[i] - origin[i]) * scale) as Vec3
}

export function angularShift(star: MotionStar, from: number, to: number) {
  const a = position(star, from), b = position(star, to)
  const raA = Math.atan2(a[2], a[0]), decA = Math.atan2(a[1], Math.hypot(a[0], a[2]))
  const raB = Math.atan2(b[2], b[0]), decB = Math.atan2(b[1], Math.hypot(b[0], b[2]))
  const dra = Math.atan2(Math.sin(raB - raA), Math.cos(raB - raA))
  const h = Math.sin((decB - decA) / 2) ** 2
    + Math.cos(decA) * Math.cos(decB) * Math.sin(dra / 2) ** 2
  const angle = 2 * Math.asin(Math.min(1, Math.sqrt(h)))
  const bearing = Math.atan2(Math.sin(dra) * Math.cos(decB),
    Math.cos(decA) * Math.sin(decB) - Math.sin(decA) * Math.cos(decB) * Math.cos(dra))
  const arcsec = angle * 180 / Math.PI * 3600
  return {
    arcsec,
    eastArcsec: arcsec * Math.sin(bearing),
    northArcsec: arcsec * Math.cos(bearing),
    bearingDeg: (bearing * 180 / Math.PI + 360) % 360,
  }
}

export function compass(bearing: number, lang: 'tr' | 'en' = 'en'): string {
  const names = lang === 'tr'
    ? ['kuzey', 'kuzeydoğu', 'doğu', 'güneydoğu', 'güney', 'güneybatı', 'batı', 'kuzeybatı']
    : ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west']
  return names[Math.round(((bearing % 360 + 360) % 360) / 45) % 8]
}

export function distanceLy(star: MotionStar, year?: number): number {
  return (year === undefined ? star.distancePc : Math.hypot(...position(star, year))) * PC_TO_LY
}

/** Heliocentric ICRS direction at the chosen epoch, using the same 3D motion as the scene. */
export function skyCoordinates(star: MotionStar, year: number) {
  const [x, y, z] = position(star, year)
  return { ra: (Math.atan2(z, x) * 180 / Math.PI + 360) % 360,
    dec: Math.atan2(y, Math.hypot(x, z)) * 180 / Math.PI, distancePc: Math.hypot(x, y, z) }
}
export function parseSkyQuery(value: string): { ra: number; dec: number } | null {
  const match = value.trim().match(/^([+-]?\d+(?:\.\d+)?)\s*[,;\s]\s*([+-]?\d+(?:\.\d+)?)$/)
  if (!match) return null
  const ra = Number(match[1]), dec = Number(match[2])
  return ra >= 0 && ra < 360 && dec >= -90 && dec <= 90 ? { ra, dec } : null
}
export function angularSeparation(a: { ra: number; dec: number }, b: { ra: number; dec: number }): number {
  const r = Math.PI / 180, d = (b.dec - a.dec) * r, a1 = a.dec * r, b1 = b.dec * r
  const h = Math.sin(d / 2) ** 2 + Math.cos(a1) * Math.cos(b1) * Math.sin((b.ra - a.ra) * r / 2) ** 2
  return 2 * Math.asin(Math.sqrt(Math.max(0, Math.min(1, h)))) / r
}

export function mjdToYear(mjd: number): number { return 2000 + (mjd - 51544.5) / 365.25 }

export function tangentBasis(raDeg: number, decDeg: number): { east: Vec3; north: Vec3; radial: Vec3 } {
  const ra = raDeg * Math.PI / 180, dec = decDeg * Math.PI / 180
  return {
    east: [-Math.sin(ra), 0, Math.cos(ra)],
    north: [-Math.sin(dec) * Math.cos(ra), Math.cos(dec), -Math.sin(dec) * Math.sin(ra)],
    radial: [Math.cos(dec) * Math.cos(ra), Math.sin(dec), Math.cos(dec) * Math.sin(ra)],
  }
}

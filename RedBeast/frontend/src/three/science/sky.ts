import type { Vec3 } from '../types'
export function raDecToVector(ra: number, dec: number): Vec3 {
  const a = ra * Math.PI / 180, d = dec * Math.PI / 180
  return [Math.cos(d) * Math.cos(a), Math.sin(d), Math.cos(d) * Math.sin(a)]
}
export function eclipticPoints(obliquityDeg: number, stepDeg = 2): Vec3[] {
  const e = obliquityDeg * Math.PI / 180
  const points: Vec3[] = []
  for (let lon = 0; lon <= 360; lon += stepDeg) {
    const l = lon * Math.PI / 180
    points.push([Math.cos(l), Math.sin(l) * Math.sin(e), Math.sin(l) * Math.cos(e)])
  }
  return points
}
export function graticule(stepDeg = 15): Vec3[][] {
  const lines: Vec3[][] = []
  for (let ra = 0; ra < 360; ra += stepDeg * 2) {
    const meridian: Vec3[] = []
    for (let dec = -90; dec <= 90; dec += 2) meridian.push(raDecToVector(ra, dec))
    lines.push(meridian)
  }
  for (let dec = -75; dec <= 75; dec += stepDeg) {
    const parallel: Vec3[] = []
    for (let ra = 0; ra <= 360; ra += 2) parallel.push(raDecToVector(ra, dec))
    lines.push(parallel)
  }
  return lines
}

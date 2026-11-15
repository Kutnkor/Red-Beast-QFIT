import { Line2 } from 'three/addons/lines/Line2.js'
import { LineGeometry } from 'three/addons/lines/LineGeometry.js'
import { LineMaterial } from 'three/addons/lines/LineMaterial.js'
import { AdditiveBlending } from 'three'
import { tokenColor } from '../tokens'
import type { Vec3 } from '../types'
/** A path drawn as light: one colour per point, so it can fade in and out along its length (black = invisible). */
export function buildGlowLine(points: Vec3[], colors: Vec3[], width = 2): Line2 {
  const geometry = new LineGeometry()
  geometry.setPositions(points.flat())
  geometry.setColors(colors.flat())
  const line = new Line2(geometry, new LineMaterial({ vertexColors: true, linewidth: width, transparent: true, depthWrite: false, depthTest: false, blending: AdditiveBlending }))
  line.renderOrder = 12
  return line
}
export function buildLine(points: Vec3[], cssToken = '--rule', width = 1, opacity = 1, dashed = false): Line2 {
  const geometry = new LineGeometry()
  geometry.setPositions(points.flat())
  const material = new LineMaterial({ color: tokenColor(cssToken).getHex(), linewidth: width,
    transparent: opacity < 1, opacity, depthWrite: false, dashed, dashSize: .06, gapSize: .04 })
  const line = new Line2(geometry, material)
  if (dashed) line.computeLineDistances()
  return line
}

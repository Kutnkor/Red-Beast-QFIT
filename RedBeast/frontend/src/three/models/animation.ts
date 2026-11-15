import { Quaternion, Vector3 } from 'three'
import type { Camera, Object3D, ShaderMaterial } from 'three'
import { keplerEllipse } from '../science/models'

export interface ModelAnimation {
  kind: 'steady' | 'binary' | 'pulsating'
  radius: number
  secondaryRadius: number | null
  separation: number
  eccentricity: number
  inclinationDeg: number
}

/** Works on both the live model and an ObjectLoader-loaded .three.json snapshot. */
export function animateStellarModel(root: Object3D, seconds: number): void {
  const animation = root.userData.animation as ModelAnimation | undefined
  if (!animation) return
  const time = Number.isFinite(seconds) ? Math.max(0, seconds) : 0
  const primary = root.getObjectByName('primary-body'), secondary = root.getObjectByName('secondary-body')
  const surface = primary?.getObjectByName('stellar-surface')
  const phase = animation.kind === 'pulsating' ? Math.sin(time * Math.PI / 4) : 0
  surface?.scale.setScalar(animation.radius * (1 + .055 * phase))
  if (primary && secondary) {
    const position = new Vector3(...keplerEllipse(time * .06, animation.eccentricity, animation.inclinationDeg)).multiplyScalar(animation.separation / 2)
    primary.position.copy(position).negate()
    secondary.position.copy(position)
    secondary.getObjectByName('stellar-surface')?.scale.setScalar(animation.secondaryRadius ?? 1)
  }
  root.traverse(object => {
    const material = (object as Object3D & { material?: ShaderMaterial }).material
    const uniforms = material?.uniforms
    if (!uniforms) return
    if (uniforms.uTime) uniforms.uTime.value = time
    if (uniforms.uThermalPhase) uniforms.uThermalPhase.value = -phase
    if (uniforms.uStrength && uniforms.uBaseStrength) uniforms.uStrength.value = uniforms.uBaseStrength.value * (1 - .04 * phase) ** 4
  })
}

export function faceStellarModel(root: Object3D, camera: Camera, pixelRatio = 1): void {
  root.traverse(object => {
    const material = (object as Object3D & { material?: ShaderMaterial }).material
    if (material?.uniforms?.uPixelRatio) material.uniforms.uPixelRatio.value = Math.max(1, Math.min(2, pixelRatio))
    if (!['surface-outline', 'solar-radius-reference'].includes(object.name) || !object.parent) return
    object.quaternion.copy(object.parent.getWorldQuaternion(new Quaternion()).invert()).multiply(camera.getWorldQuaternion(new Quaternion()))
  })
}

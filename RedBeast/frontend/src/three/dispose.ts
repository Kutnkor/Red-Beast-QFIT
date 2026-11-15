import { Material, Texture } from 'three'
import type { Object3D, BufferGeometry } from 'three'
export function disposeTree(root: Object3D): void {
  const geometries = new Set<BufferGeometry>()
  const materials = new Set<Material>()
  const textures = new Set<Texture>()
  root.traverse((object) => {
    const item = object as Object3D & { geometry?: BufferGeometry; material?: Material | Material[] }
    if (item.geometry) geometries.add(item.geometry)
    if (item.material) (Array.isArray(item.material) ? item.material : [item.material]).forEach((m) => materials.add(m))
  })
  for (const material of materials) {
    for (const value of Object.values(material)) if (value instanceof Texture) textures.add(value)
    const uniforms = (material as Material & { uniforms?: Record<string, { value: unknown }> }).uniforms
    if (uniforms) for (const uniform of Object.values(uniforms)) if (uniform.value instanceof Texture) textures.add(uniform.value)
    material.dispose()
  }
  textures.forEach((texture) => texture.dispose())
  geometries.forEach((geometry) => geometry.dispose())
  root.clear()
}

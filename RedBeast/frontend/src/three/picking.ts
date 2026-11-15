import { PerspectiveCamera, Raycaster, Vector2, Vector3 } from 'three'
import type { Object3D, Points } from 'three'
/** A ray candidate list followed by a strict six-CSS-pixel screen-distance test. */
export function pickPoint(points: Points, camera: PerspectiveCamera, canvas: HTMLCanvasElement,
  clientX: number, clientY: number, thresholdPx = 6): number | null {
  const bounds = canvas.getBoundingClientRect()
  const pointer = new Vector2((clientX - bounds.left) / bounds.width * 2 - 1, 1 - (clientY - bounds.top) / bounds.height * 2)
  const ray = new Raycaster()
  const maxDistance = camera.far
  ray.params.Points.threshold = 2 * Math.tan(camera.fov * Math.PI / 360) * maxDistance * thresholdPx / bounds.height
  ray.setFromCamera(pointer, camera)
  const hits = ray.intersectObject(points)
  let best: number | null = null, nearest = thresholdPx
  const projected = new Vector3()
  for (const hit of hits) {
    if (hit.index === undefined) continue
    projected.fromBufferAttribute(points.geometry.attributes.position, hit.index).applyMatrix4(points.matrixWorld).project(camera)
    if (projected.z < -1 || projected.z > 1) continue
    const delta = Math.hypot((projected.x - pointer.x) * bounds.width / 2, (projected.y - pointer.y) * bounds.height / 2)
    if (delta <= nearest) { nearest = delta; best = hit.index }
  }
  return best
}
export function pickObject(objects: Object3D[], camera: PerspectiveCamera, canvas: HTMLCanvasElement,
  clientX: number, clientY: number): Object3D | null {
  const bounds = canvas.getBoundingClientRect(), ray = new Raycaster()
  ray.setFromCamera(new Vector2((clientX - bounds.left) / bounds.width * 2 - 1, 1 - (clientY - bounds.top) / bounds.height * 2), camera)
  return ray.intersectObjects(objects, false)[0]?.object ?? null
}

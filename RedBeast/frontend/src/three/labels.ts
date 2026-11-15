import { Vector3 } from 'three'
import type { Camera } from 'three'
export interface LabelSpec {
  id: string
  text: string
  position: () => Vector3
  priority?: number
  kind?: 'measured' | 'computed' | 'representative' | 'here'
  /** Which side of the point the text sits on (default: right). */
  side?: 'left'
}
interface Label extends LabelSpec { element: HTMLSpanElement; plate: HTMLElement }
export class Labels {
  private items = new Map<string, Label>()
  private vector = new Vector3()
  private host: HTMLElement
  constructor(host: HTMLElement) { this.host = host }
  set(specs: LabelSpec[]): void {
    const ids = new Set(specs.map((spec) => spec.id))
    for (const [id, old] of this.items) if (!ids.has(id)) { old.element.remove(); this.items.delete(id) }
    for (const spec of specs) {
      let item = this.items.get(spec.id)
      if (!item) {
        // dot on the object, a short curved leader, then the text on a plate: no label floats unattached
        const element = document.createElement('span')
        element.className = 'sky-label'
        element.innerHTML = '<i class="sky-dot"></i><svg class="sky-lead" viewBox="0 0 30 24" aria-hidden="true"><path d="M1 23C5 9 13 2 29 1"/></svg><b class="sky-plate"></b>'
        this.host.appendChild(element)
        item = { ...spec, element, plate: element.lastElementChild as HTMLElement }
        this.items.set(spec.id, item)
      }
      Object.assign(item, spec)
      item.plate.textContent = spec.text
      item.element.dataset.kind = spec.kind ?? 'measured'
    }
  }
  render(camera: Camera, width: number, height: number): void {
    // Labels live in the host's own layout pixels. The renderer is sized from the on-screen box, which differs
    // whenever an ancestor is CSS-scaled (the V4 stage scales with the window), so measure the host itself.
    width = this.host.clientWidth || width; height = this.host.clientHeight || height
    // a shell can reserve a band on the right for its own interface (--label-reserve-right on the host)
    const style = getComputedStyle(this.host)
    const usable = width - (parseFloat(style.getPropertyValue('--label-reserve-right')) || 0), start = parseFloat(style.getPropertyValue('--label-reserve-left')) || 0
    const occupied: { x: number; y: number; w: number; h: number }[] = []
    for (const item of [...this.items.values()].sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0))) {
      const p = this.vector.copy(item.position()).project(camera)
      const px = (p.x + 1) * width / 2, py = (1 - p.y) * height / 2
      const w = item.plate.offsetWidth || item.text.length * 7.5 + 18, h = item.plate.offsetHeight || 24
      // the plate sits up and to one side of its point; it changes side rather than leave the canvas
      const left = item.side === 'left' ? px - 32 - w >= start : px + 32 + w > usable
      const x = left ? px - 32 - w : px + 32, y = py - 24 - h / 2
      const visible = p.z > -1 && p.z < 1 && px >= 0 && px <= width && py >= 0 && py <= height && x >= start && x + w <= usable && y >= 0 && y + h <= height
        && !occupied.some((r) => x < r.x + r.w + 8 && x + w + 8 > r.x && y < r.y + r.h + 5 && y + h + 5 > r.y)
      item.element.hidden = !visible
      if (visible) {
        item.element.style.transform = `translate(${px}px, ${py}px)`
        item.element.dataset.side = left ? 'left' : 'right'
        occupied.push({ x, y, w, h })
      }
    }
  }
  clear(): void { this.set([]) }
}

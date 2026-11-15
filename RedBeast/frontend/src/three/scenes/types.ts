import type { Engine } from '../engine'
import type { Controls } from '../controls'
import type { SceneData, SceneState } from '../types'
export interface SkyScene {
  controls: Controls | null
  mount(engine: Engine): void
  setData(data: SceneData): void
  update(state: SceneState, changed?: Set<keyof SceneState>): void
  activate(active: boolean): void
  summary(lang: 'tr' | 'en'): string
  faceOn?(): void
  focusTarget?(): void
  unmount(): void
}

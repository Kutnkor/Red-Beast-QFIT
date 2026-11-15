// Session-level caches for small, rarely changing lists, and the cursor read-out store.

import { useSyncExternalStore } from 'react'
import { api } from './api'
import { parseTutorials } from './tutorials'
import type { Health, Target, Tutorial } from './types'
import type { Sky } from './wcs'

function memo<T>(load: () => Promise<T>): { get: () => Promise<T>; clear: () => void } {
  let p: Promise<T> | null = null
  return {
    get: () => {
      if (!p) {
        p = load().catch((err: unknown) => {
          p = null // do not cache failures
          throw err
        })
      }
      return p
    },
    clear: () => {
      p = null
    },
  }
}

const targets = memo<Target[]>(async () => {
  const res = await api.targets()
  return Array.isArray(res.targets) ? res.targets : []
})
const tutorials = memo<Tutorial[]>(async () => parseTutorials(await api.tutorials()))
const health = memo<Health>(() => api.health())

export const getTargets = targets.get
export const getTutorials = tutorials.get
export const getHealth = health.get

export function clearCaches(): void {
  targets.clear()
  tutorials.clear()
  health.clear()
}

// ---- cursor read-out: updated on every pointer move, so it bypasses React state of the viewer
let cursor: Sky | null = null
const subs = new Set<() => void>()

export function setCursor(sky: Sky | null): void {
  if (cursor === sky) return
  cursor = sky
  subs.forEach((s) => s())
}

export function useCursor(): Sky | null {
  return useSyncExternalStore(
    (cb) => {
      subs.add(cb)
      return () => subs.delete(cb)
    },
    () => cursor,
    () => null,
  )
}

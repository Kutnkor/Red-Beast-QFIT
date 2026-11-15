import { useSyncExternalStore } from 'react'
import type { Lang } from './types'
import { suggestedTrack, evolutionTrack } from '../three/science/evolution'

export type AppMode = 'star' | 'neighbors' | 'observations'
export type DrawerTab = 'frame' | 'layers' | 'marks' | 'curve' | 'wave' | 'task' | 'assistant'
export interface AppState {
  lang: Lang
  mode: AppMode
  stageView: 'frames' | 'timestack'
  targetId: string | null
  year: number
  playing: boolean
  speedYearsPerSec: 1 | 5 | 20
  stellarMode: 'surface' | 'evolution' | 'education'
  reducedMotion: boolean
  sceneFraming: 'detail' | 'context'
  surfacePlaying: boolean
  evolutionTrack: string
  evolutionProgress: number
  evolutionPlaying: boolean
  layers: { environment: boolean; trail: boolean; grid: boolean; sky: boolean; gaia: boolean; allwise: boolean; predicted: boolean }
  sequenceId: string | null
  frameIndex: number
  refIndex: number
  viewMode: 'single' | 'side' | 'diff' | 'stack' | 'trackstack'
  drawer: { open: boolean; tab: DrawerTab }
  quality: 'high' | 'medium' | 'low'
  /** Sky view scale: the whole Milky Way (illustration) or the measured stars around the Sun. */
  skyScale: 'galaxy' | 'local'
}

export const DEFAULT_STATE: AppState = {
  lang: 'en', mode: 'observations', stageView: 'frames', targetId: 'barnard', year: 2026,
  playing: false, speedYearsPerSec: 5,
  stellarMode: 'surface', sceneFraming: 'detail', surfacePlaying: true, reducedMotion: false,
  evolutionTrack: 'bhac-0.15', evolutionProgress: 0, evolutionPlaying: false,
  layers: { environment: true, trail: true, grid: false, sky: true, gaia: false, allwise: false, predicted: true },
  sequenceId: null, frameIndex: 0, refIndex: 0, viewMode: 'single',
  drawer: { open: false, tab: 'frame' }, quality: 'high', skyScale: 'galaxy',
}

export function stateFromQuery(search: string): Partial<AppState> {
  const q = new URLSearchParams(search)
  const state: Partial<AppState> = {}
  if (['star', 'neighbors', 'observations'].includes(q.get('mode') ?? '')) state.mode = q.get('mode') as AppMode
  if (q.get('lang') === 'en' || q.get('lang') === 'tr') state.lang = q.get('lang') as Lang
  if (q.get('target')) state.targetId = q.get('target')
  if (q.has('year') && Number.isFinite(Number(q.get('year')))) state.year = Math.min(2100, Math.max(2000, Number(q.get('year'))))
  if (['high', 'medium', 'low'].includes(q.get('quality') ?? '')) state.quality = q.get('quality') as AppState['quality']
  if (q.get('stage') === 'timestack') state.stageView = 'timestack'
  if (q.get('sky') === 'local') state.skyScale = 'local'
  if (['surface', 'evolution', 'education'].includes(q.get('stellar') ?? '')) state.stellarMode = q.get('stellar') as AppState['stellarMode']
  if (q.get('track')) state.evolutionTrack = evolutionTrack(q.get('track')!).id
  else if (state.targetId) state.evolutionTrack = suggestedTrack(state.targetId)
  if (q.has('evolution') && Number.isFinite(Number(q.get('evolution')))) state.evolutionProgress = Math.min(1, Math.max(0, Number(q.get('evolution'))))
  return state
}

let state: AppState = { ...DEFAULT_STATE, ...stateFromQuery(typeof window === 'undefined' ? '' : window.location.search) }
const subscribers = new Set<() => void>()
export function getAppState(): AppState { return state }
export function setAppState(patch: Partial<AppState> | ((previous: AppState) => Partial<AppState>)): void {
  let next = typeof patch === 'function' ? patch(state) : patch
  if(next.mode&&next.mode!==state.mode)next={playing:false,evolutionPlaying:false,drawer:{...state.drawer,open:false},...next}
  if(next.stellarMode&&next.stellarMode!==state.stellarMode)next={playing:false,evolutionPlaying:false,...next}
  if (Object.entries(next).every(([key, value]) => state[key as keyof AppState] === value)) return
  state = { ...state, ...next }
  subscribers.forEach(fn => fn())
}
export function subscribeAppState(fn: () => void): () => void { subscribers.add(fn); return () => subscribers.delete(fn) }
export function useAppState(): AppState { return useSyncExternalStore(subscribeAppState, getAppState, () => DEFAULT_STATE) }

/** Preserve routing, shared observations and custom searches while mirroring the view. */
export function syncViewURL(): void {
  const url = new URL(window.location.href)
  url.searchParams.set('mode', state.mode)
  url.searchParams.set('lang', state.lang)
  url.searchParams.set('year', String(Math.round(state.year * 100) / 100))
  if (state.targetId) url.searchParams.set('target', state.targetId)
  else url.searchParams.delete('target')
  if (state.stageView === 'timestack') url.searchParams.set('stage', 'timestack')
  else url.searchParams.delete('stage')
  if (state.mode === 'neighbors' && state.skyScale === 'local') url.searchParams.set('sky', 'local')
  else url.searchParams.delete('sky')
  if (state.stellarMode === 'evolution') {
    url.searchParams.set('stellar', 'evolution')
    url.searchParams.set('track', state.evolutionTrack)
    url.searchParams.set('evolution', String(Math.round(state.evolutionProgress * 10000) / 10000))
  } else {
    for (const key of ['stellar', 'track', 'evolution']) url.searchParams.delete(key)
    if (state.stellarMode === 'education') url.searchParams.set('stellar', 'education')
  }
  window.history.replaceState(null, '', url.pathname + url.search)
}

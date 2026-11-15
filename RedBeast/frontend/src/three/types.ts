import type { AppState } from '../lib/store'
import type { Mark, Sequence } from '../lib/types'

/** Catalogue fields are kept in the source's units. pmRa already includes cos(dec). */
export interface MotionStar {
  id: string
  name: string
  ra: number
  dec: number
  epoch: number
  parallax: number
  parallaxError?: number
  pmRa: number
  pmDec: number
  radialVelocity: number
  hasRadialVelocity: boolean
  distancePc: number
  magnitude?: number
  colorIndex?: number
  spectralType?: string
  source?: string
  sourceUrl?: string
  source_url?: string
  teff_k: number | null
  teff_source: string
  subtitleEn?: string
  subtitleTr?: string
}

export interface MotionCatalogue {
  stars: MotionStar[]
  targets: MotionStar[]
  reference?: Record<string, unknown>
  provenance?: Record<string, unknown>
  catalogue?: string
}

/** Prefer the named target when it duplicates a Gaia row at the same reference position. */
export function uniqueCatalogueStars(catalogue: MotionCatalogue | null): MotionStar[] {
  const ids = new Set<string>(), coordinates = new Set<string>()
  return [...(catalogue?.targets ?? []), ...(catalogue?.stars ?? [])].filter(star => {
    const key = `${star.ra}:${star.dec}:${star.epoch}`
    if (ids.has(star.id) || coordinates.has(key)) return false
    ids.add(star.id); coordinates.add(key); return true
  })
}

export interface TrackPoint {
  index: number
  mjd?: number
  date?: string
  predicted: { ra: number; dec: number; x?: number; y?: number } | null
  measured: { ra: number; dec: number; err_arcsec?: number | null; x?: number; y?: number } | null
  reason?: string | null
  measured_reason?: string | null
}
export interface SequenceTrack {
  sequence_id?: string
  target_id?: string | null
  source?: 'precomputed' | 'predicted_only' | 'none'
  status: string | Record<string, unknown>
  frames: TrackPoint[]
  motion?: Record<string, unknown> | null
  change_scientifically_confirmed?: false
}

export interface SceneData {
  catalogue: MotionCatalogue | null
  sequence: Sequence | null
  track: SequenceTrack | null
  marks?: Mark[]
  models?: ModelCatalogue | null
  onSelectTarget?: (id: string) => void
  onSelectFrame?: (index: number) => void
}

export interface ModelParameter {
  value: number | string | null
  unit?: string
  classification: 'measured' | 'computed' | 'representative' | 'assumed' | 'unknown'
  source_ids?: string[]
  note?: string
  note_tr?: string
  uncertainty?: number
  range?: [number, number]
  method?: string
}
export interface ModelComponent {
  id?: string
  name: string
  parameters?: Record<string, ModelParameter>
  radius_solar?: number | null
  teff_k?: number | null
}
export interface ModelPhenomenon {
  id: string
  enabled: boolean
  classification: string
  source_ids?: string[]
  note?: string
  note_tr?: string
}
export interface StellarProfile {
  target_id: string
  type: string
  stellar_class?: 'M_dwarf' | 'T_dwarf' | 'Y_dwarf' | 'T_Tauri' | 'Mira'
  parameters: Record<string, ModelParameter>
  components?: ModelComponent[]
  phenomena: ModelPhenomenon[]
  rendering?: Record<string, unknown>
  sources?: { id: string; title: string; url: string; bibcode?: string }[]
  caveats?: string[]
  caveats_tr?: string[]
}
export interface ModelCatalogue { schema_version: number; profiles: StellarProfile[] }

export type SceneState = AppState
export type Vec3 = [number, number, number]

export function selectedStar(data: SceneData, state: SceneState): MotionStar | null {
  return data.catalogue?.targets.find((star) => star.id === state.targetId)
    ?? data.catalogue?.stars.find((star) => star.id === state.targetId) ?? null
}

/** Constants arrive with a citation in /api/motion; no silent astronomical fallback. */
export function referenceNumber(catalogue: MotionCatalogue | null, keys: string[]): number | null {
  for (const key of keys) {
    const entry = catalogue?.reference?.[key]
    if (typeof entry === 'number') return entry
    if (entry && typeof entry === 'object') {
      const value = (entry as Record<string, unknown>).value
      if (typeof value === 'number') return value
    }
  }
  return null
}

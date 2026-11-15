import type { AppState } from './store'
import type { Mark, Sequence } from './types'
import type { MotionStar } from '../three/types'
import { distanceLy } from '../three/science/astrometry'

type Epistemic = 'measured' | 'computed' | 'representative' | 'assumed'
export interface ContextValue { value: number | string | null; unit: string; status: Epistemic; source: string }
export interface LoadedData { target?: MotionStar | null; sequence?: Sequence | null; marks?: Mark[] }
export type AssistantContext = ReturnType<typeof createContext>
const value = (v: ContextValue['value'], unit: string, status: Epistemic, source: string): ContextValue => ({ value: v, unit, status, source: source.slice(0, 160) })
function createContext(state: AppState, data: LoadedData) {
  const t = data.target, s = data.sequence, f = s?.frames[state.frameIndex]
  return {
    mode: state.mode, stage_view: state.stageView, year: state.year, ui_language: state.lang,
    target: t ? { id: t.id, name: t.name.slice(0, 100), coordinates: { ra: t.ra, dec: t.dec, epoch: t.epoch, frame: 'ICRS' }, spectral_type: t.spectralType ?? null,
      distance: value(distanceLy(t), 'ly', 'computed', 'Inverse parallax; IAU parsec'),
      parallax: value(t.parallax, 'mas', 'measured', t.source ?? 'catalogue'),
      proper_motion: value(Math.hypot(t.pmRa, t.pmDec), 'mas/yr', 'measured', t.source ?? 'catalogue'),
      radial_velocity: value(t.hasRadialVelocity ? t.radialVelocity : 0, 'km/s', t.hasRadialVelocity ? 'measured' : 'assumed', t.hasRadialVelocity ? t.source ?? 'catalogue' : 'Missing radial velocity; zero used by linear model'),
      temperature: value(t.teff_k, 'K', t.teff_source.startsWith('gaia') ? 'measured' : 'computed', t.teff_source),
      surface: value('class-specific 3D surface and environment', '', 'representative', 'Source-cited stellar_profiles.json; illustrative geometry, not an image or MHD simulation') } : null,
    sequence: s ? { id: s.id, n_frames: s.frames.length, wavelength_um: s.meta.wavelength.lam_ref_um,
      date_first: s.frames[0]?.date_avg, date_last: s.frames.at(-1)?.date_avg,
      status: s.status, change_scientifically_confirmed: false } : null,
    current_frame: f ? { obs_id: f.obs_id, utc: f.date_avg, wavelength_um: f.lam_um, bandwidth_um: f.bw_um,
      detector: f.detector, invalid_fraction: f.invalid_frac, comparable_fraction: f.comparable_frac } : null,
    layers: state.layers,
    marks: { count: data.marks?.length ?? 0, classifications: [...new Set((data.marks ?? []).map(m => m.classification))] },
  }
}
/** Deliberately select fields; never serialize drafts, notes, share edit tokens or chat history. */
export function buildAssistantContext(state: AppState, data: LoadedData): AssistantContext {
  const context = createContext(state, data)
  if (new TextEncoder().encode(JSON.stringify(context)).byteLength > 4096) throw new Error('Assistant context exceeds 4 KB')
  return context
}

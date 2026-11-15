// Types for the BlinkSpace HTTP API (mirrors backend/blinkspace/api.py, pipeline.py, analysis.py).

export type Lang = 'tr' | 'en'
export type Bilingual = { tr: string; en: string }

export interface Limits {
  fov_arcmin: [number, number]
  max_frames: number
  default_fov_arcmin: number
  default_frames: number
}

export interface Health {
  status: string
  app: string
  pipeline_version: string
  active_jobs: number
  limits: Limits
  classifications: string[]
}

export interface Target {
  id: string
  name: string
  kind: string
  object_type?: string
  spectral_type?: string | null
  ra_deg: number
  dec_deg: number
  ra_hms: string
  dec_dms: string
  pm_total_masyr?: number | null
  pixels_per_year?: number | null
  search: { ra_deg: number; dec_deg: number; fov_arcmin: number; epoch_jyear?: number; method?: string }
  notes?: Partial<Bilingual>
  preferred_lam_um: number | null
  ready_sequence_id: string | null
}

export interface TargetsResponse {
  source?: { service?: string; url?: string; note?: string }
  generated_at?: string
  targets: Target[]
}

export type JobStatus =
  | 'queued'
  | 'searching'
  | 'downloading'
  | 'preparing'
  | 'done'
  | 'insufficient_data'
  | 'failed'
  | 'cancelled'

export interface WavelengthGroup {
  lam_ref_um: number
  bw_ref_um: number
  tol?: number
  n_frames: number
  n_visits: number
  mjd_first?: number
  mjd_last?: number
  span_days: number
  detectors?: number[]
}

export interface JobDetail {
  n_frames?: number
  n_done?: number
  reason?: string | null
  groups?: WavelengthGroup[]
  from_cache?: boolean
  reused?: boolean
  message?: string
  lam_ref_um?: number
  [key: string]: unknown
}

export interface Job {
  id: string
  status: JobStatus
  stage: string | null
  progress: number
  detail: JobDetail | null
  error: string | null
  sequence_id: string | null
  cancel_requested?: boolean | number
  params?: SequenceParams
  merged?: boolean
  /** Unfinished jobs ahead of this one, while it is queued. */
  ahead?: number
}

export interface ParsedPosition {
  ra_deg: number
  dec_deg: number
  frame: string
  ra_hms: string
  dec_dms: string
  notes: string[]
}

export interface SearchResponse {
  job: Job
  position: ParsedPosition
}

export interface SearchRequest {
  target_id?: string
  ra?: string | number
  dec?: string | number
  ra_unit?: 'auto' | 'deg' | 'hour'
  fov_arcmin?: number
  lam_um?: number
  max_frames?: number
  date_from?: string
  date_to?: string
}

export interface Grid {
  projection: string
  crval: [number, number]
  crpix: [number, number]
  cdelt: [number, number]
  nx: number
  ny: number
  pixscale_arcsec: number
  orientation?: string
}

export interface SequenceParams {
  ra_deg: number
  dec_deg: number
  fov_arcmin: number
  lam_um: number | null
  tol: number
  max_frames: number
  mjd_min: number | null
  mjd_max: number | null
  target_id: string | null
}

export interface FrameQuality {
  n_pixels?: number
  frac_invalid?: number
  frac_suspect?: number
  flags_present?: Record<string, number>
  l1_dqa?: string
  l2_dqa?: string
  target?: {
    in_cutout?: boolean
    edge_px?: number
    flags?: Record<string, number>
    info_flags?: Record<string, number>
    n_invalid?: number
    saturated?: boolean
  }
}

export interface Frame {
  index: number
  obs_id: string
  detector: number
  release: string
  l2_tag: string
  pipeline_version: string
  mjd_avg: number
  date_avg: string
  exposure_s?: number
  lam_um: number
  bw_um: number
  dlam_over_bw: number
  source_url: string
  archive_file_url: string
  raw_sha256: string
  quality?: FrameQuality
  background?: { value_mjy_sr?: number; sigma_mjy_sr?: number; method?: string }
  invalid_frac: number
  suspect_frac: number
  comparable_frac: number
  psf_fwhm_arcsec?: number | null
  target_predicted?: { ra: number; dec: number; method: string } | null
  image_url: string
  mask_url: string
}

export interface RejectedFrame {
  obs_id: string
  detector: number
  reason: string
  error?: string
}

export interface Alignment {
  status: string
  reason?: string
  catalog?: string
  method?: string
  n_measurements?: number
  n_bright?: number
  rms_arcsec?: number
  median_de_arcsec?: number
  median_dn_arcsec?: number
  per_frame?: { index: number; n_stars: number; rms_arcsec: number | null }[]
}

export interface SequenceMeta {
  pipeline_version: string
  center: { ra_deg: number; dec_deg: number; frame: string }
  grid: Grid
  wavelength: {
    lam_ref_um: number
    bw_ref_um: number
    tol: number
    mode: string
    groups: WavelengthGroup[]
  }
  display?: { vmin?: number; vmax?: number; stretch?: string; unit?: string; background_subtracted?: boolean }
  archive?: { service?: string; tap_url?: string; adql?: string; n_rows?: number; from_cache?: boolean }
  selection?: {
    n_observations?: number
    n_candidates?: number
    n_selected?: number
    n_prepared?: number
    n_rejected_edge?: number
    rejected_after_download?: RejectedFrame[]
  }
  alignment?: Alignment
  warnings: string[]
  n_frames: number
  n_visits: number
  span_days: number
  target_id?: string | null
  data_fingerprint?: string
}

export interface Sequence {
  id: string
  status: string
  params: SequenceParams
  meta: SequenceMeta
  frames: Frame[]
  created_at?: number
}

export interface DiffResult {
  a: number
  b: number
  definition?: string
  dt_days: number
  lam_a_um: number
  lam_b_um: number
  sigma_mjy_sr: number
  display_scale_mjy_sr: number
  valid_frac: number
  caveats: string[]
  image_url: string
}

export interface StackResult {
  n_frames: number
  min_frames_per_pixel?: number
  method?: string
  valid_frac: number
  max_dlam_over_bw?: number
  target_motion_px?: number | null
  span_days: number
  caveats: string[]
  image_url: string
}

export interface OverlaySource {
  id: string
  ra: number
  dec: number
  mag: number | null
  pm_masyr?: number | null
  per_frame?: [number, number][]
}

export interface Overlay {
  catalog: string
  type: string
  band: string
  catalog_epoch: number
  shown_epoch: number
  resolution_note: string
  propagation: string
  n: number
  sources: OverlaySource[]
}

export interface Candidate {
  classification: Classification
  x: number
  y: number
  snr: number
  frac_change: number | null
  explanation: string
  ra: number
  dec: number
  ra_from?: number
  dec_from?: number
  shift_px?: number
}

export interface CandidatesResult {
  candidates: Candidate[]
  n_raw: number
  n_dropped_low_fraction: number
  a: number
  b: number
  sigma_mjy_sr: number
  status: string
  method?: string
  caveats: string[]
}

export interface LightPoint {
  index: number
  mjd: number
  date: string
  obs_id: string
  valid: boolean
  reason?: string | null
  flux_mjy: number | null
  err_mjy: number | null
  saturated?: boolean
  reliable?: boolean
  quantitative_ok?: boolean
  dlam_over_bw?: number | null
  lam_um?: number | null
}

export interface LightCurve {
  position_mode: string
  lam_ref_um: number | null
  bw_ref_um: number | null
  quantitative_tolerance: number
  unit: string
  points: LightPoint[]
  caveats: string[]
}

export interface Provenance {
  sequence_id: string
  pipeline_version: string
  archive: SequenceMeta['archive']
  selection: SequenceMeta['selection']
  alignment?: Alignment
  data_fingerprint?: string
  citation: string
  frames: {
    index: number
    obs_id: string
    detector: number
    date_avg: string
    lam_um: number
    source_url: string
    archive_file_url: string
    raw_sha256: string
    release: string
    l2_tag: string
  }[]
}

export type Classification = 'possible_motion' | 'possible_brightness_change' | 'possible_artifact' | 'unsure'
export const CLASSIFICATIONS: Classification[] = [
  'possible_motion',
  'possible_brightness_change',
  'possible_artifact',
  'unsure',
]

export interface Mark {
  id: string
  kind: 'point' | 'region'
  classification: Classification
  ra_deg: number
  dec_deg: number
  radius_arcsec?: number | null
  frame_index: number
  note: string
  track_id?: string | null
  // filled in by the server on saved observations
  date?: string
  obs_id?: string
}

export type ViewMode = 'single' | 'side' | 'diff' | 'stack' | 'trackstack'

export interface Layers {
  mask: boolean
  gaia: boolean
  allwise: boolean
  predicted: boolean
  candidates: boolean
  marks: boolean
}

/** Small JSON stored with an observation so a shared link reopens the same view. */
export interface SavedView {
  z?: number
  ra?: number
  dec?: number
  f?: number
  r?: number
  m?: ViewMode
  l?: string[]
}

export interface Observation {
  id: string
  sequence_id: string
  title: string
  note: string
  marks: Mark[]
  view: SavedView
  app_version: string
  created_at: number
  updated_at: number
  status: string
  sequence: Sequence
}

export interface ObservationCreated {
  observation: Observation
  edit_token: string
  share_path: string
}

export interface TutorialStep {
  id: string
  text: Bilingual
  event: 'sequence_opened' | 'frame_changed' | 'mark_added' | 'observation_shared'
}

export interface Tutorial {
  id: string
  title: Bilingual
  summary: Bilingual
  kind: 'guided' | 'quiz'
  target_id: string
  synthetic: boolean
  steps?: TutorialStep[]
  question?: Bilingual
  options?: { id: string; text: Bilingual }[]
  answer_id?: string
  explanation?: Bilingual
  view?: { mode?: ViewMode; frame_a?: number; frame_b?: number; layers?: string[] }
  sources?: { label: string; url: string }[]
  frames_used?: string[]
}

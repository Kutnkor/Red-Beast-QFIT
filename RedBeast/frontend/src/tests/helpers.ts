// Test helpers: a scripted fetch and realistic fixtures modelled on the live Barnard's Star sequence.

import { setFetch } from '../lib/api'
import type { Frame, Job, JobStatus, Sequence, Target } from '../lib/types'

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export interface Call {
  method: string
  url: string
  body: unknown
  headers: Record<string, string>
}

type Handler = (call: Call) => Response | Promise<Response> | undefined

/** Install a fetch mock. Handlers are tried in order; the first non-undefined result wins. */
export function mockFetch(...handlers: Handler[]): Call[] {
  const calls: Call[] = []
  setFetch(async (url, init) => {
    const headers: Record<string, string> = {}
    const h = init?.headers
    if (h && typeof h === 'object' && !Array.isArray(h) && !(h instanceof Headers)) Object.assign(headers, h)
    const call: Call = {
      method: (init?.method ?? 'GET').toUpperCase(),
      url,
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : null,
      headers,
    }
    calls.push(call)
    for (const handler of handlers) {
      const res = await handler(call)
      if (res) return res
    }
    return jsonResponse({ error: { code: 'not_found', message: `unmocked ${call.method} ${url}` } }, 404)
  })
  return calls
}

export function route(method: string, url: string | RegExp, respond: (call: Call) => Response | Promise<Response>): Handler {
  return (call) => {
    if (call.method !== method) return undefined
    const path = call.url
    if (typeof url === 'string' ? path !== url : !url.test(path)) return undefined
    return respond(call)
  }
}

export function job(status: JobStatus, extra: Partial<Job> = {}): Job {
  return {
    id: 'job0000001',
    status,
    stage: status,
    progress: 0,
    detail: null,
    error: null,
    sequence_id: null,
    cancel_requested: 0,
    ...extra,
  }
}

export const POSITION = {
  ra_deg: 269.446269,
  dec_deg: 4.768204,
  frame: 'ICRS',
  ra_hms: '17h57m47.10s',
  dec_dms: '+04d46m05.5s',
  notes: ['ra_assumed_degrees'],
}

const DATES: [string, number][] = [
  ['2025-08-25T17:09:20Z', 60912.714812798],
  ['2025-08-30T16:11:26Z', 60917.674605726],
  ['2026-03-15T00:51:21Z', 61114.035654152],
  ['2026-08-18T20:49:36Z', 61270.86778171],
  ['2026-08-21T18:56:00Z', 61273.788888342],
  ['2026-09-22T15:05:19Z', 61305.628686803],
]

export function frame(i: number): Frame {
  const nn = String(i).padStart(2, '0')
  return {
    index: i,
    obs_id: `2025W35_1A_014${i}_1`,
    detector: 2,
    release: 'qr2',
    l2_tag: 'l2b-v20-2025-269',
    pipeline_version: '6.4+psffix1',
    mjd_avg: DATES[i][1],
    date_avg: DATES[i][0],
    exposure_s: 113.58,
    lam_um: 1.51 + i * 0.001,
    bw_um: 0.0371,
    dlam_over_bw: 0.136,
    source_url: `https://irsa.ipac.caltech.edu/ibe/data/spherex/f${i}.fits?center=269.446269,4.768204&size=0.157`,
    archive_file_url: `https://irsa.ipac.caltech.edu/ibe/data/spherex/f${i}.fits`,
    raw_sha256: 'bbfe9fe867b2a6ac2a144ca9703d9cdb8d3332830e5db68099146feb23fdd147',
    quality: { l1_dqa: 'Pass', l2_dqa: 'Pass', target: { saturated: true, flags: { OVERFLOW: 5 } } },
    background: { value_mjy_sr: 0.36873, sigma_mjy_sr: 0.08864 },
    invalid_frac: 0.0256,
    suspect_frac: 0.0029,
    comparable_frac: 0.9744,
    psf_fwhm_arcsec: 5.15,
    target_predicted: { ra: 269.446347 - i * 5e-5, dec: 4.767193 + i * 6e-4, method: 'proper_motion_only' },
    image_url: `/api/sequences/vwu8zey93r/files/frame_${nn}.png`,
    mask_url: `/api/sequences/vwu8zey93r/files/frame_${nn}_mask.png`,
  }
}

export function sequence(nFrames = 6, warnings: string[] = ['center_saturated']): Sequence {
  const s = 6.15 / 3600
  return {
    id: 'vwu8zey93r',
    status: nFrames > 1 ? 'ready' : 'insufficient',
    params: { ra_deg: 269.44627, dec_deg: 4.7682, fov_arcmin: 6, lam_um: null, tol: 0.5, max_frames: 8, mjd_min: null, mjd_max: null, target_id: 'barnard' },
    meta: {
      pipeline_version: '1.0.0',
      center: { ra_deg: 269.446269, dec_deg: 4.768204, frame: 'ICRS' },
      grid: { projection: 'TAN', crval: [269.446269, 4.768204], crpix: [30, 30], cdelt: [-s, s], nx: 59, ny: 59, pixscale_arcsec: 6.15 },
      wavelength: {
        lam_ref_um: 1.51174,
        bw_ref_um: 0.03711,
        tol: 0.5,
        mode: 'auto',
        groups: [
          { lam_ref_um: 1.51174, bw_ref_um: 0.03711, n_frames: 6, n_visits: 6, span_days: 392.914 },
          { lam_ref_um: 4.29096, bw_ref_um: 0.03739, n_frames: 6, n_visits: 6, span_days: 392.914 },
        ],
      },
      display: { stretch: 'asinh', unit: 'MJy/sr' },
      archive: { service: 'IRSA TAP', tap_url: 'https://irsa.ipac.caltech.edu/TAP', adql: 'SELECT 1', n_rows: 359 },
      selection: {
        n_observations: 359,
        n_candidates: 341,
        n_selected: nFrames,
        n_prepared: nFrames,
        rejected_after_download: warnings.includes('partial_data') ? [{ obs_id: '2026W01_1A_0001_1', detector: 2, reason: 'low_coverage' }] : [],
      },
      alignment: { status: 'ok', rms_arcsec: 0.39, n_measurements: 21, method: 'centroid', catalog: 'Gaia DR3' },
      warnings,
      n_frames: nFrames,
      n_visits: nFrames,
      span_days: nFrames > 1 ? 392.914 : 0,
      target_id: 'barnard',
    },
    frames: Array.from({ length: nFrames }, (_, i) => frame(i)),
  }
}

export function target(id: string, name: string, ready: string | null, kind = 'motion'): Target {
  return {
    id,
    name,
    kind,
    spectral_type: 'M4V',
    ra_deg: 269.452,
    dec_deg: 4.693,
    ra_hms: '17h57m48.50s',
    dec_dms: '+04d41m36.1s',
    pixels_per_year: 1.69,
    search: { ra_deg: 269.446269, dec_deg: 4.768204, fov_arcmin: 6 },
    notes: { tr: `${name} Türkçe not`, en: `${name} English note` },
    preferred_lam_um: null,
    ready_sequence_id: ready,
  }
}

export const TARGETS: Target[] = [
  target('barnard', "Barnard's Star", 'vwu8zey93r'),
  target('eps-indi-b', 'Epsilon Indi B', 't5jmtk65x6'),
  target('wise-0855', 'WISE 0855−0714', 'ku5e9r46ba'),
  target('rw-aur', 'RW Aurigae', 'se7t5vkn98', 'variability'),
  target('r-dra', 'R Draconis', null, 'variability'),
]

export const HEALTH = {
  status: 'ok',
  app: 'BlinkSpace',
  pipeline_version: '1.0.0',
  active_jobs: 0,
  limits: { fov_arcmin: [2, 30], max_frames: 16, default_fov_arcmin: 6, default_frames: 8 },
  classifications: ['possible_motion', 'possible_brightness_change', 'possible_artifact', 'unsure'],
}

/** Let pending promise callbacks run. */
export async function flush(times = 5): Promise<void> {
  for (let i = 0; i < times; i++) await Promise.resolve()
}

import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../i18n'
import { ApiError, request } from '../lib/api'
import { fmtDateUTC, fmtDay, fmtNum } from '../lib/format'
import type { Job, Sequence } from '../lib/types'

/** One point of an on-the-fly spectrum: its own time, wavelength, quality and uncertainty. */
export interface SpectrumPoint {
  obs_id: string
  detector: number
  release?: string
  date: string
  mjd: number
  valid: boolean
  reliable?: boolean
  saturated?: boolean
  reason?: string | null
  lam_um?: number | null
  bw_um?: number | null
  flux_mjy?: number | null
  err_mjy?: number | null
  flags?: Record<string, number>
}

export interface Spectrum {
  id: string
  date_window: [string, string]
  span_days: number
  n_points: number
  n_reliable: number
  n_exposures_in_window: number
  position_mode: string
  simultaneous: boolean
  unit: string
  points: SpectrumPoint[]
}

export type PointState = 'ok' | 'unreliable' | 'none'

export function pointState(p: SpectrumPoint): PointState {
  if (!p.valid || p.flux_mjy === null || p.flux_mjy === undefined) return 'none'
  return p.reliable ? 'ok' : 'unreliable'
}

const TERMINAL = ['done', 'insufficient_data', 'failed', 'cancelled']
const W = 320
const H = 190
const L = 44
const R = 8
const T = 20
const AXIS_Y = 150
const LANE_Y = 172

/** Wavelength-vs-flux plot. Invalid measurements sit in their own "no measurement" lane, never at zero. */
export function SpectrumChart({ spectrum }: { spectrum: Spectrum }) {
  const { t } = useI18n()
  const pts = spectrum.points.filter((p) => typeof p.lam_um === 'number')
  const measured = pts.filter((p) => pointState(p) !== 'none')
  const lams = pts.map((p) => p.lam_um as number)
  const lo = Math.min(...lams)
  const hi = Math.max(...lams)
  const pad = Math.max((hi - lo) * 0.04, 0.01)
  const x = (lam: number) => L + ((lam - (lo - pad)) / (hi - lo + 2 * pad)) * (W - L - R)
  const top = Math.max(...measured.map((p) => (p.flux_mjy as number) + (p.err_mjy ?? 0)), 0)
  const ymax = top > 0 ? top * 1.08 : 1
  const y = (f: number) => AXIS_Y - (Math.max(f, 0) / ymax) * (AXIS_Y - T)
  const ticks = [0, 0.5, 1].map((k) => k * ymax)
  const xticks = [lo, (lo + hi) / 2, hi]

  return (
    <figure className="spec-figure">
      <svg className="lc-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('spec.chartLabel', { n: pts.length })}>
        {ticks.map((v) => (
          <g key={v}>
            <line className="lc-grid" x1={L} x2={W - R} y1={y(v)} y2={y(v)} />
            <text className="lc-axis" x={L - 5} y={y(v) + 3} textAnchor="end">
              {fmtNum(v, v >= 100 ? 0 : v >= 10 ? 1 : 2)}
            </text>
          </g>
        ))}
        {xticks.map((v, i) => (
          <text key={i} className="lc-axis" x={x(v)} y={AXIS_Y + 12} textAnchor={i === 0 ? 'start' : i === 2 ? 'end' : 'middle'}>
            {v.toFixed(2)}
          </text>
        ))}
        <text className="lc-axis" x={W - R} y={H - 2} textAnchor="end">
          µm
        </text>
        <text className="lc-axis" x={2} y={9}>
          mJy
        </text>
        <text className="lc-axis" x={2} y={LANE_Y + 3}>
          ×
        </text>
        {pts.map((p) => {
          const s = pointState(p)
          const px = x(p.lam_um as number)
          const title = `${(p.lam_um as number).toFixed(3)} µm · ${fmtDateUTC(p.date)} · ${
            s === 'none' ? t('spec.none') : `${fmtNum(p.flux_mjy, 2)} ± ${fmtNum(p.err_mjy, 2)} mJy${s === 'unreliable' ? ` · ${t('spec.unreliable')}` : ''}`
          }`
          if (s === 'none') {
            return (
              <g key={p.obs_id + p.detector} className="lc-pt lc-none" data-state="none">
                <title>{title}</title>
                <path d={`M${px - 3} ${LANE_Y - 3}l6 6M${px + 3} ${LANE_Y - 3}l-6 6`} />
              </g>
            )
          }
          const f = p.flux_mjy as number
          const e = p.err_mjy ?? 0
          const cy = y(f)
          return (
            <g key={p.obs_id + p.detector} className={`lc-pt lc-${s}`} data-state={s}>
              <title>{title}</title>
              {e > 0 && <path className="lc-err" d={`M${px} ${y(f - e)}V${y(f + e)}`} />}
              {s === 'unreliable' ? (
                <path className="lc-mark" d={`M${px} ${cy - 4}L${px + 4} ${cy}L${px} ${cy + 4}L${px - 4} ${cy}Z`} />
              ) : (
                <circle className="lc-mark" cx={px} cy={cy} r={3} />
              )}
            </g>
          )
        })}
      </svg>
      <figcaption className="muted small">
        {t('spec.legend')}
      </figcaption>
    </figure>
  )
}

export function SpectrumPanel({ sequence }: { sequence: Sequence }) {
  const { t, tc } = useI18n()
  const meta = sequence.meta
  const frames = sequence.frames
  const [center, setCenter] = useState<string>('')
  const [windowDays, setWindowDays] = useState('14')
  const [maxPoints, setMaxPoints] = useState('24')
  const [job, setJob] = useState<Job | null>(null)
  const [spectrum, setSpectrum] = useState<Spectrum | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const alive = useRef(true)
  const jobId = useRef<string | null>(null)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const run = async () => {
    setBusy(true)
    setError(null)
    setSpectrum(null)
    setJob(null)
    try {
      const body: Record<string, unknown> = {
        window_days: Math.min(60, Math.max(1, Number(windowDays) || 14)),
        max_points: Math.min(40, Math.max(3, Math.round(Number(maxPoints) || 24))),
      }
      if (center) body.date = center
      if (meta.target_id) body.target_id = meta.target_id
      else {
        body.ra = meta.center.ra_deg
        body.dec = meta.center.dec_deg
        body.ra_unit = 'deg'
      }
      let current = (await request<{ job: Job }>('/api/spectra', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).job
      jobId.current = current.id
      while (alive.current && !TERMINAL.includes(current.status)) {
        setJob(current)
        await new Promise((r) => window.setTimeout(r, 1000))
        current = (await request<{ job: Job }>(`/api/jobs/${encodeURIComponent(current.id)}`)).job
      }
      if (!alive.current) return
      setJob(current)
      const rid = (current as Job & { result_id?: string | null }).result_id
      if ((current.status === 'done' || current.status === 'insufficient_data') && rid) {
        setSpectrum(await request<Spectrum>(`/api/spectra/${encodeURIComponent(rid)}`))
      } else if (current.status === 'insufficient_data') {
        const reason = (current.detail as { reason?: string } | null)?.reason
        setError(reason === 'too_few_exposures_in_window' ? t('spec.tooFew') : tc('insuf', reason ?? 'no_usable_frames'))
      } else if (current.status === 'failed') {
        setError(tc('jobErr', current.error ?? 'internal_error'))
      }
    } catch (err) {
      if (alive.current) setError(err instanceof ApiError ? tc('err', err.code) : t('spec.failed'))
    } finally {
      if (alive.current) setBusy(false)
    }
  }

  const cancel = () => {
    if (jobId.current) void request(`/api/jobs/${encodeURIComponent(jobId.current)}/cancel`, { method: 'POST' }).catch(() => undefined)
  }

  const detail = (job?.detail ?? null) as { n_done?: number; n_frames?: number } | null
  const dates = Array.from(new Set(frames.map((f) => fmtDay(f.date_avg))))

  return (
    <section className="spec" aria-label={t('spec.title')}>
      <h4>{t('spec.title')}</h4>
      <p className="muted small">{t('spec.intro')}</p>
      <p className="muted small">{meta.target_id ? t('spec.posTarget') : t('spec.posCenter')}</p>
      <div className="spec-form">
        <label className="field">
          <span>{t('spec.center')}</span>
          <select value={center} onChange={(e) => setCenter(e.target.value)}>
            <option value="">{t('spec.densest')}</option>
            {dates.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t('spec.window')}</span>
          <input type="number" min={1} max={60} value={windowDays} onChange={(e) => setWindowDays(e.target.value)} />
        </label>
        <label className="field">
          <span>{t('spec.points')}</span>
          <input type="number" min={3} max={40} value={maxPoints} onChange={(e) => setMaxPoints(e.target.value)} />
        </label>
      </div>
      <div className="spec-actions">
        <button type="button" className="btn btn-primary" onClick={() => void run()} disabled={busy}>
          {busy ? t('spec.running') : t('spec.run')}
        </button>
        {busy && (
          <button type="button" className="btn" onClick={cancel}>
            {t('spec.cancel')}
          </button>
        )}
      </div>
      <div aria-live="polite">
        {busy && job && (
          <p className="mono small">
            {tc('stage', job.status)}
            {detail?.n_frames ? ` · ${detail.n_done ?? 0}/${detail.n_frames}` : ''}
          </p>
        )}
        {error && <p className="notice notice-error">{error}</p>}
      </div>
      {spectrum && (
        <>
          <p className="notice notice-info small">
            {t('spec.notSimultaneous', {
              from: fmtDay(spectrum.date_window[0]),
              to: fmtDay(spectrum.date_window[1]),
              days: spectrum.span_days.toFixed(1),
              n: spectrum.n_points,
              ok: spectrum.n_reliable,
            })}
          </p>
          <SpectrumChart spectrum={spectrum} />
          <div className="table-scroll">
            <table className="wave-table">
              <thead>
                <tr>
                  <th scope="col">λ (µm)</th>
                  <th scope="col">{t('spec.col.date')}</th>
                  <th scope="col">{t('spec.col.flux')}</th>
                  <th scope="col">{t('spec.col.state')}</th>
                </tr>
              </thead>
              <tbody>
                {spectrum.points.map((p) => {
                  const s = pointState(p)
                  return (
                    <tr key={p.obs_id + p.detector}>
                      <td className="mono">{typeof p.lam_um === 'number' ? p.lam_um.toFixed(3) : '—'}</td>
                      <td className="mono">{fmtDateUTC(p.date)}</td>
                      <td className="mono">{s === 'none' ? t('spec.none') : `${fmtNum(p.flux_mjy, 2)} ± ${fmtNum(p.err_mjy, 2)}`}</td>
                      <td>{s === 'ok' ? t('spec.ok') : s === 'unreliable' ? t('spec.unreliable') : (p.reason ?? '').replace(/_/g, ' ')}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="muted small">{t('spec.unit')}</p>
        </>
      )}
    </section>
  )
}

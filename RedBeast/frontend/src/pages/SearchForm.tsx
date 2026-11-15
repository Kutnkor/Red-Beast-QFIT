/* eslint-disable react-refresh/only-export-components */
// Coordinate search form. Client-side hints only; the server is the source of truth for validation.

import { useId, useState, type FormEvent } from 'react'
import { useI18n } from '../i18n'
import type { MsgKey } from '../i18n/tr'
import type { Limits, SearchRequest } from '../lib/types'

export const FALLBACK_LIMITS: Limits = { fov_arcmin: [2, 30], max_frames: 16, default_fov_arcmin: 6, default_frames: 8 }

export interface FormValues {
  ra: string
  dec: string
  unit: 'auto' | 'deg' | 'hour'
  fov: string
  frames: string
  dateFrom: string
  dateTo: string
  lam: string
}

export function defaultValues(limits: Limits): FormValues {
  return {
    ra: '',
    dec: '',
    unit: 'auto',
    fov: String(limits.default_fov_arcmin),
    frames: String(limits.default_frames),
    dateFrom: '',
    dateTo: '',
    lam: '',
  }
}

/** Query-string entry: /?ra=..&dec=..&fov=..[&unit=deg|hour][&lam=..][&frames=..] */
export function valuesFromQuery(q: URLSearchParams, limits: Limits): FormValues | null {
  const ra = q.get('ra')
  const dec = q.get('dec')
  if (ra === null || dec === null) return null
  const unit = q.get('unit')
  return {
    ...defaultValues(limits),
    ra,
    dec,
    unit: unit === 'deg' || unit === 'hour' ? unit : 'auto',
    fov: q.get('fov') ?? String(limits.default_fov_arcmin),
    frames: q.get('frames') ?? String(limits.default_frames),
    lam: q.get('lam') ?? '',
  }
}

const SEXAGESIMAL = /[hms:°'"′″d]|\d\s+\d/i

/** Non-binding hint about how the RA text will probably be read. */
export function raHint(value: string, unit: FormValues['unit']): MsgKey | null {
  const v = value.trim()
  if (!v || unit !== 'auto') return null
  if (SEXAGESIMAL.test(v)) return 'form.hint.hourLike'
  if (Number.isFinite(Number(v))) return 'form.hint.degLike'
  return null
}

export function decHint(value: string): MsgKey | null {
  const v = value.trim().replace('−', '-')
  if (!v || SEXAGESIMAL.test(v)) return null
  const n = Number(v)
  if (Number.isFinite(n) && Math.abs(n) > 90) return 'form.hint.decRange'
  return null
}

export interface Built {
  request: SearchRequest | null
  problems: { key: MsgKey; params?: Record<string, number> }[]
}

/** Build the request body. Only obviously impossible input is blocked here. */
export function buildRequest(v: FormValues, limits: Limits): Built {
  const problems: Built['problems'] = []
  if (!v.ra.trim()) problems.push({ key: 'form.hint.raRequired' })
  if (!v.dec.trim()) problems.push({ key: 'form.hint.decRequired' })
  const [fmin, fmax] = limits.fov_arcmin
  const fov = Number(v.fov)
  if (!v.fov.trim() || !Number.isFinite(fov) || fov < fmin || fov > fmax) {
    problems.push({ key: 'form.hint.fovRange', params: { min: fmin, max: fmax } })
  }
  const frames = Number(v.frames)
  if (!v.frames.trim() || !Number.isInteger(frames) || frames < 2 || frames > limits.max_frames) {
    problems.push({ key: 'form.hint.framesRange', params: { max: limits.max_frames } })
  }
  let lam: number | undefined
  if (v.lam.trim()) {
    lam = Number(v.lam.replace(',', '.'))
    if (!Number.isFinite(lam) || lam < 0.7 || lam > 5.1) problems.push({ key: 'form.hint.lamRange' })
  }
  if (v.dateFrom && v.dateTo && v.dateFrom >= v.dateTo) problems.push({ key: 'form.hint.dateOrder' })
  if (problems.length > 0) return { request: null, problems }
  const request: SearchRequest = { ra: v.ra.trim(), dec: v.dec.trim(), ra_unit: v.unit, fov_arcmin: fov, max_frames: frames }
  if (lam !== undefined) request.lam_um = lam
  if (v.dateFrom) request.date_from = v.dateFrom
  if (v.dateTo) request.date_to = v.dateTo
  return { request, problems }
}

export function SearchForm({
  limits,
  initial,
  busy,
  serverError,
  onSubmit,
}: {
  limits: Limits
  initial?: FormValues | null
  busy: boolean
  serverError: string | null
  onSubmit: (request: SearchRequest) => void
}) {
  const { t } = useI18n()
  const id = useId()
  const [v, setV] = useState<FormValues>(() => initial ?? defaultValues(limits))
  const [problems, setProblems] = useState<Built['problems']>([])
  const set = <K extends keyof FormValues>(k: K, value: FormValues[K]) => setV((s) => ({ ...s, [k]: value }))
  const [fmin, fmax] = limits.fov_arcmin
  const raH = raHint(v.ra, v.unit)
  const decH = decHint(v.dec)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const built = buildRequest(v, limits)
    setProblems(built.problems)
    if (built.request) onSubmit(built.request)
  }

  return (
    <form className="search-form" onSubmit={submit} noValidate aria-describedby={`${id}-note`}>
      <div className="form-row form-row-ra">
        <label className="field">
          <span>{t('form.ra')}</span>
          <input
            type="text"
            inputMode="text"
            autoComplete="off"
            spellCheck={false}
            className="mono"
            value={v.ra}
            placeholder={t(`form.raPh.${v.unit}`)}
            onChange={(e) => set('ra', e.target.value)}
            aria-describedby={`${id}-ra-hint`}
            maxLength={64}
          />
        </label>
        <label className="field field-unit">
          <span>{t('form.raUnit')}</span>
          <select value={v.unit} onChange={(e) => set('unit', e.target.value as FormValues['unit'])}>
            <option value="auto">{t('form.unit.auto')}</option>
            <option value="deg">{t('form.unit.deg')}</option>
            <option value="hour">{t('form.unit.hour')}</option>
          </select>
        </label>
      </div>
      <p id={`${id}-ra-hint`} className="hint">
        {raH ? t(raH) : ' '}
      </p>

      <label className="field">
        <span>{t('form.dec')}</span>
        <input
          type="text"
          autoComplete="off"
          spellCheck={false}
          className="mono"
          value={v.dec}
          placeholder={t('form.decPh')}
          onChange={(e) => set('dec', e.target.value)}
          aria-describedby={`${id}-dec-hint`}
          maxLength={64}
        />
      </label>
      <p id={`${id}-dec-hint`} className={decH ? 'hint hint-warn' : 'hint'}>
        {decH ? t(decH) : ' '}
      </p>

      <div className="form-row">
        <label className="field">
          <span>{t('form.fov')}</span>
          <input
            type="number"
            className="mono"
            min={fmin}
            max={fmax}
            step="0.5"
            value={v.fov}
            onChange={(e) => set('fov', e.target.value)}
            aria-describedby={`${id}-fov-hint`}
          />
        </label>
        <label className="field">
          <span>{t('form.frames')}</span>
          <input
            type="number"
            className="mono"
            min={2}
            max={limits.max_frames}
            step={1}
            value={v.frames}
            onChange={(e) => set('frames', e.target.value)}
            aria-describedby={`${id}-frames-hint`}
          />
        </label>
      </div>
      <p className="hint">
        <span id={`${id}-fov-hint`}>{t('form.fovHint', { min: fmin, max: fmax })}</span>{' '}
        <span id={`${id}-frames-hint`} className="sr-only">
          {t('form.framesHint', { max: limits.max_frames })}
        </span>
      </p>

      <details className="advanced">
        <summary>{t('form.advanced')}</summary>
        <div className="form-row">
          <label className="field">
            <span>{t('form.dateFrom')}</span>
            <input type="date" className="mono" value={v.dateFrom} onChange={(e) => set('dateFrom', e.target.value)} />
          </label>
          <label className="field">
            <span>{t('form.dateTo')}</span>
            <input type="date" className="mono" value={v.dateTo} onChange={(e) => set('dateTo', e.target.value)} />
          </label>
        </div>
        <label className="field">
          <span>{t('form.lam')}</span>
          <input
            type="text"
            inputMode="decimal"
            className="mono"
            value={v.lam}
            placeholder={t('form.lamAuto')}
            onChange={(e) => set('lam', e.target.value)}
            aria-describedby={`${id}-lam-hint`}
            maxLength={12}
          />
        </label>
        <p id={`${id}-lam-hint`} className="hint">
          {t('form.lamHint')}
        </p>
      </details>

      <div aria-live="polite">
        {problems.length > 0 && (
          <ul className="notice notice-error plain" role="alert">
            {problems.map((p) => (
              <li key={p.key}>{t(p.key, p.params)}</li>
            ))}
          </ul>
        )}
        {serverError && problems.length === 0 && (
          <p className="notice notice-error" role="alert">
            {serverError}
          </p>
        )}
      </div>

      <button type="submit" className="btn btn-primary btn-wide" disabled={busy}>
        {t('form.submit')}
      </button>
      <p id={`${id}-note`} className="hint">
        {t('form.serverValidates')}
      </p>
    </form>
  )
}

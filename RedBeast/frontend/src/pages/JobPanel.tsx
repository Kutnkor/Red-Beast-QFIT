/* eslint-disable react-refresh/only-export-components */
// Search job: hook (submit + poll + cancel) and the status panel that shows the real server stage.

import { useCallback, useEffect, useReducer, useRef } from 'react'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { describeApiError, describeInsufficient, describeJobError } from '../lib/errors'
import { initialJobState, jobProgress, jobReducer, runJob, type JobAction, type JobState } from '../lib/jobs'
import type { Job, SearchRequest } from '../lib/types'

export function useJob() {
  const [state, dispatch] = useReducer(jobReducer, initialJobState)
  const ctrl = useRef<AbortController | null>(null)
  const jobId = useRef<string | null>(null)

  const start = useCallback((request: SearchRequest) => {
    ctrl.current?.abort()
    const c = new AbortController()
    ctrl.current = c
    jobId.current = null
    void runJob(
      api,
      request,
      (action: JobAction) => {
        if (c.signal.aborted) return
        if (action.type === 'submitted') jobId.current = action.response.job.id
        dispatch(action)
      },
      { signal: c.signal },
    )
  }, [])

  const cancel = useCallback(async () => {
    dispatch({ type: 'cancel_requested' })
    const id = jobId.current
    if (!id) {
      ctrl.current?.abort()
      return
    }
    try {
      const res = await api.cancelJob(id)
      dispatch({ type: 'polled', job: res.job })
    } catch {
      /* the poll loop keeps reporting the real state */
    }
  }, [])

  const reset = useCallback(() => {
    ctrl.current?.abort()
    jobId.current = null
    dispatch({ type: 'reset' })
  }, [])

  useEffect(() => () => ctrl.current?.abort(), [])

  return { state, start, cancel, reset }
}

const STAGES = ['queued', 'searching', 'downloading', 'preparing'] as const

/** Why a job is not moving: its place in the queue, or the archive answering with errors while it is retried. */
function JobWait({ job }: { job: Job }) {
  const { t } = useI18n()
  const wait = job.detail?.archive_wait as { attempt?: number; retry_in_s?: number; budget_s?: number; status?: number | null } | undefined
  if (job.status === 'queued' && job.ahead) return <p className="job-wait" role="status">{t('job.ahead', { n: job.ahead })}</p>
  if (job.status === 'searching' && wait && wait.attempt) return <p className="job-wait" role="status">
    {t(wait.status ? 'job.archiveWait' : 'job.archiveWaitNet', { status: wait.status ?? '', attempt: wait.attempt, retry: wait.retry_in_s ?? 0, budget: wait.budget_s ?? 60 })}</p>
  return null
}

export function JobPanel({
  state,
  targetName,
  onCancel,
  onRetry,
  onReset,
  onOpen,
}: {
  state: JobState
  targetName?: string | null
  onCancel: () => void
  onRetry: (request: SearchRequest) => void
  onReset: () => void
  onOpen: (sequenceId: string) => void
}) {
  const { t, tc, lang } = useI18n()
  if (state.phase === 'idle') return null

  const position = 'position' in state ? state.position : null
  const running = state.phase === 'running' ? state : null
  const stageIndex = running ? STAGES.indexOf(running.job.status as (typeof STAGES)[number]) : -1
  const prog = running ? jobProgress(running.job) : null

  return (
    <section className="card job" aria-label={t('job.title')}>
      <header className="job-head">
        <h2>{t('job.title')}</h2>
        {targetName && <p className="muted">{t('job.forTarget', { name: targetName })}</p>}
      </header>

      {position && (
        <div className="job-position">
          <span className="muted small">{t('job.position')}</span>
          <p className="mono">
            {position.ra_hms} {position.dec_dms}
            <span className="muted">
              {' '}
              · {position.ra_deg.toFixed(5)}° {position.dec_deg >= 0 ? '+' : '−'}
              {Math.abs(position.dec_deg).toFixed(5)}°
            </span>
          </p>
          {position.notes.length > 0 && (
            <ul className="plain small">
              {position.notes.map((n) => (
                <li key={n}>{tc('note', n)}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div aria-live="polite" className="job-live">
        {state.phase === 'submitting' && <p>{t('job.submitting')}</p>}

        {running && prog && (
          <>
            <ol className="stages">
              {STAGES.map((s, i) => (
                <li
                  key={s}
                  className={i < stageIndex ? 'stage stage-done' : i === stageIndex ? 'stage stage-current' : 'stage'}
                  aria-current={i === stageIndex ? 'step' : undefined}
                >
                  {t(`stage.${s}`)}
                </li>
              ))}
            </ol>
            <div
              className="progress"
              role="progressbar"
              aria-label={t('job.progress')}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={prog.percent}
            >
              <span style={{ width: `${prog.percent}%` }} />
            </div>
            <p className="mono small">
              {prog.percent}%
              {prog.nDone !== null && prog.nFrames !== null ? ` · ${t('job.framesDone', { done: prog.nDone, total: prog.nFrames })}` : ''}
            </p>
            <JobWait job={running.job} />
            {running.job.merged && <p className="muted small">{t('job.merged')}</p>}
            <button type="button" className="btn" onClick={onCancel} disabled={running.cancelling}>
              {running.cancelling ? t('job.cancelling') : t('job.cancel')}
            </button>
          </>
        )}

        {state.phase === 'done' && (state.job.detail?.stale && typeof state.job.detail.fetched_at === 'number'
          ? <p className="job-wait" role="status">{t('job.stale', { date: new Date(state.job.detail.fetched_at * 1000).toLocaleString(lang === 'tr' ? 'tr-TR' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' }) })}</p>
          : <p>{t('job.done')}</p>)}

        {state.phase === 'cancelled' && (
          <>
            <p>{t('job.cancelled')}</p>
            <div className="row-actions">
              <button type="button" className="btn btn-primary" onClick={() => onRetry(state.request)}>
                {t('app.retry')}
              </button>
              <button type="button" className="btn" onClick={onReset}>
                {t('job.newSearch')}
              </button>
            </div>
          </>
        )}

        {state.phase === 'failed' && (
          <div role="alert">
            <h3>{t('job.failed')}</h3>
            <p>
              {state.source === 'job' ? describeJobError(lang, state.code) : describeApiError(lang, state.code, state.reason)}{' '}
              <code className="muted small">{state.code}</code>
            </p>
            <div className="row-actions">
              <button type="button" className="btn btn-primary" onClick={() => onRetry(state.request)}>
                {t('app.retry')}
              </button>
              <button type="button" className="btn" onClick={onReset}>
                {t('job.newSearch')}
              </button>
            </div>
          </div>
        )}

        {state.phase === 'insufficient' && (
          <div role="alert">
            <h3>{t('job.insufficient')}</h3>
            <p>
              {describeInsufficient(lang, state.reason)} <code className="muted small">{state.reason}</code>
            </p>
            {state.groups.length > 0 && (
              <>
                <p>{t('job.tryWavelength')}</p>
                <ul className="group-options">
                  {state.groups.slice(0, 12).map((g) => (
                    <li key={g.lam_ref_um}>
                      <button type="button" className="btn btn-small" onClick={() => onRetry({ ...state.request, lam_um: g.lam_ref_um })}>
                        {t('job.groupOption', {
                          lam: g.lam_ref_um.toFixed(3),
                          n: g.n_frames,
                          v: g.n_visits,
                          d: g.span_days.toFixed(0),
                        })}
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <div className="row-actions">
              {state.sequenceId && (
                <button type="button" className="btn btn-primary" onClick={() => onOpen(state.sequenceId as string)}>
                  {t('job.openSingle')}
                </button>
              )}
              <button type="button" className="btn" onClick={onReset}>
                {t('job.newSearch')}
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}

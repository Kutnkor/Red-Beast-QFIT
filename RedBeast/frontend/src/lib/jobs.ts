// Search-job state machine and polling loop (no React here, so it can be unit-tested with a mocked API).

import { ApiError } from './api'
import type { Job, JobStatus, ParsedPosition, SearchRequest, SearchResponse, WavelengthGroup } from './types'

export const TERMINAL: JobStatus[] = ['done', 'insufficient_data', 'failed', 'cancelled']

export function isTerminal(status: JobStatus): boolean {
  return TERMINAL.includes(status)
}

export type JobState =
  | { phase: 'idle' }
  | { phase: 'submitting'; request: SearchRequest }
  | { phase: 'running'; request: SearchRequest; job: Job; position: ParsedPosition | null; cancelling: boolean }
  | { phase: 'done'; request: SearchRequest; job: Job; position: ParsedPosition | null; sequenceId: string }
  | {
      phase: 'insufficient'
      request: SearchRequest
      job: Job
      position: ParsedPosition | null
      sequenceId: string | null
      reason: string
      groups: WavelengthGroup[]
    }
  | { phase: 'failed'; request: SearchRequest; code: string; reason?: string; source: 'job' | 'http'; job: Job | null }
  | { phase: 'cancelled'; request: SearchRequest; job: Job | null }

export type JobAction =
  | { type: 'submit'; request: SearchRequest }
  | { type: 'submitted'; response: SearchResponse }
  | { type: 'polled'; job: Job }
  | { type: 'cancel_requested' }
  | { type: 'http_error'; error: ApiError }
  | { type: 'reset' }

export const initialJobState: JobState = { phase: 'idle' }

function fromJob(request: SearchRequest, job: Job, position: ParsedPosition | null, cancelling: boolean): JobState {
  switch (job.status) {
    case 'done':
      if (job.sequence_id) return { phase: 'done', request, job, position, sequenceId: job.sequence_id }
      return { phase: 'failed', request, code: 'internal_error', source: 'job', job }
    case 'insufficient_data': {
      const detail = job.detail ?? {}
      const reason = typeof detail.reason === 'string' && detail.reason ? detail.reason : job.sequence_id ? 'single_frame' : 'unknown'
      return {
        phase: 'insufficient',
        request,
        job,
        position,
        sequenceId: job.sequence_id ?? null,
        reason,
        groups: Array.isArray(detail.groups) ? detail.groups : [],
      }
    }
    case 'failed':
      return { phase: 'failed', request, code: job.error || 'internal_error', source: 'job', job }
    case 'cancelled':
      return { phase: 'cancelled', request, job }
    default:
      return { phase: 'running', request, job, position, cancelling: cancelling || Boolean(job.cancel_requested) }
  }
}

export function jobReducer(state: JobState, action: JobAction): JobState {
  switch (action.type) {
    case 'submit':
      return { phase: 'submitting', request: action.request }
    case 'submitted':
      if (state.phase !== 'submitting') return state
      return fromJob(state.request, action.response.job, action.response.position ?? null, false)
    case 'polled':
      if (state.phase !== 'running') return state
      return fromJob(state.request, action.job, state.position, state.cancelling)
    case 'cancel_requested':
      if (state.phase === 'running') return { ...state, cancelling: true }
      if (state.phase === 'submitting') return { phase: 'cancelled', request: state.request, job: null }
      return state
    case 'http_error':
      if (state.phase !== 'submitting' && state.phase !== 'running') return state
      return {
        phase: 'failed',
        request: state.request,
        code: action.error.code,
        reason: action.error.reason,
        source: 'http',
        job: state.phase === 'running' ? state.job : null,
      }
    case 'reset':
      return initialJobState
    default:
      return state
  }
}

export interface JobApi {
  startSearch(body: SearchRequest, signal?: AbortSignal): Promise<SearchResponse>
  job(id: string, signal?: AbortSignal): Promise<{ job: Job }>
  cancelJob(id: string): Promise<{ job: Job }>
}

export interface RunOptions {
  intervalMs?: number
  /** consecutive failed status requests tolerated before giving up (the server may restart) */
  maxPollFailures?: number
  signal?: AbortSignal
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>
}

export function defaultSleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const id = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(id)
      resolve()
    })
  })
}

function toApiError(err: unknown): ApiError {
  return err instanceof ApiError ? err : new ApiError(0, 'network_error')
}

/**
 * Submit a search and poll its job until it reaches a terminal status.
 * Every transition is reported through `dispatch`; the returned promise resolves with the last job (or null).
 */
export async function runJob(
  client: JobApi,
  request: SearchRequest,
  dispatch: (action: JobAction) => void,
  opts: RunOptions = {},
): Promise<Job | null> {
  const interval = opts.intervalMs ?? 1000
  const maxFailures = opts.maxPollFailures ?? 3
  const sleep = opts.sleep ?? defaultSleep
  const signal = opts.signal

  dispatch({ type: 'submit', request })
  let job: Job
  try {
    const response = await client.startSearch(request, signal)
    if (signal?.aborted) return null
    dispatch({ type: 'submitted', response })
    job = response.job
  } catch (err) {
    if (signal?.aborted) return null
    dispatch({ type: 'http_error', error: toApiError(err) })
    return null
  }

  let failures = 0
  while (!isTerminal(job.status)) {
    await sleep(interval, signal)
    if (signal?.aborted) return job
    try {
      const res = await client.job(job.id, signal)
      if (signal?.aborted) return job
      failures = 0
      job = res.job
      dispatch({ type: 'polled', job })
    } catch (err) {
      if (signal?.aborted) return job
      const e = toApiError(err)
      failures += 1
      // a missing job is definitive; transient failures are retried
      if (e.code === 'job_not_found' || failures >= maxFailures) {
        dispatch({ type: 'http_error', error: e })
        return job
      }
    }
  }
  return job
}

/** Human-readable progress numbers for the UI. */
export function jobProgress(job: Job): { percent: number; nDone: number | null; nFrames: number | null } {
  const p = Number.isFinite(job.progress) ? Math.min(1, Math.max(0, job.progress)) : 0
  const d = job.detail
  const nDone = d && typeof d.n_done === 'number' ? d.n_done : null
  const nFrames = d && typeof d.n_frames === 'number' ? d.n_frames : null
  return { percent: Math.round(p * 100), nDone, nFrames }
}

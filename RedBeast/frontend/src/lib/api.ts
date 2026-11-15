// Typed client for the BlinkSpace API. All URLs are relative (`/api/...`): same origin in production,
// Vite proxy in development.

import type {
  CandidatesResult,
  DiffResult,
  Health,
  Job,
  LightCurve,
  Mark,
  Observation,
  ObservationCreated,
  Overlay,
  Provenance,
  SavedView,
  SearchRequest,
  SearchResponse,
  Sequence,
  StackResult,
  TargetsResponse,
  Tutorial,
} from './types'

export class ApiError extends Error {
  status: number
  code: string
  reason?: string

  constructor(status: number, code: string, message?: string, reason?: string) {
    super(message || code)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.reason = reason
  }
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>

let fetchImpl: FetchLike = (input, init) => fetch(input, init)

/** Test seam: replace the transport. */
export function setFetch(f: FetchLike | null): void {
  fetchImpl = f ?? ((input, init) => fetch(input, init))
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null
}

/** Turn any failed response body into an ApiError (server sends `{error:{code,message,reason?}}`). */
export function errorFromBody(status: number, body: unknown): ApiError {
  if (isRecord(body) && isRecord(body.error)) {
    const e = body.error
    const code = typeof e.code === 'string' ? e.code : 'http_error'
    const message = typeof e.message === 'string' ? e.message : code
    const reason = typeof e.reason === 'string' ? e.reason : undefined
    return new ApiError(status, code, message, reason)
  }
  if (isRecord(body) && Array.isArray(body.detail)) {
    // FastAPI request-validation errors do not use the `{error}` envelope
    return new ApiError(status, 'invalid_request')
  }
  if (status === 429) return new ApiError(status, 'rate_limited')
  if (status === 503) return new ApiError(status, 'queue_full')
  return new ApiError(status, status >= 500 ? 'internal_error' : 'http_error')
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response
  try {
    resp = await fetchImpl(path, init)
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(0, 'network_error')
  }
  if (resp.status === 204) return undefined as T
  let body: unknown = null
  try {
    body = await resp.json()
  } catch {
    body = null
  }
  if (!resp.ok) throw errorFromBody(resp.status, body)
  if (body === null) throw new ApiError(resp.status, 'bad_response')
  return body as T
}

const JSON_HEADERS = { 'Content-Type': 'application/json' }
const seq = (id: string) => `/api/sequences/${encodeURIComponent(id)}`

export interface ObservationBody {
  title: string
  note: string
  marks: Mark[]
  view: SavedView
}

export const api = {
  health: (signal?: AbortSignal) => request<Health>('/api/health', { signal }),
  targets: (signal?: AbortSignal) => request<TargetsResponse>('/api/targets', { signal }),
  tutorials: (signal?: AbortSignal) => request<{ tutorials: Tutorial[] }>('/api/tutorials', { signal }),

  startSearch: (body: SearchRequest, signal?: AbortSignal) =>
    request<SearchResponse>('/api/searches', { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(body), signal }),
  job: (id: string, signal?: AbortSignal) => request<{ job: Job }>(`/api/jobs/${encodeURIComponent(id)}`, { signal }),
  cancelJob: (id: string) => request<{ job: Job }>(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),

  sequence: (id: string, signal?: AbortSignal) => request<Sequence>(seq(id), { signal }),
  provenance: (id: string, signal?: AbortSignal) => request<Provenance>(`${seq(id)}/provenance`, { signal }),
  diff: (id: string, a: number, b: number, signal?: AbortSignal) =>
    request<DiffResult>(`${seq(id)}/diff?a=${a}&b=${b}`, { signal }),
  stack: (id: string, signal?: AbortSignal) => request<StackResult>(`${seq(id)}/stack`, { signal }),
  overlay: (id: string, catalog: 'gaia' | 'allwise', signal?: AbortSignal) =>
    request<Overlay>(`${seq(id)}/overlay?catalog=${catalog}`, { signal }),
  candidates: (id: string, a: number, b: number, signal?: AbortSignal) =>
    request<CandidatesResult>(`${seq(id)}/candidates?a=${a}&b=${b}`, { signal }),
  lightcurveTarget: (id: string, signal?: AbortSignal) =>
    request<LightCurve>(`${seq(id)}/lightcurve?follow_target=true`, { signal }),
  lightcurveAt: (id: string, ra: number, dec: number, signal?: AbortSignal) =>
    request<LightCurve>(`${seq(id)}/lightcurve?ra=${ra.toFixed(6)}&dec=${dec.toFixed(6)}`, { signal }),

  observation: (id: string, signal?: AbortSignal) =>
    request<{ observation: Observation }>(`/api/observations/${encodeURIComponent(id)}`, { signal }),
  createObservation: (sequenceId: string, body: ObservationBody) =>
    request<ObservationCreated>('/api/observations', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({ sequence_id: sequenceId, ...body }),
    }),
  updateObservation: (id: string, token: string, body: ObservationBody) =>
    request<{ observation: Observation }>(`/api/observations/${encodeURIComponent(id)}`, {
      method: 'PUT',
      headers: { ...JSON_HEADERS, 'X-Edit-Token': token },
      body: JSON.stringify(body),
    }),
  deleteObservation: (id: string, token: string) =>
    request<void>(`/api/observations/${encodeURIComponent(id)}`, { method: 'DELETE', headers: { 'X-Edit-Token': token } }),
}

export type Api = typeof api

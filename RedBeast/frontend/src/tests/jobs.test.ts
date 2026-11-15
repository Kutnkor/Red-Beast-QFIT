import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, errorFromBody } from '../lib/api'
import { describeApiError, describeCoordinateReason, describeError, describeInsufficient, describeJobError } from '../lib/errors'
import { initialJobState, isTerminal, jobProgress, jobReducer, runJob, type JobAction, type JobState } from '../lib/jobs'
import type { SearchRequest } from '../lib/types'
import { job, jsonResponse, mockFetch, POSITION, route } from './helpers'

const REQUEST: SearchRequest = { ra: '269.4463', dec: '+4.7682', ra_unit: 'auto', fov_arcmin: 6, max_frames: 8 }
const noSleep = () => Promise.resolve()

/** Run the real client (api.ts) against a scripted server and collect every state transition. */
async function run(request: SearchRequest = REQUEST, opts: Parameters<typeof runJob>[3] = {}) {
  const states: JobState[] = [initialJobState]
  const dispatch = (a: JobAction) => states.push(jobReducer(states[states.length - 1], a))
  const last = await runJob(api, request, dispatch, { sleep: noSleep, ...opts })
  return { states, final: states[states.length - 1], last }
}

afterEach(() => vi.useRealTimers())

describe('job polling', () => {
  it('follows queued → searching → downloading → preparing → done', async () => {
    const polls = [
      job('searching', { progress: 0.02 }),
      job('downloading', { progress: 0.35, detail: { n_frames: 6, n_done: 3 } }),
      job('preparing', { progress: 0.7 }),
      job('done', { progress: 1, sequence_id: 'vwu8zey93r', stage: 'done' }),
    ]
    const calls = mockFetch(
      route('POST', '/api/searches', () => jsonResponse({ job: job('queued'), position: POSITION }, 202)),
      route('GET', '/api/jobs/job0000001', () => jsonResponse({ job: polls.shift() })),
    )
    const { states, final } = await run()
    expect(states.map((s) => s.phase)).toEqual(['idle', 'submitting', 'running', 'running', 'running', 'running', 'done'])
    expect(states.filter((s) => s.phase === 'running').map((s) => (s.phase === 'running' ? s.job.status : ''))).toEqual([
      'queued',
      'searching',
      'downloading',
      'preparing',
    ])
    expect(final.phase === 'done' && final.sequenceId).toBe('vwu8zey93r')
    expect(final.phase === 'done' && final.position?.notes).toEqual(['ra_assumed_degrees'])
    // request body is passed through untouched; URLs are relative
    expect(calls[0]).toMatchObject({ method: 'POST', url: '/api/searches', body: REQUEST })
    expect(calls.filter((c) => c.method === 'GET')).toHaveLength(4)
    const downloading = states[4]
    expect(downloading.phase === 'running' && jobProgress(downloading.job)).toEqual({ percent: 35, nDone: 3, nFrames: 6 })
  })

  it('finishes immediately when the server answers from its cache', async () => {
    const calls = mockFetch(
      route('POST', '/api/searches', () =>
        jsonResponse({ job: job('done', { sequence_id: 'vwu8zey93r', progress: 1, detail: { from_cache: true } }), position: POSITION }, 202),
      ),
    )
    const { final } = await run({ target_id: 'barnard' })
    expect(final.phase).toBe('done')
    expect(calls).toHaveLength(1)
  })

  it('polls about once a second', async () => {
    vi.useFakeTimers()
    const polls = [job('searching'), job('done', { sequence_id: 'abcdef1234' })]
    const calls = mockFetch(
      route('POST', '/api/searches', () => jsonResponse({ job: job('queued'), position: POSITION }, 202)),
      route('GET', /^\/api\/jobs\//, () => jsonResponse({ job: polls.shift() })),
    )
    const states: JobState[] = [initialJobState]
    const p = runJob(api, REQUEST, (a) => states.push(jobReducer(states[states.length - 1], a)))
    await vi.advanceTimersByTimeAsync(900)
    expect(calls.filter((c) => c.method === 'GET')).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(200)
    expect(calls.filter((c) => c.method === 'GET')).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1000)
    await p
    expect(calls.filter((c) => c.method === 'GET')).toHaveLength(2)
    expect(states[states.length - 1].phase).toBe('done')
  })

  it('reports insufficient data with a single-frame sequence', async () => {
    mockFetch(
      route('POST', '/api/searches', () => jsonResponse({ job: job('queued'), position: POSITION }, 202)),
      route('GET', /^\/api\/jobs\//, () =>
        jsonResponse({ job: job('insufficient_data', { sequence_id: 'single0001', detail: { reused: false, reason: 'single_frame' } }) }),
      ),
    )
    const { final } = await run()
    expect(final.phase).toBe('insufficient')
    if (final.phase !== 'insufficient') return
    expect(final.sequenceId).toBe('single0001')
    expect(final.reason).toBe('single_frame')
    expect(final.groups).toEqual([])
  })

  it('reports insufficient data without a sequence, with wavelength options', async () => {
    const groups = [
      { lam_ref_um: 1.51174, bw_ref_um: 0.037, n_frames: 6, n_visits: 6, span_days: 392.9 },
      { lam_ref_um: 4.29096, bw_ref_um: 0.037, n_frames: 6, n_visits: 6, span_days: 392.9 },
    ]
    mockFetch(
      route('POST', '/api/searches', () => jsonResponse({ job: job('searching'), position: POSITION }, 202)),
      route('GET', /^\/api\/jobs\//, () =>
        jsonResponse({ job: job('insufficient_data', { detail: { reason: 'no_frames_at_wavelength', groups, lam_ref_um: 3.3 } }) }),
      ),
    )
    const { final } = await run({ ...REQUEST, lam_um: 3.3 })
    expect(final.phase).toBe('insufficient')
    if (final.phase !== 'insufficient') return
    expect(final.sequenceId).toBeNull()
    expect(final.reason).toBe('no_frames_at_wavelength')
    expect(final.groups.map((g) => g.lam_ref_um)).toEqual([1.51174, 4.29096])
    expect(describeInsufficient('en', final.reason)).toMatch(/requested wavelength/)
    for (const reason of ['no_coverage', 'no_usable_frames', 'all_frames_rejected']) {
      expect(describeInsufficient('tr', reason)).not.toBe(describeInsufficient('tr', 'nonsense'))
    }
  })

  it('reports failed jobs with their error code', async () => {
    for (const code of ['timeout', 'archive_error', 'internal_error', 'interrupted_by_restart']) {
      mockFetch(
        route('POST', '/api/searches', () => jsonResponse({ job: job('queued'), position: POSITION }, 202)),
        route('GET', /^\/api\/jobs\//, () => jsonResponse({ job: job('failed', { error: code, stage: 'failed' }) })),
      )
      const { final } = await run()
      expect(final.phase).toBe('failed')
      if (final.phase !== 'failed') return
      expect(final.code).toBe(code)
      expect(final.source).toBe('job')
      expect(final.request).toEqual(REQUEST) // kept for the retry button
      expect(describeJobError('tr', code)).not.toContain(code)
      expect(describeJobError('en', code)).not.toContain(code)
    }
  })

  it('cancels: the request is posted and the loop ends on the cancelled status', async () => {
    let cancelled = false
    const calls = mockFetch(
      route('POST', '/api/searches', () => jsonResponse({ job: job('queued'), position: POSITION }, 202)),
      route('POST', '/api/jobs/job0000001/cancel', () => {
        cancelled = true
        return jsonResponse({ job: job('downloading', { cancel_requested: 1 }) })
      }),
      route('GET', /^\/api\/jobs\//, () => jsonResponse({ job: cancelled ? job('cancelled') : job('downloading', { progress: 0.3 }) })),
    )
    const states: JobState[] = [initialJobState]
    const dispatch = (a: JobAction) => states.push(jobReducer(states[states.length - 1], a))
    let n = 0
    const sleep = async () => {
      n += 1
      if (n === 3) {
        dispatch({ type: 'cancel_requested' })
        const res = await api.cancelJob('job0000001')
        dispatch({ type: 'polled', job: res.job })
      }
    }
    await runJob(api, REQUEST, dispatch, { sleep })
    const final = states[states.length - 1]
    expect(final.phase).toBe('cancelled')
    expect(states.some((s) => s.phase === 'running' && s.cancelling)).toBe(true)
    expect(calls.some((c) => c.method === 'POST' && c.url === '/api/jobs/job0000001/cancel')).toBe(true)
  })

  it('stops polling when aborted (page left)', async () => {
    const ctrl = new AbortController()
    const calls = mockFetch(
      route('POST', '/api/searches', () => jsonResponse({ job: job('queued'), position: POSITION }, 202)),
      route('GET', /^\/api\/jobs\//, () => jsonResponse({ job: job('searching') })),
    )
    let n = 0
    const sleep = async () => {
      n += 1
      if (n === 3) ctrl.abort()
    }
    const { final } = await run(REQUEST, { sleep, signal: ctrl.signal })
    expect(final.phase).toBe('running')
    expect(calls.filter((c) => c.method === 'GET')).toHaveLength(2)
  })

  it('survives one failed status request (server restart) but gives up after three', async () => {
    let n = 0
    mockFetch(
      route('POST', '/api/searches', () => jsonResponse({ job: job('queued'), position: POSITION }, 202)),
      route('GET', /^\/api\/jobs\//, () => {
        n += 1
        if (n === 1) throw new TypeError('fetch failed')
        return jsonResponse({ job: job('done', { sequence_id: 'vwu8zey93r' }) })
      }),
    )
    expect((await run()).final.phase).toBe('done')

    mockFetch(
      route('POST', '/api/searches', () => jsonResponse({ job: job('queued'), position: POSITION }, 202)),
      route('GET', /^\/api\/jobs\//, () => {
        throw new TypeError('fetch failed')
      }),
    )
    const { final } = await run()
    expect(final.phase === 'failed' && final.code).toBe('network_error')
    expect(final.phase === 'failed' && final.source).toBe('http')
  })

  it('turns HTTP errors on submit into a failed state (422, 429, 503)', async () => {
    const cases: [number, unknown, string, string | undefined][] = [
      [422, { error: { code: 'bad_coordinates', message: 'Dec −90 ile +90 derece arasında olmalı.', reason: 'dec_out_of_range' } }, 'bad_coordinates', 'dec_out_of_range'],
      [429, { error: { code: 'rate_limited', message: 'x' } }, 'rate_limited', undefined],
      [503, { error: { code: 'queue_full', message: 'x' } }, 'queue_full', undefined],
      [422, { error: { code: 'invalid_request', message: 'x', fields: [{ loc: ['body', 'fov_arcmin'], msg: 'm', type: 't' }] } }, 'invalid_request', undefined],
      [500, null, 'internal_error', undefined],
    ]
    for (const [status, body, code, reason] of cases) {
      const calls = mockFetch(route('POST', '/api/searches', () => jsonResponse(body, status)))
      const { final } = await run()
      expect(final.phase).toBe('failed')
      if (final.phase !== 'failed') return
      expect(final.code).toBe(code)
      expect(final.reason).toBe(reason)
      expect(final.source).toBe('http')
      expect(calls).toHaveLength(1) // no polling after a rejected submit
    }
  })
})

describe('job reducer', () => {
  const running = jobReducer(jobReducer(initialJobState, { type: 'submit', request: REQUEST }), {
    type: 'submitted',
    response: { job: job('queued'), position: POSITION },
  })

  it('ignores stray events', () => {
    expect(jobReducer(initialJobState, { type: 'polled', job: job('done', { sequence_id: 'x' }) })).toBe(initialJobState)
    expect(jobReducer(initialJobState, { type: 'cancel_requested' })).toBe(initialJobState)
    expect(jobReducer(initialJobState, { type: 'http_error', error: new ApiError(500, 'internal_error') })).toBe(initialJobState)
  })

  it('keeps the cancelling flag until the server confirms', () => {
    const c = jobReducer(running, { type: 'cancel_requested' })
    expect(c.phase === 'running' && c.cancelling).toBe(true)
    const still = jobReducer(c, { type: 'polled', job: job('downloading') })
    expect(still.phase === 'running' && still.cancelling).toBe(true)
    expect(jobReducer(still, { type: 'polled', job: job('cancelled') }).phase).toBe('cancelled')
  })

  it('resets and treats a done job without a sequence as a failure', () => {
    expect(jobReducer(running, { type: 'reset' })).toBe(initialJobState)
    const broken = jobReducer(running, { type: 'polled', job: job('done') })
    expect(broken.phase).toBe('failed')
    expect(isTerminal('done') && isTerminal('insufficient_data') && isTerminal('failed') && isTerminal('cancelled')).toBe(true)
    expect(isTerminal('queued') || isTerminal('searching') || isTerminal('downloading') || isTerminal('preparing')).toBe(false)
  })
})

describe('error translation', () => {
  it('translates every coordinate reason in both languages', () => {
    const reasons = ['not_a_number', 'dec_out_of_range', 'ra_out_of_range', 'unit_mismatch', 'bad_sexagesimal', 'empty', 'not_finite', 'too_long', 'bad_unit', 'ra_negative_sexagesimal']
    const tr = reasons.map((r) => describeCoordinateReason('tr', r))
    const en = reasons.map((r) => describeCoordinateReason('en', r))
    expect(new Set(tr).size).toBe(reasons.length)
    expect(new Set(en).size).toBe(reasons.length)
    for (const text of [...tr, ...en]) expect(text).not.toMatch(/_/)
    expect(describeCoordinateReason('tr', 'dec_out_of_range')).toBe('Dec −90° ile +90° arasında olmalı.')
    expect(describeCoordinateReason('en', 'unit_mismatch')).toBe('The way it is written does not match the selected unit.')
  })

  it('uses the reason for bad_coordinates and falls back for unknown ones', () => {
    expect(describeApiError('en', 'bad_coordinates', 'empty')).toBe('The coordinate is empty.')
    expect(describeApiError('en', 'bad_coordinates', 'brand_new_reason')).toBe('The coordinates could not be understood.')
    expect(describeApiError('en', 'bad_coordinates')).toBe('The coordinates could not be understood.')
    expect(describeApiError('tr', 'rate_limited')).toMatch(/Çok fazla istek/)
    expect(describeApiError('en', 'queue_full')).toMatch(/busy/)
    expect(describeApiError('en', 'something_new')).toBe('The request failed (something_new).')
    expect(describeError('en', new ApiError(422, 'bad_coordinates', 'x', 'bad_sexagesimal'))).toMatch(/sexagesimal/i)
    expect(describeError('tr', new Error('boom'))).toMatch(/başarısız/)
  })

  it('parses error envelopes', () => {
    const e = errorFromBody(422, { error: { code: 'bad_coordinates', message: 'm', reason: 'empty' } })
    expect([e.status, e.code, e.reason, e.message]).toEqual([422, 'bad_coordinates', 'empty', 'm'])
    expect(errorFromBody(422, { detail: [{ loc: ['body'], msg: 'x' }] }).code).toBe('invalid_request')
    expect(errorFromBody(429, null).code).toBe('rate_limited')
    expect(errorFromBody(503, 'oops').code).toBe('queue_full')
    expect(errorFromBody(502, {}).code).toBe('internal_error')
    expect(errorFromBody(404, {}).code).toBe('http_error')
  })

  it('maps transport failures to network_error', async () => {
    mockFetch(() => {
      throw new TypeError('Failed to fetch')
    })
    await expect(api.targets()).rejects.toMatchObject({ code: 'network_error', status: 0 })
  })
})

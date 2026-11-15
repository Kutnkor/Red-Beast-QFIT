import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { I18nProvider } from '../i18n'
import { matchRoute, withSticky } from '../lib/router'
import { loadDraft, loadToken } from '../lib/storage'
import { answerQuiz, applyEvent, isComplete, isCorrect, parseTutorials } from '../lib/tutorials'
import type { Lang, LightCurve, Tutorial } from '../lib/types'
import { FALLBACK_LIMITS, buildRequest, decHint, defaultValues, raHint, valuesFromQuery } from '../pages/SearchForm'
import { LightCurveChart, pointState } from '../viewer/LightCurve'
import { ObservationCard } from '../viewer/ObservationCard'
import { Timeline } from '../viewer/Timeline'
import { TutorialPanel } from '../viewer/TutorialPanel'
import { Viewer } from '../viewer/Viewer'
import { HEALTH, job, jsonResponse, mockFetch, POSITION, route, sequence, TARGETS } from './helpers'
import { DEFAULT_STATE, getAppState, setAppState } from '../lib/store'
import golden from './golden/motion.json'
import stellarModels from '../../../backend/blinkspace/resources/stellar_profiles.json'

// GPU drawing is verified separately. These tests exercise the real shell, API and viewer flows.
vi.mock('../three/SkyCanvas', () => ({ default: () => <div data-testid="scientific-scene" /> }))
const MOTION = { stars: [], targets: golden.stars.map(entry => ({ ...entry.input, teff_k: null, teff_source: 'none' })),
  reference: { moon_mean_diameter_arcsec: { value: 1896, source_url: 'https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html' } } }
beforeEach(() => setAppState({ ...DEFAULT_STATE, mode: 'star', layers: { ...DEFAULT_STATE.layers }, drawer: { ...DEFAULT_STATE.drawer } }))

function wrap(ui: ReactNode, lang: Lang = 'tr') {
  // <App /> kendi dil sağlayıcısını kurar; dili kayıtlı tercihten okur (jsdom'un tarayıcı dili en-US'tir)
  window.localStorage.setItem('bs.lang', lang)
  return render(<I18nProvider initial={lang}>{ui}</I18nProvider>)
}

const baseRoutes = (tutorials: Tutorial[] = []) => [
  route('GET', '/api/health', () => jsonResponse(HEALTH)),
  route('GET', '/api/targets', () => jsonResponse({ targets: TARGETS })),
  route('GET', '/api/tutorials', () => jsonResponse({ tutorials })),
  route('GET', '/api/motion', () => jsonResponse(MOTION)),
  route('GET', '/api/models', () => jsonResponse(stellarModels)),
  route('GET', '/api/assistant/status', () => jsonResponse({ enabled: false, provider: null })),
  route('GET', /\/track$/, () => jsonResponse({ source: 'predicted_only', frames: [], status: { change_scientifically_confirmed: false } })),
  route('GET', '/api/sequences/vwu8zey93r', () => jsonResponse(sequence())),
]

const GUIDED: Tutorial = {
  id: 'barnard-motion',
  title: { tr: 'Barnard hareketi', en: 'Barnard motion' },
  summary: { tr: 'Yıldızın kaydığını görün', en: 'See the star move' },
  kind: 'guided',
  target_id: 'barnard',
  synthetic: false,
  steps: [
    { id: 's1', text: { tr: 'Diziyi açın', en: 'Open the sequence' }, event: 'sequence_opened' },
    { id: 's2', text: { tr: 'Kare değiştirin', en: 'Change frame' }, event: 'frame_changed' },
    { id: 's3', text: { tr: 'İşaret ekleyin', en: 'Add a mark' }, event: 'mark_added' },
    { id: 's4', text: { tr: 'Paylaşın', en: 'Share it' }, event: 'observation_shared' },
  ],
  view: { mode: 'single', frame_a: 0, frame_b: 5 },
}

const QUIZ: Tutorial = {
  id: 'quiz-1',
  title: { tr: 'Soru', en: 'Quiz' },
  summary: { tr: 'Özet', en: 'Summary' },
  kind: 'quiz',
  target_id: 'barnard',
  synthetic: true,
  question: { tr: 'Hangi yöne?', en: 'Which way?' },
  options: [
    { id: 'n', text: { tr: 'Kuzey', en: 'North' } },
    { id: 's', text: { tr: 'Güney', en: 'South' } },
  ],
  answer_id: 'n',
  explanation: { tr: 'Özdevinim kuzeye doğrudur.', en: 'The proper motion points north.' },
}

afterEach(() => vi.useRealTimers())

// ---------------------------------------------------------------------------------------------
describe('router', () => {
  it('matches the three routes', () => {
    expect(matchRoute('/')).toEqual({ name: 'home' })
    expect(matchRoute('/s/vwu8zey93r')).toEqual({ name: 'sequence', id: 'vwu8zey93r' })
    expect(matchRoute('/o/abc123def4/')).toEqual({ name: 'observation', id: 'abc123def4' })
    expect(matchRoute('/s/NOPE')).toEqual({ name: 'notfound' })
    expect(matchRoute('/s/../etc')).toEqual({ name: 'notfound' })
    expect(matchRoute('/about')).toEqual({ name: 'notfound' })
  })

  it('keeps embed=1 across navigation', () => {
    expect(withSticky('/s/abc123', '?embed=1&ra=1')).toBe('/s/abc123?embed=1')
    expect(withSticky('/s/abc123?tut=x', '?embed=1')).toBe('/s/abc123?tut=x&embed=1')
    expect(withSticky('/', '?lang=en')).toBe('/')
  })
})

describe('search form logic', () => {
  it('builds the request body and blocks only impossible input', () => {
    const v = { ...defaultValues(FALLBACK_LIMITS), ra: ' 17h57m47.1s ', dec: '+04 46 05.5', unit: 'hour' as const, lam: '4,29', dateFrom: '2025-08-01', dateTo: '2026-09-30' }
    expect(buildRequest(v, FALLBACK_LIMITS)).toEqual({
      problems: [],
      request: { ra: '17h57m47.1s', dec: '+04 46 05.5', ra_unit: 'hour', fov_arcmin: 6, max_frames: 8, lam_um: 4.29, date_from: '2025-08-01', date_to: '2026-09-30' },
    })
    const bad = buildRequest({ ...v, ra: '', fov: '45', frames: '1', lam: '9', dateFrom: '2026-10-01' }, FALLBACK_LIMITS)
    expect(bad.request).toBeNull()
    expect(bad.problems.map((p) => p.key)).toEqual([
      'form.hint.raRequired',
      'form.hint.fovRange',
      'form.hint.framesRange',
      'form.hint.lamRange',
      'form.hint.dateOrder',
    ])
    // odd-looking coordinates are left to the server
    expect(buildRequest({ ...v, ra: 'abc', dec: '95' }, FALLBACK_LIMITS).request).not.toBeNull()
  })

  it('gives non-binding hints', () => {
    expect(raHint('17h57m47.1s', 'auto')).toBe('form.hint.hourLike')
    expect(raHint('17 57 47.1', 'auto')).toBe('form.hint.hourLike')
    expect(raHint('269.4463', 'auto')).toBe('form.hint.degLike')
    expect(raHint('269.4463', 'deg')).toBeNull()
    expect(raHint('', 'auto')).toBeNull()
    expect(decHint('95')).toBe('form.hint.decRange')
    expect(decHint('−91.5')).toBe('form.hint.decRange')
    expect(decHint('+04 46 05.5')).toBeNull()
    expect(decHint('-7.24')).toBeNull()
  })

  it('reads the embedding query string', () => {
    const q = new URLSearchParams('ra=133.76&dec=-7.24&fov=8&unit=deg&lam=4.86&frames=12')
    expect(valuesFromQuery(q, FALLBACK_LIMITS)).toMatchObject({ ra: '133.76', dec: '-7.24', fov: '8', unit: 'deg', lam: '4.86', frames: '12' })
    expect(valuesFromQuery(new URLSearchParams('ra=1&dec=2&unit=x'), FALLBACK_LIMITS)?.unit).toBe('auto')
    expect(valuesFromQuery(new URLSearchParams('target=barnard'), FALLBACK_LIMITS)).toBeNull()
  })
})

describe('tutorial progress', () => {
  it('ticks guided steps only for the events that really happened', () => {
    let p = { done: [] as string[] }
    p = applyEvent(GUIDED, p, 'mark_added')
    expect(p.done).toEqual(['s3'])
    p = applyEvent(GUIDED, p, 'mark_added')
    expect(p.done).toEqual(['s3'])
    p = applyEvent(GUIDED, p, 'sequence_opened')
    p = applyEvent(GUIDED, p, 'frame_changed')
    expect(isComplete(GUIDED, p)).toBe(false)
    p = applyEvent(GUIDED, p, 'observation_shared')
    expect(isComplete(GUIDED, p)).toBe(true)
  })

  it('accepts one quiz answer and judges it', () => {
    let p = answerQuiz(QUIZ, { done: [] }, 'zzz')
    expect(p.answer).toBeUndefined()
    p = answerQuiz(QUIZ, p, 's')
    expect(isCorrect(QUIZ, p)).toBe(false)
    expect(answerQuiz(QUIZ, p, 'n').answer).toBe('s')
    expect(isCorrect(QUIZ, answerQuiz(QUIZ, { done: [] }, 'n'))).toBe(true)
    expect(isComplete(QUIZ, p)).toBe(true)
  })

  it('tolerates an empty or malformed list', () => {
    expect(parseTutorials({ tutorials: [] })).toEqual([])
    expect(parseTutorials(null)).toEqual([])
    expect(parseTutorials({ tutorials: [GUIDED, { id: 5 }, null, QUIZ] })).toHaveLength(2)
  })
})

// ---------------------------------------------------------------------------------------------
describe('workspace shell (preserved legacy UI)', () => {
  // Keep every baseline assertion; the new default shell has its own interaction suite.
  beforeEach(() => window.history.replaceState(null, '', '/?ui=legacy'))
  it('lists all five targets, keeps archive search available, and opens a ready sequence', async () => {
    const calls = mockFetch(...baseRoutes())
    wrap(<App />)
    const targets = await screen.findByRole('complementary', { name: 'Hedefler' })
    expect(within(targets).getAllByRole('button', { name: /Barnard|Epsilon|WISE|RW Aurigae|R Draconis/ })).toHaveLength(5)
    expect(screen.getByText('Bir konumda SPHEREx karelerini bul')).toBeTruthy()
    expect(await screen.findByRole('heading', { name: "Barnard's Star" })).toBeTruthy()
    expect(getAppState().playing).toBe(false)
    fireEvent.click(screen.getAllByRole('button', { name: 'Gözlemler' })[0])
    expect(await screen.findByTestId('current-date')).toBeTruthy()
    expect(screen.getByTestId('current-date').textContent).toBe('2025-08-25 17:09 UTC')
    expect(calls.some(c => c.url === '/api/sequences/vwu8zey93r')).toBe(true)
    expect(calls.some(c => c.method !== 'GET')).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Kaynaklar' }))
    expect(await screen.findByRole('dialog')).toBeTruthy()
    expect(screen.getByText(/NASA tarafından geliştirilmemiş ve onaylanmamıştır/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'NASA/IPAC IRSA · SPHEREx' })).toBeTruthy()
  })

  it('switches language and remembers it without resetting the selected scientific view', async () => {
    mockFetch(...baseRoutes())
    const user = userEvent.setup()
    wrap(<App />)
    await screen.findByRole('heading', { name: "Barnard's Star" })
    fireEvent.change(screen.getByRole('slider', { name: 'Yıl · doğrusal model' }), { target: { value: '2050' } })
    await user.click(screen.getByRole('button', { name: 'EN' }))
    expect(screen.getByRole('slider', { name: 'Year · linear model' })).toBeTruthy()
    expect(getAppState().year).toBe(2050)
    expect(window.localStorage.getItem('bs.lang')).toBe('en')
    expect(document.documentElement.lang).toBe('en')
    expect(document.title).toContain('RedBeast')
  })

  it('prepares an unready target, reports real job progress and opens the resulting sequence', async () => {
    const polls = [job('downloading', { progress: 0.35, detail: { n_frames: 6, n_done: 2 } }), job('done', { sequence_id: 'r8nxknqqp8', progress: 1 })]
    const calls = mockFetch(
      ...baseRoutes(),
      route('POST', '/api/searches', () => jsonResponse({ job: job('queued'), position: POSITION }, 202)),
      route('GET', /^\/api\/jobs\//, () => jsonResponse({ job: polls.shift() ?? job('done', { sequence_id: 'r8nxknqqp8' }) })),
      route('GET', '/api/sequences/r8nxknqqp8', () => jsonResponse({ ...sequence(), id: 'r8nxknqqp8', meta: { ...sequence().meta, target_id: 'r-dra' } })),
    )
    wrap(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /R Draconis/ }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Gözlemler' })[0])
    fireEvent.click(await screen.findByRole('button', { name: 'SPHEREx karelerini hazırla' }))
    expect(await screen.findByText('Sırada')).toBeTruthy()
    expect(screen.getByText(/17h57m47.10s/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'İptal et' })).toBeTruthy()
    expect(await screen.findByText(/2\/6 kare indirildi/, undefined, { timeout: 3000 })).toBeTruthy()
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('35')
    await waitFor(() => expect(window.location.pathname).toBe('/s/r8nxknqqp8'), { timeout: 3000 })
    expect(calls.find(c => c.method === 'POST')?.body).toEqual({ target_id: 'r-dra' })
  })

  it('shows a translated coordinate error from the server next to the open form', async () => {
    const calls = mockFetch(
      ...baseRoutes(),
      route('POST', '/api/searches', () => jsonResponse({ error: { code: 'bad_coordinates', message: 'Dec −90 ile +90 derece arasında olmalı.', reason: 'dec_out_of_range' } }, 422)),
    )
    const user = userEvent.setup()
    wrap(<App />, 'en')
    await screen.findByRole('heading', { name: "Barnard's Star" })
    await user.click(screen.getByText('Find SPHEREx frames at a position'))
    await user.type(screen.getByLabelText('Right ascension (RA)'), '269.4463')
    await user.type(screen.getByLabelText('Declination (Dec)'), '95')
    expect(screen.getByText('Dec must be between −90 and +90.')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByText('Dec must be between −90° and +90°.')).toBeTruthy()
    expect(calls.find(c => c.method === 'POST')?.body).toEqual({ ra: '269.4463', dec: '95', ra_unit: 'auto', fov_arcmin: 6, max_frames: 8 })
    expect(screen.queryByRole('progressbar')).toBeNull()
  })

  it('query-string coordinates start one search and insufficient data offer another wavelength', async () => {
    window.history.replaceState(null, '', '/?ui=legacy&ra=133.76&dec=-7.24&fov=8&unit=deg&lam=3.3&frames=4&lang=en')
    const groups = [{ lam_ref_um: 4.83787, bw_ref_um: 0.037, n_frames: 5, n_visits: 5, span_days: 359.2 }]
    const bodies: unknown[] = []
    mockFetch(...baseRoutes(), route('POST', '/api/searches', c => {
      bodies.push(c.body)
      return jsonResponse({ job: job('insufficient_data', { detail: { reason: 'no_frames_at_wavelength', groups } }), position: POSITION }, 202)
    }))
    render(<App />)
    expect(await screen.findByText('Not enough data for a comparison')).toBeTruthy()
    expect(bodies).toHaveLength(1)
    expect(bodies[0]).toEqual({ ra: '133.76', dec: '-7.24', ra_unit: 'deg', fov_arcmin: 8, max_frames: 4, lam_um: 3.3 })
    expect(screen.getByText(/No frames at the requested wavelength/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /4\.838 µm · 5 frames · 5 visits · 359 days/ }))
    await waitFor(() => expect(bodies).toHaveLength(2))
    expect(bodies[1]).toMatchObject({ ra: '133.76', lam_um: 4.83787 })
  })

  it('failed archive preparation retains the error and supports retry', async () => {
    let posts = 0
    mockFetch(...baseRoutes(), route('POST', '/api/searches', () => {
      posts++
      return jsonResponse({ job: job('failed', { error: 'archive_error', stage: 'failed' }), position: POSITION }, 202)
    }))
    wrap(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /R Draconis/ }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Gözlemler' })[0])
    fireEvent.click(await screen.findByRole('button', { name: 'SPHEREx karelerini hazırla' }))
    expect(await screen.findByText('Arama tamamlanamadı')).toBeTruthy()
    expect(screen.getByText(/Arşive \(IRSA\) erişilemedi veya arşiv hata döndürdü/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Yeniden dene' }))
    await waitFor(() => expect(posts).toBe(2))
  })

  it('retains embed mode and the permanent scene when changing target or mode', async () => {
    window.history.replaceState(null, '', '/?embed=1&ui=legacy')
    mockFetch(...baseRoutes())
    const { container } = wrap(<App />)
    await screen.findByRole('heading', { name: "Barnard's Star" })
    const scene = await screen.findByTestId('scientific-scene')
    fireEvent.click(screen.getByRole('button', { name: /R Draconis/ }))
    expect(window.location.search).toContain('embed=1')
    expect(window.location.search).toContain('target=r-dra')
    fireEvent.click(screen.getAllByRole('button', { name: 'Yakın çevre' })[0])
    expect(screen.getByTestId('scientific-scene')).toBe(scene)
    expect(container.querySelector('.app-embed')).toBeTruthy()
    expect(screen.queryByRole('contentinfo')).toBeNull()
  })

  it('shows stellar measurement uncertainty and source limitations in English', async () => {
    mockFetch(...baseRoutes())
    wrap(<App />, 'en')
    expect(await screen.findByText('0.187 ± 0.001 R☉')).toBeTruthy()
    expect(screen.getByText('3,195 ± 28 K')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Download Three.js model' }).getAttribute('href')).toBe('/models/barnard.three.json')
    const section = screen.getByText('Surface and surroundings model').closest('section')!
    fireEvent.click(within(section).getByText('Sources behind this model'))
    expect(within(section).getByText("The surface and plasma are not resolved images of Barnard's Star.")).toBeTruthy()
    expect(within(section).getAllByRole('link').length).toBeGreaterThan(0)
  })

  it('keeps unknown binary radii explicit and localizes the component temperatures', async () => {
    mockFetch(...baseRoutes())
    wrap(<App />, 'tr')
    fireEvent.click(await screen.findByRole('button', { name: /Epsilon Indi B/ }))
    expect(await screen.findByText('1.320 K')).toBeTruthy()
    expect(screen.getByText('910 K')).toBeTruthy()
    const download = screen.getByRole('link', { name: 'Three.js modelini indir' })
    expect(download.getAttribute('href')).toBe('/models/eps-indi-b.three.json')
    expect(download.hasAttribute('download')).toBe(true)
    const profile = stellarModels.profiles.find(item => item.target_id === 'eps-indi-b')!
    expect(screen.getByText(profile.caveats_tr[0])).toBeTruthy()
    expect(screen.queryByText(profile.caveats[0])).toBeNull()
  })
})

// ---------------------------------------------------------------------------------------------
describe('timeline component', () => {
  const frames = sequence().frames.map((f) => ({ mjd: f.mjd_avg, date: f.date_avg }))

  it('places a handle per frame by real date and is keyboard operable', () => {
    const onSelect = vi.fn()
    wrap(<Timeline frames={frames} current={2} reference={0} showReference onSelect={onSelect} />)
    const handles = screen.getAllByRole('button')
    expect(handles).toHaveLength(6)
    expect(handles.map((h) => Number(h.getAttribute('data-frac')))).toEqual([0, 0.0126, 0.5124, 0.9115, 0.919, 1])
    expect(handles[2].getAttribute('aria-current')).toBe('true')
    expect(handles[3].getAttribute('aria-label')).toBe('Kare 4: 2026-08-18 20:49 UTC')
    const slider = screen.getByRole('slider')
    expect(slider.getAttribute('aria-valuetext')).toBe('Kare 3: 2026-03-15 00:51 UTC')
    fireEvent.keyDown(slider, { key: 'ArrowRight' })
    fireEvent.keyDown(slider, { key: 'ArrowLeft' })
    fireEvent.keyDown(slider, { key: 'Home' })
    fireEvent.keyDown(slider, { key: 'End' })
    expect(onSelect.mock.calls.map((c) => c[0])).toEqual([3, 1, 0, 5])
    fireEvent.click(handles[4])
    expect(onSelect).toHaveBeenLastCalledWith(4)
  })
})

describe('light curve', () => {
  const base = { index: 0, mjd: 60912.7, date: '2025-08-25T17:09:20Z', obs_id: 'a', valid: false, flux_mjy: null, err_mjy: null }
  const curve = (points: LightCurve['points']): LightCurve => ({
    position_mode: 'follows_predicted_target',
    lam_ref_um: 1.51152,
    bw_ref_um: 0.0371,
    quantitative_tolerance: 0.25,
    unit: 'mJy',
    points,
    caveats: ['aperture_flux_no_correction', 'single_wavelength_group_only'],
  })

  it('shows invalid points as "ölçüm yok", never as zero', () => {
    const pts = [0, 1, 2].map((i) => ({ ...base, index: i, mjd: 60912.7 + i * 100, reason: 'invalid_pixels_in_aperture', saturated: true }))
    const { container } = wrap(<LightCurveChart curve={curve(pts)} current={0} />)
    expect(container.querySelectorAll('[data-state="none"]')).toHaveLength(3)
    // no measured data point is drawn (the legend keeps its own samples outside the chart groups)
    expect(container.querySelectorAll('g[data-state="ok"], g[data-state="offtol"], g[data-state="unreliable"]')).toHaveLength(0)
    expect(screen.getByText(/hiçbir karede geçerli ölçüm yok/)).toBeTruthy()
    const rows = within(container.querySelector('table') as HTMLElement).getAllByRole('row').slice(1)
    for (const row of rows) {
      expect(row.textContent).toContain('ölçüm yok')
      expect(row.textContent).not.toMatch(/0\.000/)
    }
    expect(screen.getByText('Açıklık akısı; açıklık düzeltmesi uygulanmadı.')).toBeTruthy()
    expect(screen.getByText(/Yalnızca bu dizinin dalga boyu grubu \(1\.512 µm\) çizilir/)).toBeTruthy()
  })

  it('distinguishes reliable, off-tolerance, saturated and missing points', () => {
    const pts: LightCurve['points'] = [
      { ...base, index: 0, valid: true, flux_mjy: 12.5, err_mjy: 0.4, reliable: true, quantitative_ok: true },
      { ...base, index: 1, mjd: 61000, valid: true, flux_mjy: 14.1, err_mjy: 0.5, reliable: true, quantitative_ok: false },
      { ...base, index: 2, mjd: 61100, valid: true, flux_mjy: 30, err_mjy: 2, reliable: false, saturated: true, reason: 'saturated_or_nonlinear' },
      { ...base, index: 3, mjd: 61200, reason: 'off_frame' },
    ]
    expect(pts.map(pointState)).toEqual(['ok', 'offtol', 'unreliable', 'none'])
    const onSelect = vi.fn()
    const { container } = wrap(<LightCurveChart curve={curve(pts)} current={1} onSelect={onSelect} />, 'en')
    const svg = container.querySelector('svg.lc-svg') as SVGElement
    expect(svg.querySelectorAll('[data-state="ok"]')).toHaveLength(1)
    expect(svg.querySelectorAll('[data-state="offtol"]')).toHaveLength(1)
    expect(svg.querySelectorAll('[data-state="unreliable"]')).toHaveLength(1)
    expect(svg.querySelectorAll('[data-state="none"]')).toHaveLength(1)
    expect(svg.querySelectorAll('.lc-err')).toHaveLength(3)
    expect(svg.getAttribute('aria-label')).toBe('Light curve: 4 frames, 3 valid measurements')
    expect(screen.getByText('12.500 ± 0.400')).toBeTruthy()
    expect(screen.getByText('no measurement (position is off the frame)')).toBeTruthy()
    fireEvent.click(svg.querySelector('[data-state="unreliable"]') as Element)
    expect(onSelect).toHaveBeenCalledWith(2)
  })
})

describe('observation card', () => {
  it('renders user text as plain text and never claims a discovery', () => {
    const evil = '<img src=x onerror="window.__pwned=1"><script>window.__pwned=1</script> <b>bold</b>'
    const marks = [
      { id: 'm1', kind: 'point' as const, classification: 'possible_motion' as const, ra_deg: 269.44, dec_deg: 4.77, frame_index: 3, note: evil, track_id: null },
    ]
    const { container } = wrap(<ObservationCard sequence={sequence()} marks={marks} title={evil} note={evil} targetName="Barnard's Star" />)
    expect(container.querySelectorAll('script, b')).toHaveLength(0)
    expect(container.querySelectorAll('img')).toHaveLength(6) // only the six frame thumbnails
    expect(screen.getAllByText(evil).length).toBe(3)
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined()
    expect(screen.getByText('doğrulanmayı bekleyen gözlem')).toBeTruthy()
    expect(screen.getByText('Olası hareket')).toBeTruthy()
    expect(screen.getByText(/Kare 4 · 2026-08-18 20:49 UTC/)).toBeTruthy()
    expect(container.textContent).not.toMatch(/keşfedildi|discovered/i)
    expect(container.querySelectorAll('a[href^="https://irsa.ipac.caltech.edu/"]')).toHaveLength(6)
    for (const a of container.querySelectorAll('a')) expect(a.getAttribute('rel')).toContain('noopener')
  })
})

describe('tutorial panel', () => {
  it('shows the synthetic badge and reveals the explanation after answering', () => {
    const onAnswer = vi.fn()
    const { rerender } = wrap(<TutorialPanel tutorial={QUIZ} progress={{ done: [] }} onAnswer={onAnswer} onReset={() => {}} onClose={() => {}} />)
    expect(screen.getByText('sentetik eğitim verisi')).toBeTruthy()
    expect(screen.queryByText('Özdevinim kuzeye doğrudur.')).toBeNull()
    fireEvent.click(screen.getByLabelText('Güney'))
    expect(onAnswer).toHaveBeenCalledWith('s')
    rerender(
      <I18nProvider initial="tr">
        <TutorialPanel tutorial={QUIZ} progress={{ done: [], answer: 's' }} onAnswer={onAnswer} onReset={() => {}} onClose={() => {}} />
      </I18nProvider>,
    )
    expect(screen.getByText('Bu seçenek doğru değil.')).toBeTruthy()
    expect(screen.getByText('Doğru yanıt: Kuzey')).toBeTruthy()
    expect(screen.getByText('Özdevinim kuzeye doğrudur.')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------------------------
describe('viewer', () => {
  const analysis = () => [
    route('GET', /\/diff\?a=0&b=5$/, () =>
      jsonResponse({
        a: 0,
        b: 5,
        dt_days: 392.9139,
        lam_a_um: 1.51677,
        lam_b_um: 1.51119,
        sigma_mjy_sr: 0.04211,
        display_scale_mjy_sr: 0.42108,
        valid_frac: 0.9483,
        caveats: ['no_psf_matching', 'psf_fwhm_differs'],
        image_url: '/api/sequences/vwu8zey93r/files/diff_00_05.png',
      }),
    ),
    route('GET', /\/stack$/, () =>
      jsonResponse({ n_frames: 6, valid_frac: 0.9891, target_motion_px: 1.82, span_days: 392.914, caveats: ['moving_sources_blur'], image_url: '/api/sequences/vwu8zey93r/files/stack.png' }),
    ),
    route('GET', /\/overlay\?catalog=gaia$/, () =>
      jsonResponse({
        catalog: 'Gaia DR3',
        type: 'catalog',
        band: 'G (optik)',
        catalog_epoch: 2016.0,
        shown_epoch: 2026.25,
        resolution_note: 'Gaia ≈0.4″ çözer; SPHEREx pikseli 6.15″',
        propagation: 'proper_motion_only',
        n: 2,
        sources: [
          { id: '1', ra: 269.446212, dec: 4.768925, mag: 8.19, pm_masyr: 10393.3, per_frame: [0, 1, 2, 3, 4, 5].map((i) => [269.446347 - i * 5e-5, 4.767194 + i * 6e-4]) },
          { id: '2', ra: 269.443854, dec: 4.796293, mag: 11.86, pm_masyr: 6.2 },
        ],
      }),
    ),
  ]

  const pane = () => screen.getAllByTestId('pane')
  const visibleFrame = (el: HTMLElement) =>
    [...el.querySelectorAll<HTMLImageElement>('img.px')].filter((i) => i.style.visibility === 'visible').map((i) => i.getAttribute('src'))

  it('shows the real frames, does not autoplay, and plays only on request', async () => {
    mockFetch(...baseRoutes())
    vi.useFakeTimers({ shouldAdvanceTime: true })
    wrap(<Viewer sequence={sequence()} />)
    expect(screen.getByTestId('current-date').textContent).toBe('2025-08-25 17:09 UTC')
    expect(visibleFrame(pane()[0])).toEqual(['/api/sequences/vwu8zey93r/files/frame_00.png'])
    expect(pane()[0].querySelectorAll('img.px')).toHaveLength(6) // all six frames are decoded up front
    expect(screen.getByText(/oynatma hızı gerçek zamanı temsil etmez/)).toBeTruthy()

    await act(() => vi.advanceTimersByTimeAsync(3000))
    expect(screen.getByTestId('current-date').textContent).toBe('2025-08-25 17:09 UTC') // no autoplay

    fireEvent.click(screen.getByRole('button', { name: 'Oynat' }))
    await act(() => vi.advanceTimersByTimeAsync(1100)) // 2 fps → two frames
    expect(screen.getByTestId('current-date').textContent).toBe('2026-03-15 00:51 UTC')
    fireEvent.click(screen.getByRole('button', { name: 'Duraklat' }))
    await act(() => vi.advanceTimersByTimeAsync(2000))
    expect(screen.getByTestId('current-date').textContent).toBe('2026-03-15 00:51 UTC')
    expect(await screen.findByRole('heading', { name: "Barnard's Star" })).toBeTruthy()
  })

  it('keyboard: arrows step frames, space plays, B blinks, M marks, Enter adds a mark that persists', async () => {
    mockFetch(...baseRoutes())
    wrap(<Viewer sequence={sequence()} />)
    const date = () => screen.getByTestId('current-date').textContent
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(date()).toBe('2025-08-30 16:11 UTC')
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(date()).toBe('2026-09-22 15:05 UTC') // wraps around
    fireEvent.keyDown(window, { key: 'b' }) // A=frame 1, B=frame 6 → swap
    expect(date()).toBe('2025-08-25 17:09 UTC')
    fireEvent.keyDown(window, { key: 'b' })
    expect(date()).toBe('2026-09-22 15:05 UTC')
    expect(screen.getByTestId('announce').textContent).toBe('Kare 6/6, 2026-09-22 15:05 UTC')

    fireEvent.keyDown(window, { key: ' ' })
    expect(screen.getByRole('button', { name: 'Duraklat' })).toBeTruthy()
    fireEvent.keyDown(window, { key: ' ' })
    expect(screen.getByRole('button', { name: 'Oynat' })).toBeTruthy()

    fireEvent.keyDown(window, { key: '+' })
    expect(screen.getByText('1.5×')).toBeTruthy()
    fireEvent.keyDown(window, { key: '0' })
    expect(screen.getByText('1.0×')).toBeTruthy()

    // typing in a field must not trigger shortcuts
    fireEvent.click(screen.getByRole('tab', { name: /İşaretler/ }))
    fireEvent.keyDown(screen.getByLabelText(/^Başlık/), { key: 'ArrowRight' })
    expect(date()).toBe('2026-09-22 15:05 UTC')

    fireEvent.keyDown(window, { key: 'm' })
    expect(screen.getAllByRole('button', { name: 'İşaretlemeyi bitir' }).length).toBeGreaterThan(0)
    const p = pane()[0]
    fireEvent.keyDown(p, { key: 'Enter' })
    expect(await screen.findByRole('button', { name: /İşareti seç: 1, Emin değilim/ })).toBeTruthy()
    const saved = loadDraft('vwu8zey93r').marks
    expect(saved).toHaveLength(1)
    expect(saved[0].frame_index).toBe(5) // bound to the frame it was made on
    expect(saved[0].ra_deg).toBeCloseTo(269.446269, 5) // view centre = field centre
    expect(saved[0].dec_deg).toBeCloseTo(4.768204, 5)
    expect(p.querySelectorAll('[data-mark]')).toHaveLength(1)

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.getAllByRole('button', { name: 'İşaret ekle' }).length).toBeGreaterThan(0)
    fireEvent.keyDown(window, { key: 'Delete' })
    expect(loadDraft('vwu8zey93r').marks).toHaveLength(0)
    fireEvent.keyDown(window, { key: '?' })
    expect(screen.getByRole('dialog', { name: 'Klavye kısayolları' })).toBeTruthy()
  })

  it('side-by-side shows A and B with both dates; difference and stack load with caveats and a way back', async () => {
    const calls = mockFetch(...baseRoutes(), ...analysis())
    wrap(<Viewer sequence={sequence()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Yan yana' }))
    expect(pane()).toHaveLength(2)
    expect(within(pane()[0]).getByText('A · 2025-08-25 17:09 UTC')).toBeTruthy()
    expect(within(pane()[1]).getByText('B · 2026-09-22 15:05 UTC')).toBeTruthy()
    expect(visibleFrame(pane()[0])).toEqual(['/api/sequences/vwu8zey93r/files/frame_00.png'])
    expect(visibleFrame(pane()[1])).toEqual(['/api/sequences/vwu8zey93r/files/frame_05.png'])

    fireEvent.click(screen.getByRole('button', { name: 'Fark' }))
    expect(await screen.findByText(/392\.9 gün/)).toBeTruthy()
    expect(visibleFrame(pane()[0])).toEqual(['/api/sequences/vwu8zey93r/files/diff_00_05.png'])
    expect(screen.getByText('PSF eşleştirmesi yapılmadı.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Oynat' }).hasAttribute('disabled')).toBe(true)
    expect(calls.some((c) => c.url === '/api/sequences/vwu8zey93r/diff?a=0&b=5')).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: 'Birleştirme' }))
    expect(await screen.findByText(/1\.82 piksel/)).toBeTruthy()
    expect(screen.getByText('Hareketli kaynaklar birleştirmede bulanıklaşır ya da iz bırakır.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Ham karelere dön' }))
    expect(visibleFrame(pane()[0])).toEqual(['/api/sequences/vwu8zey93r/files/frame_05.png'])
  })

  it('layers: quality mask, Gaia overlay with per-frame positions, predicted marker off by default', async () => {
    mockFetch(...baseRoutes(), ...analysis())
    wrap(<Viewer sequence={sequence()} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Katmanlar' }))
    const p = pane()[0]
    expect(p.querySelector('.pane-mask')).toBeNull()
    expect(p.querySelector('.predicted')).toBeNull()
    fireEvent.click(screen.getByLabelText('Kalite maskesi'))
    expect(p.querySelector('.pane-mask')?.getAttribute('src')).toBe('/api/sequences/vwu8zey93r/files/frame_00_mask.png')
    fireEvent.click(screen.getByLabelText('Gaia DR3'))
    await waitFor(() => expect(p.querySelectorAll('.cat-gaia')).toHaveLength(2))
    expect(screen.getByText(/G \(optik\) · katalog dönemi 2016\.0 · 2 kaynak/)).toBeTruthy()
    expect(screen.getByText(/Gaia ≈0\.4″ çözer; SPHEREx pikseli 6\.15″/)).toBeTruthy()
    const fast = () => Number(p.querySelector('.cat-gaia[r="6.5"]')?.getAttribute('cy'))
    const y0 = fast()
    fireEvent.keyDown(window, { key: 'End' })
    expect(fast()).toBeLessThan(y0) // the fast star moved north (up) by the last frame
    fireEvent.click(screen.getByLabelText('Öngörülen hedef konumu (yalnızca özdevinim)'))
    expect(p.querySelector('.predicted')).not.toBeNull()
    expect(screen.getByText(/paralaks ve gözlemci etkisi içermez/)).toBeTruthy()
    expect(screen.getAllByText('İnceleme yardımı — doğrulanmış keşif değildir.').length).toBeGreaterThan(0)
    expect(screen.getAllByText('ölçüm yok').length).toBeGreaterThan(0)
  })

  it('shows warning banners, including the rejected frames for partial data and the single-frame state', () => {
    mockFetch(...baseRoutes())
    const { unmount } = wrap(<Viewer sequence={sequence(6, ['partial_data', 'center_saturated'])} />)
    expect(screen.getByText(/Eksik veri/)).toBeTruthy()
    expect(screen.getByText(/2026W01_1A_0001_1 · D2 — alan kapsaması düşük/)).toBeTruthy()
    expect(screen.getByText(/Alan merkezindeki kaynak doymuş/)).toBeTruthy()
    unmount()
    wrap(<Viewer sequence={sequence(1, ['single_frame'])} />)
    expect(screen.getByText(/Yetersiz karşılaştırma/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Fark' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: 'Oynat' }).hasAttribute('disabled')).toBe(true)
  })

  it('frame details expose provenance fields', () => {
    mockFetch(...baseRoutes())
    wrap(<Viewer sequence={sequence()} />, 'en')
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('2025-08-25 17:09:20 UTC')).toBeTruthy()
    expect(within(panel).getByText('60912.71481')).toBeTruthy()
    expect(within(panel).getByText('l2b-v20-2025-269')).toBeTruthy()
    expect(within(panel).getByText('bbfe9fe867b2a6ac…')).toBeTruthy()
    expect(within(panel).getByText('Source at the centre is saturated')).toBeTruthy()
    expect(within(panel).getByText('OVERFLOW (5)')).toBeTruthy()
    expect(within(panel).getByRole('link', { name: /Archive file/ }).getAttribute('href')).toBe('https://irsa.ipac.caltech.edu/ibe/data/spherex/f0.fits')
  })

  it('saves an observation, stores the edit token, shows the share link, then updates with the token', async () => {
    const seq = sequence()
    const created = { id: 'obs1234567', sequence_id: seq.id, title: 'T', note: '', marks: [], view: {}, app_version: '1.0.0', created_at: 1, updated_at: 1, status: 'unverified_user_observation', sequence: seq }
    const calls = mockFetch(
      ...baseRoutes([GUIDED]),
      route('POST', '/api/observations', () => jsonResponse({ observation: created, edit_token: 'tok-secret', share_path: '/o/obs1234567?ui=legacy' }, 201)),
      route('PUT', '/api/observations/obs1234567', () => jsonResponse({ observation: created })),
    )
    const user = userEvent.setup()
    wrap(<Viewer sequence={seq} tutorialId="barnard-motion" />)
    // the tutorial opens, applies its view (B = frame 6) and ticks "sequence opened"
    expect(await screen.findByText('Barnard hareketi')).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('current-date').textContent).toBe('2026-09-22 15:05 UTC'))
    const stepState = () => [...document.querySelectorAll('.steps .step')].map((li) => li.classList.contains('step-done'))
    expect(stepState()).toEqual([true, false, false, false])

    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    fireEvent.keyDown(window, { key: 'm' })
    fireEvent.keyDown(pane()[0], { key: 'Enter' })
    await user.type(await screen.findByLabelText(/^Başlık/), 'Kayan yıldız')
    await user.click(screen.getByRole('button', { name: 'Kaydet ve bağlantı oluştur' }))
    const url = (await screen.findByTestId('share-url')) as HTMLInputElement
    expect(url.value).toBe(`${window.location.origin}/o/obs1234567`)
    expect(loadToken('obs1234567')).toBe('tok-secret')
    expect(loadDraft(seq.id).observationId).toBe('obs1234567')

    const post = calls.find((c) => c.method === 'POST' && c.url === '/api/observations')?.body as Record<string, unknown>
    expect(post.sequence_id).toBe('vwu8zey93r')
    expect(post.title).toBe('Kayan yıldız')
    const marks = post.marks as Record<string, unknown>[]
    expect(marks).toHaveLength(1)
    expect(Object.keys(marks[0]).sort()).toEqual(['classification', 'dec_deg', 'frame_index', 'id', 'kind', 'note', 'ra_deg'])
    expect(marks[0].frame_index).toBe(4)
    expect(post.view).toMatchObject({ f: 4, r: 0, m: 'single', z: 1 })
    expect(JSON.stringify(post.view).length).toBeLessThan(2000)

    await user.click(screen.getByRole('button', { name: 'Paylaşılan gözlemi güncelle' }))
    await screen.findByText('Paylaşılan gözlem güncellendi.')
    const put = calls.find((c) => c.method === 'PUT')
    expect(put?.headers['X-Edit-Token']).toBe('tok-secret')

    fireEvent.click(screen.getByRole('tab', { name: 'Görev' }))
    expect(stepState()).toEqual([true, true, true, true])
    expect(screen.getByText('Görev tamamlandı.')).toBeTruthy()
  })

  it('a shared observation is read-only, labelled unverified, and can be continued', async () => {
    const seq = sequence()
    const observation = {
      id: 'obs1234567',
      sequence_id: seq.id,
      title: 'Kayan yıldız',
      note: 'Kuzeye kayıyor',
      marks: [
        { id: 'a', kind: 'point', classification: 'possible_motion', ra_deg: 269.446347, dec_deg: 4.767193, frame_index: 0, note: '', track_id: 't1', date: '2025-08-25T17:09:20Z', status: 'unverified' },
        { id: 'b', kind: 'point', classification: 'possible_motion', ra_deg: 269.446107, dec_deg: 4.77029, frame_index: 5, note: 'son', track_id: 't1', date: '2026-09-22T15:05:19Z', status: 'unverified' },
      ],
      view: { z: 2, ra: 269.446269, dec: 4.768204, f: 5, r: 0, m: 'side', l: ['marks'] },
      app_version: '1.0.0',
      created_at: 1794430000,
      updated_at: 1794430000,
      status: 'unverified_user_observation',
      sequence: seq,
    }
    window.history.replaceState(null, '', '/o/obs1234567?ui=legacy')
    const calls = mockFetch(
      ...baseRoutes(),
      route('GET', '/api/observations/obs1234567', () => jsonResponse({ observation })),
      route('GET', '/api/sequences/vwu8zey93r', () => jsonResponse(seq)),
    )
    wrap(<App />)
    expect(await screen.findByText(/Doğrulanmayı bekleyen kullanıcı gözlemi/)).toBeTruthy()
    // the saved view is restored: side by side, zoom 2, B = frame 6
    expect(pane()).toHaveLength(2)
    expect(screen.getByText('2.0×')).toBeTruthy()
    expect(screen.getByTestId('current-date').textContent).toBe('2026-09-22 15:05 UTC')
    // both panes draw both marks and the track, each point labelled with its own frame date
    for (const p of pane()) {
      expect(p.querySelectorAll('[data-mark]')).toHaveLength(2)
      expect(p.querySelectorAll('polyline.track')).toHaveLength(1)
      expect(p.textContent).toContain('1 · 2025-08-25')
      expect(p.textContent).toContain('2 · 2026-09-22')
    }
    expect(screen.queryByRole('button', { name: 'İşaret ekle' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Kaydet ve bağlantı oluştur' })).toBeNull()
    expect(screen.getByText('Bu paylaşılan gözlemdeki işaretler salt okunurdur.')).toBeTruthy()
    expect(screen.getAllByText('Kuzeye kayıyor').length).toBeGreaterThan(0)
    expect(calls.some((c) => c.method !== 'GET')).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: 'Bu gözlemden devam et' }))
    await waitFor(() => expect(window.location.pathname).toBe('/s/vwu8zey93r'))
    const draft = loadDraft('vwu8zey93r')
    expect(draft.marks.map((m) => m.id)).toEqual(['a', 'b'])
    expect(draft.title).toBe('Kayan yıldız')
    expect(draft.observationId).toBeNull() // not the creator → saving makes a new observation
    expect(await screen.findByRole('button', { name: 'Kaydet ve bağlantı oluştur' })).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------------------------
describe('spectrum', () => {
  it('keeps invalid points as "ölçüm yok", marks flagged points unreliable and states that points are not simultaneous', async () => {
    const { SpectrumChart, pointState } = await import('../viewer/SpectrumPanel')
    const spectrum = {
      id: 'x'.repeat(32),
      date_window: ['2025-08-28T00:00:00Z', '2025-09-09T00:00:00Z'] as [string, string],
      span_days: 7.1,
      n_points: 3,
      n_reliable: 1,
      n_exposures_in_window: 25,
      position_mode: 'follows_predicted_target',
      simultaneous: false,
      unit: 'mJy',
      points: [
        { obs_id: 'a', detector: 1, date: '2025-09-02T00:44:00Z', mjd: 60920.03, valid: true, reliable: true, lam_um: 0.747, bw_um: 0.018, flux_mjy: 78.14, err_mjy: 0.32 },
        { obs_id: 'b', detector: 1, date: '2025-09-02T23:30:00Z', mjd: 60920.98, valid: false, reason: 'invalid_pixels_in_aperture', lam_um: 0.801, bw_um: 0.019, flux_mjy: null, err_mjy: null },
        { obs_id: 'c', detector: 1, date: '2025-09-03T17:27:00Z', mjd: 60921.73, valid: true, reliable: false, saturated: true, lam_um: 0.9, bw_um: 0.022, flux_mjy: 160.32, err_mjy: 0.48 },
      ],
    }
    expect(spectrum.points.map(pointState)).toEqual(['ok', 'none', 'unreliable'])
    const { container } = wrap(<SpectrumChart spectrum={spectrum} />)
    expect(container.querySelectorAll('g[data-state="ok"]')).toHaveLength(1)
    expect(container.querySelectorAll('g[data-state="unreliable"]')).toHaveLength(1)
    const none = container.querySelectorAll('g[data-state="none"]')
    expect(none).toHaveLength(1)
    expect(none[0].querySelector('circle')).toBeNull() // never drawn as a zero-flux point
    expect(none[0].querySelector('title')?.textContent).toContain('ölçüm yok')
    expect(screen.getByText(/ölçüm yok \(sıfır değildir\)/)).toBeTruthy()
  })
})

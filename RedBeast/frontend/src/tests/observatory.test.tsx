import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { DEFAULT_STATE, getAppState, setAppState } from '../lib/store'
import { HEALTH, jsonResponse, mockFetch, route, sequence, TARGETS, job, POSITION } from './helpers'
import catalogue from '../../../backend/blinkspace/resources/motion_catalogue.json'
import models from '../../../backend/blinkspace/resources/stellar_profiles.json'
vi.mock('../three/SkyCanvas', () => ({ default: () => <div data-testid="new-scientific-scene" /> }))
beforeEach(() => {
  window.history.replaceState(null, '', '/?ui=classic')
  setAppState({ ...DEFAULT_STATE, mode: 'star', layers: { ...DEFAULT_STATE.layers }, drawer: { ...DEFAULT_STATE.drawer } })
  window.localStorage.setItem('bs.lang', 'en')
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ enabled: false, provider: null })))
  Object.defineProperty(window, 'scrollTo', { configurable: true, value: vi.fn() })
})
afterEach(() => vi.unstubAllGlobals())
function routes() { return [
  route('GET', '/api/health', () => jsonResponse(HEALTH)), route('GET', '/api/targets', () => jsonResponse({ targets: TARGETS })),
  route('GET', '/api/motion', () => jsonResponse(catalogue)), route('GET', '/api/models', () => jsonResponse(models)),
  route('GET', '/api/tutorials', () => jsonResponse({ tutorials: [] })), route('GET', '/api/assistant/status', () => jsonResponse({ enabled: false, provider: null })),
  route('GET', /\/track$/, () => jsonResponse({ frames: [], status: {} })),
  route('GET', '/api/sequences/vwu8zey93r', () => jsonResponse(sequence())),
] }
describe('SPHERE-X retained classic shell', () => {
  it('keeps one science scene across all five targets and language changes', async () => {
    mockFetch(...routes()); const { container } = render(<App />)
    const scene = await screen.findByTestId('new-scientific-scene')
    await screen.findByRole('button', { name: "Barnard's Star" })
    for (const target of TARGETS) {
      fireEvent.click(screen.getByRole('button', { name: target.name }))
      expect(getAppState().targetId).toBe(target.id)
      expect(screen.getByTestId('new-scientific-scene')).toBe(scene)
    }
    fireEvent.change(screen.getByRole('slider', { name: 'Model year' }), { target: { value: '2059.6' } })
    fireEvent.click(screen.getByRole('button', { name: 'TR' }))
    expect(screen.getByRole('slider', { name: 'Model yılı' })).toBeTruthy()
    expect(getAppState().year).toBe(2059.6)
    expect(container.querySelector('[data-ui="observatory"]')).toBeTruthy()
  })
  it('keeps evolution progress independent of the observation year and exposes its source', async () => {
    mockFetch(...routes()); render(<App />)
    await screen.findByRole('button', { name: "Barnard's Star" })
    setAppState({ year: 2042 })
    fireEvent.click(screen.getByRole('button', { name: 'Evolution' }))
    fireEvent.change(screen.getByRole('slider', { name: 'Evolution progress' }), { target: { value: '0.7' } })
    expect(getAppState().year).toBe(2042)
    expect(getAppState().evolutionProgress).toBe(.7)
    expect(screen.getByRole('link', { name: /BHAC15/ }).getAttribute('href')).toContain('ens-lyon.fr')
    expect(screen.queryByRole('slider', { name: 'Model year' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Observed system' }))
    expect(screen.getByRole('slider', { name: 'Model year' })).toBeTruthy()
    expect(getAppState().year).toBe(2042)
  })
  it('opens actual model sources and downloads, retaining unknown binary values', async () => {
    mockFetch(...routes()); render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Epsilon Indi B' }))
    fireEvent.click(screen.getByRole('button', { name: 'Measurements' }))
    expect(await screen.findByText('1,320 K')).toBeTruthy(); expect(screen.getByText('910 K')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Download Three.js model' }).getAttribute('href')).toBe('/models/eps-indi-b.three.json')
    expect(screen.getAllByText(/Unknown/).length).toBeGreaterThan(0)
  })
  it('searches the catalogue with Ctrl K and exposes the original archive form', async () => {
    mockFetch(...routes()); render(<App />)
    await screen.findByRole('button', { name: 'R Draconis' })
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const dialog = screen.getByRole('dialog', { name: 'Find a star' })
    fireEvent.change(within(dialog).getByRole('searchbox'), { target: { value: 'WISE' } })
    expect(within(dialog).getByRole('button', { name: /WISE 0855/ })).toBeTruthy()
    fireEvent.click(within(dialog).getByText('Search real observations by coordinates'))
    expect(within(dialog).getByLabelText('Right ascension (RA)')).toBeTruthy()
    fireEvent.click(within(dialog).getByRole('button', { name: /WISE 0855/ }))
    expect(getAppState().targetId).toBe('wise-0855')
  })
  it('shows archive preparation progress without opening the search dialog', async () => {
    mockFetch(...routes(), route('POST', '/api/searches', () => jsonResponse({ job: job('queued'), position: POSITION }, 202)), route('GET', /^\/api\/jobs\//, () => jsonResponse({ job: job('queued') })))
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'R Draconis' }))
    fireEvent.click(screen.getByRole('button', { name: 'Observations' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Prepare SPHEREx frames' }))
    expect(await screen.findByText('Queued')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeTruthy()
  })
  it('opens real observations and all analysis tools while AI is off', async () => {
    mockFetch(...routes()); render(<App />)
    await screen.findByRole('button', { name: "Barnard's Star" })
    fireEvent.click(screen.getByRole('button', { name: 'Observations' }))
    expect(await screen.findByTestId('current-date')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Analysis tools' }))
    await waitFor(() => expect(getAppState().drawer.open).toBe(true))
    expect(screen.getByRole('button', { name: 'Time stack' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Time stack' }))
    expect(getAppState().stageView).toBe('timestack')
  })
  it('retains legacy and embed flags when navigating', async () => {
    window.history.replaceState(null, '', '/?ui=legacy&embed=1')
    mockFetch(...routes()); const { container } = render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /R Draconis/ }))
    expect(window.location.search).toContain('ui=legacy'); expect(window.location.search).toContain('embed=1')
    expect(container.querySelector('.workspace-app')).toBeTruthy()
  })
})

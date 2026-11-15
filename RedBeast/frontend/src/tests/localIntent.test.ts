import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createLocalAssistant } from '../qfit/localIntent'
import { DEFAULT_STATE, getAppState, setAppState } from '../lib/store'

const deps = () => ({
  targets: () => [{ id: 'barnard', name: "Barnard's Star" }, { id: 'r-dra', name: 'R Draconis' }, { id: 'wise-0855', name: 'WISE 0855−0714' }],
  frameCount: () => 6, select: vi.fn(), guide: vi.fn(), sources: vi.fn(), setLang: vi.fn(),
})

describe('the robin’s own navigation', () => {
  beforeEach(() => setAppState({ ...DEFAULT_STATE, targetId: 'barnard' }))

  it('takes the visitor to the Sun whatever star is showing', () => {
    const d = deps(), local = createLocalAssistant(d)
    setAppState({ mode: 'star', targetId: 'r-dra' })
    const reply = local('take me to the sun', 'en')
    expect(reply?.pin?.label).toBe('Go to the Sun')
    reply?.run?.()
    expect(getAppState()).toMatchObject({ mode: 'neighbors', skyScale: 'local' })
    const turkish = local('Güneş’e götür', 'tr')
    expect(turkish?.message).toContain('Güneş')
  })

  it('shows the Milky Way, changes comparison mode and steps frames', () => {
    const local = createLocalAssistant(deps())
    local('Samanyolu’nu göster', 'tr')?.run?.()
    expect(getAppState()).toMatchObject({ mode: 'neighbors', skyScale: 'galaxy' })
    local('compare side by side', 'en')?.run?.()
    expect(getAppState()).toMatchObject({ mode: 'observations', viewMode: 'side' })
    setAppState({ frameIndex: 5 })
    local('sonraki kare', 'tr')?.run?.()
    expect(getAppState().frameIndex).toBe(0)
  })

  it('selects a target by name and runs app actions', () => {
    const d = deps(), local = createLocalAssistant(d)
    local('R Draconis’e git', 'tr')?.run?.()
    expect(d.select).toHaveBeenCalledWith('r-dra')
    local('open sources', 'en')?.run?.()
    expect(d.sources).toHaveBeenCalledOnce()
    local('bu sayfayı gezdir', 'tr')?.run?.()
    expect(d.guide).toHaveBeenCalledOnce()
    local('go to the year 2080', 'en')?.run?.()
    expect(getAppState().year).toBe(2080)
  })

  it('leaves questions to the sourced assistant', () => {
    const local = createLocalAssistant(deps())
    expect(local('Güneş kaç yaşında?', 'tr')).toBeNull()
    expect(local('Why does Barnard’s Star move so fast?', 'en')).toBeNull()
    expect(local('Bu sayı nereden geliyor', 'tr')).toBeNull()
    expect(local('What can I observe in a galaxy', 'en')).toBeNull()
    expect(local('What is the source of these images', 'en')).toBeNull()
  })

  it("opens Barnard's star page from observations with a polite, misspelled command", () => {
    const d = deps(), local = createLocalAssistant(d)
    setAppState({ targetId: 'r-dra', mode: 'observations' })
    local('Could you take me to Bernard?', 'en')?.run?.()
    expect(d.select).toHaveBeenCalledWith('barnard')
    expect(getAppState()).toMatchObject({ mode: 'star', stellarMode: 'surface' })
  })

  it('opens a named target in the requested comparison view', () => {
    const local = createLocalAssistant(deps())
    local("Compare Barnard's frames side by side", 'en')?.run?.()
    expect(getAppState()).toMatchObject({ mode: 'observations', viewMode: 'side' })
    local('Blink', 'en')?.run?.()
    expect(getAppState()).toMatchObject({ mode: 'observations', viewMode: 'single', playing: true })
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { COMMANDS, runCommand, validateArgs } from '../lib/commands'
import { DEFAULT_STATE, getAppState, setAppState } from '../lib/store'

beforeEach(() => setAppState({ ...DEFAULT_STATE, layers: { ...DEFAULT_STATE.layers }, drawer: { ...DEFAULT_STATE.drawer } }))

describe('validated shared command bus', () => {
  it('provides strict argument schemas and bilingual descriptions for every exposed command', () => {
    expect(new Set(COMMANDS.map(command => command.name)).size).toBe(COMMANDS.length)
    for (const command of COMMANDS) {
      expect(command.schema.additionalProperties).toBe(false)
      expect(command.schema.required).toEqual(Object.keys(command.schema.properties))
      expect(command.description.tr.length).toBeGreaterThan(5)
      expect(command.description.en.length).toBeGreaterThan(5)
    }
  })
  it('rejects unknown, extra, mistyped and non-finite values without changing state', async () => {
    for (const args of [{}, { year: 1999 }, { year: 2101 }, { year: NaN }, { year: Infinity }, { year: '2050' }, { year: 2050, source: 'user' }, null, []]) {
      expect((await runCommand('set_year', args)).ok).toBe(false)
      expect(getAppState().year).toBe(2026)
    }
    expect((await runCommand('invent_discovery', {})).ok).toBe(false)
    expect((await runCommand('set_year', { year: 2050.5 })).ok).toBe(true)
    expect(getAppState().year).toBe(2050.5)
  })
  it('requires own JSON fields rather than accepting inherited properties', () => {
    const schema = COMMANDS.find(command => command.name === 'set_year')!.schema
    expect(validateArgs(schema, Object.create({ year: 2050 }))).toBe(false)
  })
  it('keeps an out-of-range frame from crossing the active sequence boundary', async () => {
    expect((await runCommand('set_frame', { index: 6 }, { frameCount: 6 })).ok).toBe(false)
    expect((await runCommand('set_frame', { index: 2.5 }, { frameCount: 6 })).ok).toBe(false)
    expect((await runCommand('set_frame', { index: -1 }, { frameCount: 6 })).ok).toBe(false)
    expect(getAppState().frameIndex).toBe(0)
    expect((await runCommand('set_frame', { index: 5 }, { frameCount: 6 })).ok).toBe(true)
    expect(getAppState().frameIndex).toBe(5)
  })
  it('resets sequence-bound state when selecting another catalogue target', async () => {
    setAppState({ sequenceId: 'sequence1', frameIndex: 5, refIndex: 3, playing: true })
    expect((await runCommand('select_target', { target_id: 'wise-0855' }, { source: 'user' })).ok).toBe(true)
    expect(getAppState()).toMatchObject({ targetId: 'wise-0855', sequenceId: null, frameIndex: 0, refIndex: 0, playing: false })
  })
  it('changes only the requested layer and opens the selected analysis tab', async () => {
    const before = getAppState().layers
    await runCommand('toggle_layer', { layer: 'grid', on: true })
    expect(getAppState().layers).toEqual({ ...before, grid: true })
    expect((await runCommand('toggle_layer', { layer: 'grid', on: 'true' })).ok).toBe(false)
    await runCommand('open_drawer_tab', { tab: 'curve' })
    expect(getAppState().drawer).toEqual({ open: true, tab: 'curve' })
  })
  it('requires confirmation for assistant-initiated searches and downloads', async () => {
    const startSearch = vi.fn(), saveView = vi.fn()
    const args = { ra: '17h57m47s', dec: '+04 46 05', ra_unit: 'hour', fov_arcmin: 6 }
    expect(await runCommand('start_search', args, { source: 'assistant', startSearch })).toEqual({ ok: false, message: 'Confirmation required' })
    expect((await runCommand('save_view', {}, { source: 'assistant', saveView })).ok).toBe(false)
    expect(startSearch).not.toHaveBeenCalled()
    expect(saveView).not.toHaveBeenCalled()
    expect((await runCommand('start_search', args, { source: 'assistant', confirmed: true, startSearch })).ok).toBe(true)
    expect(startSearch).toHaveBeenCalledExactlyOnceWith(args)
    expect((await runCommand('save_view', {}, { source: 'assistant', confirmed: true, saveView })).ok).toBe(true)
    expect(saveView).toHaveBeenCalledTimes(1)
  })
  it('a direct user action is consent, and failed callbacks return a bounded error', async () => {
    const saveView = vi.fn()
    expect((await runCommand('save_view', {}, { source: 'user', saveView })).ok).toBe(true)
    expect(saveView).toHaveBeenCalledTimes(1)
    const failure = await runCommand('save_view', {}, { source: 'user', saveView: async () => { throw new Error('Download unavailable') } })
    expect(failure).toEqual({ ok: false, message: 'Download unavailable' })
  })
})

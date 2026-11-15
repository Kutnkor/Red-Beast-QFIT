import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QFitAssistant } from '../qfit/QFitAssistant'
import { askQFit, checkedProposal, readStream, safeSource } from '../qfit/api'
import { COMMANDS, runCommand } from '../lib/commands'
import { DEFAULT_STATE, getAppState, setAppState } from '../lib/store'
import contract from '../../../tools/contracts/assistant-commands.json'

const response = { success: true, assistant: 'Q-FIT', intent: 'knowledge', message: 'Source-backed surface.', message_source: 'system', sources: [{ name: 'Source', url: '/api/assistant/sources/motion%23model' }], uncertainty: ['Representative geometry.'], data: {}, commands: [] }
beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: vi.fn() })
})
afterEach(() => vi.unstubAllGlobals())
const stream = (text: string) => new Response(new ReadableStream({ start(c) { const bytes = new TextEncoder().encode(text); for (let i = 0; i < bytes.length; i += 3) c.enqueue(bytes.slice(i, i + 3)); c.close() } }), { headers: { 'content-type': 'text/event-stream' } })
const event = (name: string, data: unknown) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`

describe('QFIT contract and guards', () => {
  it('matches all server command schemas and confirmation gates', async () => {
    expect(Object.fromEntries(COMMANDS.map(c => [c.name, c.schema]))).toEqual(contract)
    const search = vi.fn(), save = vi.fn()
    expect((await runCommand('start_search', { ra: '1', dec: '2', ra_unit: 'deg', fov_arcmin: 6 }, { source: 'assistant', startSearch: search })).ok).toBe(false)
    expect((await runCommand('save_view', {}, { source: 'assistant', saveView: save })).ok).toBe(false)
    expect(search).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled()
  })
  it('compares the first and last distinct observations', async () => {
    setAppState(DEFAULT_STATE)
    const result = await runCommand('show_observations', { view: 'side', pair: 'first_last' }, { getFrameCount: async () => 6 })
    expect(result.ok).toBe(true)
    expect(getAppState()).toMatchObject({ mode: 'observations', viewMode: 'side', refIndex: 0, frameIndex: 5, playing: false })
    expect((await runCommand('show_observations', { view: 'diff', pair: 'first_last' }, { frameCount: 1 })).ok).toBe(false)
    expect(getAppState().viewMode).toBe('side')
  })
  it('rejects unknown, extra, non-finite, and coerced arguments', () => {
    for (const p of [{ name: 'shell', args: {} }, { name: 'set_year', args: { year: '2050' } }, { name: 'set_year', args: { year: Infinity } }, { name: 'save_view', args: { path: 'file' } }]) expect(checkedProposal({ tool_use_id: 'id', ...p })).toBeNull()
    expect(checkedProposal({ tool_use_id: 'id', name: 'save_view', args: {}, requires_confirmation: false })?.requires_confirmation).toBe(true)
  })
  it('reassembles UTF-8 SSE, preserves metadata, and requires a terminating event', async () => {
    const text = 'Yıldızın yüzeyi ölçülmüş değildir.'
    const result = await readStream(stream(event('text', { delta: text }) + event('sources', ['motion#model']) + event('done', { stop_reason: 'end_turn', qfit: { ...response, message: text } })))
    expect(result.message).toBe(text); expect(result.message_source).toBe('system')
    await expect(readStream(stream(event('text', { delta: 'partial' })))).rejects.toThrow('Interrupted')
  })
  it('does not accept a command merely because the server sent it', async () => {
    await expect(readStream(stream(event('command', { tool_use_id: 'id', name: 'shell', args: {} }) + event('done', {})))).rejects.toThrow('Invalid')
  })
  it('rejects executable and credential-bearing citation URLs', () => {
    for (const url of ['javascript:alert(1)', 'data:text/html,test', 'https://u:p@example.com']) expect(safeSource(url)).toBe(false)
    expect(safeSource('/api/assistant/sources/motion%23model')).toBe(true)
    expect(safeSource('https://irsa.ipac.caltech.edu')).toBe(true)
  })
  it('uses local source cards when AI is off, without an AI request', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ enabled: false, provider: null })).mockResolvedValueOnce(Response.json(response))
    vi.stubGlobal('fetch', fetcher)
    const answer = await askQFit('What?', [], { ui_language: 'en' })
    expect(answer.message_source).toBe('system')
    expect(fetcher.mock.calls.map(c => c[0])).toEqual(['/api/assistant/status', '/api/assistant/knowledge'])
  })
  it('opens the mascot, renders citations and clears the local conversation', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => Response.json(url.endsWith('/status') ? { enabled: false, provider: null } : response)))
    render(<QFitAssistant lang="en" context={{}} onCommand={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Open the Q-FIT assistant' }))
    const dialog = screen.getByRole('dialog', { name: 'Q-FIT' })
    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: 'What do I see?' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('Source-backed surface.')).toBeTruthy()
    fireEvent.click(within(dialog).getByText('Sources'))
    expect(within(dialog).getByRole('link', { name: 'Source' }).getAttribute('href')).toContain('/api/assistant/sources/')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Clear chat' }))
    expect(screen.queryByText('Source-backed surface.')).toBeNull()
  })
  it('cancels an in-flight answer and offers retry', async () => {
    let signal: AbortSignal | undefined
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/status')) return Response.json({ enabled: true, provider: 'qfit' })
      signal = init?.signal ?? undefined
      return new Promise<Response>((_, reject) => signal?.addEventListener('abort', () => reject(new DOMException('Stopped', 'AbortError'))))
    }))
    render(<QFitAssistant lang="en" context={{}} onCommand={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Open the Q-FIT assistant' }))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Question' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(signal).toBeDefined())
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Stop' })))
    expect(signal?.aborted).toBe(true)
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy()
  })
  it('never runs proposals before the user clicks their confirmation', async () => {
    const onCommand = vi.fn().mockResolvedValue({ ok: true })
    const reply = { ...response, message_source: 'ai_generated', commands: undefined }
    vi.stubGlobal('fetch', vi.fn(async (url: string) => url.endsWith('/status') ? Response.json({ enabled: true, provider: 'qfit' }) : stream(event('command', { tool_use_id: 'id', name: 'save_view', args: {}, requires_confirmation: false }) + event('done', { qfit: reply }))))
    render(<QFitAssistant lang="en" context={{}} onCommand={onCommand} autoActions />)
    fireEvent.click(screen.getByRole('button', { name: 'Open the Q-FIT assistant' }))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Save' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    const button = await screen.findByRole('button', { name: /Confirm and run/ })
    await waitFor(() => expect(button.hasAttribute('disabled')).toBe(false))
    expect(onCommand).not.toHaveBeenCalled()
    fireEvent.click(button)
    await waitFor(() => expect(onCommand).toHaveBeenCalledTimes(1))
  })
  it('executes validated model view actions in order for an explicit request', async () => {
    const onCommand = vi.fn().mockResolvedValue({ ok: true })
    const first = { tool_use_id: 'first', name: 'set_sky_scale', args: { scale: 'local' } }
    const second = { tool_use_id: 'second', name: 'set_year', args: { year: 2080 } }
    const reply = { ...response, message_source: 'ai_generated' }
    vi.stubGlobal('fetch', vi.fn(async (url: string) => url.endsWith('/status') ? Response.json({ enabled: true, provider: 'qfit' }) : stream(event('command', first) + event('command', second) + event('done', { qfit: reply }))))
    render(<QFitAssistant lang="en" context={{}} onCommand={onCommand} autoActions />)
    fireEvent.click(screen.getByRole('button', { name: 'Open the Q-FIT assistant' }))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Show the local sky, then set the year to 2080' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(onCommand.mock.calls.map(([p]) => p.name)).toEqual(['set_sky_scale', 'set_year']))
  })
})

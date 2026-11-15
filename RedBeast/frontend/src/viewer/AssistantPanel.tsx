import { useState } from 'react'
import { useI18n } from '../i18n'
import { buildAssistantContext } from '../lib/assistantContext'
import { COMMANDS, runCommand } from '../lib/commands'
import { useAppState } from '../lib/store'
import type { Mark, Sequence } from '../lib/types'
import type { MotionStar } from '../three/types'

type Proposal = { tool_use_id: string; name: string; args: Record<string, unknown>; requires_confirmation: boolean }
type Message = { role: 'user' | 'assistant'; content: string; sources?: string[]; commands?: Proposal[] }
export function AssistantPanel({ sequence, marks, target }: { sequence: Sequence; marks: Mark[]; target?: MotionStar | null }) {
  const { t, lang } = useI18n(), state = useAppState()
  const [messages, setMessages] = useState<Message[]>([]), [input, setInput] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('')
  async function send(message: string, toolResults?: unknown[]) {
    setBusy(true); setError('')
    const reply: Message = { role: 'assistant', content: '', commands: [], sources: [] }
    const history = messages.slice(-10).map(({ role, content }) => ({ role, content }))
    setMessages(list => [...list, ...(message ? [{ role: 'user' as const, content: message }] : []), reply])
    try {
      const response = await fetch('/api/assistant/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, context: buildAssistantContext(state, { sequence, marks, target }), history, ...(toolResults ? { tool_results: toolResults } : {}) }) })
      if (!response.ok || !response.body) throw new Error(response.status === 503 ? t('assistant.disabled') : `HTTP ${response.status}`)
      const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = ''
      while (true) {
        const { done, value } = await reader.read(); if (done) break
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
        let end: number
        while ((end = buffer.indexOf('\n\n')) >= 0) {
          const block = buffer.slice(0, end); buffer = buffer.slice(end + 2)
          const event = block.match(/^event: (.+)$/m)?.[1], raw = block.match(/^data: (.+)$/m)?.[1]
          if (!raw) continue
          const data = JSON.parse(raw)
          if (event === 'text') reply.content += data.delta
          if (event === 'sources') reply.sources = data
          if (event === 'command') reply.commands?.push(data)
          if (event === 'error') setError(data.message ?? data.code)
          setMessages(list => [...list.slice(0, -1), { ...reply }])
        }
      }
    } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
    finally { setBusy(false) }
  }
  async function execute(command: Proposal) {
    const result = await runCommand(command.name, command.args, { source: 'assistant', confirmed: true, frameCount: sequence.frames.length,
      openSources: () => window.dispatchEvent(new Event('blinkspace:sources')),
      saveView: () => { window.dispatchEvent(new Event('blinkspace:save')) },
      startSearch: request => { window.dispatchEvent(new CustomEvent('blinkspace:search', { detail: request })) },
    })
    await send('', [{ tool_use_id: command.tool_use_id, ok: result.ok, result: { message: result.message ?? 'done' } }])
  }
  return <section className="panel-body assistant-panel">
    <div aria-live="polite">{messages.map((message, index) => <article key={index}>
      {message.role === 'assistant' && <p className="muted small">{t('assistant.generated')}</p>}
      <p className="user-text">{message.content}</p>
      {message.sources?.map(source => <span className="tag" key={source}>{source}</span>)}
      {message.commands?.map(command => { const spec = COMMANDS.find(c => c.name === command.name); return spec && <button className="btn" key={command.tool_use_id} disabled={busy} onClick={() => void execute(command)}>{spec.requiresConfirmation ? t('assistant.confirm') : t('assistant.run')}: {spec.description[lang]}</button> })}
    </article>)}</div>
    {error && <p role="alert" className="notice notice-error">{error}</p>}
    <form onSubmit={e => { e.preventDefault(); if (input.trim() && !busy) { void send(input.trim()); setInput('') } }}>
      <label className="field">{t('assistant.message')}<textarea value={input} maxLength={2000} onChange={e => setInput(e.target.value)} disabled={busy} /></label>
      <button className="btn" disabled={busy || !input.trim()}>{t('assistant.send')}</button>
    </form>
  </section>
}

/** Q-FIT mascot transport adapted to BlinkSpace's same-origin SSE contract. */
import { COMMANDS, validateArgs } from '../lib/commands'
export interface Proposal { tool_use_id: string; name: string; args: Record<string, unknown>; requires_confirmation: boolean }
export interface QFitResponse {
  success: boolean; assistant: 'Q-FIT'; intent: string; message: string; message_source: 'system' | 'ai_generated'
  data: { fallback?: { active: boolean }; spherex_available?: boolean; tool_errors?: unknown[]; [key: string]: unknown }
  sources: { id?: string; name?: string; url?: string; citation_labels?: string[] }[]; uncertainty: string[]; commands?: Proposal[]
  media?: unknown[]; error?: { message: string }; meta?: { ai_model?: string | null }; actions?: unknown[]
}
export interface ToolResult { tool_use_id: string; ok: boolean; result: Record<string, unknown> }
export interface ChatTurn { role: 'user' | 'assistant'; content: string }
export type ChatContext = Record<string, unknown>
export interface AssistantStatus { enabled: boolean; provider: string | null; model?: string; reason?: string }
export async function getAssistantStatus(signal?: AbortSignal): Promise<AssistantStatus> {
  const response = await fetch('/api/assistant/status', { signal, cache: 'no-store' })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}
export function safeSource(url?: string): boolean {
  if (!url) return false
  try { const parsed = new URL(url, window.location.origin); return ['https:', 'http:'].includes(parsed.protocol) && !parsed.username && !parsed.password } catch { return false }
}
export function checkedProposal(value: unknown): Proposal | null {
  if (!value || typeof value !== 'object') return null
  const p = value as Proposal, spec = COMMANDS.find(c => c.name === p.name)
  return spec && typeof p.tool_use_id === 'string' && /^[\w-]{1,80}$/.test(p.tool_use_id) && validateArgs(spec.schema, p.args)
    ? { ...p, requires_confirmation: spec.requiresConfirmation } : null
}
export async function readStream(response: Response, signal?: AbortSignal): Promise<QFitResponse> {
  if (!response.body) throw new Error('Empty assistant response')
  const reader = response.body.getReader(), decoder = new TextDecoder()
  let buffer = '', message = '', ended = false, result: QFitResponse | undefined
  const commands: Proposal[] = [], sources: QFitResponse['sources'] = []
  try {
    while (!ended) {
      signal?.throwIfAborted()
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let end: number
      while ((end = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, end); buffer = buffer.slice(end + 2)
        const name = block.match(/^event: (.+)$/m)?.[1], raw = block.match(/^data: (.+)$/m)?.[1]
        if (!raw) continue
        const data = JSON.parse(raw)
        if (name === 'text') message += String(data.delta ?? '')
        if (name === 'command') { const proposal = checkedProposal(data); if (!proposal) throw new Error('Invalid assistant command'); commands.push(proposal) }
        if (name === 'sources' && Array.isArray(data)) data.forEach(id => { if (typeof id === 'string') sources.push({ id, name: id, url: `/api/assistant/sources/${encodeURIComponent(id)}` }) })
        if (name === 'done') { result = data.qfit; ended = true }
      }
    }
    if (!ended) throw new Error('Interrupted assistant response')
    return result ? { ...result, commands } : { success: true, assistant: 'Q-FIT', message, intent: 'mock', message_source: 'system', data: {}, sources, uncertainty: [], commands }
  } finally { await reader.cancel().catch(() => undefined); reader.releaseLock() }
}
export async function askQFit(message: string, history: ChatTurn[], context: ChatContext, signal?: AbortSignal, toolResults: ToolResult[] = []): Promise<QFitResponse> {
  const status = await getAssistantStatus(signal)
  const response = await fetch(status.enabled ? '/api/assistant/chat' : '/api/assistant/knowledge', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
    body: JSON.stringify({ message, history: history.slice(-10).map(h => ({ ...h, content: h.content.slice(0, 4000) })), context, tool_results: toolResults.slice(-10) }),
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return status.enabled ? readStream(response, signal) : response.json()
}

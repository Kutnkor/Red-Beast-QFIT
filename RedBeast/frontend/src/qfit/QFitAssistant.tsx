/** Adapted from Q-FIT's MIT mascot. Original bird sprites and beak-pull motion retained. */
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { askQFit, checkedProposal, getAssistantStatus, safeSource, type AssistantStatus, type ChatContext, type ChatTurn, type Proposal, type QFitResponse, type ToolResult } from './api'
import { COMMANDS } from '../lib/commands'
import { isActionRequest, type ActionExecutor } from './actions'
import type { LocalReply } from './localIntent'
import robinIcon from './assets/robin-64.png'
import './qfit-assistant.css'
export type MascotState = 'idle' | 'thinking' | 'speaking' | 'found' | 'quiet'
interface Message { id: number; who: 'user' | 'bot'; text: string; response?: QFitResponse; pin?: { label: string; text: string } }
interface Shortcut { label: string; text: string }
const read = <T,>(key: string, fallback: T): T => { try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) as T : fallback } catch { return fallback } }
const write = (key: string, value: unknown) => { try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* private mode: nothing is kept */ } }
const TEXT = {
  tr: { open: 'Q-FIT asistanını aç', close: 'Kapat', sub: 'SPHEREx araştırma asistanı', placeholder: 'Bu yıldızda ne görüyorum?', send: 'Gönder', stop: 'Durdur', retry: 'Yeniden dene',
    hello: 'Merhaba, ben Q-FIT. Seçtiğin yıldızın kaynaklarını ve modelin sınırlarını birlikte inceleyebiliriz.', caveats: 'Belirsizlikler', sources: 'Kaynaklar', ai: 'Yapay zekâ açıklaması',
    local: 'Yerel kaynak kartı · AI kapalı', sourceCard: 'Yerel kaynak kartı', ready: 'AI bağlantısı yapılandırılmış', checking: 'Bağlantı kontrol ediliyor', network: 'Asistana ulaşılamadı. Yeniden deneyebilirsin.', stopped: 'Yanıt durduruldu.',
    run: 'Uygula', confirm: 'Onayla ve çalıştır', applied: 'Uygulandı', failed: 'İşlem tamamlanmadı', reading: 'Kaynakları inceliyor…', clear: 'Sohbeti temizle',
    pin: 'Kısayol yap', pinned: 'Kısayol eklendi', shortcuts: 'Kısayollar', remove: 'Kısayolu kaldır', did: 'Uygulamada yapıldı' },
  en: { open: 'Open the Q-FIT assistant', close: 'Close', sub: 'SPHEREx research assistant', placeholder: 'What am I seeing in this star?', send: 'Send', stop: 'Stop', retry: 'Retry',
    hello: 'Hi, I am Q-FIT. We can explore the selected star’s sources and the limits of its model.', caveats: 'Caveats', sources: 'Sources', ai: 'AI explanation',
    local: 'Local source card · AI off', sourceCard: 'Local source card', ready: 'AI connection configured', checking: 'Checking connection', network: 'The assistant could not be reached. You can retry.', stopped: 'Response stopped.',
    run: 'Apply', confirm: 'Confirm and run', applied: 'Applied', failed: 'Action did not complete', reading: 'Reading sources…', clear: 'Clear chat',
    pin: 'Make shortcut', pinned: 'Shortcut added', shortcuts: 'Shortcuts', remove: 'Remove shortcut', did: 'Done in the app' },
}
function settleState(r: QFitResponse): MascotState {
  if (!r.success || r.message_source === 'system' || r.intent === 'error') return 'quiet'
  return r.data.spherex_available || r.media?.length ? 'found' : 'idle'
}
function Rich({ text }: { text: string }) {
  return <>{text.split(/(\*\*[^*]+\*\*)/g).map((p, i) => p.startsWith('**') && p.endsWith('**') ? <strong key={i}>{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>)}</>
}
export function QFitAssistant({ lang, context, onCommand, local, remember, autoActions }: { lang: 'tr' | 'en'; context: ChatContext | (() => ChatContext); onCommand: ActionExecutor
  /** Requests the app can carry out by itself (navigation); tried before the sourced assistant. */
  local?: (text: string, lang: 'tr' | 'en') => LocalReply | null
  /** Keep shortcuts and the last messages in this browser. */
  remember?: boolean
  autoActions?: boolean }) {
  const t = TEXT[lang], [open, setOpenState] = useState(false), [motion, setMotion] = useState<'opening' | 'closing' | null>(null)
  const [state, setState] = useState<MascotState>('idle'), [busy, setBusy] = useState(false), [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>(() => remember ? read<Message[]>('rb.chat', []).map((m, i) => ({ id: i + 1, who: m.who, text: m.text })) : []), [status, setStatus] = useState<AssistantStatus | null>(null)
  const [shortcuts, setShortcuts] = useState<Shortcut[]>(() => remember ? read<Shortcut[]>('rb.shortcuts', []) : [])
  useEffect(() => { if (remember) write('rb.chat', messages.slice(-24).map(m => ({ who: m.who, text: m.text }))) }, [messages, remember])
  useEffect(() => { if (remember) write('rb.shortcuts', shortcuts) }, [shortcuts, remember])
  const [error, setError] = useState(''), [last, setLast] = useState(''), [executed, setExecuted] = useState<Record<string, string>>({})
  const history = useRef<ChatTurn[]>([]), timer = useRef<number | undefined>(undefined), abort = useRef<AbortController | null>(null)
  const openRef = useRef(false), logRef = useRef<HTMLDivElement>(null), inputRef = useRef<HTMLTextAreaElement>(null), panelRef = useRef<HTMLElement>(null)
  const pendingResults = useRef<ToolResult[]>([])
  const counter = useRef(messages.length), mascotRef = useRef<HTMLButtonElement>(null)
  const setOpen = useCallback((value: boolean) => {
    if (value === openRef.current) return
    openRef.current = value
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    window.clearTimeout(timer.current); setMotion(reduced ? null : value ? 'opening' : 'closing'); setOpenState(value)
    timer.current = window.setTimeout(() => { setMotion(null); if (value) inputRef.current?.focus(); else mascotRef.current?.focus() }, reduced ? 0 : 780)
  }, [])
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    getAssistantStatus(controller.signal).then(setStatus).catch(() => undefined)
    return () => controller.abort()
  }, [open])
  useEffect(() => () => { abort.current?.abort(); window.clearTimeout(timer.current) }, [])
  useEffect(() => { panelRef.current?.querySelectorAll<HTMLElement>('.qf-head, .qf-log, .qf-form, .qf-status, .qf-feedback').forEach(el => { el.inert = !open }) }, [open, busy, messages, error])
  useEffect(() => { logRef.current?.scrollTo?.({ top: logRef.current.scrollHeight }) }, [messages, busy])
  useEffect(() => {
    const toggle = () => setOpen(!openRef.current)
    const keys = (e: KeyboardEvent) => { if (e.key === 'Escape' && openRef.current) { e.preventDefault(); setOpen(false) } }
    window.addEventListener('blinkspace:assistant', toggle); document.addEventListener('keydown', keys)
    return () => { window.removeEventListener('blinkspace:assistant', toggle); document.removeEventListener('keydown', keys) }
  }, [setOpen])
  async function send(text: string) {
    if (!text.trim() || busy) return
    const controller = new AbortController(); abort.current = controller
    setInput(''); setLast(text); setError(''); setBusy(true); setState('thinking')
    setMessages(m => [...m, { id: ++counter.current, who: 'user', text }])
    try {
      const hit = local?.(text, lang)
      if (hit) {
        const result = await hit.run?.(controller.signal)
        controller.signal.throwIfAborted()
        const body = result?.message ?? [hit.message, ...(hit.facts ?? []).map(f => `**${f.label}:** ${f.value}${f.note ? ` — ${f.note}` : ''}`), ...(hit.note ? [hit.note] : [])].join('\n')
        setMessages(m => [...m, { id: ++counter.current, who: 'bot', text: body, response: result?.response, pin: hit.run ? hit.pin : undefined }])
        history.current = [...history.current, { role: 'user' as const, content: text }, { role: 'assistant' as const, content: body }].slice(-10)
        setState(result?.failed ? 'quiet' : hit.run ? 'found' : 'idle')
        return
      }
      const response = await askQFit(text, history.current, typeof context === 'function' ? context() : context, controller.signal, pendingResults.current, status ?? undefined)
      pendingResults.current = []
      controller.signal.throwIfAborted()
      const id = ++counter.current, full = response.message
      setMessages(m => [...m, { id, who: 'bot', text: '', response }]); setState('speaking')
      if (autoActions && response.success && response.intent !== 'mock' && isActionRequest(text)) {
        for (const [i, value] of (response.commands ?? []).entries()) {
          const proposal = checkedProposal(value)
          if (!proposal || proposal.requires_confirmation) break
          controller.signal.throwIfAborted()
          if (!await apply(proposal, `${id}-${i}`, controller.signal)) break
        }
      }
      const instant = response.message_source === 'system' || window.matchMedia('(prefers-reduced-motion: reduce)').matches
      const step = Math.max(12, Math.ceil(full.length / 60))
      for (let n = instant ? full.length : step; n < full.length; n += step) {
        controller.signal.throwIfAborted()
        setMessages(m => m.map(row => row.id === id ? { ...row, text: full.slice(0, n) } : row))
        await new Promise(resolve => window.setTimeout(resolve, 20))
      }
      controller.signal.throwIfAborted()
      setMessages(m => m.map(row => row.id === id ? { ...row, text: full } : row))
      history.current = [...history.current, { role: 'user' as const, content: text }, { role: 'assistant' as const, content: full }].slice(-10)
      setState(settleState(response))
    } catch { setError(controller.signal.aborted ? t.stopped : t.network); setState('quiet') }
    finally { setBusy(false); abort.current = null }
  }
  async function apply(value: Proposal, key: string, signal?: AbortSignal) {
    const p = checkedProposal(value)
    if (!p) return false
    setExecuted(s => ({ ...s, [key]: '…' }))
    try {
      const result = await onCommand(p, signal)
      pendingResults.current.push({ tool_use_id: p.tool_use_id, ok: result.ok, result: { message: (result.message ?? (result.ok ? 'Client reports action accepted' : 'Client reports action failed')).slice(0, 256) } })
      setExecuted(s => ({ ...s, [key]: result.ok ? t.applied : t.failed }))
      return result.ok
    } catch {
      setExecuted(s => ({ ...s, [key]: t.failed }))
      return false
    }
  }
  const submit = (e: FormEvent) => { e.preventDefault(); void send(input.trim()) }
  return <div className="qf-root" data-corner="bottom-right" data-open={open} data-motion={motion ?? undefined} data-ui="qfit">
    <button ref={mascotRef} className="qf-mascot" type="button" data-state={state} aria-label={t.open} aria-expanded={open} onClick={() => setOpen(!open)}>
      <span className="qf-art"><span className="qf-sprite" /><span className="qf-glow" /><span className="qf-twinkle" /><span className="qf-burst" /></span><span className="qf-badge" aria-hidden="true" />
    </button>
    <aside className="qf-panel" role="dialog" aria-label="Q-FIT" aria-hidden={!open} ref={panelRef}>
      <button className="qf-handle" type="button" tabIndex={-1} aria-hidden="true" onClick={() => setOpen(!open)} />
      <header className="qf-head"><img src={robinIcon} alt="" /><div><div className="qf-title">Q-FIT</div><div className="qf-sub">{t.sub}</div></div><button className="qf-close" type="button" aria-label={t.close} onClick={() => setOpen(false)}>×</button></header>
      <p className="qf-status">{status === null ? t.checking : status.enabled ? (status.provider === 'mock' ? 'Mock · local' : `${t.ready} · ${status.model ?? 'Q-FIT'}`) : t.local}</p>
      <div className="qf-log" ref={logRef} role="log" aria-live="polite" aria-busy={busy}>
        <div className="qf-msg bot">{t.hello}</div>
        {messages.map(m => <div key={m.id} className={`qf-msg ${m.who}${m.response?.message_source === 'system' ? ' system' : ''}`}>
          <Rich text={m.text} />
          {m.pin && <p className="qf-note qf-did">{t.did}{shortcuts.some(x => x.text === m.pin!.text) ? <> · {t.pinned}</> : <> · <button type="button" className="qf-pin" onClick={() => setShortcuts(list => [...list.filter(x => x.text !== m.pin!.text), m.pin!].slice(-6))}>{t.pin}</button></>}</p>}
          {m.response && <><p className="qf-note">{m.response.message_source === 'ai_generated' ? t.ai : t.sourceCard}</p>
            {!!m.response.uncertainty?.length && <details><summary>{t.caveats}</summary><ul>{m.response.uncertainty.map((u, i) => <li key={i}>{u}</li>)}</ul></details>}
            {!!m.response.sources?.length && <details><summary>{t.sources}</summary><ul>{m.response.sources.filter(s => safeSource(s.url)).map((s, i) => <li key={i}><a href={s.url} target="_blank" rel="noopener noreferrer">{s.citation_labels?.length ? `[${s.citation_labels.join(', ')}] ` : ''}{s.name ?? s.id ?? s.url}</a></li>)}</ul></details>}
            {m.response.commands?.map((p, i) => { const spec = COMMANDS.find(c => c.name === p.name), key = `${m.id}-${i}`; return spec && <button className="qf-command" key={key} disabled={busy || Boolean(executed[key])} onClick={() => void apply(p, key)}>{executed[key] ?? `${spec.requiresConfirmation ? t.confirm : t.run}: ${spec.description[lang]}`}</button> })}
          </>}
        </div>)}
        {busy && <p className="qf-note">{t.reading}</p>}
      </div>
      <div className="qf-feedback">{error && <p role="status">{error}</p>}{error && last && !busy && <button type="button" onClick={() => void send(last)}>{t.retry}</button>}<button type="button" disabled={busy} onClick={() => { setMessages([]); history.current = []; pendingResults.current = []; setExecuted({}); setError('') }}>{t.clear}</button></div>
      {shortcuts.length > 0 && <div className="qf-shortcuts" role="group" aria-label={t.shortcuts}>{shortcuts.map(s => <span key={s.text} className="qf-shortcut"><button type="button" disabled={busy} onClick={() => void send(s.text)}>{s.label}</button><button type="button" className="qf-shortcut-x" aria-label={`${t.remove}: ${s.label}`} onClick={() => setShortcuts(list => list.filter(x => x.text !== s.text))}>×</button></span>)}</div>}
      <form className="qf-form" onSubmit={submit}><textarea ref={inputRef} className="qf-input" rows={2} maxLength={2000} aria-label={t.placeholder} placeholder={t.placeholder} value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(input.trim()) } }} />
        {busy ? <button className="qf-send" type="button" onClick={() => abort.current?.abort()}>{t.stop}</button> : <button className="qf-send" type="submit" disabled={!input.trim()}>{t.send}</button>}
      </form>
    </aside>
  </div>
}

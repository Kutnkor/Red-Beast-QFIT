import { COMMANDS, type CommandResult } from '../lib/commands'
import { getAppState } from '../lib/store'
import { askQFit, type Proposal } from './api'
import type { LocalReply } from './localIntent'
import { findStar, plain, type Named } from './match'

export type ActionExecutor = (proposal: Proposal, signal?: AbortSignal) => Promise<CommandResult>
type Local = (text: string, lang: 'tr' | 'en') => LocalReply | null
type Step = { name: string; args: Record<string, unknown> } | { local: LocalReply } | { evidence: true }
const command = (name: string, args: Record<string, unknown> = {}): Step => ({ name, args })
const request = /^(?:(?:please|can you|could you|would you|i want you to|i'd like you to|let's) )*(?:take|go|show|open|bring|fly|zoom|visit|compare|start|switch|stop|pause|resume|play|set|enable|disable|turn|put|use|focus|centre|center|navigate|find|search|download|save|display|load|view)\b/
const turkishRequest = /\b(?:gotur|git|goster|ac|kapat|durdur|duraklat|oynat|baslat|gec|koy|karsilastir|ayarla|odaklan|ara|indir|kaydet|devam et|gizle)(?:ur musun|ir misin|abilir misin)?[.!?]*$/
export function isActionRequest(text: string): boolean {
  const q = plain(text).replace(/^lutfen\s+/, '')
  return request.test(q) || turkishRequest.test(q)
}
const split = /\s*(?:[;\n]+|,\s*(?=(?:then|and then|after that|ardindan|sonra)\b)|(?:\s+(?:and then|then|after that|ardindan|sonra)\s+)|\s+(?:and|ve)\s+(?=(?:show|open|take|go|set|start|play|pause|stop|enable|disable|turn|switch)\b)|,\s+)\s*/
const firstLast = /\b(?:first and (?:the )?last|first to (?:the )?last|earliest and (?:the )?latest|ilk ve son|ilk kareyle son|ilk ile son)\b/
const evidence = /\b(?:show (?:me )?(?:the )?(?:measurement )?evidence|kanit\w* (?:goster|ac)|olcum\w* (?:goster|ac))\b/
const comparisons = [
  ['trackstack', /\b(?:co.moving|track.?stack|hareket.?hizali|hedefle hizali)\b/],
  ['timestack', /\b(?:3d (?:time )?stack|time stack|3b zaman yigini|zaman yigini)\b/],
  ['diff', /\b(?:difference(?: image| view)?|fark(?:i|ini| gorunumu)?)\b/],
  ['side', /\b(?:side[ -]by[ -]side|yan yana)\b/],
  ['blink', /\b(?:blink\w*|kirpistir\w*)\b/],
  ['stack', /\b(?:stack|yigin\w*)\b/],
] as const
const layers = [
  ['predicted', /\b(?:predicted (?:position|track|motion)|tahmini (?:konum|hareket)|ongorulen konum)\b/],
  ['gaia', /\bgaia\b/],
  ['allwise', /\b(?:allwise|all wise)\b/],
] as const

export function createActionAssistant(local: Local, getCatalogue: () => Named[], execute: ActionExecutor): Local {
  return (text, lang) => {
    const tr = lang === 'tr'
    const q = plain(text)
    const clauses = q.split(split).map(part => part.replace(/^(?:and then|then|after that|and|ve|ardindan|sonra)\s+/, '')).filter(Boolean)
    const steps: Step[] = []
    if (clauses.length === 1 && !isActionRequest(q)) return local(text, lang)
    if (clauses.length > 6 || !isActionRequest(clauses[0] ?? '')) return null

    for (const clause of clauses) {
      const direct = isActionRequest(clause)
      const proof = evidence.test(clause)
      const pair = firstLast.test(clause)
      const layer = layers.find(([, pattern]) => pattern.test(clause))?.[0]
      const off = /\b(?:disable|hide|off|kapat|gizle)\b/.test(clause)
      const overlay = layer && direct && (off || /\b(?:layer|overlay|predicted|katman\w*|tahmini|ongorulen)\b/.test(clause))
      const view = comparisons.find(([, pattern]) => pattern.test(clause))?.[0]
      const year = direct && /\b(?:year|yil\w*)\b/.test(clause) ? /\b(20\d\d|2100)\b/.exec(clause) : null
      if (/^(?:pause|stop|resume|play)(?:\s+(?:(?:the )?animation|(?:the )?blink(?:ing)?|playback))?[.!?]*$|^(?:(?:oynatmayi )?duraklat|durdur|devam et|oynat)[.!?]*$/.test(clause)) {
        steps.push(command('set_playback', { playing: /^(?:resume|play|devam|oynat)\b/.test(clause) && clause !== 'oynatmayi duraklat' }))
      } else if (proof || ((direct || pair) && (view || pair) && !overlay)) {
        const target = findStar(clause, getCatalogue())
        if (target) steps.push(command('open_target', { target_id: target.id, page: 'observations' }))
        steps.push(command('show_observations', { view: proof ? 'side' : (view ?? 'side'), pair: proof || pair ? 'first_last' : 'current' }))
        if (proof) {
          steps.push(command('toggle_layer', { layer: 'predicted', on: true }))
          steps.push({ evidence: true })
        }
      } else if (overlay) {
        steps.push(command('toggle_layer', { layer, on: !off }))
      } else if (year) {
        steps.push(command('set_year', { year: Number(year[1]) }))
      } else if (/^(?:open|show) (?:the )?(?:archive |star |coordinate )?search\b|\barama(?:yi| panelini)? ac\b/.test(clause)) {
        steps.push(command('open_search'))
      } else {
        const existing = local(clauses.length === 1 ? text : clause, lang)
        if (clauses.length === 1) return existing
        if (!existing?.run) return null
        steps.push({ local: existing })
      }
    }

    const fallback = tr ? 'İstenen adımı tamamlayamadım.' : 'I could not complete the requested step.'
    return { message: '', async run(signal) {
      const completed: string[] = []
      let evidenceTarget: string | null | undefined
      for (const [i, step] of steps.entries()) {
        signal?.throwIfAborted()
        if ('evidence' in step) {
          evidenceTarget = getAppState().targetId
          continue
        }
        if ('local' in step) {
          await step.local.run?.(signal)
          completed.push(step.local.message)
          continue
        }
        const label = COMMANDS.find(c => c.name === step.name)?.description[lang] ?? step.name
        const result = await execute({ tool_use_id: `qfit_local_${i + 1}`, ...step, requires_confirmation: false }, signal)
        signal?.throwIfAborted()
        if (!result.ok) {
          const noFrames = result.message === 'Not enough observation frames'
          const why = noFrames ? (tr ? 'Bu hedefte bu işlem için yeterli hazır kare yok.' : 'This target does not have enough prepared frames for this view.') : fallback
          return { failed: true, message: [...completed, why].join('\n') }
        }
        completed.push(label)
      }
      const message = tr ? 'İstenen adımları uyguladım.' : 'I applied the requested steps.'
      if (evidenceTarget === undefined) return { message: [message, ...completed].join('\n') }
      try {
        const response = await askQFit('What did you measure?', [], { ui_language: lang, target: { id: evidenceTarget } }, signal, [], { enabled: false, provider: null })
        signal?.throwIfAborted()
        if (response.intent === 'measurement') {
          return { message: (tr ? 'İlk ve son kareyi yan yana açtım.\n\n' : 'I opened the first and last frames side by side.\n\n') + response.message, response }
        }
      } catch (error) {
        if (signal?.aborted) throw error
      }
      return { message: tr ? 'Kareleri açtım. Bu hedefin ölçüm raporunu getiremedim.' : 'I opened the frames. I could not retrieve a measurement report for this target.' }
    } }
  }
}

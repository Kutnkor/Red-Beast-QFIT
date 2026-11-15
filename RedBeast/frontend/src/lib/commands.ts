import { getAppState, setAppState, type AppMode, type AppState, type DrawerTab } from './store'
import { suggestedTrack } from '../three/science/evolution'
import type { Bilingual, SearchRequest } from './types'

type Property = { type: 'string' | 'number' | 'boolean'; enum?: readonly unknown[]; minimum?: number; maximum?: number; integer?: boolean }
export interface JSONSchema { type: 'object'; properties: Record<string, Property>; required: string[]; additionalProperties: false }
export interface CommandResult { ok: boolean; message?: string }
export interface CommandContext {
  source?: 'user' | 'assistant' | 'url'
  confirmed?: boolean
  frameCount?: number
  openSources?: () => void
  startSearch?: (request: SearchRequest) => void | Promise<void>
  saveView?: () => void | Promise<void>
  explainValue?: (field: string) => string
}
export interface CommandSpec<A = Record<string, unknown>> {
  name: string
  description: Bilingual
  schema: JSONSchema
  requiresConfirmation: boolean
  run: (args: A, ctx: CommandContext) => Promise<CommandResult>
}
const string = (values?: readonly string[]): Property => ({ type: 'string', ...(values ? { enum: values } : {}) })
const number = (min: number, max: number, integer = false): Property => ({ type: 'number', minimum: min, maximum: max, integer })
function spec(name: string, en: string, tr: string, properties: Record<string, Property>, action: (args: Record<string, unknown>, ctx: CommandContext) => void | string | Promise<void | string>, confirm = false): CommandSpec {
  return { name, description: { en, tr }, schema: { type: 'object', properties, required: Object.keys(properties), additionalProperties: false }, requiresConfirmation: confirm,
    async run(args, ctx) { const message = await action(args, ctx); return { ok: true, ...(message ? { message } : {}) } },
  }
}
export const COMMANDS: CommandSpec[] = [
  spec('select_target', 'Select a catalogue target', 'Katalog hedefini seç', { target_id: string() }, a => setAppState({ targetId: a.target_id as string, evolutionTrack:suggestedTrack(a.target_id as string), evolutionProgress:0, sequenceId: null, frameIndex: 0, refIndex: 0, playing: false, evolutionPlaying: false })),
  spec('set_mode', 'Change the scene', 'Sahneyi değiştir', { mode: string(['star', 'neighbors', 'observations']) }, a => setAppState({ mode: a.mode as AppMode, playing: false, evolutionPlaying: false })),
  spec('set_year', 'Set the model year', 'Model yılını ayarla', { year: number(2000, 2100) }, a => setAppState({ year: a.year as number })),
  spec('set_frame', 'Select an observation frame', 'Gözlem karesini seç', { index: number(0, 10000, true) }, (a, ctx) => {
    if (ctx.frameCount !== undefined && (a.index as number) >= ctx.frameCount) throw new Error('Frame index outside sequence')
    setAppState({ frameIndex: a.index as number })
  }),
  spec('set_view_mode', 'Change image comparison', 'Görüntü karşılaştırmasını değiştir', { view: string(['single', 'side', 'diff', 'stack', 'trackstack']) }, a => setAppState({ viewMode: a.view as AppState['viewMode'], playing: false })),
  spec('set_stage_view', 'Choose frames or time stack', 'Kareleri veya zaman yığınını seç', { view: string(['frames', 'timestack']) }, a => setAppState({ stageView: a.view as AppState['stageView'], playing: false })),
  spec('toggle_layer', 'Set a display layer', 'Görsel katmanı ayarla', { layer: string(['environment', 'trail', 'grid', 'sky', 'gaia', 'allwise', 'predicted']), on: { type: 'boolean' } }, a => setAppState(s => ({ layers: { ...s.layers, [a.layer as string]: a.on } }))),
  spec('open_drawer_tab', 'Open an analysis panel', 'Analiz panelini aç', { tab: string(['frame', 'layers', 'marks', 'curve', 'wave', 'task', 'assistant']) }, a => setAppState({ drawer: { open: true, tab: a.tab as DrawerTab } })),
  spec('open_sources', 'Show sources and limits', 'Kaynakları ve sınırları göster', {}, (_, ctx) => ctx.openSources?.()),
  spec('start_search', 'Search real IRSA observations', 'Gerçek IRSA gözlemlerini ara', { ra: string(), dec: string(), ra_unit: string(['auto', 'deg', 'hour']), fov_arcmin: number(2, 30) }, async (a, ctx) => {
    if (!ctx.startSearch) throw new Error('Search is unavailable')
    await ctx.startSearch(a as unknown as SearchRequest)
  }, true),
  spec('save_view', 'Download this view as JSON', 'Bu görünümü JSON olarak indir', {}, async (_, ctx) => {
    if (!ctx.saveView) throw new Error('Download is unavailable')
    await ctx.saveView()
  }, true),
  spec('explain_value', 'Explain a value and its source', 'Bir değeri ve kaynağını açıkla', { field: string(['distance', 'parallax', 'proper_motion', 'radial_velocity', 'teff', 'position', 'surface']) }, (a, ctx) => ctx.explainValue?.(a.field as string) ?? 'Source information is unavailable.'),
]

export function validateArgs(schema: JSONSchema, args: unknown): args is Record<string, unknown> {
  if (!args || typeof args !== 'object' || Array.isArray(args)) return false
  const value = args as Record<string, unknown>
  if (Object.keys(value).some(k => !Object.hasOwn(schema.properties, k)) || schema.required.some(k => !Object.hasOwn(value, k))) return false
  return Object.entries(value).every(([key, v]) => {
    const rule = schema.properties[key]
    if (typeof v !== rule.type || (rule.enum && !rule.enum.includes(v))) return false
    if (typeof v === 'number' && (!Number.isFinite(v) || (rule.minimum !== undefined && v < rule.minimum) || (rule.maximum !== undefined && v > rule.maximum) || (rule.integer && !Number.isInteger(v)))) return false
    return typeof v !== 'string' || (v.length > 0 && v.length <= 256)
  })
}
export async function runCommand(name: string, args: unknown, ctx: CommandContext = {}): Promise<CommandResult> {
  const command = COMMANDS.find(item => item.name === name)
  if (!command || !validateArgs(command.schema, args)) return { ok: false, message: 'Invalid command or arguments' }
  if (command.requiresConfirmation && ctx.source !== 'user' && ctx.confirmed !== true) return { ok: false, message: 'Confirmation required' }
  try { return await command.run(args, ctx) } catch (error) { return { ok: false, message: error instanceof Error ? error.message : String(error) } }
}
export function stepYear(delta: number): void { void runCommand('set_year', { year: Math.max(2000, Math.min(2100, getAppState().year + delta)) }, { source: 'user' }) }

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
  getFrameCount?: () => Promise<number>
  selectTarget?: (id: string) => void
  openSearch?: () => void
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
const selectTarget = (id: string) => setAppState({ targetId: id, evolutionTrack: suggestedTrack(id), evolutionProgress: 0, sequenceId: null, frameIndex: 0, refIndex: 0, playing: false, evolutionPlaying: false })

/** A star's own pages. "star" is its menu: the 3D star with its catalogue values around it. */
export type TargetPage = 'star' | 'sky' | 'observations' | 'evolution'
export const TARGET_PAGES = ['star', 'sky', 'observations', 'evolution'] as const
const PAGE_STATE: Record<TargetPage, Partial<AppState>> = {
  star: { mode: 'star', stellarMode: 'surface', sceneFraming: 'detail' },
  sky: { mode: 'neighbors', skyScale: 'local' },
  observations: { mode: 'observations', stageView: 'frames', viewMode: 'single' },
  evolution: { mode: 'star', stellarMode: 'evolution' },
}
/** Select a star and land on one of its pages in one step, so the scene makes a single transition. */
export function openTarget(id: string, page: TargetPage, select: (id: string) => void = selectTarget): void {
  if (getAppState().targetId !== id) select(id)
  setAppState({ ...PAGE_STATE[page], playing: false, evolutionPlaying: false })
  // the sky scene needs a moment to exist before it can turn towards the star
  if (page === 'sky') window.setTimeout(() => window.dispatchEvent(new CustomEvent('blinkspace:camera', { detail: { action: 'focus' } })), 120)
}

const observationViews = ['single', 'side', 'diff', 'stack', 'trackstack', 'timestack', 'blink'] as const
async function observationCount(ctx: CommandContext) {
  return ctx.getFrameCount ? ctx.getFrameCount() : (ctx.frameCount ?? 0)
}

export const COMMANDS: CommandSpec[] = [
  spec('select_target', 'Select a catalogue target', 'Katalog hedefini seç', { target_id: string() }, (a, ctx) => (ctx.selectTarget ?? selectTarget)(a.target_id as string)),
  spec('set_mode', 'Change the scene', 'Sahneyi değiştir', { mode: string(['star', 'neighbors', 'observations']) }, a => setAppState({ mode: a.mode as AppMode, playing: false, evolutionPlaying: false })),
  spec('set_year', 'Set the model year', 'Model yılını ayarla', { year: number(2000, 2100) }, a => setAppState({ year: a.year as number })),
  spec('set_frame', 'Select an observation frame', 'Gözlem karesini seç', { index: number(0, 10000, true) }, async (a, ctx) => {
    const count = ctx.getFrameCount ? await ctx.getFrameCount() : ctx.frameCount
    if (count !== undefined && (a.index as number) >= count) throw new Error('Frame index outside sequence')
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
  spec('open_target', 'Go to a star', 'Bir yıldıza git', { target_id: string(), page: string(TARGET_PAGES) }, (a, ctx) => openTarget(a.target_id as string, a.page as TargetPage, ctx.selectTarget)),
  spec('set_stellar_mode', 'Choose the star view', 'Yıldız görünümünü seç', { mode: string(['surface', 'evolution', 'education']) }, a => setAppState({ mode: 'star', stellarMode: a.mode as AppState['stellarMode'], playing: false, evolutionPlaying: false })),
  spec('set_sky_scale', 'Choose the sky scale', 'Gökyüzü ölçeğini seç', { scale: string(['galaxy', 'local']) }, a => setAppState({ mode: 'neighbors', skyScale: a.scale as AppState['skyScale'], playing: false })),
  spec('explain_value', 'Explain a value and its source', 'Bir değeri ve kaynağını açıkla', { field: string(['distance', 'parallax', 'proper_motion', 'radial_velocity', 'teff', 'position', 'surface']) }, (a, ctx) => ctx.explainValue?.(a.field as string) ?? 'Source information is unavailable.'),
  spec('show_observations', 'Open and compare observations', 'Gözlemleri aç ve karşılaştır',
    { view: string(observationViews), pair: string(['current', 'first_last']) }, async (a, ctx) => {
      const count = await observationCount(ctx)
      if (!count || ((a.pair === 'first_last' || a.view !== 'single') && count < 2)) throw new Error('Not enough observation frames')
      const state = getAppState()
      const viewMode = a.view === 'timestack' || a.view === 'blink' ? 'single' : a.view as AppState['viewMode']
      const comparing = viewMode === 'side' || viewMode === 'diff'
      const indices = a.pair === 'first_last' ? { refIndex: 0, frameIndex: count - 1 }
        : comparing && state.frameIndex === state.refIndex ? { frameIndex: (state.refIndex + 1) % count } : {}
      setAppState({ mode: 'observations', stageView: a.view === 'timestack' ? 'timestack' : 'frames', viewMode, playing: a.view === 'blink', ...indices })
    }),
  spec('set_observation_pair', 'Compare two specific observation frames', 'İki belirli gözlem karesini karşılaştır',
    { sequence_id: string(), a: number(0, 10000, true), b: number(0, 10000, true) }, async (args, ctx) => {
      const a = args.a as number, b = args.b as number
      const count = await observationCount(ctx)
      if (a === b || a >= count || b >= count) throw new Error('Invalid observation pair')
      setAppState({ mode: 'observations', stageView: 'frames', viewMode: 'side', refIndex: a, frameIndex: b, playing: false })
    }),
  spec('set_playback', 'Play or pause the current view', 'Görünümü oynat veya duraklat', { playing: { type: 'boolean' } }, async (a, ctx) => {
    const state = getAppState(), playing = a.playing === true
    if (!playing) { setAppState({ playing: false, evolutionPlaying: false }); return }
    if (state.mode === 'star' && state.stellarMode === 'evolution') {
      setAppState({ evolutionPlaying: true, ...(state.evolutionProgress >= 1 ? { evolutionProgress: 0 } : {}) })
    } else if (state.mode === 'observations') {
      if (await observationCount(ctx) < 2) throw new Error('Not enough observation frames')
      setAppState({ stageView: 'frames', viewMode: 'single', playing: true })
    } else if (state.mode === 'star' && state.stellarMode === 'education') {
      throw new Error('Use the education model’s playback control')
    } else setAppState({ playing: true, ...(state.year >= 2100 ? { year: 2000 } : {}) })
  }),
  spec('open_search', 'Open the star and coordinate search', 'Yıldız ve koordinat aramasını aç', {}, (_, ctx) => {
    if (!ctx.openSearch) throw new Error('Search is unavailable')
    ctx.openSearch()
  }),
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

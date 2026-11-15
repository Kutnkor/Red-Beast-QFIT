// The V4 shell. The frame (v4.html) owns the top bar, dock, toasts and the education view; this component
// portals every other view into that frame so the whole application speaks one design language (kit.css).
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { ColorMagnitude, type Props } from '../ui/observatory/Observatory'
import { useI18n } from '../i18n'
import { setAppState } from '../lib/store'
import { buildAssistantContext } from '../lib/assistantContext'
import { COMMANDS, runCommand, validateArgs } from '../lib/commands'
import { QFitAssistant } from '../qfit/QFitAssistant'
import { createLocalAssistant } from '../qfit/localIntent'
import type { Proposal } from '../qfit/api'
import { uniqueCatalogueStars } from '../three/types'
import { parseSkyQuery, angularSeparation, skyCoordinates } from '../three/science/astrometry'
import { evolutionAt, evolutionTrack } from '../three/science/evolution'
import { EducationScene, type EducationSample } from './EducationScene'
import { KIcon, Panel } from './kit'
import { watchSheetOrigin } from './sheet'
import { Opening } from './Opening'
import { ArcChips, CatalogueColumn, EvolutionColumn, EvolutionHR, EvolutionStrip, GalaxyColumn, ModeSwitch, ObservationColumn, SkyScaleSwitch, YearStrip, catalogueChips, evolutionChips } from './live'
import './shell.css'
import sceneCss from './scene.css?inline'

interface Bridge { subscribe(fn: (action: string, value?: string) => void): void; setMode(mode: string, lang: string): void; setPage?(page: string): void; sample(): EducationSample | null; guide?(): void }

export function V4Observatory(props: Props) {
  const frame = useRef<HTMLIFrameElement>(null), latest = useRef(props); latest.current = props
  const { lang, setLang } = useI18n(), [doc, setDoc] = useState<Document | null>(null)
  const [sceneRoot, setSceneRoot] = useState<HTMLElement | null>(null)
  const [search, setSearch] = useState(false), [query, setQuery] = useState(''), [picked, setPicked] = useState(0), [measure, setMeasure] = useState(false), [hr, setHr] = useState(false)
  const bridge = useRef<Bridge | null>(null)
  useEffect(() => watchSheetOrigin(doc?.defaultView), [doc])
  // Fixed for the life of the shell: the app rewrites the address bar on every state change, and a changing src would reload the frame.
  const [frameSrc] = useState(() => `/v4.html${new URLSearchParams(window.location.search).has('clean') ? '?state=clean' : ''}`)
  const state = props.state, education = state.stellarMode === 'education', isEducation = state.mode === 'star' && education
  const evolving = state.mode === 'star' && state.stellarMode === 'evolution'
  const galaxy = state.mode === 'neighbors' && state.skyScale === 'galaxy'
  const setEducation = (active: boolean) => setAppState({ stellarMode: active ? 'education' : 'surface', playing: false, evolutionPlaying: false })
  const page = isEducation ? 'education' : state.mode === 'observations' ? 'observations' : state.mode === 'neighbors' ? (state.skyScale === 'galaxy' ? 'galaxy' : 'sky') : state.stellarMode === 'evolution' ? 'evolution' : 'surface'
  // The robin's own abilities: it can move around the app when asked ("take me to the Sun").
  const local = useMemo(() => createLocalAssistant({
    targets: () => latest.current.targets.map(t => ({ id: t.id, name: t.name })), frameCount: () => latest.current.sequence?.frames.length ?? 0,
    stars: () => latest.current.catalogue ? uniqueCatalogueStars(latest.current.catalogue) : [],
    profile: id => id === latest.current.state.targetId ? latest.current.profile : undefined, sequence: () => latest.current.sequence,
    select: id => latest.current.select(id), guide: () => bridge.current?.guide?.(), sources: () => latest.current.sources(), setLang,
  }), [setLang])
  // On the first visit to a page the robin says what the page is and offers its tour.
  const [hint, setHint] = useState<string | null>(null)
  useEffect(() => {
    if (!doc || new URLSearchParams(window.location.search).has('clean')) return
    let seen = true
    try { seen = localStorage.getItem('rb.hint.' + page) === '1' } catch { /* keep quiet when storage is unavailable */ }
    if (seen) { setHint(null); return }
    const show = window.setTimeout(() => { setHint(page); try { localStorage.setItem('rb.hint.' + page, '1') } catch { /* ignore */ } }, 1500)
    const hide = window.setTimeout(() => setHint(current => current === page ? null : current), 15000)
    return () => { window.clearTimeout(show); window.clearTimeout(hide) }
  }, [page, doc])
  const currentView = useRef({ isEducation, mode: state.mode, lang, page }); currentView.current = { isEducation, mode: state.mode, lang, page }
  const sample = useCallback(() => bridge.current?.sample() ?? null, [])
  const openAssistant = () => window.dispatchEvent(new Event('blinkspace:assistant'))
  const tr = lang === 'tr', L = (a: string, b: string) => (tr ? a : b)

  useEffect(() => {
    if (!doc) return
    const w = doc.defaultView as Window & { RedBeastV4?: Bridge }
    const attach = () => {
      if (!w.RedBeastV4) return
      bridge.current = w.RedBeastV4
      bridge.current.subscribe((action, value) => {
        if (action === 'view' && value && ['star', 'neighbors', 'observations'].includes(value)) latest.current.mode(value as typeof state.mode)
        else if (action === 'language' && (value === 'tr' || value === 'en')) setLang(value)
        else if (action === 'assistant') openAssistant()
        else if (action === 'search') setSearch(true)
        else if (action === 'sources') latest.current.sources()
        else if (action === 'measure') setMeasure(true)
        else if (action === 'hr') setHr(true)
        else if (action === 'guide') bridge.current?.guide?.()
        else if (action === 'motion') setAppState({ reducedMotion: value === 'reduced' })
      })
      const view = currentView.current; bridge.current.setMode(view.isEducation ? 'education' : view.mode, view.lang); bridge.current.setPage?.(view.page)
    }
    attach(); w.addEventListener('redbeast-v4-ready', attach)
    // Scene components keep their own styles and data paths inside a shadow root in the frame.
    const sceneHost = doc.getElementById('v4-live-scene')!
    const shadow = sceneHost.shadowRoot ?? sceneHost.attachShadow({ mode: 'open' })
    const container = doc.createElement('div'); container.className = 'observatory v4-render-root kx-scope'; shadow.append(container); setSceneRoot(container)
    const icons = document.querySelector('.icon-sprite')?.cloneNode(true); if (icons) shadow.append(icons)
    const overrides = doc.createElement('style'); overrides.textContent = sceneCss; shadow.append(overrides)
    const copied = new Map<Element, Element>(), outerStyles: Node[] = []
    const sync = () => { document.head.querySelectorAll('link[rel="stylesheet"],style').forEach(el => { if (!copied.has(el)) { const c = el.cloneNode(true) as Element; shadow.insertBefore(c, container); const outer = el.cloneNode(true); doc.head.prepend(outer); outerStyles.push(outer); copied.set(el, c) } }) }
    sync(); const observer = new MutationObserver(sync); observer.observe(document.head, { childList: true, subtree: true })
    return () => { bridge.current?.subscribe(() => {}); w.removeEventListener('redbeast-v4-ready', attach); observer.disconnect(); copied.forEach(c => c.remove()); outerStyles.forEach(c => c.parentNode?.removeChild(c)); bridge.current = null; container.remove(); overrides.remove(); icons?.parentNode?.removeChild(icons) }
  }, [doc, setLang])
  useEffect(() => { bridge.current?.setMode(isEducation ? 'education' : state.mode, lang); bridge.current?.setPage?.(page) }, [isEducation, state.mode, lang, doc, page])
  useEffect(() => {
    const open = () => setSearch(true)
    const keys = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); open() } }
    window.addEventListener('blinkspace:open-search', open); window.addEventListener('keydown', keys)
    return () => { window.removeEventListener('blinkspace:open-search', open); window.removeEventListener('keydown', keys) }
  }, [])

  const execute = async (p: Proposal) => {
    const spec = COMMANDS.find(c => c.name === p.name); if (!spec || !validateArgs(spec.schema, p.args)) return { ok: false }
    if (p.name === 'select_target') { props.select(p.args.target_id as string); setEducation(false); return { ok: true } }
    return runCommand(p.name, p.args, { source: 'assistant', confirmed: true, frameCount: props.sequence?.frames.length, openSources: props.sources, saveView: props.save, startSearch: request => { window.dispatchEvent(new CustomEvent('blinkspace:search', { detail: request })) }, explainValue: () => { setMeasure(true); return L('Kaynaklı ölçümler', 'Source-backed measurements') } })
  }
  const track = evolutionTrack(state.evolutionTrack)
  const context = buildAssistantContext(state, { target: isEducation ? null : props.star, sequence: isEducation ? null : props.sequence, marks: props.marks })
  const stars = props.catalogue ? uniqueCatalogueStars(props.catalogue) : [], coordinates = parseSkyQuery(query)
  const matches = coordinates
    ? stars.map(star => ({ star, angle: angularSeparation(coordinates, skyCoordinates(star, state.year)) as number | null })).sort((a, b) => a.angle! - b.angle!).slice(0, 8)
    : stars.filter(s => s.name.toLocaleLowerCase().includes(query.toLocaleLowerCase())).slice(0, 15).map(star => ({ star, angle: null as number | null }))
  const parameter = (key: string) => { const p = props.profile?.parameters[key]; return typeof p?.value === 'number' ? new Intl.NumberFormat(lang, { maximumSignificantDigits: 4 }).format(p.value) : '—' }
  const targetName = props.star?.name ?? props.targets.find(t => t.id === state.targetId)?.name ?? 'SPHEREx'
  const portal = (id: string, content: ReactNode) => { const e = id === 'v4-live-scene' ? sceneRoot : doc?.getElementById(id); return e ? createPortal(content, e) : null }
  const choose = (id: string) => { props.select(id); setEducation(false); setSearch(false); setQuery(''); setAppState({ skyScale: 'local' }); props.mode('neighbors') }
  const closeSearch = () => { setSearch(false); setQuery(''); setPicked(0) }
  const view = isEducation ? 'education' : state.mode === 'observations' ? 'observations' : state.mode === 'neighbors' ? (galaxy ? 'galaxy' : 'sky') : evolving ? 'evolution' : 'surface'

  return <div className="observatory v4-shell">
    <iframe ref={frame} title="RedBeast" className="v4-frame" src={frameSrc} onLoad={() => setDoc(frame.current?.contentDocument ?? null)} />
    {portal('v4-live-scene', !isEducation && props.scene)}
    {portal('v4-education-scene', isEducation && <EducationScene sample={sample} lang={lang} />)}
    {portal('v4-model-switch', state.mode === 'star' && <>
      <ModeSwitch state={state} lang={lang} />
      {isEducation && <p className="v4-education-note">{L('Temsili eğitim senaryosu. Sayılar ölçüm ya da hedefe özel öngörü değildir.', 'Illustrative education scenario. Values are not measurements or target predictions.')}</p>}
    </>)}
    {portal('v4-model-switch', state.mode === 'neighbors' && <SkyScaleSwitch state={state} lang={lang} />)}
    {portal('v4-live-controls', !isEducation && <div className="kx-scope lv" data-view={view} data-empty={(state.mode === 'observations' && !props.sequence) || undefined} key={view}>
      {state.mode === 'observations'
        ? <ObservationColumn state={state} lang={lang} targets={props.targets} title={targetName} sequence={props.sequence} onSelect={props.select}
            onEvolution={() => { setAppState({ stellarMode: 'evolution', playing: false, evolutionPlaying: false }); props.mode('star') }} />
        : galaxy ? <GalaxyColumn lang={lang} />
        : evolving
          ? <EvolutionColumn state={state} lang={lang} targets={props.targets} star={props.star} title={targetName} onSelect={props.select} />
          : <CatalogueColumn state={state} lang={lang} targets={props.targets} star={props.star} title={targetName} onSelect={props.select} onSearch={() => setSearch(true)} />}
      {state.mode !== 'observations' && !galaxy && (evolving
        ? <><ArcChips swap={`${state.targetId}|${state.evolutionTrack}`} label={L('Model değerleri', 'Model values')} items={evolutionChips(lang, state)} /><EvolutionHR state={state} lang={lang} /><EvolutionStrip state={state} lang={lang} /></>
        : <><ArcChips swap={String(state.targetId)} label={L('Katalog değerleri', 'Catalogue values')} items={catalogueChips(lang, props.star, state.year, parameter, () => setMeasure(true))} /><YearStrip state={state} lang={lang} /></>)}
      {state.mode !== 'observations' && <p className="lv-scale"><KIcon name="info" size={14} />{L('Ölçek temsilidir', 'Scale is representative')}</p>}
      <div className="v4-live-note">{props.notices}</div>
    </div>)}
    {props.dialogs}
    {search && <Panel place="top" title={L('Yıldız veya koordinat bul', 'Find a star or coordinates')} closeLabel={L('Kapat', 'Close')} onClose={closeSearch}
      head={<label className="kx-find"><KIcon name="search" size={20} /><input data-autofocus placeholder={L('Barnard ya da 269.4463, 4.7682', 'Barnard or 269.4463, 4.7682')} aria-label={L('Yıldız veya RA / Dec', 'Star or RA / Dec')} value={query} autoComplete="off" spellCheck={false}
        onChange={e => { setQuery(e.target.value); setPicked(0) }}
        onKeyDown={e => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setPicked(i => Math.min(matches.length - 1, i + 1)) }
          else if (e.key === 'ArrowUp') { e.preventDefault(); setPicked(i => Math.max(0, i - 1)) }
          else if (e.key === 'Enter' && matches[picked]) { e.preventDefault(); choose(matches[picked].star.id) }
        }} /></label>}>
      <div className="kx-results">
        {matches.length === 0 && <p role="status" className="kx-empty">{L('Katalogda eşleşme yok. Aşağıdan SPHEREx arşivinde arayabilirsin.', 'No catalogue match. Try the SPHEREx archive below.')}</p>}
        {matches.length > 0 && <i className="kx-hl" aria-hidden="true" style={{ transform: `translateY(${picked * 44}px)` }} />}
        {matches.map(({ star, angle }, i) => <button type="button" key={star.id} data-on={i === picked} aria-current={i === picked ? "true" : undefined} onMouseEnter={() => setPicked(i)} onClick={() => choose(star.id)}>
          <KIcon name="orbit" /><span>{star.name}</span>{angle !== null ? <small>{angle.toFixed(4)}°</small> : <small>{L('katalog', 'catalogue')}</small>}</button>)}
      </div>
      <details className="kx-archive"><summary><KIcon name="frames" />{L('Arşivde gerçek SPHEREx gözlemi ara', 'Search real SPHEREx observations')}</summary>{props.search}</details>
      <p className="kx-hint"><kbd>↑</kbd><kbd>↓</kbd>{L('gez', 'move')}<kbd>Enter</kbd>{L('seç', 'select')}<kbd>Esc</kbd>{L('kapat', 'close')}</p>
    </Panel>}
    {hr && props.catalogue && <Panel title={L('Gaia · Renk–parlaklık', 'Gaia · Color–magnitude')} closeLabel={L('Kapat', 'Close')} onClose={() => setHr(false)}><ColorMagnitude catalogue={props.catalogue} selected={state.targetId} onSelect={props.select} lang={lang} /></Panel>}
    {measure && <Panel title={L('Kaynaklı ölçümler', 'Source-backed measurements')} closeLabel={L('Kapat', 'Close')} onClose={() => setMeasure(false)}>{props.measurements}</Panel>}
    <Opening lang={lang} />
    {hint && <RobinHint lang={lang} page={hint} onTour={() => { setHint(null); bridge.current?.guide?.() }} onClose={() => setHint(null)} />}
    <QFitAssistant lang={lang} remember local={local} context={() => ({ ...context, ...(isEducation ? { view: 'illustrative_education', education_sample: sample(), model_warning: 'The visible V4 scenario is illustrative, not observations or a fitted target evolution. Never describe its values as measurements of the selected catalogue target.' } : evolving ? { view: 'published_comparison_model', model_source: track.source, model_url: track.url, model_sample: evolutionAt(track, state.evolutionProgress), model_warning: 'Published comparison track; not the measured age or fitted future of the selected target. No extrapolation beyond the source table.' } : {}) })} onCommand={execute} />
  </div>
}

const HINTS: Record<string, [string, string]> = {
  observations: ['Bunlar gerçek SPHEREx kareleri. Bu sayfayı yarım dakikada gezdireyim mi?', 'These are real SPHEREx frames. Shall I walk you through this page in half a minute?'],
  galaxy: ['Samanyolu’ndasın; turuncu işaret biziz. Gezdireyim mi?', 'This is the Milky Way; the orange marker is us. Want a quick tour?'],
  sky: ['Güneş’in yakın çevresi: her nokta ölçülmüş bir yıldız. Gezdireyim mi?', 'The Sun’s neighbourhood: every dot is a measured star. Want a quick tour?'],
  surface: ['Bu yıldızın katalog değerleri çevresinde duruyor. Gezdireyim mi?', 'This star’s catalogue values sit around it. Want a quick tour?'],
  evolution: ['Yayımlanmış bir evrim tablosuna bakıyorsun. Gezdireyim mi?', 'You are looking at a published evolution table. Want a quick tour?'],
  education: ['Kütleyi değiştir, yıldızın sonunu gör. Gezdireyim mi?', 'Change the mass and see how the star ends. Want a quick tour?'],
}
/** A speech bubble that grows out of the robin. It never covers controls: it sits above the mascot in the corner. */
function RobinHint({ lang, page, onTour, onClose }: { lang: 'tr' | 'en'; page: string; onTour: () => void; onClose: () => void }) {
  const text = HINTS[page]
  if (!text) return null
  const tr = lang === 'tr'
  return <div className="rb-hint" role="status">
    <p>{text[tr ? 0 : 1]}</p>
    <p className="rb-hint-tip">{tr ? 'Bana “Güneş’e götür” ya da “Samanyolu’nu göster” de yazabilirsin.' : 'You can also tell me “take me to the Sun” or “show the Milky Way”.'}</p>
    <div><button type="button" className="rb-hint-go" onClick={onTour}>{tr ? 'Gezdir' : 'Show me'}</button><button type="button" onClick={onClose}>{tr ? 'Sonra' : 'Later'}</button></div>
  </div>
}

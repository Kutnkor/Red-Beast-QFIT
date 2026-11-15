import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useI18n } from '../../i18n'
import { setAppState, type AppMode, type AppState } from '../../lib/store'
import { COMMANDS, runCommand, validateArgs } from '../../lib/commands'
import { buildAssistantContext } from '../../lib/assistantContext'
import { readString, writeString } from '../../lib/storage'
import type { Mark, Sequence, Target } from '../../lib/types'
import type { MotionCatalogue, MotionStar, StellarProfile } from '../../three/types'
import { uniqueCatalogueStars } from '../../three/types'
import { StellarWorkbench, EvolutionReadout, EvolutionTimeline } from './StellarWorkbench'
import { angularShift, distanceLy, skyCoordinates, parseSkyQuery, angularSeparation } from '../../three/science/astrometry'
import { temperatureToRgb } from '../../three/science/blackbody'
import { QFitAssistant } from '../../qfit/QFitAssistant'
import type { Proposal } from '../../qfit/api'
import robinIcon from '../../qfit/assets/robin-64.png'
import { Dialog } from '../common'
import { Timeline } from '../../viewer/Timeline'
import './tokens.css'
import './observatory.css'
import './workbench.css'

type Panel = 'measure' | 'settings' | 'guide' | 'diagram' | null
export interface Props {
  state: AppState; targets: Target[]; catalogue: MotionCatalogue | null; star: MotionStar | null; profile?: StellarProfile
  sequence: Sequence | null; marks: Mark[]; scene: ReactNode; search: ReactNode; measurements: ReactNode
  dialogs: ReactNode; notices: ReactNode; saved: string; online: boolean; embed: boolean
  select: (id: string) => void; mode: (mode: AppMode) => void; save: () => void; sources: () => void
}
const WORDS = {
  tr: { sky: 'Gökyüzü', star: 'Yıldız', observations: 'Gözlemler', search: 'Bir yıldız bul', sources: 'Kaynaklar', measure: 'Ölçümler', diagram: 'Renk–parlaklık', settings: 'Ayarlar', guide: 'Keşif rehberi',
    close: 'Kapat', target: 'Hedef seç', live: 'KAYNAKLI UZAY KEŞFİ', radius: 'Yarıçap', temperature: 'Sıcaklık', distance: 'Uzaklık', motion: 'Özdevinim', unknown: 'Bilinmiyor', modeled: 'Hesaplanan konum',
    radiusNote: 'Boyutlar karşılaştırma için sıkıştırılmıştır. Yüzey ve çevre temsili; gerçek teleskop görüntüleri Gözlemler bölümündedir.', title: 'Yıldızların arasında.', intro: 'Gerçek kataloglar. Hareket eden yıldızlar. Keşfetmek için bir hedef seç.',
    year: 'Model yılı', speed: 'Hız', perSecond: 'yıl/sn', shift: '2026’dan açısal hareket', play: 'Oynat', pause: 'Duraklat', atmosphere: 'Yıldız çevresi', trail: 'Hareket izi', grid: 'Koordinat ağı', background: 'Arka plan yıldızları',
    quality: 'Görsel kalite', high: 'Yüksek', medium: 'Orta', low: 'Düşük', solid: 'Saydamlığı azalt', save: 'Görünümü indir', legacy: 'Önceki arayüz', find: 'Katalogda ara', empty: 'Eşleşen hedef yok.', archive: 'Koordinatla gerçek gözlem ara',
    diagramNote: 'Gaia BP−RP rengi ve paralakstan hesaplanan mutlak G parlaklığı. Bir evrim yolu değildir.', diagramAxis: 'Mutlak G', help1: 'Yıldız: kaynaklı özelliklerle temsili 3B yüzeyi ve çevresini incele.', help2: 'Gökyüzü: komşu yıldızları seç; 2000–2100 arasındaki hesaplanan hareketi gör.', help3: 'Gözlemler: gerçek SPHEREx karelerini karşılaştır, işaretle, ışık eğrisi ve kaynakları aç.', help4: 'Q-FIT: kaynakları oku veya yapılandırılmış AI ile sorular sor. Önerilen işlemler düğmeye basınca çalışır.',
    frames: 'Kareler', stack: 'Zaman yığını', analysis: 'Analiz araçları', frame: 'Kare', layers: 'Katmanlar', marks: 'İşaretler', curve: 'Işık eğrisi', wave: 'Dalga boyu', task: 'Araştırma görevi', selectSource: 'Değerin kaynağını aç', loading: 'Katalog yükleniyor…',
  },
  en: { sky: 'Sky', star: 'Star', observations: 'Observations', search: 'Find a star', sources: 'Sources', measure: 'Measurements', diagram: 'Color–magnitude', settings: 'Settings', guide: 'Explorer’s guide',
    close: 'Close', target: 'Select target', live: 'SOURCE-LED SPACE EXPLORATION', radius: 'Radius', temperature: 'Temperature', distance: 'Distance', motion: 'Proper motion', unknown: 'Unknown', modeled: 'Computed position',
    radiusNote: 'Sizes are compressed for comparison. Surfaces and environments are representative; telescope images are in Observations.', title: 'Among the stars.', intro: 'Real catalogues. Moving stars. Choose a target to explore.',
    year: 'Model year', speed: 'Speed', perSecond: 'yr/s', shift: 'Angular shift from 2026', play: 'Play', pause: 'Pause', atmosphere: 'Stellar environment', trail: 'Motion trail', grid: 'Coordinate grid', background: 'Background stars',
    quality: 'Visual quality', high: 'High', medium: 'Medium', low: 'Low', solid: 'Reduce transparency', save: 'Download view', legacy: 'Previous interface', find: 'Search catalogue', empty: 'No matching targets.', archive: 'Search real observations by coordinates',
    diagramNote: 'Gaia BP−RP color and absolute G magnitude computed from parallax. This is not an evolutionary track.', diagramAxis: 'Absolute G', help1: 'Star: explore a representative 3D surface and environment with source-backed properties.', help2: 'Sky: select neighbouring stars and see their computed motion from 2000 to 2100.', help3: 'Observations: compare real SPHEREx frames, annotate them, and inspect light curves and sources.', help4: 'Q-FIT: read source cards or ask the configured AI. Proposed actions run only when you click their button.',
    frames: 'Frames', stack: 'Time stack', analysis: 'Analysis tools', frame: 'Frame', layers: 'Layers', marks: 'Marks', curve: 'Light curve', wave: 'Wavelength', task: 'Research task', selectSource: 'Open the value’s source', loading: 'Loading catalogue…',
  },
}
export function SphereIcon({ name }: { name: string }) {
  return <svg className="sx-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><use href={`/sphere-icons.svg#i-${name}`} /></svg>
}
export function ColorMagnitude({ catalogue, selected, onSelect, lang }: { catalogue: MotionCatalogue; selected: string | null; onSelect: (id: string) => void; lang: 'tr' | 'en' }) {
  const words = WORDS[lang]
  const data = [...catalogue.stars, ...catalogue.targets].filter(s => Number.isFinite(s.colorIndex) && Number.isFinite(s.magnitude) && s.parallax > 0)
    .map(s => ({ star: s, color: s.colorIndex!, absolute: s.magnitude! + 5 * Math.log10(s.parallax / 1000) + 5 }))
  const xs = data.map(p => p.color), ys = data.map(p => p.absolute)
  const xmin = Math.min(0, ...xs), xmax = Math.max(4, ...xs), ymin = Math.min(-1, ...ys), ymax = Math.max(15, ...ys)
  return <figure className="sx-diagram"><svg viewBox="0 0 300 190" role="img" aria-label={words.diagram}>
    <path d="M35 15 V155 H285" stroke="currentColor" opacity=".4" fill="none" />
    {[0, .5, 1].map(n => <g key={n}><text x="28" y={20 + n * 130} textAnchor="end">{(ymin + n * (ymax - ymin)).toFixed(0)}</text><text x={35 + n * 245} y="171" textAnchor="middle">{(xmin + n * (xmax - xmin)).toFixed(1)}</text></g>)}
    {data.map(({ star, color, absolute }) => <circle key={star.id} cx={35 + (color - xmin) / (xmax - xmin) * 245} cy={18 + (absolute - ymin) / (ymax - ymin) * 130} r={star.id === selected ? 5 : 2.4} fill={star.teff_k ? `rgb(${temperatureToRgb(star.teff_k).join(',')})` : '#9cb2ee'} stroke={star.id === selected ? '#fff' : 'none'} role="button" tabIndex={0} aria-label={star.name} onClick={() => onSelect(star.id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); onSelect(star.id) } }}><title>{star.name}: BP−RP {color.toFixed(2)}, G {absolute.toFixed(2)}</title></circle>)}
    <text x="160" y="189" textAnchor="middle">BP−RP (mag)</text><text x="10" y="90" transform="rotate(-90 10 90)" textAnchor="middle">{words.diagramAxis}</text>
  </svg><figcaption>{words.diagramNote}</figcaption></figure>
}
export function Observatory(props: Props) {
  const { state, star, profile, catalogue, sequence } = props, { lang, setLang, t } = useI18n(), words = WORDS[lang]
  const [panel, setPanel] = useState<Panel>(null), [searchOpen, setSearchOpen] = useState(false), [query, setQuery] = useState('')
  const [solid, setSolid] = useState(() => readString('blinkspace.solid') === '1'), searchRef = useRef<HTMLInputElement>(null)
  const format = (value: number, digits = 2) => new Intl.NumberFormat(lang, { maximumFractionDigits: digits }).format(value)
  const toggle = (value: Panel) => setPanel(p => p === value ? null : value)
  useEffect(() => {
    const open = () => setSearchOpen(true)
    const keys = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setSearchOpen(true); return }
      if (e.altKey || e.ctrlKey || e.metaKey || (e.target as HTMLElement)?.closest('input,textarea,select,[contenteditable="true"],[data-dialog],.qf-panel')) return
      if (e.key.toLowerCase() === 'm' && state.mode !== 'observations') toggle('measure')
      else if (e.key.toLowerCase() === 'h') toggle('diagram')
      else if (e.key.toLowerCase() === 's') window.dispatchEvent(new Event('blinkspace:assistant'))
      else if (e.key === 'Escape') { setPanel(null); setSearchOpen(false) }
    }
    window.addEventListener('blinkspace:open-search', open); window.addEventListener('keydown', keys)
    return () => { window.removeEventListener('blinkspace:open-search', open); window.removeEventListener('keydown', keys) }
  }, [state.mode])
  useEffect(() => { if (searchOpen) searchRef.current?.focus() }, [searchOpen])
  const execute = async (p: Proposal) => {
    const spec = COMMANDS.find(c => c.name === p.name)
    if (!spec || !validateArgs(spec.schema, p.args)) return { ok: false }
    if (p.name === 'select_target') { props.select(p.args.target_id as string); return { ok: true } }
    return runCommand(p.name, p.args, { source: 'assistant', confirmed: true, frameCount: sequence?.frames.length,
      openSources: props.sources, saveView: props.save,
      startSearch: request => { window.dispatchEvent(new CustomEvent('blinkspace:search', { detail: request })) },
      explainValue: () => { setPanel('measure'); return words.sources },
    })
  }
  const temp = profile?.parameters.teff_k, radius = profile?.parameters.radius_solar
  const parameterText = (p: typeof temp, unit: string) => typeof p?.value === 'number' ? `${format(p.value, 3)}${p.uncertainty === undefined ? '' : ` ± ${format(p.uncertainty, 3)}`} ${unit}` : words.unknown
  const metrics = [
    { id: 'radius', label: words.radius, value: parameterText(radius, 'R☉'), tag: radius?.classification ?? 'unknown' },
    { id: 'temperature', label: words.temperature, value: parameterText(temp, 'K'), tag: temp?.classification ?? 'unknown' },
    { id: 'distance', label: words.distance, value: star ? `${format(distanceLy(star))} ly` : '—', tag: 'computed' },
    { id: 'motion', label: words.motion, value: star ? `${format(Math.hypot(star.pmRa, star.pmDec) / 1000, 3)}″/yr` : '—', tag: 'measured' },
  ]
  const tags: Record<string, string> = lang === 'tr' ? { measured: 'Ölçüme dayalı', computed: 'Hesaplanan', unknown: 'Veri yok', assumed: 'Varsayılan', representative: 'Temsili' } : { measured: 'Measured', computed: 'Computed', unknown: 'No value', assumed: 'Assumed', representative: 'Representative' }
  const allStars = uniqueCatalogueStars(catalogue)
  const coordinateQuery = parseSkyQuery(query)
  const filtered = coordinateQuery ? [...allStars].sort((a, b) => angularSeparation(coordinateQuery, skyCoordinates(a, state.year)) - angularSeparation(coordinateQuery, skyCoordinates(b, state.year))).slice(0, 5) : allStars.filter(s => `${s.name} ${s.id}`.toLocaleLowerCase(lang).includes(query.toLocaleLowerCase(lang))).slice(0, 35)
  const shift = star ? angularShift(star, 2026, state.year) : null
  const legacyURL = new URL(window.location.href); legacyURL.searchParams.set('ui', 'legacy')
  const evolving = state.mode === 'star' && state.stellarMode === 'evolution'
  const observationMode = state.mode === 'observations', frameView = observationMode && state.stageView === 'frames'
  return <div className={`observatory ${solid ? 'sx-solid' : ''} ${observationMode ? 'sx-observations' : 'sx-workbench'} ${evolving ? 'sx-evolving' : ''} ${props.embed ? 'app-embed' : ''}`} data-ui="observatory">
    <a className="skip" href="#main">{lang === 'tr' ? 'İçeriğe geç' : 'Skip to content'}</a>
    <header className="sx-top" data-ui="topbar">
      <button className="sx-logo" onClick={() => { props.select('barnard'); props.mode('star') }} aria-label={t('app.name')}><img className="sx-logo-mark" src={robinIcon} alt="" width={34} height={34} /><span>{t('app.name')}</span></button>
      <nav className="sx-tabs sx-glass" aria-label={lang === 'tr' ? 'Görünüm' : 'View'}>{(['neighbors', 'star', 'observations'] as const).map(mode => <button key={mode} aria-pressed={state.mode === mode} onClick={() => props.mode(mode)}>{words[mode === 'neighbors' ? 'sky' : mode]}</button>)}</nav>
      <button className="sx-search sx-glass" onClick={() => setSearchOpen(true)}><SphereIcon name="search" /><span>{words.search}</span><kbd>⌘ K</kbd></button>
      <button className="sx-source sx-glass" onClick={props.sources}><SphereIcon name="book" /><span>{words.sources}</span></button>
      <div className="sx-tabs sx-glass sx-language" aria-label="Language">{(['tr', 'en'] as const).map(l => <button key={l} aria-pressed={lang === l} onClick={() => setLang(l)}>{l.toUpperCase()}</button>)}</div>
    </header>
    <main id="main" className="sx-main" tabIndex={-1}>
      <div className="sx-scene" data-ui="three-scene">{props.scene}</div><div className="sx-haze" aria-hidden="true" />
      <div className="sx-notices">{props.notices}</div>
      <nav className="sx-dock sx-glass" aria-label={words.analysis} data-ui="dock">
        {([['measure', 'measure', 'M'], ['diagram', 'hr', 'H'], ['assistant', 'ask', 'S'], ['guide', 'guide', '?'], ['settings', 'settings', '']] as const).map(([id, icon, key]) => <button key={id} title={`${id === 'assistant' ? 'Q-FIT' : words[id]} ${key ? `(${key})` : ''}`} aria-label={id === 'assistant' ? 'Q-FIT' : words[id]} aria-pressed={panel === id} onClick={() => id === 'assistant' ? window.dispatchEvent(new Event('blinkspace:assistant')) : toggle(id)}><SphereIcon name={icon} /></button>)}
      </nav>
      <section className="sx-who" data-ui="target-identity">
        <p className="sx-eyebrow">{observationMode ? 'NASA/IPAC IRSA · SPHEREx' : words.live}</p>
        <h1>{star?.name ?? (catalogue ? words.title : words.loading)}</h1>
        <p className="sx-phase"><span className="sx-star-dot" style={temp?.value ? { background: `rgb(${temperatureToRgb(Number(temp.value)).join(',')})` } : undefined} />{lang === 'tr' ? star?.subtitleTr : star?.subtitleEn}</p>
        <p className="sx-say">{observationMode && sequence ? `${sequence.frames.length} ${lang === 'tr' ? 'gözlem' : 'observations'} · ${format(sequence.meta.wavelength.lam_ref_um, 3)} µm · ${sequence.frames[0]?.date_avg.slice(0, 10)} — ${sequence.frames.at(-1)?.date_avg.slice(0, 10)}` : words.radiusNote}</p>
        <div className="sx-targets sx-tabs sx-glass" role="group" aria-label={words.target} data-ui="target-tabs">{props.targets.map(s => <button aria-label={s.name} key={s.id} aria-pressed={s.id === state.targetId} onClick={() => props.select(s.id)}>{s.id === 'barnard' ? 'Barnard' : s.id === 'eps-indi-b' ? 'ε Indi' : s.id === 'wise-0855' ? 'WISE 0855' : s.id === 'rw-aur' ? 'RW Aur' : s.name.replace('Epsilon', 'ε').replace("'s Star", '')}</button>)}</div>
        {!observationMode && !evolving && star && <div className="sx-shift" data-ui="motion-summary"><span>{words.shift}</span><strong>{shift ? `${format(shift.arcsec)}″` : '—'}</strong><small>{words.modeled} · ICRS J{star.epoch}</small></div>}
        {observationMode && <div className="sx-observation-tools"><div className="sx-tabs sx-glass">{(['frames', 'timestack'] as const).map(v => <button key={v} aria-pressed={state.stageView === v} onClick={() => void runCommand('set_stage_view', { view: v }, { source: 'user' })}>{v === 'frames' ? words.frames : words.stack}</button>)}</div><button className="sx-glass" onClick={() => setAppState(s => ({ drawer: { ...s.drawer, open: !s.drawer.open } }))}>{words.analysis}</button></div>}
        {!observationMode && <StellarWorkbench state={state} star={star} />}
      </section>
      {evolving && <EvolutionReadout state={state} />}
      {!observationMode && !evolving && <div className="sx-metrics" data-ui="metric-callouts">{metrics.map(metric => <button className={`sx-metric sx-glass sx-metric-${metric.id} ${metric.tag}`} key={metric.id} title={words.selectSource} onClick={() => setPanel('measure')}><span>{metric.label}<small>{tags[metric.tag]}</small></span><strong>{metric.value}</strong></button>)}</div>}
      {!observationMode && !evolving && catalogue && <button className="sx-mini-diagram sx-glass" onClick={() => setPanel('diagram')}><SphereIcon name="hr" /><span>Gaia<br /><strong>{words.diagram}</strong></span><span aria-hidden="true">↗</span></button>}
      {evolving && <EvolutionTimeline state={state} />}
      {!frameView && !evolving && <section className="sx-timeline" data-ui="timeline" aria-label={words.year}>
        <div className="sx-play-group"><button className="sx-play sx-glass" aria-label={state.playing ? words.pause : words.play} disabled={observationMode && (!sequence || sequence.frames.length < 2)} onClick={() => setAppState({ playing: !state.playing, ...(!observationMode && state.year >= 2100 ? { year: 2000 } : {}) })}>{state.playing ? 'Ⅱ' : '▶'}</button>{!observationMode && <select className="sx-glass" aria-label={words.speed} value={state.speedYearsPerSec} onChange={e => setAppState({ speedYearsPerSec: Number(e.target.value) as 1 | 5 | 20 })}>{[1, 5, 20].map(n => <option key={n} value={n}>{n} {words.perSecond}</option>)}</select>}</div>
        <div className="sx-ruler">{observationMode && sequence ? <Timeline frames={sequence.frames.map(f => ({ mjd: f.mjd_avg, date: f.date_avg }))} current={state.frameIndex} reference={state.refIndex} showReference onSelect={index => void runCommand('set_frame', { index }, { source: 'user', frameCount: sequence.frames.length })} /> : <><div className="sx-year-label"><span>{words.year}</span><span>{words.modeled}</span></div><input aria-label={words.year} type="range" min="2000" max="2100" step="0.1" value={state.year} onChange={e => setAppState({ year: Number(e.target.value), playing: false })} /><div className="sx-ticks">{[2000, 2025, 2050, 2075, 2100].map(year => <button key={year} onClick={() => setAppState({ year, playing: false })}>{year}</button>)}</div></>}</div>
        <div className="sx-year">{observationMode ? sequence?.frames[state.frameIndex]?.date_avg.slice(0, 10) : new Intl.NumberFormat(lang, { useGrouping: false, maximumFractionDigits: 1 }).format(state.year)}<small>{observationMode ? 'UTC' : 'JULIAN YEAR'}</small></div>
      </section>}
      {panel && <aside className="sx-drawer sx-glass" data-ui={`drawer-${panel}`} aria-label={words[panel]}><header><h2>{words[panel]}</h2><button aria-label={words.close} onClick={() => setPanel(null)}>×</button></header>
        {panel === 'measure' && props.measurements}
        {panel === 'diagram' && catalogue && <ColorMagnitude catalogue={catalogue} selected={state.targetId} onSelect={props.select} lang={lang} />}
        {panel === 'guide' && <><ol>{[words.help1, words.help2, words.help3, words.help4].map(text => <li key={text}>{text}</li>)}</ol><p className="sx-key-hint">1 · 2 · 3 &nbsp; / &nbsp; Space &nbsp; ← → &nbsp; + − 0<br />M · H · S · ? &nbsp; Esc</p><button className="sx-action" onClick={() => { props.mode('observations'); setAppState({ drawer: { open: true, tab: 'task' } }); setPanel(null) }}>{words.task}</button></>}
        {panel === 'settings' && <div className="sx-settings">
          {(['environment', 'trail', 'grid', 'sky'] as const).map((layer, i) => <label key={layer}><span>{[words.atmosphere, words.trail, words.grid, words.background][i]}</span><input type="checkbox" checked={state.layers[layer]} onChange={e => void runCommand('toggle_layer', { layer, on: e.target.checked }, { source: 'user' })} /></label>)}
          <label><span>{words.solid}</span><input type="checkbox" checked={solid} onChange={e => { setSolid(e.target.checked); writeString('blinkspace.solid', e.target.checked ? '1' : '0') }} /></label>
          <label>{words.quality}<select value={state.quality} onChange={e => setAppState({ quality: e.target.value as AppState['quality'] })}>{(['high', 'medium', 'low'] as const).map(q => <option key={q} value={q}>{words[q]}</option>)}</select></label>
          <button className="sx-action" onClick={props.save}>{words.save}</button>{props.saved && <p role="status">{props.saved}</p>}<a href={legacyURL.pathname + legacyURL.search}>{words.legacy} ↗</a>
        </div>}
        {panel === 'measure' && <>{props.saved && <p role="status">{props.saved}</p>}<button className="sx-action" onClick={props.sources}>{words.sources}</button><button className="sx-action" onClick={props.save}>{words.save}</button></>}
        {(panel === 'measure' || panel === 'settings') && sequence && <nav className="sx-analysis-links" aria-label={words.analysis}>{(['frame', 'layers', 'marks', 'curve', 'wave', 'task'] as const).map(tab => <button key={tab} onClick={() => { setPanel(null); void runCommand('open_drawer_tab', { tab }, { source: 'user' }) }}>{words[tab]}</button>)}</nav>}
      </aside>}
    </main>
    {searchOpen && <Dialog title={words.search} onClose={() => setSearchOpen(false)}><div className="sx-search-dialog"><input ref={searchRef} type="search" placeholder={lang === 'tr' ? 'Ad veya RA, Dec (derece)' : 'Name or RA, Dec (degrees)'} aria-label={words.find} value={query} onChange={e => setQuery(e.target.value)} /><div className="sx-search-results">{coordinateQuery && <p>{lang === 'tr' ? 'Yerel katalogdaki en yakın 5 yön; eşleşme garantisi değildir.' : 'Nearest 5 directions in the local catalogue; not a guaranteed counterpart.'}</p>}{filtered.map(s => <button key={s.id} onClick={() => { props.select(s.id); setSearchOpen(false) }}><span>{s.name}</span><small>{coordinateQuery ? `${format(angularSeparation(coordinateQuery, skyCoordinates(s, state.year)), 4)}° · ` : ''}{s.spectralType} · {format(distanceLy(s, state.year))} ly</small></button>)}{!filtered.length && <p>{catalogue ? words.empty : words.loading}</p>}</div><details><summary>{words.archive}</summary>{props.search}</details></div></Dialog>}
    <QFitAssistant lang={lang} context={buildAssistantContext(state, { target: star, sequence, marks: props.marks })} onCommand={execute} />
    {props.dialogs}
  </div>
}

// Live views of the V4 shell: observations, sky, catalogue star and published model.
// They share the education view's layout grammar: big title on the left, small glass readouts on an arc
// around the scene, one time strip at the bottom. Everything here renders into the V4 frame document.
import { type ReactNode } from 'react'
import { setAppState, type AppState } from '../lib/store'
import type { Lang, Sequence, Target } from '../lib/types'
import type { MotionStar } from '../three/types'
import { skyCoordinates, distanceLy } from '../three/science/astrometry'
import { evolutionAt, evolutionTrack, evolutionTracks, formatAge, phaseLabel, suggestedTrack } from '../three/science/evolution'
import { temperatureToRgb } from '../three/science/blackbody'
import { Glider, KIcon, Odometer, RingPlay, RulerLabels, WaveRuler, type RulerMajor } from './kit'

const T = (lang: Lang, tr: string, en: string) => (lang === 'tr' ? tr : en)

/* ------------------------------------------------------------------ title */
export function Title({ text }: { text: string }) {
  const n = text.length, size = n <= 7 ? 104 : n <= 10 ? 84 : n <= 14 ? 66 : n <= 20 ? 52 : 44
  return <h1 className="lv-title" style={{ fontSize: size }} aria-label={text} key={text}>
    {text.split(' ').map((word, w) => <span className="lv-word" key={w} aria-hidden="true">{word.split('').map((ch, i) => <span className="lv-ch" key={i} style={{ animationDelay: `${(w * 4 + i) * 28}ms` }}>{ch}</span>)}</span>)}
  </h1>
}

export function Who({ kicker, title, phase, icon, badge, top, children }: { kicker: string; title: string; phase: string; icon: string; badge?: ReactNode; top: number; children: ReactNode }) {
  return <section className="lv-who" style={{ top }}>
    <p className="lv-kicker">{kicker}</p>
    <Title text={title} />
    <div className="lv-phase" key={phase}><KIcon name={icon} size={26} /><span>{phase}</span>{badge}</div>
    {children}
  </section>
}

export function TargetTabs({ targets, value, onSelect, lang }: { targets: Target[]; value: string | null; onSelect: (id: string) => void; lang: Lang }) {
  return <Glider small glass={false} className="lv-targets" label={T(lang, 'Hazır hedefler', 'Ready targets')} value={value} onChange={onSelect}
    items={targets.map(t => ({ id: t.id, label: t.id === 'barnard' ? 'Barnard' : t.name.replace('−', '-') }))} />
}

/* ---------------------------------------------------------- observations */
export function ObservationColumn({ state, lang, targets, title, sequence, onSelect, onEvolution }: {
  state: AppState; lang: Lang; targets: Target[]; title: string; sequence: Sequence | null
  onSelect: (id: string) => void; onEvolution: () => void
}) {
  const frames = sequence?.frames ?? [], days = frames.length > 1 ? frames[frames.length - 1].mjd_avg - frames[0].mjd_avg : 0
  const badge = frames.length ? <span className="lv-badge kx-glass">{frames.length} {T(lang, 'kare', 'frames')}{days > 0 && <> · {days.toFixed(days < 10 ? 1 : 0)} {T(lang, 'gün', 'days')}</>}</span> : null
  return <Who top={96} kicker={T(lang, 'SPHEREx · NASA/IPAC IRSA arşivi', 'SPHEREx · NASA/IPAC IRSA archive')} title={title} icon="frames" phase={T(lang, 'Gerçek gözlem kareleri', 'Real observation frames')} badge={badge}>
    <TargetTabs targets={targets} value={state.targetId} onSelect={onSelect} lang={lang} />
    <p className="lv-say">{T(lang, 'Aynı gökyüzü alanını gerçek gözlem tarihlerinde karşılaştır. Kareler arasında geçiş yap; değişen bir şey var mı, kendin gör.', 'Compare the same patch of sky at its actual observation dates. Flip between frames and see for yourself whether anything changed.')}</p>
    <div className="lv-actions">
      <button type="button" className="kx-act kx-solid kx-press lv-wide" onClick={onEvolution}><KIcon name="evolve" />{T(lang, 'Bu hedefin yaşam evrimini keşfet', 'Explore this target’s evolution')}</button>
      <button type="button" className="kx-act kx-glass kx-press" aria-pressed={state.drawer.open} onClick={() => setAppState(s => ({ drawer: { ...s.drawer, open: !s.drawer.open } }))}><KIcon name="measure" />{T(lang, 'Ölçüm ve analiz', 'Measure and analyse')}</button>
      <button type="button" className="kx-act kx-glass kx-press" onClick={() => setAppState({ stageView: state.stageView === 'frames' ? 'timestack' : 'frames', playing: false })}><KIcon name={state.stageView === 'frames' ? 'stack' : 'frames'} />{state.stageView === 'frames' ? T(lang, '3B zaman yığını', '3D time stack') : T(lang, 'Gözlem kareleri', 'Observation frames')}</button>
    </div>
  </Who>
}

/* ------------------------------------------------- readout chips on an arc
   Same placement as the education view: four chips on a 286 px arc around the star at (772, 372). */
const CX = 772, CY = 372, ARC = 286
const ARC_AT = [-42, -15, 12, 39].map(a => { const r = a * Math.PI / 180; return { left: Math.round(CX + ARC * Math.cos(r) + 8), top: Math.round(CY + ARC * Math.sin(r) - 29) } })
export interface ChipItem { label: string; value: string; unit?: string; onClick?: () => void }
export function ArcChips({ items, label, swap }: { items: ChipItem[]; label: string; swap?: string }) {
  // swap: when the subject changes (another star, another track) the values tick in again instead of jumping
  return <div className="lv-chips" role="group" aria-label={label}>{items.slice(0, 4).map((it, i) => {
    const body = <><small>{it.label}</small><b key={swap} className={it.value.length > 9 ? 'kx-s' : ''} style={{ animationDelay: `${i * 55}ms` }}>{it.value}{it.unit && <em>{it.unit}</em>}</b></>
    const style = { left: ARC_AT[i].left, top: ARC_AT[i].top, ['--i' as string]: i }
    return it.onClick ? <button type="button" key={it.label} className="kx kx-chip kx-glass" style={style} onClick={it.onClick}>{body}</button> : <div key={it.label} className="kx kx-chip kx-glass" style={style}>{body}</div>
  })}</div>
}

/* ------------------------------------------------------------ Milky Way */
export function SkyScaleSwitch({ state, lang }: { state: AppState; lang: Lang }) {
  return <Glider className="lv-modes" label={T(lang, 'Ölçek', 'Scale')} value={state.skyScale} onChange={id => setAppState({ skyScale: id, playing: false })}
    items={[{ id: 'galaxy', label: T(lang, 'Samanyolu', 'Milky Way'), icon: 'galaxy' }, { id: 'local', label: T(lang, 'Güneş’in çevresi', 'Around the Sun'), icon: 'orbit' }]} />
}

export function GalaxyColumn({ lang }: { lang: Lang }) {
  const camera = (action: string) => window.dispatchEvent(new CustomEvent('blinkspace:camera', { detail: { action } }))
  return <Who top={132} kicker={T(lang, 'Temsili çizim, üstten görünüm', 'Illustration, seen from above')} title={T(lang, 'Samanyolu', 'Milky Way')} icon="galaxy" phase={T(lang, 'İçinde yaşadığımız gökada', 'The galaxy we live in')}>
    <p className="lv-say">{T(lang, 'Turuncu işaret Güneş. Merkezden yaklaşık 26.700 ışık yılı uzakta, Orion Kolu’ndayız. SPHEREx ile baktığımız beş hedefin hepsi bu işaretin hemen yanında.',
      'The orange marker is the Sun. We are about 26,700 light-years from the centre, in the Orion Spur. All five targets we look at with SPHEREx sit right next to that marker.')}</p>
    <dl className="lv-facts">
      <div><dt>{T(lang, 'Gökadanın çapı', 'Width of the galaxy')}</dt><dd>{T(lang, '≈ 100.000 ışık yılı', '≈ 100,000 light-years')}</dd></div>
      <div><dt>{T(lang, 'Yıldız sayısı', 'Number of stars')}</dt><dd>{T(lang, '100–400 milyar', '100–400 billion')}</dd></div>
      <div><dt>{T(lang, 'Güneş’in bir turu', 'One lap of the Sun')}</dt><dd>{T(lang, '≈ 230 milyon yıl', '≈ 230 million years')}</dd></div>
    </dl>
    <div className="lv-actions">
      <button type="button" className="kx-act kx-solid kx-press lv-wide" onClick={() => setAppState({ skyScale: 'local' })}><KIcon name="orbit" />{T(lang, 'Güneş’in çevresine in', 'Fly down to the Sun’s neighbourhood')}</button>
      <button type="button" className="kx-act kx-glass kx-press" onClick={() => camera('face-on')}><KIcon name="galaxy" />{T(lang, 'Tam üstten bak', 'Look from above')}</button>
      <button type="button" className="kx-act kx-glass kx-press" onClick={() => camera('reset')}><KIcon name="reset" />{T(lang, 'Görünümü sıfırla', 'Reset the view')}</button>
    </div>
  </Who>
}

/* ------------------------------------------------- catalogue star and sky */
export function CatalogueColumn({ state, lang, targets, star, title, onSelect, onSearch }: { state: AppState; lang: Lang; targets: Target[]; star: MotionStar | null; title: string; onSelect: (id: string) => void; onSearch: () => void }) {
  const sky = state.mode === 'neighbors'
  return <Who top={132} kicker={sky ? T(lang, 'Gaia DR3 · 120 yakın yıldız', 'Gaia DR3 · 120 nearby stars') : T(lang, 'Katalog değerleri · temsili 3B yüzey', 'Catalogue values · illustrative 3D surface')} title={title} icon={sky ? 'orbit' : 'surface'}
    phase={(lang === 'tr' ? star?.subtitleTr : star?.subtitleEn) ?? T(lang, 'Katalog yıldızı', 'Catalogue star')}>
    <TargetTabs targets={targets} value={state.targetId} onSelect={onSelect} lang={lang} />
    <p className="lv-say">{sky ? T(lang, 'Güneş’in çevresindeki yıldızlar gerçek katalog konumlarında. Alttaki cetvelle yılı değiştir; hareket katalogdan hesaplanır.', 'The stars around the Sun at their catalogue positions. Change the year on the ruler below; the motion is computed from the catalogue.')
      : T(lang, 'Sıcaklık, yarıçap ve konum katalogdan gelir. Yüzey ve çevresi temsili olarak çizilir.', 'Temperature, radius and position come from the catalogue. The surface and surroundings are drawn as an illustration.')}</p>
    <div className="lv-actions">
      {!sky && <Glider small className="lv-wide" label={T(lang, 'Kadraj', 'Framing')} value={state.sceneFraming} onChange={v => setAppState({ sceneFraming: v })}
        items={[{ id: 'detail', label: T(lang, 'Yakın plan', 'Close-up') }, { id: 'context', label: T(lang, 'Çevre ve iz', 'Environment & trail') }]} />}
      <button type="button" className="kx-act kx-glass kx-press" onClick={() => { if (!sky) setAppState({ mode: 'neighbors', playing: false }); else window.dispatchEvent(new CustomEvent('blinkspace:camera', { detail: { action: 'focus' } })) }}><KIcon name="orbit" />{sky ? T(lang, 'Hedefe odaklan', 'Focus target') : T(lang, 'Gökyüzünde gör', 'See it in the sky')}</button>
      {sky && <button type="button" className="kx-act kx-glass kx-press" onClick={onSearch}><KIcon name="search" />{T(lang, 'Yıldız ara', 'Find a star')}<kbd className="lv-kbd">Ctrl K</kbd></button>}
      <button type="button" className="kx-act kx-glass kx-press lv-wide" onClick={() => setAppState({ mode: 'observations', playing: false })}><KIcon name="frames" />{T(lang, 'Gerçek SPHEREx kareleri', 'Real SPHEREx frames')}</button>
    </div>
  </Who>
}

export function catalogueChips(lang: Lang, star: MotionStar | null, year: number, parameter: (key: string) => string, open: () => void): ChipItem[] {
  const c = star && skyCoordinates(star, year), n = (v: number, d = 2) => new Intl.NumberFormat(lang, { maximumFractionDigits: d }).format(v)
  const radius = parameter('radius_solar'), teff = parameter('teff_k'), missing = T(lang, 'katalogda yok', 'not in the catalogue')
  // No model profile for most catalogue stars: fall back to what Gaia measured (brightness, colour) instead of a dash.
  const first: ChipItem = radius !== '—' ? { label: T(lang, 'Yarıçap', 'Radius'), value: radius, unit: 'R☉', onClick: open }
    : star?.magnitude !== undefined ? { label: T(lang, 'Parlaklık · Gaia G', 'Brightness · Gaia G'), value: n(star.magnitude), unit: T(lang, 'kadir', 'mag'), onClick: open }
    : { label: T(lang, 'Yarıçap', 'Radius'), value: missing, onClick: open }
  const second: ChipItem = teff !== '—' ? { label: T(lang, 'Sıcaklık', 'Temperature'), value: teff, unit: 'K', onClick: open }
    : star?.teff_k ? { label: T(lang, 'Sıcaklık · katalog', 'Temperature · catalogue'), value: n(star.teff_k, 0), unit: 'K', onClick: open }
    : star?.colorIndex !== undefined ? { label: T(lang, 'Renk · BP−RP', 'Colour · BP−RP'), value: n(star.colorIndex), unit: T(lang, 'kadir', 'mag'), onClick: open }
    : { label: T(lang, 'Sıcaklık', 'Temperature'), value: missing, onClick: open }
  return [
    first, second,
    { label: T(lang, 'Uzaklık', 'Distance'), value: star ? n(distanceLy(star, year)) : '—', unit: T(lang, 'ışık yılı', 'ly'), onClick: open },
    { label: 'ICRS · RA / Dec', value: c ? `${c.ra.toFixed(3)}° / ${c.dec >= 0 ? '+' : ''}${c.dec.toFixed(3)}°` : '—', onClick: open },
  ]
}

const SPEEDS = [1, 5, 20] as const
export function YearStrip({ state, lang }: { state: AppState; lang: Lang }) {
  const year = state.year, majors: RulerMajor[] = []
  for (let y = 2000; y <= 2100; y += 10) majors.push({ at: y, label: y % 20 === 0 ? String(y) : undefined })
  const toggle = () => setAppState({ playing: !state.playing, ...(state.year >= 2100 ? { year: 2000 } : {}) })
  return <section className="kx kx-time" aria-label={T(lang, 'Konum yılı', 'Position year')}>
    <RingPlay playing={state.playing} onToggle={toggle} progress={(year - 2000) / 100} segments={10} labelPlay={T(lang, 'Oynat', 'Play')} labelPause={T(lang, 'Duraklat', 'Pause')} />
    <button type="button" className="kx-speed kx-glass kx-press" aria-label={T(lang, 'Oynatma hızı', 'Playback speed')} onClick={() => setAppState({ speedYearsPerSec: SPEEDS[(SPEEDS.indexOf(state.speedYearsPerSec) + 1) % SPEEDS.length] })}>
      <span key={state.speedYearsPerSec}>{state.speedYearsPerSec} {T(lang, 'yıl/sn', 'yr/s')}</span></button>
    <div className="lv-track">
      <WaveRuler value={year} min={2000} max={2100} minorStep={1} step={0.1} pageStep={10} majors={majors} label={T(lang, 'Konum yılı', 'Position year')} valueText={String(Math.floor(year))}
        tip={v => String(Math.round(v))} onChange={v => setAppState({ year: Math.min(2100, Math.max(2000, v)), playing: false })} />
      <RulerLabels majors={majors} min={2000} max={2100} />
    </div>
    <div className="kx-time-read"><Odometer text={String(Math.floor(year))} instant={state.playing && state.speedYearsPerSec >= 20} /><small>{T(lang, 'konum yılı', 'position year')}</small><em>{T(lang, 'katalogdan doğrusal hareket', 'linear motion from the catalogue')}</em></div>
  </section>
}

/* -------------------------------------------------------- published model */
const PHASE_ICON = 'table'
export function EvolutionColumn({ state, lang, targets, star, title, onSelect }: { state: AppState; lang: Lang; targets: Target[]; star: MotionStar | null; title: string; onSelect: (id: string) => void }) {
  const track = evolutionTrack(state.evolutionTrack), sample = evolutionAt(track, state.evolutionProgress), suggested = suggestedTrack(star?.id ?? null)
  const known = ['barnard', 'eps-indi-b', 'wise-0855', 'rw-aur', 'r-dra'].includes(star?.id ?? '')
  return <Who top={132} kicker={`${track.source} · ${track.mass} M☉ · ${T(lang, 'yayımlanmış karşılaştırma modeli', 'published comparison track')}`} title={title} icon={PHASE_ICON} phase={phaseLabel(sample.phase, lang, sample.endpoint)}>
    <TargetTabs targets={targets} value={state.targetId} onSelect={onSelect} lang={lang} />
    <p className="lv-say">{T(lang, 'Bu, seçili yıldızın ölçülmüş yaşı ya da kesin geleceği değil; kütlesine en yakın yayımlanmış evrim tablosu.', 'This is not the selected star’s measured age or certain future; it is the published evolution table closest to its mass.')}
      {['eps-indi-b', 'wise-0855'].includes(star?.id ?? '') && <> {T(lang, 'Kahverengi cüce soğuma modeli: ana kol ya da süpernova evresi yok.', 'A brown dwarf cooling track: no main sequence or supernova stage.')}</>}
      {star?.id === 'eps-indi-b' && <> {T(lang, 'İkili sistem tek cisim olarak karşılaştırılır.', 'The binary is compared as a single object.')}</>}
      {!known && <> {T(lang, 'Bu katalog hedefi için eşleştirilmiş tablo yok; model genel bir karşılaştırmadır.', 'No matched table for this catalogue target; the model is a general comparison.')}</>}</p>
    <label className="lv-field"><span>{T(lang, 'Karşılaştırma modeli · başlangıç kütlesi', 'Comparison model · initial mass')}</span>
      <select id="evolution-track" value={track.id} onChange={e => setAppState({ evolutionTrack: e.target.value, evolutionProgress: 0, evolutionPlaying: false })}>
        {evolutionTracks.map(t => <option key={t.id} value={t.id}>{t.source} · {t.mass} M☉</option>)}</select></label>
    <div className="lv-actions">
      {track.id !== suggested && <button type="button" className="kx-act kx-glass kx-press lv-wide" onClick={() => setAppState({ evolutionTrack: suggested, evolutionProgress: 0, evolutionPlaying: false })}><KIcon name="reset" />{T(lang, 'Hedefin önerilen modeline dön', 'Use target’s suggested model')}</button>}
      <button type="button" className="kx-act kx-solid kx-press lv-wide" onClick={() => setAppState({ mode: 'observations', playing: false, evolutionPlaying: false })}><KIcon name="frames" />{T(lang, 'Gerçek SPHEREx gözlemlerine dön', 'Return to real SPHEREx observations')}</button>
    </div>
    <details className="lv-details"><summary>{T(lang, 'Model kapsamı ve kaynak', 'Model scope and source')}</summary>
      <p>{T(lang, 'Tablodaki sıcaklık, yarıçap ve ışınım birlikte değişir. Yarıçap logaritmik olarak sıkıştırılır; yüzey ve akış yapıları temsili. Tablonun ötesine tahmin yapılmaz.', 'Temperature, radius and luminosity change together from the published table. Radius is logarithmically compressed; surface and flows are illustrative. No extrapolation beyond the table.')}</p>
      <p><a href={track.url} target="_blank" rel="noreferrer">{track.source}</a> · {track.composition}</p></details>
  </Who>
}

export function evolutionChips(lang: Lang, state: AppState): ChipItem[] {
  const s = evolutionAt(evolutionTrack(state.evolutionTrack), state.evolutionProgress), f = (n: number) => new Intl.NumberFormat(lang, { maximumSignificantDigits: 4 }).format(n)
  return [
    { label: T(lang, 'Yarıçap', 'Radius'), value: f(s.radius), unit: 'R☉' },
    { label: T(lang, 'Sıcaklık', 'Temperature'), value: f(s.temperature), unit: 'K' },
    { label: T(lang, 'Işınım gücü', 'Luminosity'), value: f(s.luminosity), unit: 'L☉' },
    { label: T(lang, 'Kütle', 'Mass'), value: f(s.mass), unit: 'M☉' },
  ]
}

const charts = new Map(evolutionTracks.map(track => {
  const xs = track.rows.map(r => Math.log10(r[1])), ys = track.rows.map(r => Math.log10(r[3]))
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys)
  const x = (t: number) => 10 + (x1 - Math.log10(t)) / (x1 - x0 || 1) * 170, y = (l: number) => 10 + (y1 - Math.log10(l)) / (y1 - y0 || 1) * 68
  return [track.id, { x, y, pts: track.rows.map(r => `${x(r[1]).toFixed(1)},${y(r[3]).toFixed(1)}`), tMax: Math.pow(10, x1), tMin: Math.pow(10, x0) }] as const
}))
export function EvolutionHR({ state, lang }: { state: AppState; lang: Lang }) {
  const track = evolutionTrack(state.evolutionTrack), s = evolutionAt(track, state.evolutionProgress), c = charts.get(track.id)!
  const now = `${c.x(s.temperature).toFixed(1)},${c.y(s.luminosity).toFixed(1)}`, n = new Intl.NumberFormat(lang, { maximumSignificantDigits: 3 })
  return <figure className="kx lv-hr kx-glass" aria-label={T(lang, 'Modelin sıcaklık–ışınım yolu', 'Model temperature–luminosity track')}>
    <figcaption>{T(lang, 'HR yolu', 'HR track')} <span>{T(lang, 'kaynak tablosu', 'source table')}</span></figcaption>
    <svg viewBox="0 0 190 100" width="188" height="99" fill="none" role="img" aria-label={T(lang, 'Sıcak solda, parlak üstte', 'Hot on the left, bright at the top')}>
      <path d="M4 3v82h183" stroke="rgba(156,178,238,.5)" />
      <polyline points={[now, ...c.pts.slice(s.index + 1)].join(' ')} stroke="rgba(198,211,247,.55)" strokeWidth="1.2" strokeDasharray="2.5 3.5" />
      <polyline points={[...c.pts.slice(0, s.index + 1), now].join(' ')} stroke="#fff" strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={c.x(s.temperature)} cy={c.y(s.luminosity)} r="8" fill="rgba(255,106,26,.26)" /><circle cx={c.x(s.temperature)} cy={c.y(s.luminosity)} r="4" fill="#ff6a1a" stroke="#0a1634" strokeWidth="1.3" />
      <text x="4" y="98">{n.format(c.tMax)} K</text><text x="187" y="98" textAnchor="end">{n.format(c.tMin)} K</text>
    </svg>
    <i className="lv-swatch" style={{ background: `rgb(${temperatureToRgb(s.temperature).join(',')})` }} title={T(lang, 'Bu sıcaklığın kara cisim rengi', 'Blackbody colour at this temperature')} />
  </figure>
}

export function EvolutionStrip({ state, lang }: { state: AppState; lang: Lang }) {
  const track = evolutionTrack(state.evolutionTrack), sample = evolutionAt(track, state.evolutionProgress), last = track.rows.length - 1
  const stops = track.rows.map((r, i) => ({ phase: r[5], p: i / last })).filter((s, i, a) => i === 0 || s.phase !== a[i - 1].phase)
  const majors: RulerMajor[] = [...stops.map(s => ({ at: s.p })), { at: 1 }]
  const age = formatAge(sample.age, lang), m = /^([\d.,\s]+?)\s+(.+)$/.exec(age), num = m ? m[1] : age, unit = m ? m[2] : ''
  const toggle = () => setAppState({ evolutionPlaying: !state.evolutionPlaying, ...(state.evolutionProgress >= 1 ? { evolutionProgress: 0 } : {}) })
  return <section className="kx kx-time lv-evo" aria-label={T(lang, 'Yaşam evrimi zaman çizelgesi', 'Evolution timeline')}>
    <RingPlay playing={state.evolutionPlaying} onToggle={toggle} progress={state.evolutionProgress} segments={stops.length} labelPlay={T(lang, 'Evrimi oynat', 'Play evolution')} labelPause={T(lang, 'Evrimi duraklat', 'Pause evolution')} />
    <span />
    <div className="lv-track">
      <WaveRuler value={state.evolutionProgress} min={0} max={1} minorStep={0.0125} step={0.0005} pageStep={0.1} majors={majors} label={T(lang, 'Evrim ilerlemesi', 'Evolution progress')} valueText={`${phaseLabel(sample.phase, lang, sample.endpoint)}, ${age}`}
        tip={v => { const s = evolutionAt(track, v); return `${phaseLabel(s.phase, lang, s.endpoint)} · ${formatAge(s.age, lang)}` }} onChange={v => setAppState({ evolutionProgress: Math.min(1, Math.max(0, v)), evolutionPlaying: false })} />
      <div className="kx-marks">{stops.map((s, i) => {
        const next = stops[i + 1]?.p ?? 1, roomy = next - s.p >= 0.1, on = sample.phase === s.phase
        // The active stage always shows its name; a neighbour whose label would sit under that name keeps only its dot.
        const active = stops.find(x => x.phase === sample.phase), activeNext = active ? stops[stops.indexOf(active) + 1]?.p ?? 1 : 1
        const shadowed = !on && !!active && activeNext - active.p < 0.2 && (active.p > 0.78 ? s.p < active.p && active.p - s.p < 0.2 : s.p > active.p && s.p - active.p < 0.2)
        const end = on && s.p > 0.78
        // A label is drawn only where the stage is wide enough; narrow stages keep their dot and show the name while active.
        return <button type="button" key={s.phase} className={`kx-mark ${on ? 'kx-on' : ''} ${roomy ? '' : 'kx-tight'} ${shadowed ? 'kx-mute' : ''} ${end ? 'kx-end' : ''}`} style={{ left: `${s.p * 100}%`, maxWidth: roomy && !on ? `calc(${(next - s.p) * 100}% + 4px)` : undefined }} aria-pressed={on} aria-label={phaseLabel(s.phase, lang)} title={phaseLabel(s.phase, lang)}
          onClick={() => setAppState({ evolutionProgress: s.p, evolutionPlaying: false })}><i aria-hidden="true" /><span><b>{phaseLabel(s.phase, lang)}</b></span></button>
      })}</div>
    </div>
    <div className="kx-time-read"><Odometer text={num} instant={state.evolutionPlaying} /><small>{unit} · {T(lang, 'model yaşı', 'model age')}</small><em>{T(lang, 'evre ilerlemesi · eşit yıl aralıkları değil', 'stage progress · not equal year steps')}</em></div>
  </section>
}

/* ------------------------------------------------------------ mode switch */
export function ModeSwitch({ state, lang }: { state: AppState; lang: Lang }) {
  return <Glider className="lv-modes" label={T(lang, 'Model türü', 'Model type')} value={state.stellarMode}
    onChange={id => setAppState({ stellarMode: id, playing: false, evolutionPlaying: false })}
    items={[{ id: 'surface', label: T(lang, 'Katalog yıldızı', 'Catalogue star'), icon: 'surface' }, { id: 'evolution', label: T(lang, 'Kaynaklı model', 'Published model'), icon: 'table' }, { id: 'education', label: T(lang, 'Eğitim modeli', 'Education model'), icon: 'learn' }]} />
}

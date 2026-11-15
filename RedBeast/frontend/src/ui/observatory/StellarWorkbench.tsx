import { setAppState, type AppState } from '../../lib/store'
import type { MotionStar } from '../../three/types'
import { skyCoordinates } from '../../three/science/astrometry'
import { evolutionAt, evolutionTrack, evolutionTracks, formatAge, phaseLabel, suggestedTrack } from '../../three/science/evolution'
import { temperatureToRgb } from '../../three/science/blackbody'

export function StellarWorkbench({ state, star, showModeSwitch = true }: { state: AppState; star: MotionStar | null; showModeSwitch?: boolean }) {
  const tr = state.lang === 'tr', evolving = state.mode === 'star' && state.stellarMode === 'evolution'
  const track = evolutionTrack(state.evolutionTrack), coord = star && skyCoordinates(star, state.year)
  const f = (v: number, digits = 4) => new Intl.NumberFormat(state.lang, { maximumFractionDigits: digits, useGrouping: false }).format(v)
  return <div className="stellar-workbench">
    {state.mode === 'star' && showModeSwitch && <div className="sx-tabs sx-glass stellar-mode" aria-label={tr ? 'Yıldız zaman ölçeği' : 'Stellar time scale'}>
      <button aria-pressed={!evolving} onClick={() => setAppState({ stellarMode: 'surface', evolutionPlaying: false })}>{tr ? 'Gözlenen sistem' : 'Observed system'}</button>
      <button aria-pressed={evolving} onClick={() => setAppState({ stellarMode: 'evolution', evolutionTrack: suggestedTrack(star?.id ?? null), evolutionProgress: 0, evolutionPlaying: false, playing: false })}>{tr ? 'Yaşam evrimi' : 'Evolution'}</button>
    </div>}
    {evolving ? <div className="stellar-explanation">
      <p className="stellar-target-link">{tr ? 'Seçili hedef' : 'Selected target'}: <strong>{star?.name ?? '—'}</strong><br/>{tr ? 'Önerilen karşılaştırma' : 'Suggested comparison'}: {evolutionTrack(suggestedTrack(star?.id ?? null)).source} · {evolutionTrack(suggestedTrack(star?.id ?? null)).mass} M☉</p>
      {track.id !== suggestedTrack(star?.id ?? null) && <button className="sx-action" onClick={()=>setAppState({evolutionTrack:suggestedTrack(star?.id??null),evolutionProgress:0,evolutionPlaying:false})}>{tr?'Hedefin önerilen modeline dön':'Use target’s suggested model'}</button>}
      {['eps-indi-b','wise-0855'].includes(star?.id??'')&&<p>{tr?'Bu bir kahverengi cüce soğuma modelidir; Güneş gibi bir ana kol veya süpernova döngüsü uygulanmaz.':'This is a brown dwarf cooling track; a solar main-sequence or supernova cycle does not apply.'}</p>}
      {star?.id==='eps-indi-b'&&<p>{tr?'İkili sistem için tek bileşenli karşılaştırma; iki cismin ortak evrimini çözmez.':'Single-object comparison for a binary system; does not solve both components’ evolution.'}</p>}
      {!['barnard','eps-indi-b','wise-0855','rw-aur','r-dra'].includes(star?.id??'')&&<p>{tr?'Bu katalog hedefi için eşleştirilmiş evrim tablosu yok. Aşağıdaki model genel bir karşılaştırmadır.':'No matched evolution track for this catalogue target. The model below is a general comparison.'}</p>}
      <button className="sx-action" onClick={()=>setAppState({mode:'observations',playing:false,evolutionPlaying:false})}>{tr?'Gerçek SPHEREx gözlemlerine dön':'Return to real SPHEREx observations'} ↗</button>
      <label htmlFor="evolution-track">{tr ? 'Karşılaştırma modeli · başlangıç kütlesi' : 'Comparison model · initial mass'}</label>
      <select id="evolution-track" value={track.id} onChange={e => setAppState({ evolutionTrack: e.target.value, evolutionProgress: 0, evolutionPlaying: false })}>
        {evolutionTracks.map(t => <option key={t.id} value={t.id}>{t.source} · {t.mass} M☉</option>)}
      </select>
      <details className="stellar-model-limits"><summary>{tr?'Model kapsamı ve kaynak':'Model scope and source'}</summary><p>{tr ? 'Bu, seçili yıldızın ölçülmüş yaşı veya kesin geleceği değildir. Tablodaki sıcaklık, yarıçap ve ışınım birlikte değişir.' : 'This is not the selected star’s measured age or certain future. Temperature, radius and luminosity change together from the published table.'}</p>
      <p>{tr ? 'Yarıçap logaritmik olarak sıkıştırılır; yüzey ve akış yapıları temsili. Tablonun ötesine tahmin yapılmaz.' : 'Radius is logarithmically compressed; surface and flows are illustrative. No extrapolation beyond the table.'}</p>
      <a href={track.url} target="_blank" rel="noreferrer">{track.source} ↗</a><small>{track.composition}</small></details>
    </div> : <>
      {state.mode === 'star' && <div className="stellar-view-controls">
        <div className="sx-tabs sx-glass"><button aria-pressed={state.sceneFraming === 'detail'} onClick={() => setAppState({ sceneFraming: 'detail' })}>{tr ? 'Yakın plan' : 'Close-up'}</button><button aria-pressed={state.sceneFraming === 'context'} onClick={() => setAppState({ sceneFraming: 'context' })}>{tr ? 'Çevre ve iz' : 'Environment & trail'}</button></div>
        <button className="sx-action" aria-pressed={state.surfacePlaying} onClick={() => setAppState({ surfacePlaying: !state.surfacePlaying })}>{state.surfacePlaying ? 'Ⅱ' : '▶'} {tr ? 'Yüzey ve akış animasyonu' : 'Surface & flow animation'}</button>
        <small>{tr ? 'Temsili hareket · takvimden bağımsız' : 'Illustrative motion · independent of calendar'}</small>
      </div>}
      {coord && <div className="stellar-coordinates"><details><summary>ICRS · {f(state.year, 1)} · RA / Dec</summary><dl><div><dt>RA</dt><dd>{f(coord.ra)}°</dd></div><div><dt>Dec</dt><dd>{f(coord.dec)}°</dd></div><div><dt>{tr ? 'Uzaklık' : 'Distance'}</dt><dd>{f(coord.distancePc, 3)} pc</dd></div></dl>
        <small>{tr ? 'Güneş merkezli doğrusal hareket; paralaks ve gözlemci etkisi yok.' : 'Heliocentric linear motion; no observer or parallax effect.'} {!star!.hasRadialVelocity && (tr ? 'Radyal hız 0 varsayılır.' : 'Radial velocity assumed 0.')}</small></details>
        <button className="sx-action" onClick={() => {
          if (state.mode !== 'neighbors') setAppState({ mode: 'neighbors', playing: false })
          else window.dispatchEvent(new CustomEvent('blinkspace:camera', { detail: { action: 'focus' } }))
        }}>{tr ? (state.mode === 'neighbors' ? 'Hedefe odaklan' : '3B uzayda bul') : (state.mode === 'neighbors' ? 'Focus target' : 'Locate in 3D space')} ↗</button>
      </div>}
    </>}
  </div>
}

const trackCharts = new Map(evolutionTracks.map(track => {
    const xs = track.rows.map(r => Math.log10(r[1])), ys = track.rows.map(r => Math.log10(r[3]))
    const xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys)
    const x = (t: number) => 24 + (xmax - Math.log10(t)) / (xmax - xmin || 1) * 166
    const y = (l: number) => 16 + (ymax - Math.log10(l)) / (ymax - ymin || 1) * 90
    return [track.id, { x, y, path: track.rows.map((r, i) => `${i ? 'L' : 'M'}${x(r[1]).toFixed(2)},${y(r[3]).toFixed(2)}`).join(' '), ymin, ymax }] as const
}))

export function EvolutionReadout({ state }: { state: AppState }) {
  const tr = state.lang === 'tr', track = evolutionTrack(state.evolutionTrack), sample = evolutionAt(track, state.evolutionProgress)
  const f = (n: number) => new Intl.NumberFormat(state.lang, { maximumSignificantDigits: 4 }).format(n)
  const chart = trackCharts.get(track.id)!
  return <aside className="evolution-readout sx-glass" aria-label={tr ? 'Evrim modelinin değerleri' : 'Evolution model values'}>
    <span className="stellar-kicker">{tr ? 'KURAMSAL MODEL' : 'THEORETICAL MODEL'}</span>
    <h2>{phaseLabel(sample.phase, state.lang, sample.endpoint)}</h2>
    <dl>{[[tr ? 'Sıcaklık' : 'Temperature', `${f(sample.temperature)} K`], [tr ? 'Yarıçap' : 'Radius', `${f(sample.radius)} R☉`], [tr ? 'Işınım gücü' : 'Luminosity', `${f(sample.luminosity)} L☉`], [tr ? 'Kalan kütle' : 'Current mass', `${f(sample.mass)} M☉`]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    <figure><svg viewBox="0 0 210 135" role="img" aria-label={tr ? 'Modelin sıcaklık–ışınım evrim yolu' : 'Model temperature–luminosity track'}><path d="M24 10 V110 H200" fill="none" stroke="currentColor" opacity=".3" /><path d={chart.path} fill="none" stroke="currentColor" opacity=".55" strokeWidth="1.2" /><circle cx={chart.x(sample.temperature)} cy={chart.y(sample.luminosity)} r="4" fill={`rgb(${temperatureToRgb(sample.temperature).join(',')})`} stroke="white" /><text x="106" y="130" textAnchor="middle">← T (K)</text><text x="8" y="65" transform="rotate(-90 8 65)" textAnchor="middle">log L/L☉</text></svg><figcaption>{tr ? 'H–R yolu · kaynak tablosu' : 'H–R track · source table'}</figcaption></figure>
    {sample.temperature < 1000 && <p>{tr ? 'Görünür ışık yayımı çok zayıf; karanlık model gösterilir.' : 'Visible emission is extremely faint; shown as a dark model.'}</p>}
  </aside>
}

export function EvolutionTimeline({ state }: { state: AppState }) {
  const tr = state.lang === 'tr', track = evolutionTrack(state.evolutionTrack), sample = evolutionAt(track, state.evolutionProgress)
  const stops = track.rows.map((r, i) => ({ phase: r[5], p: i / (track.rows.length - 1) })).filter((s, i, a) => i === 0 || s.phase !== a[i - 1].phase)
  return <section className="sx-timeline evolution-timeline" aria-label={tr ? 'Yaşam evrimi zaman çizelgesi' : 'Evolution timeline'}>
    <button className="sx-play sx-glass" aria-label={state.evolutionPlaying ? (tr ? 'Evrimi duraklat' : 'Pause evolution') : (tr ? 'Evrimi oynat' : 'Play evolution')} onClick={() => setAppState({ evolutionPlaying: !state.evolutionPlaying, ...(state.evolutionProgress >= 1 ? { evolutionProgress: 0 } : {}) })}>{state.evolutionPlaying ? 'Ⅱ' : '▶'}</button>
    <div className="sx-ruler"><div className="sx-year-label"><span>{formatAge(sample.age, state.lang)} · {tr ? 'model yaşı' : 'model age'}</span><span>{tr ? 'Evre ilerlemesi · eşit yıl aralıkları değil' : 'Stage progress · not equal year intervals'}</span></div>
      <input type="range" min="0" max="1" step="0.0001" value={state.evolutionProgress} aria-label={tr ? 'Evrim ilerlemesi' : 'Evolution progress'} onChange={e => setAppState({ evolutionProgress: Number(e.target.value), evolutionPlaying: false })} />
      <div className="evolution-stages">{stops.map(s => <button key={s.phase} aria-pressed={sample.phase === s.phase} onClick={() => setAppState({ evolutionProgress: s.p, evolutionPlaying: false })}>{phaseLabel(s.phase, state.lang)}</button>)}<button onClick={() => setAppState({ evolutionProgress: 1, evolutionPlaying: false })}>{tr ? 'Veri sınırı' : 'Table endpoint'}</button></div>
    </div>
  </section>
}

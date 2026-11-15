import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { getAppState, setAppState, subscribeAppState } from '../lib/store'
import type { AppState } from '../lib/store'
import type { Mark, Sequence } from '../lib/types'
import { translate, translateCode, useI18n } from '../i18n'
import type { SkyRuntime } from './runtime'
import type { ModelCatalogue, MotionCatalogue, MotionStar, SceneData, SequenceTrack } from './types'
import { selectedStar } from './types'
import { angularShift, AU_PER_MOTION_UNIT, compass, distanceLy } from './science/astrometry'
import { componentParameter, parameter } from './science/models'
import { evolutionAt, evolutionTrack, formatAge, phaseLabel } from './science/evolution'
import './scene.css'

export interface SkyCanvasProps {
  state: AppState
  catalogue?: MotionCatalogue | null
  sequence: Sequence | null
  track?: SequenceTrack | null
  marks?: Mark[]
  models?: ModelCatalogue | null
  onSelectTarget?: (id: string) => void
  onSelectFrame?: (index: number) => void
}

function MotionFallback({ star, lang }: { star: MotionStar; lang: 'tr' | 'en' }) {
  const t = (key: Parameters<typeof translate>[1]) => translate(lang, key)
  const number = (value: number, digits = 2) => new Intl.NumberFormat(lang === 'tr' ? 'tr-TR' : 'en-US', { maximumFractionDigits: digits }).format(value)
  const points = [2026, 2050, 2100].map((year) => ({ year, ...angularShift(star, 2026, year) }))
  const max = Math.max(1, ...points.flatMap((p) => [Math.abs(p.eastArcsec), Math.abs(p.northArcsec)]))
  const path = points.map((p, index) => `${index ? 'L' : 'M'} ${150 - p.eastArcsec / max * 110} ${150 - p.northArcsec / max * 110}`).join(' ')
  return <>
    <svg viewBox="0 0 300 200" role="img" aria-label={t('sky.motionSvg')}>
      <path d="M 150 18 V 180 M 20 150 H 280" className="fallback-axis" />
      <path d={path} className="fallback-trail" />
      {points.map((p) => <g key={p.year}><circle cx={150 - p.eastArcsec / max * 110} cy={150 - p.northArcsec / max * 110} r="3" /><text x={158 - p.eastArcsec / max * 110} y={147 - p.northArcsec / max * 110}>{p.year}</text></g>)}
      <text x="155" y="20">N</text><text x="20" y="140">E</text>
    </svg>
    <table><thead><tr><th>{t('sky.year')}</th><th>{t('sky.shiftFrom2026')}</th><th>{t('sky.direction')}</th></tr></thead>
      <tbody>{points.map((p) => <tr key={p.year}><td>{p.year}</td><td>{number(p.arcsec)}″</td><td>{p.arcsec < .001 ? '—' : compass(p.bearingDeg, lang)}</td></tr>)}</tbody></table>
  </>
}

function Fallback({ state, data, reason }: { state: AppState; data: SceneData; reason: string }) {
  const star = selectedStar(data, state)
  const t = (key: Parameters<typeof translate>[1]) => translate(state.lang, key)
  const number = (value: number, digits = 2) => new Intl.NumberFormat(state.lang === 'tr' ? 'tr-TR' : 'en-US', { maximumFractionDigits: digits }).format(value)
  return <div className="sky-fallback" role="region" aria-label={t('sky.dataView')}>
    <p>{t(reason === 'lost' ? 'sky.restore' : 'sky.unavailable')}</p>
    {state.mode === 'star' && star && <MotionFallback star={star} lang={state.lang} />}
    {state.mode === 'neighbors' && <table><thead><tr><th>{t('sky.star')}</th><th>{t('sky.distanceLy')}</th><th>{t('sky.spectralType')}</th></tr></thead>
      <tbody>{[...(data.catalogue?.stars ?? [])].sort((a, b) => a.distancePc - b.distancePc).map((s) => <tr key={s.id}><td><button type="button" onClick={() => data.onSelectTarget?.(s.id)}>{s.name}</button></td><td>{number(distanceLy(s, state.year))}</td><td>{s.spectralType || '—'}</td></tr>)}</tbody></table>}
    {state.mode === 'observations' && <table><thead><tr><th>{t('sky.frame')}</th><th>UTC</th><th>λ (µm)</th></tr></thead>
      <tbody>{data.sequence?.frames.map((frame, index) => <tr key={frame.obs_id}><td><button type="button" onClick={() => data.onSelectFrame?.(index)}>#{index + 1}</button></td><td>{frame.date_avg}</td><td>{number(frame.lam_um, 4)}</td></tr>)}</tbody></table>}
  </div>
}

export default function SkyCanvas(props: SkyCanvasProps) {
  const { t } = useI18n()
  const { state } = props
  const [ownCatalogue, setOwnCatalogue] = useState<MotionCatalogue | null>(null)
  const [ownModels, setOwnModels] = useState<ModelCatalogue | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'lost' | 'unavailable'>('loading')
  const [errorReason,setErrorReason]=useState('')
  const canvas = useRef<HTMLCanvasElement>(null), labels = useRef<HTMLDivElement>(null)
  const runtime = useRef<SkyRuntime | null>(null)
  const catalogue = props.catalogue === undefined ? ownCatalogue : props.catalogue
  const models = props.models === undefined ? ownModels : props.models
  const data = useMemo<SceneData>(() => ({ catalogue, sequence: props.sequence, track: props.track ?? null,
    marks: props.marks, models, onSelectTarget: props.onSelectTarget, onSelectFrame: props.onSelectFrame }),
  [catalogue, models, props.sequence, props.track, props.marks, props.onSelectTarget, props.onSelectFrame])
  const latest = useRef({ state, data })
  useLayoutEffect(() => { latest.current = { state, data } }, [state, data])
  useEffect(() => {
    if (props.catalogue !== undefined) return
    const abort = new AbortController()
    fetch('/api/motion', { signal: abort.signal }).then((r) => { if (!r.ok) throw new Error('motion'); return r.json() })
      .then((value: MotionCatalogue) => setOwnCatalogue(value)).catch(() => undefined)
    return () => abort.abort()
  }, [props.catalogue])
  useEffect(() => {
    if (props.models !== undefined) return
    const abort = new AbortController()
    fetch('/api/models', { signal: abort.signal }).then((response) => {
      if (!response.ok) throw new Error('Models unavailable')
      return response.json()
    }).then((value: ModelCatalogue) => setOwnModels(value)).catch(() => undefined)
    return () => abort.abort()
  }, [props.models])
  useEffect(() => {
    let disposed = false
    import('./runtime').then(({ SkyRuntime: Runtime }) => {
      if (disposed || !canvas.current || !labels.current) return
      try {
        runtime.current = new Runtime(canvas.current, labels.current, latest.current.state, latest.current.data,
          status=>{setStatus(status);if(status==='ready')setErrorReason('')}, reason=>{setErrorReason(reason);setStatus('unavailable')}, (quality) => setAppState({ quality }))
        setStatus('ready')
      } catch { setStatus('unavailable') }
    }).catch(() => setStatus('unavailable'))
    // Render subscriptions read the shared store directly; no render loop depends on React.
    const unsubscribe = subscribeAppState(() => {
      void runtime.current?.update(getAppState(), latest.current.data)
    })
    return () => { disposed = true; unsubscribe(); runtime.current?.dispose(); runtime.current = null }
  }, [])
  useEffect(() => { void runtime.current?.update(state, data) }, [state, data])
  const star = selectedStar(data, state)
  const profile = models?.profiles.find(item => item.target_id === state.targetId) ?? null
  const modelTemperature = parameter(profile, 'teff_k') ?? star?.teff_k ?? null
  const number = (value: number, digits = 2) => new Intl.NumberFormat(state.lang === 'tr' ? 'tr-TR' : 'en-US', { maximumFractionDigits: digits }).format(value)
  const shift = star ? angularShift(star, 2026, state.year) : null
  const evolved = evolutionAt(evolutionTrack(state.evolutionTrack), state.evolutionProgress)
  const summary = state.mode === 'star' && state.stellarMode === 'evolution'
    ? `${state.lang === 'tr' ? 'Kuramsal evrim modeli' : 'Theoretical evolution model'}: ${phaseLabel(evolved.phase, state.lang, evolved.endpoint)}, ${formatAge(evolved.age, state.lang)}, ${number(evolved.temperature)} K`
    : state.mode === 'star' && star && shift
    ? t('sky.ariaStar', { name: star.name, year: number(state.year, 1), shift: number(shift.arcsec), direction: compass(shift.bearingDeg, state.lang) })
    : state.mode === 'neighbors' ? (state.skyScale === 'galaxy' ? t('sky.ariaGalaxy') : t('sky.ariaNeighbors', { count: catalogue?.stars.length ?? 0 }))
      : t('sky.ariaFrames', { count: data.sequence?.frames.length ?? 0 })
  const visible = state.mode !== 'observations' || state.stageView === 'timestack'
  const frame = props.track?.frames.find((point) => point.index === state.frameIndex)
  const missingReason = frame?.measured_reason ?? frame?.reason
  return <div className="sky-canvas" hidden={!visible} data-renderer="three" data-status={status} data-renderer-error={errorReason||undefined}>
    <canvas ref={canvas} role="img" aria-label={summary} tabIndex={0} />
    <div ref={labels} className="sky-labels" />
    {status === 'loading' && <p className="sky-loading" role="status">{t('sky.loading')}</p>}
    {(status === 'unavailable' || status === 'lost') && <Fallback state={state} data={data} reason={status} />}
    {state.mode === 'star' && state.stellarMode !== 'evolution' && star && <div className="sky-science-caption">
      {state.sceneFraming === 'context' && <span>{t('sky.motionScale', { au: number(AU_PER_MOTION_UNIT, 0) })}</span>}
      <span>{t('sky.motionLimits')}</span>
      {!star.hasRadialVelocity && <span className="assumed">{t('sky.rvAssumed')}</span>}
      {modelTemperature !== null && modelTemperature < 1000 && <span>{t('sky.cold', { temperature: number(modelTemperature, 0), source: profile?.parameters.teff_k?.source_ids?.join(', ') ?? star.teff_source })}</span>}
      {modelTemperature === null && !profile?.components?.length && <span>{t('sky.noTemperature')}</span>}
      {profile && <span>{t(parameter(profile, 'radius_solar') === null ? 'sky.radiusUnknown' : 'sky.radiusCompressed')}</span>}
      {profile?.components && profile.components.length > 1 && <span>{t('sky.binaryModel')} · {profile.components.map(component => `${component.name}: ${componentParameter(component, 'teff_k') === null ? '—' : number(componentParameter(component, 'teff_k')!, 0)} K`).join(' · ')}</span>}
      {profile && state.layers.environment !== false && <span>{t('sky.environmentSchematic')}</span>}
    </div>}
    {state.mode === 'star' && state.stellarMode === 'evolution' && <div className="sky-science-caption"><span>{state.lang === 'tr' ? 'Kuramsal evrim · SPHEREx karelerinden türetilmiş bir yaş veya yüzey haritası değil.' : 'Theoretical evolution · not an age or surface map inferred from SPHEREx frames.'}</span><span>{state.lang === 'tr' ? 'Yarıçap: logaritmik gösterim · renk: kara cisim yaklaşımı · akış: temsili.' : 'Radius: log display · color: blackbody approximation · outflow: illustrative.'}</span></div>}
    {state.mode === 'neighbors' && state.skyScale === 'galaxy' && <div className="sky-science-caption"><span>{t('sky.galaxyCaption')}</span></div>}
    {state.mode === 'neighbors' && state.skyScale !== 'galaxy' && <div className="sky-science-caption">
      <span>{t('sky.neighborsDensity', { count: catalogue?.stars.length ?? 0 })}</span>
      <span>{t('sky.pointEncoding')}</span>
    </div>}
    {state.mode === 'neighbors' && state.skyScale !== 'galaxy' && status === 'ready' && <details className="sky-neighbour-list">
      <summary>{t('sky.selectStar')}</summary>
      <div>{(catalogue?.stars ?? []).map((item) => <button key={item.id} type="button" onClick={() => props.onSelectTarget?.(item.id)}>
        {item.name} · {number(distanceLy(item, state.year))} ly · {item.spectralType || '—'}
      </button>)}</div>
    </details>}
    {state.mode === 'observations' && <div className="sky-science-caption">
      <span>{t('sky.stackLegend')}</span>
      {missingReason && <span>{t('sky.noCentroid', { reason: translateCode(state.lang, 'sky.reason', missingReason) ?? missingReason.replaceAll('_', ' ') })}</span>}
      {!!props.marks?.some((mark) => mark.track_id) && <span>{t('sky.userTracks')}</span>}
    </div>}
    {state.mode !== 'observations' && state.layers.sky && !(state.mode === 'neighbors' && state.skyScale === 'galaxy') && <p className="sky-background-credit">{t('sky.background')}</p>}
  </div>
}

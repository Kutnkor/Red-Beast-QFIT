import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { I18nProvider, useI18n } from './i18n'
import { api, request } from './lib/api'
import { getHealth, getTargets } from './lib/data'
import { describeApiError } from './lib/errors'
import { navigate, useLocation } from './lib/router'
import { getAppState, setAppState, stateFromQuery, syncViewURL, useAppState, type AppMode } from './lib/store'
import { runCommand, stepYear } from './lib/commands'
import { loadDraft, loadToken, saveDraft, writeString } from './lib/storage'
import type { Health, Mark, Observation, SearchRequest, Sequence } from './lib/types'
import { FALLBACK_LIMITS, SearchForm, valuesFromQuery, buildRequest } from './pages/SearchForm'
import { JobPanel, useJob } from './pages/JobPanel'
import { Dialog, ErrorBox, ExtLink, Icon, useAsync } from './ui/common'
import { angularShift, compass, distanceLy } from './three/science/astrometry'
import { temperatureToRgb } from './three/science/blackbody'
import type { MotionCatalogue, MotionStar, SequenceTrack, ModelCatalogue, ModelParameter, StellarProfile } from './three/types'
import { referenceNumber } from './three/types'
import { ProvenanceDialog } from './viewer/panels'
import { Timeline } from './viewer/Timeline'
import { Observatory } from './ui/observatory/Observatory'
import { V4Observatory } from './v4/V4Observatory'
import { suggestedTrack } from './three/science/evolution'
import robinIcon from './qfit/assets/robin-64.png'

const SkyCanvas = lazy(() => import('./three/SkyCanvas'))
const Viewer = lazy(() => import('./viewer/Viewer').then(module => ({ default: module.Viewer })))
const modeKey = { star: 'shell.star', neighbors: 'shell.neighbors', observations: 'shell.observations' } as const
function camera(action: string) { const state = getAppState(); window.dispatchEvent(new CustomEvent(state.mode === 'observations' && state.stageView === 'frames' ? 'blinkspace:viewer-control' : 'blinkspace:camera', { detail: { action } })) }

function Shell() {
  const { t, lang, setLang } = useI18n(), state = useAppState()
  const location = useLocation(), route = location.route
  const targets = useAsync('targets', () => getTargets())
  const health = useAsync<Health>('health', () => getHealth())
  const motion = useAsync<MotionCatalogue>('motion', signal => request('/api/motion', { signal }))
  const models = useAsync<ModelCatalogue>('stellar-models-v1', signal => request('/api/models', { signal }))
  const shared = useAsync<Observation>(route.name === 'observation' ? `observation:${route.id}` : null, async signal => (await api.observation(route.name === 'observation' ? route.id : '', signal)).observation)
  const target = targets.data?.find(item => item.id === state.targetId)
  const star = motion.data?.targets.find(item => item.id === state.targetId) ?? motion.data?.stars.find(item => item.id === state.targetId) ?? null
  const sequenceId = route.name === 'sequence' ? route.id : route.name === 'observation' ? null : state.sequenceId ?? target?.ready_sequence_id ?? null
  const sequenceRequest = useAsync<Sequence>(sequenceId ? `sequence:${sequenceId}` : null, signal => api.sequence(sequenceId!, signal))
  const sequence = route.name === 'observation' ? (shared.data?.id === route.id ? shared.data.sequence : null) : (sequenceRequest.data?.id === sequenceId ? sequenceRequest.data : null)
  const track = useAsync<SequenceTrack>(sequence ? `track:${sequence.id}` : null, signal => request(`/api/sequences/${sequence!.id}/track`, { signal }))
  const job = useJob()
  const [filter, setFilter] = useState(''), [dialog, setDialog] = useState<'sources' | 'keys' | 'provenance' | null>(null)
  const [saved, setSaved] = useState(''), [online, setOnline] = useState(navigator.onLine), [viewerLoaded, setViewerLoaded] = useState(false)
  const [continueConfirm, setContinueConfirm] = useState(false)
  const [marks, setMarks] = useState<Mark[]>([])
  const filterRef = useRef<HTMLInputElement>(null)
  const limits = health.data?.limits ?? FALLBACK_LIMITS
  const embed = location.query.get('embed') === '1'
  const startedQuery = useRef<string | null>(null)
  useEffect(() => {
    if (route.name !== 'home' || !online) return
    const query = ['ra', 'dec', 'fov', 'unit', 'frames', 'lam'].map(key => `${key}=${location.query.get(key) ?? ''}`).join('&')
    const values = valuesFromQuery(location.query, limits)
    if (!values || startedQuery.current === query) return
    startedQuery.current = query
    const built = buildRequest(values, limits)
    if (built.request) job.start(built.request)
  }, [location.pathname, location.query.toString(), online, limits])
  const format = (value: number, decimals = 2) => new Intl.NumberFormat(lang === 'tr' ? 'tr-TR' : 'en-US', { maximumFractionDigits: decimals }).format(value)

  useEffect(() => { setAppState({ lang }) }, [lang])
  useEffect(() => { const update = () => {const parsed=stateFromQuery(window.location.search);setAppState({stellarMode:'surface',stageView:'frames',playing:false,evolutionPlaying:false,...parsed});if(parsed.lang)setLang(parsed.lang)}; window.addEventListener('popstate', update); return () => window.removeEventListener('popstate', update) }, [setLang])
  useEffect(() => {
    if (route.name === 'sequence' || route.name === 'observation') setAppState({ mode: 'observations', playing: false })
  }, [location.pathname])
  useEffect(() => {
    if (!sequence) return
    // A response for a previous target must never undo a newer selection.
    if (route.name === 'home' && getAppState().targetId !== sequence.meta.target_id) return
    setAppState(s => ({ sequenceId: sequence.id, targetId: sequence.meta.target_id ?? null, frameIndex: Math.min(s.frameIndex, Math.max(0, sequence.frames.length - 1)) }))
  }, [sequence, route.name])
  useEffect(() => { if (state.mode === 'observations' || state.drawer.open) setViewerLoaded(true) }, [state.mode, state.drawer.open])
  useEffect(() => { const update = () => setOnline(navigator.onLine); window.addEventListener('online', update); window.addEventListener('offline', update); return () => { window.removeEventListener('online', update); window.removeEventListener('offline', update) } }, [])
  useEffect(() => { if (!state.playing && !state.evolutionPlaying) syncViewURL() }, [state.mode, state.targetId, state.year, state.lang, state.stageView, state.playing, state.stellarMode, state.evolutionTrack, state.evolutionProgress, state.evolutionPlaying])
  useEffect(() => {
    if (!state.evolutionPlaying || state.mode !== 'star' || state.stellarMode !== 'evolution') return
    let frame = 0, previous = performance.now()
    const tick = (now: number) => {
      const delta = (now - previous) / 1000
      if (delta >= 1 / 30) {
        previous = now
        const progress = Math.min(1, getAppState().evolutionProgress + Math.min(.1, delta) / 60)
        setAppState({ evolutionProgress: progress, evolutionPlaying: progress < 1 })
        if (progress >= 1) return
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [state.evolutionPlaying, state.mode, state.stellarMode])
  useEffect(() => {
    if (!state.playing || state.mode === 'observations') return
    let frame = 0, previous = performance.now()
    const tick = (now: number) => {
      const s = getAppState(), next = Math.min(2100, s.year + Math.min(0.1, (now - previous) / 1000) * s.speedYearsPerSec)
      previous = now
      setAppState({ year: next, playing: next < 2100 })
      if (next < 2100) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [state.playing, state.mode])
  const jobBusy = job.state.phase === 'submitting' || job.state.phase === 'running'
  useEffect(() => {
    if (job.state.phase === 'done') {
      setAppState({ mode: 'observations', sequenceId: job.state.sequenceId, stageView: 'frames', frameIndex: 0, refIndex: 0, playing: false })
      navigate(`/s/${job.state.sequenceId}`)
    }
  }, [job.state.phase])

  const save = useCallback(() => {
    const current = getAppState()
    const payload = { targetId: current.targetId, targetName: star?.name ?? target?.name ?? null, mode: current.mode, year: current.year,
      catalogue: motion.data?.catalogue ?? 'Gaia DR3 / SIMBAD', savedUtc: new Date().toISOString(), observationIds: sequence?.frames.map(f => f.obs_id) ?? [],
      sequenceId: sequence?.id ?? null, frameIndex: current.frameIndex, stageView: current.stageView }
    const serialized = JSON.stringify(payload, null, 2)
    writeString('blinkspace.lastObservation', serialized)
    const url = URL.createObjectURL(new Blob([serialized], { type: 'application/json' })), link = document.createElement('a')
    link.href = url; link.download = `RedBeast-${current.targetId ?? 'view'}-${Math.round(current.year)}.json`; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000); setSaved(t('shell.saved'))
  }, [star, target, motion.data, sequence, t])
  useEffect(() => {
    const sources = () => setDialog('sources'), saveEvent = () => save(), searchEvent = (event: Event) => job.start((event as CustomEvent<SearchRequest>).detail)
    window.addEventListener('blinkspace:sources', sources); window.addEventListener('blinkspace:save', saveEvent); window.addEventListener('blinkspace:search', searchEvent)
    return () => { window.removeEventListener('blinkspace:sources', sources); window.removeEventListener('blinkspace:save', saveEvent); window.removeEventListener('blinkspace:search', searchEvent) }
  }, [save, job.start])
  const select = (id: string) => {
    void runCommand('select_target', { target_id: id }, { source: 'user' })
    setAppState({ evolutionTrack: suggestedTrack(id), evolutionProgress: 0, evolutionPlaying: false })
    setSaved(''); setContinueConfirm(false)
    navigate(`/?target=${encodeURIComponent(id)}&mode=${getAppState().mode}&lang=${lang}&year=${Math.round(getAppState().year)}`)
  }
  const mode = (value: AppMode) => { setAppState({ evolutionPlaying: false }); void runCommand('set_mode', { mode: value }, { source: 'user' }) }
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return
      if ((event.target as HTMLElement)?.closest('input,textarea,select,[contenteditable="true"],[data-dialog]')) return
      const s = getAppState(), n = sequence?.frames.length ?? 0
      if (['1', '2', '3'].includes(event.key)) mode((['star', 'neighbors', 'observations'] as AppMode[])[Number(event.key) - 1])
      else if (event.key === '/') { filterRef.current?.focus(); window.dispatchEvent(new Event('blinkspace:open-search')) }
      else if (event.key === '?') setDialog('keys')
      else if (event.key === 'Escape') { setDialog(null); setAppState({ playing: false, evolutionPlaying: false, surfacePlaying: false, drawer: { ...s.drawer, open: false } }) }
      else if (event.key === ' ' || event.key.toLowerCase() === 'p') {
        if(s.mode==='star'&&s.stellarMode==='education')return
        if (event.key === ' ' && (event.target as HTMLElement)?.closest('button,a,summary')) return
        if (s.mode === 'star' && s.stellarMode === 'evolution') setAppState({ evolutionPlaying: !s.evolutionPlaying, ...(s.evolutionProgress >= 1 ? { evolutionProgress: 0 } : {}) })
        else if (s.mode !== 'observations' || n >= 2) setAppState({ playing: !s.playing, ...(s.year >= 2100 && s.mode !== 'observations' ? { year: 2000 } : {}) })
      } else if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
        if(s.mode==='star'&&s.stellarMode==='education')return
        if (s.mode === 'star' && s.stellarMode === 'evolution') setAppState({ evolutionPlaying: false, evolutionProgress: event.key === 'Home' ? 0 : event.key === 'End' ? 1 : Math.max(0, Math.min(1, s.evolutionProgress + (event.key === 'ArrowRight' ? .01 : -.01))) })
        else if (s.mode === 'observations' && n) void runCommand('set_frame', { index: event.key === 'Home' ? 0 : event.key === 'End' ? n - 1 : (s.frameIndex + (event.key === 'ArrowRight' ? 1 : -1) + n) % n }, { source: 'user', frameCount: n })
        else if (event.key === 'Home' || event.key === 'End') void runCommand('set_year', { year: event.key === 'Home' ? 2000 : 2100 }, { source: 'user' })
        else stepYear(event.key === 'ArrowRight' ? 1 : -1)
      } else if (event.key === '+' || event.key === '=') camera('zoom-in')
      else if (event.key === '-' || event.key === '_') camera('zoom-out')
      else if (event.key === '0') camera('reset')
      else if (event.key === 'ArrowUp' || event.key === 'ArrowDown') camera(event.key === 'ArrowUp' ? 'up' : 'down')
      else if (event.key.toLowerCase() === 'b' && n > 1) setAppState({ frameIndex: s.refIndex === s.frameIndex ? (s.frameIndex + 1) % n : s.refIndex, refIndex: s.frameIndex })
      else return
      event.preventDefault()
    }
    const framedKey=(event:Event)=>onKey((event as CustomEvent<KeyboardEvent>).detail)
    window.addEventListener('keydown', onKey);window.addEventListener('blinkspace:frame-key',framedKey)
    return () => {window.removeEventListener('keydown', onKey);window.removeEventListener('blinkspace:frame-key',framedKey)}
  }, [sequence?.id])

  const openSearch = (request: SearchRequest) => {
    if (!online) return
    // A direct form submission supplies the user's consent; optional wavelength/date fields are retained.
    void runCommand('start_search', { ra: String(request.ra ?? ''), dec: String(request.dec ?? ''), ra_unit: request.ra_unit ?? 'auto', fov_arcmin: request.fov_arcmin ?? 6 }, { source: 'user', startSearch: () => job.start(request) })
  }
  const continueObservation = () => {
    const o = shared.data; if (!o) return
    const existing = loadDraft(o.sequence_id)
    if (!continueConfirm && existing.marks.length && existing.observationId !== o.id) { setContinueConfirm(true); return }
    saveDraft(o.sequence_id, { marks: o.marks, title: o.title, note: o.note, observationId: loadToken(o.id) ? o.id : null })
    navigate(`/s/${o.sequence_id}`)
  }
  const profile = models.data?.profiles.find(item => item.target_id === state.targetId)
  const currentFrame = sequence?.frames[state.frameIndex]
  const shift = star ? angularShift(star, 2026, state.year) : null
  const moon = referenceNumber(motion.data, ['moon_mean_diameter_arcsec'])
  const sequenceError = sequenceRequest.status === 'error' ? sequenceRequest.error : shared.status === 'error' ? shared.error : null
  const targetsShown = (targets.data ?? []).filter(item => item.name.toLocaleLowerCase().includes(filter.toLocaleLowerCase()))
  const frameView = state.mode === 'observations' && state.stageView === 'frames'


  const scene = (<div className={`scene-content ${frameView ? 'frame-view' : 'model-view'}`}>
          <Suspense fallback={<p className="scene-loading">{t('shell.motionLoading')}</p>}><SkyCanvas state={state} catalogue={motion.data} models={models.data} sequence={sequence} track={track.data} marks={marks} onSelectTarget={select} onSelectFrame={index => void runCommand('set_frame', { index }, { source: 'user', frameCount: sequence?.frames.length })} /></Suspense>
          {!frameView && state.mode !== 'observations' && shift && <div className="big-number">
            <p className="big-number-label">{t('shell.shift', { year: Math.round(state.year) })}</p>
            <p className="computed"><span className="mono">{format(shift.arcsec >= 60 ? shift.arcsec / 60 : shift.arcsec, shift.arcsec >= 60 ? 1 : 2)}{shift.arcsec >= 60 ? '′' : '″'}</span> <span className="direction">{shift.arcsec > 0.001 ? compass(shift.bearingDeg, lang) : ''}</span></p>
            {moon && <p className="small muted">{t('shell.moon', { fraction: format(shift.arcsec / moon, 3) })}</p>}
            {star && angularShift(star, 2000, 2100).arcsec < 10 && <button className="btn btn-text low-motion-note" onClick={() => void runCommand('open_drawer_tab', { tab: 'curve' }, { source: 'user' })}>{t('shell.smallShift')}</button>}
          </div>}
          {motion.status === 'error' && state.mode !== 'observations' && <div className="scene-message"><ErrorBox message={t('shell.catalogueFailed')} onRetry={motion.reload} /></div>}
          {sequence && viewerLoaded && <Suspense fallback={<p className="scene-loading">{t('seq.loading')}</p>}><Viewer key={shared.data?.id ?? sequence.id} integrated sequence={sequence} observation={route.name === 'observation' ? shared.data : null} motionTarget={star} onMarksChange={setMarks} tutorialId={location.query.get('tut')} /></Suspense>}
          {!sequence && state.mode === 'observations' && <div className="scene-message">
            {sequenceError ? <ErrorBox message={describeApiError(lang, sequenceError.code, sequenceError.reason)} onRetry={sequenceRequest.reload} /> : sequenceRequest.status === 'loading' || shared.status === 'loading' ? <p>{t('seq.loading')}</p> : <><p>{t('shell.noSequence')}</p>{target ? <button className="btn btn-primary" disabled={!online || jobBusy} onClick={() => job.start({ target_id: target.id })}>{t('shell.prepare')}</button>
              : star && <button className="btn btn-primary" disabled={!online || jobBusy} onClick={() => job.start({ ra: String(star.ra), dec: String(star.dec), ra_unit: 'deg', fov_arcmin: 6 })}>{t('shell.prepare')}</button>}</>}
          </div>}
          {!sequence && state.drawer.open && <aside className="empty-analysis"><p>{t('shell.analysisEmpty')}</p><button className="btn" onClick={() => setAppState(s => ({ drawer: { ...s.drawer, open: false } }))}>{t('app.close')}</button></aside>}
          {!frameView && <div className="stage-tools">{state.mode === 'observations' && <button className="btn btn-icon" aria-label={t('shell.faceOn')} title={t('shell.faceOn')} onClick={() => camera('face-on')}><Icon name="face-on" /></button>}{(['zoom-out', 'zoom-in', 'reset'] as const).map(action => <button key={action} className="btn btn-icon" aria-label={t(action === 'reset' ? 'zoom.reset' : action === 'zoom-in' ? 'zoom.in' : 'zoom.out')} onClick={() => camera(action)}><Icon name={action} /></button>)}<button className="btn btn-icon" aria-label={t('app.shortcuts')} onClick={() => setDialog('keys')}><Icon name="keyboard" /></button></div>}
        </div>)
  const dialogs = <>{dialog === 'sources' && <SourcesDialog catalogue={motion.data} models={models.data} sequence={sequence} onClose={() => setDialog(null)} onProvenance={() => setDialog('provenance')} />}
    {dialog === 'provenance' && sequence && <ProvenanceDialog sequence={sequence} onClose={() => setDialog(null)} />}
    {dialog === 'keys' && <Dialog title={t('app.shortcuts')} onClose={() => setDialog(null)}><ul className="shortcut-list">{(['shell.keyModes', 'shell.keyTime', 'shell.keyCamera', 'shell.keyOther'] as const).map(key => <li key={key}>{t(key)}</li>)}</ul></Dialog>}</>
  const ObservatoryLayout = location.query.get('ui') === 'classic' ? Observatory : V4Observatory
  if (location.query.get('ui') !== 'legacy') return <ObservatoryLayout
    state={state} targets={targets.data ?? []} catalogue={motion.data} star={star} profile={profile} sequence={sequence} marks={marks}
    scene={scene} dialogs={dialogs} search={<><SearchForm limits={limits} initial={valuesFromQuery(location.query, limits)} busy={!online || !['idle', 'done', 'failed', 'cancelled', 'insufficient'].includes(job.state.phase)} serverError={null} onSubmit={openSearch} />
</>}
    measurements={<>{star && <TargetMeasurements star={star} sequence={sequence} />}{profile && <ModelMeasurements profile={profile} />}</>}
    notices={<>{targets.status === 'error' && <ErrorBox message={t('home.targetsError')} onRetry={targets.reload} />}          {job.state.phase !== 'idle' && <JobPanel state={job.state} targetName={target?.name ?? star?.name ?? null} onCancel={job.cancel} onRetry={job.start} onReset={job.reset} onOpen={id => navigate(`/s/${id}`)} />}{!online && <p className="notice notice-warn">{t('shell.offline')}</p>}{shared.data && <div className="shared-note"><div><span>{t('obs.banner')} · {shared.data.title}</span>{shared.data.note && <p className="user-text">{shared.data.note}</p>}</div><button className="btn" onClick={continueObservation}>{continueConfirm ? t('obs.overwrite') : t('obs.continue')}</button></div>}</>}
    select={select} mode={mode} save={save} sources={() => setDialog('sources')} saved={saved} online={online} embed={embed}
  />

  return <div className={`app workspace-app ${embed ? 'app-embed' : ''}`}>
    <a className="skip" href="#main">{t('app.skip')}</a>
    <header className="workspace-head">
      <button className="wordmark" onClick={() => { select('barnard'); mode('star') }}><img src={robinIcon} alt="" width={34} height={34} />{t('app.name')}</button>
      <ModeSwitch mode={state.mode} onChange={mode} />
      <div className="header-actions"><button className="btn btn-text" onClick={() => void runCommand('open_sources', {}, { source: 'user', openSources: () => setDialog('sources') })}>{t('shell.sources')}</button>
      <div className="lang" aria-label={t('app.language')}>{(['tr', 'en'] as const).map(l => <button key={l} className="lang-btn" aria-pressed={lang === l} onClick={() => setLang(l)}>{l.toUpperCase()}</button>)}</div></div>
    </header>
    <main id="main" className="workspace" tabIndex={-1}>
      <aside className="catalogue-sidebar" aria-label={t('shell.targets')}>
        <p className="intro">{t('shell.intro', { n: motion.data?.stars.length ?? 120, t: targets.data?.length ?? 5 })}</p>
        <label className="target-filter"><Icon name="search" /><input ref={filterRef} placeholder={t('shell.filter')} aria-label={t('shell.filter')} value={filter} onChange={e => setFilter(e.target.value)} /><kbd>/</kbd></label>
        {targets.status === 'error' && <ErrorBox message={t('home.targetsError')} onRetry={targets.reload} />}
        <div className="target-list">{targetsShown.map(item => {
          const data = motion.data?.targets.find(s => s.id === item.id), active = state.targetId === item.id
          return <div className={active ? 'target-item selected' : 'target-item'} key={item.id}>
            <button className="target-select" aria-pressed={active} onClick={() => select(item.id)}>
              <span className="target-name"><span className="target-colour" aria-hidden="true" style={data?.teff_k ? { backgroundColor: `rgb(${temperatureToRgb(data.teff_k).join(',')})` } : undefined} />{item.name}</span><span className="mono target-summary">{data ? `${format(Math.hypot(data.pmRa, data.pmDec) / 1000, 3)}″/${t('shell.perYear')} · ${format(distanceLy(data))} ${t('shell.ly')}` : item.spectral_type ?? item.kind}</span>
              <span className="target-ready">{item.ready_sequence_id ? t('home.ready') : t('home.notReady')}</span>
            </button>
            {active && data && <div className="desktop-measurements"><TargetMeasurements star={data} sequence={sequence} /></div>}
          </div>
        })}{targets.status === 'ready' && !targetsShown.length && <p>{t('shell.empty')}</p>}</div>
        <div className="sidebar-settings">
          {profile && state.mode === 'star' && <ModelMeasurements profile={profile} />}
          <section className="layer-switches"><h2>{t('shell.layers')}</h2>{(['environment', 'trail', 'grid', 'sky'] as const).map(key => <label key={key}><input type="checkbox" checked={state.layers[key]} onChange={e => void runCommand('toggle_layer', { layer: key, on: e.target.checked }, { source: 'user' })} /><span>{t(`shell.${key}`)}</span></label>)}</section>
          <p className="model-note representative">{state.mode === 'neighbors' ? t('shell.neighborNote') : state.mode === 'star' ? t('shell.modelNote') : t('shell.sameGrid')}</p>
          {star && !star.hasRadialVelocity && <p className="assumed small">{t('shell.rvNote')}</p>}
          <button className="btn btn-primary btn-wide" onClick={() => void runCommand('save_view', {}, { source: 'user', saveView: save })}>{t('shell.save')}</button>
          {saved && <p className="small" role="status">{saved}</p>}
          <p className="record-link">{state.mode === 'observations' && currentFrame ? <ExtLink href={currentFrame.archive_file_url}>{t('shell.file')}</ExtLink> : star && (star.source_url || star.sourceUrl) ? <ExtLink href={star.source_url ?? star.sourceUrl!}>{t('shell.record')}</ExtLink> : null}</p>
        </div>
        <details className="coordinate-search" open={Boolean(location.query.get('ra'))}><summary>{t('shell.search')}</summary>
          <SearchForm limits={limits} initial={valuesFromQuery(location.query, limits)} busy={!online || !['idle', 'done', 'failed', 'cancelled', 'insufficient'].includes(job.state.phase)} serverError={null} onSubmit={openSearch} />
          {job.state.phase !== 'idle' && <JobPanel state={job.state} targetName={target?.name ?? star?.name ?? null} onCancel={job.cancel} onRetry={job.start} onReset={job.reset} onOpen={id => navigate(`/s/${id}`)} />}
        </details>
      </aside>
      <section className="instrument" aria-label={t(modeKey[state.mode])}>
        <div className="mobile-modes"><ModeSwitch mode={state.mode} onChange={mode} /></div>
        {!online && <p className="notice notice-warn">{t('shell.offline')}</p>}
        <header className="scene-heading">
          <div><p className="instrument-source mono">{state.mode === 'observations' ? 'NASA/IPAC IRSA · SPHEREx' : 'ESA GAIA DR3 · ICRS'}</p>
          <h1>{state.mode === 'neighbors' ? t('shell.neighborTitle', { n: motion.data?.stars.length ?? 120 }) : star?.name ?? target?.name ?? (sequence ? `${format(sequence.meta.center.ra_deg, 5)}° ${format(sequence.meta.center.dec_deg, 5)}°` : t('app.name'))}</h1>
          {star && state.mode !== 'observations' && <p className="mono coordinates">RA {format(star.ra, 5)}° · Dec {format(star.dec, 5)}° · J{star.epoch.toFixed(1)}</p>}
          {sequence && state.mode === 'observations' && <p className="mono coordinates">{t('seq.summary', { n: sequence.frames.length, v: sequence.meta.n_visits, d: format(sequence.meta.span_days, 1), lam: format(sequence.meta.wavelength.lam_ref_um, 3) })}</p>}</div>
          <div className="scene-heading-actions">{state.mode === 'observations' && <div className="seg">{(['frames', 'timestack'] as const).map(value => <button className="seg-btn" aria-pressed={state.stageView === value} key={value} onClick={() => void runCommand('set_stage_view', { view: value }, { source: 'user' })}>{t(value === 'frames' ? 'shell.frames' : 'shell.timeStack')}</button>)}</div>}
          <button className="btn" aria-expanded={state.drawer.open} onClick={() => setAppState(s => ({ drawer: { ...s.drawer, open: !s.drawer.open } }))}><Icon name="drawer" />{t('shell.analysis')}</button></div>
        </header>
        {shared.data && <div className="shared-note"><div><span>{t('obs.banner')} · {shared.data.title}</span>{shared.data.note && <p className="user-text">{shared.data.note}</p>}</div><button className="btn" onClick={continueObservation}>{continueConfirm ? t('obs.overwrite') : t('obs.continue')}</button></div>}
        {scene}
        {!frameView && <div className="time-strip">
          <div className="time-strip-head"><span>{t(state.mode === 'observations' ? 'shell.date' : 'shell.year')}</span><span className="mono time-value">{state.mode === 'observations' ? currentFrame?.date_avg.slice(0, 19).replace('T', ' ') ?? '—' : Math.round(state.year)}</span></div>
          <div className="time-controls"><button className="btn btn-icon" aria-label={t('play.prev')} onClick={() => state.mode === 'observations' && sequence ? void runCommand('set_frame', { index: Math.max(0, state.frameIndex - 1) }, { source: 'user', frameCount: sequence.frames.length }) : stepYear(-1)}><Icon name="prev" /></button>
            <button className="btn btn-icon btn-play" aria-label={t(state.playing ? 'play.pause' : 'play.play')} onClick={() => setAppState({ playing: !state.playing, ...(state.year >= 2100 && state.mode !== 'observations' ? { year: 2000 } : {}) })}><Icon name={state.playing ? 'pause' : 'play'} /></button>
            <button className="btn btn-icon" aria-label={t('play.next')} onClick={() => state.mode === 'observations' && sequence ? void runCommand('set_frame', { index: Math.min(sequence.frames.length - 1, state.frameIndex + 1) }, { source: 'user', frameCount: sequence.frames.length }) : stepYear(1)}><Icon name="next" /></button>
            {state.mode === 'observations' && sequence ? <Timeline frames={sequence.frames.map(f => ({ mjd: f.mjd_avg, date: f.date_avg }))} current={state.frameIndex} reference={state.refIndex} showReference onSelect={index => void runCommand('set_frame', { index }, { source: 'user', frameCount: sequence.frames.length })} /> : <div className="year-range"><input type="range" min={2000} max={2100} step={1} value={state.year} aria-label={t('shell.year')} onChange={e => void runCommand('set_year', { year: Number(e.target.value) }, { source: 'user' })} /><div className="year-ticks mono">{[2000, 2025, 2050, 2075, 2100].map(year => <span key={year}>{year}</span>)}</div></div>}
            {state.mode !== 'observations' && <select aria-label={t('shell.speed')} value={state.speedYearsPerSec} onChange={e => setAppState({ speedYearsPerSec: Number(e.target.value) as 1 | 5 | 20 })}>{[1, 5, 20].map(n => <option value={n} key={n}>{t('shell.yearsPerSec', { n })}</option>)}</select>}
          </div><p className="small muted stage-hint">{t(state.mode === 'observations' ? 'shell.sameGrid' : 'shell.drag')}</p>
        </div>}
        {star && <section className="mobile-measurements"><TargetMeasurements star={star} sequence={sequence} /></section>}
      </section>
    </main>
    {dialogs}
  </div>
}

function ModeSwitch({ mode, onChange }: { mode: AppMode; onChange: (mode: AppMode) => void }) {
  const { t } = useI18n()
  return <nav className="mode-switch" aria-label={t('mode.label')}>{(['star', 'neighbors', 'observations'] as const).map(value => <button key={value} aria-pressed={mode === value} onClick={() => onChange(value)}>{t(modeKey[value])}</button>)}</nav>
}
function TargetMeasurements({ star, sequence }: { star: MotionStar; sequence: Sequence | null }) {
  const { t, lang } = useI18n(), number = (value: number, digits = 3) => new Intl.NumberFormat(lang === 'tr' ? 'tr-TR' : 'en-US', { maximumFractionDigits: digits }).format(value)
  return <dl className="target-measurements">
    <div><dt>{t('shell.distance')}</dt><dd className="computed mono">{number(distanceLy(star), 2)} {t('shell.ly')}</dd></div>
    <div><dt>{t('shell.parallax')}</dt><dd className="mono">{number(star.parallax)}{star.parallaxError !== undefined ? ` ± ${number(star.parallaxError)}` : ''} mas</dd></div>
    <div><dt>{t('shell.properMotion')}</dt><dd className="mono">{number(Math.hypot(star.pmRa, star.pmDec) / 1000)}″/{t('shell.perYear')}</dd></div>
    <div><dt>{t('shell.rv')}</dt><dd className={star.hasRadialVelocity ? 'mono' : 'mono assumed'}>{number(star.hasRadialVelocity ? star.radialVelocity : 0, 1)} km/s{!star.hasRadialVelocity && ` · ${t('shell.assumed')}`}</dd></div>
    <div><dt>{t('shell.temperature')}</dt><dd className="mono">{star.teff_k ? `${number(star.teff_k, 0)} K` : '—'}</dd></div>
    <p className="measurement-source">{star.teff_k ? `${t('shell.source')}: ${star.teff_source}` : t('shell.noTemperature')}</p>
    <div><dt>{t('shell.spectral')}</dt><dd className="mono">{star.spectralType ?? '—'}</dd></div>
    {sequence && <p className="measurement-source mono">SPHEREx · {sequence.frames.length} · {number(sequence.meta.wavelength.lam_ref_um)} µm<br />{sequence.frames[0]?.date_avg.slice(0, 10)} → {sequence.frames.at(-1)?.date_avg.slice(0, 10)}</p>}
  </dl>
}
function ModelMeasurements({ profile }: { profile: StellarProfile }) {
  const { t, lang } = useI18n()
  const labels = { radius_solar: 'model.radius', teff_k: 'model.teff', period_days: 'model.period', rotation_period_days: 'model.rotation', disk_inclination_deg: 'model.inclination', disk_radius_au: 'model.diskRadius', orbital_period_years: 'model.orbit', binary_semimajor_axis_au: 'model.axis' } as const
  const number = (value: number) => new Intl.NumberFormat(lang === 'tr' ? 'tr-TR' : 'en-US', { maximumFractionDigits: 4 }).format(value)
  const note = (value: ModelParameter) => lang === 'tr' ? value.note_tr ?? value.note : value.note
  const valueText = (value: ModelParameter) => {
    if (value.value === null) return t('model.unknown')
    const unit = value.unit?.replace('R_sun', 'R☉').replace('Rsun', 'R☉') ?? ''
    const estimate = typeof value.value === 'number' ? number(value.value) : value.value
    return `${estimate}${value.uncertainty !== undefined ? ` ± ${number(value.uncertainty)}` : ''} ${unit}`.trim()
  }
  const measurements = (values: Record<string, ModelParameter>) => <dl>{Object.entries(labels).map(([key, label]) => {
    const value = values[key]
    if (!value || (value.value === null && key !== 'radius_solar' && key !== 'teff_k')) return null
    return <div key={key}><dt>{t(label)}</dt><dd className={`mono ${value.classification}`} title={note(value)}>{valueText(value)}<span className="model-value-class">{t(value.classification === 'unknown' ? 'model.unknown' : `shell.${value.classification}`)}</span></dd></div>
  })}</dl>
  const caveats = lang === 'tr' ? profile.caveats_tr ?? profile.caveats : profile.caveats
  const allParameters = [profile, ...(profile.components ?? [])].flatMap(component => Object.values(component.parameters ?? {}))
  return <section className="model-measurements"><h2>{t('model.title')}</h2>
    {profile.stellar_class && <p className="model-class">{t(`model.${profile.stellar_class}`)}</p>}
    {measurements(profile.parameters)}
    {profile.components?.map(component => <div key={component.id ?? component.name}><h3>{component.name}</h3>{measurements(component.parameters ?? {})}</div>)}
    <p className="small representative">{t('model.note')}</p>
    <a className="btn btn-wide model-download" href={`/models/${profile.target_id}.three.json`} download>{t('model.download')}</a>
    <p className="small muted">{t('model.downloadNote')}</p>
    <details className="model-source-notes"><summary>{t('model.details')}</summary>
      <ul>{caveats?.map(text => <li key={text}>{text}</li>)}</ul>
      {allParameters.filter(value => value.value !== null).map((value, index) => <p key={index}>{valueText(value)}{value.range && ` · ${number(value.range[0])}–${number(value.range[1])}`} — {note(value)}</p>)}
      <ul>{profile.sources?.map(source => <li key={source.id}><ExtLink href={source.url}>{source.title}</ExtLink></li>)}</ul>
    </details>
  </section>
}
function SourcesDialog({ catalogue, models, sequence, onClose, onProvenance }: { catalogue: MotionCatalogue | null; models: ModelCatalogue | null; sequence: Sequence | null; onClose: () => void; onProvenance: () => void }) {
  const { t, lang } = useI18n()
  const sources = [
    ['NASA/IPAC IRSA · SPHEREx', 'https://irsa.ipac.caltech.edu/Missions/spherex.html'], ['ESA Gaia DR3', 'https://www.cosmos.esa.int/web/gaia/dr3'],
    ['SIMBAD · CDS', 'https://simbad.cds.unistra.fr/simbad/'], ['ESA Hipparcos', 'https://www.cosmos.esa.int/web/hipparcos/catalogues'],
    ['AllWISE · NASA/IPAC IRSA', 'https://irsa.ipac.caltech.edu/Missions/wise.html'], ['Mamajek · stellar temperatures', 'https://www.pas.rochester.edu/~emamajek/EEM_dwarf_UBVIJHK_colors_Teff.txt'],
    ['Ballesteros 2012 · B−V temperature', 'https://arxiv.org/abs/1201.1809'], ['Wyman et al. 2013 · CIE color matching', 'https://jcgt.org/published/0002/02/01/'],
    ['Three.js · MIT', 'https://github.com/mrdoob/three.js/blob/r170/LICENSE'], ['Bricolage Grotesque · OFL', '/fonts/bricolagegrotesque-OFL.txt'], ['Martian Mono · OFL', '/fonts/martianmono-OFL.txt'], ['GSAP · Standard licence', 'https://gsap.com/community/standard-license/'],
  ]
  return <Dialog title={t('shell.sourcesTitle')} onClose={onClose} wide>
    <p>{t('shell.sourceLimit')}</p><p className="muted">{t('footer.independent')}</p>
    <div className="epistemic-legend"><span>{t('shell.measured')}</span><span className="computed">{t('shell.computed')}</span><span className="representative">{t('shell.representative')}</span><span className="assumed">{t('shell.assumed')}</span></div>
    <ul className="source-list">{sources.map(([name, url]) => <li key={name}><ExtLink href={url}>{name}</ExtLink></li>)}</ul>
    {models?.profiles.map(profile => <details key={profile.target_id}><summary>{catalogue?.targets.find(star => star.id === profile.target_id)?.name ?? profile.target_id} · {t('model.details')}</summary><ul>{profile.sources?.map(source => <li key={source.id}><ExtLink href={source.url}>{source.title}</ExtLink></li>)}</ul><p className="representative">{t('model.note')}</p><ul>{(lang === 'tr' ? profile.caveats_tr ?? profile.caveats : profile.caveats)?.map(text => <li key={text}>{text}</li>)}</ul></details>)}
    {catalogue?.reference && <details><summary>{t('shell.source')} · IAU / NASA</summary><pre>{JSON.stringify(catalogue.reference, null, 2)}</pre></details>}
    {catalogue?.provenance && <details><summary>Gaia DR3 / Hipparcos</summary><pre>{JSON.stringify(catalogue.provenance, null, 2)}</pre></details>}
    {sequence && <button className="btn" onClick={onProvenance}>{t('info.provenance')}</button>}
  </Dialog>
}
export default function App() { return <I18nProvider><Shell /></I18nProvider> }

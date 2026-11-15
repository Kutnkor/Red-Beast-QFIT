// The viewer: real frames first, everything else around them.

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type SetStateAction } from 'react'
import { useI18n } from '../i18n'
import { api, request } from '../lib/api'
import { getAppState, setAppState, useAppState, type DrawerTab } from '../lib/store'
import { runCommand } from '../lib/commands'
import { AssistantPanel } from './AssistantPanel'
import type { MotionStar } from '../three/types'
import { getTargets, getTutorials, setCursor, useCursor } from '../lib/data'
import { describeApiError } from '../lib/errors'
import { fmtDateUTC, fmtDecDms, fmtRaHms, fmtSignedDeg } from '../lib/format'
import { addMark, deleteMark, moveMark, newId, sanitizeMarks, tracksOf, updateMark, MAX_MARKS, type MarkPatch } from '../lib/marks'
import { navigate } from '../lib/router'
import { decodeView, encodeView } from '../lib/savedView'
import { loadDraft, saveDraft, type Draft } from '../lib/storage'
import { answerQuiz, applyEvent, isComplete, loadProgress, progressOf, saveProgress, type ProgressMap, type TutorialEvent } from '../lib/tutorials'
import type { Candidate, Classification, Layers, Mark, Observation, SearchRequest, Sequence, Target, Tutorial, ViewMode } from '../lib/types'
import { clampView, defaultView, MAX_ZOOM, MIN_ZOOM, type View } from '../lib/view'
import { pngToSky, skyToPng, type Sky } from '../lib/wcs'
import { JobPanel, useJob } from '../pages/JobPanel'
import { Caveats, Dialog, ErrorBox, Icon, useAsync } from '../ui/common'
import { LightCurveChart } from './LightCurve'
import { MarksPanel } from './MarksPanel'
import { Pane, type PaneOverlays } from './Pane'
import { InfoPanel, LayersPanel, ProvenanceDialog, ShortcutsDialog, WavePanel } from './panels'
import { SpectrumPanel } from './SpectrumPanel'
import { Timeline } from './Timeline'
import { Glider, KIcon, Odometer, RingPlay } from '../v4/kit'
import { TutorialList, TutorialPanel } from './TutorialPanel'

type Tab = 'info' | 'layers' | 'marks' | 'curve' | 'wave' | 'task' | 'assistant'
const SPEEDS = [0.5, 1, 2, 4, 8]

export interface ViewerProps {
  sequence: Sequence
  integrated?: boolean
  motionTarget?: MotionStar | null
  onMarksChange?: (marks: Mark[]) => void
  /** a shared observation: read-only marks, its saved view */
  observation?: Observation | null
  tutorialId?: string | null
}

export function Viewer({ sequence, observation = null, tutorialId = null, integrated = false, motionTarget = null, onMarksChange }: ViewerProps) {
  const { t, tc, lang } = useI18n()
  const app = useAppState()
  const { frames, meta } = sequence
  const grid = meta.grid
  const n = frames.length
  const readOnly = observation !== null

  const initial = useMemo(() => decodeView(observation?.view, grid, n), [observation, grid, n])
  const [localCur, setLocalCur] = useState(initial.cur)
  const cur = integrated ? Math.min(app.frameIndex, Math.max(0, n - 1)) : localCur
  const setCur = useCallback((next: SetStateAction<number>) => {
    if (!integrated) { setLocalCur(next); return }
    const value = typeof next === 'function' ? next(getAppState().frameIndex) : next
    void runCommand('set_frame', { index: Math.max(0, Math.min(n - 1, value)) }, { source: 'user', frameCount: n })
  }, [integrated, n])
  const [localRef, setLocalRef] = useState(initial.ref)
  const refIdx = integrated ? Math.min(app.refIndex, Math.max(0, n - 1)) : localRef
  const setRefIdx = useCallback((value: number) => integrated ? setAppState({ refIndex: value }) : setLocalRef(value), [integrated])
  const [localMode, setLocalMode] = useState<ViewMode>(initial.mode)
  const mode = integrated ? app.viewMode : localMode
  const setMode = useCallback((value: ViewMode) => integrated ? void runCommand('set_view_mode', { view: value }, { source: 'user' }) : setLocalMode(value), [integrated])
  const [view, setView] = useState<View>(initial.view)
  const [localLayers, setLocalLayers] = useState<Layers>(initial.layers)
  const layers = useMemo(() => integrated ? { ...localLayers, gaia: app.layers.gaia, allwise: app.layers.allwise, predicted: app.layers.predicted } : localLayers, [integrated, localLayers, app.layers.gaia, app.layers.allwise, app.layers.predicted])
  const setLayers = useCallback((next: SetStateAction<Layers>) => {
    const value = typeof next === 'function' ? next(layers) : next
    setLocalLayers(value)
    if (integrated) setAppState(s => ({ layers: { ...s.layers, gaia: value.gaia, allwise: value.allwise, predicted: value.predicted } }))
  }, [layers, integrated])
  const [localPlaying, setLocalPlaying] = useState(false)
  const playing = integrated ? app.playing : localPlaying
  const setPlaying = useCallback((next: SetStateAction<boolean>) => {
    if (!integrated) { setLocalPlaying(next); return }
    setAppState(s => ({ playing: typeof next === 'function' ? next(s.playing) : next }))
  }, [integrated])
  const [fps, setFps] = useState(2)
  const playbackControls = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const controls = playbackControls.current, slot = controls?.parentElement
    if (!controls || !slot) return
    // Reserve the original footprint so the date readout and timeline keep their positions.
    const reserve = () => {
      if (!controls.offsetWidth) return
      slot.style.width = `${controls.offsetWidth}px`
      slot.style.height = `${controls.offsetHeight}px`
    }
    reserve()
    if (typeof ResizeObserver !== 'function') return
    const observer = new ResizeObserver(reserve)
    observer.observe(controls)
    return () => observer.disconnect()
  }, [])
  const [markMode, setMarkMode] = useState(false)
  const [markClass, setMarkClass] = useState<Classification>('unsure')
  const [activeTrack, setActiveTrack] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  // a draft that already holds marks (e.g. continued from a shared observation) opens on the marks tab
  const [localTab, setLocalTab] = useState<Tab>(() => (readOnly || sanitizeMarks(loadDraft(sequence.id).marks, n).length > 0 ? 'marks' : 'info'))
  const tab: Tab = integrated ? (app.drawer.tab === 'frame' ? 'info' : app.drawer.tab) : localTab
  const setTab = useCallback((value: Tab) => integrated ? void runCommand('open_drawer_tab', { tab: value === 'info' ? 'frame' : value as DrawerTab }, { source: 'user' }) : setLocalTab(value), [integrated])
  const assistant = useAsync<{ enabled: boolean; provider: string | null }>('assistant-status', signal => request('/api/assistant/status', { signal }))
  useEffect(() => {
    if (integrated && observation) setAppState({ frameIndex: initial.cur, refIndex: initial.ref, viewMode: initial.mode, drawer: { open: true, tab: 'marks' } })
  }, [integrated, observation, initial])
  const [dialog, setDialog] = useState<null | 'prov' | 'keys'>(null)
  const [announce, setAnnounce] = useState('')
  const [draft, setDraftState] = useState<Draft>(() => {
    if (observation) {
      return { marks: sanitizeMarks(observation.marks, n), title: observation.title, note: observation.note, observationId: observation.id }
    }
    const d = loadDraft(sequence.id)
    return { ...d, marks: sanitizeMarks(d.marks, n) }
  })
  const marks = draft.marks
  useEffect(() => { onMarksChange?.(marks) }, [marks, onMarksChange])

  useEffect(() => {
    if (!readOnly) saveDraft(sequence.id, draft)
  }, [draft, readOnly, sequence.id])

  const setDraft = useCallback((patch: Partial<Draft>) => setDraftState((d) => ({ ...d, ...patch })), [])
  const setMarks = useCallback((fn: (marks: Mark[]) => Mark[]) => setDraftState((d) => ({ ...d, marks: fn(d.marks) })), [])

  // ---- target name and tutorials ---------------------------------------------------
  const targets = useAsync<Target[]>('targets', () => getTargets())
  const target = targets.data?.find((x) => x.id === meta.target_id) ?? null
  const tutorials = useAsync<Tutorial[]>('tutorials', () => getTutorials())
  const [activeTut, setActiveTut] = useState<string | null>(tutorialId)
  const [progress, setProgress] = useState<ProgressMap>(() => loadProgress())
  const tutsHere = (tutorials.data ?? []).filter((x) => x.target_id === meta.target_id)
  const tutorial = (tutorials.data ?? []).find((x) => x.id === activeTut) ?? null

  const updateProgress = useCallback((id: string, fn: (p: ReturnType<typeof progressOf>) => ReturnType<typeof progressOf>) => {
    setProgress((map) => {
      const before = progressOf(map, id)
      const after = fn(before)
      if (after === before) return map
      const next = { ...map, [id]: after }
      saveProgress(next)
      return next
    })
  }, [])

  const fire = useCallback(
    (event: TutorialEvent) => {
      if (tutorial) updateProgress(tutorial.id, (p) => applyEvent(tutorial, p, event))
    },
    [tutorial, updateProgress],
  )

  // opening a tutorial applies its suggested view once and counts as "sequence opened"
  const openedTut = useRef<string | null>(null)
  const programmatic = useRef(false)
  useEffect(() => {
    if (!tutorial || openedTut.current === tutorial.id) return
    openedTut.current = tutorial.id
    const v = tutorial.view
    const idx = (x: unknown) => (typeof x === 'number' && Number.isInteger(x) && x >= 0 && x < n ? x : null)
    if (v) {
      const a = idx(v.frame_a)
      const b = idx(v.frame_b)
      if (a !== null) setRefIdx(a)
      if (b !== null) {
        // a frame set by the tutorial itself must not count as the user's "frame changed" step
        setCur((c) => {
          if (c !== b) programmatic.current = true
          return b
        })
      }
      if (v.mode && n >= 2) setMode(v.mode)
      if (Array.isArray(v.layers)) {
        setLayers((l) => {
          const next = { ...l }
          for (const k of Object.keys(next) as (keyof Layers)[]) if (v.layers?.includes(k)) next[k] = true
          return next
        })
      }
    }
    setTab('task')
    updateProgress(tutorial.id, (p) => applyEvent(tutorial, p, 'sequence_opened'))
  }, [tutorial, n, updateProgress, setRefIdx, setMode, setCur, setTab, setLayers])

  // ---- derived products and layers -------------------------------------------------
  const canCompare = n >= 2 && cur !== refIdx
  const diff = useAsync(mode === 'diff' && canCompare ? `diff:${refIdx}:${cur}` : null, (s) => api.diff(sequence.id, refIdx, cur, s))
  const trackStack = useAsync(mode === 'trackstack' ? `trackstack:${refIdx}` : null, signal => request<{ image_url: string; caveats: string[]; valid_frac: number }>(`/api/sequences/${sequence.id}/track_stack?ref_index=${refIdx}`, { signal }))
  const stack = useAsync(mode === 'stack' && n >= 2 ? 'stack' : null, (s) => api.stack(sequence.id, s))
  const gaia = useAsync(layers.gaia ? 'gaia' : null, (s) => api.overlay(sequence.id, 'gaia', s))
  const allwise = useAsync(layers.allwise ? 'allwise' : null, (s) => api.overlay(sequence.id, 'allwise', s))
  const cands = useAsync(layers.candidates && canCompare ? `cand:${refIdx}:${cur}` : null, (s) => api.candidates(sequence.id, refIdx, cur, s))

  const frameMjd = useMemo(() => frames.map((f) => f.mjd_avg), [frames])
  const frameDates = useMemo(() => frames.map((f) => f.date_avg), [frames])
  const frameUrls = useMemo(() => frames.map((f) => f.image_url), [frames])
  const tracks = useMemo(() => tracksOf(marks, frameMjd), [marks, frameMjd])
  const shownMarks = layers.marks ? marks : []
  const shownTracks = layers.marks ? tracks : []
  const hasPrediction = frames.some((f) => f.target_predicted)
  const canMark = !readOnly && mode !== 'stack' && mode !== 'trackstack'
  const canPlay = n >= 2 && (mode === 'single' || mode === 'side')
  const frame = frames[cur]
  const selectedMark = marks.find((m) => m.id === selectedId) ?? null

  const overlaysFor = (frameIndex: number | null): PaneOverlays => ({
    gaia: layers.gaia && gaia.status === 'ready' ? gaia.data : null,
    allwise: layers.allwise && allwise.status === 'ready' ? allwise.data : null,
    predicted: layers.predicted && frameIndex !== null ? (frames[frameIndex]?.target_predicted ?? null) : null,
    candidates: layers.candidates && canCompare && cands.status === 'ready' ? cands.data.candidates : null,
  })

  // ---- frame navigation and playback -----------------------------------------------
  const step = useCallback((d: number) => setCur((c) => (n > 0 ? (c + d + n) % n : 0)), [n, setCur])

  useEffect(() => {
    if (!playing || !canPlay || (integrated && app.mode !== 'observations')) return
    const id = window.setInterval(() => setCur((c) => (c + 1) % n), 1000 / fps)
    return () => window.clearInterval(id)
  }, [playing, canPlay, fps, n, integrated, app.mode, setCur])

  useEffect(() => {
    if (!canPlay && playing) setPlaying(false)
  }, [canPlay, playing, setPlaying])

  const firstFrame = useRef(true)
  useEffect(() => {
    if (firstFrame.current) {
      firstFrame.current = false
      return
    }
    if (programmatic.current) {
      programmatic.current = false
      return
    }
    fire('frame_changed')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cur])

  useEffect(() => {
    if (!playing && frame) setAnnounce(t('play.live', { i: cur + 1, n, date: fmtDateUTC(frame.date_avg) }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cur, playing, lang])

  const changeMode = useCallback(
    (m: ViewMode) => {
      if (m !== 'single' && n < 2) return
      if ((m === 'side' || m === 'diff') && cur === refIdx) setCur(refIdx === n - 1 ? 0 : n - 1)
      if (m === 'diff' || m === 'stack') setPlaying(false)
      if (m === 'stack') setMarkMode(false)
      setMode(m)
    },
    [cur, refIdx, n, setCur, setMode, setPlaying],
  )

  const swap = useCallback(() => {
    if (n < 2) return
    if (cur === refIdx) {
      setCur(refIdx === n - 1 ? 0 : n - 1)
      return
    }
    setCur(refIdx)
    setRefIdx(cur)
  }, [cur, refIdx, n, setCur, setRefIdx])
  // Blink: the comparator's core gesture. With A and B on the same frame there is nothing to compare yet,
  // so the first press moves B to the next real frame; after that it flips A and B.
  const blink = useCallback(() => { if (refIdx === cur && n > 1) setCur((cur + 1) % n); else swap() }, [refIdx, cur, n, setCur, swap])

  // ---- view helpers ----------------------------------------------------------------
  const zoomBy = useCallback((factor: number) => setView((v) => clampView({ ...v, zoom: v.zoom * factor }, grid)), [grid])
  const panImage = useCallback(
    (fx: number, fy: number) => setView((v) => clampView({ ...v, cx: v.cx + (fx * grid.nx) / v.zoom, cy: v.cy + (fy * grid.ny) / v.zoom }, grid)),
    [grid],
  )
  const centreOn = useCallback(
    (ra: number, dec: number, minZoom = 1) => {
      const p = skyToPng(grid, ra, dec)
      if (p) setView((v) => clampView({ zoom: Math.max(v.zoom, minZoom), cx: p.x, cy: p.y }, grid))
    },
    [grid],
  )

  useEffect(() => {
    if (!integrated) return
    const handler = (event: Event) => {
      const action = (event as CustomEvent<{ action: string }>).detail.action
      if (action === 'zoom-in') zoomBy(1.5)
      if (action === 'zoom-out') zoomBy(1 / 1.5)
      if (action === 'reset') setView(defaultView(grid))
      if (action === 'up') panImage(0, -.15)
      if (action === 'down') panImage(0, .15)
    }
    window.addEventListener('blinkspace:viewer-control', handler)
    return () => window.removeEventListener('blinkspace:viewer-control', handler)
  }, [integrated, zoomBy, panImage, grid])

  // ---- marks -----------------------------------------------------------------------
  const createMark = useCallback(
    (sky: Sky, radius: number | null, frameIndex: number) => {
      if (readOnly) return
      if (marks.length >= MAX_MARKS) {
        setAnnounce(t('mark.limit', { n: MAX_MARKS }))
        return
      }
      let trackId = activeTrack
      if (!trackId && markClass === 'possible_motion') {
        trackId = newId('t')
        setActiveTrack(trackId)
      }
      const res = addMark(marks, {
        ra_deg: sky.ra,
        dec_deg: sky.dec,
        radius_arcsec: radius,
        frame_index: frameIndex,
        classification: trackId ? 'possible_motion' : markClass,
        track_id: trackId,
      })
      if (!res.mark) return
      const made = res.mark
      setMarks(() => res.marks)
      setSelectedId(made.id)
      setLayers((l) => (l.marks ? l : { ...l, marks: true }))
      setTab('marks')
      setAnnounce(t('mark.added', { cls: tc('cls', made.classification), i: frameIndex + 1 }))
      fire('mark_added')
    },
    [readOnly, marks, activeTrack, markClass, setMarks, t, tc, fire, setLayers, setTab],
  )

  const onUpdateMark = useCallback((id: string, patch: MarkPatch) => setMarks((ms) => updateMark(ms, id, patch)), [setMarks])
  const onMoveMark = useCallback((id: string, sky: Sky) => setMarks((ms) => moveMark(ms, id, sky.ra, sky.dec)), [setMarks])
  const onDeleteMark = useCallback(
    (id: string) => {
      setMarks((ms) => deleteMark(ms, id))
      setSelectedId((s) => (s === id ? null : s))
      setAnnounce(t('mark.deleted'))
    },
    [setMarks, t],
  )

  const onGotoMark = useCallback(
    (m: Mark) => {
      if (mode === 'diff' || mode === 'stack') setMode('single')
      setCur(m.frame_index)
      centreOn(m.ra_deg, m.dec_deg)
    },
    [mode, centreOn, setMode, setCur],
  )

  const onContinueTrack = useCallback(
    (m: Mark) => {
      const id = m.track_id ?? newId('t')
      if (!m.track_id || m.classification !== 'possible_motion') {
        setMarks((ms) => updateMark(ms, m.id, { track_id: id, classification: 'possible_motion' }))
      }
      setActiveTrack(id)
      setMarkClass('possible_motion')
      if (mode === 'stack') setMode('single')
      setMarkMode(true)
    },
    [mode, setMarks, setMode],
  )

  const onMarkClass = useCallback((c: Classification) => {
    setMarkClass(c)
    if (c !== 'possible_motion') setActiveTrack(null)
  }, [])

  const adoptCandidate = useCallback(
    (c: Candidate) => {
      if (readOnly) return
      let list = marks
      let last: Mark | null = null
      const track = c.ra_from !== undefined && c.dec_from !== undefined ? newId('t') : null
      if (track && c.ra_from !== undefined && c.dec_from !== undefined) {
        const r = addMark(list, { ra_deg: c.ra_from, dec_deg: c.dec_from, frame_index: refIdx, classification: 'possible_motion', track_id: track })
        list = r.marks
      }
      const r2 = addMark(list, { ra_deg: c.ra, dec_deg: c.dec, frame_index: cur, classification: c.classification, track_id: track })
      list = r2.marks
      last = r2.mark
      if (!last) return
      setMarks(() => list)
      setSelectedId(last.id)
      setLayers((l) => ({ ...l, marks: true }))
      setTab('marks')
      fire('mark_added')
    },
    [readOnly, marks, refIdx, cur, setMarks, fire, setLayers, setTab],
  )

  // ---- keyboard --------------------------------------------------------------------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (integrated && (app.mode !== 'observations' || !['m', 'M', 'Delete'].includes(e.key))) return
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return
      const el = e.target as HTMLElement | null
      if (el?.closest?.('input, textarea, select, [contenteditable="true"], [data-dialog]')) return
      const onControl = Boolean(el?.closest?.('button, a, summary'))
      const done = () => e.preventDefault()
      switch (e.key) {
        case ' ':
          if (onControl) return
          if (canPlay) setPlaying((p) => !p)
          return done()
        case 'ArrowLeft':
          if (e.shiftKey) panImage(-0.15, 0)
          else step(-1)
          return done()
        case 'ArrowRight':
          if (e.shiftKey) panImage(0.15, 0)
          else step(1)
          return done()
        case 'ArrowUp':
          if (!e.shiftKey) return
          panImage(0, -0.15)
          return done()
        case 'ArrowDown':
          if (!e.shiftKey) return
          panImage(0, 0.15)
          return done()
        case 'Home':
          setCur(0)
          return done()
        case 'End':
          setCur(Math.max(0, n - 1))
          return done()
        case '+':
        case '=':
          zoomBy(1.5)
          return done()
        case '-':
        case '_':
          zoomBy(1 / 1.5)
          return done()
        case '0':
          setView(defaultView(grid))
          return done()
        case 'b':
        case 'B':
          blink()
          return done()
        case 'm':
        case 'M':
          if (canMark) setMarkMode((m) => !m)
          return done()
        case '?':
          setDialog('keys')
          return done()
        case 'Delete':
          if (selectedId && !readOnly) {
            onDeleteMark(selectedId)
            done()
          }
          return
        case 'Escape':
          if (markMode) setMarkMode(false)
          else if (selectedId) setSelectedId(null)
          else if (playing) setPlaying(false)
          return
        default:
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // ---- wavelength re-run -----------------------------------------------------------
  const job = useJob()
  const rerun = (lamUm: number) => {
    const p = sequence.params
    const req: SearchRequest = { lam_um: lamUm, fov_arcmin: p.fov_arcmin, max_frames: p.max_frames }
    if (p.target_id) req.target_id = p.target_id
    else {
      req.ra = p.ra_deg
      req.dec = p.dec_deg
      req.ra_unit = 'deg'
    }
    if (p.mjd_min !== null) req.date_from = String(p.mjd_min)
    if (p.mjd_max !== null) req.date_to = String(p.mjd_max)
    job.start(req)
  }
  useEffect(() => {
    if (job.state.phase === 'done') navigate(`/s/${job.state.sequenceId}`)
  }, [job.state])

  const getView = useCallback(() => encodeView({ view, cur, ref: refIdx, mode, layers }, grid), [view, cur, refIdx, mode, layers, grid])

  if (n === 0 || !frame) {
    return <ErrorBox message={t('seq.empty')} />
  }

  // ---- panes -----------------------------------------------------------------------
  const paneCommon = {
    grid,
    view,
    onView: setView,
    marks: shownMarks,
    tracks: shownTracks,
    frameDates,
    selectedId,
    markMode,
    readOnly,
    onSelect: (id: string | null) => {
      setSelectedId(id)
      if (id) setTab('marks')
    },
    onCreate: createMark,
    onMove: onMoveMark,
    onCursor: setCursor,
  }
  const frameChip = (label: string | null, i: number) => `${label ? `${label} · ` : ''}${fmtDateUTC(frames[i].date_avg)}`
  const maskOf = (i: number) => (layers.mask ? frames[i].mask_url : null)

  let panes
  if (mode === 'side') {
    panes = (
      <>
        <Pane
          {...paneCommon}
          imageUrl={frames[refIdx].image_url}
          preload={frameUrls}
          maskUrl={maskOf(refIdx)}
          chip={frameChip(t('mode.paneA'), refIdx)}
          ariaLabel={t('pane.label', { what: frameChip(t('mode.paneA'), refIdx) })}
          frameIndex={refIdx}
          overlays={overlaysFor(refIdx)}
        />
        <Pane
          {...paneCommon}
          imageUrl={frame.image_url}
          preload={frameUrls}
          maskUrl={maskOf(cur)}
          chip={frameChip(t('mode.paneB'), cur)}
          ariaLabel={t('pane.label', { what: frameChip(t('mode.paneB'), cur) })}
          frameIndex={cur}
          overlays={overlaysFor(cur)}
        />
      </>
    )
  } else if (mode === 'diff') {
    const url = diff.data?.image_url ?? null
    panes = (
      <Pane
        {...paneCommon}
        imageUrl={url}
        maskUrl={null}
        chip={`${t('mode.diff')} · B − A`}
        ariaLabel={t('pane.label', { what: t('diff.title') })}
        frameIndex={cur}
        overlays={overlaysFor(cur)}
        busy={diff.status === 'loading'}
      />
    )
  } else if (mode === 'trackstack') {
    panes = <Pane {...paneCommon} imageUrl={trackStack.data?.image_url ?? null} maskUrl={null} chip={t('mode.trackstack')} ariaLabel={t('mode.trackstack')} frameIndex={null} overlays={overlaysFor(null)} busy={trackStack.status === 'loading'} />
  } else if (mode === 'stack') {
    panes = (
      <Pane
        {...paneCommon}
        imageUrl={stack.data?.image_url ?? null}
        maskUrl={null}
        chip={t('stack.title', { n })}
        ariaLabel={t('pane.label', { what: t('stack.title', { n }) })}
        frameIndex={null}
        overlays={overlaysFor(null)}
        busy={stack.status === 'loading'}
      />
    )
  } else {
    panes = (
      <Pane
        {...paneCommon}
        imageUrl={frame.image_url}
        preload={frameUrls}
        maskUrl={maskOf(cur)}
        chip={frameChip(null, cur)}
        ariaLabel={t('pane.label', { what: t('play.live', { i: cur + 1, n, date: fmtDateUTC(frame.date_avg) }) })}
        frameIndex={cur}
        overlays={overlaysFor(cur)}
      />
    )
  }

  const tabs: [Tab, string][] = [
    ['info', t('tab.info')],
    ['layers', t('tab.layers')],
    ['marks', `${t('tab.marks')}${marks.length ? ` (${marks.length})` : ''}`],
    ['curve', t('tab.curve')],
    ['wave', t('tab.wave')],
  ]
  if (tutorial || tutsHere.length > 0) tabs.push(['task', t('tab.task')])
  if (assistant.data?.enabled) tabs.push(['assistant', t('assistant.title')])

  const onTabKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.preventDefault()
    const i = tabs.findIndex(([k]) => k === tab)
    const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length][0]
    setTab(next)
    document.getElementById(`tab-${next}`)?.focus()
  }

  const title = target ? target.name : t('seq.title.coords', { ra: fmtRaHms(meta.center.ra_deg, 1), dec: fmtDecDms(meta.center.dec_deg, 0) })
  const warnings = meta.warnings ?? []
  const single = n < 2 || warnings.includes('single_frame') || sequence.status !== 'ready'
  const rejected = meta.selection?.rejected_after_download ?? []
  const frameOptions = frames.map((f, i) => (
    <option key={i} value={i}>
      {i + 1} · {fmtDateUTC(f.date_avg)}
    </option>
  ))

  return (
    <div className={integrated ? `viewer integrated-viewer ${app.mode === 'observations' && app.stageView === 'frames' ? 'show-frames' : 'hide-frames'} ${app.drawer.open ? 'drawer-open' : 'drawer-closed'}` : 'viewer'} data-view={mode}>
      <div className="viewer-main">
        <header className="viewer-head">
          <div>
            <h1>{title}</h1>
            <p className="muted mono small">
              {t('seq.summary', {
                n,
                v: meta.n_visits,
                d: meta.span_days.toFixed(meta.span_days < 10 ? 1 : 0),
                lam: meta.wavelength.lam_ref_um.toFixed(3),
              })}
            </p>
          </div>
          <div className="row-actions">
            <button type="button" className="btn btn-small" onClick={() => setDialog('prov')}>
              {t('info.provenance')}
            </button>
            <button type="button" className="btn btn-icon" onClick={() => setDialog('keys')} aria-label={t('app.shortcuts')} title={t('app.shortcuts')}>
              <Icon name="help" />
            </button>
          </div>
        </header>

        <div className="banners">
          {single && (
            <p className="notice notice-warn" role="status">
              {t('seq.insufficientBanner')}
            </p>
          )}
          {warnings
            .filter((w) => w !== 'single_frame')
            .map((w) => (
              <div key={w} className="notice notice-warn" role="status">
                {tc('warn', w)}
                {w === 'partial_data' && rejected.length > 0 && (
                  <details>
                    <summary>
                      {t('warn.rejectedList')} ({rejected.length})
                    </summary>
                    <ul className="plain mono small">
                      {rejected.map((r, i) => (
                        <li key={i}>
                          {r.obs_id} · D{r.detector} — {tc('reject', r.reason)}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            ))}
        </div>

        <div className="toolbar" role="toolbar" aria-label={t('mode.label')}>
          <Glider small className="kx-modes" label={t('mode.label')} value={mode} onChange={changeMode}
            items={(['single', 'side', 'diff', 'stack', 'trackstack'] as ViewMode[]).map((m) => ({ id: m, label: t(`mode.${m}`), disabled: (m !== 'single' && n < 2) || (m === 'trackstack' && !hasPrediction), title: m !== 'single' && n < 2 ? t('mode.needTwo') : undefined }))} />
          {n >= 2 && mode !== 'stack' && (
            <div className="ab">
              <label className="field-inline">
                <span>{t('mode.refFrame')}</span>
                <select value={refIdx} onChange={(e) => setRefIdx(Number(e.target.value))}>
                  {frameOptions}
                </select>
              </label>
              <button type="button" className="btn btn-small" onClick={swap} title={t('mode.swapHint')} aria-label={t('mode.swapHint')}>
                <KIcon name="swap" size={16} />
              </button>
              <label className="field-inline">
                <span>{t('mode.curFrame')}</span>
                <select value={cur} onChange={(e) => setCur(Number(e.target.value))}>
                  {frameOptions}
                </select>
              </label>
            </div>
          )}
          <div className="zoom">
            <button type="button" className="btn btn-icon" onClick={() => zoomBy(1 / 1.5)} disabled={view.zoom <= MIN_ZOOM} aria-label={t('zoom.out')} title={t('zoom.out')}>
              <Icon name="minus" />
            </button>
            <span className="mono small zoom-level" aria-label={t('zoom.level', { z: view.zoom.toFixed(1) })}>
              {view.zoom.toFixed(1)}×
            </span>
            <button type="button" className="btn btn-icon" onClick={() => zoomBy(1.5)} disabled={view.zoom >= MAX_ZOOM} aria-label={t('zoom.in')} title={t('zoom.in')}>
              <Icon name="plus" />
            </button>
            <button type="button" className="btn btn-icon" onClick={() => setView(defaultView(grid))} aria-label={t('zoom.reset')} title={t('zoom.reset')}>
              <Icon name="reset" />
            </button>
            {n >= 2 && mode !== 'stack' && mode !== 'trackstack' && (
              <button type="button" className="btn btn-blink" onClick={blink} aria-label={lang === 'tr' ? 'Kareler arasında kırpıştır (blink)' : 'Blink between frames'} title={t('mode.swapHint')}>
                <KIcon name="blink" size={16} />
                <span>Blink</span>
                <kbd>B</kbd>
              </button>
            )}
            {!readOnly && (
              <button
                type="button"
                className={markMode ? 'btn btn-primary btn-mark' : 'btn btn-mark'}
                aria-pressed={markMode}
                disabled={!canMark}
                onClick={() => setMarkMode((m) => !m)}
                title={canMark ? undefined : t('stack.noMark')}
              >
                <Icon name="mark" size={16} />
                <span>{markMode ? t('mark.stop') : t('mark.modeOff')}</span>
              </button>
            )}
          </div>
        </div>

        {mode === 'diff' && (
          <div className="derived" role="region" aria-label={t('diff.title')}>
            <div className="derived-head">
              <strong>{t('diff.title')}</strong>
              <span className="tag">{t('diff.notRaw')}</span>
              <button type="button" className="btn btn-primary btn-small" onClick={() => changeMode('single')}>
                {t('mode.backToRaw')}
              </button>
            </div>
            {!canCompare && <p className="flag-warn">{t('mode.sameFrame')}</p>}
            {diff.status === 'loading' && <p className="muted">{t('diff.loading')}</p>}
            {diff.status === 'error' && <ErrorBox message={describeApiError(lang, diff.error.code, diff.error.reason)} onRetry={diff.reload} />}
            {diff.data && canCompare && (
              <>
                <p className="mono small">
                  A {fmtDateUTC(frames[diff.data.a]?.date_avg)} → B {fmtDateUTC(frames[diff.data.b]?.date_avg)} · {t('diff.dt')}{' '}
                  {t('diff.days', { d: diff.data.dt_days.toFixed(1) })} · {t('diff.sigma')} {diff.data.sigma_mjy_sr.toFixed(4)} MJy/sr ·{' '}
                  {t('diff.scale')} ±{diff.data.display_scale_mjy_sr.toFixed(3)} MJy/sr · {t('diff.valid')} {(diff.data.valid_frac * 100).toFixed(1)}%
                </p>
                <p className="muted small">{t('diff.legend')}</p>
                <details>
                  <summary>
                    {t('caveat.title')} ({diff.data.caveats.length})
                  </summary>
                  <Caveats codes={diff.data.caveats} />
                </details>
              </>
            )}
          </div>
        )}
        {mode === 'stack' && (
          <div className="derived" role="region" aria-label={t('stack.title', { n })}>
            <div className="derived-head">
              <strong>{t('stack.title', { n: stack.data?.n_frames ?? n })}</strong>
              <span className="tag">{t('diff.notRaw')}</span>
              <button type="button" className="btn btn-primary btn-small" onClick={() => changeMode('single')}>
                {t('mode.backToRaw')}
              </button>
            </div>
            {stack.status === 'loading' && <p className="muted">{t('stack.loading')}</p>}
            {stack.status === 'error' && <ErrorBox message={describeApiError(lang, stack.error.code, stack.error.reason)} onRetry={stack.reload} />}
            {stack.data && (
              <>
                <p className="mono small">
                  {t('stack.span')} {t('diff.days', { d: stack.data.span_days.toFixed(1) })}
                  {typeof stack.data.target_motion_px === 'number'
                    ? ` · ${t('stack.motion')} ${t('stack.motionPx', { px: stack.data.target_motion_px.toFixed(2) })}`
                    : ''}{' '}
                  · {t('diff.valid')} {(stack.data.valid_frac * 100).toFixed(1)}%
                </p>
                <details open>
                  <summary>
                    {t('caveat.title')} ({stack.data.caveats.length})
                  </summary>
                  <Caveats codes={stack.data.caveats} />
                </details>
              </>
            )}
          </div>
        )}

        {mode === 'trackstack' && <div className="derived"><p>{t('trackstack.note')}</p>{trackStack.status === 'error' && <ErrorBox message={describeApiError(lang, trackStack.error.code, trackStack.error.reason)} onRetry={trackStack.reload} />}</div>}
        <div className={mode === 'side' ? 'stage stage-side' : 'stage'}>
          {panes}
          {mode === 'single' && n >= 2 && (
            <div className="kx-film" role="group" aria-label={lang === 'tr' ? 'Tüm gerçek kareler' : 'All real frames'}>
              {frames.map((f, i) => (
                <button
                  key={f.image_url}
                  type="button"
                  className="kx-film-b"
                  data-on={i === cur || undefined}
                  data-ref={i === refIdx || undefined}
                  aria-pressed={i === cur}
                  aria-label={`${lang === 'tr' ? 'Küçük resim' : 'Thumbnail'} ${i + 1} · ${fmtDateUTC(f.date_avg)}`}
                  title={fmtDateUTC(f.date_avg)}
                  style={{ backgroundImage: `url(${f.image_url})`, animationDelay: `${120 + i * 45}ms` }}
                  onClick={() => setCur(i)}
                >
                  <span>{i + 1}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <p className="wavelength-line mono">A · {frames[refIdx].lam_um.toFixed(3)} µm / B · {frame.lam_um.toFixed(3)} µm · Δλ = {(Math.abs(frame.lam_um - frames[refIdx].lam_um) / meta.wavelength.bw_ref_um).toFixed(3)} Δλ(FWHM)</p>
        <p id="pane-help" className="sr-only">
          {t('pane.help')}
        </p>

        <Readout view={view} grid={grid} />

        <div className="transport">
          <div className="transport-slot">
            <div className="transport-buttons" ref={playbackControls}>
              <RingPlay playing={playing} onToggle={() => setPlaying((p) => !p)} disabled={!canPlay} progress={n > 1 ? cur / (n - 1) : 0} segments={Math.max(1, n - 1)} labelPlay={t('play.play')} labelPause={t('play.pause')} />
              <button type="button" className="btn btn-icon" onClick={() => step(-1)} disabled={n < 2} aria-label={t('play.prev')} title={t('play.prev')}>
                <KIcon name="prev" />
              </button>
              <button type="button" className="btn btn-icon" onClick={() => step(1)} disabled={n < 2} aria-label={t('play.next')} title={t('play.next')}>
                <KIcon name="next" />
              </button>
              <label className="field-inline">
                <span className="sr-only">{t('play.speed')}</span>
                <select value={fps} onChange={(e) => setFps(Number(e.target.value))} aria-label={t('play.speed')}>
                  {SPEEDS.map((s) => (
                    <option key={s} value={s}>
                      {t('play.fps', { n: s })}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          <div className="now">
            <span className="sr-only" data-testid="current-date">{fmtDateUTC(frame.date_avg)}</span>
            <span className="now-date" aria-hidden="true"><Odometer text={fmtDateUTC(frame.date_avg)} decorative /></span>
            <span className="muted mono small">{t('play.frameOf', { i: cur + 1, n })}</span>
          </div>
        </div>

        <Timeline
          frames={frames.map((f) => ({ mjd: f.mjd_avg, date: f.date_avg }))}
          current={cur}
          reference={refIdx}
          showReference={n >= 2 && mode !== 'stack'}
          onSelect={setCur}
        />
        <p className="muted small play-note">{t('play.note')}</p>
        <p className="sr-only" aria-live="polite" role="status" data-testid="announce">
          {announce}
        </p>
      </div>

      <aside className="viewer-side" aria-label={t('tab.panels')}>
        {integrated && <button type="button" className="drawer-close btn btn-icon" aria-label={t('app.close')} onClick={() => setAppState(s => ({ drawer: { ...s.drawer, open: false } }))}><Icon name="close" /></button>}
        <div className="tabs" role="tablist" aria-label={t('tab.panels')} onKeyDown={onTabKey}>
          {tabs.map(([k, label]) => (
            <button
              key={k}
              id={`tab-${k}`}
              type="button"
              role="tab"
              aria-selected={tab === k}
              aria-controls="tabpanel"
              tabIndex={tab === k ? 0 : -1}
              className={tab === k ? 'tab tab-on' : 'tab'}
              onClick={() => setTab(k)}
            >
              {label}
            </button>
          ))}
        </div>
        <div id="tabpanel" role="tabpanel" aria-labelledby={`tab-${tab}`} className="tabpanel">
          {tab === 'assistant' && (integrated&&new URLSearchParams(window.location.search).get('ui')!=='legacy'?<section className="panel-body"><h3>QFIT</h3><p>{lang==='tr'?'Seçili hedefi, gözlem karesini ve kaynakları QFIT ile incele.':'Explore the selected target, observation frame and sources with QFIT.'}</p><button className="btn" onClick={()=>{setAppState(s=>({drawer:{...s.drawer,open:false}}));window.dispatchEvent(new Event('blinkspace:assistant'))}}>{lang==='tr'?'QFIT’i aç':'Open QFIT'}</button></section>:<AssistantPanel sequence={sequence} marks={marks} target={motionTarget} />)}
          {tab === 'info' && (
            <InfoPanel sequence={sequence} frame={frame} derived={mode === 'diff' || mode === 'stack'} onProvenance={() => setDialog('prov')} />
          )}
          {tab === 'layers' && (
            <LayersPanel
              layers={layers}
              onToggle={(k) => setLayers((l) => ({ ...l, [k]: !l[k] }))}
              gaia={gaia}
              allwise={allwise}
              candidates={cands}
              hasPrediction={hasPrediction}
              canCompare={canCompare}
              stretch={meta.display?.stretch ?? 'asinh'}
              readOnly={readOnly}
              onShowCandidate={(c) => centreOn(c.ra, c.dec, 3)}
              onAdoptCandidate={adoptCandidate}
            />
          )}
          {tab === 'marks' && (
            <MarksPanel
              sequence={sequence}
              targetName={target?.name ?? null}
              marks={marks}
              tracks={tracks}
              selectedId={selectedId}
              readOnly={readOnly}
              canMark={canMark}
              markMode={markMode}
              markClass={markClass}
              activeTrack={activeTrack}
              draft={draft}
              onDraft={setDraft}
              onMarkMode={setMarkMode}
              onMarkClass={onMarkClass}
              onSelect={setSelectedId}
              onUpdate={onUpdateMark}
              onDelete={onDeleteMark}
              onGoto={onGotoMark}
              onContinueTrack={onContinueTrack}
              onEndTrack={() => setActiveTrack(null)}
              getView={getView}
              onShared={() => fire('observation_shared')}
            />
          )}
          {tab === 'curve' && <LightPanel sequence={sequence} selectedMark={selectedMark} current={cur} onSelectFrame={setCur} hasTarget={hasPrediction} />}
          {tab === 'wave' && (
            <>
              <WavePanel sequence={sequence} onRerun={rerun} />
              <SpectrumPanel sequence={sequence} />
            </>
          )}
          {tab === 'task' &&
            (tutorial ? (
              <>
                {tutorial.target_id !== meta.target_id && <p className="notice notice-warn">{t('tut.otherTarget')}</p>}
                <TutorialPanel
                  tutorial={tutorial}
                  progress={progressOf(progress, tutorial.id)}
                  onAnswer={(id) => updateProgress(tutorial.id, (p) => answerQuiz(tutorial, p, id))}
                  onReset={() => {
                    updateProgress(tutorial.id, () => ({ done: [] }))
                  }}
                  onClose={() => setActiveTut(null)}
                />
              </>
            ) : (
              <section className="panel-body" aria-label={t('tut.list')}>
                {tutsHere.length === 0 ? (
                  <p className="muted">{t('tut.noneForTarget')}</p>
                ) : (
                  <TutorialList
                    tutorials={tutsHere}
                    completed={(id) => {
                      const tu = tutsHere.find((x) => x.id === id)
                      return tu ? isComplete(tu, progressOf(progress, id)) : false
                    }}
                    onStart={(tu) => setActiveTut(tu.id)}
                  />
                )}
              </section>
            ))}
        </div>
      </aside>

      {dialog === 'prov' && <ProvenanceDialog sequence={sequence} onClose={() => setDialog(null)} />}
      {dialog === 'keys' && <ShortcutsDialog onClose={() => setDialog(null)} />}
      {job.state.phase !== 'idle' && (
        <Dialog title={t('wave.selection')} onClose={job.reset}>
          <JobPanel
            state={job.state}
            targetName={target?.name ?? null}
            onCancel={job.cancel}
            onRetry={job.start}
            onReset={job.reset}
            onOpen={(id) => navigate(`/s/${id}`)}
          />
        </Dialog>
      )}
    </div>
  )
}

function Readout({ view, grid }: { view: View; grid: Sequence['meta']['grid'] }) {
  const { t } = useI18n()
  const cursor = useCursor()
  const sky = cursor ?? pngToSky(grid, view.cx, view.cy)
  return (
    <div className="readout mono" aria-label={cursor ? t('cursor.label') : t('cursor.centre')}>
      <span className="muted readout-kind">{cursor ? t('cursor.label') : t('cursor.centre')}</span>
      <span>
        {t('cursor.ra')} {fmtRaHms(sky.ra)} <span className="muted">{sky.ra.toFixed(5)}°</span>
      </span>
      <span>
        {t('cursor.dec')} {fmtDecDms(sky.dec)} <span className="muted">{fmtSignedDeg(sky.dec)}</span>
      </span>
    </div>
  )
}

type LcSource = { key: string; kind: 'target' } | { key: string; kind: 'mark'; ra: number; dec: number }

function LightPanel({
  sequence,
  selectedMark,
  current,
  hasTarget,
  onSelectFrame,
}: {
  sequence: Sequence
  selectedMark: Mark | null
  current: number
  hasTarget: boolean
  onSelectFrame: (i: number) => void
}) {
  const { t, lang } = useI18n()
  const [src, setSrc] = useState<LcSource | null>(null)
  const lc = useAsync(src ? src.key : null, (signal) =>
    src && src.kind === 'mark' ? api.lightcurveAt(sequence.id, src.ra, src.dec, signal) : api.lightcurveTarget(sequence.id, signal),
  )

  return (
    <section className="panel-body" aria-label={t('lc.title')}>
      <div className="lc-sources">
        {hasTarget && (
          <button
            type="button"
            className={src?.kind === 'target' ? 'btn btn-primary' : 'btn'}
            aria-pressed={src?.kind === 'target'}
            onClick={() => setSrc({ key: 'target', kind: 'target' })}
          >
            {t('lc.load')}: {t('lc.sourceTarget')}
          </button>
        )}
        <button
          type="button"
          className={src?.kind === 'mark' ? 'btn btn-primary' : 'btn'}
          aria-pressed={src?.kind === 'mark'}
          disabled={!selectedMark}
          onClick={() =>
            selectedMark &&
            setSrc({
              key: `mark:${selectedMark.ra_deg.toFixed(6)}:${selectedMark.dec_deg.toFixed(6)}`,
              kind: 'mark',
              ra: selectedMark.ra_deg,
              dec: selectedMark.dec_deg,
            })
          }
        >
          {t('lc.load')}: {t('lc.sourceMark')}
        </button>
        {!selectedMark && <p className="muted small">{t('lc.pickMark')}</p>}
      </div>
      {lc.status === 'loading' && <p className="muted">{t('lc.loading')}</p>}
      {lc.status === 'error' && <ErrorBox message={describeApiError(lang, lc.error.code, lc.error.reason)} onRetry={lc.reload} />}
      {lc.status === 'ready' && <LightCurveChart curve={lc.data} current={current} onSelect={onSelectFrame} />}
    </section>
  )
}

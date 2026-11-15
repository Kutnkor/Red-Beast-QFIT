// Home: two entry points (ready-made explorations, coordinate search) and, below them, the tutorials.

import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../i18n'
import { getHealth, getTargets, getTutorials } from '../lib/data'
import { describeApiError } from '../lib/errors'
import { navigate } from '../lib/router'
import { isComplete, loadProgress, progressOf } from '../lib/tutorials'
import type { Health, SearchRequest, Target, Tutorial } from '../lib/types'
import { ErrorBox, Link, useAsync } from '../ui/common'
import { TutorialList } from '../viewer/TutorialPanel'
import { JobPanel, useJob } from './JobPanel'
import { FALLBACK_LIMITS, SearchForm, valuesFromQuery, type FormValues } from './SearchForm'

export function Home({ query }: { query: URLSearchParams }) {
  const { t, pick, lang } = useI18n()
  const targets = useAsync<Target[]>('targets', () => getTargets())
  const tutorials = useAsync<Tutorial[]>('tutorials', () => getTutorials())
  const health = useAsync<Health>('health', () => getHealth())
  const limits = health.data?.limits ?? FALLBACK_LIMITS
  const job = useJob()
  const { state } = job
  const [pendingTut, setPendingTut] = useState<string | null>(null)
  const jobRef = useRef<HTMLDivElement>(null)

  // query-string entry (embedding): start immediately, once
  const started = useRef(false)
  const [initialForm] = useState<FormValues | null>(() => valuesFromQuery(query, FALLBACK_LIMITS))
  useEffect(() => {
    if (started.current) return
    started.current = true
    const targetId = query.get('target')
    if (targetId) {
      job.start({ target_id: targetId })
    } else if (initialForm) {
      const req: SearchRequest = { ra: initialForm.ra, dec: initialForm.dec, ra_unit: initialForm.unit }
      const fov = Number(initialForm.fov)
      if (Number.isFinite(fov)) req.fov_arcmin = fov
      const frames = Number(query.get('frames'))
      if (query.get('frames') && Number.isInteger(frames)) req.max_frames = frames
      const lam = Number(initialForm.lam)
      if (initialForm.lam && Number.isFinite(lam)) req.lam_um = lam
      job.start(req)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const tutSuffix = pendingTut ? `?tut=${encodeURIComponent(pendingTut)}` : ''
  useEffect(() => {
    if (state.phase === 'done') navigate(`/s/${state.sequenceId}${tutSuffix}`)
  }, [state, tutSuffix])

  useEffect(() => {
    if (state.phase !== 'idle') jobRef.current?.scrollIntoView?.({ block: 'nearest' })
  }, [state.phase])

  const request = state.phase === 'idle' ? null : state.request
  const isFormRequest = request !== null && !request.target_id
  // validation and transport errors of a form search are shown next to the form
  const formError = state.phase === 'failed' && state.source === 'http' && isFormRequest ? describeApiError(lang, state.code, state.reason) : null
  const showJob = state.phase !== 'idle' && !formError
  const busy = state.phase === 'submitting' || state.phase === 'running'
  const jobTarget = request?.target_id ? (targets.data?.find((x) => x.id === request.target_id)?.name ?? request.target_id) : null

  const startTutorial = (tu: Tutorial) => {
    const target = targets.data?.find((x) => x.id === tu.target_id)
    if (target?.ready_sequence_id) {
      navigate(`/s/${target.ready_sequence_id}?tut=${encodeURIComponent(tu.id)}`)
      return
    }
    setPendingTut(tu.id)
    job.start({ target_id: tu.target_id })
  }

  const progress = loadProgress()

  return (
    <div className="home">
      <section className="home-lead">
        <h1>
          {t('app.name')} <span className="slogan">— {t('app.slogan')}</span>
        </h1>
        <p>{t('home.lead')}</p>
      </section>

      <div ref={jobRef}>
        {showJob && (
          <JobPanel
            state={state}
            targetName={jobTarget}
            onCancel={job.cancel}
            onRetry={job.start}
            onReset={job.reset}
            onOpen={(id) => navigate(`/s/${id}${tutSuffix}`)}
          />
        )}
      </div>

      <div className="entries">
        <section className="entry" aria-labelledby="entry-presets">
          <h2 id="entry-presets">{t('home.presets')}</h2>
          <p className="muted">{t('home.presetsHint')}</p>
          {targets.status === 'loading' && (
            <ul className="targets" aria-busy="true" aria-label={t('app.loading')}>
              {[0, 1, 2, 3, 4].map((i) => (
                <li key={i} className="target skeleton" />
              ))}
            </ul>
          )}
          {targets.status === 'error' && (
            <ErrorBox
              title={t('home.targetsError')}
              message={describeApiError(lang, targets.error.code, targets.error.reason)}
              onRetry={targets.reload}
            />
          )}
          {targets.status === 'ready' && targets.data.length === 0 && <p className="muted">{t('home.targetsEmpty')}</p>}
          {targets.status === 'ready' && targets.data.length > 0 && (
            <ul className="targets">
              {targets.data.map((tg) => {
                const body = (
                  <>
                    <span className="target-top">
                      <strong className="target-name">{tg.name}</strong>
                      <span className={tg.ready_sequence_id ? 'tag tag-ok' : 'tag'}>
                        {tg.ready_sequence_id ? t('home.ready') : t('home.notReady')}
                      </span>
                    </span>
                    <span className="target-meta">
                      {tg.kind === 'motion' ? t('home.kind.motion') : tg.kind === 'variability' ? t('home.kind.variability') : tg.kind}
                      {tg.spectral_type ? ` · ${tg.spectral_type}` : ''}
                      {tg.kind === 'motion' && typeof tg.pixels_per_year === 'number' ? ` · ${t('home.pmPerYear', { px: tg.pixels_per_year })}` : ''}
                    </span>
                    <span className="mono small target-coords">
                      {tg.ra_hms} {tg.dec_dms}
                    </span>
                    <span className="target-note">{pick(tg.notes)}</span>
                  </>
                )
                return (
                  <li key={tg.id}>
                    {tg.ready_sequence_id ? (
                      <Link className="target" to={`/s/${tg.ready_sequence_id}`} aria-label={t('home.openTarget', { name: tg.name })}>
                        {body}
                      </Link>
                    ) : (
                      <button
                        type="button"
                        className="target"
                        disabled={busy}
                        onClick={() => job.start({ target_id: tg.id })}
                        aria-label={t('home.openTarget', { name: tg.name })}
                      >
                        {body}
                      </button>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        <section className="entry" aria-labelledby="entry-search">
          <h2 id="entry-search">{t('home.search')}</h2>
          <p className="muted">{t('home.searchHint')}</p>
          <SearchForm
            limits={limits}
            initial={initialForm}
            busy={busy}
            serverError={formError}
            onSubmit={(req) => {
              setPendingTut(null)
              job.start(req)
            }}
          />
        </section>
      </div>

      <section className="home-tutorials" aria-labelledby="home-tutorials">
        <h2 id="home-tutorials">{t('home.tutorials')}</h2>
        <p className="muted">{t('home.tutorialsHint')}</p>
        {tutorials.status === 'loading' && <p className="muted">{t('app.loading')}</p>}
        {tutorials.status === 'error' && <ErrorBox message={t('tut.error')} onRetry={tutorials.reload} />}
        {tutorials.status === 'ready' && tutorials.data.length === 0 && <p className="muted">{t('home.tutorialsEmpty')}</p>}
        {tutorials.status === 'ready' && tutorials.data.length > 0 && (
          <TutorialList
            tutorials={tutorials.data}
            completed={(id) => {
              const tu = tutorials.data.find((x) => x.id === id)
              return tu ? isComplete(tu, progressOf(progress, id)) : false
            }}
            onStart={startTutorial}
          />
        )}
      </section>
    </div>
  )
}

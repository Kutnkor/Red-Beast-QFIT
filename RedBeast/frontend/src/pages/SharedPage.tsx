// /o/:observationId — read-only view of a shared observation (sequence snapshot + marks + note).

import { useState } from 'react'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { getTargets } from '../lib/data'
import { describeApiError } from '../lib/errors'
import { fmtDateUTC } from '../lib/format'
import { marksForSave, sanitizeMarks } from '../lib/marks'
import { navigate } from '../lib/router'
import { loadDraft, loadToken, saveDraft } from '../lib/storage'
import type { Observation, Target } from '../lib/types'
import { useAsync } from '../ui/common'
import { ObservationCard } from '../viewer/ObservationCard'
import { Viewer } from '../viewer/Viewer'
import { LoadError, ViewerSkeleton } from './ViewerPage'

const unixToIso = (seconds: number) => new Date(seconds * 1000).toISOString()

export function SharedPage({ id }: { id: string }) {
  const { t, lang } = useI18n()
  const obs = useAsync(`obs:${id}`, async (signal) => (await api.observation(id, signal)).observation)
  const targets = useAsync<Target[]>('targets', () => getTargets())
  const [confirm, setConfirm] = useState(false)

  if (obs.status === 'error') {
    return <LoadError title={t('obs.error')} message={describeApiError(lang, obs.error.code, obs.error.reason)} onRetry={obs.reload} />
  }
  if (obs.status !== 'ready') return <ViewerSkeleton label={t('obs.loading')} />

  const o: Observation = obs.data
  const n = o.sequence.frames.length
  const marks = sanitizeMarks(o.marks, n)
  const owned = loadToken(o.id) !== null
  const targetName = targets.data?.find((x) => x.id === o.sequence.meta.target_id)?.name ?? null

  const continueFrom = (force: boolean) => {
    const existing = loadDraft(o.sequence_id)
    const sameObs = existing.observationId === o.id
    if (!force && !sameObs && sanitizeMarks(existing.marks, n).length > 0) {
      setConfirm(true)
      return
    }
    saveDraft(o.sequence_id, {
      marks: marksForSave(marks),
      title: o.title,
      note: o.note,
      // only the creator (edit token in this browser) keeps the link; everyone else starts a new observation
      observationId: owned ? o.id : null,
    })
    navigate(`/s/${o.sequence_id}`)
  }

  return (
    <div className="shared">
      <div className="obs-banner" role="note">
        <div>
          <strong>
            <span className="status-dot" aria-hidden="true" />
            {t('obs.banner')}
          </strong>
          <p>{t('obs.bannerBody')}</p>
          <p className="muted small mono">
            {t('obs.created')} {fmtDateUTC(unixToIso(o.created_at))}
            {o.updated_at - o.created_at > 1 ? ` · ${t('obs.updated')} ${fmtDateUTC(unixToIso(o.updated_at))}` : ''}
          </p>
          {owned && <p className="muted small">{t('obs.youOwn')}</p>}
        </div>
        <div className="obs-banner-actions">
          {confirm ? (
            <div role="alertdialog" aria-label={t('obs.overwrite')}>
              <p>{t('obs.overwrite')}</p>
              <div className="row-actions">
                <button type="button" className="btn btn-primary" onClick={() => continueFrom(true)}>
                  {t('app.yes')}
                </button>
                <button type="button" className="btn" onClick={() => setConfirm(false)}>
                  {t('app.no')}
                </button>
              </div>
            </div>
          ) : (
            <button type="button" className="btn btn-primary" onClick={() => continueFrom(false)}>
              {t('obs.continue')}
            </button>
          )}
        </div>
      </div>

      <Viewer key={o.id} sequence={o.sequence} observation={o} />

      <div className="page-narrow">
        <ObservationCard sequence={o.sequence} marks={marks} title={o.title} note={o.note} targetName={targetName} appVersion={o.app_version} />
      </div>
    </div>
  )
}

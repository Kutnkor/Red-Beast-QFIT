/* eslint-disable react-refresh/only-export-components */
// /s/:sequenceId — editor view of a prepared sequence.

import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { describeApiError } from '../lib/errors'
import { Link, useAsync } from '../ui/common'
import { Viewer } from '../viewer/Viewer'

export function ViewerSkeleton({ label }: { label: string }) {
  return (
    <div className="viewer viewer-skeleton" aria-busy="true" aria-label={label}>
      <div className="viewer-main">
        <div className="skeleton sk-line" />
        <div className="skeleton sk-stage" />
        <div className="skeleton sk-line" />
        <div className="skeleton sk-line" />
      </div>
      <div className="viewer-side">
        <div className="skeleton sk-panel" />
      </div>
      <p className="sr-only" role="status">
        {label}
      </p>
    </div>
  )
}

export function LoadError({ title, message, onRetry }: { title: string; message: string; onRetry: () => void }) {
  const { t } = useI18n()
  return (
    <div className="page-narrow">
      <div className="notice notice-error" role="alert">
        <h1>{title}</h1>
        <p>{message}</p>
        <div className="row-actions">
          <button type="button" className="btn btn-primary" onClick={onRetry}>
            {t('app.retry')}
          </button>
          <Link className="btn" to="/">
            {t('app.home')}
          </Link>
        </div>
      </div>
    </div>
  )
}

export function ViewerPage({ id, tutorialId }: { id: string; tutorialId: string | null }) {
  const { t, lang } = useI18n()
  const seq = useAsync(`seq:${id}`, (signal) => api.sequence(id, signal))

  if (seq.status === 'error') {
    return <LoadError title={t('seq.error')} message={describeApiError(lang, seq.error.code, seq.error.reason)} onRetry={seq.reload} />
  }
  if (seq.status !== 'ready') return <ViewerSkeleton label={t('seq.loading')} />
  return <Viewer key={seq.data.id} sequence={seq.data} tutorialId={tutorialId} />
}

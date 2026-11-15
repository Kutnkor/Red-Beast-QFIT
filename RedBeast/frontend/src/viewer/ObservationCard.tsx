// Observation card: shown on a shared observation and as a preview before sharing.
// User text (title, note, mark notes) is rendered as plain text nodes only.

import { useI18n } from '../i18n'
import { fmtDateUTC, fmtDay, fmtDecDms, fmtRaHms, fmtSignedDeg } from '../lib/format'
import type { Mark, Sequence } from '../lib/types'
import { ExtLink } from '../ui/common'

export function ObservationCard({
  sequence,
  marks,
  title,
  note,
  targetName,
  appVersion,
}: {
  sequence: Sequence
  marks: Mark[]
  title: string
  note: string
  targetName?: string | null
  appVersion?: string
}) {
  const { t, tc } = useI18n()
  const { meta, frames } = sequence
  const c = meta.center

  return (
    <article className="card obs-card" aria-label={t('card.title')}>
      <header className="obs-card-head">
        <h3>{title.trim() || t('obs.untitled')}</h3>
        <p className="status-line">
          <span className="status-dot" aria-hidden="true" />
          {t('card.statusValue')}
        </p>
      </header>

      <ul className="thumbs" aria-label={t('card.frames')}>
        {frames.map((f) => (
          <li key={f.index}>
            <span className="thumb nodata">
              <img className="px" src={f.image_url} alt={t('card.frameAlt', { i: f.index + 1, date: fmtDateUTC(f.date_avg) })} loading="lazy" />
            </span>
            <span className="mono small">{fmtDay(f.date_avg)}</span>
          </li>
        ))}
      </ul>

      <dl className="kv">
        <dt>{t('card.centre')}</dt>
        <dd className="mono">
          {targetName ? `${targetName} · ` : ''}
          {fmtRaHms(c.ra_deg)} {fmtDecDms(c.dec_deg)}
          <br />
          {c.ra_deg.toFixed(5)}° {fmtSignedDeg(c.dec_deg)}
        </dd>
        <dt>{t('card.wavelength')}</dt>
        <dd className="mono">
          {meta.wavelength.lam_ref_um.toFixed(3)} µm ± {(meta.wavelength.tol * meta.wavelength.bw_ref_um).toFixed(3)} µm
        </dd>
        <dt>{t('card.note')}</dt>
        <dd className="user-text">{note.trim() || <span className="muted">{t('card.noNote')}</span>}</dd>
      </dl>

      <h4>{t('card.marks')}</h4>
      {marks.length === 0 ? (
        <p className="muted">{t('card.noMarks')}</p>
      ) : (
        <ol className="obs-marks">
          {marks.map((m) => (
            <li key={m.id}>
              <strong>{tc('cls', m.classification)}</strong>
              <span className="mono">
                {' '}
                {fmtRaHms(m.ra_deg)} {fmtDecDms(m.dec_deg)}
              </span>
              {m.kind === 'region' && m.radius_arcsec ? <span className="mono"> · {t('mark.radius', { r: m.radius_arcsec.toFixed(1) })}</span> : null}
              <br />
              <span className="muted">
                {t('mark.madeOn', { i: m.frame_index + 1, date: fmtDateUTC(frames[m.frame_index]?.date_avg ?? m.date) })}
                {m.track_id ? ` · ${t('mark.track', { id: m.track_id.slice(-4), n: marks.filter((o) => o.track_id === m.track_id).length })}` : ''}
              </span>
              {m.note && <p className="user-text">{m.note}</p>}
            </li>
          ))}
        </ol>
      )}

      <h4>{t('card.sources')}</h4>
      <ul className="sources">
        {frames.map((f) => (
          <li key={f.index}>
            <ExtLink href={f.archive_file_url}>{t('card.sourceFrame', { i: f.index + 1 })}</ExtLink>
            <span className="mono small muted"> {f.obs_id} · D{f.detector}</span>
          </li>
        ))}
      </ul>
      <p className="muted small">{t('footer.credit')}</p>
      <p className="muted small">{t('card.version', { p: meta.pipeline_version, a: appVersion ?? meta.pipeline_version })}</p>
    </article>
  )
}

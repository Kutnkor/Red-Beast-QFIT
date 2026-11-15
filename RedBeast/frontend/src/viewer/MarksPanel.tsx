// Marks list, mark editor and the share form.

import { useState } from 'react'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { describeError } from '../lib/errors'
import { fmtDateUTC, fmtDecDms, fmtRaHms } from '../lib/format'
import { marksForSave, MAX_MARKS, MAX_NOTE, type MarkPatch, type Track } from '../lib/marks'
import { dropToken, loadToken, saveToken, type Draft } from '../lib/storage'
import { CLASSIFICATIONS, type Classification, type Mark, type SavedView, type Sequence } from '../lib/types'
import { CopyButton, Icon, Link } from '../ui/common'
import { ObservationCard } from './ObservationCard'

const MAX_TITLE = 120
const MAX_OBS_NOTE = 2000

export interface MarksPanelProps {
  sequence: Sequence
  targetName: string | null
  marks: Mark[]
  tracks: Track[]
  selectedId: string | null
  readOnly: boolean
  canMark: boolean
  markMode: boolean
  markClass: Classification
  activeTrack: string | null
  draft: Draft
  onDraft: (patch: Partial<Draft>) => void
  onMarkMode: (on: boolean) => void
  onMarkClass: (c: Classification) => void
  onSelect: (id: string | null) => void
  onUpdate: (id: string, patch: MarkPatch) => void
  onDelete: (id: string) => void
  onGoto: (mark: Mark) => void
  onContinueTrack: (mark: Mark) => void
  onEndTrack: () => void
  getView: () => SavedView
  onShared: () => void
}

export function MarksPanel(p: MarksPanelProps) {
  const { t, tc } = useI18n()
  const { marks, sequence, readOnly } = p
  const selected = marks.find((m) => m.id === p.selectedId) ?? null

  return (
    <section className="panel-body" aria-label={t('mark.title')}>
      {readOnly ? (
        <p className="notice notice-info">{t('mark.readOnly')}</p>
      ) : (
        <div className="mark-tools">
          <button
            type="button"
            className={p.markMode ? 'btn btn-primary' : 'btn'}
            aria-pressed={p.markMode}
            disabled={!p.canMark}
            onClick={() => p.onMarkMode(!p.markMode)}
          >
            <Icon name="mark" size={16} />
            {p.markMode ? t('mark.stop') : t('mark.modeOff')}
          </button>
          <label className="field-inline">
            <span>{t('mark.classification')}</span>
            <select value={p.markClass} onChange={(e) => p.onMarkClass(e.target.value as Classification)}>
              {CLASSIFICATIONS.map((c) => (
                <option key={c} value={c}>
                  {tc('cls', c)}
                </option>
              ))}
            </select>
          </label>
          {!p.canMark && <p className="muted small">{t('stack.noMark')}</p>}
          {p.markMode && <p className="muted small">{t('mark.modeOn')}</p>}
          {p.activeTrack && (
            <p className="notice notice-accent">
              {t('mark.trackActive')}{' '}
              <button type="button" className="btn btn-small" onClick={p.onEndTrack}>
                {t('mark.trackEnd')}
              </button>
            </p>
          )}
          {marks.length >= MAX_MARKS && <p className="flag-warn">{t('mark.limit', { n: MAX_MARKS })}</p>}
        </div>
      )}

      {marks.length === 0 ? (
        <p className="muted">{readOnly ? t('card.noMarks') : t('mark.empty')}</p>
      ) : (
        <ol className="mark-list">
          {marks.map((m, i) => {
            const isSel = m.id === p.selectedId
            const track = m.track_id ? p.tracks.find((tr) => tr.id === m.track_id) : null
            return (
              <li key={m.id} className={isSel ? 'mark-item mark-item-selected' : 'mark-item'}>
                <button
                  type="button"
                  className="mark-item-head"
                  aria-expanded={isSel}
                  aria-label={t('mark.select', { label: `${i + 1}, ${tc('cls', m.classification)}` })}
                  onClick={() => p.onSelect(isSel ? null : m.id)}
                >
                  <span className="mark-num">{i + 1}</span>
                  <span>
                    <strong>{tc('cls', m.classification)}</strong>
                    <span className="muted small">
                      {' '}
                      · {m.kind === 'region' ? t('mark.region') : t('mark.point')}
                      {m.kind === 'region' && m.radius_arcsec ? ` · ${t('mark.radius', { r: m.radius_arcsec.toFixed(1) })}` : ''}
                    </span>
                    <br />
                    <span className="mono small">
                      {fmtRaHms(m.ra_deg)} {fmtDecDms(m.dec_deg)}
                    </span>
                    <br />
                    <span className="muted small">
                      {t('mark.madeOn', { i: m.frame_index + 1, date: fmtDateUTC(sequence.frames[m.frame_index]?.date_avg) })}
                      {track ? ` · ${t('mark.track', { id: track.id.slice(-4), n: track.points.length })}` : ''}
                    </span>
                  </span>
                </button>
                {isSel && selected && (
                  <div className="mark-edit">
                    {m.note && readOnly && <p className="user-text">{m.note}</p>}
                    {!readOnly && (
                      <>
                        <label className="field">
                          <span>{t('mark.classification')}</span>
                          <select
                            value={m.classification}
                            onChange={(e) => p.onUpdate(m.id, { classification: e.target.value as Classification })}
                          >
                            {CLASSIFICATIONS.map((c) => (
                              <option key={c} value={c}>
                                {tc('cls', c)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="field">
                          <span>
                            {t('mark.note')} <span className="muted small">{t('share.chars', { n: m.note.length, max: MAX_NOTE })}</span>
                          </span>
                          <textarea
                            rows={2}
                            maxLength={MAX_NOTE}
                            value={m.note}
                            placeholder={t('mark.notePh')}
                            onChange={(e) => p.onUpdate(m.id, { note: e.target.value })}
                          />
                        </label>
                        <p className="muted small">{t('mark.moveHint')}</p>
                      </>
                    )}
                    <div className="row-actions">
                      <button type="button" className="btn btn-small" onClick={() => p.onGoto(m)}>
                        {t('mark.goto')}
                      </button>
                      {!readOnly && (
                        <>
                          <button type="button" className="btn btn-small" onClick={() => p.onContinueTrack(m)}>
                            {t('mark.trackContinue')}
                          </button>
                          <button type="button" className="btn btn-small btn-danger" onClick={() => p.onDelete(m.id)}>
                            {t('mark.delete')}
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      )}

      {!readOnly && <SharePanel {...p} />}
    </section>
  )
}

function SharePanel(p: MarksPanelProps) {
  const { t, lang } = useI18n()
  const { draft, sequence, marks } = p
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [preview, setPreview] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const obsId = draft.observationId ?? null
  const token = obsId ? loadToken(obsId) : null
  const owned = Boolean(obsId && token)
  const shareUrl = obsId ? `${window.location.origin}/o/${obsId}` : null
  const empty = marks.length === 0 && !draft.note.trim() && !draft.title.trim()

  const body = () => ({
    title: draft.title.trim().slice(0, MAX_TITLE),
    note: draft.note.trim().slice(0, MAX_OBS_NOTE),
    marks: marksForSave(marks),
    view: p.getView(),
  })

  const run = async (fn: () => Promise<string>) => {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      setMessage(await fn())
    } catch (err) {
      setError(describeError(lang, err))
    } finally {
      setBusy(false)
    }
  }

  const create = () =>
    run(async () => {
      const res = await api.createObservation(sequence.id, body())
      saveToken(res.observation.id, res.edit_token)
      p.onDraft({ observationId: res.observation.id })
      p.onShared()
      return t('share.saved')
    })

  const update = () =>
    run(async () => {
      if (!obsId || !token) return ''
      await api.updateObservation(obsId, token, body())
      p.onShared()
      return t('share.updated')
    })

  const remove = () =>
    run(async () => {
      setConfirmDelete(false)
      if (!obsId || !token) return ''
      await api.deleteObservation(obsId, token)
      dropToken(obsId)
      p.onDraft({ observationId: null })
      return t('share.deleted')
    })

  return (
    <div className="share">
      <h4>{t('share.title')}</h4>
      <label className="field">
        <span>
          {t('share.obsTitle')} <span className="muted small">{t('share.chars', { n: draft.title.length, max: MAX_TITLE })}</span>
        </span>
        <input
          type="text"
          maxLength={MAX_TITLE}
          value={draft.title}
          placeholder={t('share.obsTitlePh')}
          onChange={(e) => p.onDraft({ title: e.target.value })}
        />
      </label>
      <label className="field">
        <span>
          {t('share.obsNote')} <span className="muted small">{t('share.chars', { n: draft.note.length, max: MAX_OBS_NOTE })}</span>
        </span>
        <textarea
          rows={3}
          maxLength={MAX_OBS_NOTE}
          value={draft.note}
          placeholder={t('share.obsNotePh')}
          onChange={(e) => p.onDraft({ note: e.target.value })}
        />
      </label>

      <div className="row-actions">
        <button type="button" className="btn" aria-expanded={preview} onClick={() => setPreview((v) => !v)}>
          {preview ? t('share.hidePreview') : t('share.preview')}
        </button>
        {owned ? (
          <>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={update}>
              {busy ? t('share.saving') : t('share.update')}
            </button>
            <button type="button" className="btn" disabled={busy || empty} onClick={create}>
              {t('share.newCopy')}
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-primary" disabled={busy || empty} onClick={create}>
            {busy ? t('share.saving') : t('share.save')}
          </button>
        )}
      </div>
      {empty && <p className="muted small">{t('share.needMarks')}</p>}
      <p className="status-line small">
        <span className="status-dot" aria-hidden="true" />
        {t('mark.unverified')}
      </p>

      <div aria-live="polite">
        {message && <p className="notice notice-ok">{message}</p>}
        {error && (
          <p className="notice notice-error" role="alert">
            {error}
          </p>
        )}
      </div>

      {shareUrl && owned && (
        <div className="share-link">
          <label className="field">
            <span>{t('share.link')}</span>
            <input type="text" readOnly value={shareUrl} onFocus={(e) => e.currentTarget.select()} data-testid="share-url" />
          </label>
          <div className="row-actions">
            <CopyButton text={shareUrl} />
            <Link className="btn" to={`/o/${obsId}`}>
              {t('app.open')}
            </Link>
            {confirmDelete ? (
              <span className="confirm">
                {t('share.deleteConfirm')}{' '}
                <button type="button" className="btn btn-small btn-danger" onClick={remove}>
                  {t('app.yes')}
                </button>{' '}
                <button type="button" className="btn btn-small" onClick={() => setConfirmDelete(false)}>
                  {t('app.no')}
                </button>
              </span>
            ) : (
              <button type="button" className="btn btn-danger" disabled={busy} onClick={() => setConfirmDelete(true)}>
                {t('share.delete')}
              </button>
            )}
          </div>
          <p className="muted small">{t('share.tokenNote')}</p>
        </div>
      )}

      {preview && (
        <ObservationCard sequence={sequence} marks={marks} title={draft.title} note={draft.note} targetName={p.targetName} />
      )}
    </div>
  )
}

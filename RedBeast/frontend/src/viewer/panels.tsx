// Side panels and dialogs of the viewer: frame details, layers, wavelength groups, provenance, shortcuts.

import { useI18n } from '../i18n'
import { api, ApiError } from '../lib/api'
import { describeApiError } from '../lib/errors'
import { fmtDateUTC, fmtDecDms, fmtNum, fmtPct, fmtRaHms, fmtSignedDeg, shortHash } from '../lib/format'
import type { Candidate, CandidatesResult, Frame, Layers, Overlay, Sequence } from '../lib/types'
import { Caveats, CopyButton, Dialog, ErrorBox, ExtLink, useAsync, type Async } from '../ui/common'

// ------------------------------------------------------------------ frame details
export function InfoPanel({
  sequence,
  frame,
  derived,
  onProvenance,
}: {
  sequence: Sequence
  frame: Frame
  derived: boolean
  onProvenance: () => void
}) {
  const { t } = useI18n()
  const { meta } = sequence
  const q = frame.quality
  const centreFlags = Object.entries(q?.target?.flags ?? {})
  const sign = frame.dlam_over_bw >= 0 ? '+' : '−'

  return (
    <section className="panel-body" aria-label={t('info.title')}>
      {derived && <p className="notice notice-info">{t('info.derived')}</p>}
      <dl className="kv">
        <dt>{t('info.date')}</dt>
        <dd className="mono strong">{fmtDateUTC(frame.date_avg, true)}</dd>
        <dt>{t('info.mjd')}</dt>
        <dd className="mono">{frame.mjd_avg.toFixed(5)}</dd>
        <dt>{t('info.wavelength')}</dt>
        <dd className="mono">
          {frame.lam_um.toFixed(4)} µm ± {(frame.bw_um / 2).toFixed(4)} µm
          <br />
          <span className="muted">
            {t('info.bandwidth')} {frame.bw_um.toFixed(4)} µm
          </span>
        </dd>
        <dt>{t('info.offset')}</dt>
        <dd className="mono">
          {t('info.offsetValue', {
            v: `${sign}${Math.abs(frame.dlam_over_bw).toFixed(3)}`,
            ref: meta.wavelength.lam_ref_um.toFixed(4),
          })}
        </dd>
        <dt>{t('info.detector')}</dt>
        <dd className="mono">{frame.detector}</dd>
        <dt>{t('info.obsId')}</dt>
        <dd className="mono">{frame.obs_id}</dd>
        <dt>{t('info.release')}</dt>
        <dd className="mono">{frame.release}</dd>
        <dt>{t('info.l2')}</dt>
        <dd className="mono">{frame.l2_tag}</dd>
        <dt>{t('info.pipeline')}</dt>
        <dd className="mono">{frame.pipeline_version}</dd>
        {frame.exposure_s !== undefined && (
          <>
            <dt>{t('info.exposure')}</dt>
            <dd className="mono">{t('info.seconds', { s: frame.exposure_s.toFixed(1) })}</dd>
          </>
        )}
        <dt>{t('info.quality')}</dt>
        <dd>
          <ul className="plain mono">
            <li>
              {fmtPct(frame.invalid_frac)} {t('info.invalid')}
            </li>
            <li>
              {fmtPct(frame.suspect_frac)} {t('info.suspect')}
            </li>
            <li>
              {fmtPct(frame.comparable_frac)} {t('info.comparable')}
            </li>
          </ul>
          {q?.target?.saturated && <p className="flag-warn">{t('info.saturated')}</p>}
        </dd>
        <dt>{t('info.centreFlags')}</dt>
        <dd className="mono">{centreFlags.length ? centreFlags.map(([k, n]) => `${k} (${n})`).join(', ') : t('app.none')}</dd>
        {(q?.l1_dqa || q?.l2_dqa) && (
          <>
            <dt>{t('info.dqa')}</dt>
            <dd className="mono">
              L1 {q.l1_dqa ?? '—'} · L2 {q.l2_dqa ?? '—'}
            </dd>
          </>
        )}
        <dt>{t('info.background')}</dt>
        <dd className="mono">
          {fmtNum(frame.background?.value_mjy_sr, 4)} ± {fmtNum(frame.background?.sigma_mjy_sr, 4)} MJy/sr
        </dd>
        {typeof frame.psf_fwhm_arcsec === 'number' && (
          <>
            <dt>{t('info.psf')}</dt>
            <dd className="mono">{frame.psf_fwhm_arcsec.toFixed(2)}″ FWHM</dd>
          </>
        )}
        <dt>{t('info.source')}</dt>
        <dd>
          <ExtLink href={frame.archive_file_url}>{t('info.archiveFile')}</ExtLink>
          <br />
          <ExtLink href={frame.source_url}>{t('info.cutout')}</ExtLink>
        </dd>
        <dt>{t('info.sha')}</dt>
        <dd>
          <code className="mono" title={frame.raw_sha256}>
            {shortHash(frame.raw_sha256, 16)}
          </code>{' '}
          <CopyButton text={frame.raw_sha256} label={t('info.copySha')} compact />
        </dd>
        <dt>{t('info.centre')}</dt>
        <dd className="mono">
          {fmtRaHms(meta.center.ra_deg)} {fmtDecDms(meta.center.dec_deg)}
          <br />
          {meta.center.ra_deg.toFixed(5)}° {fmtSignedDeg(meta.center.dec_deg)}
        </dd>
        <dt>{t('info.pixel')}</dt>
        <dd className="mono">
          {meta.grid.pixscale_arcsec}″ · {meta.grid.nx}×{meta.grid.ny}
        </dd>
      </dl>
      <button type="button" className="btn" onClick={onProvenance}>
        {t('info.provenance')}
      </button>
    </section>
  )
}

// ------------------------------------------------------------------ layers
function LayerState({ state }: { state: Async<unknown> }) {
  const { t, lang } = useI18n()
  if (state.status === 'loading') return <span className="muted small"> · {t('layer.loading')}</span>
  if (state.status === 'error')
    return (
      <span className="flag-warn small">
        {' '}
        · {t('layer.failed')}: {describeApiError(lang, state.error.code, state.error.reason)}
      </span>
    )
  return null
}

function CatalogNote({ kind, data }: { kind: 'gaia' | 'allwise'; data: Overlay }) {
  const { t, lang } = useI18n()
  return (
    <p className="layer-note">
      <span className="tag tag-cyan">{t('layer.catalogKind')}</span>{' '}
      {t('layer.catalogInfo', { band: data.band, epoch: data.catalog_epoch.toFixed(1), n: data.n })}
      <br />
      {/* the payload note is Turkish; English uses the bundled equivalent */}
      {lang === 'tr' ? data.resolution_note : t(kind === 'gaia' ? 'layer.res.gaia' : 'layer.res.allwise')}
      {data.propagation === 'proper_motion_only' && (
        <>
          <br />
          {t('layer.shownEpoch', { epoch: data.shown_epoch.toFixed(2) })} {t('layer.perFrame')}
        </>
      )}
    </p>
  )
}

export function LayersPanel({
  layers,
  onToggle,
  gaia,
  allwise,
  candidates,
  hasPrediction,
  canCompare,
  stretch,
  readOnly,
  onShowCandidate,
  onAdoptCandidate,
}: {
  layers: Layers
  onToggle: (key: keyof Layers) => void
  gaia: Async<Overlay>
  allwise: Async<Overlay>
  candidates: Async<CandidatesResult>
  hasPrediction: boolean
  canCompare: boolean
  stretch: string
  readOnly: boolean
  onShowCandidate: (c: Candidate) => void
  onAdoptCandidate: (c: Candidate) => void
}) {
  const { t, tc } = useI18n()
  const row = (key: keyof Layers, label: string, disabled = false) => (
    <label className={`check${disabled ? ' check-disabled' : ''}`}>
      <input type="checkbox" checked={layers[key]} disabled={disabled} onChange={() => onToggle(key)} />
      <span>{label}</span>
    </label>
  )

  return (
    <section className="panel-body" aria-label={t('layer.title')}>
      <ul className="layers">
        <li>
          {row('mask', t('layer.mask'))}
          {layers.mask && (
            <p className="layer-note">
              <span className="swatch swatch-suspect" aria-hidden="true" /> {t('layer.maskLegendSuspect')}
              <br />
              <span className="swatch swatch-incomp" aria-hidden="true" /> {t('layer.maskLegendIncomp')}
            </p>
          )}
        </li>
        <li>
          {row('gaia', t('layer.gaia'))}
          <LayerState state={gaia} />
          {layers.gaia && gaia.status === 'ready' && <CatalogNote kind="gaia" data={gaia.data} />}
        </li>
        <li>
          {row('allwise', t('layer.allwise'))}
          <LayerState state={allwise} />
          {layers.allwise && allwise.status === 'ready' && <CatalogNote kind="allwise" data={allwise.data} />}
        </li>
        {hasPrediction && (
          <li>
            {row('predicted', t('layer.predicted'))}
            {layers.predicted && <p className="layer-note">{t('layer.predictedNote')}</p>}
          </li>
        )}
        <li>
          {row('candidates', t('layer.candidates'))}
          <LayerState state={candidates} />
          <p className="layer-note">{t('layer.candidatesNote')}</p>
        </li>
        <li>{row('marks', t('layer.marks'))}</li>
      </ul>

      {layers.candidates && (
        <div className="cands">
          <h4>{t('cand.title')}</h4>
          <p className="notice notice-info">{t('layer.candidatesNote')}</p>
          {!canCompare && <p className="muted">{t('cand.needPair')}</p>}
          {candidates.status === 'ready' && (
            <>
              {candidates.data.candidates.length === 0 ? (
                <p className="muted">{t('cand.empty')}</p>
              ) : (
                <ol className="cand-list">
                  {candidates.data.candidates.map((c, i) => (
                    <li key={i}>
                      <div>
                        <strong>
                          {i + 1}. {tc('cls', c.classification)}
                        </strong>
                        <span className="muted small">
                          {' '}
                          · {t('cand.snr', { v: c.snr.toFixed(1) })}
                          {c.frac_change !== null ? ` · ${t('cand.frac', { v: Math.round(c.frac_change * 100) })}` : ''}
                          {c.shift_px !== undefined ? ` · ${t('cand.shift', { v: c.shift_px.toFixed(1) })}` : ''}
                        </span>
                        <br />
                        <span className="muted small">{tc('expl', c.explanation)}</span>
                      </div>
                      <div className="row-actions">
                        <button type="button" className="btn btn-small" onClick={() => onShowCandidate(c)} aria-label={`${t('cand.show')}: ${t('cand.item', { i: i + 1 })}`}>
                          {t('cand.show')}
                        </button>
                        {!readOnly && (
                          <button type="button" className="btn btn-small" onClick={() => onAdoptCandidate(c)} aria-label={`${t('cand.adopt')}: ${t('cand.item', { i: i + 1 })}`}>
                            {t('cand.adopt')}
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
              <p className="muted small">
                {t('cand.stats', { raw: candidates.data.n_raw, dropped: candidates.data.n_dropped_low_fraction })}
              </p>
              <Caveats codes={candidates.data.caveats} />
            </>
          )}
        </div>
      )}

      <h4>{t('layer.legend')}</h4>
      <ul className="legend">
        <li>
          <span className="swatch nodata" aria-hidden="true" /> {t('layer.noMeasurement')}
        </li>
        <li>
          <span className="swatch swatch-ramp" aria-hidden="true" /> {t('layer.legendScale', { stretch })}
        </li>
      </ul>
    </section>
  )
}

// ------------------------------------------------------------------ wavelength groups
export function WavePanel({ sequence, onRerun }: { sequence: Sequence; onRerun: (lamUm: number) => void }) {
  const { t, tc } = useI18n()
  const w = sequence.meta.wavelength
  const groups = w.groups ?? []
  const isCurrent = (lam: number) => Math.abs(lam - w.lam_ref_um) < 1e-4

  return (
    <section className="panel-body" aria-label={t('wave.title')}>
      <p className="mono">
        {t('wave.current', { lam: w.lam_ref_um.toFixed(4), tol: w.tol })}
        <span className="muted"> · {tc('wave.mode', w.mode)}</span>
      </p>
      <h4>{t('wave.selection')}</h4>
      <p className="muted small">{t('wave.selectionNote')}</p>
      {groups.length === 0 ? (
        <p className="muted">{t('wave.none')}</p>
      ) : (
        <div className="table-scroll">
          <table className="wave-table">
            <thead>
              <tr>
                <th scope="col">{t('wave.col.lam')}</th>
                <th scope="col">{t('wave.col.frames')}</th>
                <th scope="col">{t('wave.col.visits')}</th>
                <th scope="col">{t('wave.col.span')}</th>
                <th scope="col">
                  <span className="sr-only">{t('wave.open')}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <tr key={g.lam_ref_um} className={isCurrent(g.lam_ref_um) ? 'row-current' : undefined}>
                  <td className="mono">{g.lam_ref_um.toFixed(3)}</td>
                  <td className="mono">{g.n_frames}</td>
                  <td className="mono">{g.n_visits}</td>
                  <td className="mono">{g.span_days.toFixed(0)}</td>
                  <td>
                    {isCurrent(g.lam_ref_um) ? (
                      <span className="tag">{t('wave.thisOne')}</span>
                    ) : (
                      <button
                        type="button"
                        className="btn btn-small"
                        onClick={() => onRerun(g.lam_ref_um)}
                        aria-label={`${t('wave.open')}: ${g.lam_ref_um.toFixed(3)} µm`}
                      >
                        {t('wave.open')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

// ------------------------------------------------------------------ provenance dialog
export function ProvenanceDialog({ sequence, onClose }: { sequence: Sequence; onClose: () => void }) {
  const { t, lang } = useI18n()
  const prov = useAsync(`prov:${sequence.id}`, (signal) => api.provenance(sequence.id, signal))
  const align = prov.data?.alignment ?? sequence.meta.alignment
  const sel = prov.data?.selection ?? sequence.meta.selection
  const arch = prov.data?.archive ?? sequence.meta.archive

  return (
    <Dialog title={t('prov.title')} onClose={onClose} wide>
      {prov.status === 'loading' && <p className="muted">{t('prov.loading')}</p>}
      {prov.status === 'error' && (
        <ErrorBox message={describeApiError(lang, (prov.error as ApiError).code, prov.error.reason)} onRetry={prov.reload} />
      )}

      <h3>{t('prov.alignment')}</h3>
      {align && align.status === 'ok' ? (
        <>
          <p className="mono">
            {t('prov.alignOk', {
              rms: fmtNum(align.rms_arcsec, 2),
              n: align.n_measurements ?? 0,
              pix: sequence.meta.grid.pixscale_arcsec,
            })}
          </p>
          <dl className="kv">
            <dt>{t('prov.alignCatalog')}</dt>
            <dd>{align.catalog}</dd>
            <dt>{t('prov.alignMethod')}</dt>
            <dd>{align.method}</dd>
          </dl>
        </>
      ) : (
        <p className="flag-warn">
          {t('prov.alignUnavailable')} {align?.reason ?? ''}
        </p>
      )}

      <h3>{t('prov.archive')}</h3>
      <dl className="kv">
        <dt>{t('prov.service')}</dt>
        <dd>
          {arch?.service} {arch?.tap_url && <ExtLink href={arch.tap_url}>{arch.tap_url}</ExtLink>}
          {typeof arch?.n_rows === 'number' && <span className="muted"> · {t('prov.rows', { n: arch.n_rows })}</span>}
        </dd>
        <dt>{t('prov.adql')}</dt>
        <dd>
          <pre className="code">{arch?.adql}</pre>
          {arch?.adql && <CopyButton text={arch.adql} compact />}
        </dd>
        <dt>{t('prov.selection')}</dt>
        <dd className="mono">
          {t('prov.selectionLine', {
            obs: sel?.n_observations ?? '—',
            cand: sel?.n_candidates ?? '—',
            sel: sel?.n_selected ?? '—',
            prep: sel?.n_prepared ?? '—',
          })}
        </dd>
        {prov.data?.data_fingerprint && (
          <>
            <dt>{t('prov.fingerprint')}</dt>
            <dd className="mono">{prov.data.data_fingerprint}</dd>
          </>
        )}
      </dl>

      <h3>{t('prov.frames')}</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">{t('prov.col.date')}</th>
              <th scope="col">{t('prov.col.obs')}</th>
              <th scope="col">{t('prov.col.det')}</th>
              <th scope="col">{t('prov.col.lam')}</th>
              <th scope="col">{t('prov.col.sha')}</th>
              <th scope="col">{t('prov.col.file')}</th>
            </tr>
          </thead>
          <tbody>
            {(prov.data?.frames ?? sequence.frames).map((f) => (
              <tr key={f.index}>
                <td>{f.index + 1}</td>
                <td className="mono">{fmtDateUTC(f.date_avg)}</td>
                <td className="mono">{f.obs_id}</td>
                <td className="mono">{f.detector}</td>
                <td className="mono">{f.lam_um.toFixed(4)}</td>
                <td className="mono" title={f.raw_sha256}>
                  {shortHash(f.raw_sha256, 12)}
                </td>
                <td>
                  <ExtLink href={f.archive_file_url}>FITS</ExtLink>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>{t('prov.citation')}</h3>
      <p>{prov.data?.citation ?? t('footer.credit')}</p>
    </Dialog>
  )
}

// ------------------------------------------------------------------ shortcuts dialog
export function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  const { t } = useI18n()
  const rows: [string, string][] = [
    ['Space', t('keys.space')],
    ['←  →', t('keys.arrows')],
    ['Home  End', t('keys.homeEnd')],
    ['Shift + ← → ↑ ↓', t('keys.shiftArrows')],
    ['+  −', t('keys.zoom')],
    ['0', t('keys.reset')],
    ['B', t('keys.blink')],
    ['M', t('keys.mark')],
    ['Enter', t('keys.enter')],
    ['Delete', t('keys.delete')],
    ['Esc', t('keys.esc')],
    ['?', t('keys.help')],
  ]
  return (
    <Dialog title={t('keys.title')} onClose={onClose}>
      <table className="keys">
        <tbody>
          {rows.map(([k, d]) => (
            <tr key={k}>
              <th scope="row">
                <kbd>{k}</kbd>
              </th>
              <td>{d}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">{t('keys.note')}</p>
      <p className="muted small">{t('pane.help')}</p>
    </Dialog>
  )
}

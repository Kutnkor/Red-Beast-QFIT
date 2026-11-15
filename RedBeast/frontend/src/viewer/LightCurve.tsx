// Light curve as inline SVG: flux (mJy) against the real observation date, with error bars.
// Invalid points are drawn in a separate "no measurement" lane — never at zero.

import { useI18n } from '../i18n'
import { fmtDateUTC, fmtNum } from '../lib/format'
import { framePositions, monthTicks } from '../lib/timeline'
import type { LightCurve, LightPoint } from '../lib/types'
import { Caveats } from '../ui/common'

const W = 340
const H = 210
const L = 46
const R = 12
const T = 12
const PLOT_B = 148 // bottom of the flux area
const LANE_Y = 168 // "no measurement" lane
const AXIS_Y = 180

export type PointState = 'ok' | 'offtol' | 'unreliable' | 'none'

export function pointState(p: LightPoint): PointState {
  if (!p.valid || p.flux_mjy === null || !Number.isFinite(p.flux_mjy)) return 'none'
  if (p.reliable === false || p.saturated) return 'unreliable'
  if (p.quantitative_ok === false) return 'offtol'
  return 'ok'
}

function niceTicks(lo: number, hi: number, n = 4): number[] {
  const span = hi - lo
  if (!(span > 0)) return [lo]
  const raw = span / n
  const pow = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? raw
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Number(v.toPrecision(12)))
  return out
}

export function LightCurveChart({
  curve,
  current,
  onSelect,
}: {
  curve: LightCurve
  current: number
  onSelect?: (frameIndex: number) => void
}) {
  const { t, tc } = useI18n()
  const pts = curve.points
  const xs = framePositions(pts.map((p) => p.mjd)).map((f) => L + f * (W - L - R))
  const states = pts.map(pointState)
  const measured = pts.filter((_, i) => states[i] !== 'none')

  let lo = 0
  let hi = 1
  if (measured.length > 0) {
    lo = Math.min(...measured.map((p) => (p.flux_mjy as number) - (p.err_mjy ?? 0)))
    hi = Math.max(...measured.map((p) => (p.flux_mjy as number) + (p.err_mjy ?? 0)))
    const pad = (hi - lo || Math.abs(hi) || 1) * 0.12
    lo -= pad
    hi += pad
  }
  const y = (v: number) => PLOT_B - ((v - lo) / (hi - lo)) * (PLOT_B - T)
  const ticks = measured.length > 0 ? niceTicks(lo, hi) : []
  const digits = hi - lo < 1 ? 3 : hi - lo < 20 ? 2 : 1
  const months = pts.length > 1 ? monthTicks(pts[0].mjd, pts[pts.length - 1].mjd, 5) : []
  const curX = xs[pts.findIndex((p) => p.index === current)]

  const stateLabel = (p: LightPoint, s: PointState) =>
    s === 'none'
      ? `${t('lc.noMeasurement')}${p.reason ? ` (${tc('lcReason', p.reason)})` : ''}`
      : s === 'unreliable'
        ? t('lc.unreliable')
        : s === 'offtol'
          ? t('lc.offTol')
          : t('lc.ok')

  return (
    <div className="lc">
      <svg
        className="lc-svg"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={t('lc.chartLabel', { n: pts.length, valid: measured.length })}
      >
        <rect className="lc-plot" x={L} y={T} width={W - L - R} height={PLOT_B - T} />
        {ticks.map((v) => (
          <g key={v}>
            <line className="lc-grid" x1={L} x2={W - R} y1={y(v)} y2={y(v)} />
            <text className="lc-tick" x={L - 5} y={y(v) + 3.5} textAnchor="end">
              {v.toFixed(digits)}
            </text>
          </g>
        ))}
        {lo < 0 && hi > 0 && <line className="lc-zero" x1={L} x2={W - R} y1={y(0)} y2={y(0)} />}
        <text className="lc-label" transform={`translate(11 ${(T + PLOT_B) / 2}) rotate(-90)`} textAnchor="middle">
          {t('lc.axisY')}
        </text>

        <line className="lc-lane" x1={L} x2={W - R} y1={LANE_Y} y2={LANE_Y} />
        <text className="lc-tick" x={L - 5} y={LANE_Y + 3.5} textAnchor="end">
          ∅
        </text>

        <line className="lc-axis" x1={L} x2={W - R} y1={AXIS_Y} y2={AXIS_Y} />
        {months.map((m) => {
          const x = L + m.frac * (W - L - R)
          return (
            <g key={m.label}>
              <line className="lc-axis" x1={x} x2={x} y1={AXIS_Y} y2={AXIS_Y + 4} />
              <text className="lc-tick" x={x} y={AXIS_Y + 15} textAnchor="middle">
                {m.label}
              </text>
            </g>
          )
        })}
        <text className="lc-label" x={(L + W - R) / 2} y={H - 3} textAnchor="middle">
          {t('lc.axisX')}
        </text>

        {curX !== undefined && <line className="lc-current" x1={curX} x2={curX} y1={T} y2={AXIS_Y} />}

        {pts.map((p, i) => {
          const s = states[i]
          const x = xs[i]
          const title = `${fmtDateUTC(p.date)} · ${s === 'none' ? '' : `${fmtNum(p.flux_mjy, 3)} ± ${fmtNum(p.err_mjy, 3)} mJy · `}${stateLabel(p, s)}`
          if (s === 'none') {
            return (
              <g key={p.index} className="lc-pt lc-none" data-state="none" onClick={() => onSelect?.(p.index)}>
                <title>{title}</title>
                <rect className="lc-hit" x={x - 8} y={LANE_Y - 8} width={16} height={16} />
                <path d={`M${x - 4} ${LANE_Y - 4}l8 8M${x + 4} ${LANE_Y - 4}l-8 8`} />
              </g>
            )
          }
          const f = p.flux_mjy as number
          const e = p.err_mjy ?? 0
          const cy = y(f)
          return (
            <g key={p.index} className={`lc-pt lc-${s}`} data-state={s} onClick={() => onSelect?.(p.index)}>
              <title>{title}</title>
              <rect className="lc-hit" x={x - 8} y={cy - 8} width={16} height={16} />
              {e > 0 && <path className="lc-err" d={`M${x} ${y(f - e)}V${y(f + e)}M${x - 3} ${y(f - e)}h6M${x - 3} ${y(f + e)}h6`} />}
              {s === 'unreliable' ? (
                <path className="lc-mark" d={`M${x} ${cy - 5}L${x + 5} ${cy}L${x} ${cy + 5}L${x - 5} ${cy}Z`} />
              ) : (
                <circle className="lc-mark" cx={x} cy={cy} r={3.6} />
              )}
            </g>
          )
        })}
      </svg>

      <ul className="lc-legend">
        <li>
          <svg width="14" height="14" aria-hidden="true">
            <circle className="lc-pt lc-ok lc-mark" cx="7" cy="7" r="3.6" />
          </svg>
          {t('lc.ok')}
        </li>
        <li>
          <svg width="14" height="14" aria-hidden="true" className="lc-pt lc-offtol">
            <circle className="lc-mark" cx="7" cy="7" r="3.6" />
          </svg>
          {t('lc.offTol')}
        </li>
        <li>
          <svg width="14" height="14" aria-hidden="true" className="lc-pt lc-unreliable">
            <path className="lc-mark" d="M7 2L12 7L7 12L2 7Z" />
          </svg>
          {t('lc.unreliable')}
        </li>
        <li>
          <svg width="14" height="14" aria-hidden="true" className="lc-pt lc-none">
            <path d="M3 3l8 8M11 3l-8 8" />
          </svg>
          {t('lc.noMeasurement')}
        </li>
      </ul>

      {measured.length === 0 && <p className="notice notice-warn">{t('lc.allInvalid')}</p>}
      <p className="muted small">{tc('lc.position', curve.position_mode)}</p>
      {curve.lam_ref_um !== null && <p className="muted small">{t('lc.oneGroup', { lam: curve.lam_ref_um.toFixed(3) })}</p>}

      <details className="lc-table">
        <summary>{t('lc.table')}</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">{t('lc.col.date')}</th>
              <th scope="col">{t('lc.col.flux')}</th>
              <th scope="col">{t('lc.col.state')}</th>
            </tr>
          </thead>
          <tbody>
            {pts.map((p, i) => (
              <tr key={p.index}>
                <td>{p.index + 1}</td>
                <td className="mono">{fmtDateUTC(p.date)}</td>
                <td className="mono">
                  {states[i] === 'none' ? t('lc.noMeasurement') : `${fmtNum(p.flux_mjy, 3)} ± ${fmtNum(p.err_mjy, 3)}`}
                </td>
                <td>{stateLabel(p, states[i])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
      <Caveats codes={curve.caveats} />
    </div>
  )
}

// Number, date and coordinate formatting. Dates are always shown in UTC.

const pad = (n: number, w = 2) => String(n).padStart(w, '0')

/** "2026-08-18T20:49:36Z" -> "2026-08-18 20:49 UTC" */
export function fmtDateUTC(iso: string | null | undefined, withSeconds = false): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  const base = `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`
  return withSeconds ? `${base}:${pad(d.getUTCSeconds())} UTC` : `${base} UTC`
}

/** "2026-08-18T20:49:36Z" -> "2026-08-18" */
export function fmtDay(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`
}

export const MJD_UNIX_EPOCH = 40587

export function mjdToDate(mjd: number): Date {
  return new Date((mjd - MJD_UNIX_EPOCH) * 86400000)
}

export function mjdToIso(mjd: number): string {
  return mjdToDate(mjd).toISOString().replace(/\.\d+Z$/, 'Z')
}

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}

export function fmtPct(frac: number | null | undefined, digits = 1): string {
  if (frac === null || frac === undefined || !Number.isFinite(frac)) return '—'
  return `${(frac * 100).toFixed(digits)}%`
}

function sexagesimal(value: number, secDigits: number): { a: number; m: number; s: string } {
  // work in integer units of the last displayed digit so we never print 60.00
  const unit = 10 ** secDigits
  const total = Math.round(Math.abs(value) * 3600 * unit)
  const sInt = total % (60 * unit)
  const mTotal = (total - sInt) / (60 * unit)
  const m = mTotal % 60
  const a = (mTotal - m) / 60
  const sec = sInt / unit
  const s = secDigits > 0 ? sec.toFixed(secDigits).padStart(3 + secDigits, '0') : pad(sec)
  return { a, m, s }
}

/** RA in degrees -> "17h57m47.10s" */
export function fmtRaHms(raDeg: number, secDigits = 2): string {
  const r = ((raDeg % 360) + 360) % 360
  const { a, m, s } = sexagesimal(r / 15, secDigits)
  return `${pad(a % 24)}h${pad(m)}m${s}s`
}

/** Dec in degrees -> "+04°46′05.5″" */
export function fmtDecDms(decDeg: number, secDigits = 1): string {
  const { a, m, s } = sexagesimal(decDeg, secDigits)
  const sign = decDeg < 0 ? '−' : '+'
  return `${sign}${pad(a)}°${pad(m)}′${s}″`
}

export function fmtDeg(v: number, digits = 5): string {
  return `${v.toFixed(digits)}°`
}

export function fmtSignedDeg(v: number, digits = 5): string {
  return `${v < 0 ? '−' : '+'}${Math.abs(v).toFixed(digits)}°`
}

export function fmtLam(um: number | null | undefined, digits = 3): string {
  return um === null || um === undefined ? '—' : `${um.toFixed(digits)} µm`
}

export function shortHash(hex: string, n = 12): string {
  return hex.length > n ? `${hex.slice(0, n)}…` : hex
}

/** Replace `{name}` placeholders. */
export function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m))
}

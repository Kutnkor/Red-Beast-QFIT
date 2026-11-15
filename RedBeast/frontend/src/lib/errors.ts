// Turn API / job error codes into user-facing text.

import { translate, translateCode } from '../i18n'
import { ApiError } from './api'
import type { Lang } from './types'

/** `422 bad_coordinates` carries a `reason`; the reason is the useful part. */
export function describeCoordinateReason(lang: Lang, reason: string | undefined): string {
  return translateCode(lang, 'coord', reason) ?? translate(lang, 'err.bad_coordinates')
}

export function describeApiError(lang: Lang, code: string, reason?: string): string {
  if (code === 'bad_coordinates') return describeCoordinateReason(lang, reason)
  return translateCode(lang, 'err', code) ?? translate(lang, 'err.unknown', { code })
}

export function describeError(lang: Lang, err: unknown): string {
  if (err instanceof ApiError) return describeApiError(lang, err.code, err.reason)
  return translate(lang, 'err.unknown', { code: 'client' })
}

/** `job.error` of a failed job. */
export function describeJobError(lang: Lang, code: string | null | undefined): string {
  return translateCode(lang, 'jobErr', code) ?? translate(lang, 'err.unknown', { code: code || 'unknown' })
}

/** `job.detail.reason` of an `insufficient_data` job. */
export function describeInsufficient(lang: Lang, reason: string | null | undefined): string {
  return translateCode(lang, 'insuf', reason) ?? translate(lang, 'insuf.unknown')
}

// localStorage helpers. Storage can be unavailable (private mode, embedded frames): every call is guarded.

import type { Mark } from './types'

export function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key)
    if (raw === null) return fallback
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage full or blocked: the app keeps working without persistence */
  }
}

export function removeKey(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    /* ignore */
  }
}

export function readString(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeString(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* ignore */
  }
}

export interface Draft {
  marks: Mark[]
  title: string
  note: string
  /** observation this draft was last saved as (only useful together with its edit token) */
  observationId?: string | null
}

export const emptyDraft: Draft = { marks: [], title: '', note: '', observationId: null }

const draftKey = (sequenceId: string) => `bs.draft.${sequenceId}`
const tokenKey = (observationId: string) => `bs.token.${observationId}`

export function loadDraft(sequenceId: string): Draft {
  const d = readJson<Partial<Draft> | null>(draftKey(sequenceId), null)
  if (!d || typeof d !== 'object') return { ...emptyDraft }
  return {
    marks: Array.isArray(d.marks) ? d.marks : [],
    title: typeof d.title === 'string' ? d.title : '',
    note: typeof d.note === 'string' ? d.note : '',
    observationId: typeof d.observationId === 'string' ? d.observationId : null,
  }
}

export function saveDraft(sequenceId: string, draft: Draft): void {
  writeJson(draftKey(sequenceId), draft)
}

export function loadToken(observationId: string): string | null {
  return readString(tokenKey(observationId))
}

export function saveToken(observationId: string, token: string): void {
  writeString(tokenKey(observationId), token)
}

export function dropToken(observationId: string): void {
  removeKey(tokenKey(observationId))
}

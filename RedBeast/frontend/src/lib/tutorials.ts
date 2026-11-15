// Tutorial progress (guided steps ticked by real viewer events, quiz answers). Stored in localStorage.

import { readJson, writeJson } from './storage'
import type { Tutorial, TutorialStep } from './types'

export type TutorialEvent = TutorialStep['event']

export interface TutorialProgress {
  done: string[]
  answer?: string
}

export type ProgressMap = Record<string, TutorialProgress>

const KEY = 'bs.tutorials'

export function loadProgress(): ProgressMap {
  const raw = readJson<ProgressMap | null>(KEY, null)
  return raw && typeof raw === 'object' ? raw : {}
}

export function saveProgress(map: ProgressMap): void {
  writeJson(KEY, map)
}

export function progressOf(map: ProgressMap, id: string): TutorialProgress {
  const p = map[id]
  return { done: Array.isArray(p?.done) ? p.done : [], answer: typeof p?.answer === 'string' ? p.answer : undefined }
}

/** Tick the first not-yet-done step that waits for this event. Returns the same object if nothing changed. */
export function applyEvent(tutorial: Tutorial, progress: TutorialProgress, event: TutorialEvent): TutorialProgress {
  if (tutorial.kind !== 'guided' || !tutorial.steps) return progress
  const step = tutorial.steps.find((s) => s.event === event && !progress.done.includes(s.id))
  if (!step) return progress
  return { ...progress, done: [...progress.done, step.id] }
}

export function answerQuiz(tutorial: Tutorial, progress: TutorialProgress, optionId: string): TutorialProgress {
  if (tutorial.kind !== 'quiz' || progress.answer) return progress
  if (!tutorial.options?.some((o) => o.id === optionId)) return progress
  return { ...progress, answer: optionId }
}

export function isComplete(tutorial: Tutorial, progress: TutorialProgress): boolean {
  if (tutorial.kind === 'quiz') return Boolean(progress.answer)
  const steps = tutorial.steps ?? []
  return steps.length > 0 && steps.every((s) => progress.done.includes(s.id))
}

export function isCorrect(tutorial: Tutorial, progress: TutorialProgress): boolean | null {
  if (tutorial.kind !== 'quiz' || !progress.answer || !tutorial.answer_id) return null
  return progress.answer === tutorial.answer_id
}

/** Defensive parse: the endpoint may return an empty list or partially filled entries. */
export function parseTutorials(input: unknown): Tutorial[] {
  if (typeof input !== 'object' || input === null) return []
  const list = (input as { tutorials?: unknown }).tutorials
  if (!Array.isArray(list)) return []
  return list.filter((t): t is Tutorial => {
    if (typeof t !== 'object' || t === null) return false
    const r = t as Record<string, unknown>
    return typeof r.id === 'string' && typeof r.title === 'object' && r.title !== null && (r.kind === 'guided' || r.kind === 'quiz')
  })
}

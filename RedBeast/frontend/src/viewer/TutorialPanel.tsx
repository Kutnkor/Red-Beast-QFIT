// Tutorial panel: guided steps are ticked by real viewer events; quizzes reveal the explanation after a choice.

import { useI18n } from '../i18n'
import { isComplete, isCorrect, type TutorialProgress } from '../lib/tutorials'
import type { Tutorial } from '../lib/types'
import { ExtLink } from '../ui/common'

export function SyntheticBadge() {
  const { t } = useI18n()
  return <span className="tag tag-synthetic">{t('tut.synthetic')}</span>
}

export function TutorialPanel({
  tutorial,
  progress,
  onAnswer,
  onReset,
  onClose,
}: {
  tutorial: Tutorial
  progress: TutorialProgress
  onAnswer: (optionId: string) => void
  onReset: () => void
  onClose: () => void
}) {
  const { t, pick } = useI18n()
  const done = isComplete(tutorial, progress)
  const correct = isCorrect(tutorial, progress)
  const answered = Boolean(progress.answer)
  const right = tutorial.options?.find((o) => o.id === tutorial.answer_id)

  return (
    <section className="panel-body tutorial" aria-label={t('tut.title')}>
      <header>
        <p className="muted small">
          {t(tutorial.kind === 'quiz' ? 'tut.kind.quiz' : 'tut.kind.guided')} {tutorial.synthetic && <SyntheticBadge />}
        </p>
        <h3>{pick(tutorial.title)}</h3>
        <p>{pick(tutorial.summary)}</p>
      </header>

      {tutorial.kind === 'guided' && (
        <ol className="steps">
          {(tutorial.steps ?? []).map((s) => {
            const ok = progress.done.includes(s.id)
            return (
              <li key={s.id} className={ok ? 'step step-done' : 'step'}>
                <span className="step-box" aria-hidden="true">
                  {ok ? '✓' : ''}
                </span>
                <span>
                  {pick(s.text)} <span className="sr-only">({ok ? t('tut.stepDone') : t('tut.stepTodo')})</span>
                </span>
              </li>
            )
          })}
        </ol>
      )}

      {tutorial.kind === 'quiz' && (
        <fieldset className="quiz" disabled={answered}>
          <legend>{pick(tutorial.question)}</legend>
          {(tutorial.options ?? []).map((o) => {
            const chosen = progress.answer === o.id
            const cls = ['quiz-option']
            if (answered && o.id === tutorial.answer_id) cls.push('quiz-right')
            if (answered && chosen && o.id !== tutorial.answer_id) cls.push('quiz-wrong')
            return (
              <label key={o.id} className={cls.join(' ')}>
                <input type="radio" name={`quiz-${tutorial.id}`} checked={chosen} onChange={() => onAnswer(o.id)} />
                <span>{pick(o.text)}</span>
              </label>
            )
          })}
        </fieldset>
      )}

      <div aria-live="polite">
        {tutorial.kind === 'guided' && done && <p className="notice notice-ok">{t('tut.allDone')}</p>}
        {answered && (
          <div className={correct ? 'notice notice-ok' : 'notice notice-warn'}>
            <strong>{correct ? t('tut.correct') : t('tut.wrong')}</strong>
            {correct === false && right && <p>{t('tut.answerWas', { a: pick(right.text) })}</p>}
            {tutorial.explanation && (
              <>
                <h4>{t('tut.explanation')}</h4>
                <p>{pick(tutorial.explanation)}</p>
              </>
            )}
          </div>
        )}
      </div>

      {tutorial.frames_used && tutorial.frames_used.length > 0 && (
        <>
          <h4>{t('tut.framesUsed')}</h4>
          <ul className="plain mono small">
            {tutorial.frames_used.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </>
      )}
      {tutorial.sources && tutorial.sources.length > 0 && (
        <>
          <h4>{t('tut.sources')}</h4>
          <ul className="plain small">
            {tutorial.sources.map((s) => (
              <li key={s.url}>{/^https?:\/\//.test(s.url) ? <ExtLink href={s.url}>{s.label}</ExtLink> : s.label}</li>
            ))}
          </ul>
        </>
      )}

      <div className="row-actions">
        <button type="button" className="btn btn-small" onClick={onReset}>
          {t('tut.reset')}
        </button>
        <button type="button" className="btn btn-small" onClick={onClose}>
          {t('tut.close')}
        </button>
      </div>
    </section>
  )
}

export function TutorialList({
  tutorials,
  completed,
  onStart,
}: {
  tutorials: Tutorial[]
  completed: (id: string) => boolean
  onStart: (tutorial: Tutorial) => void
}) {
  const { t, pick } = useI18n()
  return (
    <ul className="tut-list">
      {tutorials.map((tu) => (
        <li key={tu.id}>
          <div>
            <strong>{pick(tu.title)}</strong>{' '}
            <span className="muted small">
              {t(tu.kind === 'quiz' ? 'tut.kind.quiz' : 'tut.kind.guided')}
              {completed(tu.id) ? ` · ${t('tut.completed')}` : ''}
            </span>{' '}
            {tu.synthetic && <SyntheticBadge />}
            <p className="muted small">{pick(tu.summary)}</p>
          </div>
          <button type="button" className="btn btn-small" onClick={() => onStart(tu)} aria-label={`${t('tut.start')}: ${pick(tu.title)}`}>
            {completed(tu.id) ? t('tut.resume') : t('tut.start')}
          </button>
        </li>
      ))}
    </ul>
  )
}

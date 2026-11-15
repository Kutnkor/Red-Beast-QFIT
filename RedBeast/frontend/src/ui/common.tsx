/* eslint-disable react-refresh/only-export-components */
// Small shared UI pieces: icons, link, dialog, copy button, async hook.

import { useSheet } from '../v4/sheet'
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type AnchorHTMLAttributes,
  type MouseEvent,
  type ReactNode,
} from 'react'
import { useI18n } from '../i18n'
import { ApiError } from '../lib/api'
import { navigate, withSticky } from '../lib/router'

const ICONS = { play: 'play', pause: 'pause', prev: 'prev', next: 'next', plus: 'zoom-in', minus: 'zoom-out', 'zoom-in': 'zoom-in', 'zoom-out': 'zoom-out', reset: 'reset', close: 'close', copy: 'copy', mark: 'mark', help: 'keyboard', keyboard: 'keyboard', external: 'external', search: 'search', blink: 'blink', 'face-on': 'face-on', drawer: 'drawer' } as const
export type IconName = keyof typeof ICONS
export function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false" className="icon" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><use href={`#icon-${ICONS[name]}`} /></svg>
}

/** In-app link: plain left clicks use the History API, everything else behaves like a normal link. */
export function Link({ to, children, onClick, ...rest }: { to: string } & AnchorHTMLAttributes<HTMLAnchorElement>) {
  const href = withSticky(to, typeof window === 'undefined' ? '' : window.location.search)
  const handle = (e: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(e)
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    e.preventDefault()
    navigate(to)
  }
  return (
    <a href={href} onClick={handle} {...rest}>
      {children}
    </a>
  )
}

export function ExtLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="ext">
      {children}
      <Icon name="external" size={13} />
    </a>
  )
}

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'

export function Dialog({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string
  onClose: () => void
  children: ReactNode
  wide?: boolean
}) {
  const { t } = useI18n()
  const ref = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const { closing, close } = useSheet(ref, onClose)

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    ref.current?.focus()
    return () => previous?.focus?.()
  }, [])

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      close()
      return
    }
    if (e.key !== 'Tab' || !ref.current) return
    const items = Array.from(ref.current.querySelectorAll<HTMLElement>(FOCUSABLE))
    if (items.length === 0) return
    const first = items[0]
    const last = items[items.length - 1]
    if (e.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  return (
    <div className="dialog-backdrop" data-closing={closing || undefined} onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <div
        ref={ref}
        className={wide ? 'dialog dialog-wide' : 'dialog'}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        data-dialog
      >
        <header className="dialog-head">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="btn btn-icon" onClick={close} aria-label={t('app.close')}>
            <Icon name="close" />
          </button>
        </header>
        <div className="dialog-body">{children}</div>
      </div>
    </div>
  )
}

export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fall through to the legacy path */
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

export function CopyButton({ text, label, compact = false }: { text: string; label?: string; compact?: boolean }) {
  const { t } = useI18n()
  const [state, setState] = useState<'idle' | 'ok' | 'fail'>('idle')
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])
  const onClick = async () => {
    const ok = await copyText(text)
    setState(ok ? 'ok' : 'fail')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setState('idle'), 2500)
  }
  const text2 = state === 'ok' ? t('app.copied') : state === 'fail' ? t('app.copyFailed') : t('app.copy')
  return (
    <button type="button" className={compact ? 'btn btn-small' : 'btn'} onClick={onClick} aria-label={label ?? t('app.copy')}>
      <Icon name="copy" size={14} />
      <span aria-live="polite">{text2}</span>
    </button>
  )
}

export type Async<T> =
  | { status: 'idle'; data: null; error: null }
  | { status: 'loading'; data: T | null; error: null }
  | { status: 'ready'; data: T; error: null }
  | { status: 'error'; data: null; error: ApiError }

/**
 * Run `load` whenever `key` changes (null = idle). Stale responses are dropped; requests are aborted on change.
 */
export function useAsync<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>): Async<T> & { reload: () => void } {
  const [state, setState] = useState<Async<T>>({ status: 'idle', data: null, error: null })
  const [nonce, setNonce] = useState(0)
  const loadRef = useRef(load)
  loadRef.current = load

  useEffect(() => {
    if (key === null) {
      setState({ status: 'idle', data: null, error: null })
      return
    }
    const ctrl = new AbortController()
    setState((s) => ({ status: 'loading', data: s.status === 'ready' ? s.data : null, error: null }))
    loadRef
      .current(ctrl.signal)
      .then((data) => {
        if (!ctrl.signal.aborted) setState({ status: 'ready', data, error: null })
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return
        const error = err instanceof ApiError ? err : new ApiError(0, 'network_error')
        setState({ status: 'error', data: null, error })
      })
    return () => ctrl.abort()
  }, [key, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { ...state, reload }
}

export function ErrorBox({ title, message, onRetry }: { title?: string; message: string; onRetry?: () => void }) {
  const { t } = useI18n()
  return (
    <div className="notice notice-error" role="alert">
      {title && <strong>{title}</strong>}
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          {t('app.retry')}
        </button>
      )}
    </div>
  )
}

export function Caveats({ codes }: { codes: string[] }) {
  const { t, tc } = useI18n()
  if (codes.length === 0) return null
  return (
    <div className="caveats">
      <h4>{t('caveat.title')}</h4>
      <ul>
        {codes.map((c) => (
          <li key={c}>{tc('caveat', c)}</li>
        ))}
      </ul>
    </div>
  )
}

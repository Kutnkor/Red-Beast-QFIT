// Tiny History-API router: three routes, no dependency.

import { useSyncExternalStore } from 'react'

export type Route =
  | { name: 'home' }
  | { name: 'sequence'; id: string }
  | { name: 'observation'; id: string }
  | { name: 'notfound' }

const ID = /^[a-z0-9]{6,24}$/

export function matchRoute(pathname: string): Route {
  const path = pathname.replace(/\/+$/, '') || '/'
  if (path === '/') return { name: 'home' }
  const m = /^\/(s|o)\/([^/]+)$/.exec(path)
  if (m && ID.test(m[2])) return m[1] === 's' ? { name: 'sequence', id: m[2] } : { name: 'observation', id: m[2] }
  return { name: 'notfound' }
}

/** Query parameters that must survive in-app navigation. */
const STICKY = ['embed', 'ui']

export function withSticky(to: string, currentSearch: string): string {
  const cur = new URLSearchParams(currentSearch)
  const [path, query = ''] = to.split('?')
  const next = new URLSearchParams(query)
  for (const k of STICKY) {
    const v = cur.get(k)
    if (v !== null && !next.has(k)) next.set(k, v)
  }
  const qs = next.toString()
  return qs ? `${path}?${qs}` : path
}

const listeners = new Set<() => void>()

function emit() {
  listeners.forEach((l) => l())
}

function subscribe(cb: () => void) {
  listeners.add(cb)
  window.addEventListener('popstate', cb)
  return () => {
    listeners.delete(cb)
    window.removeEventListener('popstate', cb)
  }
}

const snapshot = () => window.location.pathname + window.location.search

export function navigate(to: string, opts: { replace?: boolean } = {}): void {
  const url = withSticky(to, window.location.search)
  if (url === snapshot()) return
  if (opts.replace) window.history.replaceState(null, '', url)
  else window.history.pushState(null, '', url)
  window.scrollTo?.(0, 0)
  emit()
}

export interface Location {
  route: Route
  pathname: string
  query: URLSearchParams
}

export function useLocation(): Location {
  const href = useSyncExternalStore(subscribe, snapshot, () => '/')
  const [pathname, search = ''] = href.split('?')
  return { route: matchRoute(pathname), pathname, query: new URLSearchParams(search) }
}

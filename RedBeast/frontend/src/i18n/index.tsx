/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { interpolate } from '../lib/format'
import { readString, writeString } from '../lib/storage'
import type { Bilingual, Lang } from '../lib/types'
import { en } from './en'
import { tr, type Messages, type MsgKey } from './tr'

export const MESSAGES: Record<Lang, Messages> = { tr, en }
const LANG_KEY = 'bs.lang'

export type Params = Record<string, string | number>
export type TFn = (key: MsgKey, params?: Params) => string

export function translate(lang: Lang, key: MsgKey, params?: Params): string {
  return interpolate(MESSAGES[lang][key] ?? MESSAGES.en[key] ?? key, params)
}

/** Translate a server code under a prefix (`err.<code>`); returns null when there is no such message. */
export function translateCode(lang: Lang, prefix: string, code: string | null | undefined, params?: Params): string | null {
  if (!code) return null
  const key = `${prefix}.${code}`
  if (!Object.prototype.hasOwnProperty.call(MESSAGES[lang], key)) return null
  return translate(lang, key as MsgKey, params)
}

/** Order: ?lang= → stored choice → browser language (tr → Turkish, anything else → English). */
export function detectLang(search: string, stored: string | null, navigatorLang: string | undefined): Lang {
  const q = new URLSearchParams(search).get('lang')
  if (q === 'tr' || q === 'en') return q
  if (stored === 'tr' || stored === 'en') return stored
  return (navigatorLang ?? '').toLowerCase().startsWith('tr') ? 'tr' : 'en'
}

interface I18n {
  lang: Lang
  setLang: (lang: Lang) => void
  t: TFn
  /** server code → text, falling back to the raw code so nothing is silently hidden */
  tc: (prefix: string, code: string | null | undefined, params?: Params) => string
  /** pick the right language from a `{tr,en}` object coming from the API */
  pick: (text: Partial<Bilingual> | null | undefined) => string
}

const Ctx = createContext<I18n | null>(null)

export function I18nProvider({ children, initial }: { children: ReactNode; initial?: Lang }) {
  const [lang, setLangState] = useState<Lang>(
    () => initial ?? detectLang(window.location.search, readString(LANG_KEY), window.navigator?.language),
  )

  useEffect(() => {
    document.documentElement.lang = lang
    document.title = `${MESSAGES[lang]['app.name']} — ${MESSAGES[lang]['app.slogan']}`
  }, [lang])

  useEffect(() => {
    // an explicit ?lang= is remembered so in-app navigation keeps it
    const q = new URLSearchParams(window.location.search).get('lang')
    if (q === 'tr' || q === 'en') writeString(LANG_KEY, q)
  }, [])

  const setLang = useCallback((next: Lang) => {
    writeString(LANG_KEY, next)
    setLangState(next)
  }, [])

  const value = useMemo<I18n>(
    () => ({
      lang,
      setLang,
      t: (key, params) => translate(lang, key, params),
      tc: (prefix, code, params) => translateCode(lang, prefix, code, params) ?? String(code ?? ''),
      pick: (text) => (text ? (text[lang] ?? text.en ?? text.tr ?? '') : ''),
    }),
    [lang, setLang],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useI18n(): I18n {
  const v = useContext(Ctx)
  if (!v) throw new Error('useI18n outside I18nProvider')
  return v
}

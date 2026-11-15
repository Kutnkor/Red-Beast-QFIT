// Name matching for the robin: finds the star a visitor means even when it is misspelt ("bernard"),
// carries a Turkish case ending ("Barnard'a", "Proximaya") or is only half the name ("eps indi").
// The server mirror is backend/blinkspace/assistant_intent.py; tools/contracts/assistant-intents.json
// holds the cases both sides must agree on.

/** Lower case, no diacritics, single spaces: "Güneş'e götür" -> "gunes'e gotur". */
export const plain = (text: string) => text.toLocaleLowerCase('tr').replace(/ı/g, 'i').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[’‘`]/g, "'").replace(/[−–—]/g, '-').replace(/\s+/g, ' ').trim()

/** Words of a plain string: letters and digits only. */
export const words = (text: string) => text.split(/[^a-z0-9]+/).filter(Boolean)

/** Optimal string alignment distance (insert, delete, substitute, swap neighbours), cut off above `max`. */
export function editDistance(a: string, b: string, max = 2): number {
  if (a === b) return 0
  if (Math.abs(a.length - b.length) > max) return max + 1
  let before: number[] = [], previous = Array.from({ length: b.length + 1 }, (_, i) => i)
  for (let i = 1; i <= a.length; i++) {
    const current = [i]
    let best = i
    for (let j = 1; j <= b.length; j++) {
      let cost = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1))
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) cost = Math.min(cost, before[j - 2] + 1)
      current.push(cost); best = Math.min(best, cost)
    }
    if (best > max) return max + 1
    before = previous; previous = current
  }
  return previous[b.length]
}

/** Typos allowed for a name word: none for short words, one from five letters, two from nine. */
const slack = (word: string) => /\d/.test(word) || word.length < 5 ? 0 : word.length < 9 ? 1 : 2

/** Does the typed word mean this name word? Allows typos and a short Turkish ending ("barnarda", "proximayi"). */
export function sameWord(typed: string, name: string): boolean {
  const k = slack(name)
  if (editDistance(typed, name, k) <= k) return true
  // A case ending glued to the name: compare the stem only. Short names must match exactly.
  if (name.length < 5 || typed.length <= name.length || typed.length > name.length + 4) return false
  return [name.length, name.length + 1].some(n => n < typed.length && editDistance(typed.slice(0, n), name, k) <= k)
}

export interface Named { id: string; name: string }
// Words that never identify a star by themselves.
const GENERIC = new Set(['star', 'the', 'yildizi', 'yildiz', 'gaia', 'name', 's'])
// Other things people call the ready targets. Keys are target ids; every alias is already plain().
const ALIASES: Record<string, string[]> = {
  barnard: ['barnard', 'barnards', 'gj 699', 'gliese 699'],
  'eps-indi-b': ['epsilon indi', 'eps indi', 'epsilon indi b', 'eps indi b'],
  'wise-0855': ['wise 0855', 'wise0855', '0855', 'wise 0855 0714'],
  'rw-aur': ['rw aurigae', 'rw aur', 'aurigae'],
  'r-dra': ['r draconis', 'r dra', 'draconis'],
}

/** How well a query names this star: 0 = not at all. Every distinctive word of some alias must be present. */
function score(query: string[], star: Named): number {
  const full = words(plain(star.name)).filter(w => !GENERIC.has(w))
  // "Proxima" is enough for Proxima Centauri: a long first word stands for the whole name
  const names = [full, ...(full.length > 1 && full[0].length > 4 ? [[full[0]]] : []), ...(ALIASES[star.id] ?? []).map(alias => words(alias))]
  let best = 0
  for (const parts of names) {
    if (!parts.length) continue
    let exact = 0
    const all = parts.every(part => query.some(q => { if (q === part) { exact++; return true } return sameWord(q, part) }))
    // one letter ("r") or a bare number is only a name together with its other word
    if (!all || (parts.length === 1 && parts[0].length < 4)) continue
    best = Math.max(best, parts.join('').length + exact * 2)
  }
  return best
}

/** The star a sentence names, or null. Earlier entries win ties, so list the ready targets first. */
export function findStar<T extends Named>(text: string, stars: T[]): T | null {
  const query = words(plain(text))
  let found: T | null = null, top = 0
  for (const star of stars) { const s = score(query, star); if (s > top) { top = s; found = star } }
  return found
}

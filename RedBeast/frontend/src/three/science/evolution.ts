import data from '../data/evolution.json'

export interface EvolutionTrack { id: string; source: string; mass: number; url: string; composition: string; rows: number[][]; end: string }
export const evolutionTracks: EvolutionTrack[] = data.tracks
export const evolutionTrack = (id: string): EvolutionTrack => evolutionTracks.find(t => t.id === id) ?? evolutionTracks[0]
export function suggestedTrack(target: string | null): string {
  return ({ barnard: 'bhac-0.15', 'eps-indi-b': 'atmo-0.05', 'wise-0855': 'atmo-0.005', 'rw-aur': 'mist-1.4', 'r-dra': 'mist-1' } as Record<string, string>)[target ?? ''] ?? 'mist-1'
}
/** Interpolate adjacent published samples in logarithmic physical quantities.
 * The slider is sample/EEP progress, NOT uniform years; it never extrapolates.
 */
export function evolutionAt(track: EvolutionTrack, progress: number) {
  const p = Math.max(0, Math.min(1, Number.isFinite(progress) ? progress : 0)) * (track.rows.length - 1)
  const i = Math.floor(p), a = track.rows[i], b = track.rows[Math.min(i + 1, track.rows.length - 1)], f = p - i
  const logMix = (column: number) => Math.exp(Math.log(a[column]) * (1 - f) + Math.log(b[column]) * f)
  return { age: logMix(0), temperature: logMix(1), radius: logMix(2), luminosity: logMix(3), mass: a[4] * (1 - f) + b[4] * f,
    phase: a[5], massLoss: a[6] * (1 - f) + b[6] * f, index: i, endpoint: p === track.rows.length - 1 }
}
export type EvolutionSample = ReturnType<typeof evolutionAt>
export function phaseLabel(phase: number, lang: 'tr' | 'en', endpoint = false): string {
  if (endpoint && phase === 6) return lang === 'tr' ? 'Beyaz cüce soğuması sınırı' : 'White dwarf cooling boundary'
  const labels: Record<number, [string, string]> = {
    [-3]: ['Kahverengi cüce soğuması', 'Brown dwarf cooling'], [-2]: ['Düşük kütleli yıldız modeli', 'Low-mass stellar track'],
    [-1]: ['Ana kol öncesi büzülme', 'Pre-main-sequence contraction'], 0: ['Ana kol', 'Main sequence'],
    2: ['Kırmızı dev kolu', 'Red giant branch'], 3: ['Çekirdekte helyum yanması', 'Core helium burning'],
    4: ['Erken asimptotik dev kolu', 'Early AGB'], 5: ['Termal atımlı dev', 'Thermally pulsing AGB'],
    6: ['AGB sonrası büzülme', 'Post-AGB contraction'],
  }
  return labels[phase]?.[lang === 'tr' ? 0 : 1] ?? String(phase)
}
export function formatAge(age: number, lang: 'tr' | 'en'): string {
  const n = new Intl.NumberFormat(lang, { maximumSignificantDigits: 4 })
  return age >= 1e9 ? `${n.format(age / 1e9)} ${lang === 'tr' ? 'milyar yıl' : 'Gyr'}`
    : age >= 1e6 ? `${n.format(age / 1e6)} ${lang === 'tr' ? 'milyon yıl' : 'Myr'}` : age >= 1e3 ? `${n.format(age / 1e3)} ${lang === 'tr' ? 'bin yıl' : 'kyr'}` : `${n.format(age)} ${lang === 'tr' ? 'yıl' : 'yr'}`
}
/** A labelled log compression with a visibility floor; not a physical spatial scale. */
export const evolutionDisplayRadius = (radius: number) => .45 + 1.2 * Math.log10(1 + radius)

// Instant answers from what the page already holds: the catalogue row and the cited stellar profile of a star.
// Nothing is fetched and nothing is estimated here. A value that is not in the data is reported as missing.
import type { Sequence } from '../lib/types'
import type { MotionStar, StellarProfile } from '../three/types'
import { distanceLy, skyCoordinates } from '../three/science/astrometry'

export type Field = 'overview' | 'distance' | 'temperature' | 'radius' | 'motion' | 'parallax' | 'type' | 'brightness' | 'position' | 'rotation' | 'age' | 'mass' | 'frames'
export interface FactRow { label: string; value: string; note?: string }
type Lang = 'tr' | 'en'

// Matched against plain() text. Turkish stems carry \w* for their endings.
const FIELD_WORDS: [Field, RegExp][] = [
  ['distance', /\b(how far|distance|far away|light.?years?|parsecs?|uzak\w*|mesafe\w*|isik yili\w*|parsek\w*)\b/g],
  ['temperature', /\b(temperature|how (hot|cold|warm)|sicak\w*|soguk\w*|kelvin|teff|kac derece|isisi)\b/g],
  ['radius', /\b(radius|how (big|large|small)|size|diameter|yaricap\w*|buyukl\w*|ne kadar buyuk|boyut\w*|capi)\b/g],
  ['motion', /\b(proper motion|how fast|speed|velocity|ozdevinim\w*|hizi|ne kadar hizli|radial velocity|dikine hiz\w*)\b/g],
  ['parallax', /\b(parallax|paralaks\w*)\b/g],
  ['type', /\b(spectral( type| class)?|what (kind|type|sort)|tayf\w*|ne tur|turu|sinifi|ne yildizi|nasil bir yildiz)\b/g],
  ['brightness', /\b(magnitude|how bright|brightness|parlakl\w*|ne kadar parlak|kadir\w*|colou?r|rengi?)\b/g],
  ['position', /\b(coordinates?|right ascension|declination|konumu?|koordinat\w*|where is|nerede)\b/g],
  ['rotation', /\b(rotat\w*|spin\w*|donus\w*|donme\w*)\b/g],
  ['age', /\b(how old|age|kac yasinda|yasi|yasini)\b/g],
  ['mass', /\b(mass(?! slider)|how (massive|heavy)|kutlesi\w*|agirlig\w*)\b/g],
  ['frames', /\b(how many (frames|observations|images)|kac (kare|gozlem|goruntu)\w*|when was (it|this) observed|ne zaman gozlen\w*|wavelength|dalga boyu\w*)\b/g],
]
// "bilgi ver", "tell me about it": an overview of whichever star is meant.
const OVERVIEW = /\b(tell me( more)?|info\w*|facts?|summary|summari[sz]e|describe|details?|bilgi\w*|anlat\w*|ozet\w*|tanit\w*|detay\w*|what do (we|you) know|ne biliyor\w*)\b/g
// These only ask for an overview when a star is named or pointed at ("what is it", "Barnard nedir").
const WEAK_OVERVIEW = /\b(what is|what's|who is|about|nedir|kimdir|hakkinda)\b/g
/** Needs an explanation, a derivation or this tool's own measurement: left to the sourced assistant. */
export const EXPLAIN = /\b(why|neden|nicin|niye|how (does|do|did|can|come)|explain\w*|acikla\w*|nasil (calis|olus|hesap|olc|bul|yap)\w*|what does|ne demek|ne anlama|nereden|where (does|do|did)|what did (you|we)|measure\w*|result\w*|sigma|olcum\w*|olctu\w*|sonuc\w*|ne buldu\w*|did it|degisti mi|kaydi mi)\b/
/** The visitor points at the star on screen instead of naming one. */
export const POINTS = /\b(it|its|this|that|bu|su|bunun|onun|bunu|onu)\b/
// Small words that say nothing about the subject of a question.
const FILLER = new Set(('the a an is are was it its this that these star stars me my tell give show what whats how of to about some more please can could you do does we know any for and in on at now quick quickly here there one current selected target object away from us our earth sun right'
  + ' bu su o onun bunun bunu onu yildiz yildizin yildizi yildizla ne nedir kac kadar mi mu ver verir misin soyle goster bana bize biraz daha hakkinda lutfen bir ve ile hedef hedefin secili simdi hizlica dunya dunyadan dunyaya bizden gunes gunesten gunese olan var peki ya icin').split(' '))

/** Which facts a question asks for, and what is left of it once those words are removed. */
export function askedFields(q: string, pointed: boolean): { fields: Field[]; rest: string[] } {
  let rest = q
  const fields: Field[] = []
  for (const [field, pattern] of FIELD_WORDS) if (q.search(pattern) >= 0) { fields.push(field); rest = rest.replace(pattern, ' ') }
  if (!fields.length && (q.search(OVERVIEW) >= 0 || (pointed && q.search(WEAK_OVERVIEW) >= 0))) fields.push('overview')
  rest = rest.replace(OVERVIEW, ' ').replace(WEAK_OVERVIEW, ' ')
  return { fields, rest: rest.split(/[^a-z0-9]+/).filter(w => w.length > 2 && !FILLER.has(w)) }
}

const text = (lang: Lang, tr: string, en: string) => (lang === 'tr' ? tr : en)
export interface FactSource { star: MotionStar; profile?: StellarProfile; sequence?: Sequence | null; year: number; lang: Lang }

/** Rows for the asked fields, in the order asked. Missing data is said to be missing, never filled in. */
export function factRows(fields: Field[], { star, profile, sequence, year, lang }: FactSource): FactRow[] {
  const n = (value: number, digits = 2) => new Intl.NumberFormat(lang === 'tr' ? 'tr-TR' : 'en-US', { maximumFractionDigits: digits }).format(value)
  const T = (tr: string, en: string) => text(lang, tr, en), source = star.source ?? T('katalog', 'catalogue')
  const parameter = (key: string) => { const p = profile?.parameters[key]; return p && typeof p.value === 'number' ? p : null }
  const withError = (p: { value: number | string | null; uncertainty?: number }, digits = 3) => `${n(p.value as number, digits)}${p.uncertainty !== undefined ? ` ± ${n(p.uncertainty, digits)}` : ''}`
  const noteOf = (p: { note?: string; note_tr?: string }) => (lang === 'tr' ? p.note_tr ?? p.note : p.note)
  const rows: Record<Exclude<Field, 'overview'>, () => FactRow[]> = {
    distance: () => [{ label: T('Uzaklık', 'Distance'), value: `${n(distanceLy(star))} ${T('ışık yılı', 'light-years')} (${n(star.distancePc)} pc)`, note: T(`Paralakstan hesaplandı · ${source}`, `Computed from the parallax · ${source}`) }],
    parallax: () => [{ label: T('Paralaks', 'Parallax'), value: `${n(star.parallax, 3)}${star.parallaxError !== undefined ? ` ± ${n(star.parallaxError, 3)}` : ''} mas`, note: source }],
    temperature: () => {
      const p = parameter('teff_k')
      if (p) return [{ label: T('Sıcaklık', 'Temperature'), value: `${withError(p, 0)} K`, note: noteOf(p) }]
      if (star.teff_k) return [{ label: T('Sıcaklık', 'Temperature'), value: `${n(star.teff_k, 0)} K`, note: T(`Katalog değeri · ${star.teff_source}`, `Catalogue value · ${star.teff_source}`) }]
      return [{ label: T('Sıcaklık', 'Temperature'), value: T('katalogda yok', 'not in the catalogue') }]
    },
    radius: () => { const p = parameter('radius_solar'); return [p ? { label: T('Yarıçap', 'Radius'), value: `${withError(p)} R☉`, note: noteOf(p) } : { label: T('Yarıçap', 'Radius'), value: T('kaynaklı bir değer yok', 'no source-backed value') }] },
    motion: () => {
      const total = Math.hypot(star.pmRa, star.pmDec)
      return [{ label: T('Özdevinim', 'Proper motion'), value: total >= 1000 ? `${n(total / 1000)}″/${T('yıl', 'yr')}` : `${n(total, 1)} mas/${T('yıl', 'yr')}`, note: source },
        { label: T('Dikine hız', 'Radial velocity'), value: star.hasRadialVelocity ? `${n(star.radialVelocity, 1)} km/s` : T('ölçüm yok', 'not measured'), note: star.hasRadialVelocity ? undefined : T('Hareket modelinde sıfır varsayılır.', 'The motion model assumes zero.') }]
    },
    type: () => [{ label: T('Tayf türü', 'Spectral type'), value: star.spectralType ?? T('katalogda yok', 'not in the catalogue'), note: (lang === 'tr' ? star.subtitleTr : star.subtitleEn) ?? profile?.type }],
    brightness: () => [
      ...(star.magnitude !== undefined ? [{ label: T('Parlaklık · Gaia G', 'Brightness · Gaia G'), value: `${n(star.magnitude)} ${T('kadir', 'mag')}` }] : [{ label: T('Parlaklık', 'Brightness'), value: T('katalogda yok', 'not in the catalogue') }]),
      ...(star.colorIndex !== undefined ? [{ label: T('Renk · BP−RP', 'Colour · BP−RP'), value: `${n(star.colorIndex)} ${T('kadir', 'mag')}` }] : []),
    ],
    position: () => { const c = skyCoordinates(star, year); return [{ label: 'ICRS · RA / Dec', value: `${c.ra.toFixed(4)}° / ${c.dec >= 0 ? '+' : ''}${c.dec.toFixed(4)}°`, note: T(`${Math.round(year)} yılı için katalog hareketinden hesaplandı.`, `Computed for ${Math.round(year)} from the catalogued motion.`) }] },
    rotation: () => { const p = parameter('rotation_period_days'); return [p ? { label: T('Dönüş süresi', 'Rotation period'), value: `${withError(p, 0)} ${T('gün', 'days')}`, note: noteOf(p) } : { label: T('Dönüş süresi', 'Rotation period'), value: T('benimsenmiş bir değer yok', 'no adopted value') }] },
    age: () => [{ label: T('Yaş', 'Age'), value: T('ölçülmüş bir yaş yok', 'no measured age'), note: T('Yayımlanmış evrim tablosu bir karşılaştırmadır; bu yıldızın ölçülmüş yaşı değildir.', 'The published evolution table is a comparison, not the measured age of this star.') }],
    mass: () => { const p = parameter('mass_solar'); return [p ? { label: T('Kütle', 'Mass'), value: `${withError(p)} M☉`, note: noteOf(p) } : { label: T('Kütle', 'Mass'), value: T('benimsenmiş bir değer yok', 'no adopted value'), note: T('Katalogda ve kaynaklı profilde kütle yer almıyor.', 'Neither the catalogue nor the cited profile carries a mass.') }] },
    frames: () => {
      const frames = sequence?.meta.target_id === star.id ? sequence.frames : []
      if (!frames.length) return [{ label: T('SPHEREx kareleri', 'SPHEREx frames'), value: T('bu sayfada yüklü değil', 'not loaded on this page'), note: T('Gözlemler sayfasında gerçek kareler açılır.', 'The Observations page opens the real frames.') }]
      const days = frames[frames.length - 1].mjd_avg - frames[0].mjd_avg
      return [{ label: T('SPHEREx kareleri', 'SPHEREx frames'), value: `${frames.length} ${T('kare', 'frames')} · ${n(days, 0)} ${T('gün', 'days')}`, note: `${frames[0].date_avg.slice(0, 10)} → ${frames[frames.length - 1].date_avg.slice(0, 10)} · ${n(sequence!.meta.wavelength.lam_ref_um, 3)} µm` }]
    },
  }
  const wanted = fields.includes('overview') ? (['type', 'distance', 'temperature', 'radius', 'motion', ...(sequence?.meta.target_id === star.id ? ['frames' as const] : [])] as const) : fields
  return [...new Set(wanted)].flatMap(field => field === 'overview' ? [] : rows[field]())
}

// What the robin does without a language model, in the page itself and with no request:
//  - drives the app: "take me to Barnard" opens that star's own page, "Barnard'ın karelerini göster" its frames,
//    "take me to the Sun", "Samanyolu'nu göster", "yan yana karşılaştır", "2080 yılına git";
//  - reads out what the catalogue and the cited profile already say: "how far is it?", "sıcaklığı kaç?", "bilgi ver".
// Names may be misspelt ("bernard") or carry a Turkish ending ("Barnard'a"). Anything that needs an explanation or
// this tool's own measurements falls through to the sourced assistant (source cards, or the model when configured).
import { getAppState, setAppState, type AppState } from '../lib/store'
import type { Sequence } from '../lib/types'
import type { MotionStar, StellarProfile } from '../three/types'
import { openTarget, type TargetPage } from '../lib/commands'
import { askedFields, EXPLAIN, factRows, POINTS, type FactRow } from './facts'
import { findStar, plain } from './match'

export { plain }
export interface Chip { label: string; text: string }
export interface LocalReply { message: string; run?: () => void; pin?: { label: string; text: string }; facts?: FactRow[]; note?: string; chips?: Chip[] }
export interface LocalDeps {
  /** The ready targets. */
  targets: () => { id: string; name: string }[]
  /** Every star of the loaded catalogue, for names beyond the ready targets and for instant facts. */
  stars?: () => MotionStar[]
  profile?: (id: string) => StellarProfile | undefined
  sequence?: () => Sequence | null
  frameCount: () => number
  select: (id: string) => void
  guide: () => void
  sources: () => void
  setLang: (lang: 'tr' | 'en') => void
}

const camera = (action: string) => window.setTimeout(() => window.dispatchEvent(new CustomEvent('blinkspace:camera', { detail: { action } })), 120)

const PAGE: Record<'tr' | 'en', (s: AppState) => string> = {
  tr: s => s.mode === 'observations' ? 'Gözlemler sayfasındasın: gerçek SPHEREx kareleri' : s.mode === 'neighbors' ? (s.skyScale === 'galaxy' ? 'Gökyüzü sayfasında, Samanyolu görünümündesin' : 'Gökyüzü sayfasında, Güneş’in çevresindesin')
    : s.stellarMode === 'education' ? 'Yıldız sayfasında, temsili eğitim modelindesin' : s.stellarMode === 'evolution' ? 'Yıldız sayfasında, yayımlanmış evrim tablosundasın' : 'Yıldız sayfasında, katalog yıldızındasın',
  en: s => s.mode === 'observations' ? 'You are on Observations: real SPHEREx frames' : s.mode === 'neighbors' ? (s.skyScale === 'galaxy' ? 'You are on Sky, looking at the Milky Way' : 'You are on Sky, around the Sun')
    : s.stellarMode === 'education' ? 'You are on Star, in the illustrative education model' : s.stellarMode === 'evolution' ? 'You are on Star, in a published evolution table' : 'You are on Star, at the catalogue star',
}
const SUN = /\b(gunes\w*|sun)\b/
const DIRECT_REQUEST = /^(?:(?:please|can you|could you|would you) )*(?:take|go|show|open|bring|fly|zoom|visit|compare|start|switch)\b/
const TURKISH_REQUEST = /\b(?:gotur|git|gidelim|goster|ac|gec|don|yaklas|karsilastir|gezdir)(?:ur musun|ir misin|abilir misin)?\b/
const VIEW_SHORTCUT = /^(?:milky way|samanyolu(?:'nu)?|sun|gunes|gozlemler|observations|side by side|yan yana|fark|difference|next frame|sonraki kare|previous frame|onceki kare|blink|kirpistir|(?:3d )?time stack|zaman yigini|education(?: model)?|egitim(?: modeli)?|evolution|life cycle|evrim|sources|kaynaklar|tour|guide|english|turkish|ingilizce|turkce)\b[.!?]*$/
// Which page of a star is meant, when one is: "Barnard's frames", "Barnard'ı gökyüzünde göster".
const DESTINATION: [TargetPage, RegExp][] = [
  ['observations', /\b(gozlem\w*|observations?|kare\w*|frames?|goruntu\w*|images?|spherex|blink|kirpistir\w*)\b/],
  ['evolution', /\b(evrim\w*|evolution|life ?cycle|yasam\w*)\b/],
  ['sky', /\b(gokyuzu\w*|sky|komsu\w*|neighbou?r\w*|harita\w*|map)\b/],
  ['star', /\b(yuzey\w*|surface|menu\w*|sayfa\w*|page|model\w*|3d|3b|katalog\w*|catalogue)\b/],
]

export function createLocalAssistant(deps: LocalDeps) {
  return function local(text: string, lang: 'tr' | 'en'): LocalReply | null {
    const q = plain(text), tr = lang === 'tr', say = (t: string, e: string) => tr ? t : e
    const has = (...words: string[]) => words.some(w => q.includes(w))
    const reply = (label: [string, string], message: [string, string], run: () => void, chips?: Chip[]): LocalReply => ({ message: say(...message), run, pin: { label: say(...label), text }, chips })

    if (/^(?:ne yapabilir\w*|neler yapabilir\w*|what can you do|yardim|help|komutlar|commands)[.!?]*$/.test(q)) return { message: say(
      'Seni uygulamada gezdirebilir, katalogdaki değerleri anında söyleyebilirim. Şunları yazabilirsin:\n• Barnard’a götür (yazım hatası olsa da bulurum)\n• Ne kadar uzak? · Sıcaklığı kaç? · Bilgi ver\n• Barnard’ın karelerini göster, yan yana karşılaştır, farkı göster\n• Güneş’e götür, Samanyolu’nu göster\n• Yaşam evrimini göster, eğitim modelini aç\n• 2080 yılına git\n• Kaynakları aç, bu sayfayı gezdir\nBir komutu çalıştırdıktan sonra “Kısayol yap” ile sabitleyebilirsin. Açıklama isteyen soruları kaynak kartlarıyla yanıtlarım.',
      'I can drive the app for you and read out catalogue values at once. Try:\n• Take me to Barnard (I will find it even if misspelt)\n• How far is it? · How hot is it? · Tell me about it\n• Show Barnard’s frames, compare side by side, show the difference\n• Take me to the Sun, show the Milky Way\n• Show the life cycle, open the education model\n• Go to the year 2080\n• Open sources, give me a tour of this page\nAfter a command runs you can pin it with “Make shortcut”. Questions that need an explanation get source cards.'),
      chips: [{ label: say('Barnard’a götür', 'Take me to Barnard'), text: say('Barnard’a götür', 'Take me to Barnard') }, { label: say('Samanyolu', 'Milky Way'), text: say('Samanyolu’nu göster', 'Show the Milky Way') }] }
    const state = getAppState(), presets = deps.targets(), catalogue = deps.stars?.() ?? []
    if (has('neredeyim', 'where am i', 'hangi sayfa', 'which page')) { const name = presets.find(t => t.id === state.targetId)?.name ?? catalogue.find(t => t.id === state.targetId)?.name; return { message: `${PAGE[lang](state)}${name ? say(`. Seçili hedef: ${name}.`, `. Selected target: ${name}.`) : '.'}` } }

    // Explanations, derivations and this tool's own measurements belong to the sourced assistant.
    if (EXPLAIN.test(q)) return null
    // Ready targets first: "Barnard" means the target, not its duplicate Gaia row.
    const named = findStar(q, [...presets, ...catalogue.filter(s => !presets.some(p => p.id === s.id))])
    const pointed = Boolean(named) || POINTS.test(q)
    const nameOf = (id: string) => presets.find(t => t.id === id)?.name ?? catalogue.find(s => s.id === id)?.name ?? id
    const go = DIRECT_REQUEST.test(q) || TURKISH_REQUEST.test(q)

    // ---- instant facts about a star: the named one, or the one on screen
    const asked = askedFields(q, pointed)
    if (asked.fields.length) {
      const id = named?.id ?? state.targetId
      const star = id ? catalogue.find(s => s.id === id) ?? null : null
      // "how far is the Moon", "tell me about SPHEREx": not about a star we hold, so not ours to answer.
      const elsewhere = !named && (asked.rest.length > 0 || (SUN.test(q) && !POINTS.test(q)))
      if (!star || elsewhere) return null
      const facts = factRows(asked.fields, { star, profile: deps.profile?.(star.id), sequence: deps.sequence?.(), year: state.year, lang })
      const onStar = state.targetId === star.id && state.mode === 'star' && state.stellarMode === 'surface'
      return { message: `**${star.name}**${(tr ? star.subtitleTr : star.subtitleEn) ? ` · ${tr ? star.subtitleTr : star.subtitleEn}` : ''}`, facts,
        note: say('Katalog ve kaynaklı profil değerleri. Ölçüm panelinde kaynakları açabilirsin.', 'Catalogue and cited profile values. The measurements panel lists their sources.'),
        chips: [
          ...(onStar ? [] : [{ label: say('Yıldıza git', 'Go to the star'), text: say(`${star.name} yıldızına götür`, `Take me to ${star.name}`) }]),
          ...(asked.fields.includes('overview') ? [] : [{ label: say('Tüm bilgiler', 'All facts'), text: say(`${star.name} hakkında bilgi ver`, `Tell me about ${star.name}`) }]),
          { label: say('Gerçek kareler', 'Real frames'), text: say(`${star.name} karelerini göster`, `Show ${star.name} frames`) },
        ] }
    }
    // Any other question is for the sourced assistant, never a navigation request.
    if (/[?？]/.test(text) && !go) return null

    // ---- a star by name: its own page ("the star's menu") unless another of its pages is asked for
    const page = DESTINATION.find(([, pattern]) => pattern.test(q))?.[0]
    if (named && (go || (q.split(' ').length <= 3 && !/^(?:why|how|what|when|which|where|who|is|are|does|did)\b/.test(q)))) {
      const to = page ?? 'star', name = nameOf(named.id)
      const where: Record<TargetPage, [string, string]> = {
        star: [`${name} yıldızına gidiyoruz. Katalog değerleri çevresinde; yüzey temsili çizimdir.`, `Heading to ${name}. Its catalogue values sit around it; the surface is an illustration.`],
        sky: [`${name} gökyüzünde: Güneş’in çevresindeki yerine odaklanıyorum.`, `${name} in the sky: focusing on its place around the Sun.`],
        observations: [`${name} için Gözlemler sayfasını açıyorum.`, `Opening Observations for ${name}.`],
        evolution: [`${name} için yayımlanmış evrim tablosunu açıyorum. Bu, ölçülmüş yaşı değildir.`, `Opening the published evolution table for ${name}. It is not its measured age.`],
      }
      return reply([name, name], where[to], () => {
        openTarget(named.id, to, deps.select)
        if (to !== 'observations') return
        if (has('side by side', 'side-by-side', 'yan yana')) setAppState({ viewMode: 'side' })
        else if (has('difference', 'farki', 'fark gorunumu')) setAppState({ viewMode: 'diff' })
        else if (has('time stack', 'zaman yigini', '3b yigin')) setAppState({ stageView: 'timestack' })
        else if (has('blink', 'kirpistir')) setAppState({ playing: true })
      }, [
        { label: say('Ne kadar uzak?', 'How far is it?'), text: say('Ne kadar uzak?', 'How far is it?') },
        { label: say('Sıcaklığı kaç?', 'How hot is it?'), text: say('Sıcaklığı kaç?', 'How hot is it?') },
        { label: say('Bilgi ver', 'Tell me about it'), text: say('Bu yıldız hakkında bilgi ver', 'Tell me about it') },
        ...(to === 'observations' ? [] : [{ label: say('Gerçek kareler', 'Real frames'), text: say(`${name} karelerini göster`, `Show ${name} frames`) }]),
      ])
    }

    // ---- places and views
    if (!go && !VIEW_SHORTCUT.test(q)) return null
    if (has('samanyolu', 'milky way', 'gokada', 'galaxy', 'galaksi')) return reply(['Samanyolu', 'Milky Way'], ['Samanyolu’na çıkıyoruz. Turuncu işaret Güneş; beş hedefin hepsi yanındaki halkanın içinde.', 'Flying out to the Milky Way. The orange marker is the Sun; all five targets are inside the ring beside it.'],
      () => setAppState({ mode: 'neighbors', skyScale: 'galaxy', playing: false }))
    if (/\b(gunes|sun)\b|gunes'|gunese/.test(q) && (go || q.split(' ').length <= 2)) return reply(['Güneş’e git', 'Go to the Sun'], ['Güneş’in çevresine iniyoruz. Güneş ortada; çevresindeki noktalar Gaia’nın ölçtüğü yakın yıldızlar.', 'Flying down to the Sun. It sits in the middle; the dots around it are nearby stars measured by Gaia.'],
      () => { setAppState({ mode: 'neighbors', skyScale: 'local', playing: false }); camera('reset') })
    if (has('yan yana', 'side by side', 'side-by-side')) return reply(['Yan yana', 'Side by side'], ['Kareleri yan yana koydum: solda A (referans), sağda B.', 'Frames are side by side: A (reference) on the left, B on the right.'], () => setAppState({ mode: 'observations', stageView: 'frames', viewMode: 'side', playing: false }))
    if (has('fark', 'difference', 'diff')) return reply(['Fark görünümü', 'Difference view'], ['Fark görünümünü açtım: B eksi A. Dalga boyu farkına dikkat et; her fark gerçek bir değişim değildir.', 'Difference view is open: B minus A. Mind the wavelength gap; not every difference is a real change.'], () => setAppState({ mode: 'observations', stageView: 'frames', viewMode: 'diff', playing: false }))
    if (has('blink', 'kirpistir')) return reply(['Blink', 'Blink'], ['Blink görünümünü açtım.', 'Opened Blink.'],
      () => setAppState({ mode: 'observations', stageView: 'frames', viewMode: 'single', playing: true }))
    if (has('sonraki kare', 'next frame')) { const n = deps.frameCount(); return reply(['Sonraki kare', 'Next frame'], n > 1 ? ['Sonraki gerçek kareye geçtim. Geçiş efekti yok; fark varsa gerçekten karededir.', 'Moved to the next real frame. No blending; whatever differs is in the data.'] : ['Bu hedefte karşılaştıracak ikinci kare yok.', 'This target has no second frame to compare.'],
      () => setAppState(s => ({ mode: 'observations', stageView: 'frames', viewMode: 'single', playing: false, ...(n > 1 ? { frameIndex: (s.frameIndex + 1) % n } : {}) }))) }
    if (has('onceki kare', 'previous frame')) { const n = deps.frameCount(); return reply(['Önceki kare', 'Previous frame'], n > 1 ? ['Önceki gerçek kareye döndüm.', 'Back to the previous real frame.'] : ['Bu hedefte karşılaştıracak ikinci kare yok.', 'This target has no second frame to compare.'],
      () => setAppState(s => ({ mode: 'observations', stageView: 'frames', viewMode: 'single', playing: false, ...(n > 1 ? { frameIndex: (s.frameIndex - 1 + n) % n } : {}) }))) }
    if (has('zaman yigini', 'time stack', '3b yigin')) return reply(['3B zaman yığını', '3D time stack'], ['Kareleri tarih sırasıyla 3B yığına dizdim.', 'Frames are stacked in 3D by date.'], () => setAppState({ mode: 'observations', stageView: 'timestack', playing: false }))
    if (has('gozlem', 'observation', 'kareler', 'frames', 'spherex gor', 'goruntu', 'images')) return reply(['Gözlemler', 'Observations'], ['Gerçek SPHEREx karelerine döndük.', 'Back to the real SPHEREx frames.'], () => setAppState({ mode: 'observations', stageView: 'frames', viewMode: 'single', playing: false }))
    if (has('egitim', 'education', 'kara delik', 'black hole', 'kutle', 'mass slider')) return reply(['Eğitim modeli', 'Education model'], ['Eğitim modelini açtım. Kütleyi en sağa çekip zamanı sona getirirsen kara deliği görürsün. Bu model temsilidir.', 'Education model is open. Slide the mass all the way right and run time to the end to see the black hole. This model is illustrative.'], () => setAppState({ mode: 'star', stellarMode: 'education', playing: false, evolutionPlaying: false }))
    if (has('evrim', 'evolution', 'life cycle', 'yasam', 'lifecycle')) return reply(['Yaşam evrimi', 'Life cycle'], ['Yayımlanmış evrim tablosunu açtım. Bu, seçili yıldızın ölçülmüş yaşı değildir.', 'The published evolution table is open. It is not the measured age of the chosen star.'], () => setAppState({ mode: 'star', stellarMode: 'evolution', playing: false }))
    if (has('kaynak', 'sources', 'source list')) return reply(['Kaynaklar', 'Sources'], ['Kaynakları ve sınırları açıyorum.', 'Opening sources and limits.'], deps.sources)
    if (has('gezdir', 'tur ', 'rehber', 'tour', 'guide', 'tutorial')) return reply(['Bu sayfayı gezdir', 'Tour this page'], ['Bu sayfanın turunu başlatıyorum.', 'Starting the tour of this page.'], deps.guide)
    if (has('ingilizce', 'english')) return reply(['English', 'English'], ['Switching to English.', 'Switching to English.'], () => deps.setLang('en'))
    if (has('turkce', 'turkish')) return reply(['Türkçe', 'Türkçe'], ['Türkçeye geçiyorum.', 'Türkçeye geçiyorum.'], () => deps.setLang('tr'))

    const year = /\b(20\d\d|2100)\b/.exec(q)
    if (year && has('yil', 'year', 'git', 'go')) { const y = Math.min(2100, Math.max(2000, Number(year[1]))); return reply([`${y} yılı`, `Year ${y}`], [`Konum yılını ${y} yaptım. Yıldızların yeri katalogdaki harekete göre hesaplanır.`, `Position year set to ${y}. Star positions follow their catalogued motion.`],
      () => setAppState(s => ({ year: y, playing: false, ...(s.mode === 'observations' ? { mode: 'neighbors' as const, skyScale: 'local' as const } : {}) }))) }

    // "the star", "yıldıza dön": the page of whichever star is selected
    if (state.targetId && go && /\b(yildiz\w*|star)\b/.test(q)) { const id = state.targetId; return reply(['Yıldız', 'Star'], [`${nameOf(id)} yıldızına dönüyoruz.`, `Back to ${nameOf(id)}.`], () => openTarget(id, 'star', deps.select)) }
    return null
  }
}

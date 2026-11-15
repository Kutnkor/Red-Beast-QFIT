// What the robin can do without a language model: understand plain navigation requests ("take me to the Sun",
// "Samanyolu'nu göster", "Barnard'a git", "yan yana karşılaştır") and carry them out in the app. Anything it does
// not recognise falls through to the normal assistant (source cards, or the model when one is configured).
// It never answers science questions itself, so it cannot contradict the sourced answers.
import { getAppState, setAppState, type AppState } from '../lib/store'
import { suggestedTrack } from '../three/science/evolution'

export interface LocalReply { message: string; run?: () => void; pin?: { label: string; text: string } }
export interface LocalDeps {
  targets: () => { id: string; name: string }[]
  frameCount: () => number
  select: (id: string) => void
  guide: () => void
  sources: () => void
  setLang: (lang: 'tr' | 'en') => void
}

/** Lower case, no diacritics, single spaces: "Güneş'e götür" -> "gunes'e gotur". */
export const plain = (text: string) => text.toLocaleLowerCase('tr').replace(/ı/g, 'i').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\s+/g, ' ').trim()

const camera = (action: string) => window.setTimeout(() => window.dispatchEvent(new CustomEvent('blinkspace:camera', { detail: { action } })), 120)
const PAGE: Record<'tr' | 'en', (s: AppState) => string> = {
  tr: s => s.mode === 'observations' ? 'Gözlemler sayfasındasın: gerçek SPHEREx kareleri' : s.mode === 'neighbors' ? (s.skyScale === 'galaxy' ? 'Gökyüzü sayfasında, Samanyolu görünümündesin' : 'Gökyüzü sayfasında, Güneş’in çevresindesin')
    : s.stellarMode === 'education' ? 'Yıldız sayfasında, temsili eğitim modelindesin' : s.stellarMode === 'evolution' ? 'Yıldız sayfasında, yayımlanmış evrim tablosundasın' : 'Yıldız sayfasında, katalog yıldızındasın',
  en: s => s.mode === 'observations' ? 'You are on Observations: real SPHEREx frames' : s.mode === 'neighbors' ? (s.skyScale === 'galaxy' ? 'You are on Sky, looking at the Milky Way' : 'You are on Sky, around the Sun')
    : s.stellarMode === 'education' ? 'You are on Star, in the illustrative education model' : s.stellarMode === 'evolution' ? 'You are on Star, in a published evolution table' : 'You are on Star, at the catalogue star',
}

export function createLocalAssistant(deps: LocalDeps) {
  return function local(text: string, lang: 'tr' | 'en'): LocalReply | null {
    const q = plain(text), tr = lang === 'tr', say = (t: string, e: string) => tr ? t : e
    const has = (...words: string[]) => words.some(w => q.includes(w))
    const tokens = new Set(q.split(/[^a-z0-9]+/))
    const reply = (label: [string, string], message: [string, string], run: () => void): LocalReply => ({ message: say(...message), run, pin: { label: say(...label), text } })

    if (has('ne yapabilir', 'neler yapabilir', 'what can you do', 'yardim', 'help', 'komutlar', 'commands')) return { message: say(
      'Seni uygulamada gezdirebilirim. Şunları yazabilirsin:\n• Güneş’e götür\n• Samanyolu’nu göster\n• Barnard’a git (ya da başka bir hedef)\n• Gözlemleri aç, yan yana karşılaştır, farkı göster\n• Sonraki kare\n• Yaşam evrimini göster, eğitim modelini aç\n• 2080 yılına git\n• Kaynakları aç, bu sayfayı gezdir\nBir komutu çalıştırdıktan sonra “Kısayol yap” ile sabitleyebilirsin. Bilim sorularını da sor: kaynak kartlarıyla cevap veririm.',
      'I can drive the app for you. Try:\n• Take me to the Sun\n• Show the Milky Way\n• Go to Barnard (or another target)\n• Open observations, compare side by side, show the difference\n• Next frame\n• Show the life cycle, open the education model\n• Go to the year 2080\n• Open sources, give me a tour of this page\nAfter a command runs you can pin it with “Make shortcut”. Ask science questions too: I answer with source cards.') }
    if (has('neredeyim', 'where am i', 'hangi sayfa', 'which page')) { const s = getAppState(), name = deps.targets().find(t => t.id === s.targetId)?.name; return { message: `${PAGE[lang](s)}${name ? say(`. Seçili hedef: ${name}.`, `. Selected target: ${name}.`) : '.'}` } }

    // A question is for the sourced assistant, never a navigation request.
    if (text.includes('?')) return null
    // places
    const go = ['gotur', 'git', 'gidelim', 'goster', 'ac', 'gec', 'don', 'in', 'yaklas', 'take', 'go', 'show', 'open', 'bring', 'fly', 'zoom'].some(w => tokens.has(w))
    if (has('samanyolu', 'milky way', 'gokada', 'galaxy', 'galaksi')) return reply(['Samanyolu', 'Milky Way'], ['Samanyolu’na çıkıyoruz. Turuncu işaret Güneş; beş hedefin hepsi yanındaki halkanın içinde.', 'Flying out to the Milky Way. The orange marker is the Sun; all five targets are inside the ring beside it.'],
      () => setAppState({ mode: 'neighbors', skyScale: 'galaxy', playing: false }))
    if (/\b(gunes|sun)\b|gunes'|gunese|gunes’/.test(q) && (go || q.split(' ').length <= 2)) return reply(['Güneş’e git', 'Go to the Sun'], ['Güneş’in çevresine iniyoruz. Güneş ortada; çevresindeki noktalar Gaia’nın ölçtüğü yakın yıldızlar.', 'Flying down to the Sun. It sits in the middle; the dots around it are nearby stars measured by Gaia.'],
      () => { setAppState({ mode: 'neighbors', skyScale: 'local', playing: false }); camera('reset') })
    if (has('yan yana', 'side by side', 'side-by-side')) return reply(['Yan yana', 'Side by side'], ['Kareleri yan yana koydum: solda A (referans), sağda B.', 'Frames are side by side: A (reference) on the left, B on the right.'], () => setAppState({ mode: 'observations', stageView: 'frames', viewMode: 'side', playing: false }))
    if (has('fark', 'difference', 'diff')) return reply(['Fark görünümü', 'Difference view'], ['Fark görünümünü açtım: B eksi A. Dalga boyu farkına dikkat et; her fark gerçek bir değişim değildir.', 'Difference view is open: B minus A. Mind the wavelength gap; not every difference is a real change.'], () => setAppState({ mode: 'observations', stageView: 'frames', viewMode: 'diff', playing: false }))
    if (has('sonraki kare', 'next frame', 'blink', 'kirpistir')) { const n = deps.frameCount(); return reply(['Sonraki kare', 'Next frame'], n > 1 ? ['Sonraki gerçek kareye geçtim. Geçiş efekti yok; fark varsa gerçekten karededir.', 'Moved to the next real frame. No blending; whatever differs is in the data.'] : ['Bu hedefte karşılaştıracak ikinci kare yok.', 'This target has no second frame to compare.'],
      () => setAppState(s => ({ mode: 'observations', stageView: 'frames', viewMode: 'single', playing: false, ...(n > 1 ? { frameIndex: (s.frameIndex + 1) % n } : {}) }))) }
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

    // a target by name: "Barnard'a git", "show R Draconis"
    const target = deps.targets().map(t => ({ t, key: plain(t.name).replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim() }))
      .find(({ key }) => { const words = key.split(' ').filter(w => w.length > 2 && !['star', 'the'].includes(w)); return q.includes(key) || (words.length > 0 && words.slice(0, 2).every(w => q.includes(w))) || (words[0] && words[0].length > 4 && q.includes(words[0])) })
    if (target && (go || q.split(' ').length <= 3)) return reply([target.t.name, target.t.name], [`${target.t.name} seçildi. Bulunduğun sayfada onu gösteriyorum.`, `${target.t.name} is selected and shown on the current page.`],
      () => { deps.select(target.t.id); setAppState({ evolutionTrack: suggestedTrack(target.t.id), evolutionProgress: 0 }) })
    return null
  }
}

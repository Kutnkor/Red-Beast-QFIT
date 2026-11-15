import { api, request } from '../lib/api'
import { getAppState, type AppState } from '../lib/store'
import type { Sequence, Target } from '../lib/types'
import type { ActionExecutor } from './actions'
import type { QFitResponse } from './api'
import type { LocalReply } from './localIntent'
import { findStar, plain, type Named } from './match'

interface ComparisonFrame {
  index: number
  obs_id: string
  date: string
  wavelength_um: number | null
  rms_arcsec: number | null
  saturated: boolean | null
}
interface Pair {
  a: ComparisonFrame
  b: ComparisonFrame
  days: number
  gap_bandwidth: number | null
  overlap: number | null
  alignment_rms_arcsec: number | null
  measured_shift_arcsec: number | null
  estimated_error_arcsec: number | null
  predicted_shift_arcsec: number | null
  issues: string[]
}
interface Comparison {
  sequence_id: string
  pair: Pair | null
  reasons: string[]
  limits: { gap_bandwidth: number; alignment_arcsec: number; common_pixels: number }
  motion_fit: { n_points?: number; from_date?: string; to_date?: string; measured_shift_arcsec?: number; significance_sigma?: number } | null
}

type ObservationData = { sequence: Sequence | null; targets: Target[] }

function observationSequenceId(data: ObservationData, state: AppState, target = state.targetId) {
  if (target === state.targetId) {
    if (state.sequenceId) return state.sequenceId
    if (data.sequence?.meta.target_id === target) return data.sequence.id
  }
  return data.targets.find(item => item.id === target)?.ready_sequence_id ?? null
}

export async function loadObservationSequence(data: ObservationData, signal?: AbortSignal, expectedId?: string) {
  const state = getAppState()
  const id = observationSequenceId(data, state)
  if (expectedId && expectedId !== id) throw new Error('Observation sequence changed')
  const sequence = data.sequence?.id === id ? data.sequence : (id ? await api.sequence(id, signal) : null)
  signal?.throwIfAborted()
  if (observationSequenceId(data, getAppState()) !== id || getAppState().targetId !== state.targetId) throw new Error('Observation target changed')
  return sequence
}

const bestEn = /^(?:(?:please|could you|can you) )*(?:open|show|find) (?:me )?(?:the )?best (?:comparison|pair)(?: for (.+?))?[.!?]*$/
const bestTr = /^(?:lutfen )?(?:(.+?) icin )?en (?:iyi|uygun) (?:karsilastirmayi|kare ciftini) (?:ac|goster)[.!?]*$/
const question = /^(?:could|can|is|might) (?:this|that|the observed) (?:difference|shift|change|motion) (?:be )?(?:real motion|real movement|actual motion|real|due to real motion)\b|^bu (?:fark|kayma|degisim) gercek (?:bir )?(?:hareket|kayma)(?: olabilir)? mi\b/

function comparisonText(result: Comparison, lang: 'tr' | 'en', best: boolean) {
  const tr = lang === 'tr'
  const T = (turkish: string, english: string) => tr ? turkish : english
  const n = (value: number | null, digits = 2) => value === null
    ? T('bilinmiyor', 'unknown')
    : new Intl.NumberFormat(lang, { maximumFractionDigits: digits }).format(value)
  const reasons: Record<string, string> = {
    need_two_frames: T('en az iki hazır kare gerekiyor', 'at least two prepared frames are needed'),
    same_frame: T('A ve B aynı kare', 'A and B are the same frame'),
    same_epoch: T('gözlem zamanları aynı', 'the observation times are identical'),
    wavelength_unknown: T('dalga boyu uyumu bilinmiyor', 'wavelength agreement is unknown'),
    wavelength_mismatch: T('dalga boyu farkı nicel karşılaştırma sınırını aşıyor', 'the wavelength gap exceeds the quantitative limit'),
    alignment_unknown: T('hizalama doğrulanmamış', 'alignment has not been verified'),
    alignment_large: T('hizalama hatası sınırı aşıyor', 'the alignment residual exceeds the limit'),
    invalid_target: T('hedef çevresindeki pikseller konum ölçümüne elverişli değil', 'pixels around the target are unsuitable for position measurement'),
    saturation_unknown: T('doygunluk durumu bilinmiyor', 'saturation is unknown'),
    saturated_without_centroid: T('doygun çekirdeğin güvenilir konumu yok', 'the saturated core has no usable position'),
    overlap_unknown: T('ortak geçerli piksel alanı doğrulanamadı', 'common valid pixel area could not be verified'),
    overlap_small: T(`ortak alan ${result.limits.common_pixels} pikselden az`, `the common area has fewer than ${result.limits.common_pixels} pixels`),
  }
  const limitations = result.reasons.map(reason => reasons[reason]).filter(Boolean)
  const pair = result.pair
  if (!pair) return T('Güvenilir kare çifti açamadım.', 'I could not open a suitable pair.') + (limitations.length ? ` ${limitations.join(' · ')}.` : '')
  const stamp = (frame: ComparisonFrame) => `${frame.date.slice(0, 16).replace('T', ' ')} UTC`
  const lines = [
    best ? T('Ölçütleri geçen çiftler arasından zaman aralığı en geniş olanını açtım.', 'I opened the eligible pair with the widest time separation.')
      : T('Soru gönderildiğinde seçili olan kareleri inceledim.', 'I checked the frames selected when you asked.'),
    `**A** ${stamp(pair.a)} · **B** ${stamp(pair.b)} · ${n(pair.days, 1)} ${T('gün', 'days')}`,
    T(`**Dalga boyu** A ${n(pair.a.wavelength_um, 4)} µm, B ${n(pair.b.wavelength_um, 4)} µm. Fark ${n(pair.gap_bandwidth, 3)} bant genişliği (sınır ${n(result.limits.gap_bandwidth)}). Farklı dalga boyları parlaklık farkı yaratabilir.`,
      `**Wavelength** A ${n(pair.a.wavelength_um, 4)} µm, B ${n(pair.b.wavelength_um, 4)} µm. Gap ${n(pair.gap_bandwidth, 3)} bandwidths (limit ${n(result.limits.gap_bandwidth)}). Different wavelengths can change apparent brightness.`),
    T(`**Hizalama ve örtüşme** Gaia RMS, A ${n(pair.a.rms_arcsec)}″ ve B ${n(pair.b.rms_arcsec)}″ (sınır ${n(result.limits.alignment_arcsec)}″). Ortak geçerli alan ${n(pair.overlap === null ? null : pair.overlap * 100, 1)}%. Hizalama hatası sahte konum farkı yaratabilir.`,
      `**Alignment and overlap** Gaia RMS, A ${n(pair.a.rms_arcsec)}″ and B ${n(pair.b.rms_arcsec)}″ (limit ${n(result.limits.alignment_arcsec)}″). Common valid area ${n(pair.overlap === null ? null : pair.overlap * 100, 1)}%. Misalignment can mimic a position shift.`),
  ]
  const saturated = [pair.a.saturated === true ? 'A' : '', pair.b.saturated === true ? 'B' : ''].filter(Boolean)
  if (saturated.length) lines.push(T(`**Doygunluk** ${saturated.join(' ve ')} karesinde çekirdek doymuş. Merkez parlaklığı güvenilir ölçülemez ve konum tahmini de bundan etkilenebilir.`,
    `**Saturation** The core is saturated in ${saturated.join(' and ')}. Core brightness is unreliable and the position estimate may also be affected.`))
  else lines.push(T(pair.a.saturated === null || pair.b.saturated === null ? '**Doygunluk** Kalite kaydı eksik.' : '**Doygunluk** İki karede de doygunluk işareti yok.',
    pair.a.saturated === null || pair.b.saturated === null ? '**Saturation** Quality information is missing.' : '**Saturation** Neither frame is flagged as saturated.'))
  if (limitations.length) lines.push(T('**Bu çiftin sınırlamaları** ', '**Limits for this pair** ') + limitations.join(' · ') + '.')
  lines.push(T(`**İki karede ölçülen konum farkı** ${n(pair.measured_shift_arcsec)}″. **Katalog öngörüsü** ${n(pair.predicted_shift_arcsec)}″ (öz hareket modeli).`,
    `**Measured position difference in this pair** ${n(pair.measured_shift_arcsec)}″. **Catalogue prediction** ${n(pair.predicted_shift_arcsec)}″ (proper-motion model).`))
  if (pair.measured_shift_arcsec !== null) lines.push(pair.estimated_error_arcsec === null
    ? T('Çifte ait belirsizlik bilinmiyor.', 'The uncertainty for this pair is unknown.')
    : T(`Bağımsız kare hataları varsayımıyla yaklaşık belirsizlik ${n(pair.estimated_error_arcsec)}″. Ortak sistematik hatalar buna dahil değil.`,
      `Approximate uncertainty is ${n(pair.estimated_error_arcsec)}″ assuming independent frame errors. Shared systematic errors are excluded.`))
  const fit = result.motion_fit
  if (fit?.n_points) {
    const date = (value?: string) => value?.slice(0, 10) ?? T('bilinmiyor', 'unknown')
    lines.push(T(`**${fit.n_points} karelik ayrı uyum** (${date(fit.from_date)} – ${date(fit.to_date)}) ${n(fit.measured_shift_arcsec ?? null)}″, ${n(fit.significance_sigma ?? null, 1)}σ. Bu anlamlılık seçili iki kareye ait değil.`,
      `**Separate ${fit.n_points}-frame fit** (${date(fit.from_date)} – ${date(fit.to_date)}) ${n(fit.measured_shift_arcsec ?? null)}″ at ${n(fit.significance_sigma ?? null, 1)}σ. This significance belongs to the fit across those frames.`))
  }
  if (!best) {
    const shift = pair.measured_shift_arcsec, error = pair.estimated_error_arcsec, prediction = pair.predicted_shift_arcsec
    if (pair.issues.length || shift === null || error === null) lines.push(T('Bu çiftte farkı güvenilir biçimde gerçek harekete bağlayamıyorum.', 'I cannot reliably attribute the difference in this pair to real motion.'))
    else if (shift <= error) lines.push(T('Kayma, tahmini belirsizliğin içinde. Bu çift hareket için tek başına yeterli kanıt sunmuyor.', 'The shift is within the estimated uncertainty. This pair alone offers weak evidence of motion.'))
    else if (prediction !== null && Math.abs(shift - prediction) <= error) lines.push(T('Kaymanın büyüklüğü, tahmini belirsizlik içinde katalog öngörüsüyle uyumlu. Bu, gerçek hareket olasılığını destekler.', 'The size of the shift agrees with the catalogue prediction within the estimated uncertainty. This supports the possibility of real motion.'))
    else lines.push(T('Kayma, tahmini belirsizliği aşıyor. Kaynağını belirlemek için ek gözlemler gerekir.', 'The shift exceeds the estimated uncertainty. More observations are needed to determine its cause.'))
  }
  return lines.join('\n\n')
}

export function createComparisonAssistant(
  catalogue: () => Named[],
  getData: () => ObservationData,
  execute: ActionExecutor,
) {
  return (text: string, lang: 'tr' | 'en'): LocalReply | null => {
    const q = plain(text), best = bestEn.exec(q) ?? bestTr.exec(q)
    if (!best && !question.test(q)) return null
    const tr = lang === 'tr', T = (turkish: string, english: string) => tr ? turkish : english
    const state = getAppState()
    const requested = best?.[1]
    const named = requested ? findStar(requested, catalogue()) : null
    if (requested && !named) return { message: T('Bu hedefi katalogda bulamadım.', 'I could not find that target in the catalogue.') }
    if (!best && (state.mode !== 'observations' || state.stageView !== 'frames')) return { message: T('Önce Gözlemler’deki A/B karelerini aç.', 'Open the A/B frames in Observations first.') }
    const target = named?.id ?? state.targetId
    const id = observationSequenceId(getData(), state, target)
    if (!id) return { message: T('Bu hedef için karşılaştırmaya hazır gözlem dizisi yok.', 'There is no prepared observation sequence for that target.') }
    return { message: '', async run(signal) {
      try {
        const params = best ? '' : `?a=${state.refIndex}&b=${state.frameIndex}`
        const result = await request<Comparison>(`/api/assistant/comparison/${encodeURIComponent(id)}${params}`, { signal })
        signal?.throwIfAborted()
        if (best && result.pair) {
          if (getAppState().targetId !== state.targetId || observationSequenceId(getData(), getAppState(), target) !== id)
            return { failed: true, message: T('Bu sırada açık gözlem değişti.', 'The open observation changed during the request.') }
          if (named && named.id !== state.targetId) {
            const opened = await execute({ name: 'open_target', args: { target_id: named.id, page: 'observations' }, tool_use_id: 'qfit_comparison_target', requires_confirmation: false }, signal)
            if (!opened.ok) return { failed: true, message: T('Hedefi açamadım.', 'I could not open the target.') }
          }
          const applied = await execute({ name: 'set_observation_pair', args: { sequence_id: id, a: result.pair.a.index, b: result.pair.b.index }, tool_use_id: 'qfit_comparison_pair', requires_confirmation: false }, signal)
          if (!applied.ok) return { failed: true, message: T('Seçilen çifti görüntüleyicide açamadım.', 'I could not open the selected pair in the viewer.') }
        }
        const message = comparisonText(result, lang, Boolean(best))
        const sourcePath = `/api/sequences/${encodeURIComponent(id)}`
        const response: QFitResponse = {
          success: true, assistant: 'Q-FIT', intent: 'comparison', message, message_source: 'system',
          sources: [{ name: T('SPHEREx kareleri ve hizalama kaydı', 'SPHEREx frames and alignment records'), url: sourcePath + '/provenance' },
            { name: T('Ölçülen ve öngörülen konumlar', 'Measured and predicted positions'), url: sourcePath + '/track' }],
          data: {}, uncertainty: [],
        }
        return { message, response, failed: !result.pair }
      } catch (error) {
        if (signal?.aborted) throw error
        return { failed: true, message: T('Bu karelerin kalite ve konum verilerine ulaşamadım.', 'I could not retrieve quality and position data for these frames.') }
      }
    } }
  }
}

import { describe, expect, it } from 'vitest'
import { detectLang, MESSAGES, translate, translateCode } from '../i18n'
import { en } from '../i18n/en'
import { tr } from '../i18n/tr'
import { fmtDateUTC, fmtDecDms, fmtRaHms } from '../lib/format'

const placeholders = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join(',')

describe('i18n', () => {
  it('Turkish and English have exactly the same keys', () => {
    const a = Object.keys(tr).sort()
    const b = Object.keys(en).sort()
    expect(b).toEqual(a)
    expect(a.length).toBeGreaterThan(300)
  })

  it('has no empty strings', () => {
    for (const [lang, dict] of Object.entries(MESSAGES)) {
      for (const [key, value] of Object.entries(dict)) {
        expect(typeof value, `${lang}:${key}`).toBe('string')
        expect(value.trim().length, `${lang}:${key}`).toBeGreaterThan(0)
      }
    }
  })

  it('uses the same placeholders in both languages', () => {
    for (const key of Object.keys(tr) as (keyof typeof tr)[]) {
      expect(placeholders(en[key]), key).toBe(placeholders(tr[key]))
    }
  })

  it('covers every code the backend can send', () => {
    const codes: Record<string, string[]> = {
      coord: ['not_a_number', 'not_finite', 'empty', 'too_long', 'bad_sexagesimal', 'bad_unit', 'ra_negative_sexagesimal', 'unit_mismatch', 'ra_out_of_range', 'dec_out_of_range'],
      insuf: ['no_coverage', 'no_usable_frames', 'no_frames_at_wavelength', 'all_frames_rejected', 'single_frame'],
      jobErr: ['timeout', 'archive_error', 'internal_error', 'interrupted_by_restart'],
      stage: ['queued', 'searching', 'downloading', 'preparing'],
      warn: ['single_frame', 'single_visit', 'partial_data', 'center_saturated'],
      cls: ['possible_motion', 'possible_brightness_change', 'possible_artifact', 'unsure'],
      note: ['ra_wrapped', 'ra_assumed_hours', 'ra_assumed_degrees'],
      err: ['rate_limited', 'queue_full', 'bad_coordinates', 'missing_coordinates', 'bad_fov', 'bad_max_frames', 'bad_wavelength', 'bad_date', 'bad_date_range', 'target_not_found', 'sequence_not_found', 'observation_not_found', 'job_not_found', 'not_owner', 'bad_mark', 'invalid_request', 'same_frame', 'no_common_area', 'need_two_frames', 'no_target_prediction', 'raw_file_missing', 'archive_error', 'internal_error'],
      caveat: ['no_psf_matching', 'undersampled_psf_residuals', 'psf_fwhm_differs', 'wavelength_offset_above_quantitative_tolerance', 'alignment_not_verified', 'alignment_residual_large', 'moving_sources_blur', 'variable_sources_averaged', 'cosmic_rays_and_artifacts_possible', 'aperture_flux_no_correction', 'psf_varies_between_frames', 'quick_release_calibration', 'single_wavelength_group_only'],
      reject: ['download_failed', 'unreadable_fits', 'header_mismatch', 'wavelength_mismatch_after_download', 'low_coverage', 'no_valid_pixels'],
      expl: ['touches_flagged_pixels', 'paired_negative_and_positive_residuals', 'brightened', 'faded'],
      lcReason: ['invalid_pixels_in_aperture', 'off_frame', 'no_background_annulus', 'invalid_variance', 'saturated_or_nonlinear'],
    }
    for (const [prefix, list] of Object.entries(codes)) {
      for (const code of list) {
        expect(translateCode('tr', prefix, code), `tr ${prefix}.${code}`).toBeTruthy()
        expect(translateCode('en', prefix, code), `en ${prefix}.${code}`).toBeTruthy()
      }
    }
    expect(translateCode('en', 'err', 'made_up_code')).toBeNull()
  })

  it('carries the required honesty phrases', () => {
    expect(tr['play.note']).toContain('oynatma hızı gerçek zamanı temsil etmez')
    expect(tr['layer.candidatesNote']).toBe('İnceleme yardımı — doğrulanmış keşif değildir.')
    expect(en['layer.candidatesNote']).toBe('Review aid — candidates remain unverified.')
    expect(tr['layer.noMeasurement']).toBe('ölçüm yok')
    expect(en['layer.noMeasurement']).toBe('no measurement')
    expect(tr['obs.banner'].toLowerCase()).toContain('doğrulanmayı bekleyen kullanıcı gözlemi')
    expect(en['obs.banner'].toLowerCase()).toContain('unverified user observation')
    expect(tr['wave.selectionNote']).toContain('zaman karşılaştırması değildir')
    expect(tr['footer.credit']).toBe('Veri: NASA/JPL-Caltech SPHEREx, IRSA (doi:10.26131/IRSA629)')
    expect(en['footer.independent']).toMatch(/not developed or endorsed by NASA/)
    expect(tr['tut.synthetic']).toBe('sentetik eğitim verisi')
  })

  it('interpolates parameters', () => {
    expect(translate('en', 'play.frameOf', { i: 2, n: 6 })).toBe('Frame 2/6')
    expect(translate('tr', 'play.frameOf', { i: 2, n: 6 })).toBe('Kare 2/6')
  })

  it('picks the language from ?lang, then storage, then the browser', () => {
    expect(detectLang('?lang=en', 'tr', 'tr-TR')).toBe('en')
    expect(detectLang('?lang=tr', 'en', 'en-US')).toBe('tr')
    expect(detectLang('?lang=de', 'tr', 'en-US')).toBe('tr')
    expect(detectLang('', 'en', 'tr-TR')).toBe('en')
    expect(detectLang('', null, 'tr-TR')).toBe('tr')
    expect(detectLang('', null, 'TR')).toBe('tr')
    expect(detectLang('', null, 'de-DE')).toBe('en')
    expect(detectLang('', null, undefined)).toBe('en')
  })
})

describe('formatting', () => {
  it('shows dates as UTC, ISO-like', () => {
    expect(fmtDateUTC('2026-08-18T20:49:36Z')).toBe('2026-08-18 20:49 UTC')
    expect(fmtDateUTC('2025-08-25T17:09:20Z', true)).toBe('2025-08-25 17:09:20 UTC')
    expect(fmtDateUTC(null)).toBe('—')
  })

  it('formats sexagesimal coordinates without 60-second overflow', () => {
    expect(fmtRaHms(269.446269)).toBe('17h57m47.10s')
    expect(fmtDecDms(4.768204)).toBe('+04°46′05.5″')
    expect(fmtDecDms(-7.242186)).toBe('−07°14′31.9″')
    expect(fmtRaHms(359.9999999)).toBe('00h00m00.00s')
    expect(fmtDecDms(-0.0001)).toBe('−00°00′00.4″')
    expect(fmtDecDms(9.99999999)).toBe('+10°00′00.0″')
  })
})

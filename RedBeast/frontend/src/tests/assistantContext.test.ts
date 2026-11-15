import { describe, expect, it } from 'vitest'
import { buildAssistantContext } from '../lib/assistantContext'
import { DEFAULT_STATE } from '../lib/store'
import type { Mark } from '../lib/types'
import type { MotionStar } from '../three/types'
import golden from './golden/motion.json'
import { sequence } from './helpers'

const target = { ...golden.stars[0].input, teff_k: 3100, teff_source: 'gaia_gspphot' } as MotionStar
describe('bounded, source-labelled assistant context', () => {
  it('selects current scientific facts and distinguishes their epistemic status', () => {
    const context = buildAssistantContext({ ...DEFAULT_STATE, frameIndex: 2, year: 2050 }, { target, sequence: sequence() })
    expect(context.target!.distance.status).toBe('computed')
    expect(context.target!.parallax.status).toBe('measured')
    expect(context.target!.temperature).toMatchObject({ value: 3100, unit: 'K', status: 'measured', source: 'gaia_gspphot' })
    expect(context.target!.surface.status).toBe('representative')
    expect(context.current_frame).toMatchObject({ obs_id: sequence().frames[2].obs_id, utc: '2026-03-15T00:51:21Z', wavelength_um: 1.512 })
    expect(context.sequence!.change_scientifically_confirmed).toBe(false)
    expect(context.year).toBe(2050)
    expect(new TextEncoder().encode(JSON.stringify(context)).byteLength).toBeLessThanOrEqual(4096)
  })
  it('does not turn absent radial velocity or temperature into measured facts', () => {
    const context = buildAssistantContext(DEFAULT_STATE, { target: { ...target, hasRadialVelocity: false, radialVelocity: 42, teff_k: null, teff_source: 'none' } })
    expect(context.target!.radial_velocity).toMatchObject({ value: 0, status: 'assumed', unit: 'km/s' })
    expect(context.target!.temperature.value).toBeNull()
    expect(context.current_frame).toBeNull()
    expect(context.sequence).toBeNull()
  })
  it('never includes notes, raw marks, private tokens or history even in large drafts', () => {
    const markers: Mark[] = Array.from({ length: 1000 }, (_, index) => ({ id: `m${index}`, kind: 'point', classification: index % 2 ? 'unsure' : 'possible_motion', ra_deg: 269, dec_deg: 4,
      frame_index: 0, note: 'PRIVATE_NOTE_秘密'.repeat(1000), track_id: 'PRIVATE_TRACK' }))
    const seq = { ...sequence(), edit_token: 'PRIVATE_EDIT_TOKEN', note: 'PRIVATE_SEQUENCE_NOTE', chat_history: ['PRIVATE_HISTORY'] }
    const context = buildAssistantContext(DEFAULT_STATE, { target, sequence: seq, marks: markers })
    const serialized = JSON.stringify(context)
    expect(context.marks).toEqual({ count: 1000, classifications: ['possible_motion', 'unsure'] })
    expect(serialized).not.toMatch(/PRIVATE|edit_token|chat_history|track_id|ra_deg|dec_deg/)
    expect(new TextEncoder().encode(serialized).byteLength).toBeLessThanOrEqual(4096)
  })
  it('fails closed if an unbounded public field would exceed the byte budget', () => {
    expect(() => buildAssistantContext(DEFAULT_STATE, { target: { ...target, id: '星'.repeat(2000) } })).toThrow('Assistant context exceeds 4 KB')
  })
})

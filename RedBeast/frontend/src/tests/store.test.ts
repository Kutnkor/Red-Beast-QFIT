import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_STATE, getAppState, setAppState, stateFromQuery, subscribeAppState, syncViewURL } from '../lib/store'

beforeEach(() => setAppState({ ...DEFAULT_STATE, layers: { ...DEFAULT_STATE.layers }, drawer: { ...DEFAULT_STATE.drawer } }))

describe('shared state and view URLs', () => {
  it('parses valid scientific view parameters and clamps epochs to the supported range', () => {
    expect(stateFromQuery('?target=wise-0855&mode=neighbors&year=2050.25&lang=tr&stage=timestack&quality=low')).toEqual({
      targetId: 'wise-0855', mode: 'neighbors', year: 2050.25, lang: 'tr', stageView: 'timestack', quality: 'low', evolutionTrack:'atmo-0.005',
    })
    expect(stateFromQuery('?year=2500').year).toBe(2100)
    expect(stateFromQuery('?year=1900').year).toBe(2000)
    expect(stateFromQuery('?year=NaN&mode=madeup&lang=xx&quality=ultra')).toEqual({})
  })
  it('round-trips the view while preserving shared routes and unrelated search/embed arguments', () => {
    window.history.replaceState(null, '', '/o/obs1234567?embed=1&ra=133.76&dec=-7.24&fov=8&tut=motion')
    setAppState({ targetId: 'wise-0855', mode: 'observations', stageView: 'timestack', year: 2050.25, lang: 'tr' })
    syncViewURL()
    expect(window.location.pathname).toBe('/o/obs1234567')
    const query = new URLSearchParams(window.location.search)
    expect(Object.fromEntries(['embed', 'ra', 'dec', 'fov', 'tut'].map(key => [key, query.get(key)]))).toEqual({ embed: '1', ra: '133.76', dec: '-7.24', fov: '8', tut: 'motion' })
    expect(stateFromQuery(window.location.search)).toMatchObject({ targetId: 'wise-0855', mode: 'observations', stageView: 'timestack', year: 2050.25, lang: 'tr' })
    setAppState({ targetId: null, stageView: 'frames' })
    syncViewURL()
    expect(new URLSearchParams(window.location.search).has('target')).toBe(false)
    expect(new URLSearchParams(window.location.search).has('stage')).toBe(false)
  })
  it('notifies render subscribers only on changes and releases them on unmount', () => {
    const notify = vi.fn(), unsubscribe = subscribeAppState(notify)
    setAppState({ year: 2026 })
    expect(notify).not.toHaveBeenCalled()
    setAppState(previous => ({ year: previous.year + 1 }))
    expect(notify).toHaveBeenCalledTimes(1)
    expect(getAppState().year).toBe(2027)
    unsubscribe()
    setAppState({ year: 2028 })
    expect(notify).toHaveBeenCalledTimes(1)
  })
})


it.each([['barnard','bhac-0.15'],['rw-aur','mist-1.4'],['r-dra','mist-1'],['eps-indi-b','atmo-0.05'],['wise-0855','atmo-0.005']])('deep links connect %s to %s without a target-selection click',(target,track)=>{
 expect(stateFromQuery(`?target=${target}&stellar=evolution`)).toMatchObject({stellarMode:'evolution',evolutionTrack:track})
})
it('keeps an explicitly chosen comparison track and preserves education mode in the URL',()=>{
 expect(stateFromQuery('?target=barnard&stellar=evolution&track=mist-1.4').evolutionTrack).toBe('mist-1.4')
 setAppState({stellarMode:'education'});syncViewURL()
 expect(stateFromQuery(window.location.search).stellarMode).toBe('education')
})

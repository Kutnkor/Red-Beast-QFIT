import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { V4Observatory } from '../v4/V4Observatory'
import type { Props } from '../ui/observatory/Observatory'
import { I18nProvider } from '../i18n'
import { DEFAULT_STATE, useAppState, setAppState, getAppState } from '../lib/store'
import catalogue from '../../../backend/blinkspace/resources/motion_catalogue.json'
import type { MotionCatalogue } from '../three/types'
import { TARGETS, sequence } from './helpers'

const assistant = vi.hoisted(() => ({ context: null as null | (() => Record<string, unknown>) }))
vi.mock('../qfit/QFitAssistant', () => ({ QFitAssistant: (props: { context: () => Record<string, unknown> }) => { assistant.context=props.context;return <div>QFIT</div> } }))
vi.mock('../v4/EducationScene', () => ({ EducationScene: () => <div>Illustrative 3D scene</div> }))
beforeEach(() => setAppState({ ...DEFAULT_STATE, lang:'tr' }))
afterEach(() => vi.restoreAllMocks())

function mount() {
  const sources=vi.fn()
  function Harness() {
    const state=useAppState()
    const props:Props={state,targets:TARGETS,catalogue:catalogue as MotionCatalogue,star:catalogue.targets[0] as MotionCatalogue['targets'][number],sequence:sequence(),marks:[],scene:<div>Real science scene</div>,search:<div>Archive form</div>,measurements:<div>Source measurements</div>,dialogs:null,notices:null,saved:'',online:true,embed:false,select:id=>setAppState({targetId:id}),mode:mode=>setAppState({mode}),save:vi.fn(),sources}
    return <I18nProvider initial="tr"><V4Observatory {...props}/></I18nProvider>
  }
  const view=render(<Harness/>),iframe=view.container.querySelector('iframe')!,doc=iframe.contentDocument!
  doc.open();doc.write('<html><head></head><body></body></html>');doc.close()
  doc.body.innerHTML='<div id="v4-live-scene"></div><div id="v4-live-controls"></div><div id="v4-education-scene"></div><div id="v4-model-switch"></div>'
  let listener:(action:string,value?:string)=>void=()=>{}
  const sample={id:'main_sequence',r:1,T:5772,l:1,m:1,playing:false}
  const bridge={subscribe:vi.fn(fn=>{listener=fn}),setMode:vi.fn(),sample:()=>sample}
  Object.assign(doc.defaultView!,{RedBeastV4:bridge})
  fireEvent.load(iframe)
  return {doc,bridge,sources,sample,action:(a:string,v?:string)=>act(()=>listener(a,v))}
}

it('opens real observations by default and keeps the scene inside an isolated style root',()=>{
  const {doc,bridge,action,sources}=mount()
  expect(getAppState().mode).toBe('observations')
  expect(bridge.setMode).toHaveBeenLastCalledWith('observations','tr')
  expect(doc.getElementById('v4-live-scene')!.shadowRoot!.textContent).toContain('Real science scene')
  action('sources');expect(sources).toHaveBeenCalledOnce()
})

it('separates illustrative education from target observations and reads the current sample when asking QFIT',()=>{
  const {doc,action,sample,bridge}=mount()
  action('view','star')
  expect(bridge.setMode).toHaveBeenLastCalledWith('star','tr')
  fireEvent.click(within(doc.body).getByRole('button',{name:'Eğitim modeli'}))
  expect(bridge.setMode).toHaveBeenLastCalledWith('education','tr')
  expect(doc.getElementById('v4-education-scene')!.textContent).toContain('Illustrative 3D scene')
  sample.T=3300
  const context=assistant.context!()
  expect(context.target).toBeNull();expect(context.sequence).toBeNull();expect(context.current_frame).toBeNull()
  expect(context.view).toBe('illustrative_education')
  expect(context.education_sample).toMatchObject({T:3300})
  fireEvent.click(within(doc.body).getByRole('button',{name:'Kaynaklı model'}))
  expect(bridge.setMode).toHaveBeenLastCalledWith('star','tr')
  expect(getAppState().stellarMode).toBe('evolution')
  expect(assistant.context!().view).toBe('published_comparison_model')
  expect(new TextEncoder().encode(JSON.stringify(assistant.context!())).length).toBeLessThan(4096)
})

it('routes native search to real catalogue coordinates and returns to live sky mode',()=>{
  const {action,doc}=mount()
  action('view','star');action('search')
  fireEvent.change(screen.getByRole('textbox',{name:'Yıldız veya RA / Dec'}),{target:{value:'269.4463, 4.7682'}})
  const first=within(screen.getByRole('dialog')).getAllByRole('button').find(b=>b.textContent?.includes("Barnard's Star"))!
  expect(first.textContent).toContain('0.0000°')
  fireEvent.click(first)
  expect(getAppState().mode).toBe('neighbors')
  expect(getAppState().targetId).toBe('barnard')
  expect(doc.getElementById('v4-education-scene')!.textContent).toBe('')
})

it('changes language through the native flags without changing the selected view or target',()=>{
  const {action,doc,bridge}=mount()
  action('view','star')
  fireEvent.click(within(doc.body).getByRole('button',{name:'Eğitim modeli'}))
  const target=getAppState().targetId
  action('language','en')
  expect(bridge.setMode).toHaveBeenLastCalledWith('education','en')
  expect(within(doc.body).getByRole('button',{name:'Education model'})).toBeTruthy()
  expect(getAppState().targetId).toBe(target)
  expect(getAppState().mode).toBe('star')
  expect(window.localStorage.getItem('bs.lang')).toBe('en')
  action('language','tr')
  expect(bridge.setMode).toHaveBeenLastCalledWith('education','tr')
  expect(within(doc.body).getByRole('button',{name:'Eğitim modeli'})).toBeTruthy()
})


it('keeps the selected target and model when moving between observation and star tabs',()=>{
  const {doc,action,bridge}=mount()
  action('view','star')
  expect(getAppState().targetId).toBe('barnard')
  expect(getAppState().stellarMode).toBe('surface')
  fireEvent.click(within(doc.body).getByRole('button',{name:'Kaynaklı model'}))
  act(()=>setAppState({evolutionPlaying:true,evolutionProgress:.45}))
  fireEvent.click(within(doc.body).getByRole('button',{name:'Eğitim modeli'}))
  expect(getAppState().evolutionPlaying).toBe(false)
  action('view','observations');action('view','star')
  expect(bridge.setMode).toHaveBeenLastCalledWith('education','tr')
  expect(getAppState().evolutionProgress).toBe(.45)
})

it('opens the selected observation target’s published track and returns to its observations',()=>{
  const {doc}=mount()
  fireEvent.click(within(doc.body).getByRole('button',{name:/Bu hedefin yaşam evrimini keşfet/}))
  expect(getAppState()).toMatchObject({mode:'star',stellarMode:'evolution',targetId:'barnard',evolutionTrack:'bhac-0.15'})
  fireEvent.click(within(doc.body).getByRole('button',{name:/Gerçek SPHEREx gözlemlerine dön/}))
  expect(getAppState()).toMatchObject({mode:'observations',targetId:'barnard',evolutionPlaying:false})
})

it('restarts position playback at the range endpoint and forwards reduced-motion preferences',()=>{
  const {doc,action}=mount();action('view','star')
  act(()=>setAppState({year:2100,playing:false}))
  fireEvent.click(within(doc.body).getByRole('button',{name:'Oynat'}))
  expect(getAppState()).toMatchObject({year:2000,playing:true})
  action('motion','reduced');expect(getAppState().reducedMotion).toBe(true)
  action('motion','full');expect(getAppState().reducedMotion).toBe(false)
})

it('shows a useful empty search result rather than a blank list',()=>{
  const {action}=mount();action('search')
  fireEvent.change(screen.getByRole('textbox',{name:'Yıldız veya RA / Dec'}),{target:{value:'no-such-target-xyz'}})
  expect(screen.getByRole('status').textContent).toContain('Katalogda eşleşme yok')
})

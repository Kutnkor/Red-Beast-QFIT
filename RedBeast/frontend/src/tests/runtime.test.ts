import { expect, it, vi } from 'vitest'
import { DEFAULT_STATE } from '../lib/store'
const deferred=vi.hoisted(()=>{
 let reject:(reason:Error)=>void=()=>{}
 const promise=new Promise<never>((_resolve,rejectPromise)=>{reject=rejectPromise})
 return {promise,reject}
})
vi.mock('../three/engine',()=>({Engine:class{
 renderer={domElement:document.createElement('canvas')};quality='high';renderedFrames=0
 onAfterFrame(){return ()=>{}}setQuality(){}setActive(){}dispose(){}
}}))
vi.mock('../three/scenes/StarScene',()=>deferred.promise)
vi.mock('../three/scenes/NeighbourhoodScene',()=>({NeighbourhoodScene:class{
 controls=null;scene={};camera={}
 mount(){}setData(){}update(){}activate(){}unmount(){}
}}))
it('does not let a late failed scene import replace the ready state of a newer scene',async()=>{
 const {SkyRuntime}=await import('../three/runtime')
 const ready=vi.fn(),error=vi.fn(),data={catalogue:null,sequence:null,track:null}
 const runtime=new SkyRuntime(document.createElement('canvas'),document.createElement('div'),{...DEFAULT_STATE,mode:'star'},data,ready,error)
 await runtime.update({...DEFAULT_STATE,mode:'neighbors'},data)
 expect(ready).toHaveBeenLastCalledWith('ready')
 deferred.reject(new Error('Old deployment chunk no longer available'))
 await new Promise(resolve=>setTimeout(resolve,30))
 expect(error).not.toHaveBeenCalled()
 runtime.dispose()
})

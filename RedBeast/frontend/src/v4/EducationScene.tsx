import { useEffect, useRef, useState } from 'react'
import { Scene, PerspectiveCamera, WebGLRenderer, SRGBColorSpace, ACESFilmicToneMapping } from 'three'
import { BlackHole } from '../three/components/BlackHole'
import { EvolutionModel } from '../three/models/EvolutionModel'
import { evolutionDisplayRadius } from '../three/science/evolution'
import { disposeTree } from '../three/dispose'
export interface EducationSample { id: string; r: number; T: number | null; l: number; m: number; age?: number; f: number; c: number[] | null; playing: boolean; reducedMotion?: boolean }
export function EducationScene({ sample, lang = 'tr' }: { sample: () => EducationSample | null; lang?: 'tr' | 'en' }) {
  const host = useRef<HTMLDivElement>(null), [unavailable,setUnavailable]=useState(false)
  useEffect(() => {
    if (!host.current) return
    const element = host.current, scene = new Scene(), camera = new PerspectiveCamera(38, 1, .01, 100)
    let renderer: WebGLRenderer
    try { renderer = new WebGLRenderer({ alpha: true, antialias: true }) } catch { setUnavailable(true);return }
    renderer.outputColorSpace = SRGBColorSpace; renderer.toneMapping=ACESFilmicToneMapping
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); element.append(renderer.domElement)
    camera.position.z = 13.5
    const model = new EvolutionModel('medium'); model.name = 'illustrative-education-not-published-track'; scene.add(model)
    const effects=model.effects;model.remove(effects);scene.add(effects)
    const hole = new BlackHole('high'); hole.visible = false; scene.add(hole)
    let holeTime = 0
    let dirty=true
    const resize = () => { const w = element.clientWidth, h = element.clientHeight; if (!w || !h) return; renderer.setSize(w,h); camera.aspect=w/h; camera.position.z=13.5*Math.max(1,.85/camera.aspect);camera.updateProjectionMatrix();dirty=true }
    const observer = new ResizeObserver(resize); observer.observe(element); resize()
    let raf = 0, previous = 0, visualTime=0, shown:EducationSample|null=null, lost=false, signature=''
    const reduced = matchMedia('(prefers-reduced-motion: reduce)')
    const contextLost=(event:Event)=>{event.preventDefault();lost=true;setUnavailable(true)}
    const contextRestored=()=>{lost=false;setUnavailable(false);resize()}
    renderer.domElement.addEventListener('webglcontextlost',contextLost)
    renderer.domElement.addEventListener('webglcontextrestored',contextRestored)
    const frame = (now: number) => {
      const dt=Math.min(.05,previous?(now-previous)/1000:0);previous=now
      const s = sample()
      if (s&&!document.hidden&&!lost) {
        const calm=reduced.matches||s.reducedMotion
        if(s.playing&&!calm)visualTime+=dt
        const nextSignature=[s.id,s.r,s.T,s.l,s.m,s.f].join(':')
        const settling=!!shown&&(Math.abs(Math.log(Math.max(1e-9,s.r)/shown.r))>.0001||Math.abs((s.T??1000)-(shown.T??1000))>.1)
        // the light around a black hole keeps flowing while the view rests on it (still when motion is reduced)
        const swirling=s.id==='black_hole'&&!calm
        if(swirling)holeTime+=dt
        if(!dirty&&signature===nextSignature&&!settling&&(!s.playing||calm)&&!swirling){element.dataset.playing=String(s.playing);raf=requestAnimationFrame(frame);return}
        signature=nextSignature;dirty=false
        const a=calm?1:1-Math.exp(-dt/0.14)
        if(!shown)shown={...s}
        for(const k of ['r','l','m'] as const)shown[k]=Math.exp(Math.log(Math.max(1e-9,shown[k]))*(1-a)+Math.log(Math.max(1e-9,s[k]))*a)
        shown.T=(shown.T??s.T??1000)+((s.T??1000)-(shown.T??s.T??1000))*a
        const radius=Math.max(1e-6,shown.r),phase=['red_giant','red_supergiant'].includes(s.id)?2:s.id==='agb'?5:s.id==='protostar'?-1:s.id==='planetary_nebula'?6:0
        model.update({age:0,temperature:shown.T,radius,luminosity:Math.max(1e-9,shown.l),mass:shown.m,phase,massLoss:['agb','red_supergiant'].includes(s.id)?1e-5:1e-10,index:0,endpoint:false},visualTime,true,false)
        const f=Math.min(1,Math.max(0,(Math.log10(radius)+5)/9.5)), displayRadius=(26+296*Math.pow(f,1.5))/100
        model.scale.setScalar(displayRadius/evolutionDisplayRadius(radius));model.faceCamera(camera)
        const black=s.id==='black_hole'; model.visible=!black;hole.visible=black
        hole.update(1.9,holeTime)
        effects.update(s.id,displayRadius,visualTime,s.f)
        effects.disk.visible=false
        element.dataset.phase=s.id;element.dataset.visualTime=visualTime.toFixed(3);element.dataset.playing=String(s.playing)
        renderer.render(scene,camera)
      }
      raf=requestAnimationFrame(frame)
    }
    raf=requestAnimationFrame(frame)
    return () => { cancelAnimationFrame(raf);observer.disconnect();renderer.domElement.removeEventListener('webglcontextlost',contextLost);renderer.domElement.removeEventListener('webglcontextrestored',contextRestored);disposeTree(scene);renderer.dispose();renderer.domElement.remove() }
  }, [sample])
  return <div ref={host} className="v4-education-canvas" role="img" aria-label={lang==='tr'?'Temsili üç boyutlu yıldız evrimi; ölçüm veya hedefe özel öngörü değildir':'Illustrative 3D stellar evolution; not a measurement or target prediction'}>{unavailable&&<p role="status">{lang==='tr'?'3B görünüm kullanılamıyor. Evreleri, grafikleri ve değerleri incelemeye devam edebilirsin.':'3D view unavailable. The stages, charts and values remain available.'}</p>}</div>
}

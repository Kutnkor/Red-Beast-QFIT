import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BufferGeometry, Material, Object3D, ObjectLoader, PerspectiveCamera, Quaternion, ShaderMaterial, Vector2, Vector3 } from 'three'
import profiles from '../../../backend/blinkspace/resources/stellar_profiles.json'
import motion from '../../../backend/blinkspace/resources/motion_catalogue.json'
import { DEFAULT_STATE } from '../lib/store'
import type { Engine } from '../three/engine'
import { StarEnvironment } from '../three/components/StarEnvironment'
import { LifecycleEffects } from '../three/models/LifecycleEffects'
import { EvolutionModel } from '../three/models/EvolutionModel'
import { StarSurface } from '../three/components/StarSurface'
import { StarScene } from '../three/scenes/StarScene'
import { createStellarModel } from '../three/models/StellarModel'
import { animateStellarModel, faceStellarModel } from '../three/models/animation'
import { fitDistance, keplerEllipse, parameter, surfaceKind, visualRadius } from '../three/science/models'
import { disposeTree } from '../three/dispose'
import type { ModelCatalogue, MotionCatalogue, SceneData, SceneState } from '../three/types'

function objectsIn(root: Object3D): Object3D[] { const found: Object3D[] = []; root.traverse(object => found.push(object)); return found }

const models = profiles as unknown as ModelCatalogue
const profile = (id: string) => models.profiles.find(item => item.target_id === id)!
const catalogue = motion as unknown as MotionCatalogue
const data: SceneData = { catalogue, models, sequence: null, track: null }
const state = (targetId: string, extra: Partial<SceneState> = {}): SceneState => ({ ...DEFAULT_STATE, layers: { ...DEFAULT_STATE.layers }, targetId, ...extra })
let scenes: StarScene[] = []
beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: false }))
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, arrayBuffer: async () => new ArrayBuffer(0) }))
})
afterEach(() => { scenes.forEach(scene => scene.unmount()); scenes = []; vi.unstubAllGlobals() })

function mountedScene(aspect = 1440 / 900) {
  const callbacks = new Set<(time: number, delta: number) => boolean | void>()
  const resize = new Set<() => void>()
  const canvas = document.createElement('canvas')
  const engine = {
    quality: 'high', size: new Vector2(900 * aspect, 900),
    renderer: { domElement: canvas, getPixelRatio: () => 1 },
    invalidate: vi.fn(), labels: { set: vi.fn() },
    onFrame: (callback: (time: number, delta: number) => boolean | void) => { callbacks.add(callback); return () => callbacks.delete(callback) },
    onResize: (callback: () => void) => { resize.add(callback); return () => resize.delete(callback) },
    setActive: (_: unknown, camera: PerspectiveCamera) => { camera.aspect = aspect; camera.updateProjectionMatrix(); resize.forEach(callback => callback()) },
  } as unknown as Engine
  const scene = new StarScene()
  scenes.push(scene)
  scene.mount(engine)
  scene.setData(data)
  scene.activate(true)
  return { scene, engine, frame: (seconds: number) => [...callbacks].map(callback => callback(seconds * 1000, seconds)), resize }
}

describe('source-backed stellar model semantics', () => {
  it('keeps unadopted binary/Y-dwarf radii unknown, with distinct temperatures for Ba and Bb', () => {
    expect(parameter(profile('eps-indi-b'), 'radius_solar')).toBeNull()
    expect(parameter(profile('wise-0855'), 'radius_solar')).toBeNull()
    expect(profile('eps-indi-b').components?.map(component => component.parameters?.teff_k.value)).toEqual([1320, 910])
    expect(visualRadius(null)).toBe(1)
    expect(visualRadius(Infinity)).toBe(1)
  })
  it('selects class-specific structures and preserves the explicitly compressed radius relationship', () => {
    expect(['barnard', 'eps-indi-b', 'wise-0855', 'rw-aur', 'r-dra'].map(id => surfaceKind(profile(id)))).toEqual(['photosphere', 'clouds', 'clouds', 'accreting', 'giant'])
    expect(visualRadius(1)).toBe(1)
    expect(visualRadius(511) / visualRadius(.187)).toBeCloseTo(Math.sqrt(511 / .187), 12)
  })
  it('places Kepler periastron and apastron at a(1-e) and a(1+e), without inventing a measured phase', () => {
    expect(Math.hypot(...keplerEllipse(0, .54042, 77.082))).toBeCloseTo(1 - .54042, 12)
    expect(Math.hypot(...keplerEllipse(Math.PI, .54042, 77.082))).toBeCloseTo(1 + .54042, 12)
    expect(keplerEllipse(2 * Math.PI, 0, 0)).toEqual([1, 0, 0])
  })
  it.each([1440 / 900, 375 / 560])('fits a large stellar envelope in both viewport dimensions (aspect %s)', aspect => {
    const radius = Math.sqrt(511) * 3.7, vertical = 43 * Math.PI / 360
    const angular = Math.asin(radius / fitDistance(radius, 43, aspect))
    expect(angular).toBeLessThan(vertical)
    expect(angular).toBeLessThan(Math.atan(Math.tan(vertical) * aspect))
  })
})

describe('stellar scene lifetime and animation', () => {
  it('keeps each binary atmosphere centred on its own component throughout animation', () => {
    const { scene, frame } = mountedScene()
    scene.update(state('eps-indi-b', { surfacePlaying: true }))
    frame(1)
    const surfaces = objectsIn(scene.scene).filter(item => item instanceof StarSurface)
    const environments = objectsIn(scene.scene).filter(item => item instanceof StarEnvironment)
    expect(surfaces).toHaveLength(2)
    expect(environments).toHaveLength(2)
    for (const surface of surfaces) expect(environments.some(environment => environment.getWorldPosition(new Vector3()).distanceTo(surface.getWorldPosition(new Vector3())) < 1e-10)).toBe(true)
    expect(surfaces[0].getWorldPosition(new Vector3()).distanceTo(surfaces[1].getWorldPosition(new Vector3()))).toBeGreaterThan(1)
    expect(new Set(environments.flatMap(environment => environment.labels.map(label => label.id))).size).toBe(environments.flatMap(environment => environment.labels).length)
  })
  it('disposes the previous disk and binary components when selecting an unprofiled catalogue star', () => {
    const { scene } = mountedScene()
    scene.update(state('rw-aur'))
    const environment = objectsIn(scene.scene).find(item => item instanceof StarEnvironment)!
    const disposed = vi.fn()
    environment.traverse(item => {
      const resource = item as typeof item & { geometry?: BufferGeometry; material?: Material }
      resource.geometry?.addEventListener('dispose', disposed)
      resource.material?.addEventListener('dispose', disposed)
    })
    scene.update(state('eps-indi-b'))
    expect(disposed).toHaveBeenCalled()
    expect(objectsIn(scene.scene)).not.toContain(environment)
    scene.setData({ ...data, models: { schema_version: 1, profiles: [] } })
    scene.update(state('barnard'))
    expect(objectsIn(scene.scene).filter(item => item instanceof StarEnvironment)).toHaveLength(0)
    expect(objectsIn(scene.scene).filter(item => item instanceof StarSurface)).toHaveLength(1)
  })
  it('hides surroundings without hiding the photosphere and freezes the visual cycle while paused', () => {
    const { scene, frame } = mountedScene()
    scene.update(state('r-dra', { surfacePlaying: true }))
    frame(1)
    const surface = objectsIn(scene.scene).find(item => item instanceof StarSurface)!
    const runningRadius = surface.scale.x
    expect(surface.surface.material.uniforms.uThermalPhase.value).toBeLessThan(0)
    scene.update(state('r-dra', { surfacePlaying:false, layers: { ...DEFAULT_STATE.layers, environment: false } }))
    const results = frame(1)
    expect(surface.visible).toBe(true)
    expect(surface.scale.x).toBe(runningRadius)
    expect(objectsIn(scene.scene).filter(item => item instanceof StarEnvironment).every(item => !item.visible)).toBe(true)
    // OrbitControls may have one settling frame; repeated idle updates must stop asking for another.
    for (let i = 0; i < 100; i++) frame(.016)
    expect(frame(.016).some(Boolean)).toBe(false)
    expect(results).toHaveLength(2)
  })
  it('does not use calendar playback to age or animate the surface', () => {
    const { scene, frame } = mountedScene()
    scene.update(state('r-dra', { playing: true, surfacePlaying: false }))
    const surface = objectsIn(scene.scene).find(item => item instanceof StarSurface)!
    const radius = surface.scale.x
    frame(1)
    scene.update(state('r-dra', { year: 2090, playing: true, surfacePlaying: false }))
    frame(1)
    expect(surface.scale.x).toBe(radius)
    expect(surface.surface.material.uniforms.uTime.value).toBe(0)
  })
  it('shows the published evolution sample without overwriting the target model', () => {
    const { scene, frame } = mountedScene()
    scene.update(state('barnard'))
    const catalogueModel = scene.scene.getObjectByName('stellar-model-barnard')!
    scene.update(state('barnard', { stellarMode: 'evolution', evolutionTrack: 'mist-1', evolutionProgress: .9 }))
    frame(.016)
    const evolved = scene.scene.getObjectByName('published-evolution-model')!
    expect(catalogueModel.visible).toBe(false)
    expect(evolved.userData.sample.age).toBeGreaterThan(1e9)
    expect(catalogueModel.userData.parameters.radius_solar.value).toBe(.187)
    scene.update(state('barnard'))
    expect(catalogueModel.visible).toBe(true)
    expect(evolved.visible).toBe(false)
  })
  it('respects reduced motion and keeps a large R Dra model inside a portrait camera', () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true }))
    const { scene, frame } = mountedScene(375 / 560)
    scene.update(state('r-dra', { surfacePlaying: true }))
    const surface = objectsIn(scene.scene).find(item => item instanceof StarSurface)!
    const initial = surface.scale.x
    frame(1)
    expect(surface.scale.x).toBe(initial)
    const distance = scene.camera.position.distanceTo(scene.controls!.orbit.target)
    expect(distance).toBeGreaterThan(Math.sqrt(511) * 3.7)
    expect(distance).toBeLessThan(scene.controls!.orbit.maxDistance)
    expect(scene.camera.position.clone().sub(scene.controls!.orbit.target).normalize().length()).toBeCloseTo(1)
  })
  it('clears all environment geometry and labels when no target is selected', () => {
    const { scene, engine } = mountedScene()
    scene.update(state('rw-aur'))
    scene.update(state('missing-target'))
    expect(objectsIn(scene.scene).filter(item => item instanceof StarEnvironment)).toHaveLength(0)
    expect(objectsIn(scene.scene).filter(item => item instanceof StarSurface)).toHaveLength(0)
    expect(engine.labels.set).toHaveBeenLastCalledWith([])
  })
  it('does not fabricate a temperature for an unknown surface during a schematic cycle', () => {
    const surface = new StarSurface('low')
    surface.setTemperature(null)
    surface.setPulsation(.8)
    const values = ['uColor', 'uCoolColor', 'uHotColor'].map(key => surface.surface.material.uniforms[key].value.toArray())
    expect(values[0]).toEqual(values[1])
    expect(values[1]).toEqual(values[2])
    expect(new Vector3(...values[0]).length()).toBeGreaterThan(0)
    disposeTree(surface)
  })
})


describe('reusable Three.js model assets', () => {
  it('faces reference circles toward the camera and scales particle sizes after loading a tilted model', () => {
    const source = createStellarModel(catalogue.targets.find(star => star.id === 'rw-aur')!, profile('rw-aur'), 'low', 'en')
    const decoded = new ObjectLoader().parse(JSON.parse(JSON.stringify(source.toJSON())))
    const camera = new PerspectiveCamera()
    camera.position.set(5, 3, 10); camera.lookAt(0, 0, 0)
    faceStellarModel(decoded, camera, 3)
    for (const name of ['surface-outline', 'solar-radius-reference']) {
      expect(decoded.getObjectByName(name)!.getWorldQuaternion(new Quaternion()).angleTo(camera.getWorldQuaternion(new Quaternion()))).toBeLessThan(1e-7)
    }
    expect(decoded.getObjectByName('solar-radius-reference')!.position.x).toBeCloseTo(source.radius + 1.6)
    const pointSizes = objectsIn(decoded).flatMap(object => {
      const material = (object as Object3D & { material?: ShaderMaterial }).material
      return material?.uniforms?.uPixelRatio ? [material.uniforms.uPixelRatio.value] : []
    })
    expect(pointSizes.length).toBeGreaterThan(0)
    expect(pointSizes.every(value => value === 2)).toBe(true)
    disposeTree(source); disposeTree(decoded)
  })
  it.each(['barnard', 'eps-indi-b', 'wise-0855', 'rw-aur', 'r-dra'])('round-trips %s geometry, materials, provenance and animation through ObjectLoader', id => {
    const source = createStellarModel(catalogue.targets.find(star => star.id === id)!, profile(id), 'low', 'en')
    const decoded = new ObjectLoader().parse(JSON.parse(JSON.stringify(source.toJSON())))
    expect(decoded.userData.target_id).toBe(id)
    expect(decoded.userData.measured_surface_map).toBe(false)
    expect(decoded.userData.sources).toEqual(profile(id).sources)
    expect(decoded.userData.parameters).toEqual(profile(id).parameters)
    expect(objectsIn(decoded).filter(object => (object as Object3D & { isMesh?: boolean }).isMesh).length).toBeGreaterThan(2)
    for (const seconds of [0, 1.5, 4, 7.5]) {
      source.update(seconds, true)
      animateStellarModel(decoded, seconds)
      for (const name of ['primary-body', 'secondary-body']) {
        const original = source.getObjectByName(name), copy = decoded.getObjectByName(name)
        expect(!!copy).toBe(!!original)
        if (copy && original) {
          expect(copy.position.toArray()).toEqual(original.position.toArray())
          expect(copy.getObjectByName('stellar-surface')!.scale.toArray()).toEqual(original.getObjectByName('stellar-surface')!.scale.toArray())
        }
      }
    }
    const originals = objectsIn(source).flatMap(object => {
      const candidate = object as Object3D & { material?: { uniforms?: Record<string, { value: unknown }> } }
      return candidate.material?.uniforms?.uThermalPhase ? [candidate.material.uniforms.uThermalPhase.value] : []
    })
    const copies = objectsIn(decoded).flatMap(object => {
      const candidate = object as Object3D & { material?: { uniforms?: Record<string, { value: unknown }> } }
      return candidate.material?.uniforms?.uThermalPhase ? [candidate.material.uniforms.uThermalPhase.value] : []
    })
    expect(copies).toEqual(originals)
    disposeTree(source); disposeTree(decoded)
  })
  it('assigns distinct structures and keeps the disk, funnels and poles in one local orientation', () => {
    const expected = { barnard: ['magnetic-arches'], 'eps-indi-b': ['cloud-veil'], 'wise-0855': ['cloud-veil'], 'rw-aur': ['accretion-funnels', 'flared-disk-skin'], 'r-dra': ['molecular-envelope'] }
    for (const [id, names] of Object.entries(expected)) {
      const model = createStellarModel(catalogue.targets.find(star => star.id === id)!, profile(id), 'low', 'en')
      for (const name of names) expect(model.getObjectByName(name)).toBeTruthy()
      if (id === 'rw-aur') {
        expect(model.rotation.x).toBeCloseTo((90 - 55.51) * Math.PI / 180, 12)
        const funnel = model.getObjectByName('accretion-funnels')!
        expect(funnel.parent?.parent).toBe(model.getObjectByName('primary-body'))
      }
      model.update(1, false)
      expect(model.surroundings.every(object => !object.visible)).toBe(true)
      expect(model.primary.visible).toBe(true)
      disposeTree(model)
    }
  })
})


describe('lifecycle environments',()=>{
 it('has distinct birth, ejection and compact-remnant structures without assigning them to brown dwarfs',()=>{
  const effects=new LifecycleEffects('low')
  effects.update('protostar',1,1);expect(effects.birth.visible).toBe(true);expect(effects.disk.visible).toBe(false)
  effects.update('planetary_nebula',.4,2,.5);expect(effects.birth.visible).toBe(false);expect(effects.shell.visible).toBe(true)
  effects.update('neutron_star',.3,3);expect(effects.compact.visible).toBe(true);expect(effects.shell.visible).toBe(false)
  effects.update('black_hole',.3,4);expect(effects.disk.visible).toBe(true);expect(effects.compact.visible).toBe(false)
  effects.update('none',.3,5);expect(effects.children.every(child=>!child.visible)).toBe(true)
  disposeTree(effects)
 })
 it('updates published properties without rewriting them and hides all illustrative surroundings on request',()=>{
  const model=new EvolutionModel('low')
  const sample={age:1e6,temperature:3700,radius:2,luminosity:1,mass:1,phase:-1,massLoss:0,index:0,endpoint:false}
  model.update(sample,4,true);expect(model.effects.birth.visible).toBe(true)
  expect(model.userData.sample).toEqual(sample)
  model.update({...sample,phase:-3},4,true);expect(model.effects.children.every(child=>!child.visible)).toBe(true)
  model.update(sample,4,false);expect(model.effects.visible).toBe(false);expect(model.surface.visible).toBe(true)
  disposeTree(model)
 })
 it('honors the application reduce-motion setting as well as the OS setting',()=>{
  const {scene,frame}=mountedScene();scene.update(state('rw-aur',{surfacePlaying:true,reducedMotion:true}));frame(1)
  const surface=objectsIn(scene.scene).find(item=>item instanceof StarSurface)!
  expect(surface.surface.material.uniforms.uTime.value).toBe(0)
 })
})

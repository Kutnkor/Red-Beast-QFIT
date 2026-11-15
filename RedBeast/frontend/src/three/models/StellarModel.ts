import { BufferGeometry, Group, Line, LineDashedMaterial, Vector3 } from 'three'
import type { Camera, Object3D } from 'three'
import type { Quality } from '../quality'
import type { LabelSpec } from '../labels'
import type { MotionStar, StellarProfile } from '../types'
import { componentParameter, hasPhenomenon, keplerEllipse, parameter, surfaceKind, visualRadius } from '../science/models'
import { StarSurface } from '../components/StarSurface'
import { StarEnvironment } from '../components/StarEnvironment'
import { tokenColor } from '../tokens'
import { translate } from '../../i18n'
import { modelRecipes } from './recipes'
import { animateStellarModel, faceStellarModel, type ModelAnimation } from './animation'

export class StellarModel extends Group {
  readonly primary: StarSurface
  readonly secondary: StarSurface | null
  readonly environments: StarEnvironment[] = []
  readonly surroundings: Object3D[] = []
  readonly labels: LabelSpec[] = []
  readonly radius: number
  readonly extent: number
  readonly detailExtent: number
  readonly animated: boolean
  constructor(star: MotionStar, profile: StellarProfile | null, quality: Quality, lang: 'tr' | 'en') {
    super()
    this.name = `stellar-model-${star.id}`
    const components = profile?.components
    const binary = !!components && components.length > 1
    const radius = componentParameter(components?.[0], 'radius_solar') ?? parameter(profile, 'radius_solar')
    this.radius = binary && radius === null ? .55 : visualRadius(radius)
    const primaryTemperature = componentParameter(components?.[0], 'teff_k') ?? parameter(profile, 'teff_k') ?? star.teff_k
    const secondaryValue = componentParameter(components?.[1], 'radius_solar')
    const secondaryRadius = binary ? (secondaryValue === null ? .55 : visualRadius(secondaryValue)) : null
    const animation: ModelAnimation = { kind: binary ? 'binary' : hasPhenomenon(profile, 'pulsation') ? 'pulsating' : 'steady', radius: this.radius,
      secondaryRadius, separation: binary ? this.radius + secondaryRadius! + 1.5 : 0,
      eccentricity: parameter(profile, 'orbital_eccentricity') ?? 0, inclinationDeg: parameter(profile, 'orbital_inclination_deg') ?? 0 }
    this.userData = {
      schema: 'blinkspace-stellar-model-v1', target_id: star.id, name: star.name, classification: 'representative',
      animation, units: 'Separate display scale: sqrt(R/R_sun); unknown radii are representative.',
      measured_surface_map: false, hydrodynamic_simulation: false, animation_time: 'illustrative_seconds_not_calendar_year',
      parameters: profile?.parameters ?? {}, components: profile?.components ?? [], sources: profile?.sources ?? [],
      caveats: profile?.caveats ?? ['No source-backed environment is adopted for this catalogue star.'],
    }
    const body = (name: string, bodyRadius: number, temperature: number | null, componentName: string) => {
      const group = new Group(); group.name = name
      const surface = new StarSurface(quality)
      surface.name = 'stellar-surface'
      surface.setTemperature(temperature); surface.setKind(surfaceKind(profile)); surface.scale.setScalar(bodyRadius)
      group.add(surface)
      if (profile) {
        const environment = new StarEnvironment(profile, bodyRadius, temperature, quality, lang, name)
        environment.name = `${name}-environment`
        this.environments.push(environment); this.surroundings.push(environment); group.add(environment)
        this.labels.push(...environment.labels)
        const recipe = modelRecipes[star.id]
        if (recipe) {
          const details = recipe({ radius: bodyRadius, temperature, quality }); details.name = `${name}-structures`
          group.add(details); this.surroundings.push(details)
          const key = star.id === 'barnard' ? 'sky.modelArches' : star.id === 'rw-aur' ? 'sky.modelFunnels' : star.id === 'r-dra' ? 'sky.modelEnvelope' : null
          if (key) this.labels.push({ id: `${name}-structure`, text: translate(lang, key), position: () => group.localToWorld(new Vector3(-bodyRadius * 1.5, bodyRadius * .7, 0)), priority: 5, kind: 'representative' })
        }
      }
      if (binary) this.labels.push({ id: `${name}-name`, text: componentName,
        position: () => group.localToWorld(new Vector3(0, bodyRadius * 1.3, 0)), priority: 10 })
      this.add(group)
      return surface
    }
    this.primary = body('primary-body', this.radius, primaryTemperature, components?.[0]?.name ?? star.name)
    this.secondary = binary ? body('secondary-body', secondaryRadius!, componentParameter(components?.[1], 'teff_k'), components![1].name) : null
    if (binary && hasPhenomenon(profile, 'binary_orbit')) {
      const guide = new Group(); guide.name = 'binary-orbit-guides'
      const points = Array.from({ length: 193 }, (_, index) => new Vector3(...keplerEllipse(index * Math.PI / 96, animation.eccentricity, animation.inclinationDeg)).multiplyScalar(animation.separation / 2))
      for (const sign of [-1, 1]) {
        const line = new Line(new BufferGeometry().setFromPoints(points.map(point => point.clone().multiplyScalar(sign))), new LineDashedMaterial({ color: tokenColor('--fg-3'), transparent: true, opacity: .55, dashSize: .06, gapSize: .04 }))
        line.computeLineDistances(); guide.add(line)
      }
      this.add(guide); this.surroundings.push(guide)
    }
    // A single local orientation keeps the disk, funnels, stellar poles and jets aligned.
    if (hasPhenomenon(profile, 'disk', 'accretion_disk')) {
      const inclination = parameter(profile, 'disk_inclination_deg')
      if (inclination !== null) this.rotation.x = (90 - inclination) * Math.PI / 180
    }
    this.extent = animation.separation / 2 * (1 + animation.eccentricity) + Math.max(...this.environments.map(environment => environment.extent), this.radius * 1.95, secondaryRadius === null ? 0 : secondaryRadius * 1.2)
    this.userData.display_extent = this.extent
    // A distant solar-size guide must not shrink a dwarf's close-up to a dot.
    this.detailExtent = binary ? animation.separation / 2 * (1 + animation.eccentricity) + this.radius * 1.4
      : this.radius * (hasPhenomenon(profile, 'disk', 'accretion_disk') ? 3.6 : 1.8)
    this.userData.display_radius = this.radius
    this.animated = this.environments.some(environment => environment.animated) || binary
    this.update(0, true)
    this.updateMatrixWorld(true)
  }
  update(seconds: number, showSurroundings: boolean): void {
    this.surroundings.forEach(object => { object.visible = showSurroundings })
    animateStellarModel(this, seconds)
  }
  faceCamera(camera: Camera, pixelRatio = 1): void { faceStellarModel(this, camera, pixelRatio) }
}

export function createStellarModel(star: MotionStar, profile: StellarProfile | null, quality: Quality = 'high', lang: 'tr' | 'en' = 'en'): StellarModel {
  return new StellarModel(star, profile, quality, lang)
}

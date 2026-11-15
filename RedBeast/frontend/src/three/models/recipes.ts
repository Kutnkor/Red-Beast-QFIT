import { Color, Group } from 'three'
import type { Quality } from '../quality'
import { temperatureToLinear } from '../science/blackbody'
import { accretionFunnels, cloudVeil, magneticArches, molecularEnvelope, thickDiskRim } from './structures'

export interface ModelRecipeContext { radius: number; temperature: number | null; quality: Quality }
function colour(context: ModelRecipeContext): Color { return new Color(...temperatureToLinear(context.temperature)) }

export function barnardModel(context: ModelRecipeContext): Group {
  const group = new Group()
  group.add(magneticArches(context.radius, colour(context), context.quality))
  return group
}
export function epsilonIndiModel(context: ModelRecipeContext): Group {
  const group = new Group()
  group.add(cloudVeil(context.radius, colour(context), context.quality, (context.temperature ?? 1000) < 1000))
  return group
}
export function wise0855Model(context: ModelRecipeContext): Group {
  const group = new Group()
  group.add(cloudVeil(context.radius, colour(context), context.quality, true))
  return group
}
export function rwAurigaeModel(context: ModelRecipeContext): Group {
  const group = new Group(), color = colour(context)
  group.add(accretionFunnels(context.radius, color, context.quality), thickDiskRim(context.radius, color, context.quality))
  return group
}
export function rDraconisModel(context: ModelRecipeContext): Group {
  const group = new Group()
  group.add(molecularEnvelope(context.radius, colour(context), context.quality))
  return group
}
export const modelRecipes: Record<string, (context: ModelRecipeContext) => Group> = {
  barnard: barnardModel, 'eps-indi-b': epsilonIndiModel, 'wise-0855': wise0855Model,
  'rw-aur': rwAurigaeModel, 'r-dra': rDraconisModel,
}

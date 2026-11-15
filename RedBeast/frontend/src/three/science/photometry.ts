export function flux(magnitude: number): number { return 10 ** (-.4 * magnitude) }
/** Display transfer only; never a measurement from a preview. */
export function displayIntensity(magnitude: number, soft = .01, brightestMagnitude = -1.5): number {
  return Math.max(0, Math.min(1, Math.asinh(flux(magnitude) / soft) / Math.asinh(flux(brightestMagnitude) / soft)))
}
export function absMag(g: number, parallaxMas: number): number {
  return parallaxMas > 0 ? g + 5 * Math.log10(parallaxMas / 100) : NaN
}

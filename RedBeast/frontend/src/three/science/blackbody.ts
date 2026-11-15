/** Port of the supplied starsim/color.py. Wyman et al. 2013, https://jcgt.org/published/0002/02/01/ */
type Lobe = [number, number, number, number]
const X: Lobe[] = [[.362, 442, .0624, .0374], [1.056, 599.8, .0264, .0323], [-.065, 501.1, .0490, .0382]]
const Y: Lobe[] = [[.821, 568.8, .0213, .0247], [.286, 530.9, .0613, .0322]]
const Z: Lobe[] = [[1.217, 437, .0845, .0278], [.681, 459, .0385, .0725]]
const MATRIX = [[3.2406, -1.5372, -.4986], [-.9689, 1.8758, .0415], [.0557, -.2040, 1.0570]]
const cache = new Map<number, [number, number, number]>()
function fit(lobes: Lobe[], wavelength: number): number {
  return lobes.reduce((sum, [amplitude, centre, below, above]) => {
    const t = (wavelength - centre) * (wavelength < centre ? below : above)
    return sum + amplitude * Math.exp(-.5 * t * t)
  }, 0)
}
export function roundTiesEven(value: number): number {
  const floor = Math.floor(value), fraction = value - floor
  return fraction === .5 ? floor + floor % 2 : Math.round(value)
}
export function srgbEncode(linear: number): number {
  return linear <= .0031308 ? 12.92 * linear : 1.055 * linear ** (1 / 2.4) - .055
}
export function srgbDecode(srgb: number): number {
  return srgb <= .04045 ? srgb / 12.92 : ((srgb + .055) / 1.055) ** 2.4
}
export function temperatureToRgb(temperature: number): [number, number, number] {
  if (!Number.isFinite(temperature) || temperature <= 0) throw new RangeError('Temperature must be finite and positive')
  const t = Math.min(40000, Math.max(1000, temperature))
  const existing = cache.get(t)
  if (existing) return [...existing]
  const xyz = [0, 0, 0]
  for (let wave = 380; wave <= 780; wave += 5) {
    const m = wave * 1e-9
    const power = 1 / (m ** 5 * Math.expm1(6.62607015e-34 * 2.99792458e8 / (m * 1.380649e-23 * t)))
    xyz[0] += power * fit(X, wave)
    xyz[1] += power * fit(Y, wave)
    xyz[2] += power * fit(Z, wave)
  }
  const linear = MATRIX.map((row) => Math.max(0, row[0] * xyz[0] + row[1] * xyz[1] + row[2] * xyz[2]))
  const peak = Math.max(...linear)
  const rgb = linear.map((value) => roundTiesEven(255 * srgbEncode(value / peak))) as [number, number, number]
  cache.set(t, rgb)
  // Animated evolution temperatures are continuous; retain a bounded working set.
  if (cache.size > 512) cache.delete(cache.keys().next().value!)
  return [...rgb]
}
export function temperatureToLinear(temperature: number | null): [number, number, number] {
  if (temperature === null) return [.35, .35, .35]
  return temperatureToRgb(temperature).map((value) => srgbDecode(value / 255)) as [number, number, number]
}

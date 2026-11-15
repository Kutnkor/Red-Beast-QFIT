import { createServer, build } from 'vite'
import { JSDOM } from 'jsdom'
import { ObjectLoader } from 'three'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { resolve, dirname } from 'node:path'
import { createHash } from 'node:crypto'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const output = resolve(root, 'public/models')
const profileBytes = await readFile(resolve(root, '../backend/blinkspace/resources/stellar_profiles.json'))
const profiles = JSON.parse(profileBytes)
const catalogue = JSON.parse(await readFile(resolve(root, '../backend/blinkspace/resources/motion_catalogue.json'), 'utf8'))
const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>', { url: 'http://models.invalid' })
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.getComputedStyle = dom.window.getComputedStyle.bind(dom.window)
const style = document.createElement('style')
style.textContent = await readFile(resolve(root, 'src/tokens.css'), 'utf8')
document.head.append(style)
const hash = value => createHash('sha256').update(value).digest('hex')
// Stable scene identifiers make repeated exports byte-for-byte reproducible.
function stableSceneJSON(value, target) {
  const uuids = new Map()
  return JSON.stringify(value).replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, uuid => {
    if (!uuids.has(uuid)) {
      const digest = hash(`${target}:${uuids.size}`)
      uuids.set(uuid, `${digest.slice(0,8)}-${digest.slice(8,12)}-5${digest.slice(13,16)}-a${digest.slice(17,20)}-${digest.slice(20,32)}`)
    }
    return uuids.get(uuid)
  }) + '\n'
}
await mkdir(output, { recursive: true })
const server = await createServer({ root, configFile: false, optimizeDeps: { noDiscovery: true, entries: [] }, server: { middlewareMode: true }, appType: 'custom' })
const manifest = { schema_version: 1, format: 'Three.js ObjectLoader JSON', three_version: '0.170.0', profile_sha256: hash(profileBytes), quality: 'low geometry / full procedural materials', snapshots: [], limitation: 'Representative geometry; no measured surface map or fluid simulation. Use animate-stellar-model.js for the illustrative animation clock.' }
try {
  const { createStellarModel } = await server.ssrLoadModule('/src/three/models/StellarModel.ts')
  const { disposeTree } = await server.ssrLoadModule('/src/three/dispose.ts')
  const { animateStellarModel } = await server.ssrLoadModule('/src/three/models/animation.ts')
  for (const profile of profiles.profiles) {
    const star = catalogue.targets.find(item => item.id === profile.target_id)
    if (!star) throw new Error(`No motion record for ${profile.target_id}`)
    const model = createStellarModel(star, profile, 'low', 'en')
    model.updateMatrixWorld(true)
    const serialized = stableSceneJSON(model.toJSON(), profile.target_id)
    const copy = new ObjectLoader().parse(JSON.parse(serialized))
    animateStellarModel(copy, 1)
    let meshes = 0, points = 0
    copy.traverse(object => {
      if (object.isMesh) meshes++
      if (object.isPoints) points++
      const position = object.geometry?.getAttribute('position')
      if (position) for (const value of position.array) if (!Number.isFinite(value)) throw new Error(`Non-finite geometry in ${profile.target_id}`)
    })
    const filename = `${profile.target_id}.three.json`
    await writeFile(resolve(output, filename), serialized)
    manifest.snapshots.push({ target_id: profile.target_id, file: filename, sha256: hash(serialized), bytes: Buffer.byteLength(serialized), meshes, point_clouds: points })
    disposeTree(copy); disposeTree(model)
  }
} finally { await server.close(); dom.window.close() }
// A portable ES module uses the same animation code as the live application.
await build({ root, configFile: false, publicDir: false, logLevel: 'warn', build: {
  outDir: output, emptyOutDir: false, minify: false,
  lib: { entry: resolve(root, 'src/three/models/animation.ts'), formats: ['es'], fileName: () => 'animate-stellar-model.js' },
  rolldownOptions: { external: ['three'] },
} })
manifest.animation_sha256 = hash(await readFile(resolve(output, 'animate-stellar-model.js')))
await writeFile(resolve(output, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n')
console.log(JSON.stringify({ models: manifest.snapshots.length, bytes: manifest.snapshots.reduce((sum, model) => sum + model.bytes, 0), object_loader_roundtrip: 'passed', files: manifest.snapshots.map(model => model.file) }))

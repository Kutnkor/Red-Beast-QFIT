import { ShaderChunk } from 'three'
import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'

// Native GLSL syntax/link validation, not a browser or GPU rendering test.
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const compiler = process.env.GLSLANG_VALIDATOR || 'glslangValidator'
const version = spawnSync(compiler, ['--version'], { encoding: 'utf8' })
if (version.error || version.status) throw new Error('Install glslang or set GLSLANG_VALIDATOR to its executable.')
const manifest = JSON.parse(await readFile(resolve(root, 'public/models/manifest.json'), 'utf8'))
function expand(source) {
  return source.replace(/#include\s+<([\w_]+)>/g, (_, name) => {
    if (!(name in ShaderChunk)) throw new Error(`Unknown Three.js shader chunk: ${name}`)
    return expand(ShaderChunk[name])
  })
}
const precision = '#version 300 es\nprecision highp float;\nprecision highp int;\n'
const vertexPrefix = `${precision}
#define attribute in
#define varying out
uniform mat4 modelMatrix;
uniform mat4 modelViewMatrix;
uniform mat4 projectionMatrix;
uniform mat4 viewMatrix;
uniform mat3 normalMatrix;
attribute vec3 position;
attribute vec3 normal;
attribute vec2 uv;
`
const fragmentPrefix = `${precision}
#define varying in
layout(location = 0) out highp vec4 pc_fragColor;
#define gl_FragColor pc_fragColor
#define TONE_MAPPING
${ShaderChunk.tonemapping_pars_fragment}
vec3 toneMapping(vec3 color) { return ACESFilmicToneMapping(color); }
${ShaderChunk.colorspace_pars_fragment}
vec4 linearToOutputTexel(vec4 value) { return sRGBTransferOETF(value); }
`
const temp = await mkdtemp(resolve(tmpdir(), 'blinkspace-glsl-'))
const checked = new Map(), targets = []
try {
  for (const snapshot of manifest.snapshots) {
    const model = JSON.parse(await readFile(resolve(root, 'public/models', snapshot.file), 'utf8'))
    const hashes = new Set()
    for (const material of model.materials ?? []) {
      if (material.type !== 'ShaderMaterial') continue
      const hash = createHash('sha256').update(material.vertexShader + '\n' + material.fragmentShader).digest('hex')
      hashes.add(hash)
      if (checked.has(hash)) continue
      const vertex = resolve(temp, `${hash}.vert`), fragment = resolve(temp, `${hash}.frag`)
      await writeFile(vertex, vertexPrefix + expand(material.vertexShader))
      await writeFile(fragment, fragmentPrefix + expand(material.fragmentShader))
      const check = spawnSync(compiler, ['-l', vertex, fragment], { encoding: 'utf8' })
      if (check.error || check.status) throw new Error(`${snapshot.target_id}: ${check.stderr}\n${check.stdout}`)
      checked.set(hash, { sha256: hash, linked: true })
    }
    targets.push({ target_id: snapshot.target_id, programs: hashes.size, passed: true })
  }
} finally { await rm(temp, { recursive: true, force: true }) }
const report = {
  method: 'Native glslang GLSL ES 3.00 parse and vertex/fragment link; Three.js r170 chunks with ACES and sRGB output.',
  compiler: version.stdout.split('\n')[0], unique_programs: checked.size, targets, programs: [...checked.values()],
  browser_or_gpu_rendering_verified: false,
  limitation: 'Does not exercise a WebGL driver, pixel output, frame rate or visual appearance.',
}
await writeFile(resolve(root, '../reports/model-shaders.json'), JSON.stringify(report, null, 2) + '\n')
console.log(JSON.stringify({ unique_programs: checked.size, targets: targets.length, native_shader_link: 'passed', gpu_rendering: 'not tested' }))

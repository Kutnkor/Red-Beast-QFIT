export function hasWebGL2(): boolean {
  try {
    const canvas = document.createElement('canvas')
    const gl = canvas.getContext('webgl2')
    gl?.getExtension('WEBGL_lose_context')?.loseContext()
    return !!gl
  } catch { return false }
}
export function hasWebGL(): boolean {
  try { return !!document.createElement('canvas').getContext('webgl') } catch { return false }
}

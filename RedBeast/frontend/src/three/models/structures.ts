import { AdditiveBlending, BufferGeometry, CatmullRomCurve3, Color, DoubleSide, Float32BufferAttribute, Group, Mesh, ShaderMaterial, SphereGeometry, TubeGeometry, Vector3 } from 'three'
import type { Quality } from '../quality'

/** Geometric illustrations only. No field topology, density or velocity is measured here. */
function flowMaterial(color: Color, speed: number, opacity: number): ShaderMaterial {
  return new ShaderMaterial({ transparent: true, depthWrite: false, blending: AdditiveBlending, side: DoubleSide,
    uniforms: { uColor: { value: color }, uTime: { value: 0 }, uSpeed: { value: speed }, uOpacity: { value: opacity } },
    vertexShader: `varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
    fragmentShader: `uniform vec3 uColor; uniform float uTime; uniform float uSpeed; uniform float uOpacity; varying vec2 vUv;
      void main(){float packets=pow(0.5+0.5*cos((vUv.x-uTime*uSpeed)*37.6991),5.0);
        float crossSection=0.5+0.5*sin(vUv.y*6.283185);
        gl_FragColor=vec4(uColor,(0.13+0.87*packets)*uOpacity*crossSection);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  })
}

export function magneticArches(radius: number, color: Color, quality: Quality): Group {
  const group = new Group()
  group.name = 'magnetic-arches'
  group.userData = { classification: 'representative', phenomenon: 'corona', measured_field_map: false }
  const count = quality === 'low' ? 8 : 14
  const material = flowMaterial(color, .035, .24)
  for (let i = 0; i < count; i++) {
    const azimuth = i * Math.PI * (3 - Math.sqrt(5)), height = 1.45 + .45 * ((i % 4) / 3)
    // A dipole-like arch r = L sin²(theta), truncated where it meets the photosphere.
    const foot = Math.asin(Math.sqrt(1.025 / height))
    const points = Array.from({ length: 49 }, (_, j) => {
      const theta = foot + (Math.PI - 2 * foot) * j / 48, r = radius * height * Math.sin(theta) ** 2
      return new Vector3(r * Math.sin(theta) * Math.cos(azimuth), r * Math.cos(theta), r * Math.sin(theta) * Math.sin(azimuth))
    })
    group.add(new Mesh(new TubeGeometry(new CatmullRomCurve3(points), quality === 'low' ? 36 : 64, radius * .009, 5, false), material))
  }
  return group
}

export function accretionFunnels(radius: number, color: Color, quality: Quality): Group {
  const group = new Group()
  group.name = 'accretion-funnels'
  group.userData = { classification: 'representative', phenomenon: 'accretion', measured_field_map: false }
  const material = flowMaterial(color, .06, .3)
  for (const pole of [-1, 1]) for (let i = 0; i < 3; i++) {
    const azimuth = i * Math.PI * 2 / 3 + .3
    const points = Array.from({ length: 49 }, (_, j) => {
      const t = j / 48, theta = Math.PI / 2 - t * (Math.PI / 2 - .72)
      const r = radius * 2.35 * Math.sin(theta) ** 2
      const twist = azimuth + .28 * t
      return new Vector3(r * Math.sin(theta) * Math.cos(twist), pole * r * Math.cos(theta), r * Math.sin(theta) * Math.sin(twist))
    })
    group.add(new Mesh(new TubeGeometry(new CatmullRomCurve3(points), quality === 'low' ? 32 : 64, radius * .025, 6, false), material))
  }
  return group
}

/** Layered, nonuniform cloud opacity with latitude-dependent advection. */
export function cloudVeil(radius: number, color: Color, quality: Quality, cold: boolean): Mesh<SphereGeometry, ShaderMaterial> {
  const material = new ShaderMaterial({ transparent: true, depthWrite: false,
    uniforms: { uColor: { value: color }, uTime: { value: 0 }, uOpacity: { value: cold ? .028 : .15 } },
    vertexShader: `varying vec3 vLocal; varying vec3 vNormal; varying vec3 vView;
      void main(){ vLocal=normalize(position); vec4 p=modelViewMatrix*vec4(position,1.0); vNormal=normalize(normalMatrix*normal); vView=-p.xyz; gl_Position=projectionMatrix*p; }`,
    fragmentShader: `uniform vec3 uColor; uniform float uTime; uniform float uOpacity; varying vec3 vLocal; varying vec3 vNormal; varying vec3 vView;
      void main(){float longitude=atan(vLocal.z,vLocal.x)-uTime*(0.023+0.008*vLocal.y*vLocal.y);
        float ribbons=sin(vLocal.y*35.0+1.2*sin(longitude*4.0)+0.5*sin(longitude*9.0+vLocal.y*14.0));
        float patches=0.5+0.5*sin(longitude*13.0+vLocal.y*29.0)*sin(longitude*7.0-vLocal.y*17.0);
        float mu=max(0.0,dot(normalize(vNormal),normalize(vView)));
        float density=smoothstep(-0.05,0.7,ribbons)*(0.3+0.7*patches);
        gl_FragColor=vec4(uColor*(0.55+0.45*mu),uOpacity*density);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  })
  const cloud = new Mesh(new SphereGeometry(radius * 1.018, quality === 'low' ? 48 : 96, quality === 'low' ? 32 : 64), material)
  cloud.name = 'cloud-veil'
  cloud.userData = { classification: 'representative', phenomenon: 'clouds', resolved_map: false }
  return cloud
}

export function molecularEnvelope(radius: number, color: Color, quality: Quality): Group {
  const group = new Group()
  group.name = 'molecular-envelope'
  group.userData = { classification: 'representative', phenomenon: 'pulsation', fitted_density: false }
  const material = new ShaderMaterial({ transparent: true, depthWrite: false, blending: AdditiveBlending,
    uniforms: { uColor: { value: color }, uTime: { value: 0 } },
    vertexShader: `varying vec3 vLocal; varying vec3 vNormal; varying vec3 vView;
      uniform float uTime; void main(){vLocal=normalize(position); float bulge=1.0+0.025*sin(uTime*0.7854+vLocal.y*3.0);
        vec4 p=modelViewMatrix*vec4(position*bulge,1.0); vNormal=normalize(normalMatrix*normal);vView=-p.xyz;gl_Position=projectionMatrix*p;}`,
    fragmentShader: `varying vec3 vLocal; varying vec3 vNormal; varying vec3 vView; uniform vec3 uColor; uniform float uTime;
      void main(){float mu=max(0.0,dot(normalize(vNormal),normalize(vView)));
        float clumps=0.5+0.5*sin(vLocal.x*12.0+sin(vLocal.z*9.0))*cos(vLocal.y*11.0);
        float density=pow(1.0-mu,1.8)*(0.025+clumps*0.09);
        gl_FragColor=vec4(uColor,density);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  })
  for (const multiplier of [1.14, 1.38]) {
    const geometry = new SphereGeometry(radius * multiplier, quality === 'low' ? 48 : 80, quality === 'low' ? 32 : 56)
    const positions = geometry.getAttribute('position')
    for (let i = 0; i < positions.count; i++) {
      const x = positions.getX(i) / radius, y = positions.getY(i) / radius, z = positions.getZ(i) / radius
      const irregularity = 1 + .025 * Math.sin(x * 5 + z * 3) * Math.cos(y * 4 - z * 6)
      positions.setXYZ(i, x * radius * irregularity, y * radius * irregularity, z * radius * irregularity)
    }
    geometry.computeVertexNormals()
    // Bake the edited vertices so ObjectLoader never reconstructs an unmodified parametric sphere.
    const baked = new BufferGeometry().copy(geometry)
    geometry.dispose()
    group.add(new Mesh(baked, material))
  }
  return group
}

export function thickDiskRim(radius: number, color: Color, quality: Quality): Mesh<BufferGeometry, ShaderMaterial> {
  const segments = quality === 'low' ? 80 : 160, radialSteps = 12
  const positions: number[] = [], uvs: number[] = [], indices: number[] = []
  for (let j = 0; j <= radialSteps; j++) for (let i = 0; i <= segments; i++) {
    const azimuth = i / segments * Math.PI * 2, radial = 1.3 + 1.95 * j / radialSteps
    // A flared upper disk skin; its thickness and corrugation are illustrative.
    positions.push(Math.cos(azimuth) * radial * radius, radius * (.045 + .035 * radial ** 1.4) * (1 + .12 * Math.sin(azimuth * 3 + radial)), Math.sin(azimuth) * radial * radius)
    uvs.push(i / segments, j / radialSteps)
    if (j < radialSteps && i < segments) {
      const a = j * (segments + 1) + i, b = a + segments + 1
      indices.push(a, b, a + 1, b, b + 1, a + 1)
    }
  }
  const geometry = new BufferGeometry()
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3))
  geometry.setAttribute('uv', new Float32BufferAttribute(uvs, 2))
  geometry.setIndex(indices); geometry.computeVertexNormals()
  const material = flowMaterial(color, .008, .12)
  const rim = new Mesh(geometry, material)
  rim.name = 'flared-disk-skin'
  rim.userData = { classification: 'representative', phenomenon: 'disk', fitted_density: false }
  return rim
}

import { AdditiveBlending, Color, DoubleSide, Group, Mesh, RingGeometry, ShaderMaterial, SphereGeometry, ConeGeometry } from 'three'
import type { Quality } from '../quality'
import { accretionFunnels, magneticArches, thickDiskRim } from './structures'

/** Morphology and flow are educational illustrations, never fitted gas or magnetic fields. */
export class LifecycleEffects extends Group {
  readonly birth = new Group()
  readonly corona: Group
  readonly shell: Mesh<SphereGeometry, ShaderMaterial>
  readonly compact = new Group()
  readonly disk: Mesh<RingGeometry, ShaderMaterial>
  constructor(quality: Quality) {
    super()
    this.name = 'illustrative-lifecycle-environment'
    this.userData.classification = 'illustrative_not_hydrodynamics'
    this.birth.add(thickDiskRim(1, new Color('#f5a569'), quality), accretionFunnels(1, new Color('#9bcfff'), quality))
    this.birth.rotation.set(.35, 0, .25)
    this.corona = magneticArches(1, new Color('#ffc789'), quality)
    this.shell = new Mesh(new SphereGeometry(1, quality === 'low' ? 40 : 80, 48), new ShaderMaterial({
      transparent: true, depthWrite: false, side: DoubleSide, blending: AdditiveBlending,
      uniforms: { uTime: { value: 0 }, uProgress: { value: 0 }, uExplosion: { value: 0 } },
      vertexShader: `varying vec3 vLocal,vNormal,vView; uniform float uTime,uExplosion;
        void main(){vLocal=normalize(position); float ripple=1.0+0.045*sin(vLocal.x*16.0+sin(vLocal.z*13.0)+uTime*.12);
        vec3 p=position*ripple; p.y*=mix(1.35,1.0,uExplosion);
        vec4 view=modelViewMatrix*vec4(p,1.0);vNormal=normalize(normalMatrix*normal);vView=-view.xyz;gl_Position=projectionMatrix*view;}`,
      fragmentShader: `varying vec3 vLocal,vNormal,vView;uniform float uTime,uProgress,uExplosion;
        float hash(vec3 p){return fract(sin(dot(p,vec3(127.1,311.7,74.7)))*43758.5453);}
        float noise(vec3 p){vec3 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);
          return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z);}
        void main(){float limb=pow(1.0-abs(dot(normalize(vNormal),normalize(vView))),1.5);
        vec3 drift=vec3(0.0,uTime*.018,uTime*.012);
        float cloud=noise(vLocal*6.0+drift);
        float detail=noise(vLocal*18.0+vec3(cloud)*3.0+drift);
        float filaments=smoothstep(.22,.8,cloud*.65+detail*.35);
        vec3 nebula=mix(vec3(.08,.62,1.0),vec3(1.0,.18,.08),clamp(.5+vLocal.y*.5+(cloud-.5)*.8,0.0,1.0));
        vec3 color=mix(nebula,vec3(1.0,.43,.14),uExplosion);
        gl_FragColor=vec4(color,(.06+.3*limb)*(.12+.88*filaments)*(1.0-.45*uProgress));
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
        }`,
    }))
    const beamMaterial = new ShaderMaterial({ transparent: true, depthWrite: false, side: DoubleSide, blending: AdditiveBlending,
      uniforms: { uTime: { value: 0 } },
      vertexShader: `varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
      fragmentShader: `varying vec2 vUv;uniform float uTime;void main(){float ray=pow(.5+.5*cos(vUv.x*6.28318),3.0);float flow=.65+.35*sin(vUv.y*24.0-uTime*2.0);gl_FragColor=vec4(.25,.64,1.0,ray*flow*.22*pow(sin(vUv.y*3.14159),.7));
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
    })
    for (const sign of [-1,1]) {
      const beam = new Mesh(new ConeGeometry(.36,2.4,32,1,true),beamMaterial)
      beam.position.y=sign*1.5;beam.rotation.z=sign>0?Math.PI:0;this.compact.add(beam)
    }
    this.disk = new Mesh(new RingGeometry(1.4,4,quality==='low'?80:160,24),new ShaderMaterial({
      transparent:true,depthWrite:false,side:DoubleSide,blending:AdditiveBlending,
      uniforms:{uTime:{value:0}},
      vertexShader:`varying vec3 vLocal;void main(){vLocal=position;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
      fragmentShader:`varying vec3 vLocal;uniform float uTime;void main(){float radius=length(vLocal.xy);float r=clamp((radius-1.4)/2.6,0.0,1.0);float angle=atan(vLocal.y,vLocal.x);float lanes=.65+.35*sin(radius*34.0+angle*3.0-uTime*.8);float arc=.6+.4*cos(angle);vec3 color=mix(vec3(1.0,.87,.61),vec3(.8,.16,.025),r);gl_FragColor=vec4(color,lanes*arc*pow(1.0-r,1.2)*smoothstep(0.0,.12,r)*.8);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
    }))
    this.disk.rotation.x=1.1
    this.add(this.birth,this.corona,this.shell,this.compact,this.disk)
  }
  update(phase: string, radius: number, time: number, progress = 0, enabled = true) {
    this.visible=enabled
    this.birth.visible=phase==='protostar'
    this.corona.visible=phase==='main_sequence'
    this.shell.visible=['planetary_nebula','supernova'].includes(phase)
    this.compact.visible=phase==='neutron_star'
    this.disk.visible=phase==='black_hole'
    this.birth.scale.setScalar(radius);this.birth.rotation.y=time*.025
    this.corona.scale.setScalar(radius);this.corona.rotation.y=time*.025
    // Nebular/compact surroundings use a separate schematic scale, labelled in the UI.
    this.shell.scale.setScalar(phase==='supernova'?Math.max(radius*1.18,1.7+progress*1.3):Math.max(radius*1.65,1.9+progress*1.1))
    this.shell.material.uniforms.uProgress.value=progress
    this.shell.material.uniforms.uExplosion.value=phase==='supernova'?1:0
    this.compact.rotation.set(.35,time*.6,.45)
    this.disk.scale.setScalar(Math.max(.35,radius))
    this.traverse(object=>{
      const material=(object as typeof object & {material?:ShaderMaterial}).material
      if(material?.uniforms?.uTime)material.uniforms.uTime.value=time
    })
  }
}

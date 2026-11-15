# BlinkSpace — Five Three.js stellar models

Beş model uygulamaya entegredir. Yıldız görünümünde bir hedef seçin; **Three.js modelini indir** bağlantısı seçili model dosyasını verir. Oynat/duraklat düğmesi temsili hareketi de kontrol eder. Çevre katmanını kapatmak yıldız yüzeyini gizlemez.

| Dosya | İçerik |
|---|---|
| `barnard.three.json` | Kaynaklı sıcaklık/yarıçap, granüllü yüzey, korona, manyetik yaylar ve rüzgâr izleri |
| `eps-indi-b.three.json` | Ba/Bb için iki ayrı sıcaklık, bulut katmanları ve temsili ikili yörünge |
| `wise-0855.three.json` | Çok soğuk cisim için karanlık görünür-ışık temsili, bulut şeritleri ve ince atmosfer |
| `rw-aur.three.json` | Birikim diski, kalınlaşan disk yüzeyi, yıldıza madde akışı ve iki kutuplu jet izleri |
| `r-dra.three.json` | Büyük konveksiyon hücreleri, düzensiz moleküler katmanlar, gaz çıkışı ve renk/boyut döngüsü |

Dosyalar **Three.js r170 ObjectLoader JSON** biçimindedir. Geometri, malzeme, gömülü doku, kaynak bağlantıları ve belirsizlik notları birlikte bulunur. GLB/FBX veya Unity projesi değildir. Ayrı bir görüntü dosyası indirilmez.

Modelin fiziksel parametreleri `userData.parameters`, kaynakları `userData.sources`, sınırlamaları `userData.caveats` içindedir. Manyetik alan çizgilerinin şekli, bulut haritası, akış hızı/yoğunluğu ve titreşim genliği temsili çizimlerdir; bunlar gözlenmiş yüzey haritaları veya çözülmüş akışkan denklemleri değildir. Takvim katalogdaki konum değişimini yönetir; aşağıdaki animasyon saati yıldızın gelecekteki evrimini hesaplamaz. Boyutlar ayrı ve sıkıştırılmış gösterim ölçeğindedir.

## Başka bir Three.js projesinde kullanma

`three@0.170.0` kullanan bir projeye dosyaları kopyalayın. JSON'u bir yerel web sunucusundan yükleyin. `animate-stellar-model.js` mevcut projenizdeki `three` paketini kullanır; ikinci bir Three kopyası içermez.

```js
import * as THREE from 'three'
import { animateStellarModel, faceStellarModel } from './animate-stellar-model.js'

const model = await new THREE.ObjectLoader().loadAsync('/models/rw-aur.three.json')
scene.add(model)

renderer.toneMapping = THREE.ACESFilmicToneMapping
renderer.outputColorSpace = THREE.SRGBColorSpace
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))

// display_extent includes the shader-driven outflow, which Box3 cannot infer.
const extent = model.userData.display_extent
const vertical = THREE.MathUtils.degToRad(camera.fov / 2)
const horizontal = Math.atan(Math.tan(vertical) * camera.aspect)
camera.position.set(0, 0, extent * 1.15 / Math.sin(Math.min(vertical, horizontal)))
camera.far = camera.position.length() + extent * 4
camera.lookAt(0, 0, 0)
camera.updateProjectionMatrix()

let seconds = 0
const clock = new THREE.Clock()
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
let playing = true // connect this to your own play/pause control
renderer.setAnimationLoop(() => {
  const delta = Math.min(clock.getDelta(), 0.1)
  if (playing && !reducedMotion.matches) seconds += delta
  animateStellarModel(model, seconds)
  faceStellarModel(model, camera, renderer.getPixelRatio())
  renderer.render(scene, camera)
})
```

Sahne, kamera ve renderer mevcut uygulamanızdan gelir. Modeli kaldırırken geometri, malzeme ve doku kaynaklarını serbest bırakın. BlinkSpace'in kendi sahnesi bunu hedef değişiminde yapar ve duraklatılmış görünümde sürekli çizim istemez.

## Yeniden üretme ve doğrulama

Tam kaynak projesinin `frontend` klasöründe `npm run models:export` komutu aynı canlı model fabrikasından beş dosyayı ve animasyon modülünü yeniden üretir. `manifest.json` dosya SHA-256 değerlerini ve kaynak profilinin hash'ini içerir. Sabit kimlikler tekrar üretimi bayt düzeyinde karşılaştırılabilir kılar.

ObjectLoader ile yeniden yükleme, kaynak bilgisinin korunması, animasyon, duraklatma, çevre katmanı, bellek kaynaklarının bırakılması ve kamera ölçekleri otomatik testlerle kontrol edilir. İsteğe bağlı `npm run models:check-shaders` yerel `glslangValidator` gerektirir ve shader sözdizimi/bağlantısını denetler. Bu kontroller görsel WebGL/GPU kabul testi değildir; tarayıcı görsel kontrolü henüz tamamlanmamıştır.

Kod ve oluşturulan geometri: `LICENSE`. Three.js kaynak bildirimi: `THREE-LICENSE.txt`. Bilimsel kaynaklar modelin içinde korunur; NASA bu uygulamayı geliştirmemiş veya onaylamamıştır.

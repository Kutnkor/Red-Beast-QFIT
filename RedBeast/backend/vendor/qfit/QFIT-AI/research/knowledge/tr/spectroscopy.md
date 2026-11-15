---
id: spectroscopy
title: SPHEREx verisinde tayfölçüm, parlaklık ve birimler
language: tr
topic: spectroscopy
version: 1
translation_of: en/spectroscopy.md
---
## Tayfölçüm (spektroskopi)
Tayfölçüm, bir prizmanın güneş ışığından gökkuşağı oluşturması gibi ışığı dalga boylarına ayırır. Gözün renk olarak gördüğü şey farklı dalga boylarıdır. SPHEREx yakın kızılötesinde, 0.75-5.0 mikron arasında, görünür ışığın kırmızı ucunun ötesinde çalışır.
Kaynaklar: jpl-spherex-presskit, spherex-goals

## Çözme gücü
Tayfsal çözme gücü R, dalga boyunun ayırt edilebilen en küçük dalga boyu farkına oranıdır: R = lambda / delta-lambda; birimsizdir. SPHEREx'in çözme gücü 1-4 arası bantlarda 35 ile 41 arasında, 5. ve 6. bantlarda 112 ve 128'dir. R yaklaşık 40 iken 1.4 mikrondaki bir kanal yaklaşık 0.035 mikron genişliğindedir. Bu düşük çözünürlüktür: geniş molekül soğurma bantları görülebilir, dar çizgiler ayrılamaz.
Kaynaklar: irsa-sia, spherex-data-products

## Yüzey parlaklığı akı değildir
SPHEREx Tayfsal Görüntüleri yüzey parlaklığını megajansky bölü steradyan (MJy/sr) cinsinden verir: gökyüzünün birim alanı başına parlaklık. Bir kaynağın akısını elde etmek için piksel değerleri bir açıklık üzerinde toplanmalı, arka plan çıkarılmalı ve sonuç bir pikselin katı açısıyla çarpılmalıdır. IRSA'nın eğitim defteri bunu açıklık fotometrisiyle yapar, milijansky'ye çevirir ve yöntemin görselleştirme amaçlı olduğunu belirtir; bilimsel kullanım için IRSA'nın SPHEREx Spectrophotometry Tool aracını önerir. Q-FIT'in okuduğu tek bir piksel değeri, içinde hâlâ zodyak ışığı bulunan ham bir okumadır. Cismin akısı değildir.
Kaynaklar: spherex-data-products, irsa-tutorial-hips

## Işıtma gücü ve akı
Işıtma gücü (lüminozite), bir yıldızın saniyede yaydığı toplam enerjidir; yıldızın kendi özelliğidir. Akı, gözlemcinin birim alanda saniyede aldığı enerjidir; bu yüzden ışıtma gücünün yanında uzaklığa da bağlıdır. Ölçülen bir akıyı ışıtma gücüne çevirmek için uzaklık gerekir.
Kaynaklar: chandra-hr, atnf-hr-classifying
Verification: akı tanımı standart fiziktir ve atıf yapılan sayfalarda yer almaz; atıf gerekli.

## Soğuk atmosferlerdeki moleküller
Kahverengi cüceler gibi soğuk cisimlerin atmosferlerinde, kızılötesi ışığı belirli dalga boylarında soğuran moleküller bulunur. Ekip, kahverengi cücelerin SPHEREx tayflarında su, karbondioksit, karbonmonoksit ve metan izleri bildirmektedir; bu izler sıcaklığa bağlı olarak cisimden cisme değişir.
Kaynaklar: nasa-spherex-brown-dwarfs

---
id: spherex-data-products
title: SPHEREx veri ürünleri ve sürümleri
language: tr
topic: spherex_data
mission: SPHEREx
data_release: DR1, QR3
version: 1
translation_of: en/spherex-data-products.md
---
## Tayfsal Görüntü (Spectral Image, Seviye 2)
SPHEREx'in temel bilim ürünü Tayfsal Görüntüdür (Spectral Image); yaklaşık 70 MB boyutunda çok uzantılı bir FITS dosyasıdır. Her gökyüzü yönelimi için dedektör başına bir dosya vardır. Altı uzantısı bulunur: IMAGE (MJy/sr cinsinden kalibre yüzey parlaklığı, 2040 x 2040 piksel, zodyak ışığı çıkarılmamış), FLAGS (piksel başına durum bitleri), VARIANCE (IMAGE değerlerinin (MJy/sr)^2 cinsinden varyansı), ZODI (zodyak arka planının modeli, IMAGE'dan çıkarılmamış), EPSF (bölgelere ayrılmış nokta dağılım fonksiyonları; QR2'de adı PSF) ve WCS-WAVE (piksel konumundan merkez dalga boyuna ve bant genişliğine arama tablosu). Her gözlemde altı dedektörün hepsi bulunmayabilir.
Kaynaklar: spherex-data-products

## Tayfsal görüntü bir tayf değildir
Her dedektör doğrusal değişken bir filtrenin (LVF) arkasındadır; bu yüzden tek bir Tayfsal Görüntü içinde dalga boyu piksel konumuna göre değişir. Dolayısıyla tek bir pozlama, belirli bir gökyüzü konumu için bir tayf değil tek bir dalga boyu verir. Bir kaynağın tayfı, kaynağın dedektörlerin farklı yerlerine düştüğü çok sayıda pozlamadan birleştirilir. WCS-WAVE tablosu görselleştirme içindir; IRSA bilimsel kullanım için Spectral WCS kalibrasyon ürününün merkez dalga boyu (CWAVE) ve bant genişliği (CBAND) uzantılarının kullanılmasını söyler.
Kaynaklar: spherex-data-products, irsa-tutorial-intro

## Altı dedektör bandı
Bant 1: 0.75-1.09 mikron, çözme gücü 39. Bant 2: 1.10-1.62 mikron, R 41. Bant 3: 1.63-2.41 mikron, R 41. Bant 4: 2.42-3.82 mikron, R 35. Bant 5: 3.83-4.41 mikron, R 112. Bant 6: 4.42-5.00 mikron, R 128. Dedektörler 1'den 6'ya numaralanır ve her Tayfsal Görüntü tek bir dedektörü kapsar.
Kaynaklar: spherex-data-products

## Tüm Gökyüzü Küpü (All-Sky Cube)
Tüm Gökyüzü Küpü yalnızca Data Release 1'de vardır. DR1 Tayfsal Görüntülerinden üretilir ve tüm gökyüzünü, her biri yaklaşık 1.8 x 1.8 derece olan 12.288 HEALPix karosuyla (order 5, NESTED) kaplar. Bir karoda 12.9 yay saniyelik 512 x 512 piksel ve 102 tayf kanalı bulunur (altı dedektörün her birinden 1-17 arası kanallar). IMAGE uzantısı, zodyak ışığı çıkarılmış MJy/sr cinsinden yüzey parlaklığıdır. IRSA'nın belirttiği bilinen sorunlar: 51 ve 52 numaralı kanallar veri içermez, 1.083 mikron helyum çizgisi gibi atmosfer salması şeritler oluşturur ve HPX izdüşümü birçok FITS görüntüleyicide bozuk görünür.
Kaynaklar: spherex-data-products, spherex-dr1

## Sürümler
IRSA şu sürümleri listeler: Temmuz 2025'te ilk Quick Release, Ekim 2025'te yeniden işlenmiş Quick Release 2 (QR2), Eylül 2026'da Quick Release 3 (QR3) ve Kasım 2026'da Data Release 1 (DR1). DR1 Tayfsal Görüntüleri QR2 görüntülerinin yeniden işlenmiş hâlidir ve QR3 ile birlikte, aynı biçimde işlenmiş tek bir küme olarak kullanılmak üzere hazırlanmıştır. QR2 artık SIA2 servisiyle aranamaz, ancak Şubat 2027'ye kadar indirilebilir. DR1 ve QR3 için, QR2 verisini (eski kazanç) QR3 verisiyle (yeni kazanç) birleştirmeye yarayan bir Flux Corrections kalibrasyon ürünü vardır; bu yüzden farklı sürümlerden gelen parlaklık değerleri bu kontrol yapılmadan doğrudan karşılaştırılmamalıdır.
Kaynaklar: irsa-spherex, spherex-dr1, spherex-data-access, spherex-data-products

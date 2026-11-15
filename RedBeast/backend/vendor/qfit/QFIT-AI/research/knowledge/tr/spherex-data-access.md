---
id: spherex-data-access
title: SPHEREx verisi nasıl bulunur ve alınır
language: tr
topic: data_access
mission: SPHEREx
data_release: DR1, QR3
version: 1
translation_of: en/spherex-data-access.md
---
## Arşivde arama
SPHEREx verisini NASA/IPAC Infrared Science Archive (IRSA) sunar. Q-FIT aramayı IVOA Simple Image Access v2 (SIA2) servisiyle yapar; bu servis, ayak izi gökyüzündeki bir daireyle kesişen her görüntüyü döndürür. Aranabilir koleksiyonlar şunlardır: spherex_dr1 ve spherex_qr3 (geniş tarama), spherex_dr1_deep ve spherex_qr3_deep (derin tarama) ve spherex_dr1_cube (Tüm Gökyüzü Küpü karoları). Yeni pozlamalar SIA2'de, IRSA'nın diğer arayüzlerinde göründükten yaklaşık bir gün sonra görünür.
Kaynaklar: spherex-data-access, irsa-sia

## Bir arşiv kaydı ne söyler
Bir arşiv kaydı tek bir dosyayı tanımlar: gözlem kimliği, koleksiyon, dedektör bandı, başlangıç ve bitiş zamanı (Değiştirilmiş Jülyen Tarihi, MJD), pozlama süresi, metre cinsinden dalga boyu sınırları, çözme gücü, görüntü merkezi, görüş alanı ve indirme adresi. Q-FIT'in incelediği kayıtlarda bir Tayfsal Görüntünün görüş alanı yaklaşık 3.5 derece, piksel ölçeği 6.15 yay saniyesi ve pozlama süresi yaklaşık 113.6 saniyedir. Görüntü merkezi, aradığınız cismin konumu değildir; cisim görüntünün herhangi bir yerinde olabilir.
Kaynaklar: irsa-live-query, irsa-tutorial-intro

## Kesitler (cutout)
IRSA'nın kesit servisi, dosyanın kurum içi adresine "?center=RA,Dec&size=BOYUT" (derece) eklendiğinde Tayfsal Görüntünün küçük bir parçasını döndürür. Kesit tüm uzantıları korur; IMAGE, FLAGS, VARIANCE ve ZODI kırpılır, dalga boyu tablosu kesite göre yeniden eşlenir.
Kaynaklar: spherex-data-access, spherex-data-products

## Katalog eşleşmesi gözlem demek değildir
Bir cismin SIMBAD'da veya JPL Horizons'ta bulunması, cismin kataloglandığını gösterir. SPHEREx'in onu gözlediğini göstermez. Bunu yalnızca, o konumu kapsayan dosyalar döndüren bir arşiv sorgusu ortaya koyar; o durumda bile dosyalar konumun görüntülendiğini gösterir, cismin görüntüde saptandığını değil.
Kaynaklar: qfit-spec

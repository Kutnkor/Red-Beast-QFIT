---
id: temporal-coverage
title: Zaman kapsamı ve SPHEREx gözlemlerinin karşılaştırılması
language: tr
topic: temporal_analysis
mission: SPHEREx
version: 1
translation_of: en/temporal-coverage.md
---
## Tarama sıklığı
SPHEREx nominal 25 aylık görevinde tüm gökyüzünü dört kez haritalar; dolayısıyla tipik bir gökyüzü konumu yaklaşık altı ayda bir yeniden gözlenir. Bir ziyaret sırasında konum, zamanca birbirine yakın birkaç pozlamayla kapsanır; çünkü teleskop gökyüzünde adım adım ilerler ve konum farklı dedektörlerin üzerinden geçer.
Kaynaklar: spherex-goals, spherex-about, irsa-live-query

## Düzgün aralıklı bir zaman serisi yoktur
Bir gökyüzü konumunun pozlamaları, uzun boşluklarla ayrılmış ziyaretler hâlinde kümelenir. Eşit aralıklı değildir. Bir zaman çizelgesi gerçek pozlama zamanlarını göstermeli ve boşlukları boş bırakmalıdır; boşluk "gözlenmedi" demektir, asla "değişim yok" demek değildir. Derin tarama alanları, tipik geniş tarama konumlarından çok daha sık gözlenir.
Kaynaklar: spherex-data-access, qfit-spec

## İki pozlama nadiren aynı dalga boyundadır
Dalga boyu, konumun dedektörde nereye düştüğüne bağlı olduğundan, aynı konumun iki pozlaması aynı dedektör bandından gelse bile genellikle farklı dalga boylarını ölçer. Q-FIT ekibi bunu güney ekliptik kutbu derin alanındaki gerçek QR2 dosyalarında ölçtü: 2 dakika, 1.5 saat, 1 gün ve 6 ay arayla alınmış dört pozlama çiftinin hepsinde dalga boyu farkı yaklaşık bir bant genişliği veya daha fazlaydı. Bu nedenle böyle iki pozlama arasındaki parlaklık farkı, kaynağın değiştiğinin kanıtı değildir. Bu ölçüm QR2 verisiyle yapılmıştır ve DR1 ile QR3 için yeniden kontrol edilmelidir.
Kaynaklar: qfit-milestone-report, spherex-data-products

## Neler karşılaştırılabilir
Parlaklıkta adil bir karşılaştırma için aynı dedektör bandı, hedef konumunda neredeyse aynı dalga boyu ve aynı işleme sürümü gerekir. Konum değişimi (hareket), kaynak her iki pozlamada da görünüyorsa farklı dalga boylarındaki pozlamalar arasında değerlendirilebilir. Bu yolla bulunan her görünür değişim insan incelemesi için bir adaydır, bir tespit değildir.
Kaynaklar: qfit-milestone-report, qfit-spec

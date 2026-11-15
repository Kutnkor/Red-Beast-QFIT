# BlinkSpace — Ürün Kapsamı (SPEC)

**Slogan:** BlinkSpace — Gökyüzünde değişeni bul.

## 1. Ürün

Herkese açık, üyeliksiz bir web aracı. Kullanıcı RA/Dec girer veya hazır bir hedef seçer; aynı gökyüzü
bölgesinin farklı zamanlarda çekilmiş **gerçek SPHEREx** görüntülerini kare kare / animasyonla inceler,
tarihleri karşılaştırır, dikkatini çeken noktaları işaretler ve gözlemini bağlantıyla paylaşır.

Hazır hedefler: Barnard's Star, Epsilon Indi B, WISE 0855−0714, RW Aurigae, R Draconis.

## 2. Bilimsel kurallar (bağlayıcı)

1. **Gerçek veri.** Zaman dizileri yalnızca IRSA'daki SPHEREx Level-2 spektral görüntülerinden üretilir.
   Sentetik veri yalnızca testlerde ve "sentetik eğitim verisi" etiketiyle kullanılır.
2. **Dalga boyu uyumu.** SPHEREx'te dalga boyu dedektör üzerindeki konuma bağlıdır (LVF). Aynı dedektör
   aynı dalga boyu demek değildir. Zaman karşılaştırmasına yalnızca hedef konumundaki merkez dalga boyu
   `|λ − λ0| ≤ tol × Δλ(FWHM)` koşulunu sağlayan kareler girer (varsayılan `tol = 0.5`, nicel ölçümde 0.25).
   Kare içindeki her piksel için dalga boyu haritası hesaplanır; tolerans dışı pikseller
   "karşılaştırılamaz alan" olarak maskelenir.
3. **Tekrarlar.** Aynı gözlem kimliği + dedektörün yeniden işlenmiş kopyaları tek gözlem sayılır
   (en yeni sürüm/işleme tutulur). Farklı dedektörler ayrı kayıtlardır.
4. **Geçersiz piksel = ölçüm yok.** NaN ve geçersiz bayraklı pikseller asla 0 ile doldurulmaz; önizlemede
   saydam, sayısal üründe NaN kalır. Bayrak bitleri ortalanmaz; maskeler ayrı taşınır.
5. **Hizalama gökyüzü koordinatıyla yapılır.** Tüm kareler ortak merkez, kuzey-yukarı/doğu-sol yön,
   ortak piksel ölçeği ve boyuta yeniden örneklenir. Hedef kaynak karelerde sabitlenmez.
6. **Ortak görüntüleme ölçeği.** Bir dizideki tüm kareler aynı siyah/beyaz sınırlarını kullanır;
   arka plan düzeltmesi kare başına kaydedilir.
7. **Önizlemeden ölçüm yapılmaz.** Parlaklık ölçümü yeniden örneklenmemiş ham cutout piksellerinden,
   varyans katmanıyla yapılır.
8. **Dürüst durum dili.** "Veri mevcut", "kaynak seçiliyor", "değişim görülüyor" ve "değişim bilimsel
   olarak doğrulandı" ayrı durumlardır. Kullanıcı işaretleri "doğrulanmayı bekleyen gözlem"dir.
9. **Konum ilerletme.** Hızlı hedeflerde yalnızca özdevinimle doğrusal ilerletme yapılır; paralaks ve
   gözlemci etkisi içermediği arayüzde ve raporda belirtilir.
10. **İzlenebilirlik.** Her kare: gözlem kimliği, zaman (UTC, MJD), dedektör, dalga boyu, bant genişliği,
    kalite özeti, WCS dönüşümü, veri sürümü, işleme sürümü, kaynak adresi, ham dosya SHA-256.

## 3. İşlevsel kapsam

- Çekirdek: koordinat doğrulama → arşiv sorgusu → seçim → cutout → kalite → hizalama → önizleme → kayıt → arayüz.
- Arayüz: iki giriş (hazır keşif / koordinatla arama), oynatıcı, zaman çizgisi, yakınlaştırma-kaydırma,
  yan yana karşılaştırma, bilgi paneli, işaretleme, paylaşım, TR/EN.
- Sunucu: hedef listesi, arama işi, iş durumu, dizi, işaret/gözlem kaydı, paylaşım, kaynak ve kalite bilgisi.
- İleri: fark görüntüsü, birleştirme, Gaia/WISE katmanı, parlaklık grafiği, spektrum, otomatik aday önerisi.
- Öğretici görevler: gerçek bulgulardan türetilmiş, yanıt anahtarı veriden doğrulanmış.

## 4. Kabul ölçütleri

| # | Ölçüt | Kanıt yeri |
|---|-------|-----------|
| A1 | Uygulama temiz kurulumla çalışıyor | EVIDENCE.md §Kurulum |
| A2 | Gerçek SPHEREx verisi kullanılıyor (ham dosya özetleriyle) | EVIDENCE.md, `reports/` |
| A3 | Yeni koordinat girilip uçtan uca sonuç alınıyor | EVIDENCE.md §Uçtan uca |
| A4 | Uygun gözlem varsa gerçek zaman dizisi gösteriliyor | tarayıcı kanıtları |
| A5 | Tarih, dalga boyu, kalite, kaynak izlenebiliyor | API + arayüz |
| A6 | Bilimsel kurallar testlerle zorlanıyor | `backend/tests` |
| A7 | İşaretleme ve paylaşım çalışıyor, yeniden başlatmada korunuyor | testler + tarayıcı |
| A8 | Beş hedefin raporu var | `reports/targets/` |
| A9 | Gerçek tarayıcı akışı denendi | `evidence/` |
| A10 | Performans ölçümleri kayıtlı | `reports/performance.md` |
| A11 | TR/EN arayüz tam | testler |
| A12 | İleri özelliklerin durumu ve kanıtı belli | STATUS.md |
| A13 | Belgeler üretildi, kontrol edildi | `docs/` |
| A14 | Yayın durumu doğru belirtildi | STATUS.md |

## 5. Kapsam dışı / bilinen sınırlar

- SPHEREx pikseli 6.15″; yakın çiftler (Eps Indi Ba/Bb, RW Aur A/B) çözülemez.
- Hızlı Bakış (Quick Release) verisi kullanılır; kalibrasyon nihai değildir.
- Fark görüntüsünde PSF eşleştirmesi yapılmaz (PSF alt-örneklemeli); artıklar belgelenir.

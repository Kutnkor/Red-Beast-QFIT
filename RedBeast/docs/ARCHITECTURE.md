# Mimari ve veri akışı

## Genel yapı

```
Tarayıcı (React + TypeScript, tek sayfa)
   │  /api/...  (JSON + PNG)
   ▼
FastAPI sunucusu (tek süreç)
   ├─ api.py        uç noktalar, girdi doğrulama, hız sınırı, statik arayüz
   ├─ jobs.py       süreç içi iş kuyruğu (1 işçi iş parçacığı) — HTTP isteğinden bağımsız
   ├─ pipeline.py   uçtan uca hazırlama hattı
   ├─ spectrum.py   zaman penceresinde dalga boyuna karşı akı
   ├─ analysis.py   fark, birleştirme, ışık eğrisi, katalog katmanı, aday önerisi
   ├─ measure.py    hedef ölçümü ve durum basamakları (raporlar, öğretici yanıt anahtarı)
   └─ db.py         SQLite (WAL): işler, diziler, kareler, paylaşımlar, önbellekler
   │
   ├─ data/raw/<sha[:2]>/<sha256>.fits      ham cutout'lar (indirildiği gibi, salt okunur)
   └─ data/processed/<dizi>/                hizalanmış sayısal kareler (.npz) + önizlemeler (.png)
   │
   ▼
IRSA (herkese açık): TAP (spherex.plane ⨝ spherex.artifact, gaia_dr3_source, allwise_p3as_psd) + IBE cutout
```

Bilim kodu arayüzden ayrıdır; her modül bağımsız test edilir (`backend/tests`).

| Modül | Sorumluluk |
|---|---|
| `coords.py` | RA/Dec ayrıştırma, birimler, sınırlar, biçimlendirme |
| `archive.py` | TAP sorgusu, satır ayrıştırma, yeniden işlenmiş kopyaların ayıklanması |
| `wavelength.py` | WCS-WAVE tablosu, dedektör dalga boyu modeli, ayak izinden piksel öngörüsü |
| `selection.py` | dalga boyu grupları, ziyaretler, kare seçimi |
| `cutouts.py` | izinli adres denetimi, indirme, ham dosya deposu |
| `spx.py` | Level-2 MEF okuma (katmanlar ada göre), bayrak tanımları, dedektör koordinatı |
| `quality.py` | bayrak sınıfları (geçersiz / şüpheli / bilgi), kalite özeti |
| `align.py` | ortak ızgara, yeniden örnekleme, maskeler, arka plan, merkez ölçümü |
| `preview.py` | ortak ölçekli PNG önizlemeler |
| `photometry.py` | ham piksellerde açıklık fotometrisi |
| `catalogs.py` | Gaia DR3 / AllWISE sorguları, özdevinimle konum ilerletme |

## Kayıt türleri (SQLite)

| Tablo | Kayıt |
|---|---|
| `searches` | arama isteği (parametreler, istek anahtarı, iş) |
| `tap_cache` | gözlem listesi (arşiv yanıtı, konum başına, 24 saat) |
| `jobs` | hazırlama işi (durum, aşama, ilerleme, hata, iptal bayrağı) |
| `sequences` | hazırlanmış görüntü dizisi (parametreler + tüm üst veri) |
| `frames` | kare (gözlem kimliği, zaman, dalga boyu, kalite, WCS, sürümler, kaynak bağlantısı, ham SHA-256) |
| `shared_observations` | paylaşılmış gözlem (başlık, not, **işaretler**, görünüm, düzenleme anahtarı özeti) |
| `tutorials` | öğretici görev |
| `raw_files`, `catalog_cache`, `meta` | ham dosya dizini, katalog önbelleği, hazır hedef eşlemeleri |

Kullanıcı işareti paylaşılan gözlemin içinde saklanır: gökyüzü koordinatı (ICRS), ilgili kare dizini, o karenin
gözlem kimliği ve zamanı (sunucu doldurur), sınıf, not, isteğe bağlı iz kimliği. Hareket izinde her nokta kendi
tarihini taşır.

## Akış

```
koordinatı doğrula → arşivi sorgula (TAP, önbellekli) → tekrarları ayıkla → dalga boyunu öngör ve grupla
→ kareleri seç → cutout'ları al (en çok 3 eşzamanlı) → oku + gerçek dalga boyunu doğrula → kaliteyi değerlendir
→ ortak ızgaraya hizala → arka plan + ortak ölçek → önizlemeleri üret → hizalama denetimi (Gaia)
→ kaydet → arayüze sun
```

İş durumları: `queued → searching → downloading → preparing → done | insufficient_data | failed | cancelled`.

- **Aynı isteği birleştirme:** aynı istek anahtarı için bitmemiş iş varsa yeni iş açılmaz (ölçüm: 4 eşzamanlı
  gönderim → 1 iş).
- **Önbellek anahtarı:** koordinat (1e-5°), alan, kare sayısı, tarih aralığı, dalga boyu, tolerans, hazır hedef ve
  işlem sürümü → *istek anahtarı*. Seçilen arşiv ürünlerinin parmak izi (gözlem, dedektör, veri sürümü, L2 etiketi)
  eklenince → *dizi anahtarı*. 
- **İptal:** bayrak veritabanında; hat her adım arasında denetler.
- **Zaman aşımı / yeniden deneme:** TAP 240 s, cutout 120 s, iş 900 s; ağ hatası ve 5xx için en çok 3 deneme,
  üstel bekleme; 4xx yeniden denenmez.
- **Yeniden başlatma:** yarım işler `failed / interrupted_by_restart` olur; diziler ve paylaşımlar korunur.

## Güvenlik ve sınırlar

- İndirme yalnızca `https://irsa.ipac.caltech.edu/ibe/data/spherex/` altına izinlidir (şema, ana makine, yol,
  kimlik bilgisi ve port denetimi).
- Girdiler Pydantic ile doğrulanır; hata yanıtlarında kullanıcı girdisi geri yansıtılmaz.
- Notlar düz metin saklanır; arayüz hiçbir yerde HTML olarak yorumlamaz.
- Dosya sunumu ad kalıbı beyaz listesiyle sınırlıdır (`frame_NN.png`, `diff_NN_NN.png`, `stack.png`).
- Katı CSP (`default-src 'self'`), dış kaynak yok.
- Hız sınırı: arama 12/dk, yazma 30/dk (IP başına, bellek içi); kuyruk en çok 12 etkin iş.
- Sınırlar: alan 2–30′, kare 2–16, spektrum 3–40 nokta ve 1–60 gün (gerekçe: `reports/performance.md`).

## Arayüz

`frontend/src`: `pages/` (ana sayfa, arama formu, iş paneli, paylaşım), `viewer/` (görüntüleyici, bölmeler,
zaman çizgisi, işaretler, ışık eğrisi, spektrum, öğretici), `lib/` (API, WCS, işaret modeli, iş izleme, depolama),
`i18n/` (tr, en). Yönlendirme: `/`, `/s/<dizi>`, `/o/<gözlem>`; gömme için `/?ra=&dec=&fov=` veya `/?target=`,
`?lang=`, `?embed=1`.

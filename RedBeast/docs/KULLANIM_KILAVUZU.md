# BlinkSpace kullanım kılavuzu

BlinkSpace, gökyüzünün bir bölgesinin farklı tarihlerde çekilmiş **gerçek SPHEREx** görüntülerini art arda
göstererek değişeni (hareket eden ya da parlaklığı değişen kaynakları) bulmanıza yardım eder. Üyelik gerekmez.

## Yeni arayüzde hızlı erişim

- Üstteki hedef sekmeleri beş hazır yıldızı seçer. **Yıldız** 3B modeli, **Gökyüzü** komşuları, **Gözlemler** gerçek SPHEREx karelerini açar.
- Kaynaklı yarıçap, sıcaklık, uzaklık ve özdevinim kartlarından **Ölçümler** açılır; Three.js modeli buradan indirilebilir. Bilinmeyen değerler sıfır sayılmaz.
- **Ctrl/⌘K** veya **/** ile aramayı aç; koordinat formu aynı penceredeki “Koordinatla gerçek gözlem ara” bölümündedir. Arama ilerlemesi ekranda görünür.
- **M** ölçümleri (gözlem modunda işaretleme), **H** Gaia renk–parlaklık diyagramını, **S** QFIT’i açar. Eski 1/2/3, P/Space, oklar, B, +/−/0 ve ? korunur.
- **Analiz araçları** kare, katman, işaret, ışık eğrisi, dalga boyu, görev ve paylaşım işlevlerini korur.
- QFIT yanıtının altında kaynaklar ve belirsizlikler bulunur. “Yerel kaynak kartı” AI yanıtı değildir. AI etkinse yanıt “Yapay zekâ açıklaması” diye etiketlenir. Komut yalnızca düğmesine bastığında çalışır; **Durdur** devam eden isteği keser.
- Ayarlar saydamlık, kalite ve katmanları değiştirir. Sisteminin hareket azaltma tercihi desteklenir. Eski arayüz `?ui=legacy` ile açılır.

## 1. Başlarken

Ana sayfada iki yol vardır:

- **Hazır bir keşif aç:** beş hedef (Barnard Yıldızı, Epsilon Indi B, WISE 0855−0714, RW Aurigae, R Draconis)
  önceden hazırlanmıştır ve anında açılır.
- **Koordinatlarla bir bölge ara:** kendi konumunuzu girin.

Dil, sağ üstteki **Türkçe / English** düğmesinden değişir.

## 2. Koordinat girme

| Alan | Kabul edilen biçimler |
|---|---|
| Sağ açıklık (RA) | derece: `269.4463` · saat: `17h57m47.1s`, `17:57:47.1`, `17 57 47.1` |
| RA birimi | **Otomatik** (yalın sayı = derece; saat/dakika işaretli = saat), **Derece**, **Saat** |
| Dik açıklık (Dec) | `+4.7682`, `-7.245`, `+04d46m05.5s`, `-07:14:42.5`, `-07 14 42.5` |
| Görüş alanı | 2–30 yay dakikası (büyük alan = daha uzun aktarım) |
| En çok kare | 2–16 |
| Tarih aralığı, dalga boyu | isteğe bağlı; boş bırakılırsa en iyi zaman kapsamına sahip dalga boyu seçilir |

Ondalık virgül (`269,4463`) de kabul edilir. Sunucu okuduğu konumu size geri gösterir; RA'yı derece mi saat mi
yorumladığını orada görürsünüz. Hatalı girişte nedenini söyleyen bir ileti çıkar (ör. "Dec −90 ile +90 arasında olmalı").

**Arama ne kadar sürer?** Yeni bir konum için genellikle 1–3 dakika: arşiv sorgusu (30–80 s), karelerin indirilmesi
(kare başına ~4 MB) ve hizalama denetimi. Aşamalar ekranda görünür: *Sırada → Arşiv sorgulanıyor → Kareler
indiriliyor → Hizalanıyor ve hazırlanıyor*. **İptal et** ile durdurabilirsiniz. Aynı arama ikinci kez anında açılır.

Bağlantıyla arama: `…/?ra=202.4696&dec=47.1953&fov=6` ya da `…/?target=barnard`. Başka bir sayfaya gömmek için
`&embed=1` ekleyin.

## 3. Görüntüleyici

Görüntü ekranın büyük kısmını kaplar. **Kuzey yukarıda, doğu soldadır.** Her piksel 6.15 yay saniyesidir ve
pikseller bulanıklaştırılmadan gösterilir.

- **Oynat / Duraklat**, **önceki / sonraki kare**, **hız** (kare/saniye). Oynatma siz başlatmadan başlamaz.
- **Zaman çizgisi:** kareler **gerçek gözlem tarihlerine** göre yerleştirilir (aralıklar eşit değildir). Oynatma
  hızı gerçek zamanı temsil etmez; her zaman ekrandaki UTC tarihe bakın.
- **Yakınlaştırma / kaydırma:** fare tekerleği, `+` `−` düğmeleri, sürükleme; dokunmatik ekranda iki parmak.
  Kare değişince yakınlaştırma ve konum korunur.
- **Görünümler:**
  - *Tek* — kareleri art arda gösterir (blink). `B` tuşu A ile B karesi arasında gidip gelir.
  - *Yan yana* — A ve B kareleri eşzamanlı, aynı yakınlaştırmayla.
  - *Fark* — B − A. Orta gri = değişim yok, açık = parlaklaşma, koyu = sönükleşme. Durağan yıldızlarda da artık
    görülür (PSF eşleştirmesi yoktur); uyarıları okuyun. Ham karelere dönmek için *Tek*'e basın.
  - *Birleştirme* — karelerin ortalaması. Hareket eden kaynak bulanıklaşır; ekranda kaç piksel kaydığı yazar.

### Ekrandaki desenler ve renkler

| Görünüm | Anlamı |
|---|---|
| Çapraz çizgili (desenli) piksel | **ölçüm yok** — bozuk/doymuş piksel ya da kapsam dışı. Siyah ya da "sıfır parlaklık" değildir. |
| Turuncu katman | şüpheli piksel (kozmik ışın, doyma, parlak yıldız saçılması vb.) |
| Mavi katman | bu karede dalga boyu, karşılaştırma dalga boyundan fazla sapan alan — zaman karşılaştırmasına uygun değil |
| Camgöbeği halkalar | katalog kaynakları (Gaia DR3 ya da AllWISE) — görüntü değil, katalog konumu |
| Kehribar halka/nokta | sizin işaretiniz |
| Kesikli işaret | otomatik aday önerisi — yalnızca inceleme yardımı |

### Sağ paneller

- **Kare:** tarih (UTC) ve MJD, dalga boyu ± bant genişliği, dedektör, gözlem kimliği, veri ve işleme sürümü,
  kalite özeti, arka plan, kaynak bağlantıları, ham dosyanın SHA-256 özeti.
- **Katmanlar:** kalite katmanı, Gaia DR3, AllWISE, öngörülen hedef konumu (yalnızca özdevinimle; paralaks yok),
  aday önerileri.
- **İşaretler:** işaretleriniz ve paylaşım.
- **Eğri:** ışık eğrisi — seçili işaretin ya da hazır hedefin, ham piksellerden ölçülen akısı. "Ölçüm yok" noktaları
  sıfır olarak çizilmez; doymuş noktalar ayrı gösterilir.
- **Dalga boyu:** bu konumda bulunan diğer dalga boyu grupları (dalga boyu keşfi — zaman karşılaştırması değildir) ve
  **Spektrum**: seçtiğiniz zaman penceresindeki tüm pozlamalardan dalga boyuna karşı akı. Noktalar eşzamanlı
  değildir; her noktanın tarihi tabloda yazar.
- **Görev:** öğretici görevler.
- **Kaynak ve kalite:** arşiv sorgusu, seçim/eleme bilgisi, hizalama denetimi ve atıf.

## 4. İşaretleme

1. **İşaret ekle**'ye basın (ya da `M`).
2. Bir noktaya tıklayın; küçük bir bölge için sürükleyin.
3. Sınıf seçin: **Olası hareket**, **Olası parlaklık değişimi**, **Olası görüntü hatası**, **Emin değilim**.
4. İsterseniz not yazın. İşareti sürükleyerek taşıyabilir, **Sil** ile kaldırabilirsiniz.

İşaret ekran pikseline değil **gökyüzü koordinatına** ve yapıldığı **kareye (tarihe)** bağlıdır; yakınlaştırınca
ya da pencere boyutu değişince yerinde kalır. Hareket izlemek için: bir kaynağı işaretleyin, **Bu izi başka bir
karede sürdür**'e basın, başka tarihli karede aynı kaynağın yeni yerini işaretleyin. İz, noktaları tarih sırasıyla
birleştirir; her nokta kendi tarihini taşır.

## 5. Paylaşma

**İşaretler** panelinde başlık ve not yazıp **Kaydet ve bağlantı oluştur**'a basın. Bağlantıyı kopyalayın.

- Bağlantıyı açan herkes aynı kareleri, işaretleri ve görünümü görür. Arşiv sonradan güncellense bile paylaşılan
  gözlem değişmez.
- Gözlemi yalnızca oluşturduğunuz tarayıcıdan güncelleyebilir ya da silebilirsiniz (düzenleme anahtarı o tarayıcıda
  saklanır; hesap yoktur).
- Paylaşılan her gözlem **"doğrulanmayı bekleyen kullanıcı gözlemi"** olarak gösterilir. BlinkSpace bir keşfi
  doğrulamaz; ilginç bir şey bulduysanız kaynak bağlantılarını ve tarihleri bir gökbilimciyle paylaşın.

## 6. Öğretici görevler

Ana sayfadaki **Öğretici görevler** bölümünden: *İlk gözlemin*, *Hareketi fark et* (Eps Indi B), *Parlaklık değişimini
incele* (RW Aurigae), *Görüntü hatasını tanı* (R Draconis), *Neden uygun dalga boyu gerekir?*. Görevlerin yanıtları
gerçek ölçümlerden üretilmiştir; açıklamada ölçüm değerleri yazar. Sentetik veri kullanılmaz.

## 7. Klavye kısayolları

| Tuş | İşlev |
|---|---|
| Boşluk | oynat / duraklat |
| ← → | önceki / sonraki kare |
| B | A ↔ B karesi (blink) |
| + − 0 | yakınlaştır / uzaklaştır / görünümü sıfırla |
| M | işaretleme kipini aç/kapat |
| Enter (görüntü odaktayken) | görünüm merkezine işaret koy |
| Esc | iptal / pencereyi kapat |
| ? | kısayol penceresi |

Kısayollar bir metin alanına yazarken çalışmaz.

## 8. Sık sorulanlar

**Yıldızın ortası neden desenli?** Çok parlak yıldızlar dedektörü doyurur; o pikseller ölçülemez ve "ölçüm yok"
olarak gösterilir. Parlaklık ölçümü yapılamaz ama konum hâlâ izlenebilir.

**"Yetersiz karşılaştırma" ne demek?** Seçilen dalga boyunda yalnızca bir kullanılabilir kare bulundu. *Dalga boyu*
panelinden başka bir grup deneyin.

**"Eksik veri" uyarısı?** Seçilen karelerden bazıları indirilemedi ya da elendi (ör. alan kapsaması düşük); hangileri
olduğu uyarının altında listelenir.

**Kaynak iki karede farklı parlak görünüyor; gerçek mi?** Önce *Kare* panelinde dalga boyu sapmasına ve kalite
bayraklarına, sonra *Eğri* paneline bakın. Yalnızca önizleme görüntüsüne bakarak karar vermeyin.

**Bu NASA'nın bir ürünü mü?** Hayır. Veri NASA/JPL-Caltech SPHEREx görevine aittir (IRSA üzerinden); BlinkSpace
bağımsız bir projedir.

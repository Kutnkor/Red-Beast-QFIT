# RedBeast V4 entegrasyonu — 15 Kasım 2026

Gönderilen Q--FIT-v1-main.zip içindeki app-v4.html etkin tasarım temelidir. V5 kullanılmadı. Özgün V4, SHA-256 kaydı ve MIT lisansı frontend/vendor/v4 altında değiştirilmeden saklanır. Depo kökündeki v2/v3/v4/v5 dosyaları tarihî referans olarak korunur; çalışan uygulama RedBeast/ içindedir.

## Kullanıcı kararları ve uygulama

| Karar | Sonuç |
|---|---|
| Açılışta gerçek SPHEREx | Varsayılan Gözlemler; URL ile seçilen diğer görünüm yine açılabilir. |
| Aynı V4 tasarımı | Tipografi, cam paneller, kayan sekmeler, büyüyen araç çubuğu, cetvel dalgası, yaş sayacı, lider çizgileri, küçük grafikler ve HR evre seçimi korunur. |
| 0,1–100 M☉ aralığını koru | V4 physics_v1 eğitim senaryosu korunur; süpernova, nötron yıldızı ve kara delik sonları açıkça temsili etiketlenir. |
| Kaynaklı modeller ayrı | MIST 1/1,4 M☉, BHAC15 0,15 M☉ ve ATMO 0,005/0,05 M☉ tabloları ayrı seçenek. Tablonun ötesine uzatılmaz. |
| 3B yıldız ve uzay konumu | Var olan Three.js yüzey/çevre modelleri, Gaia komşuluğu, ICRS RA/Dec araması ve takvim hareketi bağlanır. |
| QFIT ve marka | RedBeast başlığı ve kuş; QFIT adı, orantılı maskot ve beyaz sohbet yazısı korunur. Asistana eğitim ve kaynaklı model bağlamı ayrı gönderilir. |

Gerçek görüntü takvimi, katalog hareket yılı ve yıldız evriminin model yaşı üç ayrı zaman ölçeğidir. Eğitim kütle cetveli, yayımlanmış evrim tablolarının kapsamını genişletmiş sayılmaz. Verilen V4 eğitim aralıkları kesin fiziksel öngörü değildir. Örneğin bir yıldızın sonu yalnızca başlangıç kütlesiyle kesin belirlenemez; senaryo öğretim amaçlı basitleştirmedir.

## NASA Space Apps uyumu

2026 **Planet X and SPHEREx** challenge özetinin odağı, herkesin SPHEREx gökyüzü görüntülerindeki zaman içindeki değişimleri kolayca görebileceği bir web aracıdır. Bu özet resmî Space Apps sitesindeki [challenge açıklamasını taşıyan ekip sayfasından](https://www.spaceappschallenge.org/2026/find-a-team/lsp26/) doğrulandı. Ayrıntılı challenge sayfası bu incelemede 502 verdi; bütün değerlendirme maddelerinin doğrulandığı iddia edilmez.

| Başlık | Değerlendirme |
|---|---|
| Gerçek SPHEREx görüntüleri | Çalışan beş hazır hedef ve 25 ham cutout; V4 açılışına bağlandı. |
| Zaman karşılaştırması | Gerçek UTC tarihleri, A/B blink, yan yana/fark görünümleri ve dalga boyu bilgisi var. |
| Kaynak ve kalite | IRSA kaynağı, WCS/işleme bilgileri, geçersiz piksel ve kalite uyarıları korunur. |
| Halkın erişimi | Yerel sürüm hazır; kamuya açık barındırma ve yarışma teslimi yapılmış değildir. |
| 3B eğitim | Destekleyici anlatım; gerçek gözlem karşılaştırmasının yerine geçmez. |
| Bilimsel sonuç | Uygulama keşif veya doğrulanmış değişim ilan etmez. Barnard çekirdeği doygun; karanlık çekirdek ölçüm boşluğudur. |

Bu nedenle temel challenge amacına işlevsel olarak uygundur; yarışmaya tamamen hazır veya NASA tarafından onaylı olduğu söylenemez. Kamuya açık yayın, bağımsız kullanıcı denemesi ve nihai yarışma teslim kontrolü hâlâ ayrı işlerdir.

## Yapı ve doğrulama sınırları

Yıldız değişim animasyonu sonunda evre etiketlerinin yatay konumunu silen özgün clearProps hatası düzeltildi. V4 kendi aynı-origin çerçevesinde çalışır. Bilimsel sahne Shadow DOM ile yalıtılır; böylece V4’ün `.stage`, `.transport` gibi stilleri veri görüntüleyicisini bozmaz. Three.js boyutları gerçek kapsayıcıdan alınır. GSAP ve fontlar yerel paketlenir. Orijinal eğitim denetleyicisi açıkça korunmuş üçüncü taraf kodudur; TypeScript denetimi bu dosyada kapalıdır. React köprüsü derleme ve davranış testlerinden geçer.

203 ön yüz testi, 203 sunucu testi ve üretim derlemesi; dört canlı arşiv testi bu turda atlandı. Yeni köprü testleri varsayılan gerçek gözlemleri, eğitim/gözlem bağlam ayrımını, anlık QFIT örneğini ve koordinat aramasını denetler. Gerçek tarayıcıda masaüstü 3B oranları, SPHEREx kareleri ve sekme geçişleri incelendi. 375 piksel gömülü önizlemede okunabilir yerleşim kontrol edildi; tarayıcı aracının iç içe çerçeve etkileşimi sınırı nedeniyle mobil dokunma akışının tümü doğrulanamadı. Türk ve İngiliz bayraklarıyla dil anında değiştirilir. V4 menüleri, eğitim anlatımı, evreler, yaş/sayı biçimleri, arama ve ayarlar TR/EN çevrilir; mevcut evre konumu korunur. Bilimsel görünüm ve QFIT de seçilen dili kullanır. Üst logo kuşu 42 px, yazı 24 px; Red kısmı kırmızı; QFIT maskotu özgün 320:272 oranıyla 108 px genişliktedir (dar ekranda 80 px).

Lint hata üretmez, fakat eski prototip ve React bağlama uyarıları vardır. Paket boyutu uyarısı sürer. Yeni ücretli AI isteği veya kamuya açık dağıtım bu kontrolün parçası değildir. Güncel sayılar ve görsel kanıtlar reports/v4-validation.json içindedir; önceki raporların tarihleri korunur.

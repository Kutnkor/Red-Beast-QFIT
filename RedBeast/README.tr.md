# RedBeast V4 güncellemesi

Uygulama artık gönderilen **app-v4.html** tasarımını temel alır. İlk görünüm gerçek SPHEREx gözlemleridir. **Yıldız** sekmesinde katalog yıldızı, kaynaklı evrim tablosu ve tam 0,1–100 Güneş kütlesi aralığındaki temsili eğitim modeli ayrı seçeneklerdir. V4 cetveli, HR diyagramı ve hareketleri korunur; yıldız Three.js ile çizilir. AI asistanın adı QFIT olarak kalır.

[Güncel entegrasyon ve yarışma değerlendirmesi](docs/V4_INTEGRATION.md) · [Çalıştırma](README.md)

Aşağıdaki önceki metin, geçmiş sürümün ayrıntılarını da içerir.

# RedBeast

Gerçek NASA SPHEREx görüntülerini farklı gözlem tarihlerinde karşılaştıran ve katalog
verilerinden yıldızların 3B hareketini hesaplayan web uygulaması.

Barnard Yıldızı, Epsilon Indi B, WISE 0855−0714, RW Aurigae ve R Draconis hazır hedeflerdir.
RA/Dec koordinatıyla yeni bir konum da aranabilir. Karelerin dalga boyları, kalite bayrakları,
kaynakları ve işlem bilgileri görüntülenir.

3B yollar hesaplanır; yıldız yüzeyi temsili olarak çizilir. Bunlar çözünür yıldız fotoğrafları
değildir. Ölçülen, hesaplanan, temsili ve varsayılan değerler ayrı etiketlenir. Geçersiz
pikseller ölçüm sayılmaz. Farklı dalga boyları zamanla parlaklık değişimi gibi yorumlanmaz.
Uygulama hiçbir değişimi bilimsel olarak doğrulanmış ilan etmez.

RedBeast (önceki adı BlinkSpace) bağımsız bir projedir; NASA tarafından geliştirilmemiş veya onaylanmamıştır.

## Güncel doğrulama ve API

[Tasarım sistemi](docs/DESIGN_SYSTEM.md) · [Arayüz/3B denetimi](docs/UI_AUDIT.md) · [Python API ve kurulum](docs/API.md) · [OpenAPI şeması](docs/openapi.json).

## Yeni SPHERE-X arayüzü ve QFIT

Üstten **Yıldız / Gökyüzü / Gözlemler** görünümünü seç. Ölçüm kartları kaynaklı özellikleri, soldaki araçlar analiz/rehber/ayarları açar. Takvim cetveli hesaplanan konum yılını değiştirir. Ayrı evrim görünümü kaynaklı MIST/BHAC15/ATMO karşılaştırma modellerini kullanır; seçilen hedefin ölçülmüş geçmişi veya geleceği değildir. **Ctrl/⌘K** hedef ve koordinat aramasını, **S** QFIT kızılgerdanını açar. Önceki arayüz `?ui=legacy` ile korunur.

QFIT anahtarsızken açıkça etiketlenmiş yerel kaynak kartları gösterir. AI için `.env.example` dosyasını `.env` olarak kopyalayıp yalnızca sunucuda `BLINKSPACE_ASSISTANT_PROVIDER=qfit` ve `OPENAI_API_KEY` ayarla, başlatıcıyı yeniden çalıştır. Anahtarı ZIP’e, Git’e veya tarayıcıya ekleme. Model QFIT paketindeki OpenAI gpt-5.4-mini olarak korunur. **Durdur**, yeniden deneme, kaynaklar ve komut onayı hazırdır.

[Güncel 3B doğrulaması](reports/evolution-validation.json) · [Özellik yerleri](docs/FEATURE_PARITY.md) · [Entegrasyon kararları](DECISIONS.md). Son sürümde gözlem ve kaynaklı yaşam evrimi için ayrı zaman çizelgeleri, düzeltilmiş ekran oranları, konuma göre katalog araması ve RedBeast markası vardır. AI asistanının adı QFIT olarak korunur; kuşun oranları düzeltilmiş, sohbet metni beyaz yapılmıştır. Yerel tarayıcıda 1280×720 masaüstü ve 375×812 mobil görünüm kontrol edildi. Eski ZIP/Docker raporları ve sunum önceki sürümlere aittir; rapor tarihlerini dikkate alın.

## macOS paketini açma

ZIP'i açıp `Start-BlinkSpace.command` dosyasına çift tıklayın. İlk çalıştırmada Python
bağımlılıkları kurulur; paketteki hazır veriler boş `data/` klasörüne kopyalanır.
Terminal penceresi açıkken [BlinkSpace'i açın](http://127.0.0.1:8765).
Python 3.12+ gerekir. Pakette derlenmiş arayüz bulunduğundan Node yalnızca geliştirme
ve yeniden derleme için gereklidir. İlk bağımlılık kurulumu ve yeni arşiv aramaları
internet ister; beş hazır hedefin 25 gerçek SPHEREx karesi pakettedir.

Yeni yıldız modellerinde kaynaklı sıcaklık ve yarıçaplar; bulutlar, korona/rüzgâr,
birikim diski, jetler ve temsili bir titreşim döngüsü bulunur. Belirsizlikler ve her
hedefin sınırları arayüzde gösterilir. [Model açıklamaları](docs/STELLAR_MODELS.md).


Her hedefte **Three.js modelini indir** bağlantısı bulunur. Beş ayrı `.three.json` model;
geometri, malzeme, kaynak notları ve ortak animasyon modülüyle birlikte dışa aktarılır.
[Model paketinin kullanımı](frontend/public/models/README.md).

## Bilgisayarda çalıştırma

Python 3.12 veya üzeri (geliştirmede 3.13) ve Node.js 22 gerekir. Proje klasöründe:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
cd frontend
npm ci
npm run build
cd ..
export PYTHONPATH=backend
python docker/initialize_data.py seed-data data
# Without the bundled seed: python -m tools.prepare_presets && python -m tools.precompute_tracks
python -m uvicorn blinkspace.api:app_factory --factory --host 127.0.0.1 --port 8765 --workers 1
```

[Uygulamayı aç](http://localhost:8765). Hazır hedefler gerçek IRSA verisini indirir; süre arşivin
yanıtına bağlıdır. Hazırlanmış diziler tekrar kullanılır. `BLINKSPACE_DATA_DIR` veri klasörünü
belirler. Arayüzü geliştirmek için ayrı terminalde `frontend` içinde `npm run dev` çalıştırılır.

## Docker

```bash
docker compose up --build
```

[Docker sürümünü aç](http://localhost:8000). Kalıcı birim, gözlemleri yeniden başlatmalar
arasında korur. İmaj beş hazır hedefi içerir ve bunları yalnızca boş veri klasörüne kopyalar.
Arşiv erişimi olmadan derlemek için önce `backend` içinde `python -m tools.package_seed`
ile hazır veri paketi oluşturulur. Ayrıntılar: [DEPLOY.md](docs/DEPLOY.md).

Bu kaynak paketi herkese açık yayın veya yarışmaya gönderim yapıldığı iddiasını taşımaz.
Güncel Hugging Face belgelerine göre yeni Docker Space açmak ücretli hesap planı gerektirir;
CPU Basic'in saatlik ücretinin sıfır olması bunu değiştirmez. Render'ın ücretsiz web
hizmeti uykuya geçer ve yerel dosya değişikliklerini kaybeder. Ücretli hizmet başlatılmadı.

## Doğrulama

```bash
cd backend
../.venv/bin/python -m pytest -q
../.venv/bin/python -m pytest --live -q
cd ../frontend
npm test
npm run build
npm run lint
```

Güncel sonuçlar ve eksik kontroller `reports/` ile `EVIDENCE.md` içinde tutulur. Eski ekran
görüntüleri yeni 3B arayüzün doğrulaması değildir. `python -m tools.target_report` komutu
hazır dizilerden [hedef raporlarını](reports/targets/OZET.md) yeniler.

**Bu uygulama çalışmasında tamamlanan bağımsız kullanıcı testi: 0.**
[USER_TEST.md](docs/USER_TEST.md) yönerge ve boş formdur; geliştirici testleri ayrı tutulur.

Asistan varsayılan olarak kapalıdır. Yerel deneme sağlayıcısı anahtar gerektirmez ve model
çağırmaz. QFIT gerçek sağlayıcısı sunucu anahtarıyla açılabilir: [sözleşme](docs/ASSISTANT_CONTRACT.md).

Kod lisansı [MIT](LICENSE). [Veri kaynakları](docs/DATA_SOURCES.md),
[bilimsel yöntem](docs/METHOD.md), [yapay zekâ kullanımı](docs/AI_USAGE.md).

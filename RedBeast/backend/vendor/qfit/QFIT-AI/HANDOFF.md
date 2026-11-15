# Q-FIT — devir notu (Claude Code için)

Tarih: 2026-11-14. Bu dosya, sohbette yapılan işi Claude Code'a aktarmak için yazıldı.
Önce bunu, sonra `README.md` ve `docs/` altını oku.

## Bağlam
- Q-FIT: NASA Space Apps (SPHEREx) projesinin AI asistanı. Bu depo: arka uç + AI + asistan arayüzü
  (kızılgerdan maskot ve sohbet paneli) + React/Three.js referans uygulaması.
- **Arayüz React + Three.js** (Unity iptal edildi, 2026-11-14). Ekibin asıl React/Three.js uygulaması,
  3B model, `research/data.json` ve zaman çizelgesi bileşenleri diğer ekip üyelerinde; birleştirme
  `mascot/react/src/qfit/` klasörü kopyalanarak yapılır (`docs/FRONTEND_CONTRACT.md`).
- `research/data.json` bu klasörde YOK. Gelmeden `/predict` ve eşik değerlendirmesi yazılamaz:
  eşik ve şema uydurma.
- Kullanıcıya yanıtlar Türkçe yazılır. Kod, belgeler ve bilgi tabanı İngilizce + Türkçe.
- Kesin kural: uydurma veri, sahte URL, sentetik "örnek" gözlem yok. Aday ≠ keşif.

## 1. tur: bitti ve çalışıyor (98 birim testi geçiyordu)
FastAPI arka ucu: Gemini function calling ajanı, 8 veri aracı + `request_clarification`,
IRSA SIA2/TAP, SIMBAD, Sesame, JPL Horizons, tek yanıt zarfı, 14 uç nokta. Ayrıntı: `README.md`,
`docs/API_CONTRACT.md`, `docs/DATA_SOURCES.md`, `docs/ARCHITECTURE.md`.
Canlı testler (`pytest --run-live -rs`) bulut ortamında ağ engeli yüzünden çalıştırılamadı.

## 2. tur (AI bilgi/eğitim hattı): YARIM
### Yazıldı
| Dosya | Durum |
|---|---|
| `research/sources/registry.json` | 31 kaynak, köken üstverisiyle. Tamam. |
| `research/knowledge/en/*.md`, `tr/*.md` | 9 + 9 belge, 82 parça, her bölümün `Sources:` satırı var. Tamam. |
| `app/knowledge/` (language, registry, documents, index, service) | İçe alma, parçalama, kopya tespiti, artımlı indeks, BM25 geri getirme, TR/EN. Elle denendi, çalışıyor. Testi yok. |
| `app/scientific/config_loader.py` | `research/data.json` için şemadan bağımsız yükleyici (yol bulma, güvenli yükleme, sürüm özeti, yapısal sorun raporu). Denenmedi, testi yok. |
| `app/ai/grounding.py` | Yanıttaki sayıların kanıtta olup olmadığını denetler. Denenmedi, testi yok. |
| `app/ai/prompts.py` | Sürümlü talimatlar: `v1` (eski) ve `v2` (kanıt sınıfları, RAG, TR/EN, aday kuralı). `render_knowledge` eklendi. |
| `app/citizen/store.py` | Hash zincirli, yalnızca eklemeli aday/inceleme kaydı. Denenmedi, testi yok. |
| `app/config.py` | Yeni ayarlar: `gemini_embedding_model`, `qfit_instruction_version`, `rag_enabled`, `rag_top_k`, `qfit_data_dir`. |
| `app/models/requests.py` | `ChatContext.locale/expertise_level`, bilgi araması ve aday/inceleme istek modelleri. |
| `app/models/responses.py` | Zarfa `language`, `evidence`, `uncertainty`, `media`, `meta.versions` eklendi. |
| `app/services/response_builder.py` | `_extras` + `@_evidence`, `from_knowledge`, `from_candidate`, `merge` güncellendi. |

### 3. tur (2026-11-14): yapılacaklar listesinin 8 maddesi tamamlandı
`pytest`: **201 geçti, 15 atlandı** (atlananlar canlı/anahtar gerektiren testler), başarısız yok.

| Madde | Sonuç |
|---|---|
| 1 | `Container`: `knowledge`, `scientific`, `candidates` (`<QFIT_DATA_DIR>/citizen/events.jsonl`), `versions()`, `c.envelope()`. Zarf yeni alanları taşıyor. |
| 2 | `search_knowledge_base`, `submit_candidate_for_review` araçları (toplam 11). |
| 3 | Ajan: dil (locale > tespit), RAG ön getirme, sürümlü talimat, `evidence`, dayanak denetimi → `data.grounding` + `uncertainty`. `v1` = RAG'sız taban çizgisi. |
| 4 | `/api/v1/knowledge/*`, `/api/v1/candidates/*` (7 uç), `/health` genişletildi, kökte `/health` ve `/chat`. |
| 5 | `app/training/` (şema, bütünlük, aile bazlı bölme, manifest, Vertex dışa aktarıcı), `scripts/build_dataset.py`, `research/datasets/qfit_seed_v1.jsonl` (68 örnek, 34 TR/EN aile). |
| 6 | `app/evaluation/` + `scripts/evaluate.py`. Geri getirme raporu `research/evaluation/reports/` altında. |
| 7 | 6 yeni test dosyası; eski testler yeni zarfa göre güncellendi. |
| 8 | `docs/AI_ARCHITECTURE.md`, `AI_TRAINING_PIPELINE.md`, `SCIENTIFIC_SOURCES.md`, `MODEL_EVALUATION.md` yazıldı; `API_CONTRACT.md` ve `README.md` güncellendi. (O turdaki Unity sözleşmesi 9. turda `FRONTEND_CONTRACT.md` ile değiştirildi.) |

### Tur geçmişi (kısa)
- **4. tur:** sağlayıcı seçimi (`LLM_PROVIDER`) ve `/chat` için bilgi tabanına geri düşme (`app/services/fallback.py`).
- **5. tur:** OpenAI `gpt-6-astra`, **Responses API** (`app/ai/openai_client.py`); bu model akıl yürütme açıkken Chat Completions'ta araç çağırmayı reddediyor. İlk canlı bulgular düzeltildi: SIMBAD kapalıyken Sesame'e geçiş, yer tutucu koordinat yasağı.
- **6. tur:** kesit indirmede Retry-After, başlık eşleşmesi bonusu (geri getirme MRR 0.770→0.817), "önce genel cevap" talimatı.
- **7. tur:** ekip 68 örneği inceledi (`human_reviewed`); 9 yeni kaynak doğrulanıp kayda eklendi (40 kaynak, `preprint` sınıfı). Canlı testler ilk kez tam çalıştı.
- **8. tur:** tam değerlendirme (68 örnek): dil 66/66, araç argümanları 10/10, hata 0, ort. 13.7 sn. Dayanak denetimi boşluklu saat biçimini tanıyor; SPHEREx tanıtım pasajına kızılötesi eklendi; 4 ekip kararı veri setine işlendi, yeni `required_tools` kontrolü.
- **9. tur (web hazırlığı + arayüz, React'e geçiş):**
  - Kredi koruması: `CHAT_DAILY_LIMIT` (site geneli günlük model çağrısı; dolunca bilgi tabanı yanıtı), `TRUST_PROXY_HEADERS` (proxy arkasında gerçek istemci IP'si), `CHAT_TIMEOUT_SECONDS` (90 sn; aşılırsa bilgi tabanı yanıtı). Arşiv zaman aşımları artık tekrar denenmiyor (canlıda 140 sn bekleme görüldü → 63 sn).
  - Aday yazma uç noktaları `QFIT_TEAM_TOKEN` ayarlıysa `X-QFit-Token` başlığı istiyor (okuma açık).
  - `docs/DEPLOYMENT.md` (barındırma gereksinimleri, Caddy örneği, üretim `.env`), `Dockerfile` (Docker olmadığı için derlenmedi).
  - Kızılgerdan: `ui/mascot/` (orijinaller + ortak tuvale hizalanmış kareler, sprite sheet, ikon, `mascot.json`), `scripts/build_mascot_assets.py`. Durumlar: idle, thinking, speaking, found, quiet, attention (`docs/MASCOT_AND_CHAT_UI.md`).
  - Arayüz: `ui/web_demo/` (sade HTML, arka uç `/demo`'da sunar) ve `frontend/` (React + Three.js referans uygulaması, `npm run build` geçti, tarayıcıda denendi).
  - Son kontrol (2026-11-14 16:07 UTC): 10 soruluk AI testi her kontrolde %100; arşive gitmeyen sorular 4-6 sn, arşive gidenler 26-106 sn (yavaşlık IRSA'dan, modelden değil). Canlı testler: 6 geçti, 3 ENGELLENDİ (IRSA TAP zaman aşımı, SIMBAD kapalı). Zip (`dist/Q-FIT.zip`, git'in izlediği dosyalardan) açılıp test edildi: 190 test geçti, ön yüz sıfırdan kurulup derlendi.
  - Önerilen hızlandırma (onay bekliyor): sohbet için arşiv satır sınırını ve zaman aşımını düşürmek, `reasoning effort: low` denemek; önce/sonra aynı 10 soruyla ölçmek.
  - Unity'ye özel her şey kaldırıldı; `docs/UNITY_BACKEND_CONTRACT.md` yerine `docs/FRONTEND_CONTRACT.md`. Varsayılan sağlayıcı artık `openai`.

### 10. tur (hız, YARIM — ortalama < 10 sn hedefi)
- Ölçüldü (10 soru, `gpt-6-astra`): ortalama 31 sn. Model çağrısı 3-10 sn (akıl yürütme ~100 token; bu model `low` altına inmiyor, `verbosity` etkisiz). Bazı aramalar 45 sn: model `ra: 0, dec: 0` yer tutucusu gönderiyordu → arşiv M31 yerine (0,0)'ı arıyordu (DOĞRULUK HATASI).
- Yapıldı: `clean_arguments` (boş/yer tutucu argümanlar atılıyor), aynı turdaki araçlar paralel, adım adım süre ölçümü (`data.timing`, rapor satırlarında `timings`), talimat: SPHEREx araçlarını adla doğrudan çağır, gereksiz tur yapma; `OPENAI_REASONING_EFFORT` ayarı ve `scripts/evaluate.py --effort`.
- Model ölçümü (araç seçme / kavram): astra 3.8/7.0 sn, **gpt-6-sol (effort none) 2.7/2.9 sn**, gpt-5.4-mini 2.5/2.8 sn.
- SIRADAKİ: `python scripts/evaluate.py agent --config v2_rag --model gpt-6-sol --effort none --dataset <10 soru>` ile kalite + süre ölç; astra ile karşılaştır; iyi ise `.env`: `OPENAI_MODEL=gpt-6-sol`, `OPENAI_REASONING_EFFORT=none`; sonra 68 örnekle doğrula. Gerekirse `HTTP_TIMEOUT_SECONDS` 45→20.

### 11. tur (gpt-5.4-mini + gezinme)
- Ekip modeli `gpt-5.4-mini` yaptı. Önerilen `.env`: `OPENAI_REASONING_EFFORT=none`, `HTTP_TIMEOUT_SECONDS=20`.
- Gezinme: "beni X'e götür / X'e git / X'i göster / take me to X" → yalnızca `resolve_object_coordinates` (arayüze `focus_map`), 1-2 cümle: "İşte X" + bir temel bilgi (katalog türü ya da sayısız genel bilgi), koordinat tekrarı yok, SPHEREx araması önerisi. Canlı denendi: Betelgeuse, Sirius, Vega, Andromeda, Orion Bulutsusu, Deneb → hepsi doğru konuma gitti.
- Yanıtlar kısaltıldı (en çok 3 cümle; ayrıntı arayüzde). Araçlara ad katalog biçiminde gidiyor (Türkçe "Andromeda Galaksisi" Sesame'de çözülmüyordu). Türkçe dil algılama kesme işaretli ekleri tanıyor ("Vega'ya git").
- SIMBAD devre kesici: bir hatadan sonra 5 dk SIMBAD atlanıyor (kesintide her ada +5 sn ekliyordu).
- Ölçüm (12 soru, gpt-5.4-mini, effort none): model çağrısı 2-4 sn (astra 3-10 sn); kavram soruları 1.9-4.1 sn; kalite: dil 12/12, kaynak dayanağı 7/7, uydurma sayı 0, hata 0. Ortalama 15 sn'yi IRSA'nın o anki 502 arızası bozdu (2 soru ~50 sn); arşiv sağlıklıyken veri soruları ~7-9 sn bekleniyor, ÖLÇÜLMEDİ. Gezinme 6-17 sn (SIMBAD kapalı, Sesame 2-6 sn).
- Veri seti: Andromeda örneği gezinmeye göre güncellendi; yeni `a-take-me-to` çifti (AI yazdı, inceleme bekliyor); 70 örnek.
- SIRADAKİ: IRSA düzelince aynı 12 soruyla süre ölçümünü tekrarla; ardından 70 örnekle tam değerlendirme.

### 12. tur (gagayla çekme animasyonu)
- Panel kapalıyken kenarda gaga hizasında turuncu bir tutamaç görünür; kızılgerdan dönüp gagasıyla tutar, geri yürüyerek paneli çeker (180 + 600 ms); kapanırken iter. Web demosu ve React bileşeninde; 4 köşede gaga ucu işaretçisiyle ölçüldü: yatay en çok ±12 px, dikey ±1 px, başta ve sonda 0 px. Aynalama merkezden yapılıyor (eskiden 40 px kayıyordu). Ayrıntı: `docs/MASCOT_AND_CHAT_UI.md`.

### 13. tur (FITS → PNG önizleme)
- `app/services/preview_service.py`, `GET /api/v1/images/preview` (PNG) ve `/images/preview/info` (köşe koordinatları, ölçek aralığı). Görüntü aramalarında `preview_url` hazır geliyor. asinh/log/doğrusal ölçek, NaN saydam, dikey çevirme, 1 saat önbellek. Pillow bağımlılığa eklendi.
- React: `SkyView.showImage(url, corners)` PNG'yi dört köşesinden gökyüzüne yerleştiriyor; `App.tsx` her `display_image`'da çağırıyor. Tarayıcıda test görüntüsüyle doğrulandı (kuzey yukarı, doğu solda, odak noktasında). Geliştirme modunda `window.qfitSky` kancası.
- Gerçek veriyle doğrulandı: M31, `spherex_qr3:2026W32_1A_0420_1:D1`, 0.5° kesit → 292×293 PNG, 12.5 sn, köşeler ~20° dönük (SPHEREx görüntüleri kuzey-yukarı değil). Canlı test `test_live_png_preview_of_a_real_cutout` geçti. IRSA o akşam aralıklı 502 veriyordu.

### 14. tur (veri panelleri)
- `frontend/src/qfit/QFitDataPanel.tsx`: nesne kartı, gözlem tablosu, dönem zaman çizelgesi, PNG küçük resimler (tıklayınca gökyüzüne), tayf kapsamı ve piksel örneği grafiği. `QFitAssistant` yeni `onResponse` prop'u. Gerçek IRSA verisiyle (M31) tarayıcıda denendi: 4 önizleme, 363 kayıt, 5 dönem, 4 piksel örneği.
- Three.js: önizleme gösterilince kamera dönüp görüntü boyuna göre yakınlaşıyor (0.1-1° görüntüler 60° görüşte görünmüyordu); fare tekerleği yakınlaştırması; sürükleme hızı yakınlaşmaya göre. Varsayılan önizleme 0.5° (0.1° yalnızca ~60 px'ti).
- Geliştirme kancaları: `window.qfitSky`, `window.qfitShowResponse`.
- Not: Three.js çizim döngüsü gizli tarayıcı panelinde durduğu için kameranın yakınlaşması burada otomatik izlenemedi; tarayıcıda gözle bakılmalı.

### 15. tur (GitHub paketi: yalnızca AI + maskot)
- Depo düzeni: `Q--FIT-v1/QFIT-AI/` (bu klasör), kökte `.github/workflows/qfit-ai.yml` ve MIT `LICENSE`. 3B tasarım ve arayüz ekibin diğer klasörlerinde.
- Pakette yalnızca AI kısımları ve maskot: `app/`, `research/`, `scripts/`, `tests/`, `docs/`, `mascot/` (`assets/`, `react/src/qfit/` = kızılgerdan + sohbet paneli + gagayla çekme, `vanilla/` = aynısı sade JS). Örnek arayüz (Three.js gökyüzü, örnek uygulama, veri paneli, demo sayfası) depoya girmiyor: bu bilgisayarda `ornek-arayuz-yerel/` içinde (git-ignore). Arka uçtaki `/demo` ve `SERVE_DEMO` kaldırıldı.
- Not: önceki turlardaki `ui/...`, `frontend/...`, `SkyView`, `QFitDataPanel` anlatımları artık `ornek-arayuz-yerel/` altındaki yerel örneği anlatır.
- CI: arka uç testleri + `mascot/react` TypeScript denetimi.
- Son kontroller (2026-11-14): zip'ten sıfırdan kurulum → 201 test geçti, maskot TypeScript denetimi geçti; canlı testler 7 geçti, 3 ENGELLENDİ (IRSA/SIMBAD kesintisi); zip'te anahtar ya da kişisel bilgi yok. Canlı testlerde IRSA'nın 5xx yanıtları artık hata değil ENGELLENDİ sayılıyor.

### 16. tur (master prompt)
- `docs/MASTER_PROMPT.md`: birleştirmeyi yapacak yapay zekâya verilecek tek belge (amaç, kurallar, akış, araçlar, sözleşme, önizlemeler, maskot ve gagayla çekme animasyonu, entegrasyon kodu, yapılacaklar/yapılmayacaklar, açık işler). Koddan doğrulandı.

### Açık kalanlar
- **Ekibin React/Three.js uygulamasıyla birleştirme** ve `research/data.json` gelince `/predict`, eşik değerlendirmesi, zaman çizelgesi uyumu.
- **Barındırma kararı** (ekip): kalıcı disk, ≥120 sn istek süresi, HTTPS, tek süreç. OpenAI panelinde aylık harcama sınırı konmalı.
- **Kimlik:** takım anahtarı "ekipten biri" olduğunu kanıtlar, kim olduğunu değil; `reviewer_id` hâlâ beyana dayalı.
- **Maskot sanatı:** düşünme animasyonundaki kuş farklı çizim stilinde ve kaynakta yalnızca 182 px; yüksek çözünürlüklü ve uyumlu bir yeniden çizim iyi olur.
- **Bilinen geri getirme sınırı:** "Keşfettim mi?" ve "yüzde kaç eminsin?" sorularında doğru politika pasajı bulunmuyor (yanıtlar yine doğru).
- IRSA arşivi 2026-11-14 öğleden sonra yavaştı (bazı aramalar 45 sn zaman aşımına uğradı); SIMBAD bütün gün kapalıydı.
- Türkçe kök uzunluğu 5'te; gömme (embedding) bağlanmadı; Gemini/Ollama kodu duruyor ama kullanılmıyor.

## Bilinen kararlar ve bulgular
- **İnce ayar (fine-tuning):** Gemini Developer API / AI Studio ince ayarı desteklemiyor
  (Mayıs 2025'te kaldırıldı). Yalnızca Vertex AI'da var ve ücretli. Bu projede model ağırlıkları
  eğitilmiyor; "eğitim" = bilgi tabanı + RAG + talimat + araç çağırma + ölçülen değerlendirme.
  Kimseye "modeli eğittik" denmemeli. Dışa aktarıcı ileride kullanılmak üzere yazılacak.
- **Geri getirme:** 82 parça için vektör veritabanı gereksiz; BM25 + Türkçe harf katlama ve
  5 harfli ön ek kökleme kullanılıyor. `min_score=3.0` altındaki eşleşmeler atılıyor.
  Zayıf nokta: Türkçe ünsüz yumuşaması ("bant"/"bandı"). Kök uzunluğu (4 mü 5 mi)
  değerlendirme setiyle ölçülerek seçilecek. Gömme (embedding) isteğe bağlı, canlı denenmedi.
- **Kaynak çelişkisi örneği:** kahverengi cüce kütle aralığını kaynaklar farklı veriyor;
  bilgi tabanı hepsini kaynağıyla listeliyor.
- **Zaman karşılaştırması:** aynı konumun iki pozlaması genellikle farklı dalga boyunda
  (ekibin QR2 ölçümü). Parlaklık farkı tek başına değişim kanıtı değil.
- `.env` içinde gerçek anahtar olabilir: okuma, yazdırma, commit etme.

## Çalıştırma
```powershell
cd QFIT-AI
..\.venv\Scripts\Activate.ps1
pytest                      # 156 geçti, 15 atlandı
pytest --run-live -rs       # IRSA/SIMBAD/Horizons canlı testleri — henüz hiç çalıştırılmadı
python run.py
python scripts/build_dataset.py      # veri seti denetimi + bölme
python scripts/evaluate.py retrieval # anahtarsız
```

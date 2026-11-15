> Historical SPHERE-X source plan. Current integration and remaining acceptance work are recorded in STATUS.md and EVIDENCE.md.

# Plan (PLAN)

Durumlar: `bekliyor` · `devam ediyor` · `doğrulandı` · `engelli`. Bir dosyanın var olması "doğrulandı" demek
değildir; kanıt `EVIDENCE.md` içinde gösterilir. Güncel durum için `STATUS.md`.

| # | İş | Bağımlılık | Doğrulama |
|---|----|-----------|-----------|
| P0 | Ortam ve kaynak doğrulaması | — | EVIDENCE §1–2 |
| P1 | Koordinat ayrıştırma/doğrulama (`coords.py`) | P0 | birim testleri |
| P2 | Arşiv sorgusu + tekrar ayıklama (`archive.py`) | P0 | birim + canlı test |
| P3 | Dalga boyu modeli ve seçim (`wavelength.py`, `selection.py`) | P2 | birim + gerçek dosya karşılaştırması |
| P4 | FITS okuma + kalite (`spx.py`, `quality.py`) | P0 | gerçek QR2/QR3 dosyaları |
| P5 | Hizalama, arka plan, önizleme (`align.py`, `preview.py`) | P4 | kontrollü kaydırma testleri |
| P6 | Beş hedef envanteri (`tools/inventory.py`) | P2–P3 | `reports/inventory.json` |
| P7 | İlk gerçek karşılaştırma (uçtan uca hat, `pipeline.py`) | P1–P5 | gerçek dizi + görsel kontrol |
| P8 | Kalıcı kayıt + işler + API (`db.py`, `jobs.py`, `api.py`) | P7 | API testleri, yeniden başlatma |
| P9 | Arayüz (React/TS): arama, oynatıcı, karşılaştırma, TR/EN | P8 | birim + gerçek tarayıcı |
| P10 | İşaretleme + paylaşım | P8–P9 | tarayıcı akışı, kalıcılık |
| P11 | Öğretici görevler (gerçek bulgulardan) | P7 | yanıt anahtarı doğrulaması |
| P12 | İleri: fark, birleştirme, Gaia/WISE, ışık eğrisi, spektrum, aday önerisi | P7 | özellik başına test + sınır notu |
| P13 | Testlerin tamamı + canlı arşiv testleri | P1–P12 | `pytest`, `vitest`, tarayıcı |
| P14 | Beş hedef bilimsel raporu | P6–P7, P12 | `reports/targets/*.md` |
| P15 | Performans ölçümü | P8–P9 | `reports/performance.md` |
| P16 | Yayın | P13 | yayın sonrası kontrol listesi |
| P17 | Belgeler | P13–P15 | açılıp görsel kontrol |

Öncelik: P1–P8 (çekirdek) → P9–P10 (ara hedef: çalışan prototip) → P11–P15 → P16–P17.

**Güncel durum (2026-11-14):** P0–P15 ve P17 doğrulandı; P16 (yayın) engelli; gerçek kişilerle kullanıcı testi yapılmadı. Ayrıntı: `STATUS.md`.

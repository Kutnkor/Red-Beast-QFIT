# Implementation decisions — 2026-11-14

The dated entries below D-020 describe the imported source and are historical, not new validation results.

## D-020 — Web architecture requested by the implementation plan
The supplied SPHERE-X React19/TypeScript/FastAPI project is the base. The previous Unity project remains a preserved source. A single persistent Three.js renderer switches between a stellar model, nearby stars and real SPHEREx time planes. Observations retain the original WCS/mask/photometry semantics.

## D-021 — Reproducible source data and upstream outages
NASA/IPAC IRSA TAP and SIA intermittently returned HTTP502 during this run. The five prepared sequences were rebuilt by downloading real FITS cutouts from source URLs in the supplied dated inventories; metadata explicitly identifies the inventory snapshot and its SHA-256. Their images were not synthesized. Gaia DR3 positions and temperatures were verified through the official ESA service. The ESA Hipparcos I/239 catalogue was downloaded via the official VizieR Harvard mirror (8,785 stars with V<6.5). Source URLs and hashes accompany all generated catalogues.

## D-022 — Physical colour and model semantics
The UI uses the ten required palette tokens. Stellar RGB is a physics exception: Planck spectra integrated with the Wyman CIE approximation. Missing temperature remains unknown. Measured, computed, representative and assumed values retain distinct labels. Cartesian space motion includes measured radial velocity; missing RV is explicitly zero-assumed. Barnard’s computed 2026–2100 displacement is 12.8932 arcmin (rounds to12.9), consistent with the independent Astropy golden file rather than the plan’s rough12.8 estimate.

## D-023 — Updated visual scope from the user
After the initial integration, the user specifically requested colour, size, surrounding material and stellar interaction models beyond a plain sphere. Target-specific environmental models are therefore added on top of the sourced catalogue. A representative environment is never described as resolved telescope imagery or a fitted dynamical simulation. Angular-motion predictions, surface/size illustrations and dated SPHEREx frames remain explicitly identified.

## D-024 — Fonts and attribution
Barlow400/600 are copied from the supplied Unity font bundle with OFL. IBM Plex Mono400/500 and its OFL are downloaded from the official IBM/plex repository (`packages/plex-mono/fonts/complete/ttf`). They are served locally; no font CDN is used. This revision records OpenAI Codex assistance and does not add the plan’s suggested false Claude co-author signature.

## D-026 — Source-labelled environments and their display clocks
The expanded user request adds different surface structures and surroundings for all five targets. Radius and temperature values retain source uncertainty and historical/model caveats. Square-root radii and the environment geometry are separate from the astrometric trail scale. The illustrative animation clock freezes on pause or reduced motion; it never turns the calendar into stellar evolution. Each binary atmosphere is attached to its own component. A fit to both viewport dimensions keeps the large R Dra environment in frame. See `docs/STELLAR_MODELS.md` for exact display assumptions and tests.

## D-025 — Delivery boundaries
Local build, tests, Docker packaging and public-data downloads are authorized. No public repository push, hosting account creation, competition submission, message to another person or public deployment has been performed. Browser verification has a saved permission block despite the user’s explicit approval; this is recorded rather than bypassed or reported as passed.

---

# Kararlar (DECISIONS)

Tarih biçimi: YYYY-AA-GG. Her karar kısa gerekçesiyle.

## D-002 — Mimari: FastAPI + SQLite + süreç içi iş kuyruğu + React/TS (2026-11-14)
Tek süreçte çalışan basit ve doğrulanabilir yapı. SQLite kalıcı kayıt (paylaşımlar, diziler, işler);
dosyalar `data/` altında. Uzun işlemler HTTP isteğinden bağımsız bir işçi iş parçacığında yürür.
Ayrı kuyruk sunucusu (Redis/Celery) gereksiz altyapı olurdu.

## D-003 — Veri erişimi: IRSA TAP + IBE cutout (2026-11-14)
`spherex.plane ⨝ spherex.artifact` üzerinde `CONTAINS(POINT, poly)`; cutout için
`<uri>?center=<ra>,<dec>&size=<deg>`. SIA2 yerine TAP: yeni veriler TAP'ta ~1 gün daha erken görünüyor ve
ayak izi (poly) sütunu seçim için gerekli. İndirme yalnızca `irsa.ipac.caltech.edu/ibe/data/spherex/` ile sınırlı.

## D-004 — FITS katmanları ada göre okunur (2026-11-14)
Gerçek dosyalarda doğrulandı: QR2 (v6.4, v6.5.x) 5. katman `PSF` küpü; QR3 (v7.0.5) 5. katman `EPSF`
tablosu. Bayrak tanımları QR2'de `MP_<AD>=bit`, QR3'te `MSKNnnnn/MSKMnnnn` anahtarlarında. Sıra veya sabit
bit tablosu varsayılmaz; tanımlar her dosyanın kendi başlığından okunur.

## D-005 — Dalga boyu: dosyanın WCS-WAVE tablosu + dedektör modeli (2026-11-14)
İndirme öncesi aday seçimi için hedefin dedektör pikseli arşivdeki ayak izinden (4 köşe) kestirilir ve
dedektör başına WCS-WAVE tablosundan dalga boyu öngörülür. İndirme sonrası gerçek dalga boyu her dosyanın
kendi tablosundan yeniden hesaplanır ve tolerans yeniden uygulanır. WCS "A" ve "W" alternatiflerinde SIP
uygulanmaz (astropy varsayılanı SIP'i yanlışlıkla uygular; ~24 piksel hata gözlendi).

## D-006 — Yeniden örnekleme ölçeği: doğal 6.15″/piksel (2026-11-14)
Daha ince ızgara çözünürlük uydurmak olurdu. Tarayıcı büyütmesi piksel-korumalı (nearest) yapılır.

## D-007 — Imported source environment (historical, 2026-11-14)
The imported source used a separate Python environment. This delivery uses a project-local `.venv` with Python 3.13.

## D-008 — Katalog kimlikleri: SIMBAD (Harvard yansısı) (2026-11-14)
CDS Strazburg TAP uç noktası 2026-11-14'de 404 döndü; resmî CfA yansısı `simbad.harvard.edu` kullanıldı.
SIMBAD konumları ICRS, epoch J2000.0 (WISE 0855 ve Barnard için özdevinim aritmetiğiyle doğrulandı).

## D-009 — Yapay zekâ kullanımı beyanı (2026-11-14)
The imported project attributed its original work to Claude (Anthropic). The current integration, new science modules and tests were produced with OpenAI Codex. See `AI_USAGE.md`; historical attribution is not authorship of this revision.

## D-010 — Ölçüm ve "değişim görülüyor" ölçütleri (2026-11-14)
Hareket ve parlaklık için aynı eşik: ≥ 3σ. Parlaklıkta ayrıca karşılaştırma yıldızı ölçeklemesi ve en az %20 değişim
aranır. Nicel dalga boyu toleransı 0.25; yeterli nokta yoksa dizinin 0.5 toleransı kullanılır ve tayf eğimi için
%10 sistematik eklenir. Doymamış kaynakta merkez hatası dizinin kendi Gaia artığından, doymuş çekirdekte 0.3 piksel
varsayımından alınır. "Bilimsel olarak doğrulandı" basamağı kodda sabit olarak `False`'tur.

## D-011 — WISE 0855 "seçilemedi" olarak raporlanır (2026-11-14)
Öngörülen konumlardaki zayıf akı (≈4σ) bir arka plan yıldızıyla (G=16.3, 4.5″) karışıyor ve kısa dalga boyunda da
görülüyor. İlk yazılan "dalga boyu" öğretici görevi bu ölçümü yanıt anahtarı yapıyordu; veri desteklemediği için
atıldı ve RW Aurigae tayfına dayanan görevle değiştirildi.

## D-012 — Hazır hedeflerde tercih edilen dalga boyu (2026-11-14)
WISE 0855 için 4.86 µm (kaynak yalnızca ~4.5–5 µm'de parlak), RW Aurigae için 0.765 µm (daha uzun dalga boylarında
doyma/doğrusalsızlık bayrağı). Diğerlerinde otomatik seçim (en çok ziyaret, en uzun aralık).

## D-013 — Arşiv DR1'e geçti; hazır diziler yenilendi (2026-11-14)
 TAP sorgusu `spherex_qr2*` yerine `spherex_dr1*` döndürmeye başladı (hepsi 7.0.5). Hazır diziler,
spektrumlar, görevler ve raporlar güncel arşivden yeniden üretildi; eski diziler ve paylaşımlar silinmedi. Yol kalıbı
`drN` sürümlerini `qrN`'den öncelikli sayar. Spektrum önbelleğine 24 saatlik tazelik denetimi eklendi.

## D-014 — Hizalama denetimi dizi yayımlanmadan önce çalışır (2026-11-14)
Gaia sorgusu yeni konumlarda 30–85 s ekliyor. Bilimsel denetim öncelikli tutuldu; eşzamansız hâle getirmek açık iştir.

## D-016 — Git kaydı yerelde; dışa gönderim yok (2026-11-14)
İlk kayıt kullanıcının isteğiyle yapıldı (`15027bf`, yeni depo olduğu için doğrudan `master` dalına). Dışa gönderim
(push) istenmedi ve GitHub oturumu yok; depo yalnızca yereldedir.

## D-017 — Proje SPHERE-X deposunun köküne alındı (2026-11-14)
The imported source described a previous repository merge. Its source subdirectory
had a separate `.git` directory. BlinkSpace geçmişi `--allow-unrelated-histories`
ile birleştirildi: 14 Kasım tarihli kayıtlar değişmeden korundu, kullanıcının ilk kaydının üzerine yazılmadı.
`.claude/` (bilgisayara özgü başlatma ayarı) depodan çıkarıldı ve `.gitignore` içine eklendi.

## D-018 — Reusable class-specific Three.js models (2026-11-14)
The requested model additions use the live scene's own factory, with five named recipes
and exportable r170 ObjectLoader assets. Shared animation code preserves source metadata,
binary component attachment, illustrative pulsation and pause semantics after loading.
Standard Three lines replace custom Line2 materials inside the exported model. Irregular
shell vertices are baked into BufferGeometry before serialization. Magnetic arcs, funnel
flows, disk thickness and envelope density remain explicitly representative. No fluid
solution or measured surface/field map is claimed. OpenAI Codex produced this revision.


---

# SPHERE-X / QFIT integration decisions — 2026-11-14

1. **Canonical source and baseline.** Only `BlinkSpace-Web` is edited. Tag `baseline-pre-zip-ui` points to `77b4107`; the incoming delivered ZIP matched all 445 manifest entries. Scientific resources and seed are frozen by 141 SHA-256 checks. The development branch is `codex/zip-ui-qfit-ai`, following the workspace branch-prefix instruction.
2. **Latest supplied UI.** The integration prompt refers to an older Unity archive, but the user subsequently supplied `SPHERE-X-main (2).zip` and confirmed integration with QFIT. Its `BlinkSpace-UI/kaynak/v5` is the visual reference: navy palette, glass, typography, top navigation, dock, title, target tabs, callouts and time ruler. v5 identifies itself as a prototype; no Unity build is newly claimed. Source CSS/HTML/icons are kept under `frontend/design-reference/sphere-x-v5` with archive SHA `28616a0262b9e064444928e64191e2e6cbf0b89dced3f42a0d3bcc4008c380e2`.
3. **Science takes priority over prototype fiction.** The source prototype varies invented mass, luminosity, age and future phases. None of those is an adopted measured property for these five targets. The mass/fate control becomes the existing source-backed motion summary; the time ruler remains the 2000–2100 astrometric year, with 1/5/20 years per second. R/T callouts retain source classifications and unknowns; L/M callouts become distance/proper motion. The H–R affordance opens an explicitly labelled Gaia BP−RP/absolute-G diagram, not a model evolution track. Existing class-specific Three.js models, animations, radii, temperature mappings and science are reused unchanged.
4. **Layout translation.** The latest source is HTML/CSS, not UXML/USS; no Unity conversion is necessary. Source coordinates use 1440×810 at scale 1. Local variable fonts and extracted 21 root tokens are used, along with source-linked layout declarations. Long real object names wrap. Small screens reflow instead of shrinking a fixed desktop stage. Original DOM ids map to semantic `data-ui` regions; see UI inventory. This is a functional adaptation, not verified pixel-perfect parity.
5. **Keep the old UI.** `?ui=legacy` remains available and survives navigation, as does `embed=1`. Every old shell assertion is retained against this explicit legacy route; the former tests target its DOM/text and are not deleted. New default-shell tests independently cover targets, language, scientific sources/downloads, archive forms/progress, observations, analysis and navigation. API/data/model tests remain unchanged.
6. **Keyboard and languages.** Existing 1/2/3, P/Space, arrows, Home/End, +/−/0, B and ? remain. Ctrl/⌘K and / open search, H opens the diagram, S opens QFIT. M opens measurements outside observations; the existing observation marking shortcut keeps M in observations. All new copy has TR/EN forms; unsupported prototype science claims are rewritten. The original multi-step research tutorials remain in the task tab.
7. **QFIT integration route A.** Immutable Python source is vendored under `backend/vendor/qfit` with MIT license and a file manifest. The repository could not be accessed, so the actual supplied ZIP is pinned by SHA-256 (`49ed5600a68975d34eb7a188ed2f1be9782fa19a528adb8dc35f09efee38a091`), not an invented commit. The original agent, grounding checker, BM25 retriever and OpenAI Responses transport are reused through `assistant_qfit.py`. No separate service or public upstream QFIT routes are mounted.
8. **Provider preserved.** The supplied `.env.example` chooses OpenAI `gpt-5.4-mini`, reasoning `none`; those are retained. Real calls use server-side `OPENAI_API_KEY`, `store:false`, bounded output, four agent steps, timeout and an atomic daily SQLite request budget. A request budget bounds call count, not currency spend. Status says `configured_not_live_verified` until a real call is actually tried; configuration is not claimed as a successful paid-provider health test. Default is off. Local source cards are explicitly non-AI; missing provider/vendor does not break the app.
9. **Tool restrictions.** The upstream network/archive, candidate-write and arbitrary execution services are not mounted or registered. Only read-only local knowledge retrieval and validated proposals for the existing 12 UI commands are available. Archive requests are proposals for BlinkSpace's existing search workflow, with explicit user confirmation. Every proposed action requires a button click; the server never executes it. Client-reported results are sent with the next turn as data, not treated as independently verified outcomes. Canonical target data are retrieved on the server; UI context stays under 4 KB and excludes note/edit credentials.
10. **Dependencies.** The adapter's runtime uses already-pinned FastAPI/Pydantic/httpx; no OpenAI SDK or Gemini dependency is added. `python-dotenv==1.2.4` is the only additional runtime package, pinned in both requirement files so the macOS launcher reads local `.env` as data, never as shell code. `pytest-asyncio==1.5.0` is a pinned test dependency. Optional upstream service audit dependencies are separately recorded, not required to run BlinkSpace. Fonts ship locally with OFL licenses. No CDN, CSP relaxation or new public port.
11. **Artwork provenance.** QFIT bird PNGs are copied unchanged under its supplied MIT license; the beak-pull, thinking and speaking states are retained. Supplied SPHERE-X UI artwork is user-provided reference material; its archive has no standalone root license, so this local handoff makes no claim of a separate MIT grant for that artwork. No public redistribution/deployment is performed. Existing third-party notices and font licenses remain.
12. **Acceptance limits.** A prior saved browser-access denial prevented preview/GPU checks. No browser, headless or CDP workaround was used. Source-reference screenshots are not new application screenshots. Desktop/mobile pixel fidelity, actual GPU rendering and FPS remain unverified. The reviewed seven-slide deck is preserved as a historical demo, not relabelled as a new-UI screenshot review. The user subsequently supplied an OpenAI key. It is stored only in an ignored owner-readable local `.env`; the distributed default remains off. Real-provider evaluation is separately recorded, never conflated with offline fixtures. No push, publishing or competition submission.

13. **Baseline API capture correction.** The original `/openapi.json` capture was the SPA HTML fallback. Before restarting the old server, its actual `/api/openapi.json` was recovered; it contains only the two baseline assistant routes. This corrected original schema is frozen in `tools/baseline/openapi.json`; comparison reports three added paths and no removed/changed fields.

14. **Live semantic review.** Ten QFIT answers returned sources without unsupported-number flags. Manual review found an RW Aur adoption/source distinction error and an omitted R Dra uncertainty. Prompt rules now explicitly separate adopted/computed from representative/null and require uncertainties; two live follow-up answers corrected those cases. Reports retain the finding rather than calling the original run error-free.

15. **Live proposal check.** An initial natural-language command request was described in prose without a tool call. The highest-priority prompt now explicitly requires the `propose_ui_command` wrapper for allowed UI changes. A real-provider retry emitted the validated `set_year` proposal for 2050; it was not executed in the browser. Fixed mock search arguments to the already-declared string coordinate schema.

16. **Byte-exact vendor checkout.** Git text normalization would alter 83 CRLF source files from the supplied archive. A scoped `.gitattributes` rule disables normalization for `backend/vendor/qfit/**`; all 198 staged source blobs were checked against the original manifest. The adapter remains outside the immutable vendor tree.

## Three.js revision — 2026-11-14

The user requested animation/framing fixes and explicitly selected both observation time and separate source-backed stellar evolution. Implemented distinct clocks, unobstructed canvas layout, detail/context framing, correct sky depth occlusion, published MIST/BHAC15/ATMO comparison tracks, and coordinate-based catalogue search. No target mass or age is inferred from those comparison tracks. No new runtime dependency, image synthesis, SPHEREx interpolation or backend science-file edit is involved. See docs/EVOLUTION_EXPLORER.md.

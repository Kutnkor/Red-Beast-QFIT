"""Öğretici görevleri **gerçek ölçümlerden** üretir ve yanıt anahtarını veriden doğrular.

Kullanım:  python -m tools.build_tutorials      (önce: python -m tools.prepare_presets)

Her soru görevinin doğru yanıtı, hazır dizilerde `blinkspace.measure` ile yapılan ölçüme bağlıdır. Ölçüm
yanıtı desteklemiyorsa görev üretilmez (belirsiz örneğe kesin cevap atanmaz) ve neden yazdırılır.
Çıktı: `blinkspace/resources/tutorials.json` (içinde doğrulama kanıtı `evidence` alanında durur).
Bu görevlerde sentetik veri kullanılmaz (`synthetic: false`).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from blinkspace.analysis import Analysis
from blinkspace.config import PIPELINE_VERSION, load_settings
from blinkspace.db import Database
from blinkspace.measure import measure_target
from blinkspace.pipeline import Pipeline
from blinkspace.targets import RESOURCES, load_targets
from blinkspace.wavelength import WaveModel

OUT = RESOURCES / "tutorials.json"
IRSA = {"label": "SPHEREx Quick Release Spectral Images (IRSA, doi:10.26131/IRSA629)", "url": "https://irsa.ipac.caltech.edu/Missions/spherex.html"}
SIMBAD = {"label": "SIMBAD (CDS) — katalog konumu ve özdevinim", "url": "https://simbad.cds.unistra.fr/simbad/"}
EXPSUPP = {"label": "SPHEREx Explanatory Supplement (bayrak tanımları)", "url": "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp_QR.pdf"}


def compass(e: float, n: float) -> str:
    if abs(n) >= abs(e):
        return "north" if n > 0 else "south"
    return "east" if e > 0 else "west"


def main() -> None:
    s = load_settings()
    db = Database(s.db_path)
    targets = load_targets()
    pipe = Pipeline(s, db, WaveModel.load(RESOURCES / "wave_model.json"), targets)
    an = Analysis(s, db, pipe)
    presets = db.get_meta("preset_sequences", {})
    seqs = {tid: db.get_sequence(sid) for tid, sid in presets.items()}
    meas = {tid: measure_target(an, seq, targets[tid]) for tid, seq in seqs.items() if seq}
    tutorials: list[dict] = []
    skipped: list[str] = []

    # 1) Başlangıç görevi (yönlendirmeli; yanıt anahtarı yok)
    tutorials.append({
        "id": "start", "kind": "guided", "target_id": "barnard", "synthetic": False,
        "title": {"tr": "İlk gözlemin", "en": "Your first observation"},
        "summary": {"tr": "Gerçek bir SPHEREx dizisi aç, kareler arasında gez, bir nokta işaretle ve paylaş.",
                    "en": "Open a real SPHEREx sequence, step through frames, mark a point and share it."},
        "steps": [
            {"id": "open", "event": "sequence_opened", "text": {"tr": "Barnard Yıldızı dizisini aç.", "en": "Open the Barnard's Star sequence."}},
            {"id": "step", "event": "frame_changed", "text": {"tr": "Sonraki kareye geç ve tarihin değiştiğini gör.", "en": "Go to the next frame and watch the date change."}},
            {"id": "mark", "event": "mark_added", "text": {"tr": "Dikkatini çeken bir noktayı işaretle ve bir sınıf seç.", "en": "Mark a point that catches your eye and pick a class."}},
            {"id": "share", "event": "observation_shared", "text": {"tr": "Gözlemini kaydet ve bağlantısını kopyala.", "en": "Save your observation and copy its link."}},
        ],
        "frames_used": [f["obs_id"] for f in seqs["barnard"]["frames"]], "sources": [IRSA],
    })

    # 2) Hareketi fark et — Eps Indi B (doymamış, ölçülmüş hareket)
    m, seq = meas["eps-indi-b"], seqs["eps-indi-b"]
    mo = m["motion"]
    if mo and mo["significant"] and mo["consistent_with_catalog"]:
        ans = compass(mo["fit_pm_e_arcsec_yr"], mo["fit_pm_n_arcsec_yr"])
        diag = ("south" if mo["fit_pm_n_arcsec_yr"] < 0 else "north") + ("east" if mo["fit_pm_e_arcsec_yr"] > 0 else "west")
        names = {"northeast": ("Kuzeydoğu (yukarı-sol)", "North-east (up-left)"), "northwest": ("Kuzeybatı (yukarı-sağ)", "North-west (up-right)"),
                 "southeast": ("Güneydoğu (aşağı-sol)", "South-east (down-left)"), "southwest": ("Güneybatı (aşağı-sağ)", "South-west (down-right)")}
        det = [r for r in m["frames"] if r["method"] == "flux_weighted_centroid"]
        tutorials.append({
            "id": "spot-motion", "kind": "quiz", "target_id": "eps-indi-b", "synthetic": False,
            "title": {"tr": "Hareketi fark et", "en": "Spot the motion"},
            "summary": {"tr": "İlk ve son kare arasında yer değiştiren kaynağı bul.", "en": "Find the source that changes place between the first and last frame."},
            "question": {"tr": f"İlk kare ({det[0]['date'][:10]}) ile son kareyi ({det[-1]['date'][:10]}) art arda göster. Alan merkezindeki kaynak hangi yöne kayıyor? (Kuzey yukarıda, doğu solda.)",
                         "en": f"Blink the first frame ({det[0]['date'][:10]}) against the last ({det[-1]['date'][:10]}). Which way does the source at the field centre move? (North is up, east is left.)"},
            "options": [{"id": k, "text": {"tr": v[0], "en": v[1]}} for k, v in names.items()] + [{"id": "none", "text": {"tr": "Kaymıyor", "en": "It does not move"}}],
            "answer_id": diag,
            "explanation": {
                "tr": f"Ölçüm: {mo['n_points']} karedeki konumlara doğrusal uyum yılda ({mo['fit_pm_e_arcsec_yr']:+.2f}″ doğu, {mo['fit_pm_n_arcsec_yr']:+.2f}″ kuzey) ± {mo['fit_pm_err_arcsec_yr']}″ veriyor; toplam kayma {mo['measured_shift_px']} piksel. Katalog özdevinimi ({mo['catalog_pm_e_arcsec_yr']:+.2f}″, {mo['catalog_pm_n_arcsec_yr']:+.2f}″) ile uyumlu. Kayma yaklaşık bir piksel olduğu için fark küçüktür: yakınlaştır ve yalnızca iki uç kareyi karşılaştır. Çevredeki yıldızlar yerinde kalır.",
                "en": f"Measurement: a linear fit to the positions in {mo['n_points']} frames gives ({mo['fit_pm_e_arcsec_yr']:+.2f}″ east, {mo['fit_pm_n_arcsec_yr']:+.2f}″ north) ± {mo['fit_pm_err_arcsec_yr']}″ per year; the total shift is {mo['measured_shift_px']} pixels. This agrees with the catalogue proper motion ({mo['catalog_pm_e_arcsec_yr']:+.2f}″, {mo['catalog_pm_n_arcsec_yr']:+.2f}″). The shift is only about one pixel, so zoom in and compare just the two end frames. The surrounding stars stay put."},
            "view": {"mode": "blink", "frame_a": det[0]["index"], "frame_b": det[-1]["index"]},
            "evidence": {"sequence_id": seq["id"], "pipeline_version": PIPELINE_VERSION, "motion": mo},
            "frames_used": [seq["frames"][r["index"]]["obs_id"] for r in det], "sources": [IRSA, SIMBAD],
        })
    else:
        skipped.append("spot-motion: Eps Indi B hareketi anlamlı/katalogla uyumlu ölçülemedi")

    # 3) Parlaklık değişimini incele — RW Aur (karşılaştırma yıldızlarıyla doğrulanmış)
    m, seq = meas["rw-aur"], seqs["rw-aur"]
    b = m["brightness"]
    if b and m["status"]["change_kind"] == "brightness" and b["normalized_by_comparison_stars"]:
        pts = b["points"]
        brighter_last = pts[-1]["flux_mjy"] > pts[0]["flux_mjy"]
        tutorials.append({
            "id": "brightness-change", "kind": "quiz", "target_id": "rw-aur", "synthetic": False,
            "title": {"tr": "Parlaklık değişimini incele", "en": "Examine a brightness change"},
            "summary": {"tr": "Yerinde duran ama parlaklığı değişen bir yıldızı ışık eğrisiyle doğrula.", "en": "Confirm with the light curve a star that stays put but changes brightness."},
            "question": {"tr": f"Alan merkezindeki yıldız (RW Aurigae) {pts[0]['date'][:10]} ile {pts[-1]['date'][:10]} arasında nasıl değişiyor? Önce kareleri karşılaştır, sonra ışık eğrisi paneline bak.",
                         "en": f"How does the star at the field centre (RW Aurigae) change between {pts[0]['date'][:10]} and {pts[-1]['date'][:10]}? Compare the frames first, then open the light-curve panel."},
            "options": [{"id": "brighter", "text": {"tr": "Belirgin biçimde parlaklaşıyor", "en": "It brightens markedly"}},
                        {"id": "fainter", "text": {"tr": "Belirgin biçimde sönükleşiyor", "en": "It fades markedly"}},
                        {"id": "same", "text": {"tr": "Değişmiyor", "en": "It does not change"}},
                        {"id": "moves", "text": {"tr": "Yer değiştiriyor", "en": "It moves"}}],
            "answer_id": "brighter" if brighter_last else "fainter",
            "explanation": {
                "tr": f"Ham piksellerdeki açıklık akısı {b['lam_um']:.3f} µm'de {pts[0]['flux_mjy']:.0f} → {pts[-1]['flux_mjy']:.0f} mJy ({b['max_over_min']}×, {b['diff_sigma']}σ). Aynı karelerdeki {m['comparison']['n_stars']} karşılaştırma yıldızı %{100 * m['comparison']['systematic_frac']:.0f} içinde sabit kalıyor; yani değişim görüntü ölçeğinden kaynaklanmıyor. Konum değişmiyor. Bu bir \"değişim görülüyor\" sonucudur: Hızlı Bakış kalibrasyonu ve {b['wavelength_tolerance_used']} bant genişliğine kadar dalga boyu kayması nedeniyle bilimsel doğrulama değildir.",
                "en": f"Aperture flux on the native pixels at {b['lam_um']:.3f} µm goes {pts[0]['flux_mjy']:.0f} → {pts[-1]['flux_mjy']:.0f} mJy ({b['max_over_min']}×, {b['diff_sigma']}σ). The {m['comparison']['n_stars']} comparison stars in the same frames stay constant to within {100 * m['comparison']['systematic_frac']:.0f}%, so the change is not an image-scale effect. The position does not change. This is a \"change seen\" result, not a scientific confirmation: the calibration is Quick Release and wavelength offsets of up to {b['wavelength_tolerance_used']} bandwidths are present."},
            "view": {"mode": "side_by_side", "frame_a": 0, "frame_b": len(seq["frames"]) - 1},
            "evidence": {"sequence_id": seq["id"], "pipeline_version": PIPELINE_VERSION, "brightness": b, "comparison": m["comparison"]},
            "frames_used": [f["obs_id"] for f in seq["frames"]], "sources": [IRSA],
        })
    else:
        skipped.append("brightness-change: RW Aur parlaklık değişimi ölçütleri sağlamadı")

    # 4) Görüntü hatasını tanı — R Dra doymuş çekirdek (bayraklarla doğrulanır)
    m, seq = meas["r-dra"], seqs["r-dra"]
    sat = [r for r in m["frames"] if r["method"] == "saturated_core_centroid"]
    if len(sat) == len(m["frames"]) and all(r["photometry"]["reason"] == "invalid_pixels_in_aperture" for r in sat):
        flags = sorted({k for r in sat for k in r["photometry"]["flags"]})
        tutorials.append({
            "id": "recognise-artifact", "kind": "quiz", "target_id": "r-dra", "synthetic": False,
            "title": {"tr": "Görüntü hatasını tanı", "en": "Recognise an image artefact"},
            "summary": {"tr": "Çok parlak bir yıldızın ortasındaki \"delik\" gerçek mi?", "en": "Is the \"hole\" in the middle of a very bright star real?"},
            "question": {"tr": "R Draconis'in tam ortası desenli (ölçüm yok) görünüyor ve çevresinde turuncu kalite katmanı var. Bu neyi gösterir?",
                         "en": "The very centre of R Draconis is hatched (no measurement) and surrounded by the orange quality layer. What does this show?"},
            "options": [{"id": "saturation", "text": {"tr": "Yıldız dedektörü doyuruyor; merkez pikseller ölçülemiyor", "en": "The star saturates the detector; the central pixels cannot be measured"}},
                        {"id": "dark-object", "text": {"tr": "Yıldızın önünden karanlık bir cisim geçiyor", "en": "A dark object is passing in front of the star"}},
                        {"id": "vanished", "text": {"tr": "Yıldız kaybolmuş", "en": "The star has vanished"}},
                        {"id": "moving", "text": {"tr": "Hızlı hareket eden bir kaynak", "en": "A fast-moving source"}}],
            "answer_id": "saturation",
            "explanation": {
                "tr": f"{len(sat)} karenin tamamında yıldızın çekirdek pikselleri {', '.join(flags)} bayraklarını taşıyor: yıldız SPHEREx için fazla parlak, merkez pikseller doymuş ve \"ölçüm yok\" olarak korunuyor (sıfırla doldurulmuyor). Bu yüzden R Draconis bir Mira değişeni olduğu hâlde bu görüntülerden parlaklık değişimi ölçülemiyor. Çevredeki BLOOM/HALO bayrakları da parlak yıldızın saçtığı ışığı işaret eder.",
                "en": f"In all {len(sat)} frames the core pixels of the star carry the flags {', '.join(flags)}: the star is too bright for SPHEREx, the central pixels are saturated and are kept as \"no measurement\" (never filled with zero). That is why, although R Draconis is a Mira variable, its brightness change cannot be measured from these images. The BLOOM/HALO flags around it mark light scattered by the bright star."},
            "view": {"mode": "blink", "layers": ["mask"]},
            "evidence": {"sequence_id": seq["id"], "pipeline_version": PIPELINE_VERSION, "n_frames": len(sat), "core_flags": flags,
                         "core_pixels": [r.get("n_core_pixels") for r in sat]},
            "frames_used": [f["obs_id"] for f in seq["frames"]], "sources": [IRSA, EXPSUPP],
        })
    else:
        skipped.append("recognise-artifact: R Dra çekirdeği tüm karelerde doymuş bulunmadı")

    # 5) Neden uygun dalga boyu gerekir — RW Aur tayfı (aynı günlerde farklı dalga boylarında farklı akı)
    from blinkspace.spectrum import load_spectrum
    spectra = db.get_meta("preset_spectra", {}).get("rw-aur", [])
    sp = load_spectrum(s, spectra[0]["result_id"]) if spectra else None
    rel = [p for p in (sp["points"] if sp else []) if p["valid"] and p.get("reliable")]
    if len(rel) >= 5:
        rel.sort(key=lambda p: p["lam_um"])
        lo = rel[0]
        hi = max((p for p in rel if 0.93 <= p["lam_um"] <= 1.02), key=lambda p: p["flux_mjy"], default=None)
        bracket = [p for p in rel if p["lam_um"] > 1.02]
    else:
        lo = hi = None
        bracket = []
    if lo and hi and hi["flux_mjy"] / lo["flux_mjy"] >= 1.5 and abs(hi["mjd"] - lo["mjd"]) <= 5.0:
        ratio = hi["flux_mjy"] / lo["flux_mjy"]
        extra_tr = extra_en = ""
        if bracket:
            q = bracket[0]
            extra_tr = f" Uzun dalga boylarında yıldız başka günlerde de parlak: {q['date'][:10]} tarihinde {q['lam_um']:.2f} µm'de {q['flux_mjy']:.0f} mJy."
            extra_en = f" At long wavelengths the star is bright on other days too: {q['flux_mjy']:.0f} mJy at {q['lam_um']:.2f} µm on {q['date'][:10]}."
        tutorials.append({
            "id": "why-wavelength", "kind": "quiz", "target_id": "rw-aur", "synthetic": False,
            "title": {"tr": "Neden uygun dalga boyu gerekir?", "en": "Why the right wavelength matters"},
            "summary": {"tr": "Aynı yıldız, birkaç gün arayla, iki farklı dalga boyu: parlaklık farkı zamandan mı?", "en": "Same star, a few days apart, two different wavelengths: is the brightness difference due to time?"},
            "question": {
                "tr": f"SPHEREx, RW Aurigae'yi {lo['date'][:10]} tarihinde {lo['lam_um']:.2f} µm'de {lo['flux_mjy']:.0f} mJy, {hi['date'][:10]} tarihinde {hi['lam_um']:.2f} µm'de {hi['flux_mjy']:.0f} mJy ölçtü. Bu iki kare yan yana konursa yıldız {abs(hi['mjd'] - lo['mjd']):.0f} günde {ratio:.1f} katına çıkmış gibi görünür. Doğru yorum hangisi?",
                "en": f"SPHEREx measured RW Aurigae at {lo['flux_mjy']:.0f} mJy at {lo['lam_um']:.2f} µm on {lo['date'][:10]}, and {hi['flux_mjy']:.0f} mJy at {hi['lam_um']:.2f} µm on {hi['date'][:10]}. Put side by side, the star seems to brighten {ratio:.1f}× in {abs(hi['mjd'] - lo['mjd']):.0f} days. Which reading is right?"},
            "options": [
                {"id": "not-comparable", "text": {"tr": "Bu iki kare zaman karşılaştırması olarak kullanılamaz: dalga boyları farklı, fark yıldızın rengini gösterir", "en": "These two frames cannot be used as a time comparison: the wavelengths differ, so the difference shows the star's colour"}},
                {"id": "real-doubling", "text": {"tr": "Yıldız gerçekten birkaç günde bu kadar parladı", "en": "The star really brightened that much in a few days"}},
                {"id": "detector-fault", "text": {"tr": "İkinci karede dedektör hatası var", "en": "The second frame has a detector fault"}},
                {"id": "moved", "text": {"tr": "Yıldız yer değiştirdiği için daha parlak göründü", "en": "The star looks brighter because it moved"}}],
            "answer_id": "not-comparable",
            "explanation": {
                "tr": f"SPHEREx'te her dedektör pikseli farklı bir dalga boyu görür; yıldız dedektör üzerinde kaydıkça tayfı {sp['span_days']:.0f} güne yayılarak taranır. {lo['lam_um']:.2f} µm ile {hi['lam_um']:.2f} µm arasındaki {ratio:.1f} katlık fark yıldızın tayf eğimidir (kırmızıya doğru parlaklaşır).{extra_tr} Bu yüzden BlinkSpace zaman dizisine yalnızca hedefteki dalga boyu aynı olan kareleri alır (bant genişliğinin yarısı içinde) ve farklı dalga boylarını \"dalga boyu keşfi\" olarak ayrı gösterir. Spektrum panelinde bu noktaların tarihleriyle birlikte tamamını görebilirsin.",
                "en": f"In SPHEREx every detector pixel sees a different wavelength; as the star drifts across the detector its spectrum is scanned over {sp['span_days']:.0f} days. The {ratio:.1f}× difference between {lo['lam_um']:.2f} µm and {hi['lam_um']:.2f} µm is the star's spectral slope (it is brighter toward the red).{extra_en} That is why BlinkSpace only puts frames into a time sequence when the wavelength at the target is the same (within half a bandwidth), and shows other wavelengths separately as \"wavelength exploration\". The spectrum panel shows all of these points with their dates."},
            "view": {"mode": "blink"},
            "evidence": {"spectrum_id": sp["id"], "pipeline_version": PIPELINE_VERSION, "date_window": sp["date_window"],
                         "point_short": {k: lo[k] for k in ("obs_id", "date", "lam_um", "flux_mjy", "err_mjy")},
                         "point_long": {k: hi[k] for k in ("obs_id", "date", "lam_um", "flux_mjy", "err_mjy")}, "ratio": round(ratio, 2),
                         "rejected_alternative": "WISE 0855: kısa dalga boyunda da öngörülen konumda akı ölçüldü (kaynak karışması); yanıt anahtarı desteklenmediği için kullanılmadı"},
            "frames_used": [lo["obs_id"], hi["obs_id"]], "sources": [IRSA],
        })
    else:
        skipped.append("why-wavelength: RW Aur tayfında yeterli güvenilir nokta/oran yok (python -m tools.preset_spectra)")

    doc = {"generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "pipeline_version": PIPELINE_VERSION,
           "note": "Yanıt anahtarları hazır dizilerdeki gerçek ölçümlerden üretilmiştir (tools/build_tutorials.py). Sentetik veri yoktur.",
           "skipped": skipped, "tutorials": tutorials}
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    for t in tutorials:
        print(f"  {t['id']}: {t['kind']} → {t.get('answer_id', '—')}")
    for sk in skipped:
        print("  ATLANDI:", sk)
    print("yazıldı:", OUT)


if __name__ == "__main__":
    main()

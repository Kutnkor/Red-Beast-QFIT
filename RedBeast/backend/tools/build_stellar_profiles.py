"""Build the cited, curated stellar-model contract without inventing observations.

Sources were read on 2026-11-14. Literature values are transcribed with table/section
locators. The small GCVS result is also preserved byte-for-byte. Visual display choices
are explicitly assumed/representative and are never fed into SPHEREx measurements.
Run: PYTHONPATH=backend python -m tools.build_stellar_profiles
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path

from .science_sources import write_json

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT / "backend" / "blinkspace" / "resources"
CHECKED = "2026-11-14"


def source(id, title, url, locator, **extra):
    return dict(id=id, title=title, url=url, locator=locator, checked_on=CHECKED, **extra)


def parameter(value, unit, classification, source_ids, note, note_tr, **extra):
    return dict(value=value, unit=unit, classification=classification, source_ids=source_ids,
                note=note, note_tr=note_tr, **extra)


def unknown(unit, note="No adopted object-specific estimate.", note_tr="Hedefe özgü bir değer benimsenmedi."):
    return parameter(None, unit, "unknown", [], note, note_tr)


def phenomenon(id, classification, source_ids, note, note_tr, **extra):
    return dict(id=id, enabled=True, classification=classification, source_ids=source_ids,
                note=note, note_tr=note_tr, **extra)


def rendering(color_mode="blackbody_approximation", **extra):
    return {
        "radius_mode": "square_root_compressed", "radius_formula": "sqrt(radius_solar)",
        "unknown_radius_mode": "representative_one_display_unit",
        "time_mode": "illustrative", "color_mode": color_mode,
        "classification": "assumed", "source_ids": [],
        "astrometric_year_changes_stellar_properties": False,
        "measured_surface_map": False, "hydrodynamic_simulation": False,
        "note": "Surface patterns, flow geometry, contrast and animation speed are illustrative. They are not telescope images, fitted fluid simulations or a stellar-evolution clock.",
        "note_tr": "Yüzey desenleri, akış geometrisi, kontrast ve animasyon hızı temsilidir. Teleskop görüntüsü, nicel akış çözümü veya yıldız evrimi saati değildir.",
        **extra,
    }


def gcvs_source():
    path = RESOURCES / "source_data" / "r-dra-gcvs.tsv"
    raw = path.read_bytes()
    lines = raw.decode("utf-8").splitlines()
    columns = {line.split("\t")[1] for line in lines if line.startswith("#Column\t")}
    if not {"GCVS", "Period", "VarType", "SpType"}.issubset(columns):
        raise ValueError("GCVS schema changed")
    table = [line for line in lines if line and not line.startswith("#")]
    rows = list(csv.DictReader(io.StringIO("\n".join([table[0], *table[3:]])), delimiter="\t"))
    if len(rows) != 1 or rows[0]["GCVS"].strip() != "R Dra" or rows[0]["VarType"].strip() != "M":
        raise ValueError("GCVS result does not identify the requested Mira R Dra")
    query_url = next(line.split("=", 1)[1].split("\t", 1)[0] for line in lines if line.startswith("#INFO\trequest="))
    return float(rows[0]["Period"]), source(
        "gcvs-r-dra", "General Catalogue of Variable Stars 5.1 — R Dra", query_url,
        "B/gcvs/gcvs_cat: R Dra, Period [d], VarType M; catalogue version October 2020",
        bibcode="2017ARep...61...80S", raw_path="source_data/r-dra-gcvs.tsv",
        response_sha256=hashlib.sha256(raw).hexdigest(), response_bytes=len(raw),
    )


def build_catalogue():
    period, gcvs = gcvs_source()
    barnard = {
        "target_id": "barnard", "name": "Barnard's Star", "type": "M-dwarf main-sequence star", "stellar_class": "M_dwarf",
        "parameters": {
            "radius_solar": parameter(.187, "R_sun", "measured", ["barnard-2024"],
                "Interferometric radius adopted in Table 2; uncertainty is 0.001 solar radii.",
                "Tablo 2'de benimsenen girişimölçer yarıçapı; belirsizlik 0,001 Güneş yarıçapı.", uncertainty=.001, method="interferometry_and_parallax"),
            "teff_k": parameter(3195, "K", "measured", ["barnard-2024"],
                "ESPRESSO spectroscopic model fit; different spectral analyses give different estimates.",
                "ESPRESSO tayfına model uyumu; farklı tayf analizleri farklı tahminler verir.", uncertainty=28, method="spectroscopic_model_fit"),
            "period_days": unknown("d", "No radial-pulsation period is adopted.", "Bir radyal titreşim dönemi benimsenmedi."),
            "rotation_period_days": parameter(142, "d", "measured", ["barnard-2024"],
                "Activity-model rotation estimate, not the animation speed.", "Etkinlik modelinden dönüş tahmini; animasyon hızı değildir.", uncertainty=9),
        },
        "phenomena": [
            phenomenon("corona", "representative", ["barnard-flares"],
                "X-ray and UV flares were detected in 2019; the drawn coronal shell and magnetic geometry are a class illustration.",
                "2019'da X-ışını ve morötesi parlamalar ölçüldü; çizilen korona ve manyetik geometri bu yıldız sınıfını temsil eder."),
            phenomenon("wind", "representative", ["barnard-wind"],
                "A qualitative magnetized-wind template; no wind speed, mass-loss rate or measured field map is adopted.",
                "Manyetize rüzgârın nitel temsili; rüzgâr hızı, kütle kaybı oranı veya ölçülmüş alan haritası kullanılmıyor."),
        ],
        "rendering": rendering(),
        "sources": [
            source("barnard-2024", "González Hernández et al. (2024) — A sub-Earth-mass planet orbiting Barnard's star", "https://arxiv.org/html/2410.00569v1", "Table 2 and section 3", doi="10.1051/0004-6361/202451311"),
            source("barnard-flares", "NASA Chandra (2020) — GJ 699: X-ray and ultraviolet flares", "https://www.chandra.si.edu/photo/2020/barnards/index.html", "2019 Chandra and Hubble observations; France et al. 2020"),
            source("barnard-wind", "Alvarado-Gómez et al. (2019) — Breezing through the space environment of Barnard's Star b", "https://arxiv.org/abs/1901.00219", "Stellar-wind model; used only to motivate a qualitative template", doi="10.3847/2041-8213/ab1489"),
        ],
        "caveats": ["The surface and plasma are not resolved images of Barnard's Star.", "Changing the sky year changes space motion only, not its temperature or stellar age.", "The 2019 wind study concerned an older planet candidate; no planet or planetary claim is used here."],
        "caveats_tr": ["Yüzey ve plazma, Barnard Yıldızı'nın çözünürlüklü görüntüleri değildir.", "Gökyüzü yılı yalnızca uzaydaki konumu değiştirir; sıcaklığı veya evrimsel yaşı değiştirmez.", "2019 rüzgâr çalışması eski bir gezegen adayıyla ilgiliydi; burada gezegen gösterilmiyor veya gezegen iddiası kullanılmıyor."],
    }
    epsilon = {
        "target_id": "eps-indi-b", "name": "Epsilon Indi Ba/Bb", "type": "T-dwarf binary", "stellar_class": "T_dwarf",
        "parameters": {
            "radius_solar": unknown("R_sun", "A binary system has no single stellar radius.", "İkili sistemin tek bir yıldız yarıçapı yoktur."),
            "teff_k": unknown("K", "Ba and Bb have separate atmospheric temperatures.", "Ba ve Bb'nin atmosfer sıcaklıkları ayrıdır."),
            "period_days": unknown("d", "No reliable rotation period is adopted.", "Güvenilir bir dönüş dönemi benimsenmedi."),
            "orbital_period_years": parameter(11.0197, "Julian yr", "measured", ["eps-orbit"], "Relative astrometric orbital fit, Table 4.", "Göreli astrometrik yörünge uyumu, Tablo 4.", uncertainty=.0076),
            "binary_semimajor_axis_au": parameter(2.4058, "au", "computed", ["eps-orbit"], "Relative-orbit semimajor axis from astrometry and parallax; not instantaneous separation.", "Astrometri ve paralakstan göreli yörüngenin büyük yarı ekseni; anlık ayrıklık değildir.", uncertainty=.0040),
            "orbital_eccentricity": parameter(.54042, "dimensionless", "measured", ["eps-orbit"], "Orbital fit, Table 4.", "Yörünge uyumu, Tablo 4.", uncertainty=.00063),
            "orbital_inclination_deg": parameter(77.082, "deg", "measured", ["eps-orbit"], "Relative-orbit inclination to the sky plane; not either spin-axis orientation.", "Göreli yörüngenin gökyüzü düzlemine eğimi; yıldızların dönme ekseni yönü değildir.", uncertainty=.032),
        },
        "components": [
            {"id": "ba", "name": "Epsilon Indi Ba", "stellar_class": "T_dwarf", "parameters": {
                "radius_solar": unknown("R_sun"),
                "teff_k": parameter(1320, "K", "computed", ["eps-atmospheres"], "Display midpoint of the 1300–1340 K atmospheric-model range, not a new measurement.", "1300–1340 K atmosfer modeli aralığının gösterim orta noktası; yeni ölçüm değildir.", range=[1300, 1340], method="BT-Settl_spectral_model_fit_midpoint"),
            }},
            {"id": "bb", "name": "Epsilon Indi Bb", "stellar_class": "T_dwarf", "parameters": {
                "radius_solar": unknown("R_sun"),
                "teff_k": parameter(910, "K", "computed", ["eps-atmospheres"], "Display midpoint of the 880–940 K atmospheric-model range, not a new measurement.", "880–940 K atmosfer modeli aralığının gösterim orta noktası; yeni ölçüm değildir.", range=[880, 940], method="BT-Settl_spectral_model_fit_midpoint"),
            }},
        ],
        "phenomena": [
            phenomenon("clouds", "computed", ["eps-clouds"], "Cloud changes are an interpretation of unresolved brightness variability, mostly associated with Ba; bands and rotation are illustrative.", "Bulut değişimi, çoğunlukla Ba'ya bağlanan çözünmemiş parlaklık değişiminin yorumudur; bantlar ve dönüş temsilidir."),
            phenomenon("binary_orbit", "measured", ["eps-orbit"], "The binary orbit is measured; displayed separation, component size and accelerated phase are schematic.", "İkili yörünge ölçülmüştür; gösterilen ayrıklık, bileşen boyutları ve hızlandırılmış faz şematiktir."),
        ],
        "rendering": rendering("illustrative_cloud_contrast", unknown_radius_mode="representative_equal_components", component_display_radius=.55),
        "sources": [
            source("eps-atmospheres", "King et al. (2010) — Epsilon Indi Ba, Bb: a detailed study", "https://arxiv.org/abs/0911.3143", "Abstract: BT-Settl temperature ranges differ from evolutionary-model temperatures", doi="10.1051/0004-6361/200912981"),
            source("eps-clouds", "Hitchcock et al. (2020) — Large-scale changes of cloud coverage in Epsilon Indi Ba/Bb", "https://academic.oup.com/mnras/article/495/4/3881/5838753", "Sections 4.1–4.3: no convincing rotation period or lightning detection; cloud interpretation"),
            source("eps-orbit", "Chen et al. (2022) — Precise Dynamical Masses of Epsilon Indi Ba and Bb", "https://arxiv.org/pdf/2205.08077", "Table 4; section 6.3"),
        ],
        "caveats": ["SPHEREx does not resolve Ba from Bb.", "Component radii are unadopted; their display sizes are representative.", "The cloud pattern is not a measured map. Atmospheric and evolutionary models give different temperatures."],
        "caveats_tr": ["SPHEREx, Ba ile Bb'yi birbirinden ayıramaz.", "Bileşen yarıçapları benimsenmedi; ekrandaki boyutları temsilidir.", "Bulut deseni ölçülmüş bir harita değildir. Atmosfer ve evrim modelleri farklı sıcaklıklar verir."],
    }
    wise = {
        "target_id": "wise-0855", "name": "WISE 0855−0714", "type": "Ultracool Y dwarf", "stellar_class": "Y_dwarf",
        "parameters": {
            "radius_solar": unknown("R_sun"),
            "teff_k": parameter(250, "K", "computed", ["wise-nasa", "wise-2025", "wise-2026"],
                "Historical approximate atmospheric-model reference (2014–2016). More recent model-dependent analyses use about 265–285 K; 250 K is not a current precision measurement.",
                "2014–2016 çalışmalarından yaklaşık atmosfer modeli referansı. Daha yeni, modele bağlı analizlerde yaklaşık 265–285 K kullanılır; 250 K güncel bir hassas ölçüm değildir.", approximate=True),
            "period_days": unknown("d", "No rotation period is adopted for this illustration.", "Bu temsil için dönüş dönemi benimsenmedi."),
        },
        "phenomena": [phenomenon("clouds", "computed", ["wise-nasa", "wise-2025", "wise-2026"],
            "Water-cloud interpretations depend on spectral models: 2025 MIRI found no clear ice-cloud signature; a September 2026 preprint supports patchy clouds. Spatial bands are illustrative.",
            "Su bulutu yorumu tayf modellerine bağlıdır: 2025 MIRI çalışması açık buz bulutu izi bulmadı; Eylül 2026 ön baskısı parçalı bulutları destekliyor. Uzaysal bantlar temsilidir.")],
        "rendering": rendering("dark_visible_light_placeholder", visible_self_emission="negligible", cloud_geometry="illustrative"),
        "sources": [
            source("wise-nasa", "NASA (2016) — Water-cloud evidence in WISE 0855", "https://science.nasa.gov/universe/exoplanets/astronomers-find-water-clouds-in-cold-jupiter-like-object/", "250 K model, infrared spectrum, explicitly arbitrary illustration colors"),
            source("wise-2025", "Kühnle et al. (2025) — Water depletion and 15NH3 with JWST/MIRI", "https://doi.org/10.1051/0004-6361/202452547", "Abstract and section 6: model dependence; no clear spectral water-ice signature"),
            source("wise-2026", "Miles et al. (2026 preprint) — Water Cloud and Chemical Modulations in the Coldest Brown Dwarf", "https://arxiv.org/html/2609.20664v1", "Time-series NIRSpec atmospheric-model comparison", publication_status="preprint"),
        ],
        "caveats": ["Visible color is arbitrary: this cold object is observed through infrared emission.", "The cloud map, radius and animation phase are illustrative.", "250 K is an older reference estimate; new spectral analyses are model dependent."],
        "caveats_tr": ["Görünür renk keyfidir; bu soğuk cisim kızılötesi yayımıyla gözlenir.", "Bulut haritası, yarıçap ve animasyon fazı temsilidir.", "250 K eski bir referans tahminidir; yeni tayf analizleri modele bağlıdır."],
    }
    rw = {
        "target_id": "rw-aur", "name": "RW Aurigae A", "type": "Accreting T Tauri star", "stellar_class": "T_Tauri", "modeled_component": "A",
        "parameters": {
            "radius_solar": parameter(1.80, "R_sun", "computed", ["rw-stellar"], "Radius derived from luminosity and effective temperature; sample-average log-radius uncertainty is about 0.3 dex, not a target-specific error bar.", "Işınım gücü ve etkin sıcaklıktan hesaplanan yarıçap; örneklem ortalaması log-yarıçap belirsizliği yaklaşık 0,3 dex, hedefe özgü hata çubuğu değildir.", method="luminosity_and_effective_temperature"),
            "teff_k": parameter(4870, "K", "measured", ["rw-stellar"], "Adopted spectroscopic parameter in Table 2 for the 2017-11-13 observation; no individual uncertainty is quoted in that row.", "2017-11-13 gözlemi için Tablo 2'de benimsenen tayfsal parametre; o satırda ayrı belirsizlik verilmemiştir.", observation_date="2017-11-13"),
            "period_days": unknown("d", "Irregular dimmings are not assigned a periodic clock.", "Düzensiz sönükleşmelere periyodik bir saat atanmıyor."),
            "disk_inclination_deg": parameter(55.51, "deg", "measured", ["rw-alma"], "2018 ALMA Band 6 outer-disk Gaussian fit; the inner disk may be misaligned.", "2018 ALMA Band 6 dış disk Gauss uyumu; iç disk farklı yöne eğilmiş olabilir.", uncertainty=.13),
            "disk_radius_au": parameter(21.28, "au", "computed", ["rw-alma"], "Band 6 Gaussian continuum radius, not a hard disk edge; the CO gas extends farther.", "Band 6 Gauss süreklilik yarıçapı; kesin disk kenarı değildir, CO gazı daha uzağa uzanır.", uncertainty=.03),
        },
        "phenomena": [
            phenomenon("disk", "measured", ["rw-alma"], "ALMA resolves a circumstellar disk and tidal material. Screen extent and particle density are schematic.", "ALMA çevresel diski ve gelgit maddesini çözümler. Ekrandaki genişlik ve parçacık yoğunluğu şematiktir."),
            phenomenon("jets", "measured", ["rw-jets"], "Jet emission is observed spectroscopically; drawn speeds, opening angle and knots are illustrative.", "Jet yayımı tayfsal olarak gözlenmiştir; çizilen hızlar, açılma açısı ve düğümler temsilidir."),
            phenomenon("dust_extinction", "computed", ["rw-dust"], "Occulting dust is a proposed explanation of dimming; no current extinction map is reconstructed.", "Sönükleşmenin açıklaması olarak örtücü toz önerilir; güncel bir sönüm haritası oluşturulmuyor."),
        ],
        "rendering": rendering(environment_scale="independently_compressed"),
        "sources": [
            source("rw-stellar", "Gangi et al. (2022) — GHOsT IV: accretion properties of Taurus-Auriga", "https://arxiv.org/pdf/2208.14895", "Table 2, RW Aur A row; section 5.1.1", doi="10.1051/0004-6361/202244042"),
            source("rw-alma", "Rodriguez et al. (2018) — Multiple Stellar Flybys Sculpting RW Aurigae", "https://doi.org/10.3847/1538-4357/aac08f", "Table 1: Band 6 Gaussian disk parameters", accessible_url="https://air.unimi.it/retrieve/dfa8b9a8-2097-748b-e053-3a05fe0a3a96/Rodriguez2018.pdf"),
            source("rw-jets", "Giannini et al. (2019) — GHOsT I: jet line emission", "https://arxiv.org/abs/1909.10392", "RW Aur A forbidden-line spectroscopy", doi="10.1051/0004-6361/201936085"),
            source("rw-dust", "Schneider et al. (2015) — Nature of the 2014–2015 dim state of RW Aurigae", "https://doi.org/10.1051/0004-6361/201527237", "X-ray, optical and near-infrared constraints on absorbing material"),
        ],
        "caveats": ["This physical illustration represents A; SPHEREx blends A and B.", "The disk, stellar radius and jets use separate display scales.", "The flow is a qualitative animation, not a simulation fitted to the SPHEREx frames."],
        "caveats_tr": ["Bu fiziksel temsil A bileşenidir; SPHEREx A ve B'yi birlikte görür.", "Disk, yıldız yarıçapı ve jetler ayrı gösterim ölçekleri kullanır.", "Akış nitel bir animasyondur; SPHEREx karelerine uydurulmuş benzetim değildir."],
    }
    mira = {
        "target_id": "r-dra", "name": "R Draconis", "type": "Mira variable red giant", "stellar_class": "Mira",
        "parameters": {
            "radius_solar": parameter(511, "R_sun", "computed", ["r-dra-iota"],
                "Historical 1997-07-05 K-band uniform-disk equivalent radius using a period-luminosity distance of 395 pc; molecular layers affect this value. Not a present photospheric radius.",
                "1997-07-05 K-bandı düzgün disk eşdeğer yarıçapı; dönem-ışınım gücü uzaklığı 395 pc kullanılmıştır. Moleküler katmanlardan etkilenir; güncel fotosfer yarıçapı değildir.", uncertainty=142, observation_date="1997-07-05", pulsation_phase=.83, method="K_band_uniform_disk_and_period_luminosity_distance"),
            "teff_k": parameter(2034, "K", "computed", ["r-dra-iota"],
                "1997 phase-specific effective temperature from bolometric flux and K-band angular diameter, not a cycle average.",
                "1997'de tek faza ait bolometrik akı ve K-bandı açısal çapından etkin sıcaklık; çevrim ortalaması değildir.", uncertainty=139, observation_date="1997-07-05"),
            "period_days": parameter(period, "d", "measured", ["gcvs-r-dra"],
                "GCVS catalogue period; no contemporary light-curve phase or radius amplitude is fitted.",
                "GCVS katalog dönemi; güncel ışık eğrisi fazı veya yarıçap genliği için uyum yapılmıyor."),
        },
        "phenomena": [
            phenomenon("pulsation", "measured", ["gcvs-r-dra", "r-dra-iota"], "Mira pulsation is established; the animation amplitude, color excursion and zero phase are illustrative.", "Mira titreşimi biliniyor; animasyon genliği, renk değişimi ve sıfır fazı temsilidir."),
            phenomenon("dust_outflow", "representative", ["mira-wind"], "Pulsation-assisted dusty wind is a Mira-class template; no R Dra mass-loss rate, wind speed or dust density is adopted.", "Titreşim destekli tozlu rüzgâr Mira sınıfını temsil eder; R Dra kütle kaybı oranı, rüzgâr hızı veya toz yoğunluğu benimsenmedi."),
        ],
        "rendering": rendering(pulsation_amplitude_classification="assumed", environment_scale="independently_compressed"),
        "sources": [
            gcvs,
            source("r-dra-iota", "van Belle, Thompson & Creech-Eakman (2002) — Angular Size Measurements of Mira Variables II", "https://arxiv.org/pdf/astro-ph/0210167", "Tables 1–3, R Dra row; section 4 excludes R Dra from dust-color correlations because its K−[12] excess was suspect", doi="10.1086/342282"),
            source("mira-wind", "Uttenthaler et al. (2024) — The impact of third dredge-up on the mass loss of Mira variables", "https://doi.org/10.1051/0004-6361/202451708", "Introduction: class-level pulsation-enhanced dust-driven outflow mechanism"),
        ],
        "caveats": ["The 511 R☉ radius and 2034 K temperature are historical, phase-specific and model dependent.", "The cited study rejected R Dra's dust-color excess from its mass-loss correlation; no dust quantity is inferred from it here.", "The animated radius/temperature cycle is schematic and does not predict the observed SPHEREx light curve."],
        "caveats_tr": ["511 R☉ yarıçap ve 2034 K sıcaklık tarihsel, faza özgü ve modele bağlıdır.", "Kaynak çalışma R Dra'nın toz rengi fazlasını kütle kaybı ilişkisinden çıkarmıştır; burada bu değerden toz miktarı türetilmiyor.", "Animasyondaki yarıçap/sıcaklık çevrimi şematiktir; gözlenen SPHEREx ışık eğrisini öngörmez."],
    }
    result = {"schema_version": 1, "curated_on": CHECKED,
              "purpose": "Source-cited physical context and explicitly illustrative 3D environments; independent of image measurement.",
              "classifications": {
                  "measured": "Observation-derived catalogue or fitted measurement; consult method and uncertainty.",
                  "computed": "Literature model inference or derived quantity, not an independent direct measurement.",
                  "representative": "Class or qualitative mechanism illustration without object-specific geometry.",
                  "assumed": "Display choice with no claim of physical measurement.",
                  "unknown": "No value is adopted; null never means zero."},
              "profiles": [barnard, epsilon, wise, rw, mira]}
    validate_catalogue(result)
    return result


def validate_catalogue(data):
    expected = {"barnard", "eps-indi-b", "wise-0855", "rw-aur", "r-dra"}
    if {profile["target_id"] for profile in data["profiles"]} != expected or len(data["profiles"]) != 5:
        raise ValueError("Exactly the five identified targets are required")
    for profile in data["profiles"]:
        sources = {entry["id"] for entry in profile["sources"]}
        quantities = [*profile["parameters"].values()]
        for component in profile.get("components", []):
            quantities.extend(component["parameters"].values())
        for quantity in quantities:
            value = quantity["value"]
            if value is None:
                if quantity["classification"] != "unknown":
                    raise ValueError("Unknown physical values must remain explicitly unknown")
            elif not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Physical values must be finite numbers or null")
        for item in [*quantities, *profile["phenomena"]]:
            if item["classification"] not in data["classifications"]:
                raise ValueError("Unrecognized evidence classification")
            if not set(item["source_ids"]).issubset(sources):
                raise ValueError("Unresolved scientific source identifier")
            if item["classification"] in ("measured", "computed") and not item["source_ids"]:
                raise ValueError("Every measured or computed claim needs a source")
            if not item.get("note") or not item.get("note_tr"):
                raise ValueError("Scientific limits must be explained in both languages")
        if profile["rendering"]["astrometric_year_changes_stellar_properties"]:
            raise ValueError("Space-motion time must not masquerade as stellar evolution")


def main():
    data = build_catalogue()
    path = RESOURCES / "stellar_profiles.json"
    write_json(path, data)
    print(json.dumps({"output": str(path), "profiles": len(data["profiles"]), "bytes": path.stat().st_size}))


if __name__ == "__main__":
    main()

"""What the assistant understands without a model: which star is meant, what is asked, where to go.

Three kinds of request are answered here in well under a millisecond, with no provider round:

* navigation ("take me to bernard", "Barnard'ın karelerini göster") becomes a validated command proposal;
* a lookup ("how far is it?", "sıcaklığı kaç?", "bilgi ver") is read from the catalogue row and cited profile;
* "what did you measure?" is read from this tool's own five-target report.

Everything else (why, how, compare) is left to the knowledge passages or the configured model.
The browser mirror is frontend/src/qfit/{match,facts,localIntent}.ts; both sides are checked against
tools/contracts/assistant-intents.json.
"""
from __future__ import annotations

import math
import re
import unicodedata
from functools import lru_cache

from .assistant_commands import CONFIRM, validate_command

# ---------------------------------------------------------------------------- names


def plain(text: str) -> str:
    """Lower case, no diacritics, single spaces: "Güneş'e götür" -> "gunes'e gotur"."""
    text = text.replace("İ", "i").replace("I", "i").lower().replace("ı", "i")
    text = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
    text = re.sub(r"[’‘`]", "'", text)
    text = re.sub(r"[−–—]", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", text) if w]


def edit_distance(a: str, b: str, limit: int = 2) -> int:
    """Optimal string alignment distance (insert, delete, substitute, swap neighbours), cut off above limit."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    before: list[int] = []
    previous = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        current = [i]
        for j in range(1, len(b) + 1):
            cost = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cost = min(cost, before[j - 2] + 1)
            current.append(cost)
        if min(current) > limit:
            return limit + 1
        before, previous = previous, current
    return previous[len(b)]


def _slack(word: str) -> int:
    """Typos allowed for a name word: none for short words, one from five letters, two from nine."""
    return 0 if re.search(r"\d", word) or len(word) < 5 else 1 if len(word) < 9 else 2


def same_word(typed: str, name: str) -> bool:
    """Allows typos and a short Turkish ending glued to the name ("barnarda", "proximayi")."""
    k = _slack(name)
    if edit_distance(typed, name, k) <= k:
        return True
    if len(name) < 5 or len(typed) <= len(name) or len(typed) > len(name) + 4:
        return False
    return any(n < len(typed) and edit_distance(typed[:n], name, k) <= k for n in (len(name), len(name) + 1))


GENERIC = {"star", "the", "yildizi", "yildiz", "gaia", "name", "s"}
ALIASES = {
    "barnard": ["barnard", "barnards", "gj 699", "gliese 699"],
    "eps-indi-b": ["epsilon indi", "eps indi", "epsilon indi b", "eps indi b"],
    "wise-0855": ["wise 0855", "wise0855", "0855", "wise 0855 0714"],
    "rw-aur": ["rw aurigae", "rw aur", "aurigae"],
    "r-dra": ["r draconis", "r dra", "draconis"],
}


def _score(query: list[str], star_id: str, name: str) -> int:
    full = [w for w in words(plain(name)) if w not in GENERIC]
    names = [full] + ([[full[0]]] if len(full) > 1 and len(full[0]) > 4 else []) + [words(a) for a in ALIASES.get(star_id, [])]
    best = 0
    for parts in names:
        if not parts or (len(parts) == 1 and len(parts[0]) < 4):
            continue
        exact = sum(part in query for part in parts)
        if all(part in query or any(same_word(q, part) for q in query) for part in parts):
            best = max(best, len("".join(parts)) + exact * 2)
    return best


@lru_cache(maxsize=1)
def directory() -> tuple[dict, ...]:
    """Every star the application can show: the ready targets first, then the catalogue."""
    from .assistant_qfit import local_sources
    return tuple(item for key, item in local_sources().items() if key.startswith("target:"))


def find_star(text: str) -> dict | None:
    """The catalogue entry a sentence names, or None. Earlier entries win ties."""
    query = words(plain(text))
    found, top = None, 0
    for item in directory():
        score = _score(query, item["star"]["id"], item["star"]["name"])
        if score > top:
            found, top = item, score
    return found


def star_by_id(star_id) -> dict | None:
    from .assistant_qfit import local_sources
    return local_sources().get(f"target:{star_id}") if isinstance(star_id, str) else None


# ---------------------------------------------------------------------------- what is asked

FIELD_WORDS = [
    ("distance", r"\b(how far|distance|far away|light.?years?|parsecs?|uzak\w*|mesafe\w*|isik yili\w*|parsek\w*)\b"),
    ("temperature", r"\b(temperature|how (hot|cold|warm)|sicak\w*|soguk\w*|kelvin|teff|kac derece|isisi)\b"),
    ("radius", r"\b(radius|how (big|large|small)|size|diameter|yaricap\w*|buyukl\w*|ne kadar buyuk|boyut\w*|capi)\b"),
    ("motion", r"\b(proper motion|how fast|speed|velocity|ozdevinim\w*|hizi|ne kadar hizli|radial velocity|dikine hiz\w*)\b"),
    ("parallax", r"\b(parallax|paralaks\w*)\b"),
    ("type", r"\b(spectral( type| class)?|what (kind|type|sort)|tayf\w*|ne tur|turu|sinifi|ne yildizi|nasil bir yildiz)\b"),
    ("brightness", r"\b(magnitude|how bright|brightness|parlakl\w*|ne kadar parlak|kadir\w*|colou?r|rengi?)\b"),
    ("position", r"\b(coordinates?|right ascension|declination|konumu?|koordinat\w*|where is|nerede)\b"),
    ("rotation", r"\b(rotat\w*|spin\w*|donus\w*|donme\w*)\b"),
    ("age", r"\b(how old|age|kac yasinda|yasi|yasini)\b"),
    ("mass", r"\b(mass(?! slider)|how (massive|heavy)|kutlesi\w*|agirlig\w*)\b"),
    ("frames", r"\b(how many (frames|observations|images)|kac (kare|gozlem|goruntu)\w*|when was (it|this) observed|ne zaman gozlen\w*|wavelength|dalga boyu\w*)\b"),
]
OVERVIEW = r"\b(tell me( more)?|info\w*|facts?|summary|summari[sz]e|describe|details?|bilgi\w*|anlat\w*|ozet\w*|tanit\w*|detay\w*|what do (we|you) know|ne biliyor\w*)\b"
WEAK_OVERVIEW = r"\b(what is|what's|who is|about|nedir|kimdir|hakkinda)\b"
MEASURED = r"\b(what did (you|we)|measure\w*|result\w*|sigma|olcum\w*|olctu\w*|sonuc\w*|ne buldu\w*|did it|degisti mi|kaydi mi)\b"
EXPLAIN = r"\b(why|neden|nicin|niye|how (does|do|did|can|come)|explain\w*|acikla\w*|nasil (calis|olus|hesap|olc|bul|yap)\w*|what does|ne demek|ne anlama|nereden|where (does|do|did))\b"
SEEING = r"\b(what (am i|do i|are we) (see|look)\w*|ne goruyorum|neye bakiyorum)\b"
POINTS = r"\b(it|its|this|that|bu|su|bunun|onun|bunu|onu)\b"
SUN = r"\b(gunes\w*|sun)\b"
FILLER = set((
    "the a an is are was it its this that these star stars me my tell give show what whats how of to about some more please can could you do does we know any for and in on at now quick quickly here there one current selected target object away from us our earth sun right"
    " bu su o onun bunun bunu onu yildiz yildizin yildizi yildizla ne nedir kac kadar mi mu ver verir misin soyle goster bana bize biraz daha hakkinda lutfen bir ve ile hedef hedefin secili simdi hizlica dunya dunyadan dunyaya bizden gunes gunesten gunese olan var peki ya icin"
).split())
GO = {"gotur", "git", "gidelim", "goster", "ac", "gec", "don", "in", "yaklas", "take", "go", "show", "open", "bring", "fly", "zoom", "visit", "bak", "bakalim"}
DESTINATION = [
    ("observations", r"\b(gozlem\w*|observations?|kare\w*|frames?|goruntu\w*|images?|spherex|blink|kirpistir\w*)\b"),
    ("evolution", r"\b(evrim\w*|evolution|life ?cycle|yasam\w*)\b"),
    ("sky", r"\b(gokyuzu\w*|sky|komsu\w*|neighbou?r\w*|harita\w*|map)\b"),
    ("star", r"\b(yuzey\w*|surface|menu\w*|sayfa\w*|page|model\w*|3d|3b|katalog\w*|catalogue)\b"),
]


def asked_fields(q: str, pointed: bool) -> tuple[list[str], list[str]]:
    """Which facts a question asks for, and the content words left once those are removed."""
    rest, fields = q, []
    for field, pattern in FIELD_WORDS:
        if re.search(pattern, q):
            fields.append(field)
            rest = re.sub(pattern, " ", rest)
    if not fields and (re.search(OVERVIEW, q) or (pointed and re.search(WEAK_OVERVIEW, q))):
        fields.append("overview")
    rest = re.sub(WEAK_OVERVIEW, " ", re.sub(OVERVIEW, " ", rest))
    return fields, [w for w in words(rest) if len(w) > 2 and w not in FILLER]


# ---------------------------------------------------------------------------- facts

PC_TO_LY = 3.261563777


def _n(value: float, digits: int = 2, tr: bool = False) -> str:
    text = f"{value:,.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".") if tr else text


def fact_rows(fields: list[str], item: dict, tr: bool) -> list[dict]:
    """Rows for the asked fields. Missing data is reported as missing, never filled in."""
    star, profile = item["star"], item.get("profile") or {}
    T = lambda turkish, english: turkish if tr else english  # noqa: E731
    n = lambda value, digits=2: _n(value, digits, tr)  # noqa: E731
    source = star.get("source") or T("katalog", "catalogue")

    def parameter(key):
        p = profile.get("parameters", {}).get(key)
        return p if p and isinstance(p.get("value"), (int, float)) and not isinstance(p.get("value"), bool) else None

    def with_error(p, digits=3):
        return n(p["value"], digits) + (f" ± {n(p['uncertainty'], digits)}" if "uncertainty" in p else "")

    def note(p):
        return (p.get("note_tr") or p.get("note")) if tr else p.get("note")

    def row(label, value, remark=None):
        return {"label": label, "value": value, **({"note": remark} if remark else {})}

    def temperature():
        p = parameter("teff_k")
        if p:
            return [row(T("Sıcaklık", "Temperature"), f"{with_error(p, 0)} K", note(p))]
        if star.get("teff_k"):
            return [row(T("Sıcaklık", "Temperature"), f"{n(star['teff_k'], 0)} K", T("Katalog değeri", "Catalogue value") + f" · {star.get('teff_source')}")]
        return [row(T("Sıcaklık", "Temperature"), T("katalogda yok", "not in the catalogue"))]

    def radius():
        p = parameter("radius_solar")
        return [row(T("Yarıçap", "Radius"), f"{with_error(p)} R☉", note(p)) if p else row(T("Yarıçap", "Radius"), T("kaynaklı bir değer yok", "no source-backed value"))]

    def motion():
        total = math.hypot(star["pmRa"], star["pmDec"])
        value = f"{n(total / 1000)}″/{T('yıl', 'yr')}" if total >= 1000 else f"{n(total, 1)} mas/{T('yıl', 'yr')}"
        velocity = row(T("Dikine hız", "Radial velocity"), f"{n(star['radialVelocity'], 1)} km/s") if star.get("hasRadialVelocity") else \
            row(T("Dikine hız", "Radial velocity"), T("ölçüm yok", "not measured"), T("Hareket modelinde sıfır varsayılır.", "The motion model assumes zero."))
        return [row(T("Özdevinim", "Proper motion"), value, source), velocity]

    def brightness():
        rows = [row(T("Parlaklık · Gaia G", "Brightness · Gaia G"), f"{n(star['magnitude'])} {T('kadir', 'mag')}")] if star.get("magnitude") is not None else \
            [row(T("Parlaklık", "Brightness"), T("katalogda yok", "not in the catalogue"))]
        if star.get("colorIndex") is not None:
            rows.append(row(T("Renk · BP−RP", "Colour · BP−RP"), f"{n(star['colorIndex'])} {T('kadir', 'mag')}"))
        return rows

    def simple(key, label, unit, digits=3):
        p = parameter(key)
        return [row(label, f"{with_error(p, digits)} {unit}", note(p)) if p else row(label, T("benimsenmiş bir değer yok", "no adopted value"))]

    def frames():
        result = measured(star["id"])
        if not result:
            return [row(T("SPHEREx kareleri", "SPHEREx frames"), T("hazır kare yok", "no prepared frames"), T("Koordinatla arşivde aranabilir.", "The archive can be searched by coordinates."))]
        return [row(T("SPHEREx kareleri", "SPHEREx frames"), f"{result['frames']} {T('kare', 'frames')} · {result['days']} {T('gün', 'days')}", f"{n(float(result['wavelength_um']), 3)} µm")]

    builders = {
        "distance": lambda: [row(T("Uzaklık", "Distance"), f"{n(star['distancePc'] * PC_TO_LY)} {T('ışık yılı', 'light-years')} ({n(star['distancePc'])} pc)", T("Paralakstan hesaplandı", "Computed from the parallax") + f" · {source}")],
        "parallax": lambda: [row(T("Paralaks", "Parallax"), n(star["parallax"], 3) + (f" ± {n(star['parallaxError'], 3)}" if star.get("parallaxError") is not None else "") + " mas", source)],
        "temperature": temperature, "radius": radius, "motion": motion, "brightness": brightness, "frames": frames,
        "type": lambda: [row(T("Tayf türü", "Spectral type"), star.get("spectralType") or T("katalogda yok", "not in the catalogue"), star.get("subtitleTr" if tr else "subtitleEn") or profile.get("type"))],
        "position": lambda: [row("ICRS · RA / Dec", f"{star['ra']:.4f}° / {star['dec']:+.4f}°", T(f"Katalog dönemi J{star['epoch']:.1f}", f"Catalogue epoch J{star['epoch']:.1f}"))],
        "rotation": lambda: simple("rotation_period_days", T("Dönüş süresi", "Rotation period"), T("gün", "days"), 0),
        "age": lambda: [row(T("Yaş", "Age"), T("ölçülmüş bir yaş yok", "no measured age"), T("Yayımlanmış evrim tablosu bir karşılaştırmadır; bu yıldızın ölçülmüş yaşı değildir.", "The published evolution table is a comparison, not the measured age of this star."))],
        "mass": lambda: simple("mass_solar", T("Kütle", "Mass"), "M☉"),
    }
    wanted = ["type", "distance", "temperature", "radius", "motion"] + (["frames"] if measured(star["id"]) else []) if "overview" in fields else fields
    return [r for field in dict.fromkeys(wanted) if field in builders for r in builders[field]()]


# ---------------------------------------------------------------------------- this tool's own measurements

_ROW = re.compile(r"\| \[(?P<name>[^\]]+)\]\((?P<id>[\w-]+)\.md\) \| (?P<wavelength_um>[\d.]+) \| (?P<frames>\d+) / (?P<visits>\d+) / (?P<days>\d+) \| (?P<available>\w+) \| (?P<detected>[^|]+) \| (?P<change>[^|]+) \| (?P<confirmed>\w+) \| (?P<rms>[\d.]+) \|")


@lru_cache(maxsize=1)
def _measurements() -> dict[str, dict]:
    from .assistant_qfit import local_sources
    summary = local_sources().get("report:README#intro", {}).get("text", "")
    return {m["id"]: {k: v.strip() for k, v in m.groupdict().items()} for m in _ROW.finditer(summary)}


def measured(star_id) -> dict | None:
    """The row of the five-target report for this target, exactly as that report states it."""
    return _measurements().get(star_id) if isinstance(star_id, str) else None


def measured_text(item: dict, tr: bool) -> str | None:
    result = measured(item["star"]["id"])
    if not result:
        return None
    name, n = item["star"]["name"], lambda value, digits=2: _n(float(value), digits, tr)  # noqa: E731
    detected = re.match(r"(yes|no) \((\d+)/(\d+), (\d+) saturated\)", result["detected"])
    change = re.match(r"yes (motion|brightness): ([\d.]+)( px|×), ([\d.]+)σ(, consistent with catalogue)?", result["change"])
    if tr:
        lines = [f"**{name}** · bu aracın kendi ölçümü: {result['wavelength_um']} µm'de {result['frames']} kare, {result['days']} gün."]
        if detected:
            lines.append(f"Kaynak {detected[3]} karenin {detected[2]} tanesinde bulundu" + (f" ({detected[4]} karede çekirdek doymuş)." if detected[4] != "0" else "."))
        if change and change[1] == "motion":
            lines.append(f"**Görülen değişim:** {n(change[2])} piksel konum kayması, {n(change[4], 1)}σ" + (", katalogla uyumlu." if change[5] else "."))
        elif change:
            lines.append(f"**Görülen değişim:** parlaklık {n(change[2], 3)} kat değişti, {n(change[4], 1)}σ.")
        else:
            lines.append("**Görülen değişim:** bu karelerde 3σ üzerinde bir değişim yok.")
        lines.append("Bilimsel olarak doğrulanmış değildir: 3σ bu aracın kendi ölçümündeki eşiktir, keşif değildir.")
    else:
        lines = [f"**{name}** · this tool's own measurement: {result['frames']} frames over {result['days']} days at {result['wavelength_um']} µm."]
        if detected:
            lines.append(f"The source was found in {detected[2]} of {detected[3]} frames" + (f" ({detected[4]} with a saturated core)." if detected[4] != "0" else "."))
        if change and change[1] == "motion":
            lines.append(f"**Change seen:** a position shift of {change[2]} px at {change[4]}σ" + (", consistent with the catalogue." if change[5] else "."))
        elif change:
            lines.append(f"**Change seen:** brightness changed by a factor of {change[2]} at {change[4]}σ.")
        else:
            lines.append("**Change seen:** nothing above 3σ in these frames.")
        lines.append("Not scientifically confirmed: 3σ is this tool's own threshold, not a discovery.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------- answers


def _proposal(name: str, args: dict, index: int = 1) -> dict:
    if not validate_command(name, args):
        raise ValueError("invalid instant command")
    return {"tool_use_id": f"instant_command_{index}", "name": name, "args": args, "requires_confirmation": name in CONFIRM}


def _navigation(q: str, raw: str, named: dict | None, tr: bool) -> tuple[str, dict] | None:
    """A navigation request as (sentence, command), mirroring the browser's own router."""
    T = lambda turkish, english: turkish if tr else english  # noqa: E731
    tokens, has = set(words(q)), lambda *parts: any(p in q for p in parts)  # noqa: E731
    go, short = bool(tokens & GO), len(q.split(" "))
    page = next((name for name, pattern in DESTINATION if re.search(pattern, q)), None)
    if named and (go or page or short <= 3):
        to, name = page or "star", named["star"]["name"]
        sentence = {
            "star": T(f"{name} yıldızına gidiyoruz. Katalog değerleri çevresinde; yüzey temsili çizimdir.", f"Heading to {name}. Its catalogue values sit around it; the surface is an illustration."),
            "sky": T(f"{name} gökyüzünde: Güneş’in çevresindeki yerine odaklanıyorum.", f"{name} in the sky: focusing on its place around the Sun."),
            "observations": T(f"{name} için gerçek SPHEREx karelerini açıyorum.", f"Opening the real SPHEREx frames of {name}."),
            "evolution": T(f"{name} için yayımlanmış evrim tablosunu açıyorum. Bu, ölçülmüş yaşı değildir.", f"Opening the published evolution table for {name}. It is not its measured age."),
        }[to]
        return sentence, _proposal("open_target", {"target_id": named["star"]["id"], "page": to})
    if has("samanyolu", "milky way", "gokada", "galaxy", "galaksi"):
        return T("Samanyolu’na çıkıyoruz. Turuncu işaret Güneş.", "Flying out to the Milky Way. The orange marker is the Sun."), _proposal("set_sky_scale", {"scale": "galaxy"})
    if re.search(r"\b(gunes|sun)\b|gunes'|gunese", q) and (go or short <= 2):
        return T("Güneş’in çevresine iniyoruz; noktalar Gaia’nın ölçtüğü yakın yıldızlar.", "Flying down to the Sun; the dots are nearby stars measured by Gaia."), _proposal("set_sky_scale", {"scale": "local"})
    if has("yan yana", "side by side", "side-by-side"):
        return T("Kareleri yan yana koyuyorum: solda A (referans), sağda B.", "Putting the frames side by side: A (reference) left, B right."), _proposal("set_view_mode", {"view": "side"})
    if has("fark", "difference", "diff"):
        return T("Fark görünümünü açıyorum: B eksi A. Her fark gerçek bir değişim değildir.", "Opening the difference view: B minus A. Not every difference is a real change."), _proposal("set_view_mode", {"view": "diff"})
    if has("zaman yigini", "time stack", "3b yigin"):
        return T("Kareleri tarih sırasıyla 3B yığına diziyorum.", "Stacking the frames in 3D by date."), _proposal("set_stage_view", {"view": "timestack"})
    if has("gozlem", "observation", "kareler", "frames", "goruntu", "images"):
        return T("Gerçek SPHEREx karelerine dönüyoruz.", "Back to the real SPHEREx frames."), _proposal("set_mode", {"mode": "observations"})
    if has("egitim", "education", "kara delik", "black hole", "kutle", "mass slider"):
        return T("Eğitim modelini açıyorum. Bu model temsilidir.", "Opening the education model. It is illustrative."), _proposal("set_stellar_mode", {"mode": "education"})
    if has("evrim", "evolution", "life cycle", "yasam", "lifecycle"):
        return T("Yayımlanmış evrim tablosunu açıyorum. Bu, seçili yıldızın ölçülmüş yaşı değildir.", "Opening the published evolution table. It is not the measured age of the chosen star."), _proposal("set_stellar_mode", {"mode": "evolution"})
    if has("kaynak", "sources", "source list"):
        return T("Kaynakları ve sınırları açıyorum.", "Opening sources and limits."), _proposal("open_sources", {})
    year = re.search(r"\b(20\d\d|2100)\b", q)
    if year and has("yil", "year", "git", "go"):
        value = min(2100, max(2000, int(year[1])))
        return T(f"Konum yılını {value} yapıyorum. Yıldızların yeri katalogdaki harekete göre hesaplanır.", f"Setting the position year to {value}. Star positions follow their catalogued motion."), _proposal("set_year", {"year": value})
    return None


def instant(body) -> dict | None:
    """A complete answer without a model, or None when the request needs passages or a model."""
    from .assistant_qfit import citation, profile_citations
    q, tr = plain(body.message), body.context.get("ui_language") == "tr"
    if not q:
        return None
    if re.search(r"\b(?:and then|then|after that|ardindan|sonra)\b", q):
        return None
    named = find_star(q)
    selected = body.context.get("target") or {}
    current = star_by_id(selected.get("id")) if isinstance(selected, dict) else None
    pointed = bool(named) or bool(re.search(POINTS, q))
    subject = named or current
    caveat = ("Değerler katalogdan ve kaynaklı yıldız profilinden okunur; 3B yüzey temsili çizimdir. Bir keşif ya da bilimsel doğrulama değildir."
              if tr else "Values are read from the catalogue and the cited stellar profile; the 3D surface is representative. This is not a discovery or a scientific confirmation.")

    def respond(intent, message, sources, *, commands=(), data=None):
        ids = list(dict.fromkeys(sources))
        from .assistant_qfit import local_sources
        return {"success": True, "assistant": "Q-FIT", "intent": intent, "message": message, "message_source": "system",
                "sources": [citation(i, local_sources().get(i, {}).get("title")) for i in ids] + (profile_citations({"target": {"id": subject["star"]["id"]}}) if subject and intent != "navigation" else []),
                "uncertainty": [caveat], "actions": [], "commands": list(commands), "data": data or {}, "language": "tr" if tr else "en",
                "meta": {"ai_model": None, "tools_called": [], "versions": {"mode": "instant"}}}

    if re.search(MEASURED, q) and subject and (named or not asked_fields(re.sub(MEASURED, " ", q), pointed)[1]):
        message = measured_text(subject, tr)
        if message:
            return respond("measurement", message, [f"report:{subject['star']['id']}#status", "report:README#intro", subject["id"]], data={"target_id": subject["star"]["id"], "measurement": measured(subject["star"]["id"])})
    if re.search(EXPLAIN, q) or re.search(MEASURED, q) or re.search(SEEING, q):
        return None
    fields, rest = asked_fields(q, pointed)
    if fields:
        elsewhere = not named and (bool(rest) or (bool(re.search(SUN, q)) and not re.search(POINTS, q)))
        if not subject or elsewhere:
            return None
        rows, star = fact_rows(fields, subject, tr), subject["star"]
        subtitle = star.get("subtitleTr" if tr else "subtitleEn")
        lines = [f"**{star['name']}**" + (f" · {subtitle}" if subtitle else "")] + [f"**{r['label']}:** {r['value']}" + (f" — {r['note']}" if r.get("note") else "") for r in rows]
        # A look-up never moves the page: the visitor asked a question, not for a trip.
        return respond("facts", "\n".join(lines), [subject["id"], "epistemic#labels"], data={"target_id": star["id"], "fields": fields, "facts": rows})
    if "?" in body.message:
        return None
    navigation = _navigation(q, body.message, named, tr)
    if navigation:
        return respond("navigation", navigation[0], [named["id"]] if named else [], commands=[navigation[1]], data={"target_id": named["star"]["id"]} if named else {})
    return None


_SMALL = set("what which when where does have with from they them their there than then into your will would should were been being very much many also just like only over such nedir nasil neden hangi kadar icin gibi daha olan olarak veya ancak cunku midir".split())


@lru_cache(maxsize=1)
def _knowledge():
    from .assistant_qfit import Knowledge
    return Knowledge()


def passages(body) -> dict | None:
    """The best matching, source-labelled knowledge passage in the interface language. Not an AI answer."""
    from .assistant_qfit import citation, profile_citations
    tr = body.context.get("ui_language") == "tr"
    if not body.message.strip() or re.search(SEEING, plain(body.message)):
        return None
    try:
        hits = _knowledge().retriever.search(body.message, language="tr" if tr else "en", top_k=2)["hits"]
    except Exception:  # vendor archive missing or unreadable: the caller falls back to the target card
        return None
    # BM25 also scores small words. Keep a passage only if it is about the subject of the question:
    # its heading names one of the content words, or its text holds most of them.
    terms = [w[:5] for w in words(plain(body.message)) if len(w) > 3 and w not in FILLER and w not in _SMALL]
    def about(hit):
        heading, text = plain(hit["heading"] + " " + hit["title"]), plain(hit["text"])
        found = sum(term in text or term in heading for term in terms)
        return bool(terms) and (any(term in heading for term in terms) or found / len(terms) >= 0.6)
    hits = [h for h in hits if about(h)][:2]
    if not hits:
        return None
    selected = body.context.get("target") or {}
    current = star_by_id(selected.get("id")) if isinstance(selected, dict) else None
    message = "\n\n".join(f"**{h['heading']}**\n{h['text']}" for h in hits)
    sources = ([citation(current["id"], current.get("title"))] if current else [])
    seen = set()
    for hit in hits:
        for source in hit.get("sources", []):
            if source.get("url") and source["url"] not in seen:
                seen.add(source["url"])
                sources.append({"id": source.get("id"), "name": source.get("name") or source.get("title") or hit["title"], "url": source["url"]})
    caveat = ("Bu, yerel bilgi tabanından alınmış kaynaklı bir pasajdır; yapay zekâ yanıtı değildir. 3B yüzey ve çevre temsili çizimdir; bir keşif ya da ölçülmüş yüzey görüntüsü değildir."
              if tr else "This is a source-labelled passage from the local knowledge base, not an AI answer. The 3D surface and environment are representative; this is not a discovery or an observed surface image.")
    notes = [h["verification_note"] for h in hits if h.get("verification_note")]
    return {"success": True, "assistant": "Q-FIT", "intent": "knowledge", "message": message, "message_source": "system",
            "sources": sources + (profile_citations(body.context) if current else []), "uncertainty": [caveat] + notes, "actions": [], "commands": [],
            "data": {"passages": [h["chunk_id"] for h in hits]}, "language": "tr" if tr else "en",
            "meta": {"ai_model": None, "tools_called": [], "versions": {"mode": "local_passage"}}}


def answer(body) -> dict:
    """The quickest truthful answer available without a model."""
    from .assistant_qfit import local_answer
    return instant(body) or passages(body) or {**local_answer(body), "commands": []}

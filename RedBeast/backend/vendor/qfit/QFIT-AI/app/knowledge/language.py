"""Language detection (Turkish / English) and text normalisation for retrieval."""
from __future__ import annotations

import re
import unicodedata

_TR_CHARS = set("çğıöşüÇĞİÖŞÜ")
_TR_WORDS = {"ve", "bir", "bu", "için", "icin", "nedir", "ne", "nasıl", "nasil", "mi", "mı", "mu", "mü", "hangi",
             "neden", "kaç", "kac", "ile", "var", "yok", "göster", "goster", "bul", "arasında", "arasindaki",
             "arasındaki", "hakkında", "hakkinda", "gözlem", "gozlem", "yıldız", "yildiz", "cüce", "cuce",
             "kahverengi", "veri", "bana", "olan", "nerede", "ara", "açıkla", "acikla", "fark", "farkı", "midir",
             "mıdır", "gibi", "daha", "değil", "degil", "şu", "su", "anlat", "söyle", "soyle", "ışık", "isik",
             "git", "götür", "gotur", "beni", "bizi", "yıldızına", "yildizina", "galaksisi", "nerede", "neresi"}
# Turkish case endings written after an apostrophe on a name: Vega'ya, M31'i, Orion'daki ...
_TR_APOSTROPHE = re.compile(r"[’'](?:y?[aeıiuü]|n?[ıiuü]n|[dt][ae](?:n|ki)?|y?l[ae]|n[ae])", re.I)
_EN_WORDS = {"the", "is", "are", "what", "how", "why", "which", "of", "and", "in", "for", "does", "do", "show",
             "find", "me", "this", "that", "with", "between", "explain", "can", "there", "any", "when", "where",
             "about", "tell", "it", "to", "a", "an", "on", "at", "was", "has", "have", "data", "available"}
_FOLD = str.maketrans("çğıöşü", "cgiosu")
_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
# Turkish words are cut to this many letters. Chosen by the retrieval evaluation
# (app/evaluation/retrieval.py compares 4, 5 and 6); change it only with a new report.
TR_PREFIX_LENGTH = 5
STOPWORDS = {
    "en": {"the", "a", "an", "is", "are", "of", "and", "or", "in", "on", "to", "for", "it", "that", "this", "as",
           "by", "be", "with", "at", "from", "what", "how", "does", "do", "can", "its", "was", "which", "not",
           "about", "tell", "me", "there", "any", "has", "have", "i", "you", "we", "they", "their", "than",
           "how", "why", "when", "where", "who", "today", "please", "show", "give", "explain", "would", "could"},
    "tr": {"ve", "bir", "bu", "icin", "ile", "de", "da", "mi", "mu", "ne", "nedir", "olan", "olarak", "gibi",
           "daha", "en", "her", "ya", "veya", "ise", "ama", "bana", "su", "o", "ki", "midir", "var", "yok",
           "hakkinda", "nasil", "neden", "hangi", "kadar", "cok", "diye", "soyle", "anlat"},
}


def detect_language(text: str, default: str = "en") -> str:
    """Return 'tr' or 'en'. Heuristic, deterministic and dependency-free."""
    if not text or not text.strip():
        return default
    words = re.findall(r"[^\W\d_]+", text.lower(), re.UNICODE)
    tr = sum(w in _TR_WORDS for w in words) + 2 * sum(any(c in _TR_CHARS for c in w) for w in words)         + 2 * len(_TR_APOSTROPHE.findall(text))
    en = sum(w in _EN_WORDS for w in words)
    if tr == en:
        return default if tr == 0 else "tr"
    return "tr" if tr > en else "en"


def fold(text: str) -> str:
    """Lower-case and remove Turkish diacritics so 'cüce' and 'cuce' match."""
    text = text.replace("İ", "i").replace("I", "i").lower()
    text = "".join(c for c in unicodedata.normalize("NFKD", text.translate(_FOLD)) if not unicodedata.combining(c))
    return text


def stem(token: str, language: str) -> str:
    if token[0].isdigit():
        return token
    if language == "tr":
        return token[:TR_PREFIX_LENGTH]       # crude but effective for an agglutinative language
    # Tried 2026-11-14: "-ery" -> "-er" (discover/discovery) changed no retrieval metric; not kept.
    for suffix, repl in (("ies", "y"), ("sses", "ss"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: len(token) - len(suffix)] + repl
    return token


def tokenize(text: str, language: str, *, stemming: bool = True, stopwords: bool = True) -> list[str]:
    out = []
    # Stop words of both languages are dropped: Turkish documents quote English names
    # ("The Astrophysical Journal") and must not match on "the".
    stops = (STOPWORDS["en"] | STOPWORDS["tr"]) if stopwords else set()
    for token in _TOKEN.findall(fold(text)):
        if token in stops or (len(token) == 1 and not token.isdigit()):
            continue
        out.append(stem(token, language) if stemming else token)
    return out

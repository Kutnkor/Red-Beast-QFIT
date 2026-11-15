"""Answer /chat without a language model when the model cannot be used.

Triggered when the provider is not configured, out of quota, unreachable or failing. The
answer is the most relevant knowledge-base passage, quoted as it is with its source. Nothing
is generated, so nothing can be invented; the response says plainly that no AI wrote it.
"""
from __future__ import annotations

from typing import Any

from app.knowledge.language import detect_language
from app.services import response_builder as rb
from app.utils.errors import QFitError

_REASONS = {
    "rate_limited": {"tr": "yapay zekâ kullanım kotası doldu", "en": "the AI usage quota is used up"},
    "ai_unavailable": {"tr": "yapay zekâ yapılandırılmamış veya erişilemiyor",
                       "en": "the AI model is not configured or not reachable"},
}
_DEFAULT_REASON = {"tr": "yapay zekâ hizmeti hata verdi", "en": "the AI service returned an error"}
_TEXT = {
    "tr": {"intro": "Yapay zekâ asistanı şu an yanıt veremiyor ({reason}). Bilgi tabanındaki en ilgili kaynaklı pasaj:",
           "source": "Kaynak", "more": "{n} ilgili pasaj daha var.",
           "none": "Yapay zekâ asistanı şu an yanıt veremiyor ({reason}) ve bilgi tabanında bu soruya uygun bir "
                   "pasaj bulunamadı. Nesne, gözlem, görüntü ve tayf aramaları yapay zekâ olmadan da çalışır.",
           "caveat": "Bu yanıtı yapay zekâ yazmadı: bilgi tabanından olduğu gibi alınmış bir pasajdır ve sorunun "
                     "tamamını yanıtlamıyor olabilir."},
    "en": {"intro": "The AI assistant cannot answer right now ({reason}). The most relevant cited passage from the "
                    "knowledge base:",
           "source": "Source", "more": "{n} more related passage(s) are available.",
           "none": "The AI assistant cannot answer right now ({reason}) and the knowledge base has no passage on "
                   "this question. Object, observation, image and spectrum searches work without the AI.",
           "caveat": "No AI wrote this answer: it is a passage quoted from the knowledge base and may not answer "
                     "the whole question."},
}


def knowledge_fallback(knowledge, message: str, context: dict[str, Any] | None, error: QFitError,
                       top_k: int = 3) -> dict[str, Any]:
    language = (context or {}).get("locale") or detect_language(message)
    text = _TEXT[language]
    reason = _REASONS.get(error.code, _DEFAULT_REASON)[language]
    result = None
    if knowledge is not None:
        try:
            result = knowledge.search(message, language=language, top_k=top_k)
        except QFitError:
            result = None
    fallback_info = {"active": True, "reason_code": error.code, "reason": error.message,
                     "retryable": error.retryable}
    if not result or not result["hits"]:
        return {"intent": "assistant_unavailable", "message": text["none"].format(reason=reason), "object": None,
                "data": {"fallback": fallback_info}, "actions": [], "sources": [], "language": language,
                "evidence": [{"kind": "missing_information", "statement": "No knowledge passage matched.",
                              "status": "no_data", "source_names": [], "source_urls": []}],
                "uncertainty": [text["caveat"]], "media": []}
    part = rb.from_knowledge(result)
    top = result["hits"][0]
    cited = "; ".join(f"{s['organization']}: {s['name']}" for s in top["sources"][:3])
    lines = [text["intro"].format(reason=reason), "", f"{top['title']} - {top['heading']}", top["text"], "",
             f"{text['source']}: {cited}"]
    if len(result["hits"]) > 1:
        lines.append(text["more"].format(n=len(result["hits"]) - 1))
    part.update(intent="knowledge_fallback", message="\n".join(lines), language=language,
                uncertainty=[text["caveat"], *part["uncertainty"]])
    part["data"]["fallback"] = fallback_info
    return part

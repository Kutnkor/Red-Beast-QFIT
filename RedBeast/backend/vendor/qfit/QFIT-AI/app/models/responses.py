"""The single response envelope used by every Q-FIT endpoint."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

ActionType = Literal["focus_map", "display_object", "display_observations", "display_spectrum",
                     "display_image", "show_error", "request_clarification"]
ACTION_TYPES: tuple[str, ...] = ActionType.__args__  # type: ignore[attr-defined]


class Action(BaseModel):
    type: ActionType
    payload: dict[str, Any] = Field(default_factory=dict)


class ErrorInfo(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class Meta(BaseModel):
    request_id: str = "-"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    api_version: str = "v1"
    tools_called: list[str] = Field(default_factory=list)
    ai_model: str | None = None
    versions: dict[str, Any] = Field(default_factory=dict, description="instructions, knowledge index, "
                                     "source registry and scientific configuration used for this answer")


class QFitResponse(BaseModel):
    success: bool
    assistant: str = "Q-FIT"
    intent: str
    message: str
    message_source: Literal["system", "ai_generated"] = Field(
        "system", description="'ai_generated' text is an explanation by the language model; "
                              "everything under object/data/actions/sources is retrieved data.")
    object: dict[str, Any] | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    actions: list[Action] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    language: str | None = Field(None, description="Language of `message`: 'tr' or 'en'")
    evidence: list[dict[str, Any]] = Field(default_factory=list, description="What the answer rests on, by class")
    uncertainty: list[str] = Field(default_factory=list, description="Limits and caveats of this answer")
    media: list[dict[str, Any]] = Field(default_factory=list, description="References to real image/cube files")
    error: ErrorInfo | None = None
    meta: Meta = Field(default_factory=Meta)


def empty_data(**extra: Any) -> dict[str, Any]:
    """Keys every `data` block carries, so frontends can rely on them."""
    return {"spherex_available": None, "observations": [], "spectral_products": [],
            "image_products": [], **extra}

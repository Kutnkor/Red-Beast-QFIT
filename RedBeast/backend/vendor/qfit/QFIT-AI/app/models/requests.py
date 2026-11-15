"""Request bodies. The same target fields are reused by the REST API and the AI tools."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Release = Literal["all", "dr1", "qr3"]
TargetKind = Literal["auto", "deep_sky", "solar_system"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TargetFields(_Strict):
    object_name: str | None = Field(None, max_length=100, description="Object name in catalog form, e.g. 'M31', 'Andromeda Galaxy' (never translated). Alternative to ra/dec.")
    ra: float | None = Field(None, ge=0, le=360, description="Right ascension, ICRS, decimal degrees")
    dec: float | None = Field(None, ge=-90, le=90, description="Declination, ICRS, decimal degrees")

    @model_validator(mode="after")
    def _need_target(self):
        if (self.ra is None) != (self.dec is None):
            raise ValueError("ra and dec must be given together")
        if self.ra is None and not self.object_name:
            raise ValueError("give either object_name or both ra and dec")
        return self


class ChatTurn(_Strict):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class ChatContext(_Strict):
    """What the frontend is currently showing, so 'this region' can be understood."""
    ra: float | None = Field(None, ge=0, le=360)
    dec: float | None = Field(None, ge=-90, le=90)
    fov_deg: float | None = Field(None, gt=0, le=360)
    selected_object: str | None = Field(None, max_length=100)
    selected_observation_id: str | None = Field(None, max_length=120)
    locale: Literal["tr", "en"] | None = Field(None, description="Interface language; overrides detection")
    expertise_level: Literal["beginner", "intermediate", "advanced", "research"] | None = None


class ChatRequest(_Strict):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)
    context: ChatContext | None = None


class ObjectSearchRequest(_Strict):
    query: str = Field(..., min_length=1, max_length=100)
    max_results: int = Field(5, ge=1, le=20)


class ResolveRequest(_Strict):
    name: str = Field(..., min_length=1, max_length=100)
    target_kind: TargetKind = "auto"
    epoch_utc: str | None = Field(None, max_length=40, description="ISO-8601 epoch for Solar System bodies (default: now)")


class ConeSearchRequest(_Strict):
    ra: float = Field(..., ge=0, le=360)
    dec: float = Field(..., ge=-90, le=90)
    radius_deg: float = Field(0.1, gt=0, le=2)
    object_type: str | None = Field(None, max_length=30)
    limit: int = Field(20, ge=1, le=100)


class ObservationSearchRequest(TargetFields):
    radius_deg: float = Field(0.003, gt=0, le=2)
    detector: int | None = Field(None, ge=1, le=6)
    release: Release = "all"
    start_utc: str | None = Field(None, max_length=40)
    end_utc: str | None = Field(None, max_length=40)
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)
    include_footprint: bool = False


class PeriodsRequest(TargetFields):
    radius_deg: float = Field(0.003, gt=0, le=2)
    gap_days: float = Field(20, gt=0, le=365)
    release: Release = "all"


class ImageSearchRequest(TargetFields):
    cutout_size_deg: float = Field(0.1, gt=0, le=3.5)
    detector: int | None = Field(None, ge=1, le=6)
    release: Release = "all"
    limit: int = Field(6, ge=1, le=50)
    verify: bool = Field(False, description="Probe the archive URLs to confirm they are downloadable")


class SpectrumSearchRequest(TargetFields):
    release: Release = "all"
    extract_samples: bool = False
    max_samples: int = Field(6, ge=1, le=12)


class KnowledgeSearchRequest(_Strict):
    query: str = Field(..., min_length=2, max_length=300)
    language: Literal["tr", "en"] | None = None
    topic: str | None = Field(None, max_length=40)
    top_k: int = Field(4, ge=1, le=10)


class CandidateTarget(_Strict):
    object_name: str | None = Field(None, max_length=100)
    ra: float = Field(..., ge=0, le=360)
    dec: float = Field(..., ge=-90, le=90)


class CandidateCreateRequest(_Strict):
    origin: Literal["ai", "human"] = "human"
    created_by: str = Field(..., min_length=2, max_length=60, pattern=r"^[\w.\-@ ]+$")
    title: str | None = Field(None, max_length=120)
    target: CandidateTarget
    reason: str = Field(..., min_length=10, max_length=1000, description="Why this deserves a look")
    observation_ids: list[str] = Field(default_factory=list, max_length=50)


class ReviewRequest(_Strict):
    reviewer_id: str = Field(..., min_length=2, max_length=60, pattern=r"^[\w.\-@ ]+$")
    classification: Literal["real_motion", "real_brightness_change", "artifact", "known_object",
                            "no_change_visible", "cannot_tell"]
    self_reported_certainty: Literal["low", "medium", "high"]
    comment: str | None = Field(None, max_length=1000)
    observation_ids_inspected: list[str] = Field(default_factory=list, max_length=50)


class ReviewValidationRequest(_Strict):
    validator_id: str = Field(..., min_length=2, max_length=60, pattern=r"^[\w.\-@ ]+$")
    decision: Literal["accepted", "rejected"]
    note: str | None = Field(None, max_length=500)


class ConfirmationRequest(_Strict):
    recorded_by: str = Field(..., min_length=2, max_length=60, pattern=r"^[\w.\-@ ]+$")
    reference_url: str = Field(..., pattern=r"^https?://\S+$", max_length=500)
    reference_title: str = Field(..., min_length=5, max_length=300)
    note: str | None = Field(None, max_length=500)

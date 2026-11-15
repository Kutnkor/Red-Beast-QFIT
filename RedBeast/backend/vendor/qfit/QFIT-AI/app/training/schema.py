"""Canonical schema of a Q-FIT training / evaluation example (one JSON object per line).

No model weights are trained in this project (see docs/AI_TRAINING_PIPELINE.md). The same
examples serve three purposes: the evaluation suites, regression tests of the instructions,
and, if the team ever pays for Vertex AI supervised tuning, an export to its format.

Honesty fields
  synthetic            True when the example was written (by a person or an AI), not taken
                       from a real user conversation.
  annotation_status    who has looked at it; AI-drafted examples stay
                       'ai_drafted_pending_human_review' until a person reviews them.
  verification_status  whether the expected behaviour was checked against the cited sources.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CATEGORIES: dict[str, str] = {
    "A": "data retrieval: choose the right data tool and arguments",
    "B": "conceptual question answered from the knowledge base",
    "C": "no data / missing information reported plainly",
    "D": "ambiguity or missing target: ask for clarification",
    "E": "uncertainty: comparisons, time coverage, conflicting sources",
    "F": "citizen science: candidates are not discoveries",
    "G": "refusal to fabricate or overclaim (numbers, classifications, confidence)",
}
ANNOTATION_STATUSES = ("ai_drafted_pending_human_review", "human_reviewed", "human_validated")
VERIFICATION_STATUSES = ("unverified", "source_checked", "expert_verified")
SPLITS = ("train", "validation", "test")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ExampleInput(_Strict):
    message: str = Field(..., min_length=2, max_length=2000)
    context: dict[str, Any] | None = None
    history: list[dict[str, str]] = Field(default_factory=list)


class Expected(_Strict):
    """What a correct answer does. Everything is checkable by code; free text is optional."""
    behavior: str = Field(..., min_length=5, max_length=400, description="Plain description of the right behaviour")
    tools: list[str] = Field(default_factory=list, description="Acceptable first tool calls; empty = no data tool")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Arguments the first call must contain")
    required_tools: list[str] = Field(default_factory=list,
                                      description="Tools that must be called at some point in the turn, in any order")
    no_tool: bool = Field(False, description="True when no data tool may be called")
    relevant_chunks: list[str] = Field(default_factory=list, description="Knowledge chunk ids that answer it")
    must_mention: list[str] = Field(default_factory=list, description="Terms the answer must contain (any case)")
    must_not_mention: list[str] = Field(default_factory=list, description="Terms that indicate a wrong answer")
    reference_answer: str | None = Field(None, max_length=1500,
                                         description="Optional model answer; every number must be in the evidence")


class TrainingExample(_Strict):
    id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9\-_.]*$")
    category: Literal["A", "B", "C", "D", "E", "F", "G"]
    family: str = Field(..., pattern=r"^[a-z0-9][a-z0-9\-_]*$",
                        description="Examples that are translations or paraphrases share a family and "
                                    "always land in the same split")
    language: Literal["tr", "en"]
    input: ExampleInput
    expected: Expected
    source_refs: list[str] = Field(default_factory=list, description="Source registry ids")
    label: str = Field(..., pattern=r"^[a-z_]+$", description="Short behaviour label, e.g. tool_selection")
    verification_status: Literal["unverified", "source_checked", "expert_verified"] = "unverified"
    annotation_status: Literal["ai_drafted_pending_human_review", "human_reviewed",
                               "human_validated"] = "ai_drafted_pending_human_review"
    dataset_version: str = Field(..., min_length=1)
    synthetic: bool = True

    @model_validator(mode="after")
    def _honest_labels(self):
        if self.annotation_status == "ai_drafted_pending_human_review" and self.verification_status == "expert_verified":
            raise ValueError("an AI-drafted example nobody has reviewed cannot be expert_verified")
        if self.annotation_status == "ai_drafted_pending_human_review" and not self.synthetic:
            raise ValueError("an AI-drafted example is synthetic by definition")
        if self.expected.no_tool and (self.expected.tools or self.expected.required_tools):
            raise ValueError("expected.no_tool contradicts expected.tools / expected.required_tools")
        return self

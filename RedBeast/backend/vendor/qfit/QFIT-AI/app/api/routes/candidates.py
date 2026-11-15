"""Citizen-science candidates: create, review, validate, record an external confirmation, audit.

Every change is an event in the append-only, hash-chained log (app/citizen/store.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from app.api.dependencies import Container, get_container, require_team_token
from app.citizen.store import STATUSES
from app.models.requests import (CandidateCreateRequest, ConfirmationRequest, ReviewRequest,
                                 ReviewValidationRequest)
from app.models.responses import QFitResponse
from app.services import response_builder as rb
from app.utils.errors import InvalidInputError

router = APIRouter(tags=["citizen science"])
# Writes need the team token when QFIT_TEAM_TOKEN is set; reads stay public.
WRITE = [Depends(require_team_token)]
CandidateId = Path(..., pattern=r"^cand-[0-9a-f]{10}$", description="e.g. cand-3f9a01b2c4")
_NOT_DISCOVERY = "A candidate is not a discovery."


def _candidate(c: Container, intent: str, message: str, candidate: dict) -> QFitResponse:
    part = rb.from_candidate(candidate)
    return c.envelope({**part, "intent": intent, "message": f"{message} {_NOT_DISCOVERY}"})


@router.post("/candidates", dependencies=WRITE, response_model=QFitResponse, summary="Submit a candidate for human review")
async def create_candidate(body: CandidateCreateRequest, c: Container = Depends(get_container)) -> QFitResponse:
    candidate = await c.candidates.create(origin=body.origin, created_by=body.created_by, title=body.title,
                                          target=body.target.model_dump(), reason=body.reason,
                                          observation_ids=body.observation_ids)
    return c.envelope(rb.from_candidate(candidate))


@router.get("/candidates", response_model=QFitResponse, summary="List candidates")
async def list_candidates(status: str | None = Query(None, description=f"One of: {', '.join(STATUSES)}"),
                          limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                          c: Container = Depends(get_container)) -> QFitResponse:
    result = c.candidates.list(status, limit, offset)
    return c.envelope({"intent": "list_candidates",
                       "message": f"{result['total']} candidate(s). {_NOT_DISCOVERY}",
                       "data": {"candidates": result, "log_chain_valid": c.candidates.chain_valid},
                       "uncertainty": [] if c.candidates.chain_valid else
                       ["The candidate log failed its integrity check: some history may have been altered."]})


@router.get("/candidates/{candidate_id}", response_model=QFitResponse, summary="One candidate")
async def get_candidate(candidate_id: str = CandidateId, c: Container = Depends(get_container)) -> QFitResponse:
    candidate = c.candidates.get(candidate_id)
    return _candidate(c, "get_candidate", f"Candidate {candidate_id} has status {candidate['status']}.", candidate)


@router.post("/candidates/{candidate_id}/reviews", dependencies=WRITE, response_model=QFitResponse, summary="Add a human review")
async def add_review(body: ReviewRequest, candidate_id: str = CandidateId,
                     c: Container = Depends(get_container)) -> QFitResponse:
    candidate = await c.candidates.add_review(candidate_id, **body.model_dump())
    return _candidate(c, "review_candidate", f"Review recorded for {candidate_id}.", candidate)


@router.post("/candidates/{candidate_id}/reviews/{review_id}/validation", dependencies=WRITE, response_model=QFitResponse,
             summary="A second person accepts or rejects a review")
async def validate_review(body: ReviewValidationRequest, candidate_id: str = CandidateId,
                          review_id: str = Path(..., pattern=r"^[0-9a-f]{12}$"),
                          c: Container = Depends(get_container)) -> QFitResponse:
    candidate = await c.candidates.validate_review(candidate_id, review_id, **body.model_dump())
    return _candidate(c, "validate_review", f"Review {review_id} was {body.decision}.", candidate)


@router.post("/candidates/{candidate_id}/confirmation", dependencies=WRITE, response_model=QFitResponse,
             summary="Record an external scientific reference")
async def confirm_candidate(body: ConfirmationRequest, candidate_id: str = CandidateId,
                            c: Container = Depends(get_container)) -> QFitResponse:
    """Only an external reference (publication, professional follow-up) moves a candidate to
    `scientifically_confirmed`. The reference is recorded, not checked by Q-FIT."""
    if not body.reference_url.startswith("https://"):
        raise InvalidInputError("reference_url must be an https link to the external reference.")
    candidate = await c.candidates.confirm(candidate_id, **body.model_dump())
    part = rb.from_candidate(candidate)
    return c.envelope({**part, "intent": "confirm_candidate",
                       "message": f"An external reference was recorded for {candidate_id}.",
                       "uncertainty": ["Q-FIT records the reference as given; it does not verify the publication."]})


@router.get("/candidates/{candidate_id}/audit", response_model=QFitResponse, summary="Full event history")
async def audit_candidate(candidate_id: str = CandidateId, c: Container = Depends(get_container)) -> QFitResponse:
    audit = c.candidates.audit(candidate_id)
    return c.envelope({"intent": "audit_candidate",
                       "message": f"{len(audit['events'])} recorded event(s) for {candidate_id}.",
                       "data": {"audit": audit},
                       "uncertainty": [] if audit["log_chain_valid"] else
                       ["The candidate log failed its integrity check: some history may have been altered."]})

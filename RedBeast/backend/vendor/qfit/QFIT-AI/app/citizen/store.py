"""Citizen-science candidate store.

An append-only, hash-chained event log (JSON lines). The current state of every
candidate is rebuilt by replaying the log, so each status has a recorded cause and the
history cannot be rewritten without breaking the chain.

Status vocabulary (never merged):
  ai_generated_candidate   suggested by software, not looked at by anyone
  unreviewed_candidate     submitted by a person, waiting for review
  human_reviewed_candidate at least one recorded human review
  scientifically_confirmed an external reference (publication, professional follow-up) is recorded
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.errors import InvalidInputError, NotFoundError, QFitError

STATUSES = ("ai_generated_candidate", "unreviewed_candidate", "human_reviewed_candidate", "scientifically_confirmed")
CLASSIFICATIONS = ("real_motion", "real_brightness_change", "artifact", "known_object", "no_change_visible",
                   "cannot_tell")
_GENESIS = "0" * 16


class StoreError(QFitError):
    code, status_code = "candidate_store_error", 500


def _digest(prev: str, body: dict[str, Any]) -> str:
    return hashlib.sha256((prev + json.dumps(body, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:16]


class CandidateStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()
        self._events: list[dict[str, Any]] = []
        self._candidates: dict[str, dict[str, Any]] = {}
        self.chain_valid = True
        self._load()

    # ------------------------------------------------------------------ log
    def _load(self) -> None:
        if not self.path.is_file():
            return
        prev = _GENESIS
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                self.chain_valid = False
                continue
            body = {k: v for k, v in event.items() if k != "hash"}
            if event.get("prev_hash") != prev or event.get("hash") != _digest(prev, body):
                self.chain_valid = False
            prev = event.get("hash", prev)
            self._events.append(event)
            self._apply(event)

    async def _append(self, kind: str, actor: str, candidate_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            prev = self._events[-1]["hash"] if self._events else _GENESIS
            body = {"event_id": uuid.uuid4().hex[:12], "type": kind, "candidate_id": candidate_id, "actor": actor,
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "payload": payload,
                    "prev_hash": prev}
            event = {**body, "hash": _digest(prev, body)}
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            except OSError as exc:
                raise StoreError("The candidate log could not be written.") from exc
            self._events.append(event)
            self._apply(event)
            return event

    def _apply(self, event: dict[str, Any]) -> None:
        kind, cid, payload = event["type"], event["candidate_id"], event["payload"]
        if kind == "candidate_created":
            self._candidates[cid] = {**payload, "candidate_id": cid, "created_at": event["timestamp"],
                                     "created_by": event["actor"], "reviews": [], "confirmation": None}
            return
        candidate = self._candidates.get(cid)
        if candidate is None:
            return
        if kind == "review_submitted":
            candidate["reviews"].append({**payload, "review_id": event["event_id"], "reviewer_id": event["actor"],
                                         "submitted_at": event["timestamp"], "validation": None})
        elif kind == "review_validated":
            for review in candidate["reviews"]:
                if review["review_id"] == payload["review_id"]:
                    review["validation"] = {"decision": payload["decision"], "note": payload.get("note"),
                                            "validator_id": event["actor"], "validated_at": event["timestamp"]}
        elif kind == "candidate_confirmed":
            candidate["confirmation"] = {**payload, "recorded_by": event["actor"], "recorded_at": event["timestamp"]}

    # ---------------------------------------------------------------- views
    @staticmethod
    def _status(candidate: dict[str, Any]) -> str:
        if candidate["confirmation"]:
            return "scientifically_confirmed"
        if candidate["reviews"]:
            return "human_reviewed_candidate"
        return "ai_generated_candidate" if candidate["origin"] == "ai" else "unreviewed_candidate"

    def view(self, candidate: dict[str, Any]) -> dict[str, Any]:
        counts = Counter(r["classification"] for r in candidate["reviews"])
        return {**candidate, "status": self._status(candidate),
                "is_confirmed_discovery": candidate["confirmation"] is not None,
                "review_summary": {"reviews": len(candidate["reviews"]), "by_classification": dict(counts),
                                   "validated_for_dataset": sum(1 for r in candidate["reviews"] if r["validation"]
                                                                and r["validation"]["decision"] == "accepted"),
                                   "note": "Counts of human reviews. They are not probabilities."},
                "disclaimer": "A candidate is not a discovery. Only a recorded external reference changes "
                              "its status to scientifically_confirmed."}

    def get(self, candidate_id: str) -> dict[str, Any]:
        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise NotFoundError(f"No candidate with id '{candidate_id}'.")
        return self.view(candidate)

    def list(self, status: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        if status is not None and status not in STATUSES:
            raise InvalidInputError(f"status must be one of: {', '.join(STATUSES)}.")
        items = [self.view(c) for c in self._candidates.values()]
        if status:
            items = [c for c in items if c["status"] == status]
        items.sort(key=lambda c: c["created_at"], reverse=True)
        return {"total": len(items), "offset": offset, "limit": limit, "candidates": items[offset:offset + limit],
                "by_status": dict(Counter(self.view(c)["status"] for c in self._candidates.values()))}

    def audit(self, candidate_id: str) -> dict[str, Any]:
        self.get(candidate_id)
        return {"candidate_id": candidate_id, "log_chain_valid": self.chain_valid,
                "events": [e for e in self._events if e["candidate_id"] == candidate_id]}

    def validated_reviews(self) -> list[dict[str, Any]]:
        """Reviews accepted by a second person: the only ones eligible for a dataset."""
        out = []
        for candidate in self._candidates.values():
            for review in candidate["reviews"]:
                if review["validation"] and review["validation"]["decision"] == "accepted":
                    out.append({"candidate": {k: candidate[k] for k in ("candidate_id", "target", "observation_ids",
                                                                        "reason", "origin")}, "review": review})
        return out

    # -------------------------------------------------------------- commands
    async def create(self, *, origin: str, created_by: str, target: dict[str, Any], reason: str,
                     observation_ids: list[str], evidence: list[dict[str, Any]] | None = None,
                     title: str | None = None) -> dict[str, Any]:
        cid = "cand-" + uuid.uuid4().hex[:10]
        await self._append("candidate_created", created_by, cid, {
            "origin": origin, "title": title, "target": target, "reason": reason,
            "observation_ids": observation_ids, "evidence": evidence or []})
        return self.get(cid)

    async def add_review(self, candidate_id: str, *, reviewer_id: str, classification: str,
                         self_reported_certainty: str, comment: str | None,
                         observation_ids_inspected: list[str]) -> dict[str, Any]:
        self.get(candidate_id)
        await self._append("review_submitted", reviewer_id, candidate_id, {
            "classification": classification, "self_reported_certainty": self_reported_certainty,
            "comment": comment, "observation_ids_inspected": observation_ids_inspected})
        return self.get(candidate_id)

    async def validate_review(self, candidate_id: str, review_id: str, *, validator_id: str, decision: str,
                              note: str | None) -> dict[str, Any]:
        candidate = self.get(candidate_id)
        review = next((r for r in candidate["reviews"] if r["review_id"] == review_id), None)
        if review is None:
            raise NotFoundError(f"Candidate '{candidate_id}' has no review '{review_id}'.")
        if review["reviewer_id"] == validator_id:
            raise InvalidInputError("A review cannot be validated by the person who wrote it.")
        if review["validation"]:
            raise InvalidInputError("This review has already been validated.")
        await self._append("review_validated", validator_id, candidate_id,
                           {"review_id": review_id, "decision": decision, "note": note})
        return self.get(candidate_id)

    async def confirm(self, candidate_id: str, *, recorded_by: str, reference_url: str, reference_title: str,
                      note: str | None) -> dict[str, Any]:
        candidate = self.get(candidate_id)
        if not candidate["reviews"]:
            raise InvalidInputError("A candidate needs at least one human review before a confirmation "
                                    "reference can be recorded.")
        await self._append("candidate_confirmed", recorded_by, candidate_id,
                           {"reference_url": reference_url, "reference_title": reference_title, "note": note})
        return self.get(candidate_id)

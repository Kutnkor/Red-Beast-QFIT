"""Candidate store: status rules, separation of duties, hash chain."""
from __future__ import annotations

import json

import pytest

from app.citizen.store import CandidateStore
from app.utils.errors import InvalidInputError, NotFoundError

TARGET = {"object_name": None, "ra": 56.75, "dec": 24.12}


@pytest.fixture
def store(tmp_path) -> CandidateStore:
    return CandidateStore(tmp_path / "events.jsonl")


async def _candidate(store, origin="human"):
    return await store.create(origin=origin, created_by="ayse", target=TARGET, reason="Seems to move between exposures.",
                              observation_ids=["spherex_qr3:2026W21_1A_0491_2:D4"])


async def test_status_moves_only_through_recorded_events(store):
    ai = await _candidate(store, origin="ai")
    assert ai["status"] == "ai_generated_candidate" and ai["is_confirmed_discovery"] is False
    human = await _candidate(store)
    assert human["status"] == "unreviewed_candidate"
    with pytest.raises(InvalidInputError):                       # no confirmation without a review
        await store.confirm(human["candidate_id"], recorded_by="mehmet", reference_url="https://doi.org/x",
                            reference_title="A paper", note=None)
    reviewed = await store.add_review(human["candidate_id"], reviewer_id="mehmet", classification="real_motion",
                                      self_reported_certainty="medium", comment=None, observation_ids_inspected=[])
    assert reviewed["status"] == "human_reviewed_candidate"
    assert reviewed["review_summary"]["by_classification"] == {"real_motion": 1}
    confirmed = await store.confirm(human["candidate_id"], recorded_by="mehmet", reference_url="https://doi.org/x",
                                    reference_title="A paper", note=None)
    assert confirmed["status"] == "scientifically_confirmed" and confirmed["is_confirmed_discovery"] is True
    assert store.list()["by_status"] == {"ai_generated_candidate": 1, "scientifically_confirmed": 1}
    assert store.list(status="ai_generated_candidate")["total"] == 1
    with pytest.raises(InvalidInputError):
        store.list(status="discovered")
    with pytest.raises(NotFoundError):
        store.get("cand-0000000000")


async def test_reviews_need_a_second_person_to_enter_a_dataset(store):
    cid = (await _candidate(store))["candidate_id"]
    candidate = await store.add_review(cid, reviewer_id="mehmet", classification="artifact",
                                       self_reported_certainty="high", comment="Scattered light", observation_ids_inspected=[])
    review_id = candidate["reviews"][0]["review_id"]
    assert store.validated_reviews() == []
    with pytest.raises(InvalidInputError):
        await store.validate_review(cid, review_id, validator_id="mehmet", decision="accepted", note=None)
    await store.validate_review(cid, review_id, validator_id="zeynep", decision="accepted", note=None)
    with pytest.raises(InvalidInputError):
        await store.validate_review(cid, review_id, validator_id="ali", decision="rejected", note=None)
    assert len(store.validated_reviews()) == 1


async def test_log_replays_and_detects_tampering(store, tmp_path):
    cid = (await _candidate(store))["candidate_id"]
    await store.add_review(cid, reviewer_id="mehmet", classification="cannot_tell", self_reported_certainty="low",
                           comment=None, observation_ids_inspected=[])
    replay = CandidateStore(store.path)
    assert replay.chain_valid and replay.get(cid)["status"] == "human_reviewed_candidate"
    assert [e["type"] for e in replay.audit(cid)["events"]] == ["candidate_created", "review_submitted"]
    lines = store.path.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[1])
    event["payload"]["classification"] = "real_motion"            # rewrite history
    store.path.write_text(lines[0] + "\n" + json.dumps(event) + "\n", encoding="utf-8")
    assert CandidateStore(store.path).chain_valid is False

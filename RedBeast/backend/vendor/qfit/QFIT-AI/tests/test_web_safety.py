"""Protections needed before the backend is public: daily AI budget, team token for
candidate writes, and the client IP used by the per-client rate limit."""
from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.ai.llm_provider import LLMTurn
from app.api.dependencies import DailyBudget
from app.main import create_app
from tests.conftest import ScriptedProvider

CANDIDATE = {"created_by": "ayse", "target": {"ra": 56.75, "dec": 24.12},
             "reason": "The source shifts between two exposures."}


def test_daily_budget_counts_and_resets():
    budget = DailyBudget(2)
    assert budget.take() and budget.take() and not budget.take()
    assert budget.status()["remaining"] == 0
    budget.day = "1999-01-01"                       # a new UTC day starts a new count
    assert budget.take() and budget.status()["used_today"] == 1
    assert DailyBudget(0).take() and DailyBudget(0).status()["limit_per_day"] is None


def test_chat_falls_back_when_the_daily_budget_is_used(settings, make_container):
    provider = ScriptedProvider([LLMTurn(text="A brown dwarf is a substellar object.")])
    with TestClient(create_app(settings, make_container(provider, chat_daily_limit=1))) as client:
        first = client.post("/chat", json={"message": "What is a brown dwarf?"}).json()
        second = client.post("/chat", json={"message": "What is a brown dwarf?"}).json()
        health = client.get("/health").json()["data"]
    assert first["message_source"] == "ai_generated"
    assert second["success"] and second["data"]["fallback"]["reason_code"] == "rate_limited"
    assert "daily AI budget" in second["data"]["fallback"]["reason"] and len(provider.calls) == 1
    assert health["chat_daily_budget"]["used_today"] == 1 and health["chat_daily_budget"]["remaining"] == 0


def test_candidate_writes_need_the_team_token_when_set(settings, make_container):
    container = make_container(qfit_team_token=SecretStr("team-secret"))
    with TestClient(create_app(settings, container)) as client:
        denied = client.post("/api/v1/candidates", json=CANDIDATE)
        wrong = client.post("/api/v1/candidates", json=CANDIDATE, headers={"X-QFit-Token": "nope"})
        ok = client.post("/api/v1/candidates", json=CANDIDATE, headers={"X-QFit-Token": "team-secret"})
        cid = ok.json()["data"]["candidate"]["candidate_id"]
        review = client.post(f"/api/v1/candidates/{cid}/reviews", json={
            "reviewer_id": "mehmet", "classification": "artifact", "self_reported_certainty": "low"})
        read = client.get(f"/api/v1/candidates/{cid}")                      # reads stay public
        health = client.get("/health").json()["data"]
    assert denied.status_code == 401 and denied.json()["error"]["code"] == "unauthorized"
    assert wrong.status_code == 401 and "team-secret" not in wrong.text
    assert ok.status_code == 200 and review.status_code == 401 and read.status_code == 200
    assert health["candidate_writes_protected"] is True


def test_without_a_token_candidate_writes_stay_open_and_health_says_so(client):
    assert client.post("/api/v1/candidates", json=CANDIDATE).status_code == 200
    assert client.get("/health").json()["data"]["candidate_writes_protected"] is False


def test_a_slow_chat_turn_falls_back_instead_of_hanging(settings, make_container):
    import asyncio

    class Slow:
        name, model = "slow", "slow"

        async def generate(self, **_):
            await asyncio.sleep(5)

    with TestClient(create_app(settings, make_container(Slow(), chat_timeout_seconds=0.2))) as client:
        body = client.post("/chat", json={"message": "What is a brown dwarf?"}).json()
    assert body["success"] and body["data"]["fallback"]["reason_code"] == "upstream_error"
    assert "longer than 0.2 s" in body["data"]["fallback"]["reason"]


async def test_archive_timeouts_are_not_retried():
    import httpx
    import pytest
    from app.astronomy.archive_client import ArchiveClient
    from app.utils.errors import UpstreamUnavailableError
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("slow", request=request)
    archive = ArchiveClient("https://irsa.ipac.caltech.edu", timeout=1, max_retries=2, cache_ttl=0,
                            transport=httpx.MockTransport(handler))
    with pytest.raises(UpstreamUnavailableError, match="did not respond in time"):
        await archive.request("GET", "https://irsa.ipac.caltech.edu/SIA")
    assert len(calls) == 1
    await archive.aclose()


def test_cors_allows_the_token_header(client):
    preflight = client.options("/api/v1/candidates", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-qfit-token"})
    assert preflight.status_code == 200 and "x-qfit-token" in preflight.headers["access-control-allow-headers"].lower()


def test_placeholder_tool_arguments_are_dropped():
    from app.ai.tool_registry import clean_arguments
    assert clean_arguments({"object_name": "M31", "ra": 0, "dec": 0, "start_utc": "", "limit": 1}) == \
        {"object_name": "M31", "limit": 1}
    assert clean_arguments({"ra": 0, "dec": 0}) == {"ra": 0, "dec": 0}          # a real request for RA 0, Dec 0
    assert clean_arguments({"object_name": "M31", "ra": 10.5, "dec": 41.2}) == {"object_name": "M31", "ra": 10.5, "dec": 41.2}

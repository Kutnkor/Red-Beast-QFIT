"""Contract tests for the local mock. No external provider is contacted."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from blinkspace.api import RateLimiter, create_app
from blinkspace.assistant import DailyCounter, build_assistant_router


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("BLINKSPACE_ASSISTANT_PROVIDER", raising=False)
    monkeypatch.delenv("BLINKSPACE_ASSISTANT_DAILY_LIMIT", raising=False)
    app = FastAPI()
    app.include_router(build_assistant_router(RateLimiter))
    with TestClient(app) as client:
        yield client


def events(response):
    return [(block.splitlines()[0][7:], json.loads(block.splitlines()[1][6:])) for block in response.text.strip().split("\n\n")]


def test_default_and_unknown_provider_cannot_enable_model(client, monkeypatch):
    assert client.get("/api/assistant/status").json() == {"enabled": False, "provider": None}
    assert client.post("/api/assistant/chat", json={"message": "hello"}).status_code == 503
    monkeypatch.setenv("BLINKSPACE_ASSISTANT_PROVIDER", "anthropic")
    assert client.get("/api/assistant/status").json() == {"enabled": False, "provider": None}


def test_main_application_exposes_disabled_contract(settings, monkeypatch):
    monkeypatch.delenv("BLINKSPACE_ASSISTANT_PROVIDER", raising=False)
    with TestClient(create_app(settings=settings, start_workers=False)) as client:
        assert client.get("/api/assistant/status").json() == {"enabled": False, "provider": None}
        response = client.post("/api/assistant/chat", json={"message": "hello"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "assistant_disabled"
        assert "connect-src 'self'" in response.headers["content-security-policy"]


def test_mock_stream_and_manual_tool_round_trip(client, monkeypatch):
    monkeypatch.setenv("BLINKSPACE_ASSISTANT_PROVIDER", "mock")
    assert client.get("/api/assistant/status").json() == {"enabled": True, "provider": "mock"}
    response = client.post("/api/assistant/chat", json={"message": "hello", "context": {"ui_language": "en"}})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    stream = events(response)
    assert [event for event, _ in stream] == ["text", "command", "sources", "done"]
    command = stream[1][1]
    assert command == {"tool_use_id": "mock_command_1", "name": "set_year", "args": {"year": 2100}, "requires_confirmation": False}
    result = client.post("/api/assistant/chat", json={"context": {"ui_language": "tr"}, "tool_results": [{"tool_use_id": command["tool_use_id"], "ok": True, "result": {"year": 2100}}]})
    assert [event for event, _ in events(result)] == ["text", "done"]
    assert "Komut sonucu" in events(result)[0][1]["delta"]


@pytest.mark.parametrize("message,name", [("mock:save", "save_view"), ("mock:search", "start_search")])
def test_write_and_network_commands_require_confirmation(client, monkeypatch, message, name):
    monkeypatch.setenv("BLINKSPACE_ASSISTANT_PROVIDER", "mock")
    command = events(client.post("/api/assistant/chat", json={"message": message}))[1][1]
    assert command["name"] == name
    assert command["requires_confirmation"] is True


def test_failed_client_tool_has_error_event(client, monkeypatch):
    monkeypatch.setenv("BLINKSPACE_ASSISTANT_PROVIDER", "mock")
    response = client.post("/api/assistant/chat", json={"tool_results": [{"tool_use_id": "mock_command_1", "ok": False, "result": {}}]})
    assert [event for event, _ in events(response)] == ["error", "done"]


@pytest.mark.parametrize("body", [
    {"message": "hello", "history": [{"role": "user", "content": "a"}] * 11},
    {"message": "hello", "context": {"value": "a" * 4096}},
    {"message": "hello", "context": {"value": "ğ" * 2050}},
    {"message": "hello", "context": {"target": {"edit_key": "private"}}},
    {"message": "hello", "context": {"marks": [{"note": "private"}]}},
    {"message": "hello", "unexpected": "not allowed"},
    {"message": "hello", "history": [{"role": "system", "content": "ignored"}]},
    {},
])
def test_input_limits_and_private_fields(client, monkeypatch, body):
    monkeypatch.setenv("BLINKSPACE_ASSISTANT_PROVIDER", "mock")
    assert client.post("/api/assistant/chat", json=body).status_code == 422


def test_rate_and_daily_limits(client, monkeypatch):
    monkeypatch.setenv("BLINKSPACE_ASSISTANT_PROVIDER", "mock")
    for _ in range(6):
        assert client.post("/api/assistant/chat", json={"message": "hello"}).status_code == 200
    response = client.post("/api/assistant/chat", json={"message": "hello"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


def test_daily_budget_and_invalid_limit_fail_closed(client, monkeypatch):
    monkeypatch.setenv("BLINKSPACE_ASSISTANT_PROVIDER", "mock")
    monkeypatch.setenv("BLINKSPACE_ASSISTANT_DAILY_LIMIT", "1")
    assert client.post("/api/assistant/chat", json={"message": "one"}).status_code == 200
    assert client.post("/api/assistant/chat", json={"message": "two"}).json()["detail"]["code"] == "assistant_daily_limit"
    monkeypatch.setenv("BLINKSPACE_ASSISTANT_DAILY_LIMIT", "bad")
    assert client.post("/api/assistant/chat", json={"message": "three"}).status_code == 429


def test_daily_counter_resets_only_at_utc_day_boundary():
    now = [86400.0 - 1]
    counter = DailyCounter(lambda: now[0])
    assert counter.allow(1)
    assert not counter.allow(1)
    now[0] = 86400.0
    assert counter.allow(1)


def test_no_message_content_logged(client, monkeypatch, caplog):
    monkeypatch.setenv("BLINKSPACE_ASSISTANT_PROVIDER", "mock")
    client.post("/api/assistant/chat", json={"message": "UNIQUE_PRIVATE_MESSAGE_42"})
    assert "UNIQUE_PRIVATE_MESSAGE_42" not in caplog.text

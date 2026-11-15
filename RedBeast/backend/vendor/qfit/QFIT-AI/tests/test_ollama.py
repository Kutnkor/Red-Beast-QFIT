"""Ollama provider, provider selection and the chat fallback when the model fails."""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai.agent import QFitAgent
from app.ai.ollama_client import OllamaProvider
from app.main import create_app
from app.utils.errors import AIUnavailableError, RateLimitedError, UpstreamError


class FakeOllama:
    def __init__(self, replies):
        self.replies, self.bodies = list(replies), []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(json.loads(request.content))
        status, payload = self.replies.pop(0)
        return httpx.Response(status, json=payload)


def provider(fake) -> OllamaProvider:
    return OllamaProvider("http://ollama.test:11434/", "test-model", transport=httpx.MockTransport(fake))


async def test_ollama_runs_the_tool_loop(container):
    fake = FakeOllama([
        (200, {"message": {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "resolve_object_coordinates", "arguments": {"name": "M31"}}}]}}),
        (200, {"message": {"role": "assistant", "content": "<think>plan</think>M 31 is at RA 10.6847."}}),
    ])
    result = await QFitAgent(provider(fake), container.registry).run("Where is M31?")
    assert [r.name for r in result.tool_runs] == ["resolve_object_coordinates"]
    assert result.text == "M 31 is at RA 10.6847." and result.model == "test-model"
    first, second = fake.bodies
    assert first["model"] == "test-model" and first["stream"] is False and first["messages"][0]["role"] == "system"
    assert first["tools"][0]["type"] == "function" and "name" in first["tools"][0]["function"]
    assert second["messages"][-2]["tool_calls"][0]["function"]["name"] == "resolve_object_coordinates"
    tool_message = second["messages"][-1]
    assert tool_message["role"] == "tool" and tool_message["tool_name"] == "resolve_object_coordinates"
    assert json.loads(tool_message["content"])["ok"] is True


async def test_ollama_accepts_arguments_as_json_text():
    fake = FakeOllama([(200, {"message": {"content": "", "tool_calls": [
        {"function": {"name": "search_spherex_observations", "arguments": '{"ra": 1.5, "dec": 2}'}}]}})])
    turn = await provider(fake).generate(system="s", messages=[{"role": "user", "content": "x"}], tools=[])
    assert turn.tool_calls[0].args == {"ra": 1.5, "dec": 2} and "tools" not in fake.bodies[0]


async def test_ollama_errors_are_mapped():
    with pytest.raises(AIUnavailableError, match="ollama pull test-model"):
        await provider(FakeOllama([(404, {"error": "model not found"})])).generate(system="s", messages=[], tools=[])
    with pytest.raises(UpstreamError, match="HTTP 500"):
        await provider(FakeOllama([(500, {"error": "boom"})])).generate(system="s", messages=[], tools=[])

    def down(request):
        raise httpx.ConnectError("refused")
    unreachable = OllamaProvider("http://ollama.test", "m", transport=httpx.MockTransport(down))
    with pytest.raises(AIUnavailableError, match="not reachable"):
        await unreachable.generate(system="s", messages=[], tools=[])
    with pytest.raises(AIUnavailableError):
        OllamaProvider("http://x", "")


def test_provider_selection_and_health(settings, make_container):
    gemini_less = make_container(llm_provider="ollama", ollama_model="")
    assert gemini_less.ai_configured is False
    with pytest.raises(AIUnavailableError, match="OLLAMA_MODEL"):
        gemini_less.agent
    local = make_container(llm_provider="ollama", ollama_model="qwen-test")
    assert local.ai_configured is True and local.ai_provider_name == "ollama"
    assert isinstance(local.agent.provider, OllamaProvider) and local.agent.provider.model == "qwen-test"
    with TestClient(create_app(settings, local)) as client:
        data = client.get("/health").json()["data"]
    assert data["ai_provider"] == "ollama" and data["ai_model"] == "qwen-test" and data["ai_fallback_enabled"] is True


@pytest.mark.parametrize("error,code", [(RateLimitedError("daily quota used up"), "rate_limited"),
                                        (UpstreamError("HTTP 503"), "upstream_error")])
def test_chat_falls_back_when_the_model_fails(settings, make_container, error, code):
    class Failing:
        name, model = "failing", "failing"

        async def generate(self, **_):
            raise error

    with TestClient(create_app(settings, make_container(Failing()))) as client:
        body = client.post("/chat", json={"message": "What is a brown dwarf?"}).json()
    assert body["success"] is True and body["intent"] == "knowledge_fallback"
    assert body["data"]["fallback"]["reason_code"] == code and body["message_source"] == "system"
    assert body["data"]["knowledge"]["hits"][0]["chunk_id"] == "brown-dwarfs:en:1"
    assert body["message"].startswith("The AI assistant cannot answer right now") and "Source:" in body["message"]
    assert body["meta"]["tools_called"] == [] and body["meta"]["ai_model"] is None

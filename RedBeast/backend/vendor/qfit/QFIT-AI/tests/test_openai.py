"""OpenAI provider (Responses API + function calling), served by a fake HTTP endpoint."""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai.agent import QFitAgent
from app.ai.openai_client import OpenAIProvider
from app.config import Settings
from app.main import create_app
from app.utils.errors import AIUnavailableError, RateLimitedError, UpstreamError


class FakeOpenAI:
    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status, payload = self.replies.pop(0)
        return httpx.Response(status, json=payload)


def reply(content=None, calls=()):
    output = [{"type": "reasoning", "id": "rs_1", "summary": []}]
    output += [{"type": "function_call", "id": f"fc_{i}", "call_id": call_id, "name": name, "arguments": args}
               for i, (call_id, name, args) in enumerate(calls)]
    if content is not None:
        output.append({"type": "message", "role": "assistant",
                       "content": [{"type": "output_text", "text": content, "annotations": []}]})
    return 200, {"id": "resp_1", "output": output}


def provider(fake) -> OpenAIProvider:
    return OpenAIProvider("sk-test-secret", "test-model", base_url="https://openai.test/v1/",
                          transport=httpx.MockTransport(fake))


async def test_openai_runs_the_tool_loop(container):
    fake = FakeOpenAI([
        reply(calls=[("call_1", "resolve_object_coordinates", '{"name": "M31"}')]),
        reply("M 31 is at RA 10.6847, Dec 41.2688."),
    ])
    result = await QFitAgent(provider(fake), container.registry).run("Where is M31?")
    assert [r.name for r in result.tool_runs] == ["resolve_object_coordinates"] and result.model == "test-model"
    assert result.text == "M 31 is at RA 10.6847, Dec 41.2688." and result.unsupported_numbers == []
    first, second = (json.loads(r.content) for r in fake.requests)
    assert fake.requests[0].url == "https://openai.test/v1/responses"
    assert fake.requests[0].headers["authorization"] == "Bearer sk-test-secret"
    assert first["model"] == "test-model" and "temperature" not in first and "RESPONSE LANGUAGE" in first["instructions"]
    assert first["input"][-1]["role"] == "user" and first["tools"][0]["type"] == "function" and first["tools"][0]["name"]
    # the model's own output (reasoning + function call) is replayed, then the tool output
    replayed = second["input"][-3:]
    assert [i["type"] for i in replayed] == ["reasoning", "function_call", "function_call_output"]
    assert replayed[2]["call_id"] == "call_1" and json.loads(replayed[2]["output"])["ok"] is True


async def test_openai_bad_arguments_go_back_as_a_validation_error(container):
    fake = FakeOpenAI([reply(calls=[("c", "search_spherex_observations", "{oops")]),
                       reply("Sorry, I could not run that search.")])
    result = await QFitAgent(provider(fake), container.registry).run("search")
    assert result.tool_runs[0].outcome["error"]["code"] == "invalid_arguments"


@pytest.mark.parametrize("status,error,exc,text", [
    (401, {"code": "invalid_api_key"}, AIUnavailableError, "rejected"),
    (429, {"code": "insufficient_quota"}, RateLimitedError, "no API credit"),
    (429, {"code": "rate_limit_exceeded"}, RateLimitedError, "rate limit"),
    (404, {"code": "model_not_found"}, AIUnavailableError, "OPENAI_MODEL"),
    (500, {"type": "server_error"}, UpstreamError, "HTTP 500"),
    (400, {"type": "invalid_request_error", "param": "reasoning_effort"}, UpstreamError, "parameter reasoning_effort"),
])
async def test_openai_errors_are_mapped_without_the_key(status, error, exc, text):
    fake = FakeOpenAI([(status, {"error": {"message": "key sk-test-secret ...", **error}})])
    with pytest.raises(exc) as info:
        await provider(fake).generate(system="s", messages=[{"role": "user", "content": "x"}], tools=[])
    assert text in info.value.message and "sk-test" not in info.value.message


def test_openai_selection_secret_and_fallback(settings, make_container):
    configured = Settings(_env_file=None, openai_api_key="sk-super-secret")
    assert "sk-super" not in repr(configured) and "sk-super" not in configured.model_dump_json()
    missing = make_container(llm_provider="openai", openai_model="test-model")
    assert missing.ai_configured is False
    with TestClient(create_app(settings, missing)) as client:
        body = client.post("/chat", json={"message": "What is a brown dwarf?"}).json()
        health = client.get("/health").json()["data"]
    assert body["intent"] == "knowledge_fallback" and "OPENAI_API_KEY" in body["data"]["fallback"]["reason"]
    assert health["ai_provider"] == "openai" and health["ai_model"] == "test-model"
    from pydantic import SecretStr
    ready = make_container(llm_provider="openai", openai_api_key=SecretStr("sk-x"), openai_model="test-model")
    assert ready.ai_configured and isinstance(ready.agent.provider, OpenAIProvider)

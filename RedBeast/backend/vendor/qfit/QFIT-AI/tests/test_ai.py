"""AI layer: tool registry, agent loop, Gemini adapter and the /chat endpoint.

The scripted provider proves the plumbing (tool selection -> validated call -> real
service -> structured answer). Whether Gemini itself picks the right tool can only be
shown by the live tests at the bottom, which need GEMINI_API_KEY."""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.ai.agent import QFitAgent, compact_for_model
from app.ai.gemini_client import GeminiProvider
from app.ai.llm_provider import LLMTurn
from app.ai.prompts import INSTRUCTION_SETS, SYSTEM_PROMPT, build_system_prompt, render_user_message
from app.main import create_app
from app.utils.errors import AIUnavailableError, RateLimitedError
from tests.conftest import ScriptedProvider, call

EXPECTED_TOOLS = ["search_celestial_object", "resolve_object_coordinates", "search_spherex_observations",
                  "get_spherex_observation_metadata", "retrieve_spherex_image", "retrieve_spherex_spectral_data",
                  "search_objects_by_coordinates", "get_available_observation_periods", "request_clarification",
                  "search_knowledge_base", "submit_candidate_for_review"]


def test_registry_exposes_the_documented_tools(container):
    assert container.registry.names() == EXPECTED_TOOLS
    for declaration in container.registry.declarations():
        schema = declaration["parameters"]
        assert declaration["description"] and schema["type"] == "object"
        assert all("anyOf" not in spec and "title" not in spec for spec in schema["properties"].values())
    cone = container.registry.get("search_objects_by_coordinates").json_schema()
    assert cone["required"] == ["ra", "dec"] and cone["properties"]["ra"]["type"] == "number"


async def test_tool_arguments_are_validated(container):
    bad = await container.registry.execute("search_spherex_observations", {"ra": 400, "dec": 0})
    assert bad["ok"] is False and bad["error"]["code"] == "invalid_arguments"
    missing = await container.registry.execute("search_spherex_observations", {"radius_deg": 0.1})
    assert missing["ok"] is False and "object_name" in missing["error"]["message"]
    extra = await container.registry.execute("resolve_object_coordinates", {"name": "M31", "bogus": 1})
    assert extra["ok"] is False
    unknown = await container.registry.execute("launch_rocket", {})
    assert unknown["error"]["code"] == "unknown_tool"


async def test_tool_failures_are_returned_not_raised(container, fake_archive):
    fake_archive.fail_next = [503, 503]
    outcome = await container.registry.execute("search_spherex_observations", {"ra": 1.0, "dec": 2.0})
    assert outcome == {"ok": False, "error": {"code": "upstream_error", "retryable": True, "details": {},
                                               "message": "IRSA SIA2 returned server error 503."}}


async def test_agent_runs_function_calls_and_builds_structured_answer(container):
    provider = ScriptedProvider([
        call("resolve_object_coordinates", name="Andromeda Galaxy"),
        call("search_spherex_observations", object_name="Andromeda Galaxy"),
        LLMTurn(text="Andromeda (M 31) is at RA 10.6847, Dec 41.2688; the archive lists 6 files."),
    ])
    result = await QFitAgent(provider, container.registry).run("Show me the Andromeda Galaxy.")
    assert [r.name for r in result.tool_runs] == ["resolve_object_coordinates", "search_spherex_observations"]
    assert result.intent == "search_observations" and result.text.startswith("Andromeda")
    assert result.parts["object"]["name"] == "M 31"
    assert result.parts["data"]["spherex_available"] is True and len(result.parts["data"]["observations"]) == 6
    kinds = [a["type"] for a in result.parts["actions"]]
    assert kinds == ["display_object", "focus_map", "display_observations"]      # de-duplicated
    assert not any("was not checked" in u for u in result.parts["uncertainty"])  # it was checked this turn
    focus = result.parts["actions"][1]["payload"]
    assert focus == {"ra": pytest.approx(10.684708), "dec": pytest.approx(41.26875), "frame": "ICRS"}
    # the tool results were fed back to the model, and the tool list was offered each turn
    tool_messages = [m for m in provider.calls[-1]["messages"] if m["role"] == "tool"]
    assert len(tool_messages) == 2 and tool_messages[0]["result"]["ok"] is True
    assert len(provider.calls[0]["tools"]) == len(EXPECTED_TOOLS)


async def test_agent_reports_no_data_without_inventing_observations(container):
    provider = ScriptedProvider([call("search_spherex_observations", ra=0.0, dec=-85.0),
                                 LLMTurn(text="No SPHEREx images are available there.")])
    result = await QFitAgent(provider, container.registry).run("Any SPHEREx data at RA 0 Dec -85?")
    assert result.parts["data"]["spherex_available"] is False and result.parts["data"]["observations"] == []
    assert result.parts["data"]["search"]["status"] == "no_data"


async def test_agent_clarification_ends_the_turn(container):
    provider = ScriptedProvider([call("request_clarification", question="Which region do you mean?",
                                      options=["Give an object name", "Give RA and Dec"])])
    result = await QFitAgent(provider, container.registry).run("Find brown dwarfs in this region.")
    assert result.intent == "clarification_needed" and result.text == "Which region do you mean?"
    assert result.parts["actions"][0]["type"] == "request_clarification" and len(provider.calls) == 1


async def test_agent_surfaces_tool_errors(container):
    provider = ScriptedProvider([call("search_spherex_observations", ra=999, dec=0),
                                 LLMTurn(text="That right ascension is not valid.")])
    result = await QFitAgent(provider, container.registry).run("Search RA 999")
    assert result.intent == "error" and result.parts["actions"][-1]["type"] == "show_error"
    assert result.parts["data"]["tool_errors"][0]["code"] == "invalid_arguments"


async def test_agent_stops_after_max_steps(container):
    provider = ScriptedProvider([call("resolve_object_coordinates", name="M31")] * 3)
    result = await QFitAgent(provider, container.registry, max_steps=3).run("loop")
    assert len(result.tool_runs) == 3 and "could not finish" in result.text


def test_large_results_are_compacted_for_the_model_only():
    result = {"ok": True, "result": {"observations": [{"observation_id": i, "footprint": "POLYGON"} for i in range(30)],
                                     "sources": [1], "total": 30}}
    compact = compact_for_model(result)
    assert len(compact["result"]["observations"]) == 8 and "footprint" not in compact["result"]["observations"][0]
    assert compact["result"]["observations_omitted_from_this_view"] == 22 and compact["result"]["total"] == 30
    assert len(result["result"]["observations"]) == 30


def test_prompt_rules_and_context_rendering():
    assert "Never state a coordinate" in INSTRUCTION_SETS["v1"]                     # v1 kept as baseline
    assert SYSTEM_PROMPT == INSTRUCTION_SETS["v2"]
    for rule in ("comes from a tool result or a knowledge excerpt", "It never shows that SPHEREx observed it",
                 "Never call it a discovery", "Never give a confidence percentage", "No data means no data"):
        assert rule in SYSTEM_PROMPT
    turkish = build_system_prompt("v2", "tr", "beginner")
    assert "RESPONSE LANGUAGE: Turkish" in turkish and "USER LEVEL: beginner" in turkish
    assert "RESPONSE LANGUAGE" not in build_system_prompt("v1", "tr")
    assert render_user_message("hi", None) == "hi"
    assert "- ra: 10.5" in render_user_message("What is here?", {"ra": 10.5, "dec": None})
    assert "locale" not in render_user_message("x", {"locale": "tr", "ra": 1.0})


# ------------------------------------------------------------------ Gemini adapter
class _FakeGeminiModels:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.kwargs = response, error, None

    async def generate_content(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def _gemini(response=None, error=None):
    models = _FakeGeminiModels(response, error)
    return GeminiProvider("test-key", "gemini-test", client=SimpleNamespace(aio=SimpleNamespace(models=models))), models


async def test_gemini_adapter_sends_declarations_and_parses_function_calls(container):
    from google.genai import types
    model_content = types.Content(role="model", parts=[types.Part(
        function_call=types.FunctionCall(name="resolve_object_coordinates", args={"name": "M31"}))])
    response = types.GenerateContentResponse(candidates=[types.Candidate(content=model_content)])
    provider, models = _gemini(response)
    turn = await provider.generate(system="sys", messages=[{"role": "user", "content": "Show me M31"}],
                                   tools=container.registry.declarations())
    assert turn.tool_calls[0].name == "resolve_object_coordinates" and turn.tool_calls[0].args == {"name": "M31"}
    assert turn.raw is model_content
    config = models.kwargs["config"]
    assert models.kwargs["model"] == "gemini-test" and config.system_instruction == "sys"
    assert config.automatic_function_calling.disable is True
    names = [d.name for d in config.tools[0].function_declarations]
    assert names == EXPECTED_TOOLS and config.tools[0].function_declarations[0].parameters_json_schema["type"] == "object"

    # second round: the model turn is replayed verbatim and tool results go back as function responses
    response2 = types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(role="model", parts=[types.Part(text="M31 is at RA 10.68.")]))])
    provider, models = _gemini(response2)
    turn2 = await provider.generate(system="sys", tools=[], messages=[
        {"role": "user", "content": "Show me M31"},
        {"role": "assistant", "content": "", "raw": model_content},
        {"role": "tool", "name": "resolve_object_coordinates", "result": {"ok": True}}])
    contents = models.kwargs["contents"]
    assert turn2.text == "M31 is at RA 10.68." and turn2.tool_calls == []
    assert [c.role for c in contents] == ["user", "model", "user"] and contents[1] is model_content
    assert contents[2].parts[0].function_response.name == "resolve_object_coordinates"
    assert contents[2].parts[0].function_response.response == {"result": {"ok": True}}


async def test_gemini_errors_are_mapped_without_leaking_details():
    from google.genai import errors
    provider, _ = _gemini(error=errors.APIError(429, {"error": {"message": "quota for key AIza-secret"}}))
    with pytest.raises(RateLimitedError) as info:
        await provider.generate(system="s", messages=[{"role": "user", "content": "x"}], tools=[])
    assert "AIza" not in info.value.message
    provider, _ = _gemini(error=errors.APIError(403, {"error": {"message": "bad key"}}))
    with pytest.raises(AIUnavailableError):
        await provider.generate(system="s", messages=[{"role": "user", "content": "x"}], tools=[])
    provider, _ = _gemini(error=errors.APIError(429, {"error": {"message": "Generate content requests per day limit "
                                                                           "exceeded on Free Tier.", "status": "RESOURCE_EXHAUSTED"}}))
    with pytest.raises(RateLimitedError) as daily:
        await provider.generate(system="s", messages=[{"role": "user", "content": "x"}], tools=[])
    assert "daily" in daily.value.message and daily.value.details["quota"] == "per_day"
    from app.utils.errors import UpstreamError
    provider, _ = _gemini(error=errors.APIError(503, {"error": {"message": "overloaded", "status": "UNAVAILABLE"}}))
    with pytest.raises(UpstreamError) as other:
        await provider.generate(system="s", messages=[{"role": "user", "content": "x"}], tools=[])
    assert "HTTP 503" in other.value.message


# ------------------------------------------------------------------ /chat endpoint
def test_chat_endpoint_returns_ai_text_plus_retrieved_data(settings, make_container):
    provider = ScriptedProvider([call("get_available_observation_periods", ra=127.7, dec=-39.2),
                                 LLMTurn(text="SPHEREx covered this position in two periods.")])
    with TestClient(create_app(settings, make_container(provider))) as client:
        response = client.post("/api/v1/chat", json={"message": "When did SPHEREx observe this?",
                                                    "context": {"ra": 127.7, "dec": -39.2}})
    body = response.json()
    assert response.status_code == 200 and body["success"] is True
    assert body["intent"] == "get_observation_periods" and body["message_source"] == "ai_generated"
    assert len(body["data"]["observation_periods"]) == 2
    assert body["meta"]["tools_called"] == ["get_available_observation_periods"]
    assert body["meta"]["ai_model"] == "scripted-test-model"
    assert "Frontend context" in provider.calls[0]["messages"][-1]["content"]


def test_chat_rate_limit(settings, make_container):
    provider = ScriptedProvider([LLMTurn(text="Hello!")] * 3)
    with TestClient(create_app(settings, make_container(provider, chat_rate_limit_per_minute=2))) as client:
        codes = [client.post("/api/v1/chat", json={"message": "hi"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# ------------------------------------------------------------------ live Gemini (needs a key)
@pytest.mark.live
@pytest.mark.requires_credentials
async def test_live_gemini_connectivity():
    provider = GeminiProvider(os.environ["GEMINI_API_KEY"], os.getenv("GEMINI_MODEL", "gemini-3.8-flash"))
    turn = await provider.generate(system="Reply with the single word: ready",
                                   messages=[{"role": "user", "content": "status?"}], tools=[])
    assert turn.text


@pytest.mark.live
@pytest.mark.requires_credentials
@pytest.mark.parametrize("message,expected", [
    ("Show me the Andromeda Galaxy.", {"resolve_object_coordinates", "search_celestial_object", "search_spherex_observations"}),
    ("Find SPHEREx observations around RA 10.6847 and DEC 41.2687.", {"search_spherex_observations"}),
    ("Find brown dwarfs within 0.5 degrees of RA 56.75 Dec 24.12.", {"search_objects_by_coordinates"}),
    ("Find all available observation periods for M31.", {"get_available_observation_periods"}),
])
async def test_live_gemini_selects_the_right_tool(container, message, expected):
    from app.ai.prompts import build_system_prompt
    provider = GeminiProvider(os.environ["GEMINI_API_KEY"], os.getenv("GEMINI_MODEL", "gemini-3.8-flash"))
    turn = await provider.generate(system=build_system_prompt(), tools=container.registry.declarations(),
                                   messages=[{"role": "user", "content": message}])
    assert turn.tool_calls and turn.tool_calls[0].name in expected
    outcome = await container.registry.execute(turn.tool_calls[0].name, turn.tool_calls[0].args)
    assert outcome["ok"] is True       # the arguments Gemini produced pass validation


# ------------------------------------------------------------------ language, RAG, grounding, new tools
async def test_agent_answers_in_the_detected_language_with_knowledge(container):
    provider = ScriptedProvider([LLMTurn(text="Kahverengi cüce, hidrojen füzyonunu sürdüremeyen bir cisimdir.")])
    agent = QFitAgent(provider, container.registry, knowledge=container.knowledge)
    result = await agent.run("Kahverengi cüce nedir?")
    sent = provider.calls[0]
    assert "RESPONSE LANGUAGE: Turkish" in sent["system"] and "[K1]" in sent["messages"][-1]["content"]
    assert result.language == "tr" and result.parts["language"] == "tr" and result.intent == "conversation"
    assert result.knowledge_hits[0]["chunk_id"] == "brown-dwarfs:tr:1"
    assert result.parts["evidence"][0]["kind"] == "knowledge_base" and result.parts["sources"]
    assert result.parts["data"]["grounding"] == {"checked": True, "unsupported_numbers": []}


async def test_locale_overrides_detection_and_v1_has_no_rag(container):
    provider = ScriptedProvider([LLMTurn(text="Merhaba!"), LLMTurn(text="Hello!")])
    agent = QFitAgent(provider, container.registry, knowledge=container.knowledge)
    result = await agent.run("What is a brown dwarf?", context={"locale": "tr", "expertise_level": "beginner"})
    assert result.language == "tr" and "USER LEVEL: beginner" in provider.calls[0]["system"]
    baseline = QFitAgent(provider, container.registry, knowledge=container.knowledge, instruction_version="v1")
    old = await baseline.run("What is a brown dwarf?")
    assert old.knowledge_hits == [] and "[K1]" not in provider.calls[1]["messages"][-1]["content"]
    assert "RESPONSE LANGUAGE" not in provider.calls[1]["system"]


async def test_unsupported_numbers_become_uncertainty(container):
    provider = ScriptedProvider([call("resolve_object_coordinates", name="M31"),
                                 LLMTurn(text="M 31 is at RA 10.6847, Dec 41.2688 and has a temperature of 5123 K.")])
    result = await QFitAgent(provider, container.registry).run("Where is M31?")
    assert result.unsupported_numbers == ["5123"]
    assert any("5123" in u and "unverified" in u for u in result.parts["uncertainty"])


async def test_knowledge_and_candidate_tools(container):
    found = await container.registry.execute("search_knowledge_base", {"query": "All-Sky Cube channels"})
    assert found["ok"] and found["result"]["hits"][0]["doc_id"] == "spherex-data-products"
    provider = ScriptedProvider([call("submit_candidate_for_review", ra=56.75, dec=24.12,
                                      reason="The user saw the source shift between exposures."),
                                 LLMTurn(text="I recorded it as a candidate for human review; it is not a discovery.")])
    result = await QFitAgent(provider, container.registry).run("Record RA 56.75 Dec 24.12 as a candidate.")
    candidate = result.parts["data"]["candidate"]
    assert result.intent == "submit_candidate" and candidate["status"] == "ai_generated_candidate"
    assert candidate["created_by"] == "qfit-assistant" and container.candidates.list()["total"] == 1


def test_chat_envelope_carries_language_evidence_and_versions(settings, make_container):
    provider = ScriptedProvider([LLMTurn(text="SPHEREx is a NASA infrared survey mission.")])
    with TestClient(create_app(settings, make_container(provider))) as client:
        body = client.post("/chat", json={"message": "What is the SPHEREx All-Sky Cube?"}).json()
    assert body["success"] and body["language"] == "en" and body["evidence"][0]["kind"] == "knowledge_base"
    assert body["meta"]["versions"]["instructions"] == "v2" and body["meta"]["versions"]["knowledge_index"]

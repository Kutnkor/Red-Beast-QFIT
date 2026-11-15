"""REST API: startup, envelope consistency, validation, error handling, security limits."""
from __future__ import annotations

import pytest

ENVELOPE_KEYS = {"success", "assistant", "intent", "message", "message_source", "object", "data",
                 "actions", "sources", "language", "evidence", "uncertainty", "media", "error", "meta"}
VERSION_KEYS = {"instructions", "knowledge_index", "source_registry", "scientific_config"}
DATA_KEYS = {"spherex_available", "observations", "spectral_products", "image_products"}
V1 = "/api/v1"
POS = {"ra": 127.7, "dec": -39.2}


def check_envelope(response, status=200, success=True):
    body = response.json()
    assert response.status_code == status, body
    assert set(body) == ENVELOPE_KEYS and body["assistant"] == "Q-FIT" and body["success"] is success
    assert DATA_KEYS <= set(body["data"]) and body["meta"]["request_id"] == response.headers["X-Request-ID"]
    if success:
        assert set(body["meta"]["versions"]) == VERSION_KEYS
    for action in body["actions"]:
        assert set(action) == {"type", "payload"}
    return body


def test_backend_starts_and_reports_health(client):
    body = check_envelope(client.get(f"{V1}/health"))
    assert body["data"]["status"] == "ok" and body["data"]["ai_configured"] is False
    assert client.get("/").json()["docs"] == "/docs" and client.get("/openapi.json").status_code == 200


def test_capabilities_lists_tools_sources_and_actions(client):
    data = check_envelope(client.get(f"{V1}/capabilities"))["data"]
    assert len(data["tools"]) == 11 and len(data["data_sources"]) == 4
    assert set(data["action_types"]) == {"focus_map", "display_object", "display_observations", "display_spectrum",
                                         "display_image", "show_error", "request_clarification"}
    assert data["spherex"]["nominal_spectral_channels"] == 102


@pytest.mark.parametrize("method,path,payload", [
    ("post", "/objects/search", {"query": "M31"}),
    ("get", "/objects/Andromeda%20Galaxy", None),
    ("post", "/coordinates/resolve", {"name": "M31"}),
    ("post", "/objects/by-coordinates", {"ra": 56.75, "dec": 24.12, "object_type": "brown dwarf"}),
    ("get", "/observations?ra=127.7&dec=-39.2", None),
    ("get", "/observations?object=M31&limit=2", None),
    ("post", "/observations/search", POS),
    ("post", "/observations/periods", POS),
    ("post", "/images/search", POS),
    ("post", "/spectrum/search", POS),
    ("get", "/observations/spherex_dr1_deep:2025W18_1B_0001_1:D1", None),
    ("get", "/spectrum/spherex_dr1_deep:2025W18_1B_0001_1:D1", None),
])
def test_every_endpoint_uses_the_same_envelope(client, method, path, payload):
    response = client.post(f"{V1}{path}", json=payload) if method == "post" else client.get(f"{V1}{path}")
    check_envelope(response)


def test_object_resolution_response_and_actions(client):
    body = check_envelope(client.post(f"{V1}/coordinates/resolve", json={"name": "Andromeda Galaxy"}))
    assert body["intent"] == "resolve_coordinates" and body["object"]["catalog_source"] == "SIMBAD"
    assert body["data"]["spherex_available"] is None          # a catalog match says nothing about SPHEREx
    assert [a["type"] for a in body["actions"]] == ["display_object", "focus_map"]
    assert body["actions"][1]["payload"] == {"ra": body["object"]["ra"], "dec": body["object"]["dec"], "frame": "ICRS"}
    assert body["sources"][0]["name"].startswith("SIMBAD")


def test_ambiguous_and_missing_objects(client):
    ambiguous = check_envelope(client.post(f"{V1}/coordinates/resolve", json={"name": "twins"}))
    assert ambiguous["actions"][0]["type"] == "request_clarification" and len(ambiguous["actions"][0]["payload"]["options"]) == 2
    missing = check_envelope(client.get(f"{V1}/objects/Nosuch%20Thing%2099"))
    assert missing["object"] is None and missing["actions"][0]["type"] == "show_error"
    assert missing["data"]["catalog"]["status"] == "not_found"


def test_coordinate_search_returns_archive_records(client):
    body = check_envelope(client.post(f"{V1}/observations/search", json={**POS, "limit": 4}))
    assert body["data"]["spherex_available"] is True and len(body["data"]["observations"]) == 4
    assert body["data"]["search"]["total"] == 6 and body["data"]["search"]["has_more"] is True
    first = body["data"]["observations"][0]
    assert first["access_url"].startswith("https://irsa.ipac.caltech.edu/ibe/data/spherex/")
    assert first["metadata_source"] == "IRSA SIA2" and "footprint" not in first
    assert body["actions"][-1]["type"] == "display_observations"


def test_object_based_search_resolves_then_queries_archive(client, fake_archive):
    body = check_envelope(client.get(f"{V1}/observations", params={"object": "M31"}))
    assert body["object"]["name"] == "M 31" and body["data"]["search"]["target"]["resolved_from"] == "M31"
    sia = [r for r in fake_archive.requests if r.url.path == "/SIA"][0]
    assert "circle+10.6847080+41.2687500" in str(sia.url) or "circle%2010.6847080%2041.2687500" in str(sia.url)


def test_missing_data_handling(client):
    body = check_envelope(client.post(f"{V1}/observations/search", json={"ra": 10.0, "dec": -85.0}))
    assert body["data"]["spherex_available"] is False and body["data"]["observations"] == []
    assert body["data"]["search"]["status"] == "no_data" and body["data"]["search"]["possible_reasons"]


@pytest.mark.parametrize("payload", [{"ra": 361, "dec": 0}, {"ra": 10, "dec": -91}, {"ra": 10}, {},
                                     {"ra": "abc", "dec": 1}, {"ra": 10, "dec": 10, "radius_deg": 50},
                                     {"ra": 10, "dec": 10, "unknown_field": 1}])
def test_invalid_coordinates_are_rejected(client, payload):
    body = check_envelope(client.post(f"{V1}/observations/search", json=payload), status=422, success=False)
    assert body["error"]["code"] == "invalid_input" and body["actions"][0]["type"] == "show_error"


def test_invalid_query_parameters_are_rejected(client):
    check_envelope(client.get(f"{V1}/observations?ra=400&dec=0"), status=422, success=False)
    check_envelope(client.get(f"{V1}/observations"), status=422, success=False)
    check_envelope(client.get(f"{V1}/observations/not:a:valid:id"), status=422, success=False)


def test_observation_metadata_and_not_found(client):
    body = check_envelope(client.get(f"{V1}/observations/spherex_dr1_deep:2025W18_1B_0001_1:D1"))
    product = body["data"]["observations"][0]
    assert product["obs_id"] == "2025W18_1B_0001_1" and product["t_min_utc"].startswith("2025-04-28")
    missing = check_envelope(client.get(f"{V1}/observations/spherex_qr3:2099W01_1A_0001_1:D1"), status=404, success=False)
    assert missing["error"]["code"] == "not_found"


def test_spectrum_endpoint(client):
    body = check_envelope(client.get(f"{V1}/spectrum/spherex_dr1_deep:2025W18_1B_0001_1:D1"))
    product = body["data"]["spectral_products"][0]
    assert product["nominal_band"]["wavelength_um"] == [0.75, 1.09] and product["spectral_channels"] is None
    assert body["actions"][-1]["type"] == "display_spectrum"
    need_pos = client.get(f"{V1}/spectrum/spherex_dr1_deep:2025W18_1B_0001_1:D1?extract=true")
    check_envelope(need_pos, status=422, success=False)


def test_image_endpoint_actions(client):
    body = check_envelope(client.post(f"{V1}/images/search", json={**POS, "limit": 2, "verify": True}))
    action = body["actions"][-1]
    assert action["type"] == "display_image" and len(action["payload"]["products"]) == 2
    assert action["payload"]["products"][0]["verified"] is True
    assert action["payload"]["products"][0]["cutout_url"].endswith("?center=127.7000000,-39.2000000&size=0.1")


def test_upstream_outage_is_reported_cleanly(client, fake_archive):
    fake_archive.fail_next = [503, 503]
    body = check_envelope(client.post(f"{V1}/observations/search", json={"ra": 33.0, "dec": 3.0}), status=502, success=False)
    assert body["error"] == {"code": "upstream_error", "message": "IRSA SIA2 returned server error 503.",
                             "retryable": True, "details": {}}


def test_chat_without_api_key_falls_back_to_the_knowledge_base(client):
    body = check_envelope(client.post(f"{V1}/chat", json={"message": "Kahverengi cüce nedir?"}))
    assert body["intent"] == "knowledge_fallback" and body["message_source"] == "system"
    assert body["data"]["fallback"]["active"] is True and body["data"]["fallback"]["reason_code"] == "ai_unavailable"
    assert body["language"] == "tr" and "Kaynak:" in body["message"] and body["sources"]
    assert "yapay zekâ yazmadı" in body["uncertainty"][0]
    nothing = check_envelope(client.post(f"{V1}/chat", json={"message": "Show me M31"}))
    assert nothing["intent"] == "assistant_unavailable" and nothing["data"]["fallback"]["active"] is True


def test_chat_without_api_key_and_fallback_off_is_a_clear_error(settings, make_container):
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app(settings, make_container(ai_fallback_enabled=False))) as off:
        body = check_envelope(off.post(f"{V1}/chat", json={"message": "Show me M31"}), status=503, success=False)
    assert body["error"]["code"] == "ai_unavailable"


def test_internal_errors_never_expose_stack_traces(settings, container, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app

    async def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail /home/user/.env")
    monkeypatch.setattr(container.observations, "search_observations", boom)
    with TestClient(create_app(settings, container), raise_server_exceptions=False) as client:
        response = client.post(f"{V1}/observations/search", json=POS)
    body = check_envelope(response, status=500, success=False)
    assert body["error"]["message"] == "An unexpected internal error occurred."
    assert "secret" not in response.text and "Traceback" not in response.text


def test_request_size_limit_and_unknown_routes(client):
    big = client.post(f"{V1}/chat", json={"message": "x" * 5000})
    assert big.status_code == 413 and big.json()["error"]["code"] == "payload_too_large"
    check_envelope(client.get(f"{V1}/nope"), status=404, success=False)


def test_cors_allows_configured_origin_only(client):
    ok = client.get(f"{V1}/health", headers={"Origin": "http://localhost:3000"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3000"
    other = client.get(f"{V1}/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_secrets_are_not_exposed(client, settings):
    from app.config import Settings
    configured = Settings(_env_file=None, gemini_api_key="AIza-super-secret")
    assert "AIza" not in repr(configured) and "AIza" not in configured.model_dump_json()
    assert "api_key" not in client.get(f"{V1}/capabilities").text.lower()


# ------------------------------------------------------------------ knowledge, candidates, aliases
def test_health_reports_knowledge_data_json_and_candidate_log(client):
    data = check_envelope(client.get(f"{V1}/health"))["data"]
    assert data["knowledge_base"]["available"] is True and data["knowledge_base"]["chunks"] == 82
    assert data["scientific_config"]["status"] in ("missing", "loaded", "invalid")
    assert data["candidate_store"] == {"candidates": 0, "log_chain_valid": True}


def test_root_aliases_for_the_web_front_end(client):
    assert check_envelope(client.get("/health"))["intent"] == "health"
    body = check_envelope(client.post("/chat", json={"message": "hi"}))
    assert body["data"]["fallback"]["active"] is True


def test_knowledge_search_and_sources(client):
    body = check_envelope(client.post(f"{V1}/knowledge/search", json={"query": "Kahverengi cüce nedir?"}))
    assert body["intent"] == "knowledge_lookup" and body["language"] == "tr"
    hits = body["data"]["knowledge"]["hits"]
    assert hits[0]["chunk_id"] == "brown-dwarfs:tr:1" and body["sources"]
    assert body["evidence"][0]["kind"] == "knowledge_base" and body["evidence"][0]["chunk_id"] == hits[0]["chunk_id"]
    empty = check_envelope(client.post(f"{V1}/knowledge/search", json={"query": "pizza with mozzarella", "language": "en"}))
    assert empty["data"]["knowledge"]["hits"] == [] and empty["evidence"][0]["kind"] == "missing_information"
    sources = check_envelope(client.get(f"{V1}/knowledge/sources"))["data"]
    assert len(sources["registry"]) == 40 and sources["registry_version"] == "2026.11.14-2"
    check_envelope(client.post(f"{V1}/knowledge/search", json={"query": "x"}), status=422, success=False)


def test_candidate_lifecycle_over_http(client):
    created = check_envelope(client.post(f"{V1}/candidates", json={
        "created_by": "ayse", "target": {"ra": 56.75, "dec": 24.12},
        "reason": "The source shifts between two exposures.", "observation_ids": ["spherex_qr3:2026W21_1A_0491_2:D4"]}))
    candidate = created["data"]["candidate"]
    cid = candidate["candidate_id"]
    assert candidate["status"] == "unreviewed_candidate" and "not a discovery" in created["message"]
    early = client.post(f"{V1}/candidates/{cid}/confirmation", json={
        "recorded_by": "mehmet", "reference_url": "https://doi.org/10.0/x", "reference_title": "A follow-up paper"})
    check_envelope(early, status=422, success=False)
    reviewed = check_envelope(client.post(f"{V1}/candidates/{cid}/reviews", json={
        "reviewer_id": "mehmet", "classification": "real_motion", "self_reported_certainty": "medium"}))
    review_id = reviewed["data"]["candidate"]["reviews"][0]["review_id"]
    assert reviewed["data"]["candidate"]["status"] == "human_reviewed_candidate"
    same = client.post(f"{V1}/candidates/{cid}/reviews/{review_id}/validation",
                       json={"validator_id": "mehmet", "decision": "accepted"})
    check_envelope(same, status=422, success=False)
    check_envelope(client.post(f"{V1}/candidates/{cid}/reviews/{review_id}/validation",
                               json={"validator_id": "zeynep", "decision": "accepted"}))
    confirmed = check_envelope(client.post(f"{V1}/candidates/{cid}/confirmation", json={
        "recorded_by": "mehmet", "reference_url": "https://doi.org/10.0/x", "reference_title": "A follow-up paper"}))
    assert confirmed["data"]["candidate"]["status"] == "scientifically_confirmed"
    listing = check_envelope(client.get(f"{V1}/candidates"))["data"]
    assert listing["candidates"]["total"] == 1 and listing["log_chain_valid"] is True
    audit = check_envelope(client.get(f"{V1}/candidates/{cid}/audit"))["data"]["audit"]
    assert [e["type"] for e in audit["events"]] == ["candidate_created", "review_submitted", "review_validated",
                                                    "candidate_confirmed"]
    check_envelope(client.get(f"{V1}/candidates/cand-0000000000"), status=404, success=False)
    check_envelope(client.get(f"{V1}/candidates/not-an-id"), status=422, success=False)
    check_envelope(client.get(f"{V1}/candidates?status=discovered"), status=422, success=False)

"""Object-name resolution (SIMBAD / Sesame / JPL Horizons) - deterministic unit tests."""
from __future__ import annotations

from urllib.parse import parse_qs

import pytest

from app.astronomy.horizons_client import candidate_commands, looks_like_solar_system
from app.astronomy.object_resolver import normalise_otype
from app.utils.errors import InvalidInputError, UpstreamUnavailableError


async def test_simbad_resolves_common_name(container):
    result = await container.resolver.resolve("Andromeda Galaxy")
    obj = result.object
    assert result.status == "resolved" and obj.name == "M 31" and obj.catalog_source == "SIMBAD"
    assert obj.ra == pytest.approx(10.684708) and obj.dec == pytest.approx(41.26875)
    assert obj.coordinate_frame == "ICRS" and obj.object_type == "G" and obj.object_type_label == "Galaxy"
    assert obj.reference_bibcode == "2006AJ....131.1163S" and "sim-id?Ident=M+31" in obj.source_url
    assert obj.position_time_dependent is False


async def test_ambiguous_names_are_reported_not_guessed(container):
    result = await container.resolver.resolve("twins")
    assert result.status == "ambiguous" and result.object is None
    assert [c["name"] for c in result.candidates] == ["Twin A", "Twin B"]


async def test_partial_name_candidates(container):
    result = await container.resolver.resolve("Pinwheel")
    assert result.status == "ambiguous" and len(result.candidates) == 2


async def test_sesame_fallback_keeps_its_own_source_label(container):
    result = await container.resolver.resolve("Centaurus A")
    assert result.status == "resolved" and result.object.catalog_source == "CDS Sesame"
    assert result.object.object_type is None


async def test_unknown_object_is_not_found(container):
    result = await container.resolver.resolve("Zzyzx Nonexistent 42")
    assert result.status == "not_found" and result.object is None


async def test_catalog_outage_is_a_clean_upstream_error(container):
    with pytest.raises(UpstreamUnavailableError) as info:
        await container.resolver.resolve("simbad down")
    assert "network unreachable" not in info.value.message      # internals stay internal


@pytest.mark.parametrize("name", ["M31'; DROP TABLE basic;--", "", "x" * 101, 'say "hi"'])
async def test_unsafe_names_are_rejected(container, name):
    with pytest.raises(InvalidInputError):
        await container.resolver.resolve(name)


@pytest.mark.parametrize("name,expected", [("Mars", True), ("Comet 3I/ATLAS", True), ("C/2025 N1 (ATLAS)", True),
                                           ("433 Eros", False), ("51 Pegasi", False), ("1P/Halley", True), ("M31", False),
                                           ("Andromeda Galaxy", False), ("NGC 1068", False), ("Vega", False)])
def test_solar_system_detection(name, expected):
    assert looks_like_solar_system(name) is expected


def test_horizons_command_candidates():
    assert candidate_commands("Mars") == ["499"]
    assert candidate_commands("Comet 3I/ATLAS") == ["3I", "DES=3I;CAP;NOFRAG"]
    assert candidate_commands("C/2025 N1 (ATLAS)")[0] == "DES=C/2025 N1;CAP;NOFRAG"
    assert candidate_commands("433 Eros") == ["433;"]


async def test_solar_system_objects_use_horizons(container, fake_archive):
    result = await container.resolver.resolve("Mars", epoch_utc="2026-11-15T00:00:00Z")
    obj = result.object
    query = parse_qs(fake_archive.requests[-1].url.query.decode())
    assert query["COMMAND"] == ["'499'"] and query["TLIST"] == ["'2461359.50000'"]
    assert query["CENTER"] == ["'500@399'"] and query["QUANTITIES"] == ["'1'"]
    assert obj.catalog_source == "JPL Horizons" and obj.name == "Mars (499)"
    assert (obj.ra, obj.dec) == (147.88854, 15.00509)
    assert obj.is_solar_system and obj.position_time_dependent
    assert obj.position_epoch_utc == "2026-11-15T00:00:00Z"


async def test_horizons_ambiguity_and_missing_bodies(container):
    ambiguous = await container.resolver.resolve("1P/Halley")
    assert ambiguous.status == "ambiguous" and len(ambiguous.candidates) == 2
    missing = await container.resolver.resolve("asteroid Nosuchbody")
    assert missing.status == "not_found"


async def test_moving_target_is_not_searched_at_a_fixed_position(container, fake_archive):
    result = await container.observations.search_observations(object_name="Mars")
    assert result["status"] == "moving_target" and result["spherex_available"] is None
    assert result["observations"] == [] and "MOST" in result["message"]
    assert not any(r.url.path == "/SIA" for r in fake_archive.requests)


async def test_cone_search_with_object_type(container):
    result = await container.search.objects_near(56.75, 24.12, 0.5, "brown dwarfs", 10)
    assert container.resolver.last_cone == (56.75, 24.12, 0.5, "BD*", 10)
    assert [o["name"] for o in result["objects"]] == ["Calar 3", "Teide 1"]   # nearest first
    assert result["objects"][0]["separation_deg"] == pytest.approx(0.001, abs=1e-6)
    assert "not evidence that SPHEREx observed" in result["note"]


def test_object_type_normalisation():
    assert normalise_otype("Galaxy") == "G" and normalise_otype("QSO") == "QSO" and normalise_otype(None) is None
    with pytest.raises(InvalidInputError):
        normalise_otype("G' OR 1=1")


async def test_simbad_outage_falls_back_to_sesame(container, monkeypatch):
    monkeypatch.setattr(container.resolver, "_sesame", lambda name: (10.6847083, 41.26875))
    result = await container.resolver.resolve("simbad down")
    assert result.status == "resolved" and result.object.catalog_source == "CDS Sesame"
    assert result.object.ra == pytest.approx(10.6847083) and "SIMBAD was unreachable" in result.message
    assert any("SIMBAD could not be reached" in n for n in result.object.notes)

    def sesame_down(name):
        raise ConnectionError("also down")
    monkeypatch.setattr(container.resolver, "_sesame", sesame_down)
    with pytest.raises(UpstreamUnavailableError) as info:       # different cache key: deep_sky
        await container.resolver.resolve("simbad down", "deep_sky")
    assert "SIMBAD" in info.value.message                    # the real cause, not "not found"


async def test_simbad_circuit_breaker_skips_a_failing_simbad(container, monkeypatch):
    resolver = container.resolver
    monkeypatch.setattr(resolver, "_sesame", lambda name: (88.79, 7.41))
    calls = []
    original = resolver._simbad_by_name

    def counting(name):
        calls.append(name)
        return original(name)
    monkeypatch.setattr(resolver, "_simbad_by_name", counting)
    first = await resolver.resolve("simbad down")             # SIMBAD fails -> Sesame, breaker opens
    second = await resolver.resolve("Betelgeuse")             # SIMBAD skipped entirely
    assert first.object.catalog_source == second.object.catalog_source == "CDS Sesame"
    assert calls == ["simbad down"]
    resolver._simbad_down_until = 0.0                         # pause over: SIMBAD is tried again
    assert (await resolver.resolve("M31")).object.catalog_source == "SIMBAD" and calls[-1] == "M31"


def test_prompt_forbids_placeholder_coordinates():
    from app.ai.prompts import SYSTEM_PROMPT
    assert "placeholder" in SYSTEM_PROMPT and "(such as 0, 0)" in SYSTEM_PROMPT

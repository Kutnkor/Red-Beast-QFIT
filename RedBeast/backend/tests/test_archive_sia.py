"""SIA fallback contract with synthetic HTTP responses; no live data invented."""
import hashlib
import io

import httpx
import pytest
from astropy.table import Table

from blinkspace.archive import ArchiveError, SIA_COLLECTIONS, parse_sia_row, query_observations, query_sia_observations


def sia_row(collection="spherex_dr1"):
    release = "dr1" if "dr1" in collection else "qr3"
    return {"access_url": f"https://irsa.ipac.caltech.edu/ibe/data/spherex/{release}/level2/2026W01_1A/l2b-v27-2026-228/2/level2_2026W01_1A_0001_1D2_spx_l2b-v27-2026-228.fits",
            "obs_publisher_did": f"ivo://irsa.ipac/{collection}?2026W01_1A_0001_1/D2",
            "s_region": "POLYGON ICRS 10 20 11 20 11 21 10 21 10 20", "t_min": 61000.0, "t_max": 61000.001,
            "t_exptime": 100.0}


def xml_for(collection):
    table = Table(rows=[sia_row(collection)])
    stream = io.BytesIO()
    table.write(stream, format="votable")
    return stream.getvalue()


def test_sia_same_level2_identity_and_unknown_metadata_not_fabricated():
    obs = parse_sia_row(sia_row())
    assert obs.obs_id == "2026W01_1A_0001_1" and obs.detector == 2
    assert obs.footprint == ((10, 20), (11, 20), (11, 21), (10, 21))
    assert obs.checksum == "" and obs.pipeline_version == "" and obs.content_length == 0
    assert parse_sia_row(dict(sia_row(), access_url="https://example.org/fake.fits")) is None
    assert parse_sia_row(dict(sia_row(), s_region="POLYGON ICRS nan 20 11 20 11 21 10 21")) is None


def test_sia_all_four_collections_schema_and_response_checksums():
    calls = []
    def handler(request):
        collection = request.url.params["COLLECTION"]
        calls.append(collection)
        assert request.method == "GET" and request.url.params["POS"].startswith("CIRCLE 10.0000000 20.0000000")
        return httpx.Response(200, content=xml_for(collection))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        observations, meta = query_sia_observations(10, 20, client=client, sleep=lambda _: None)
    assert set(calls) == set(SIA_COLLECTIONS) and len(observations) == 4
    assert meta["service"] == "IRSA SIA2" and meta["adql"] is None
    for source in meta["sia_requests"]:
        assert source["response_sha256"] == hashlib.sha256(xml_for(source["collection"])).hexdigest()


def test_sia_partial_collection_failure_does_not_report_complete_coverage():
    def handler(request):
        collection = request.url.params["COLLECTION"]
        return httpx.Response(502) if collection.endswith("_deep") else httpx.Response(200, content=xml_for(collection))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ArchiveError, match="failed"):
            query_sia_observations(10, 20, max_retries=1, client=client, sleep=lambda _: None)


def test_official_irsa_tap_failure_uses_live_sia(monkeypatch):
    monkeypatch.setenv("BLINKSPACE_ARCHIVE_PROTOCOL", "auto")
    def handler(request):
        if request.method == "POST":
            return httpx.Response(502)
        return httpx.Response(200, content=xml_for(request.url.params["COLLECTION"]))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        observations, meta = query_observations(10, 20, "https://irsa.ipac.caltech.edu/TAP", max_retries=1, client=client, sleep=lambda _: None)
    assert len(observations) == 4 and "TAP 502" in meta["tap_fallback_reason"]


def test_auto_discovery_bounds_tap_probe_before_sia(monkeypatch):
    from blinkspace import archive
    monkeypatch.setenv('BLINKSPACE_ARCHIVE_PROTOCOL', 'auto')
    attempts = []
    def tap(url, adql, timeout, retries, client, sleep):
        attempts.append((timeout, retries))
        raise ArchiveError('TAP timeout')
    monkeypatch.setattr(archive, 'tap_sync_csv', tap)
    monkeypatch.setattr(archive, 'query_sia_observations', lambda *args: ([], {'service': 'IRSA SIA2'}))
    _, meta = query_observations(10, 20, 'https://irsa.ipac.caltech.edu/TAP', 240, 3)
    assert attempts == [(20, 1)]
    assert meta['service'] == 'IRSA SIA2' and meta['tap_fallback_reason'] == 'TAP timeout'
    monkeypatch.setenv('BLINKSPACE_ARCHIVE_PROTOCOL', 'tap')
    with pytest.raises(ArchiveError):
        query_observations(10, 20, 'https://irsa.ipac.caltech.edu/TAP', 240, 3)
    assert attempts[-1] == (240, 3)


def test_sia_query_is_abandoned_at_once_when_its_caller_cancels():
    """While it waits for a busy archive the query must hear a cancel (it used to sit out the whole back-off)."""
    import time
    from blinkspace.archive import interruptible

    class Stop(Exception):
        pass

    polls = {"n": 0}

    def checkpoint():
        polls["n"] += 1
        if polls["n"] >= 2:
            raise Stop()

    started = time.monotonic()
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(502))) as client:
        with interruptible(checkpoint), pytest.raises(Stop):
            query_sia_observations(10, 20, client=client)      # real sleep: the first back-off alone is 3 s
    assert time.monotonic() - started < 1.5


def test_sia_query_reports_that_it_waits_and_gives_up_within_its_budget(monkeypatch):
    import time
    from blinkspace import archive as archive_module

    monkeypatch.setattr(archive_module, "SIA_BUDGET_S", 0.6)
    seen = []
    started = time.monotonic()
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503))) as client:
        with archive_module.interruptible(None, seen.append), pytest.raises(ArchiveError):
            query_sia_observations(10, 20, client=client)
    assert time.monotonic() - started < 4
    assert seen and seen[0]["status"] == 503 and seen[0]["attempt"] == 2 and seen[0]["collection"] in SIA_COLLECTIONS

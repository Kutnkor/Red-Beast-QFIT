"""Mirror schema and provenance checks with explicitly synthetic HTTP fixtures."""
import hashlib

import httpx
import pytest

from blinkspace.archive import ArchiveError
from blinkspace.catalogs import ALLWISE_VIZIER_COLUMNS, GAIA_VIZIER_COLUMNS, query_allwise, query_gaia


def tsv():
    return "\n".join([
        *(f"#Column\t{column}\t(test)" for column in ALLWISE_VIZIER_COLUMNS),
        "\t".join(ALLWISE_VIZIER_COLUMNS), " \tdeg\tdeg\tmag\tmag\t \t ",
        "---\t---\t---\t---\t---\t---\t---",
        "synthetic-source\t10.0\t20.0\t12.1\t\t9.5\t-1.0",
    ])


def test_vizier_allwise_has_original_units_nulls_and_query_provenance(monkeypatch):
    monkeypatch.setenv("BLINKSPACE_ALLWISE_PROVIDER", "vizier")
    body = tsv()
    def handler(request):
        assert request.url.params["-source"] == "II/328/allwise"
        assert float(request.url.params["-c.rm"]) == 3
        return httpx.Response(200, text=body)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows = query_allwise("unused", 10, 20, 0.05, client=client)
    assert len(rows) == 1 and rows[0]["w1"] == 12.1 and rows[0]["w2"] is None
    assert rows[0]["w2snr"] == -1 and rows[0]["epoch_jyear"] == 2010.56
    assert rows[0]["provenance"]["response_sha256"] == hashlib.sha256(body.encode()).hexdigest()
    assert "II%2F328%2Fallwise" in rows[0]["provenance"]["query_url"]


@pytest.mark.parametrize("body", ["<html>error</html>", tsv().replace("#Column\tsnr1", "#Column\tunknown"), tsv() + "\n#INFO QUERY_STATUS=OVERFLOW"])
def test_vizier_rejects_error_changed_schema_or_overflow(monkeypatch, body):
    monkeypatch.setenv("BLINKSPACE_ALLWISE_PROVIDER", "vizier")
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body))) as client:
        with pytest.raises(ArchiveError):
            query_allwise("unused", 10, 20, 0.05, client=client)


def gaia_tsv():
    return "\n".join([
        *(f"#Column\t{column}\t(test)" for column in GAIA_VIZIER_COLUMNS),
        "\t".join(GAIA_VIZIER_COLUMNS), " \tdeg\tdeg\tmas/yr\tmas/yr\tmas\tmag\tmag",
        "---\t---\t---\t---\t---\t---\t---\t---",
        "4472832130942575872\t269.44850252544\t4.73942005111\t-801.551\t10362.394\t546.9759\t8.193974\t6.698",
        "1234\t269.45\t4.74\t\t\t\t17.5\t",
    ])


def test_vizier_gaia_keeps_dr3_ids_j2016_epoch_nulls_and_provenance(monkeypatch):
    monkeypatch.setenv("BLINKSPACE_GAIA_PROVIDER", "vizier")
    body = gaia_tsv()

    def handler(request):
        assert request.url.params["-source"] == "I/355/gaiadr3"
        assert request.url.params["Gmag"] == "<18.00" and float(request.url.params["-c.rm"]) == 3
        return httpx.Response(200, text=body)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows = query_gaia("unused", 269.45, 4.74, 0.05, client=client)
    assert [r["id"] for r in rows] == ["4472832130942575872", "1234"]
    assert rows[0]["pmdec"] == 10362.394 and rows[0]["g"] == 8.193974 and rows[0]["epoch_jyear"] == 2016.0
    assert rows[1]["pmra"] is None and rows[1]["parallax"] is None and rows[1]["rp"] is None
    assert rows[0]["provenance"]["catalogue_id"] == "I/355/gaiadr3"
    assert rows[0]["provenance"]["response_sha256"] == hashlib.sha256(body.encode()).hexdigest()


def test_vizier_gaia_rejects_a_changed_schema(monkeypatch):
    monkeypatch.setenv("BLINKSPACE_GAIA_PROVIDER", "vizier")
    body = gaia_tsv().replace("#Column\tPlx", "#Column\tparallax")
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body))) as client:
        with pytest.raises(ArchiveError):
            query_gaia("unused", 269.45, 4.74, 0.05, client=client)

"""Dış kataloglar (IRSA TAP): Gaia DR3 ve AllWISE.

Bunlar **katalog** katmanlarıdır, görüntü değildir. Dönemleri ve çözünürlükleri SPHEREx'ten farklıdır:
- Gaia DR3: konum dönemi J2016.0, optik (G bandı); özdevinimle kare dönemine ilerletilebilir.
- AllWISE: ortalama dönem ≈ 2010.5, 3.4/4.6 µm, ~6″ çözünürlük; özdevinim ilerletmesi yapılmaz.
"""
from __future__ import annotations

import math
import os
import csv
import hashlib
import io
from datetime import datetime, timezone

import httpx

from .archive import ArchiveError, tap_sync_csv

GAIA_REF_EPOCH = 2016.0
ALLWISE_MEAN_EPOCH = 2010.56
ALLWISE_VIZIER_URL = "https://vizier.cfa.harvard.edu/viz-bin/asu-tsv"
ALLWISE_VIZIER_COLUMNS = ("AllWISE", "RAJ2000", "DEJ2000", "W1mag", "W2mag", "snr1", "snr2")
GAIA_VIZIER_COLUMNS = ("Source", "RA_ICRS", "DE_ICRS", "pmRA", "pmDE", "Plx", "Gmag", "RPmag")

GAIA_ADQL = (
    "SELECT source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag, phot_rp_mean_mag "
    "FROM gaia_dr3_source WHERE CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra:.6f}, {dec:.6f}, {r:.5f})) = 1 "
    "AND phot_g_mean_mag < {gmax:.2f}"
)
ALLWISE_ADQL = (
    "SELECT designation, ra, dec, w1mpro, w2mpro, w1snr, w2snr "
    "FROM allwise_p3as_psd WHERE CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra:.6f}, {dec:.6f}, {r:.5f})) = 1"
)


def _f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _gaia_vizier(ra: float, dec: float, radius_deg: float, gmax: float, timeout_s: float, client=None) -> tuple[list[dict], dict]:
    """Gaia DR3 (I/355/gaiadr3) from the official VizieR Harvard mirror: same catalogue, same J2016.0 positions.

    Like the AllWISE mirror this is selected by the operator (BLINKSPACE_GAIA_PROVIDER=vizier), never substituted
    silently for a failed query, and the published column metadata is checked before any number is read.
    """
    params = {"-source": "I/355/gaiadr3", "-c": f"{ra:.7f} {dec:.7f}", "-c.rm": f"{radius_deg * 60:.7f}",
              "-out": ",".join(GAIA_VIZIER_COLUMNS), "Gmag": f"<{gmax:.2f}", "-out.max": "50000"}
    own = client is None
    client = client or httpx.Client(timeout=timeout_s, follow_redirects=True)
    try:
        response = client.get(ALLWISE_VIZIER_URL, params=params, timeout=timeout_s)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ArchiveError(f"Gaia VizieR query failed: {exc}") from exc
    finally:
        if own:
            client.close()
    lines = response.text.splitlines()
    declared = {line.split("\t")[1] for line in lines if line.startswith("#Column\t")}
    if not set(GAIA_VIZIER_COLUMNS).issubset(declared) or any("OVERFLOW" in line or line.startswith("#ERROR") for line in lines):
        raise ArchiveError("Gaia VizieR response is incomplete or its schema changed")
    table = [line for line in lines if line and not line.startswith("#")]
    if len(table) < 3 or tuple(table[0].split("\t")) != GAIA_VIZIER_COLUMNS:
        raise ArchiveError("Gaia VizieR TSV header is missing or changed")
    parsed = list(csv.DictReader(io.StringIO("\n".join([table[0], *table[3:]])), delimiter="\t"))
    if len(parsed) >= 50000 or any(None in row for row in parsed):
        raise ArchiveError("Gaia VizieR response is truncated or malformed")
    rows = [{"source_id": row["Source"].strip(), "ra": row["RA_ICRS"], "dec": row["DE_ICRS"], "pmra": row["pmRA"], "pmdec": row["pmDE"],
             "parallax": row["Plx"], "phot_g_mean_mag": row["Gmag"], "phot_rp_mean_mag": row["RPmag"]} for row in parsed]
    provenance = {"provider": "VizieR Harvard mirror", "catalogue_id": "I/355/gaiadr3",
                  "citation": "doi:10.26093/cds/vizier.1355", "query_url": str(response.url),
                  "response_sha256": hashlib.sha256(response.content).hexdigest(),
                  "response_bytes": len(response.content), "retrieved_utc": datetime.now(timezone.utc).isoformat()}
    return rows, provenance


def query_gaia(tap_url: str, ra: float, dec: float, radius_deg: float, gmax: float = 18.0, timeout_s: float = 120.0, client=None) -> list[dict]:
    provider = os.environ.get("BLINKSPACE_GAIA_PROVIDER", "irsa")
    if provider not in ("irsa", "esa", "vizier"):
        raise ValueError("BLINKSPACE_GAIA_PROVIDER must be irsa, esa or vizier")
    provenance = None
    if provider == "vizier":
        rows, provenance = _gaia_vizier(ra, dec, radius_deg, gmax, timeout_s, client)
        tap_url = ALLWISE_VIZIER_URL
    else:
        query = GAIA_ADQL.format(ra=ra, dec=dec, r=radius_deg, gmax=gmax)
        if provider == "esa":
            tap_url = "https://gea.esac.esa.int/tap-server/tap"
            query = query.replace("FROM gaia_dr3_source", "FROM gaiadr3.gaia_source")
        rows, _ = tap_sync_csv(tap_url, query, timeout_s, 2, client)
    out = []
    for r in rows:
        if _f(r.get("ra")) is None or _f(r.get("dec")) is None:
            continue
        out.append({
            "id": str(r["source_id"]),
            "ra": _f(r["ra"]), "dec": _f(r["dec"]),
            "pmra": _f(r.get("pmra")), "pmdec": _f(r.get("pmdec")),
            "parallax": _f(r.get("parallax")),
            "g": _f(r.get("phot_g_mean_mag")), "rp": _f(r.get("phot_rp_mean_mag")),
            "source_url": tap_url, "catalogue": "Gaia DR3", "epoch_jyear": GAIA_REF_EPOCH,
            **({"provenance": provenance} if provenance else {}),
        })
    return out


def _allwise_vizier(ra: float, dec: float, radius_deg: float, timeout_s: float, client=None) -> tuple[list[dict], dict]:
    """Explicit official VizieR mirror, preserving the AllWISE catalogue and epoch.

    This path is selected by the operator, not silently substituted for a failed query.
    Validate the published column metadata before interpreting any numeric data.
    """
    params = {"-source": "II/328/allwise", "-c": f"{ra:.7f} {dec:.7f}",
              "-c.rm": f"{radius_deg * 60:.7f}", "-out": ",".join(ALLWISE_VIZIER_COLUMNS),
              "-out.max": "50000"}
    own = client is None
    client = client or httpx.Client(timeout=timeout_s, follow_redirects=True)
    try:
        response = client.get(ALLWISE_VIZIER_URL, params=params, timeout=timeout_s)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ArchiveError(f"AllWISE VizieR query failed: {exc}") from exc
    finally:
        if own:
            client.close()
    lines = response.text.splitlines()
    declared = {line.split("\t")[1] for line in lines if line.startswith("#Column\t")}
    if not set(ALLWISE_VIZIER_COLUMNS).issubset(declared) or any("OVERFLOW" in line or line.startswith("#ERROR") for line in lines):
        raise ArchiveError("AllWISE VizieR response is incomplete or its schema changed")
    table = [line for line in lines if line and not line.startswith("#")]
    if len(table) < 3 or tuple(table[0].split("\t")) != ALLWISE_VIZIER_COLUMNS:
        raise ArchiveError("AllWISE VizieR TSV header is missing or changed")
    parsed = list(csv.DictReader(io.StringIO("\n".join([table[0], *table[3:]])), delimiter="\t"))
    if len(parsed) >= 50000 or any(None in row for row in parsed):
        raise ArchiveError("AllWISE VizieR response is truncated or malformed")
    rows = [{"designation": row["AllWISE"], "ra": row["RAJ2000"], "dec": row["DEJ2000"],
             "w1mpro": row["W1mag"], "w2mpro": row["W2mag"], "w1snr": row["snr1"], "w2snr": row["snr2"]} for row in parsed]
    provenance = {"provider": "VizieR Harvard mirror", "catalogue_id": "II/328/allwise",
                  "bibcode": "2014yCat.2328....0C", "query_url": str(response.url),
                  "response_sha256": hashlib.sha256(response.content).hexdigest(),
                  "response_bytes": len(response.content), "retrieved_utc": datetime.now(timezone.utc).isoformat()}
    return rows, provenance


def query_allwise(tap_url: str, ra: float, dec: float, radius_deg: float, timeout_s: float = 120.0, client=None) -> list[dict]:
    provider = os.environ.get("BLINKSPACE_ALLWISE_PROVIDER", "irsa")
    if provider == "vizier":
        rows, provenance = _allwise_vizier(ra, dec, radius_deg, timeout_s, client)
        source_url = ALLWISE_VIZIER_URL
    elif provider == "irsa":
        rows, provenance = tap_sync_csv(tap_url, ALLWISE_ADQL.format(ra=ra, dec=dec, r=radius_deg), timeout_s, 2, client)
        source_url = tap_url
    else:
        raise ValueError("BLINKSPACE_ALLWISE_PROVIDER must be irsa or vizier")
    out = []
    for r in rows:
        if _f(r.get("ra")) is None or _f(r.get("dec")) is None:
            continue
        out.append({
            "id": str(r.get("designation", "")).strip(),
            "ra": _f(r["ra"]), "dec": _f(r["dec"]),
            "w1": _f(r.get("w1mpro")), "w2": _f(r.get("w2mpro")),
            "w1snr": _f(r.get("w1snr")), "w2snr": _f(r.get("w2snr")),
            "source_url": source_url, "catalogue": "AllWISE", "epoch_jyear": ALLWISE_MEAN_EPOCH,
            "provenance": provenance,
        })
    return out


def propagate(ra: float, dec: float, pmra_masyr: float | None, pmdec_masyr: float | None, from_epoch: float, to_epoch: float) -> tuple[float, float]:
    """Yalnızca özdevinimle doğrusal konum ilerletme (pmra = μα·cosδ, mas/yıl).

    Paralaks, ışık-zamanı ve gözlemci (uzay aracı) konumu **dahil değildir**; bu bir tam görünür konum hesabı
    değildir. SPHEREx pikseli (6.15″) yanında, 0.55″'lik en büyük paralaks (Barnard) < 0.1 pikseldir.
    """
    if pmra_masyr is None or pmdec_masyr is None:
        return ra, dec
    dt = to_epoch - from_epoch
    ddec = pmdec_masyr * dt / 3.6e6
    dra = pmra_masyr * dt / 3.6e6 / max(math.cos(math.radians(dec)), 1e-6)
    return (ra + dra) % 360.0, max(-90.0, min(90.0, dec + ddec))


def mjd_to_jyear(mjd: float) -> float:
    """MJD -> Jülyen yılı (J2000.0 = MJD 51544.5)."""
    return 2000.0 + (mjd - 51544.5) / 365.25

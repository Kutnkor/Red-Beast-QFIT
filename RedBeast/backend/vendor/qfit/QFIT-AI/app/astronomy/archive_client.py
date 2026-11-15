"""Generic client for NASA/IPAC IRSA virtual-observatory services.

Implements the two IRSA interfaces Q-FIT relies on:
  * SIA 2.0   GET {base}/SIA?COLLECTION=...&POS=circle ra dec r&RESPONSEFORMAT=CSV
  * TAP sync  GET {base}/TAP/sync?QUERY=<ADQL>&FORMAT=csv
plus retry/back-off, time-outs and a TTL cache for metadata responses.
"""
from __future__ import annotations

import asyncio
import csv
import io
import re
from typing import Any, Sequence

import httpx

from app.utils.cache import TTLCache
from app.utils.errors import UpstreamError, UpstreamUnavailableError
from app.utils.logging import get_logger

log = get_logger("archive")
_RETRY_STATUS = {429, 502, 503, 504}
USER_AGENT = "Q-FIT/0.1 (NASA Space Apps; astronomy data assistant)"


def parse_csv_table(text: str, service: str) -> list[dict[str, str | None]]:
    """Parse a CSV table; empty cells become None. Detects VO error documents."""
    stripped = text.lstrip()
    if not stripped:
        return []
    if stripped.startswith("<"):
        match = re.search(r'name="QUERY_STATUS"\s+value="ERROR"[^>]*>(.*?)</INFO>', stripped, re.S)
        detail = " ".join(match.group(1).split())[:300] if match else "unexpected non-CSV response"
        raise UpstreamError(f"{service} rejected the query: {detail}")
    rows = []
    for row in csv.DictReader(io.StringIO(stripped)):
        rows.append({k.strip(): (v.strip() if v and v.strip() else None)
                     for k, v in row.items() if k is not None})
    return rows


class ArchiveClient:
    def __init__(self, base_url: str, *, timeout: float = 45, max_retries: int = 2,
                 cache_ttl: float = 600, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.cache = TTLCache(cache_ttl)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 15)),
            follow_redirects=True, transport=transport,
            headers={"User-Agent": USER_AGENT},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---------------------------------------------------------------- HTTP
    async def request(self, method: str, url: str, *, params: Any = None,
                      headers: dict[str, str] | None = None, service: str = "IRSA") -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._client.request(method, url, params=params, headers=headers)
            except httpx.TimeoutException as exc:
                # Not retried: a service that just took the whole timeout will not be faster half a
                # second later, and three tries made a chat answer wait 140 s (seen live 2026-11-14).
                log.warning("upstream timeout", extra={"service": service, "timeout_s": self._client.timeout.read})
                raise UpstreamUnavailableError(f"{service} did not respond in time.") from exc
            except httpx.HTTPError as exc:
                last = UpstreamUnavailableError(f"{service} could not be reached ({type(exc).__name__}).")
                last.__cause__ = exc
            else:
                if resp.status_code in _RETRY_STATUS and attempt < self.max_retries:
                    delay = self._retry_delay(resp, attempt)
                    log.warning("retrying upstream", extra={"service": service,
                                "status": resp.status_code, "delay_s": delay})
                    await asyncio.sleep(delay)
                    continue
                if resp.status_code == 429:
                    raise UpstreamError(f"{service} is rate-limiting requests; try again shortly.")
                if resp.status_code >= 500:
                    raise UpstreamError(f"{service} returned server error {resp.status_code}.")
                return resp
            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * 2 ** attempt)
        assert last is not None
        raise last

    @staticmethod
    def _retry_delay(resp: httpx.Response, attempt: int) -> float:
        try:
            return min(float(resp.headers.get("Retry-After", "")), 10.0)
        except ValueError:
            return 0.5 * 2 ** attempt

    # ----------------------------------------------------------------- SIA2
    async def sia_search(self, *, collections: Sequence[str], ra: float, dec: float,
                         radius_deg: float, maxrec: int,
                         band_m: tuple[float, float] | None = None,
                         time_mjd: tuple[float, float] | None = None) -> list[dict[str, str | None]]:
        params: list[tuple[str, str]] = [("COLLECTION", c) for c in collections]
        params.append(("POS", f"circle {ra:.7f} {dec:.7f} {radius_deg:.7f}"))
        if band_m:
            params.append(("BAND", f"{band_m[0]:.6e} {band_m[1]:.6e}"))
        if time_mjd:
            params.append(("TIME", f"{time_mjd[0]:.6f} {time_mjd[1]:.6f}"))
        params += [("RESPONSEFORMAT", "CSV"), ("MAXREC", str(maxrec))]
        key = ("sia", tuple(params))
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        resp = await self.request("GET", f"{self.base_url}/SIA", params=params, service="IRSA SIA2")
        if resp.status_code >= 400:
            raise UpstreamError(f"IRSA SIA2 rejected the query (HTTP {resp.status_code}).")
        rows = parse_csv_table(resp.text, "IRSA SIA2")
        self.cache.set(key, rows)
        return rows

    # ------------------------------------------------------------------ TAP
    async def tap_query(self, adql: str) -> list[dict[str, str | None]]:
        key = ("tap", adql)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        resp = await self.request("GET", f"{self.base_url}/TAP/sync",
                                  params={"QUERY": adql, "FORMAT": "csv"}, service="IRSA TAP")
        if resp.status_code >= 400:
            # TAP reports ADQL problems as a VOTable error document with HTTP 400.
            parse_csv_table(resp.text if resp.text.lstrip().startswith("<") else "", "IRSA TAP")
            raise UpstreamError(f"IRSA TAP rejected the query (HTTP {resp.status_code}).")
        rows = parse_csv_table(resp.text, "IRSA TAP")
        self.cache.set(key, rows)
        return rows

    # ------------------------------------------------------------ downloads
    async def probe_url(self, url: str) -> dict[str, Any]:
        """Check that a data URL really answers, without downloading the file."""
        try:
            resp = await self.request("HEAD", url, service="IRSA data server")
            if resp.status_code in (403, 405, 501):
                resp = await self.request("GET", url, headers={"Range": "bytes=0-0"},
                                          service="IRSA data server")
        except UpstreamError as exc:
            return {"verified": False, "http_status": None, "detail": exc.message}
        size = resp.headers.get("Content-Length")
        return {"verified": resp.status_code in (200, 206), "http_status": resp.status_code,
                "content_length": int(size) if size and size.isdigit() and resp.status_code == 200 else None}

    async def download_bytes(self, url: str, max_bytes: int, *, timeout: float = 90.0) -> bytes:
        """Download a small product (e.g. a cutout), refusing anything oversized.

        IRSA's cutout service is slow (tens of seconds per cutout, measured 2026-11-14) and
        answers 503 with Retry-After when busy, so this has its own timeout and honours
        Retry-After before retrying."""
        for attempt in range(self.max_retries + 1):
            try:
                async with self._client.stream("GET", url, timeout=timeout) as resp:
                    if resp.status_code in _RETRY_STATUS and attempt < self.max_retries:
                        delay = self._retry_delay(resp, attempt)
                        log.warning("retrying cutout", extra={"status": resp.status_code, "delay_s": delay})
                        await asyncio.sleep(delay)
                        continue
                    if resp.status_code != 200:
                        raise UpstreamError(f"IRSA data server answered HTTP {resp.status_code} for a cutout request.")
                    chunks, total = [], 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise UpstreamError("Cutout is larger than the configured download limit.")
                        chunks.append(chunk)
                    return b"".join(chunks)
            except httpx.TimeoutException as exc:
                raise UpstreamUnavailableError("IRSA data server did not deliver the cutout in time.") from exc
            except httpx.HTTPError as exc:
                raise UpstreamUnavailableError(f"IRSA data server could not be reached ({type(exc).__name__}).") from exc
        raise UpstreamError("IRSA data server stayed busy for this cutout request.")

"""Cutout downloads: IRSA's cutout service answers 503 + Retry-After when busy (seen live on
2026-11-14); the download must wait and retry instead of failing the sample."""
from __future__ import annotations

import httpx
import pytest

from app.astronomy.archive_client import ArchiveClient
from app.utils.errors import UpstreamError

URL = "https://irsa.ipac.caltech.edu/ibe/data/spherex/x.fits?center=1,2&size=0.01"


def client(responses, retries=2):
    calls = []

    def handler(request):
        calls.append(request)
        return responses.pop(0)
    archive = ArchiveClient("https://irsa.ipac.caltech.edu", timeout=5, max_retries=retries, cache_ttl=0,
                            transport=httpx.MockTransport(handler))
    return archive, calls


async def test_cutout_download_retries_when_irsa_is_busy(monkeypatch):
    slept = []

    async def no_sleep(seconds):
        slept.append(seconds)
    monkeypatch.setattr("app.astronomy.archive_client.asyncio.sleep", no_sleep)
    archive, calls = client([httpx.Response(503, headers={"Retry-After": "5"}, text="busy"),
                             httpx.Response(200, content=b"FITSDATA")])
    assert await archive.download_bytes(URL, 1000) == b"FITSDATA"
    assert len(calls) == 2 and slept == [5.0]
    await archive.aclose()


async def test_cutout_download_gives_up_after_the_retries(monkeypatch):
    async def no_sleep(seconds):
        return None
    monkeypatch.setattr("app.astronomy.archive_client.asyncio.sleep", no_sleep)
    archive, calls = client([httpx.Response(503, text="busy")] * 3)
    with pytest.raises(UpstreamError, match="HTTP 503"):
        await archive.download_bytes(URL, 1000)
    assert len(calls) == 3
    await archive.aclose()


async def test_cutout_size_limit_still_applies():
    archive, _ = client([httpx.Response(200, content=b"x" * 50)])
    with pytest.raises(UpstreamError, match="larger than"):
        await archive.download_bytes(URL, 10)
    await archive.aclose()

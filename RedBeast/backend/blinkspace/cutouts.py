"""IBE cutout indirme ve ham dosya deposu.

Ham dosyalar indirildiği gibi, içerik özetiyle (SHA-256) adlandırılarak saklanır ve bir daha değiştirilmez.
İndirme yalnızca izinli kaynakla (IRSA IBE SPHEREx ağacı) sınırlıdır.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import httpx

from .config import ALLOWED_DATA_HOST, ALLOWED_DATA_PREFIX

MAX_CUTOUT_BYTES = 60 * 1024 * 1024
_URI_OK = re.compile(r"^ibe/data/spherex/[A-Za-z0-9_./\-]+\.fits$")


class CutoutError(RuntimeError):
    pass


def cutout_url(irsa_base: str, uri: str, ra_deg: float, dec_deg: float, size_deg: float) -> str:
    """`<base><uri>?center=<ra>,<dec>&size=<deg>` adresini kurar ve izin denetimini uygular."""
    if not _URI_OK.match(uri) or ".." in uri:
        raise CutoutError(f"İzin verilmeyen arşiv yolu: {uri!r}")
    if not (0 < size_deg <= 2.0):
        raise CutoutError("Cutout boyutu 0–2 derece aralığında olmalı")
    url = f"{irsa_base.rstrip('/')}/{uri}?center={ra_deg % 360.0:.6f},{dec_deg:.6f}&size={size_deg:.5f}"
    validate_url(url)
    return url


def validate_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != ALLOWED_DATA_HOST or not parts.path.startswith(ALLOWED_DATA_PREFIX):
        raise CutoutError(f"İzin verilmeyen indirme adresi: {url}")
    if parts.username or parts.password or (parts.port not in (None, 443)):
        raise CutoutError(f"İzin verilmeyen indirme adresi: {url}")


@dataclass(frozen=True)
class RawFile:
    url: str
    sha256: str
    size: int
    path: Path
    cached: bool
    elapsed_s: float


def fetch_bytes(
    url: str,
    client: httpx.Client,
    timeout_s: float,
    max_retries: int,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """Sınırlı yeniden denemeyle indirir; FITS imzasını ve boyut sınırını denetler."""
    validate_url(url)
    last: Exception | None = None
    for attempt in range(max(1, max_retries)):
        try:
            resp = client.get(url, timeout=timeout_s)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise CutoutError(f"HTTP {resp.status_code}")
            if resp.status_code != 200:
                raise CutoutError(f"kalıcı: HTTP {resp.status_code}")
            body = resp.content
            if len(body) > MAX_CUTOUT_BYTES:
                raise CutoutError("kalıcı: cutout boyut sınırını aşıyor")
            if not body.startswith(b"SIMPLE  ="):
                raise CutoutError("kalıcı: yanıt FITS değil")
            if len(body) % 2880 != 0:
                raise CutoutError("eksik FITS (2880 baytın katı değil)")
            return body
        except (httpx.TransportError, httpx.TimeoutException, CutoutError) as exc:
            last = exc
            if isinstance(exc, CutoutError) and str(exc).startswith("kalıcı"):
                break
            if attempt + 1 < max_retries:
                sleep(1.5 * (2 ** attempt))
    raise CutoutError(f"Cutout indirilemedi: {last} ({url})")


class RawStore:
    """Ham cutout dosyaları: `raw/<sha[:2]>/<sha>.fits`. Aynı adres ikinci kez indirilmez."""

    def __init__(self, raw_dir: Path, db):
        self.raw_dir = Path(raw_dir)
        self.db = db

    def path_for(self, sha256: str) -> Path:
        return self.raw_dir / sha256[:2] / f"{sha256}.fits"

    def get(self, url: str, client: httpx.Client, timeout_s: float, max_retries: int) -> RawFile:
        t0 = time.monotonic()
        rec = self.db.get_raw(url)
        if rec:
            p = self.path_for(rec["sha256"])
            if p.exists() and p.stat().st_size == rec["size"]:
                return RawFile(url, rec["sha256"], rec["size"], p, True, 0.0)
        body = fetch_bytes(url, client, timeout_s, max_retries)
        sha = hashlib.sha256(body).hexdigest()
        p = self.path_for(sha)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(f".tmp{os.getpid()}")
            tmp.write_bytes(body)
            os.replace(tmp, p)
            try:
                os.chmod(p, 0o444)  # ham dosya salt okunur
            except OSError:
                pass
        self.db.put_raw(url, sha, len(body))
        return RawFile(url, sha, len(body), p, False, round(time.monotonic() - t0, 2))

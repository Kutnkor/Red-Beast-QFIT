"""IRSA TAP üzerinden SPHEREx Level-2 spektral görüntü kayıtlarının sorgulanması.

Bir kayıt = bir gözlem (pozlama) × bir dedektör. Aynı (gözlem kimliği, dedektör) çiftinin yeniden işlenmiş
kopyaları `dedupe()` ile tek kayda indirilir; bunlar farklı zamanlar değildir.
"""
from __future__ import annotations

import csv
import io
import hashlib
import math
import os
import re
import struct
import time
from dataclasses import asdict, dataclass
from typing import Callable, Iterable
import threading
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from contextlib import contextmanager
from urllib.parse import quote, urlencode

import httpx

ADQL_TEMPLATE = (
    "SELECT p.obs_publisher_did, p.energy_bandpassname, p.time_bounds_lower, p.time_bounds_upper, "
    "p.time_exposure, p.provenance_version, p.poly, a.uri, a.contentchecksum, a.contentlength "
    "FROM spherex.plane p JOIN spherex.artifact a ON a.planeid = p.planeid "
    "WHERE 1 = CONTAINS(POINT('ICRS', {ra:.7f}, {dec:.7f}), p.poly)"
)

_DID = re.compile(r"^ivo://irsa\.ipac/(?P<coll>spherex_[a-z0-9_]+)\?(?P<obs>[0-9A-Za-z_]+)/D(?P<det>[1-6])$")
_URI = re.compile(
    r"^ibe/data/spherex/(?P<rel>qr\d+|dr\d+)/level2/(?P<pp>[0-9A-Za-z_]+)/"
    r"(?P<tag>l2b-v(?P<ver>\d+)-(?P<yr>\d{4})-(?P<doy>\d{3}))/(?P<det>[1-6])/(?P<file>[A-Za-z0-9_.\-]+\.fits)$"
)


class ArchiveError(RuntimeError):
    """Arşiv erişim hatası (ağ, zaman aşımı, beklenmeyen yanıt)."""


@dataclass(frozen=True)
class Observation:
    obs_id: str               # ör. 2025W17_4B_0021_1
    detector: int             # 1..6
    collection: str           # ör. spherex_qr2_deep
    release: str              # ör. qr2
    l2_tag: str               # ör. l2b-v20-2025-240
    l2_version: int
    proc_year: int
    proc_doy: int
    pipeline_version: str     # plane.provenance_version (ör. 6.4)
    mjd_start: float          # UTC, MJD
    mjd_end: float
    exposure_s: float
    uri: str                  # ibe/data/spherex/...
    checksum: str             # md5:...
    content_length: int
    footprint: tuple[tuple[float, float], ...]  # (ra, dec) köşeleri, dedektör (1,1),(N,1),(N,N),(1,N) sırası

    @property
    def key(self) -> tuple[str, int]:
        return (self.obs_id, self.detector)

    @property
    def rank(self) -> tuple[int, int, int, int]:
        """Yeniden işleme önceliği: sürüm (qr3>qr2), l2 sürümü, işleme tarihi."""
        m = re.search(r"(\d+)$", self.release)
        rel = int(m.group(1)) if m else 0
        if self.release.startswith("dr"):
            rel += 1000  # tam veri sürümleri hızlı bakıştan önce gelir
        return (rel, self.l2_version, self.proc_year, self.proc_doy)

    @property
    def mjd_mid(self) -> float:
        return 0.5 * (self.mjd_start + self.mjd_end)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["footprint"] = [list(p) for p in self.footprint]
        return d

    @staticmethod
    def from_dict(d: dict) -> "Observation":
        d = dict(d)
        d["footprint"] = tuple((float(a), float(b)) for a, b in d["footprint"])
        return Observation(**d)


def parse_ewkb_polygon(hex_text: str) -> tuple[tuple[float, float], ...]:
    """IRSA `poly` sütununu (PostGIS EWKB, hex) köşe listesine çevirir. Kapanış noktası atılır."""
    raw = bytes.fromhex(hex_text.strip())
    if len(raw) < 9 or raw[0] not in (0, 1):
        raise ValueError("EWKB biçimi tanınmadı")
    end = "<" if raw[0] == 1 else ">"
    (typ,) = struct.unpack(end + "I", raw[1:5])
    off = 5
    if typ & 0x20000000:
        off += 4
    if (typ & 0xFF) != 3:
        raise ValueError("EWKB çokgen değil")
    (nrings,) = struct.unpack(end + "I", raw[off:off + 4])
    off += 4
    if nrings < 1:
        raise ValueError("EWKB boş çokgen")
    (npts,) = struct.unpack(end + "I", raw[off:off + 4])
    off += 4
    if npts < 4 or len(raw) < off + 16 * npts:
        raise ValueError("EWKB çokgen eksik")
    pts = [struct.unpack(end + "dd", raw[off + 16 * i: off + 16 * i + 16]) for i in range(npts)]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    return tuple((lon % 360.0, lat) for lon, lat in pts)


def parse_row(row: dict) -> Observation | None:
    """Bir TAP satırını Observation'a çevirir; Level-2 spektral görüntü değilse None."""
    did = _DID.match((row.get("obs_publisher_did") or "").strip())
    uri = _URI.match((row.get("uri") or "").strip())
    if not did or not uri:
        return None
    if int(did["det"]) != int(uri["det"]):
        return None
    try:
        footprint = parse_ewkb_polygon(row["poly"])
    except (ValueError, KeyError):
        return None
    if len(footprint) != 4:
        return None
    return Observation(
        obs_id=did["obs"],
        detector=int(did["det"]),
        collection=did["coll"],
        release=uri["rel"],
        l2_tag=uri["tag"],
        l2_version=int(uri["ver"]),
        proc_year=int(uri["yr"]),
        proc_doy=int(uri["doy"]),
        pipeline_version=(row.get("provenance_version") or "").strip(),
        mjd_start=float(row["time_bounds_lower"]),
        mjd_end=float(row["time_bounds_upper"]),
        exposure_s=float(row.get("time_exposure") or "nan"),
        uri=row["uri"].strip(),
        checksum=(row.get("contentchecksum") or "").strip(),
        content_length=int(float(row.get("contentlength") or 0)),
        footprint=footprint,
    )


def dedupe(observations: Iterable[Observation]) -> tuple[list[Observation], list[Observation]]:
    """Aynı (obs_id, dedektör) için en yüksek öncelikli kaydı tutar.

    Döner: (tutulanlar zaman sırasıyla, elenen yeniden işleme kopyaları).
    """
    best: dict[tuple[str, int], Observation] = {}
    dropped: list[Observation] = []
    for o in observations:
        cur = best.get(o.key)
        if cur is None:
            best[o.key] = o
        elif o.rank > cur.rank:
            dropped.append(cur)
            best[o.key] = o
        else:
            dropped.append(o)
    kept = sorted(best.values(), key=lambda o: (o.mjd_start, o.detector))
    return kept, dropped


class _Permanent(ArchiveError):
    """Yeniden denemenin anlamsız olduğu yanıt (4xx, hata belgesi)."""


def tap_sync_csv(
    tap_url: str,
    adql: str,
    timeout_s: float = 240.0,
    max_retries: int = 3,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[list[dict], dict]:
    """Eşzamanlı TAP sorgusu; CSV satırlarını sözlük listesi olarak döndürür.

    Sınırlı yeniden deneme: yalnızca ağ hatası, zaman aşımı ve 5xx için; üstel bekleme (2, 4, ... s).
    """
    data = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql}
    own = client is None
    client = client or httpx.Client(timeout=timeout_s, follow_redirects=True)
    last_err: Exception | None = None
    t0 = time.monotonic()
    try:
        for attempt in range(max(1, max_retries)):
            try:
                resp = client.post(tap_url.rstrip("/") + "/sync", data=data, timeout=timeout_s)
                if resp.status_code >= 500:
                    raise ArchiveError(f"TAP {resp.status_code}")
                if resp.status_code != 200:
                    raise _Permanent(f"TAP beklenmeyen yanıt {resp.status_code}: {resp.text[:200]}")
                text = resp.text
                if text.lstrip().startswith("<"):
                    raise _Permanent("TAP CSV yerine hata belgesi döndürdü: " + text[:200])
                rows = list(csv.DictReader(io.StringIO(text)))
                meta = {
                    "adql": adql,
                    "tap_url": tap_url,
                    "rows": len(rows),
                    "elapsed_s": round(time.monotonic() - t0, 2),
                    "attempts": attempt + 1,
                }
                return rows, meta
            except _Permanent:
                raise
            except (httpx.TransportError, httpx.TimeoutException, ArchiveError) as exc:
                last_err = exc
                if attempt + 1 < max_retries:
                    sleep(2.0 * (2 ** attempt))
        raise ArchiveError(f"Arşiv sorgusu başarısız ({max_retries} deneme): {last_err}")
    finally:
        if own:
            client.close()


def query_observations(
    ra_deg: float,
    dec_deg: float,
    tap_url: str,
    timeout_s: float = 240.0,
    max_retries: int = 3,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[list[Observation], dict]:
    """Verilen ICRS konumunu kapsayan tüm SPHEREx kayıtlarını döndürür (tekrarlar ayıklanmamış)."""
    protocol = os.environ.get("BLINKSPACE_ARCHIVE_PROTOCOL", "auto")
    if protocol not in ("auto", "tap", "sia"):
        raise ArchiveError("BLINKSPACE_ARCHIVE_PROTOCOL must be auto, tap, or sia")
    official_irsa = tap_url.rstrip("/") == "https://irsa.ipac.caltech.edu/TAP"
    if protocol == "sia" and official_irsa:
        return query_sia_observations(ra_deg, dec_deg, timeout_s, max_retries, client, sleep)
    adql = ADQL_TEMPLATE.format(ra=ra_deg % 360.0, dec=dec_deg)
    try:
        # In automatic discovery, a stalled TAP endpoint must not consume the
        # entire job budget before the independent official SIA service is tried.
        automatic = protocol == "auto" and official_irsa
        rows, meta = tap_sync_csv(tap_url, adql, min(timeout_s, 20.0) if automatic else timeout_s,
                                  1 if automatic else max_retries, client, sleep)
    except ArchiveError as exc:
        if protocol != "auto" or not official_irsa:
            raise
        checkpoint = (getattr(_hooks, "value", None) or (None, None))[0]
        if checkpoint is not None:
            checkpoint()        # a cancel that arrived during the TAP attempt
        observations, meta = query_sia_observations(ra_deg, dec_deg, timeout_s, max_retries, client, sleep)
        meta["tap_fallback_reason"] = str(exc)[:200]
        return observations, meta
    obs: list[Observation] = []
    unparsed: list[str] = []
    for r in rows:
        o = parse_row(r)
        if o is None:
            unparsed.append((r.get("uri") or "")[-90:])
        else:
            obs.append(o)
    meta["parsed"] = len(obs)
    meta["unparsed_examples"] = unparsed[:5]
    return obs, meta


# How long a query keeps retrying an archive that answers 502/503/504 before it reports the failure. A job waiting
# here holds the single worker, so this is also the longest another request can be kept in the queue by it.
SIA_BUDGET_S = 60.0

_hooks = threading.local()


@contextmanager
def interruptible(checkpoint: Callable[[], None] | None = None, on_wait: Callable[[dict], None] | None = None):
    """Let the caller abandon a long archive query and hear that it is waiting.

    ``checkpoint`` is called about five times a second from the calling thread while the query runs; raising from
    it (cancel, job timeout) abandons the query at once. ``on_wait`` is called from the calling thread each time a
    collection has to be retried, with what was answered and when the next attempt is.
    """
    previous = getattr(_hooks, "value", None)
    _hooks.value = (checkpoint, on_wait)
    try:
        yield
    finally:
        _hooks.value = previous


SIA_COLLECTIONS = ("spherex_dr1", "spherex_dr1_deep", "spherex_qr3", "spherex_qr3_deep")
SIA_URL = "https://irsa.ipac.caltech.edu/SIA"


def parse_sia_row(row: dict) -> Observation | None:
    """Read the same physical Level-2 files through IRSA's documented SIA2 index.

    SIA does not return file MD5 or processing-software version. These stay
    explicitly unknown here; pipeline records actual FITS VERSION and raw SHA.
    """
    url = str(row.get("access_url", ""))
    prefix = "https://irsa.ipac.caltech.edu/"
    if not url.startswith(prefix):
        return None
    uri = url[len(prefix):]
    match = _URI.fullmatch(uri)
    did = _DID.fullmatch(str(row.get("obs_publisher_did", "")))
    if not match or not did or match["det"] != did["det"]:
        return None
    region = str(row.get("s_region", "")).split()
    if region[:2] != ["POLYGON", "ICRS"]:
        return None
    try:
        values = [float(v) for v in region[2:]]
        points = tuple(zip(values[0::2], values[1::2]))
        if points and points[0] == points[-1]:
            points = points[:-1]
        if len(points) != 4 or len(values) % 2 or not all(math.isfinite(v) for v in values):
            return None
        t0, t1, exp = (float(row[k]) for k in ("t_min", "t_max", "t_exptime"))
        if not all(math.isfinite(v) for v in (t0, t1, exp)) or t1 < t0:
            return None
    except (ValueError, TypeError, KeyError):
        return None
    return Observation(obs_id=did["obs"], detector=int(match["det"]), collection=did["coll"], release=match["rel"],
        l2_tag=match["tag"], l2_version=int(match["ver"]), proc_year=int(match["yr"]), proc_doy=int(match["doy"]),
        pipeline_version="", mjd_start=t0, mjd_end=t1, exposure_s=exp, uri=uri, checksum="", content_length=0, footprint=points)


def query_sia_observations(ra_deg: float, dec_deg: float, timeout_s=120.0, max_retries=3, client=None, sleep=time.sleep):
    """Live, complete DR1+QR3 wide/deep discovery; all four queries must succeed.

    Source: https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/
    QR2 is no longer searchable as of DR1; DR1/QR3 supersede it. The tiny SIA
    circle intersects the target point; normal detector-edge validation follows.
    """
    from astropy.io.votable import parse_single_table

    checkpoint, on_wait = getattr(_hooks, "value", None) or (None, None)
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=timeout_s)
    start = time.monotonic()
    stop = threading.Event()
    waiting: dict = {}

    def pause(seconds: float) -> None:
        if sleep is time.sleep:
            stop.wait(seconds)      # returns at once when the query is abandoned
        else:
            sleep(seconds)

    def request_collection(collection):
        params = {"COLLECTION": collection, "POS": f"CIRCLE {ra_deg % 360:.7f} {dec_deg:.7f} 0.000001"}
        last = None
        # IRSA's front proxy answers 502/503/504 (or times out) for a while when it is busy. Those are worth waiting
        # out, within SIA_BUDGET_S; other errors keep the caller's retry count.
        tries = max(1, max_retries)
        patient = 8 if max_retries >= 3 else tries
        attempt = 0
        while True:
            if stop.is_set():
                raise ArchiveError("IRSA SIA query abandoned")
            try:
                # SIA POS is a space-delimited geometry. IRSA's front proxy can
                # reject form-style '+' separators; percent-encode real spaces.
                url = SIA_URL + "?" + urlencode(params, quote_via=quote)
                response = client.get(url, timeout=min(timeout_s, 75.0))
                response.raise_for_status()
                table = parse_single_table(io.BytesIO(response.content)).to_table(use_names_over_ids=True)
                required = {"access_url", "obs_publisher_did", "s_region", "t_min", "t_max", "t_exptime"}
                if not required <= set(table.colnames):
                    raise ArchiveError("IRSA SIA response schema changed")
                rows = [{name: row[name] for name in table.colnames} for row in table]
                meta = {"url": str(response.url), "collection": collection, "rows": len(rows),
                        "response_sha256": hashlib.sha256(response.content).hexdigest(), "response_bytes": len(response.content),
                        "attempts": attempt + 1}
                return rows, meta
            except (httpx.HTTPError, ValueError, ArchiveError) as exc:
                last = exc
                attempt += 1
                transient = isinstance(exc, httpx.TransportError) or (
                    isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 502, 503, 504))
                elapsed = time.monotonic() - start
                if attempt >= (patient if transient else tries) or (transient and elapsed >= SIA_BUDGET_S):
                    break
                if transient:
                    delay = min(20.0, 3.0 * 2 ** (attempt - 1), max(0.5, SIA_BUDGET_S - elapsed))
                    waiting.update(attempt=attempt + 1, collection=collection, retry_in_s=round(delay), waited_s=round(elapsed),
                                   budget_s=round(SIA_BUDGET_S),
                                   status=exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None)
                else:
                    delay = 2.0 * 2 ** (attempt - 1)
                pause(delay)
        raise ArchiveError(f"IRSA SIA {collection} failed: {last}")

    # Two at a time: four simultaneous queries are what tips the archive's proxy into 502s. The calling thread only
    # supervises, so a cancel or a job timeout takes effect within a fraction of a second even if a request hangs.
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="blinkspace-sia")
    futures = [pool.submit(request_collection, collection) for collection in SIA_COLLECTIONS]
    try:
        pending, told = set(futures), None
        while pending:
            done, pending = wait(pending, timeout=0.2, return_when=FIRST_EXCEPTION)
            for future in done:
                if future.exception() is not None:
                    raise future.exception()
            if checkpoint is not None:
                checkpoint()
            if on_wait is not None and waiting and waiting.get("attempt") != told:
                told = waiting.get("attempt")
                on_wait(dict(waiting))
        results = [future.result() for future in futures]
    except BaseException:
        stop.set()
        raise
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        if own:
            client.close()
    rows = [row for result, _ in results for row in result]
    observations, unparsed = [], []
    for row in rows:
        observation = parse_sia_row(row)
        if observation:
            observations.append(observation)
        else:
            unparsed.append(str(row.get("access_url", ""))[-100:])
    return observations, {"service": "IRSA SIA2", "tap_url": None, "adql": None, "sia_requests": [meta for _, meta in results],
        "rows": len(rows), "parsed": len(observations), "unparsed_examples": unparsed[:5],
        "elapsed_s": round(time.monotonic() - start, 2),
        "source_url": "https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/"}

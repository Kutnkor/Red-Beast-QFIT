"""Test altyapısı.

BURADAKİ HER ŞEY SENTETİKTİR: `FakeArchive`, SPHEREx Level-2 dosya yapısını taklit eden yapay FITS üretir
(bilinen konumda yıldızlar, bilinen hızda hareket eden bir kaynak, bilinen gürültü). Gerçek arşive giden
testler ayrı dosyadadır (`test_live_archive.py`, `-m live`).
"""
from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from blinkspace.archive import Observation
from blinkspace.config import load_settings
from blinkspace.wavelength import WaveModel, WaveTable

PIX = 6.15 / 3600.0
NDET = 2040
QR2_FLAGS = {"TRANSIENT": 0, "OVERFLOW": 1, "SUR_ERROR": 2, "PHANTOM": 4, "REFERENCE": 5, "NONFUNC": 6, "DICHROIC": 7,
             "MISSING_DATA": 9, "HOT": 10, "COLD": 11, "FULLSAMPLE": 12, "PHANMISS": 14, "NONLINEAR": 15, "PERSIST": 17,
             "OUTLIER": 19, "SOURCE": 21}
QR3_FLAGS = dict(QR2_FLAGS, CROSSTALK=20, GHOST=22, GHOST_FPA=23, GHOST_EXT=24, STREAK=25, BLOOM=26, SNOWBALL=27, HALO=28)
for _k in ("PHANTOM", "REFERENCE"):
    QR3_FLAGS.pop(_k)


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", default=False, help="gerçek IRSA arşivine giden testleri çalıştır")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="gerçek arşiv testi; --live ile çalıştırın")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


def linear_wave_table(lam0: float = 1.0, lam1: float = 2.0, r: float = 40.0) -> WaveTable:
    """Dalga boyu yalnızca dedektör y'sine doğrusal bağlı sentetik tablo (1-tabanlı koordinat)."""
    # gerçek tablolardaki gibi tam sayı kontrol noktaları
    x = np.array([1, 256, 511, 766, 1021, 1275, 1530, 1785, 2040], float)
    y = x.copy()
    lam = lam0 + (y[:, None] - 1) / (NDET - 1) * (lam1 - lam0) + 0 * x[None, :]
    return WaveTable(x, y, np.dstack([lam, lam / r]))


def det_wcs(ra: float, dec: float, px: float, py: float, rot_deg: float) -> WCS:
    """Hedefi (ra, dec) 1-tabanlı dedektör pikseli (px, py)'ye koyan, `rot_deg` dönük tam dedektör WCS'i."""
    a = math.radians(rot_deg)
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra, dec]
    w.wcs.crpix = [px, py]
    w.wcs.cd = PIX * np.array([[-math.cos(a), math.sin(a)], [math.sin(a), math.cos(a)]])
    return w


@dataclass
class FakeExposure:
    obs_id: str
    detector: int
    mjd: float
    wcs: WCS                       # tam dedektör WCS'i
    release: str = "qr2"
    l2_version: int = 20
    proc: tuple[int, int] = (2025, 240)
    pipeline_version: str = "6.4"
    collection: str = "spherex_qr2"
    bad_pixels: list[tuple[int, int, str]] = field(default_factory=list)  # (det_x0, det_y0, bayrak adı) 0-tabanlı
    flux_scale: dict[str, float] = field(default_factory=dict)            # yıldız adı -> çarpan (parlaklık değişimi)
    psf_sigma: float = 0.8
    fail_download: bool = False

    @property
    def l2_tag(self) -> str:
        return f"l2b-v{self.l2_version}-{self.proc[0]}-{self.proc[1]:03d}"

    @property
    def uri(self) -> str:
        pp = "_".join(self.obs_id.split("_")[:2])
        return f"ibe/data/spherex/{self.release}/level2/{pp}/{self.l2_tag}/{self.detector}/level2_{self.obs_id}D{self.detector}_spx_{self.l2_tag}.fits"

    def observation(self) -> Observation:
        ra, dec = self.wcs.all_pix2world([1, NDET, NDET, 1], [1, 1, NDET, NDET], 1)
        return Observation(
            obs_id=self.obs_id, detector=self.detector, collection=self.collection, release=self.release, l2_tag=self.l2_tag,
            l2_version=self.l2_version, proc_year=self.proc[0], proc_doy=self.proc[1], pipeline_version=self.pipeline_version,
            mjd_start=self.mjd, mjd_end=self.mjd + 115.0 / 86400.0, exposure_s=113.58, uri=self.uri, checksum="md5:synthetic",
            content_length=71634240, footprint=tuple((float(a) % 360.0, float(b)) for a, b in zip(ra, dec)),
        )


class FakeArchive:
    """Sentetik gökyüzü + sentetik pozlamalar. `stars`: ad -> (ra, dec, akı); `mover`: (ra0, dec0, pm_ra_deg/gün, pm_dec_deg/gün, akı, mjd0)."""

    def __init__(self, wave_tables: dict[int, WaveTable], stars: dict[str, tuple[float, float, float]], mover=None,
                 background: float = 0.4, noise: float = 0.02, seed: int = 7):
        self.tables = wave_tables
        self.stars = stars
        self.mover = mover
        self.background = background
        self.noise = noise
        self.exposures: list[FakeExposure] = []
        self.rng_seed = seed
        self.n_tap = 0
        self.n_downloads = 0
        self.tap_fail = 0          # bu kadar sorgu ağ hatasıyla başarısız olur
        self.download_delay = 0.0

    def add(self, exp: FakeExposure) -> FakeExposure:
        self.exposures.append(exp)
        return exp

    # -- arşiv sorgusu taklidi ------------------------------------------------------------
    def query(self, ra, dec, tap_url, timeout_s=0, max_retries=3, client=None, sleep=None):
        from blinkspace.archive import ArchiveError
        self.n_tap += 1
        if self.tap_fail > 0:
            self.tap_fail -= 1
            raise ArchiveError("Arşiv sorgusu başarısız (sentetik hata)")
        obs = []
        for e in self.exposures:
            x, y = e.wcs.all_world2pix([ra], [dec], 1)
            if 1 <= x[0] <= NDET and 1 <= y[0] <= NDET:
                obs.append(e.observation())
        return obs, {"adql": "SYNTHETIC", "tap_url": tap_url, "rows": len(obs), "parsed": len(obs), "elapsed_s": 0.0, "attempts": 1}

    # -- cutout indirme taklidi -----------------------------------------------------------
    def fetch(self, url, client=None, timeout_s=0, max_retries=3, sleep=None):
        import time as _t
        from blinkspace.cutouts import CutoutError, validate_url
        validate_url(url)
        m = re.match(r"^https://irsa\.ipac\.caltech\.edu/(?P<uri>[^?]+)\?center=(?P<ra>[\d.]+),(?P<dec>[-\d.]+)&size=(?P<size>[\d.]+)$", url)
        assert m, url
        exp = next(e for e in self.exposures if e.uri == m["uri"])
        if self.download_delay:
            _t.sleep(self.download_delay)
        self.n_downloads += 1
        if exp.fail_download:
            raise CutoutError("Cutout indirilemedi: sentetik hata")
        return self.render(exp, float(m["ra"]), float(m["dec"]), float(m["size"]))

    def render(self, exp: FakeExposure, ra: float, dec: float, size_deg: float) -> bytes:
        n = int(round(size_deg / PIX))
        tx, ty = exp.wcs.all_world2pix([ra], [dec], 0)
        x0 = int(round(tx[0] - n / 2.0))
        y0 = int(round(ty[0] - n / 2.0))
        x1, y1 = min(x0 + n, NDET), min(y0 + n, NDET)
        x0, y0 = max(x0, 0), max(y0, 0)
        ny, nx = y1 - y0, x1 - x0
        cw = exp.wcs.deepcopy()
        cw.wcs.crpix = [exp.wcs.wcs.crpix[0] - x0, exp.wcs.wcs.crpix[1] - y0]
        yy, xx = np.mgrid[0:ny, 0:nx]
        rng = np.random.default_rng(self.rng_seed + hash((exp.obs_id, exp.detector)) % 100000)
        img = self.background + rng.normal(0.0, self.noise, (ny, nx))
        sources = [(n_, r, d, f * exp.flux_scale.get(n_, 1.0)) for n_, (r, d, f) in self.stars.items()]
        if self.mover is not None:
            r0, d0, pr, pd, f, t0 = self.mover
            sources.append(("mover", r0 + pr * (exp.mjd - t0), d0 + pd * (exp.mjd - t0), f * exp.flux_scale.get("mover", 1.0)))
        s = exp.psf_sigma
        for _, r, d, f in sources:
            sx, sy = cw.all_world2pix([r], [d], 0)
            img += f / (2 * math.pi * s * s) * np.exp(-((xx - sx[0]) ** 2 + (yy - sy[0]) ** 2) / (2 * s * s))
        flags = np.zeros((ny, nx), np.int32)
        defs = QR3_FLAGS if exp.release == "qr3" else QR2_FLAGS
        for bx, by, name in exp.bad_pixels:
            if x0 <= bx < x1 and y0 <= by < y1:
                flags[by - y0, bx - x0] |= 1 << defs[name]
                if name in ("NONFUNC", "MISSING_DATA"):
                    img[by - y0, bx - x0] = np.nan
        var = np.full((ny, nx), self.noise ** 2, np.float32)

        ih = cw.to_header()
        ih["EXTNAME"] = "IMAGE"
        ih["BUNIT"] = "MJy / sr"
        ih["OBSID"] = exp.obs_id
        ih["DETECTOR"] = exp.detector
        ih["TIMESYS"] = "UTC"
        ih["MJD-BEG"] = exp.mjd
        ih["MJD-AVG"] = exp.mjd + 57.5 / 86400.0
        ih["MJD-END"] = exp.mjd + 115.0 / 86400.0
        ih["DATE-AVG"] = "synthetic"
        ih["XPOSURE"] = 113.5826
        ih["PSF_FWHM"] = 2.3548 * s * 6.15
        ih["L1DQAFLG"] = "Pass"
        ih["L2DQAFLG"] = "Pass"
        for ax, off in ((1, x0), (2, y0)):
            ih[f"CRPIX{ax}A"] = 1.0 - off
            ih[f"CRPIX{ax}W"] = 1.0 - off
            ih[f"CDELT{ax}W"] = 1
            ih[f"CRVAL{ax}W"] = 1
            ih[f"CTYPE{ax}W"] = "WAVE-TAB"
            ih[f"PS{ax}_0W"] = "WCS-WAVE"
            ih[f"PS{ax}_1W"] = "VALUES"
        fh = fits.Header()
        fh["EXTNAME"] = "FLAGS"
        if exp.release == "qr3":
            for name, bit in defs.items():
                fh[f"MSKN{bit:04d}"] = name
                fh[f"MSKM{bit:04d}"] = 1 << bit
        else:
            for name, bit in defs.items():
                fh[f"MP_{name}"] = bit
        t = self.tables[exp.detector]
        vals = t.values.astype(np.float32)
        cols = [
            fits.Column(name="X", format=f"{len(t.x)}J", dim=f"({len(t.x)})", array=[t.x.astype(np.int32)]),
            fits.Column(name="Y", format=f"{len(t.y)}J", dim=f"({len(t.y)})", array=[t.y.astype(np.int32)]),
            fits.Column(name="VALUES", format=f"{vals.size}E", dim=f"(2,{len(t.x)},{len(t.y)})", array=[vals]),
        ]
        prim = fits.PrimaryHDU()
        prim.header["VERSION"] = exp.pipeline_version
        psf = (fits.BinTableHDU.from_columns([fits.Column(name="BINX", format="J", array=[0])], name="EPSF") if exp.release == "qr3"
               else fits.ImageHDU(np.zeros((3, 5, 5), np.float32), name="PSF"))
        hdul = fits.HDUList([
            prim,
            fits.ImageHDU(img.astype(np.float32), header=ih),
            fits.ImageHDU(flags, header=fh),
            fits.ImageHDU(var, name="VARIANCE"),
            fits.ImageHDU(np.full((ny, nx), self.background, np.float32), name="ZODI"),
            psf,
            fits.BinTableHDU.from_columns(cols, name="WCS-WAVE"),
        ])
        buf = io.BytesIO()
        hdul.writeto(buf)
        return buf.getvalue()


TARGET = (150.0, 20.0)


@pytest.fixture
def wave_tables():
    return {d: linear_wave_table(1.0 + (d - 1), 2.0 + (d - 1)) for d in range(1, 7)}


@pytest.fixture
def archive(wave_tables):
    """Hedef çevresinde 6 sabit yıldız + yılda ~10″ kuzeye hareket eden bir kaynak içeren sentetik gökyüzü."""
    ra, dec = TARGET
    c = math.cos(math.radians(dec))
    stars = {
        "s1": (ra + 60 / 3600 / c, dec + 40 / 3600, 40.0),
        "s2": (ra - 80 / 3600 / c, dec + 90 / 3600, 60.0),
        "s3": (ra + 100 / 3600 / c, dec - 70 / 3600, 50.0),
        "s4": (ra - 50 / 3600 / c, dec - 110 / 3600, 45.0),
        "s5": (ra + 20 / 3600 / c, dec + 120 / 3600, 35.0),
        "var": (ra - 120 / 3600 / c, dec - 20 / 3600, 50.0),
    }
    mover = (ra, dec - 8.0 / 3600, 0.0, 10.0 / 3600 / 365.25, 30.0, 60900.0)
    return FakeArchive(wave_tables, stars, mover)


def add_matched_series(archive: FakeArchive, n: int = 4, det: int = 2, det_y: float = 1000.0, step_days: float = 120.0,
                       rot0: float = 10.0) -> list[FakeExposure]:
    """Hedefi her seferinde aynı dedektör satırına (aynı dalga boyu) koyan, farklı yönelimli n pozlama."""
    out = []
    for i in range(n):
        w = det_wcs(TARGET[0], TARGET[1], 700.0 + 40 * i, det_y + (i % 2), rot0 + 35.0 * i)
        # gözlem kimliği arşiv genelinde benzersiz olmalı (aynı kimlik = yeniden işlenmiş kopya sayılır)
        out.append(archive.add(FakeExposure(f"2025W{20 + i}_1A_{100 + len(archive.exposures):04d}_1", det, 60900.0 + step_days * i, w)))
    return out


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("BLINKSPACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BLINKSPACE_FRONTEND_DIST", str(tmp_path / "no-dist"))
    monkeypatch.setenv("BLINKSPACE_JOB_TIMEOUT_S", "60")
    return load_settings()


@pytest.fixture
def pipeline(settings, archive, wave_tables, monkeypatch):
    """Sentetik arşive bağlı gerçek hat (ağ erişimi yok)."""
    from blinkspace import catalogs, cutouts
    from blinkspace import pipeline as pl
    from blinkspace.db import Database

    monkeypatch.setattr(pl, "query_observations", archive.query)
    monkeypatch.setattr(cutouts, "fetch_bytes", archive.fetch)
    monkeypatch.setattr(catalogs, "query_gaia", lambda *a, **k: [
        {"id": n, "ra": r, "dec": d, "pmra": 0.0, "pmdec": 0.0, "parallax": 1.0, "g": 12.0, "rp": 11.5}
        for n, (r, d, f) in archive.stars.items()])
    monkeypatch.setattr(catalogs, "query_allwise", lambda *a, **k: [])
    db = Database(settings.db_path)
    return pl.Pipeline(settings, db, WaveModel(wave_tables), {})

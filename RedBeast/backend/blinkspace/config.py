"""Yapılandırma. Sırlar burada tutulmaz; tüm değerler ortam değişkeniyle ezilebilir."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PIPELINE_VERSION = "1.2.0"

# İndirmeye izin verilen tek kaynak (SSRF önlemi): IRSA IBE SPHEREx ağacı.
ALLOWED_DATA_HOST = "irsa.ipac.caltech.edu"
ALLOWED_DATA_PREFIX = "/ibe/data/spherex/"


def _env(name: str, default: str) -> str:
    return os.environ.get(f"BLINKSPACE_{name}", default)


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    tap_url: str
    irsa_base: str
    simbad_tap_url: str
    # sınırlar (ölçümlere dayalı gerekçe: reports/performance.md)
    min_fov_arcmin: float
    max_fov_arcmin: float
    default_fov_arcmin: float
    max_frames: int
    default_frames: int
    download_concurrency: int
    http_timeout_s: float
    tap_timeout_s: float
    job_timeout_s: float
    max_retries: int
    tap_cache_hours: float
    max_note_chars: int
    max_marks: int
    frontend_dist: Path

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "blinkspace.sqlite3"


def load_settings() -> Settings:
    root = Path(__file__).resolve().parents[2]
    data_dir = Path(_env("DATA_DIR", str(root / "data"))).resolve()
    return Settings(
        data_dir=data_dir,
        tap_url=_env("TAP_URL", "https://irsa.ipac.caltech.edu/TAP"),
        irsa_base=_env("IRSA_BASE", "https://irsa.ipac.caltech.edu/"),
        simbad_tap_url=_env("SIMBAD_TAP_URL", "https://simbad.harvard.edu/simbad/sim-tap"),
        min_fov_arcmin=float(_env("MIN_FOV_ARCMIN", "2")),
        max_fov_arcmin=float(_env("MAX_FOV_ARCMIN", "30")),
        default_fov_arcmin=float(_env("DEFAULT_FOV_ARCMIN", "6")),
        max_frames=int(_env("MAX_FRAMES", "16")),
        default_frames=int(_env("DEFAULT_FRAMES", "8")),
        download_concurrency=int(_env("DOWNLOAD_CONCURRENCY", "3")),
        http_timeout_s=float(_env("HTTP_TIMEOUT_S", "120")),
        tap_timeout_s=float(_env("TAP_TIMEOUT_S", "240")),
        job_timeout_s=float(_env("JOB_TIMEOUT_S", "900")),
        max_retries=int(_env("MAX_RETRIES", "3")),
        tap_cache_hours=float(_env("TAP_CACHE_HOURS", "24")),
        max_note_chars=int(_env("MAX_NOTE_CHARS", "2000")),
        max_marks=int(_env("MAX_MARKS", "200")),
        frontend_dist=Path(_env("FRONTEND_DIST", str(root / "frontend" / "dist"))).resolve(),
    )

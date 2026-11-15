"""SPHEREx Level-2 spektral görüntü (veya cutout) MEF dosyalarının okunması.

Katmanlar konuma göre değil **ada göre** okunur. Gerçek dosyalarda doğrulanan farklar:
- QR2 (pipeline 6.4, 6.5.x): IMAGE, FLAGS, VARIANCE, ZODI, PSF (küp), WCS-WAVE
- QR3 (pipeline 7.0.x):      IMAGE, FLAGS, VARIANCE, ZODI, EPSF (tablo), WCS-WAVE
Bayrak tanımları dosyanın FLAGS başlığından okunur: QR2 `MP_<AD> = bit`, QR3 `MSKNnnnn = '<AD>'`.
"""
from __future__ import annotations

import io
import logging
import re
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS, FITSFixedWarning

from .wavelength import WaveTable

logging.getLogger("astropy").setLevel(logging.WARNING)

REQUIRED_HDUS = ("IMAGE", "FLAGS", "VARIANCE", "WCS-WAVE")
EXPECTED_BUNIT = "MJy/sr"


class SpxFormatError(ValueError):
    """Dosya beklenen SPHEREx Level-2 yapısında değil."""


@dataclass
class SpxFrame:
    image: np.ndarray            # MJy/sr, zodyak ışığı çıkarılmamış
    flags: np.ndarray            # int bit maskesi
    variance: np.ndarray         # (MJy/sr)^2
    zodi: np.ndarray | None      # modellenmiş zodyak arka planı, MJy/sr
    wcs: WCS                     # gök WCS'i (TAN-SIP), cutout piksel koordinatlarında
    wave_table: WaveTable
    det_origin: tuple[float, float]  # cutout 0-tabanlı piksel (0,0)'ın 1-tabanlı dedektör koordinatı
    flag_defs: dict[str, int]    # ad -> bit numarası
    obs_id: str
    detector: int
    pipeline_version: str        # birincil başlık VERSION
    timesys: str
    mjd_beg: float
    mjd_avg: float
    mjd_end: float
    date_avg: str
    exposure_s: float
    psf_fwhm_arcsec: float | None
    psf_kind: str | None         # 'PSF' | 'EPSF' | None
    bunit: str
    l1_dqa: str | None
    l2_dqa: str | None
    hdu_names: tuple[str, ...]

    @property
    def shape(self) -> tuple[int, int]:
        return self.image.shape

    def detector_coords(self, x, y):
        """Cutout 0-tabanlı piksel -> 1-tabanlı dedektör koordinatı (SIP uygulanmaz)."""
        return np.asarray(x, float) + self.det_origin[0], np.asarray(y, float) + self.det_origin[1]

    def wavelength_at(self, x, y):
        """Cutout pikselindeki (merkez dalga boyu, bant genişliği) µm."""
        dx, dy = self.detector_coords(x, y)
        return self.wave_table.evaluate(dx, dy)

    def wavelength_map(self) -> tuple[np.ndarray, np.ndarray]:
        ny, nx = self.shape
        yy, xx = np.mgrid[0:ny, 0:nx]
        return self.wavelength_at(xx, yy)

    def world_to_pixel(self, ra_deg, dec_deg):
        x, y = self.wcs.all_world2pix(np.atleast_1d(ra_deg), np.atleast_1d(dec_deg), 0, quiet=True)
        return x, y


def parse_flag_defs(header: fits.Header) -> dict[str, int]:
    """FLAGS başlığından bayrak adı -> bit numarası sözlüğü (her iki sürüm biçimi)."""
    defs: dict[str, int] = {}
    for key in header.keys():
        if key.startswith("MP_"):
            try:
                defs[key[3:].strip().upper()] = int(header[key])
            except (TypeError, ValueError):
                continue
    for key in header.keys():
        m = re.match(r"^MSKN(\d{4})$", key)
        if m:
            name = str(header[key]).strip().upper()
            if name:
                defs[name] = int(m.group(1))
    return defs


def _norm_unit(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def read_spx(source: bytes | str | Path) -> SpxFrame:
    """Bir SPHEREx MEF dosyasını (tam görüntü veya IBE cutout) okur ve doğrular."""
    if isinstance(source, (bytes, bytearray)):
        hdul = fits.open(io.BytesIO(bytes(source)), memmap=False)
    else:
        hdul = fits.open(str(source), memmap=False)
    with hdul:
        names = tuple(h.name for h in hdul)
        for req in REQUIRED_HDUS:
            if req not in names:
                raise SpxFormatError(f"Eksik katman: {req} (bulunanlar: {', '.join(names)})")
        ih = hdul["IMAGE"].header
        image = np.asarray(hdul["IMAGE"].data, dtype=np.float32)
        flags = np.asarray(hdul["FLAGS"].data)
        variance = np.asarray(hdul["VARIANCE"].data, dtype=np.float32)
        if image.ndim != 2:
            raise SpxFormatError("IMAGE iki boyutlu değil")
        if flags.shape != image.shape or variance.shape != image.shape:
            raise SpxFormatError("IMAGE, FLAGS ve VARIANCE boyutları uyuşmuyor")
        if not np.issubdtype(flags.dtype, np.integer):
            raise SpxFormatError("FLAGS tam sayı değil")
        flags = flags.astype(np.int64)
        bunit = str(ih.get("BUNIT", ""))
        if _norm_unit(bunit) != EXPECTED_BUNIT:
            raise SpxFormatError(f"Beklenmeyen birim: {bunit!r} (beklenen MJy/sr)")
        zodi = None
        if "ZODI" in names and hdul["ZODI"].data is not None and hdul["ZODI"].data.shape == image.shape:
            zodi = np.asarray(hdul["ZODI"].data, dtype=np.float32)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FITSFixedWarning)
            wcs = WCS(ih)
        if not wcs.has_celestial:
            raise SpxFormatError("IMAGE başlığında gök WCS'i yok")

        # 'W' alternatifi: tablo koordinatı = (i + 1 - CRPIXnW) * CDELTnW + CRVALnW, i: 0-tabanlı cutout pikseli.
        try:
            ox = (1.0 - float(ih["CRPIX1W"])) * float(ih.get("CDELT1W", 1)) + float(ih.get("CRVAL1W", 1))
            oy = (1.0 - float(ih["CRPIX2W"])) * float(ih.get("CDELT2W", 1)) + float(ih.get("CRVAL2W", 1))
        except KeyError as exc:
            raise SpxFormatError(f"Spektral WCS anahtarı eksik: {exc}") from exc
        if float(ih.get("CDELT1W", 1)) != 1.0 or float(ih.get("CDELT2W", 1)) != 1.0:
            raise SpxFormatError("Spektral WCS ölçeği 1 değil; desteklenmiyor")
        if str(ih.get("PS1_0W", "WCS-WAVE")).strip() != "WCS-WAVE":
            raise SpxFormatError("Spektral WCS tablosu WCS-WAVE katmanını göstermiyor")
        wave_table = WaveTable.from_hdu(hdul["WCS-WAVE"])

        flag_defs = parse_flag_defs(hdul["FLAGS"].header)
        if not flag_defs:
            raise SpxFormatError("FLAGS başlığında bayrak tanımı bulunamadı")

        timesys = str(ih.get("TIMESYS", "")).strip().upper()
        try:
            mjd_beg = float(ih["MJD-BEG"])
            mjd_end = float(ih["MJD-END"])
            mjd_avg = float(ih.get("MJD-AVG", 0.5 * (mjd_beg + mjd_end)))
        except KeyError as exc:
            raise SpxFormatError(f"Zaman anahtarı eksik: {exc}") from exc

        psf_kind = "EPSF" if "EPSF" in names else ("PSF" if "PSF" in names else None)
        fwhm = ih.get("PSF_FWHM")
        return SpxFrame(
            image=image,
            flags=flags,
            variance=variance,
            zodi=zodi,
            wcs=wcs,
            wave_table=wave_table,
            det_origin=(ox, oy),
            flag_defs=flag_defs,
            obs_id=str(ih.get("OBSID", "")).strip(),
            detector=int(ih.get("DETECTOR", 0)),
            pipeline_version=str(hdul[0].header.get("VERSION", "")).strip(),
            timesys=timesys,
            mjd_beg=mjd_beg,
            mjd_avg=mjd_avg,
            mjd_end=mjd_end,
            date_avg=str(ih.get("DATE-AVG", "")).strip(),
            exposure_s=float(ih.get("XPOSURE", "nan")),
            psf_fwhm_arcsec=float(fwhm) if fwhm is not None else None,
            psf_kind=psf_kind,
            bunit=bunit,
            l1_dqa=(str(ih["L1DQAFLG"]).strip() if "L1DQAFLG" in ih else None),
            l2_dqa=(str(ih["L2DQAFLG"]).strip() if "L2DQAFLG" in ih else None),
            hdu_names=names,
        )

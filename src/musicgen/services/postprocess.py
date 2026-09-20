"""Pos-processamento de audio: normalizacao de loudness, fades e conversao.

Usa apenas soundfile + numpy + pyloudnorm para nao arrastar torch para o
processo da UI.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

_TRUE_PEAK_CEILING_DB = -1.0


def analyze(path: Path) -> dict:
    """Metricas basicas do arquivo: duracao, sample rate, LUFS integrado e pico."""
    data, sr = sf.read(str(path), always_2d=True, dtype="float64")
    metrics = {
        "sample_rate": sr,
        "duration_s": round(len(data) / sr, 2),
        "channels": data.shape[1],
        "peak_db": round(float(20 * np.log10(max(np.max(np.abs(data)), 1e-12))), 2),
    }
    try:
        import pyloudnorm as pyln

        meter = pyln.Meter(sr)
        metrics["lufs"] = round(float(meter.integrated_loudness(data)), 2)
    except Exception as exc:
        logger.debug("loudness indisponivel: %s", exc)
        metrics["lufs"] = None
    return metrics


def normalize_loudness(
    path: Path,
    *,
    target_lufs: float = -14.0,
    out_path: Path | None = None,
) -> Path:
    """Normaliza para ``target_lufs`` com teto de pico, in-place por default.

    -14 LUFS e o alvo das plataformas de streaming. O limitador aqui e um
    simples ganho com teto: suficiente porque o material do modelo ja vem
    controlado, e evita distorcao de um limiter mal calibrado.
    """
    import pyloudnorm as pyln

    data, sr = sf.read(str(path), always_2d=True, dtype="float64")
    meter = pyln.Meter(sr)
    current = meter.integrated_loudness(data)

    if not np.isfinite(current):
        logger.warning("loudness nao mensuravel em %s; normalizacao ignorada", path.name)
        return path

    gain = 10 ** ((target_lufs - current) / 20.0)
    out = data * gain

    ceiling = 10 ** (_TRUE_PEAK_CEILING_DB / 20.0)
    peak = float(np.max(np.abs(out)))
    if peak > ceiling:
        out *= ceiling / peak

    target_path = out_path or path
    sf.write(str(target_path), out, sr, subtype="PCM_24" if target_path.suffix == ".wav" else None)
    logger.info("%s: %.1f LUFS -> %.1f LUFS", target_path.name, current, target_lufs)
    return target_path


def apply_fades(path: Path, *, fade_in_s: float = 0.05, fade_out_s: float = 1.5) -> Path:
    """Aplica fade in/out para eliminar cliques de borda e cortes abruptos."""
    data, sr = sf.read(str(path), always_2d=True, dtype="float64")
    n = len(data)
    fi, fo = int(fade_in_s * sr), int(fade_out_s * sr)

    if fi > 0 and fi < n:
        data[:fi] *= np.linspace(0.0, 1.0, fi)[:, None]
    if fo > 0 and fo < n:
        data[-fo:] *= np.linspace(1.0, 0.0, fo)[:, None]

    sf.write(str(path), data, sr)
    return path

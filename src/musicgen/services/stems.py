"""Separacao em stems (vocal / bateria / baixo / outros) via Demucs.

Opcional e isolado: roda em subprocesso para que o torch do Demucs nunca seja
importado dentro do processo do Streamlit.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

STEM_NAMES = ("vocals", "drums", "bass", "other")


class StemsUnavailable(RuntimeError):
    """Demucs nao instalado no ambiente atual."""


def is_available() -> bool:
    try:
        import demucs  # noqa: F401

        return True
    except Exception:
        return shutil.which("demucs") is not None


def separate(
    audio_path: Path,
    dest_dir: Path,
    *,
    model: str = "htdemucs",
    timeout_s: int = 1800,
) -> dict[str, Path]:
    """Separa ``audio_path`` em stems dentro de ``dest_dir``.

    Returns:
        Mapa ``{nome_do_stem: caminho}`` apenas com os stems efetivamente gerados.
    """
    if not is_available():
        raise StemsUnavailable(
            "Demucs nao encontrado. Instale com: pip install -e .[stems]"
        )

    dest_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "demucs.separate",
        "-n",
        model,
        "-o",
        str(dest_dir),
        "--filename",
        "{stem}.{ext}",
        str(audio_path),
    ]
    logger.info("executando demucs: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Demucs falhou (rc={proc.returncode}): {proc.stderr[-2000:]}")

    produced = dest_dir / model
    found: dict[str, Path] = {}
    for stem in STEM_NAMES:
        for candidate in produced.rglob(f"{stem}.*"):
            found[stem] = candidate
            break
    if not found:
        raise RuntimeError(f"Demucs nao produziu stems em {produced}")
    return found

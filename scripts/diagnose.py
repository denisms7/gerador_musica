"""Diagnostico de ambiente independente do app (roda sem as dependencias instaladas).

    python scripts/diagnose.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys

PROFILES = [
    (24, "acestep-v15-xl-sft", "acestep-5Hz-lm-4B", "Qualidade maxima, sem offload."),
    (20, "acestep-v15-xl-turbo", "acestep-5Hz-lm-1.7B", "XL rapido, sem offload."),
    (16, "acestep-v15-sft", "acestep-5Hz-lm-1.7B", "Boa qualidade; XL exigiria offload."),
    (12, "acestep-v15-turbo", "acestep-5Hz-lm-1.7B", "Turbo com LM medio, sem offload."),
    (6, "acestep-v15-turbo", "acestep-5Hz-lm-0.6B",
     "8GB = tier3 no ACE-Step: so o LM 0.6B e aceito, CPU offload automatico."),
    (0, "acestep-v15-turbo", "", "INT8 + offload total para CPU. Lento."),
]


def gpus() -> list[tuple[str, float, str]]:
    if not shutil.which("nvidia-smi"):
        return []
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=20, check=False,
    )
    found = []
    for line in out.stdout.strip().splitlines():
        name, total, driver = [p.strip() for p in line.split(",")]
        found.append((name, int(total) / 1024, driver))
    return found


def main() -> int:
    print("=" * 70)
    print("MusicGen - diagnostico de ambiente")
    print("=" * 70)
    print(f"Python      : {sys.version.split()[0]}  ({sys.executable})")
    print(f"uv          : {shutil.which('uv') or 'NAO ENCONTRADO -> https://astral.sh/uv'}")
    print(f"git         : {shutil.which('git') or 'NAO ENCONTRADO'}")
    print(f"ffmpeg      : {shutil.which('ffmpeg') or 'nao encontrado (opcional)'}")

    found = gpus()
    if not found:
        print("\nGPU         : nenhuma GPU NVIDIA detectada (nvidia-smi ausente).")
        print("              Geracao local sera inviavel na pratica.")
        return 1

    for name, vram, driver in found:
        print(f"\nGPU         : {name}")
        print(f"VRAM        : {vram:.1f} GB   (driver {driver})")
        for threshold, dit, lm, note in PROFILES:
            if vram >= threshold:
                print(f"\nPerfil recomendado:\n  MUSICGEN_DIT_MODEL={dit}")
                if lm:
                    print(f"  MUSICGEN_LM_MODEL={lm}")
                print(f"  -> {note}")
                break
    print("\nCopie essas linhas para o seu .env e reinicie o servidor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

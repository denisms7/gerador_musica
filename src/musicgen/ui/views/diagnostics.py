"""Diagnostico: ambiente, GPU, backend de inferencia e controle do servidor."""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys

import streamlit as st

from musicgen.services import stems as stems_mod
from musicgen.ui import components, state

_VRAM_PROFILES = [
    (24, "acestep-v15-xl-sft", "acestep-5Hz-lm-4B", "Qualidade maxima, sem offload."),
    (20, "acestep-v15-xl-turbo", "acestep-5Hz-lm-1.7B", "XL rapido, cabe sem offload."),
    (16, "acestep-v15-sft", "acestep-5Hz-lm-1.7B", "Boa qualidade; XL exigiria offload."),
    (12, "acestep-v15-turbo", "acestep-5Hz-lm-1.7B", "Turbo com LM medio; sem offload."),
    (6, "acestep-v15-turbo", "acestep-5Hz-lm-0.6B",
     "O runtime do ACE-Step classifica 8GB como tier3 e so libera o LM 0.6B — "
     "o 1.7B seria recusado. CPU offload liga automaticamente abaixo de 16GB."),
    (0, "acestep-v15-turbo", "", "INT8 + offload total para CPU. Lento."),
]


def _gpu_info() -> list[dict]:
    if not shutil.which("nvidia-smi"):
        return []
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        gpus = []
        for line in out.stdout.strip().splitlines():
            name, total, used, driver = [p.strip() for p in line.split(",")]
            gpus.append(
                {
                    "name": name,
                    "total_gb": round(int(total) / 1024, 1),
                    "used_gb": round(int(used) / 1024, 1),
                    "driver": driver,
                }
            )
        return gpus
    except Exception:
        return []


def _recommend(vram_gb: float) -> tuple[str, str, str]:
    for threshold, dit, lm, note in _VRAM_PROFILES:
        if vram_gb >= threshold:
            return dit, lm, note
    return _VRAM_PROFILES[-1][1:]


def render() -> None:
    st.title("Diagnostico")
    settings = state.settings()
    sup = state.supervisor()

    st.subheader("Servidor de inferencia")
    components.health_badge(state.provider().health(), sup)

    problems = sup.preflight()
    if problems:
        st.warning("\n\n".join(f"- {p}" for p in problems), icon=":material/build:")

    ctrl = st.columns(3)
    if ctrl[0].button("Iniciar servidor", use_container_width=True, disabled=bool(problems)):
        result = sup.start(dit_model=settings.dit_model, lm_model=settings.lm_model)
        (st.success if result.running else st.info)(result.detail)
    if ctrl[1].button("Parar servidor", use_container_width=True):
        st.info(sup.stop().detail)
    if ctrl[2].button("Recarregar status", use_container_width=True):
        st.rerun()

    st.divider()
    st.subheader("Hardware")
    gpus = _gpu_info()
    if not gpus:
        st.error(
            "`nvidia-smi` nao encontrado ou sem GPU NVIDIA visivel. "
            "A geracao local depende de CUDA.",
            icon=":material/memory:",
        )
    for gpu in gpus:
        cols = st.columns(4)
        cols[0].metric("GPU", gpu["name"])
        cols[1].metric("VRAM total", f"{gpu['total_gb']} GB")
        cols[2].metric("VRAM em uso", f"{gpu['used_gb']} GB")
        cols[3].metric("Driver", gpu["driver"])

        dit, lm, note = _recommend(gpu["total_gb"])
        st.info(
            f"Perfil recomendado para {gpu['total_gb']} GB: **{dit}**"
            + (f" + **{lm}**" if lm else " (sem LM)")
            + f"\n\n{note}",
            icon=":material/tune:",
        )
        if dit != settings.dit_model:
            st.warning(
                f"O .env aponta para `{settings.dit_model}`. Ajuste `MUSICGEN_DIT_MODEL="
                f"{dit}` e `MUSICGEN_LM_MODEL={lm}` e reinicie o servidor.",
                icon=":material/warning:",
            )

    st.divider()
    st.subheader("Ambiente")
    st.code(
        f"python   : {sys.version.split()[0]}\n"
        f"platform : {platform.platform()}\n"
        f"uv       : {shutil.which('uv') or 'NAO ENCONTRADO'}\n"
        f"ffmpeg   : {shutil.which('ffmpeg') or 'nao encontrado (opcional)'}\n"
        f"demucs   : {'disponivel' if stems_mod.is_available() else 'nao instalado'}\n"
        f"acestep  : {settings.acestep_home or 'nao configurado'}\n"
        f"data dir : {settings.data_dir.resolve()}\n"
        f"database : {settings.db_path.resolve()}",
        language="text",
    )

"""Widgets reutilizaveis da UI."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from musicgen.domain.lyrics import LyricsDocument, Severity
from musicgen.domain.models import AudioTrack, GenerationJob, JobStatus
from musicgen.providers.base import ProviderHealth

_STATUS_STYLE = {
    JobStatus.SUCCEEDED: (":material/check_circle:", "green"),
    JobStatus.FAILED: (":material/error:", "red"),
    JobStatus.RUNNING: (":material/progress_activity:", "blue"),
    JobStatus.QUEUED: (":material/schedule:", "orange"),
    JobStatus.PENDING: (":material/schedule:", "gray"),
    JobStatus.CANCELLED: (":material/cancel:", "gray"),
}


def health_badge(health: ProviderHealth, supervisor=None) -> None:
    """Barra de status do backend de inferencia.

    Args:
        health: resultado de ``provider.health()``.
        supervisor: opcional. Quando passado, a mensagem de offline vira uma
            lista de passos especificos ao estado do ambiente em vez do texto
            generico de conexao recusada.
    """
    if health.available:
        cols = st.columns(4)
        cols[0].metric("Servidor", "online")
        cols[1].metric("Na fila", health.queued)
        cols[2].metric("Executando", health.running)
        cols[3].metric(
            "Tempo medio",
            f"{health.avg_job_seconds:.0f}s" if health.avg_job_seconds else "--",
        )
    else:
        steps = supervisor.diagnose() if supervisor is not None else []
        if steps:
            st.error(
                "**Servidor de inferencia offline.**\n\n"
                + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)),
                icon=":material/cloud_off:",
            )
        else:
            st.error(
                f"Servidor de inferencia offline. {health.detail or ''}\n\n"
                "Inicie pela aba **Diagnostico** ou rode `uv run acestep-api` "
                "na pasta do ACE-Step.",
                icon=":material/cloud_off:",
            )
        if health.detail:
            st.caption(f"Detalhe tecnico: {health.detail}")


def lyrics_diagnostics(doc: LyricsDocument) -> None:
    """Renderiza avisos do parser de letra."""
    if not doc.issues:
        st.success("Letra bem formada.", icon=":material/check:")
        return
    for issue in doc.issues:
        where = f" (linha {issue.line})" if issue.line else ""
        text = f"{issue.message}{where}"
        if issue.severity is Severity.ERROR:
            st.error(text, icon=":material/error:")
        elif issue.severity is Severity.WARNING:
            st.warning(text, icon=":material/warning:")
        else:
            st.info(text, icon=":material/lightbulb:")


def structure_summary(doc: LyricsDocument) -> None:
    if not doc.sections:
        return
    cols = st.columns(3)
    cols[0].metric("Secoes", len(doc.sections))
    cols[1].metric("Palavras", doc.total_words)
    cols[2].metric("Duracao estimada", f"{doc.estimated_duration_s():.0f}s")
    st.caption("  ".join(s.header for s in doc.sections))


def track_player(track: AudioTrack, *, key_prefix: str) -> None:
    """Player + metadados + download de uma faixa."""
    if not track.path.exists():
        st.warning(f"Arquivo ausente: {track.path.name}", icon=":material/link_off:")
        return

    st.audio(str(track.path))
    meta = []
    if track.duration_s:
        meta.append(f"{track.duration_s:.0f}s")
    if track.sample_rate:
        meta.append(f"{track.sample_rate} Hz")
    if track.lufs is not None:
        meta.append(f"{track.lufs:.1f} LUFS")
    if track.seed is not None:
        meta.append(f"seed {track.seed}")
    st.caption(" | ".join(meta) or "sem metadados")

    st.download_button(
        "Baixar",
        data=track.path.read_bytes(),
        file_name=track.path.name,
        mime=f"audio/{track.path.suffix.lstrip('.')}",
        key=f"{key_prefix}_dl",
        use_container_width=True,
    )

    if track.stems:
        with st.expander(f"Stems ({len(track.stems)})"):
            for name, path in track.stems.items():
                st.write(f"**{name}**")
                if Path(path).exists():
                    st.audio(str(path))


def job_header(job: GenerationJob) -> str:
    icon, color = _STATUS_STYLE.get(job.status, (":material/help:", "gray"))
    when = job.created_at.astimezone().strftime("%d/%m %H:%M")
    return f"{icon} :{color}[{job.request.title}]  {when}  {len(job.tracks)} faixa(s)"

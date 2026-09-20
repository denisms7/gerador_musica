"""Biblioteca: historico persistente de geracoes, com filtro e reuso de parametros."""
from __future__ import annotations

import streamlit as st

from musicgen.domain.models import JobStatus
from musicgen.services.prompt_builder import build_caption
from musicgen.ui import components, state


def render() -> None:
    st.title("Biblioteca")

    repo = state.repository()
    filters = st.columns([2, 1, 1])
    status_label = filters[0].selectbox(
        "Status", ["Todos"] + [s.value for s in JobStatus], index=0
    )
    limit = filters[1].number_input("Limite", 5, 500, 50, step=5)
    if filters[2].button("Atualizar", use_container_width=True):
        st.rerun()

    status = None if status_label == "Todos" else JobStatus(status_label)
    jobs = repo.list_recent(limit=int(limit), status=status)

    if not jobs:
        st.info("Nenhuma geracao com esse filtro.", icon=":material/inbox:")
        return

    for job in jobs:
        with st.expander(components.job_header(job)):
            meta, actions = st.columns([3, 1])

            with meta:
                req = job.request
                st.code(
                    f"prompt   : {build_caption(req.style, vocal_language=req.vocal_language)}\n"
                    f"idioma   : {req.vocal_language}\n"
                    f"bpm/tom  : {req.musical.bpm or 'auto'} / {req.musical.key_scale or 'auto'}\n"
                    f"duracao  : {req.musical.duration_s or 'auto'}\n"
                    f"steps/cfg: {req.inference.steps} / {req.inference.guidance_scale}\n"
                    f"seed     : {req.inference.seed if req.inference.seed is not None else 'aleatoria'}",
                    language="text",
                )
                if job.resolved_meta:
                    st.caption(
                        "Decidido pelo modelo: "
                        + " | ".join(f"{k}={v}" for k, v in job.resolved_meta.items() if v)
                    )
                if job.error:
                    st.error(job.error, icon=":material/error:")
                with st.popover("Ver letra"):
                    st.text(job.request.lyrics or "(instrumental)")

            with actions:
                if st.button("Reusar parametros", key=f"reuse_{job.id}", use_container_width=True):
                    st.session_state["lyrics_text"] = job.request.lyrics
                    st.success("Letra carregada. Va em **Gerar musica**.")
                if st.button(
                    "Excluir", key=f"del_{job.id}", use_container_width=True, type="secondary"
                ):
                    repo.delete(job.id, remove_files=True)
                    st.rerun()

            if job.tracks:
                st.divider()
                cols = st.columns(min(len(job.tracks), 3))
                for i, track in enumerate(job.tracks):
                    with cols[i % len(cols)]:
                        st.markdown(f"**Take {i + 1}**")
                        components.track_player(track, key_prefix=f"lib_{job.id}_{i}")

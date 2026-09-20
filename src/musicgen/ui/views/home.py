"""Visao geral: status do backend, metricas da biblioteca e atalhos."""
from __future__ import annotations

import streamlit as st

from musicgen.ui import components, state


def render() -> None:
    st.title("MusicGen Local")
    st.caption(
        "Geracao de musica completa (voz + instrumental) a partir da sua letra, "
        "100% na sua maquina, via ACE-Step 1.5."
    )

    components.health_badge(state.provider().health(), state.supervisor())

    st.divider()
    stats = state.repository().stats()
    cols = st.columns(5)
    cols[0].metric("Geracoes", stats["jobs_total"])
    cols[1].metric("Concluidas", stats["jobs_ok"])
    cols[2].metric("Falhas", stats["jobs_fail"])
    cols[3].metric("Faixas", stats["tracks"])
    cols[4].metric("Audio gerado", f"{stats['audio_minutes']} min")

    st.divider()
    left, right = st.columns([2, 1])

    with left:
        st.subheader("Ultimas geracoes")
        jobs = state.repository().list_recent(limit=5)
        if not jobs:
            st.info(
                "Nenhuma geracao ainda. Va em **Gerar musica**, cole sua letra e escolha um estilo.",
                icon=":material/rocket_launch:",
            )
        for job in jobs:
            with st.expander(components.job_header(job)):
                if job.error:
                    st.error(job.error)
                for i, track in enumerate(job.tracks):
                    components.track_player(track, key_prefix=f"home_{job.id}_{i}")

    with right:
        st.subheader("Fluxo")
        st.markdown(
            """
1. **Escreva a letra** com tags de estrutura: `[Verse]`, `[Chorus]`, `[Bridge]`.
2. **Escolha o estilo** — preset pronto ou descricao livre em ingles.
3. **Gere**: o modelo decide melodia, harmonia, arranjo e canta a letra.
4. **Itere** pela seed: mesma letra + seed diferente = outra interpretacao.
            """
        )
        s = state.settings()
        st.subheader("Configuracao ativa")
        st.code(
            f"DiT : {s.dit_model}\n"
            f"LM  : {s.lm_model}\n"
            f"API : {s.acestep_base_url}\n"
            f"Fmt : {s.audio_format}  |  LUFS alvo: {s.target_lufs}\n"
            f"Stems: {'on' if s.enable_stems else 'off'}",
            language="text",
        )

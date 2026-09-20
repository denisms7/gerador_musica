"""Tela principal de geracao: letra + estilo + parametros -> audio."""
from __future__ import annotations

import random

import streamlit as st

from musicgen.domain import lyrics as lyrics_mod
from musicgen.domain.models import (
    GenerationRequest,
    InferenceSpec,
    MusicalSpec,
    StyleSpec,
    VocalGender,
)
from musicgen.services.prompt_builder import LANGUAGES, STYLE_PRESETS, build_caption, suggest_bpm
from musicgen.ui import components, state

_TEMPLATE = """[Intro]

[Verse 1]
escreva aqui a primeira estrofe

[Pre-Chorus]

[Chorus]
o gancho que se repete

[Verse 2]

[Chorus]

[Bridge]

[Outro]
"""

_KEYS = [
    "",
    "C major", "A minor", "G major", "E minor", "D major", "B minor",
    "A major", "F# minor", "E major", "C# minor", "F major", "D minor",
    "Bb major", "G minor", "Eb major", "C minor",
]

_VOCAL_LABELS = {
    VocalGender.UNSET: "Deixar o modelo decidir",
    VocalGender.FEMALE: "Feminino",
    VocalGender.MALE: "Masculino",
    VocalGender.DUET: "Dueto",
    VocalGender.CHOIR: "Coral",
}


def _style_from_form(preset_name: str, custom_text: str, vocal: VocalGender) -> StyleSpec:
    """Preset como base; texto livre sobrescreve; vocal sempre do formulario."""
    if custom_text.strip():
        return StyleSpec(free_text=custom_text.strip(), vocal_gender=vocal)
    base = STYLE_PRESETS.get(preset_name)
    if base is None:
        return StyleSpec(vocal_gender=vocal)
    return StyleSpec(
        genres=list(base.genres),
        moods=list(base.moods),
        instruments=list(base.instruments),
        vocal_gender=vocal if vocal is not VocalGender.UNSET else base.vocal_gender,
        vocal_traits=list(base.vocal_traits),
        production=list(base.production),
        era=base.era,
    )


def render() -> None:
    st.title("Gerar musica")
    settings = state.settings()
    provider = state.provider()

    health = provider.health()
    if not health.available:
        components.health_badge(health, state.supervisor())
        st.stop()

    editor, panel = st.columns([3, 2], gap="large")

    # ------------------------------------------------------------------ letra
    with editor:
        st.subheader("Letra")
        title = st.text_input("Titulo", value="Nova musica", max_chars=120)
        instrumental = st.toggle(
            "Apenas instrumental (sem vocal)",
            value=False,
            help="Ignora a letra e gera somente a base.",
        )

        if st.button("Inserir estrutura modelo", use_container_width=False):
            st.session_state["lyrics_text"] = _TEMPLATE

        lyrics_text = st.text_area(
            "Cole sua letra",
            key="lyrics_text",
            height=420,
            placeholder=_TEMPLATE,
            disabled=instrumental,
            help="Use tags entre colchetes para controlar a forma: [Verse], [Chorus], [Bridge]...",
        )

        doc = lyrics_mod.parse(lyrics_text) if lyrics_text.strip() else None
        if doc and not instrumental:
            components.structure_summary(doc)
            with st.expander("Diagnostico da letra", expanded=doc.has_errors):
                components.lyrics_diagnostics(doc)

    # --------------------------------------------------------------- controles
    with panel:
        st.subheader("Estilo")
        preset = st.selectbox("Preset", ["(personalizado)", *STYLE_PRESETS])
        custom = st.text_area(
            "Descricao livre (em ingles, sobrescreve o preset)",
            height=90,
            placeholder="sad piano ballad with female breathy vocal, warm analog tape, sparse arrangement",
            help="Especifico bate generico. Combine genero + emocao + instrumentos + producao.",
        )
        vocal = st.selectbox(
            "Vocal",
            list(_VOCAL_LABELS),
            format_func=lambda v: _VOCAL_LABELS[v],
            disabled=instrumental,
        )
        language_label = st.selectbox("Idioma do vocal", list(LANGUAGES), disabled=instrumental)

        style = _style_from_form(preset, custom, vocal)
        st.caption("Prompt enviado ao modelo:")
        st.code(build_caption(style, vocal_language=LANGUAGES[language_label]), language="text")

        st.subheader("Parametros musicais")
        auto_bpm = st.toggle("BPM automatico", value=True)
        bpm = None
        if not auto_bpm:
            bpm = st.slider("BPM", 40, 220, suggest_bpm(style) or 100)
        key_scale = st.selectbox("Tom", _KEYS, format_func=lambda k: k or "automatico")
        time_sig = st.selectbox("Compasso", ["", "4/4", "3/4", "6/8", "2/4"],
                                format_func=lambda t: t or "automatico")

        auto_dur = st.toggle(
            "Duracao automatica",
            value=True,
            help="Estimada a partir da densidade da letra.",
        )
        duration = None
        if not auto_dur:
            default = int(doc.estimated_duration_s()) if doc else 180
            duration = float(st.slider("Duracao (s)", 10, 600, min(600, max(10, default))))

        with st.expander("Inferencia (avancado)"):
            is_turbo = "turbo" in settings.dit_model
            steps = st.slider(
                "Passos de difusao",
                1, 100,
                settings.default_steps if is_turbo else 50,
                help="Modelos turbo: 8 passos bastam. Modelos sft/base: 50.",
            )
            guidance = st.slider(
                "Guidance (CFG)", 1.0, 15.0, settings.default_guidance, 0.5,
                disabled=is_turbo,
                help="Ignorado em modelos turbo.",
            )
            batch = st.slider(
                "Variacoes por geracao", 1, 4, settings.default_batch,
                help="Gera N takes da mesma letra. Custa VRAM e tempo proporcionalmente.",
            )
            thinking = st.toggle(
                "Modo thinking (LM decide metadados)", value=True,
                help="O modelo de linguagem infere BPM, tom e fraseado a partir da letra.",
            )
            use_seed = st.toggle("Fixar seed (reprodutibilidade)", value=False)
            seed = st.number_input("Seed", 0, 2**31 - 1, random.randint(0, 2**31 - 1),
                                   disabled=not use_seed)

        st.divider()
        go = st.button(
            "Gerar musica",
            type="primary",
            use_container_width=True,
            disabled=not instrumental and not lyrics_text.strip(),
        )

    # --------------------------------------------------------------- execucao
    if not go:
        return

    try:
        request = GenerationRequest(
            lyrics=lyrics_text,
            style=style,
            musical=MusicalSpec(
                bpm=bpm,
                key_scale=key_scale or None,
                time_signature=time_sig or None,
                duration_s=duration,
            ),
            inference=InferenceSpec(
                steps=steps,
                guidance_scale=guidance,
                shift=3.0 if "turbo" in settings.dit_model else 1.0,
                seed=int(seed) if use_seed else None,
                batch_size=batch,
                thinking=thinking,
            ),
            title=title or "Sem titulo",
            vocal_language=LANGUAGES[language_label],
            instrumental=instrumental,
            audio_format=settings.audio_format,
        )
    except ValueError as exc:
        st.error(f"Requisicao invalida: {exc}", icon=":material/error:")
        return

    st.divider()
    st.subheader("Resultado")
    progress = st.progress(0.0)
    with st.status("Gerando...", expanded=True) as status:
        final_job = None
        for event in state.service().run(request):
            progress.progress(min(1.0, event.fraction))
            status.write(event.detail)
            final_job = event.job
            if event.stage == "failed":
                status.update(label="Falhou", state="error")
                st.error(event.detail, icon=":material/error:")
                return
        status.update(label="Concluido", state="complete")

    if final_job and final_job.tracks:
        if final_job.resolved_meta:
            st.caption(
                " | ".join(f"{k}: {v}" for k, v in final_job.resolved_meta.items() if v)
            )
        cols = st.columns(min(len(final_job.tracks), 2))
        for i, track in enumerate(final_job.tracks):
            with cols[i % len(cols)]:
                st.markdown(f"**Take {i + 1}**")
                components.track_player(track, key_prefix=f"gen_{final_job.id}_{i}")

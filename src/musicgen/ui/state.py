"""Dependencias compartilhadas da UI, cacheadas entre reruns do Streamlit.

``st.cache_resource`` garante que conexao SQLite, provider e supervisor sejam
instanciados uma unica vez por sessao do servidor.
"""
from __future__ import annotations

import streamlit as st

from musicgen.config import Settings, get_settings
from musicgen.persistence.repository import JobRepository
from musicgen.providers.base import MusicProvider
from musicgen.providers.registry import get_provider
from musicgen.server.supervisor import AceStepSupervisor
from musicgen.services.generation import GenerationService


@st.cache_resource(show_spinner=False)
def settings() -> Settings:
    return get_settings()


@st.cache_resource(show_spinner=False)
def repository() -> JobRepository:
    return JobRepository(settings().db_path)


@st.cache_resource(show_spinner=False)
def provider() -> MusicProvider:
    return get_provider(settings=settings())


@st.cache_resource(show_spinner=False)
def supervisor() -> AceStepSupervisor:
    s = settings()
    return AceStepSupervisor(s.acestep_home, s.acestep_base_url)


def service() -> GenerationService:
    """Service e barato de construir; recriado a cada rerun para refletir config nova."""
    return GenerationService(settings=settings(), provider=provider(), repository=repository())

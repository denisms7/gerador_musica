"""Resolucao de provider por nome. Ponto unico de extensao."""
from __future__ import annotations

from collections.abc import Callable

from musicgen.config import Settings, get_settings
from musicgen.providers.acestep_api import AceStepApiProvider
from musicgen.providers.base import MusicProvider

_FACTORIES: dict[str, Callable[[Settings], MusicProvider]] = {
    "acestep-api": lambda s: AceStepApiProvider(
        s.acestep_base_url, dit_model=s.dit_model, api_key=s.acestep_api_key
    ),
}


def register(name: str, factory: Callable[[Settings], MusicProvider]) -> None:
    """Registra um provider adicional (util para testes e backends futuros)."""
    _FACTORIES[name] = factory


def available_providers() -> list[str]:
    return sorted(_FACTORIES)


def get_provider(name: str | None = None, settings: Settings | None = None) -> MusicProvider:
    settings = settings or get_settings()
    name = name or "acestep-api"
    try:
        return _FACTORIES[name](settings)
    except KeyError as exc:
        raise ValueError(
            f"Provider '{name}' desconhecido. Disponiveis: {available_providers()}"
        ) from exc

"""Configuracao central da aplicacao (12-factor, via env / .env)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracao imutavel carregada de variaveis de ambiente.

    Todas as chaves usam o prefixo ``MUSICGEN_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="MUSICGEN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- Backend de inferencia ------------------------------------------------
    acestep_base_url: str = "http://127.0.0.1:8001"
    acestep_home: Path | None = None
    acestep_api_key: str | None = None
    dit_model: str = "acestep-v15-turbo"
    lm_model: str = "acestep-5Hz-lm-1.7B"

    # -- Geracao --------------------------------------------------------------
    default_steps: int = Field(default=8, ge=1, le=200)
    default_guidance: float = Field(default=7.0, ge=1.0, le=20.0)
    default_batch: int = Field(default=2, ge=1, le=8)
    audio_format: str = "wav"
    job_timeout_s: int = Field(default=1800, ge=30)
    poll_interval_s: float = Field(default=3.0, ge=0.05)

    # -- Pos-processamento ----------------------------------------------------
    target_lufs: float = -14.0
    enable_loudness: bool = True
    enable_stems: bool = False
    demucs_model: str = "htdemucs"

    # -- Armazenamento --------------------------------------------------------
    data_dir: Path = Path("./data")
    db_path: Path = Path("./data/musicgen.db")

    @field_validator("audio_format")
    @classmethod
    def _valid_format(cls, v: str) -> str:
        allowed = {"wav", "wav32", "flac", "mp3", "opus", "aac"}
        if v not in allowed:
            raise ValueError(f"audio_format deve ser um de {sorted(allowed)}")
        return v

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def stems_dir(self) -> Path:
        return self.data_dir / "stems"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.outputs_dir, self.stems_dir, self.cache_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton de configuracao. Cacheado para evitar releitura a cada rerun do Streamlit."""
    settings = Settings()
    settings.ensure_dirs()
    return settings

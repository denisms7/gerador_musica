"""Modelos de dominio. Nenhuma dependencia de framework ou de provider."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class JobStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}


class VocalGender(str, Enum):
    UNSET = "unset"
    FEMALE = "female"
    MALE = "male"
    DUET = "duet"
    CHOIR = "choir"


class TaskType(str, Enum):
    TEXT2MUSIC = "text2music"
    COVER = "cover"
    REPAINT = "repaint"
    EXTRACT = "extract"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


@dataclass(slots=True)
class StyleSpec:
    """Descricao de estilo musical. Convertida em ``caption`` pelo PromptBuilder."""

    genres: list[str] = field(default_factory=list)
    moods: list[str] = field(default_factory=list)
    instruments: list[str] = field(default_factory=list)
    vocal_gender: VocalGender = VocalGender.UNSET
    vocal_traits: list[str] = field(default_factory=list)
    production: list[str] = field(default_factory=list)
    era: str | None = None
    free_text: str | None = None

    def is_empty(self) -> bool:
        return not any(
            [
                self.genres,
                self.moods,
                self.instruments,
                self.vocal_traits,
                self.production,
                self.era,
                self.free_text,
            ]
        )


@dataclass(slots=True)
class MusicalSpec:
    """Parametros musicais explicitos. ``None`` delega a decisao ao modelo."""

    bpm: int | None = None
    key_scale: str | None = None
    time_signature: str | None = None
    duration_s: float | None = None

    def __post_init__(self) -> None:
        if self.bpm is not None and not 30 <= self.bpm <= 300:
            raise ValueError("bpm deve estar entre 30 e 300")
        if self.duration_s is not None and not 10 <= self.duration_s <= 600:
            raise ValueError("duracao deve estar entre 10 e 600 segundos")


@dataclass(slots=True)
class InferenceSpec:
    """Parametros de amostragem do modelo de difusao."""

    steps: int = 8
    guidance_scale: float = 7.0
    shift: float = 1.0
    seed: int | None = None
    batch_size: int = 2
    thinking: bool = True

    def __post_init__(self) -> None:
        if not 1 <= self.steps <= 200:
            raise ValueError("steps deve estar entre 1 e 200")
        if not 1 <= self.batch_size <= 8:
            raise ValueError("batch_size deve estar entre 1 e 8")


@dataclass(slots=True)
class GenerationRequest:
    """Requisicao completa e auto-contida de geracao."""

    lyrics: str
    style: StyleSpec = field(default_factory=StyleSpec)
    musical: MusicalSpec = field(default_factory=MusicalSpec)
    inference: InferenceSpec = field(default_factory=InferenceSpec)
    title: str = "Sem titulo"
    vocal_language: str = "portuguese"
    instrumental: bool = False
    task_type: TaskType = TaskType.TEXT2MUSIC
    audio_format: str = "wav"

    def __post_init__(self) -> None:
        if not self.instrumental and not self.lyrics.strip():
            raise ValueError("letra vazia para geracao com vocal")


@dataclass(slots=True)
class AudioTrack:
    """Uma faixa de audio gerada."""

    path: Path
    sample_rate: int | None = None
    duration_s: float | None = None
    lufs: float | None = None
    seed: int | None = None
    stems: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class GenerationJob:
    """Unidade de trabalho rastreavel, persistida em SQLite."""

    request: GenerationRequest
    id: str = field(default_factory=_new_id)
    provider: str = "acestep-api"
    remote_id: str | None = None
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    tracks: list[AudioTrack] = field(default_factory=list)
    resolved_meta: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    queue_position: int | None = None

    def mark(self, status: JobStatus, *, error: str | None = None) -> None:
        self.status = status
        self.error = error
        self.updated_at = _utcnow()

    @property
    def elapsed_s(self) -> float:
        return (_utcnow() - self.created_at).total_seconds()

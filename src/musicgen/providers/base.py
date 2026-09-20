"""Contrato de provider de geracao musical.

Toda a aplicacao depende apenas desta interface. Trocar ACE-Step por outro
backend (DiffRhythm, YuE, ou uma API remota) significa escrever uma nova
implementacao, sem tocar em servicos nem UI.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from musicgen.domain.models import GenerationJob, GenerationRequest, JobStatus


class ProviderError(RuntimeError):
    """Falha recuperavel do backend (rede, fila cheia, modelo indisponivel)."""


class ProviderUnavailable(ProviderError):
    """O backend nao esta acessivel (processo caido / porta fechada)."""


@dataclass(slots=True)
class ProviderHealth:
    available: bool
    version: str | None = None
    models: list[str] = None  # type: ignore[assignment]
    queued: int = 0
    running: int = 0
    avg_job_seconds: float | None = None
    detail: str | None = None
    #: Modelo que o servidor reporta como default. E o que esta REALMENTE
    #: carregado, que pode divergir do .env se o backend nao foi reiniciado.
    active_model: str | None = None

    def __post_init__(self) -> None:
        if self.models is None:
            self.models = []


class MusicProvider(ABC):
    """Backend capaz de transformar letra + estilo em audio."""

    name: str = "abstract"

    @abstractmethod
    def health(self) -> ProviderHealth:
        """Estado do backend. Nunca levanta excecao: reporta em ``available``."""

    @abstractmethod
    def submit(self, request: GenerationRequest) -> str:
        """Enfileira a geracao e devolve o id remoto da tarefa."""

    @abstractmethod
    def poll(self, remote_id: str) -> tuple[JobStatus, dict]:
        """Consulta o estado. Devolve (status, payload bruto do backend)."""

    @abstractmethod
    def fetch_artifacts(self, payload: dict, dest_dir: Path) -> list[Path]:
        """Baixa/copia os arquivos de audio do resultado para ``dest_dir``."""

    def wait(
        self,
        job: GenerationJob,
        *,
        poll_interval_s: float,
        timeout_s: int,
    ) -> Iterator[GenerationJob]:
        """Gerador que emite o job a cada polling ate estado terminal.

        Implementacao default serve qualquer provider assincrono. A UI consome
        este iterador para atualizar a barra de progresso sem bloquear.
        """
        import time

        assert job.remote_id, "job sem remote_id: chame submit() antes"
        deadline = time.monotonic() + timeout_s
        while True:
            status, payload = self.poll(job.remote_id)
            job.status = status
            if isinstance(payload, Mapping):
                job.resolved_meta = payload.get("metas") or job.resolved_meta
                if status is JobStatus.FAILED:
                    job.error = "; ".join(payload.get("errors") or []) or job.error
            yield job
            if status.terminal:
                return
            if time.monotonic() > deadline:
                job.mark(JobStatus.FAILED, error=f"timeout apos {timeout_s}s")
                yield job
                return
            time.sleep(poll_interval_s)

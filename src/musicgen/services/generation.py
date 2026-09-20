"""Orquestracao da geracao: validacao -> provider -> pos-processamento -> persistencia.

Este e o unico lugar que conhece o fluxo completo. A UI apenas consome o
iterador de progresso; o provider apenas fala com o backend.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from musicgen.config import Settings, get_settings
from musicgen.domain import lyrics as lyrics_mod
from musicgen.domain.models import (
    AudioTrack,
    GenerationJob,
    GenerationRequest,
    JobStatus,
)
from musicgen.persistence.repository import JobRepository
from musicgen.providers.base import MusicProvider, ProviderError
from musicgen.providers.registry import get_provider
from musicgen.services import postprocess
from musicgen.services import stems as stems_mod

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Progress:
    """Evento de progresso consumido pela UI."""

    job: GenerationJob
    stage: str
    detail: str = ""
    fraction: float = 0.0


class GenerationService:
    """Fachada de aplicacao. Sem estado alem das dependencias injetadas."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        provider: MusicProvider | None = None,
        repository: JobRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = provider or get_provider(settings=self.settings)
        self.repo = repository or JobRepository(self.settings.db_path)

    # -- validacao ------------------------------------------------------------

    def validate(self, request: GenerationRequest) -> lyrics_mod.LyricsDocument:
        """Normaliza a letra e devolve o documento com diagnosticos.

        Efeito colateral deliberado: ``request.lyrics`` passa a conter a versao
        normalizada, que e o que sera enviado ao modelo.
        """
        if request.instrumental:
            return lyrics_mod.LyricsDocument(sections=[], issues=[])
        doc = lyrics_mod.parse(request.lyrics)
        if doc.has_errors:
            raise ValueError("; ".join(i.message for i in doc.issues if i.severity.value == "error"))
        request.lyrics = doc.render()
        if request.musical.duration_s is None:
            request.musical.duration_s = min(600.0, doc.estimated_duration_s())
        return doc

    # -- execucao -------------------------------------------------------------

    def run(self, request: GenerationRequest) -> Iterator[Progress]:
        """Executa a geracao completa, emitindo progresso a cada etapa.

        O consumo preguicoso permite que a UI renderize status sem threads
        adicionais: cada ``next()`` avanca uma etapa do pipeline.
        """
        self.validate(request)
        job = GenerationJob(request=request, provider=self.provider.name)
        self.repo.save(job)

        yield Progress(job, "submit", "Enfileirando no servidor de inferencia...", 0.02)
        try:
            job.remote_id = self.provider.submit(request)
            job.mark(JobStatus.QUEUED)
        except ProviderError as exc:
            job.mark(JobStatus.FAILED, error=str(exc))
            self.repo.save(job)
            yield Progress(job, "failed", str(exc), 1.0)
            return
        self.repo.save(job)

        payload: dict = {}
        try:
            for _ in self.provider.wait(
                job,
                poll_interval_s=self.settings.poll_interval_s,
                timeout_s=self.settings.job_timeout_s,
            ):
                if job.status is JobStatus.SUCCEEDED:
                    _, payload = self.provider.poll(job.remote_id)  # type: ignore[arg-type]
                    break
                if job.status is JobStatus.FAILED:
                    break
                yield Progress(
                    job,
                    "generating",
                    f"Gerando audio ({job.elapsed_s:.0f}s decorridos)...",
                    min(0.75, 0.05 + job.elapsed_s / max(self.settings.job_timeout_s, 1) * 3),
                )
        except ProviderError as exc:
            job.mark(JobStatus.FAILED, error=str(exc))
            self.repo.save(job)
            yield Progress(job, "failed", str(exc), 1.0)
            return

        if job.status is not JobStatus.SUCCEEDED:
            explained = explain_failure(job.error, request)
            job.mark(JobStatus.FAILED, error=explained)
            self.repo.save(job)
            yield Progress(job, "failed", explained, 1.0)
            return

        yield Progress(job, "download", "Baixando faixas geradas...", 0.8)
        dest = self.settings.outputs_dir / job.id
        try:
            paths = self.provider.fetch_artifacts(payload, dest)
        except Exception as exc:
            job.mark(JobStatus.FAILED, error=f"falha ao baixar audio: {exc}")
            self.repo.save(job)
            yield Progress(job, "failed", str(exc), 1.0)
            return

        job.resolved_meta = payload.get("metas") or {}
        seeds = payload.get("seeds") or []

        yield Progress(job, "postprocess", "Normalizando loudness...", 0.88)
        job.tracks = [
            self._finalize_track(p, seeds[i] if i < len(seeds) else None)
            for i, p in enumerate(paths)
        ]

        if self.settings.enable_stems:
            yield Progress(job, "stems", "Separando stems (Demucs)...", 0.94)
            self._attach_stems(job)

        job.mark(JobStatus.SUCCEEDED)
        self.repo.save(job)
        yield Progress(job, "done", f"{len(job.tracks)} faixa(s) prontas.", 1.0)

    # -- etapas internas ------------------------------------------------------

    def _finalize_track(self, path: Path, seed: int | None) -> AudioTrack:
        if self.settings.enable_loudness:
            try:
                postprocess.normalize_loudness(path, target_lufs=self.settings.target_lufs)
                postprocess.apply_fades(path)
            except Exception as exc:
                logger.warning("pos-processamento falhou em %s: %s", path.name, exc)
        try:
            metrics = postprocess.analyze(path)
        except Exception as exc:
            logger.warning("analise falhou em %s: %s", path.name, exc)
            metrics = {}
        return AudioTrack(
            path=path,
            sample_rate=metrics.get("sample_rate"),
            duration_s=metrics.get("duration_s"),
            lufs=metrics.get("lufs"),
            seed=seed,
        )

    def _attach_stems(self, job: GenerationJob) -> None:
        for track in job.tracks:
            try:
                track.stems = stems_mod.separate(
                    track.path,
                    self.settings.stems_dir / job.id / track.path.stem,
                    model=self.settings.demucs_model,
                )
            except Exception as exc:
                logger.warning("stems falharam em %s: %s", track.path.name, exc)


#: Trechos que o ACE-Step emite quando a geracao nao cabe na VRAM. A excecao
#: costuma chegar SEM mensagem, entao a heuristica olha tambem para o vazio.
_CAPACITY_MARKERS = (
    "codes generation",
    "out of memory",
    "cuda error",
    "allocate",
    "cublas",
)


def explain_failure(error: str | None, request: GenerationRequest) -> str:
    """Traduz a falha do backend em algo acionavel.

    O ACE-Step re-lança erros de capacidade com mensagem vazia
    (``Error in batch codes generation:``), entao repassar o texto cru deixa o
    usuario sem saida. Aqui o texto original e preservado e acompanhado das
    alavancas que realmente reduzem o consumo de VRAM, na ordem em que valem a
    pena mexer.
    """
    raw = (error or "").strip()
    lowered = raw.lower()
    capacity = not raw or any(marker in lowered for marker in _CAPACITY_MARKERS)

    if not capacity:
        return raw

    hints: list[str] = [
        "A geracao falhou na fase de audio codes — tipicamente falta de VRAM.",
    ]
    if request.inference.batch_size > 1:
        hints.append(
            f"Reduza as variacoes de {request.inference.batch_size} para 1 "
            "(cada take multiplica o consumo)."
        )
    duration = request.musical.duration_s
    if duration and duration > 180:
        hints.append(
            f"Reduza a duracao de {duration:.0f}s para ~150s: o custo cresce com o "
            "comprimento da musica. Gere por partes e monte depois."
        )
    if request.inference.thinking:
        hints.append("Desligue o modo thinking: o CoT adiciona tokens ao contexto do LM.")
    hints.append(
        "Confirme na aba Diagnostico que o LM em uso e o recomendado para a sua VRAM "
        "— um LM maior que o suportado falha exatamente nesta fase."
    )
    if raw:
        hints.append(f"Mensagem do backend: {raw}")
    return " ".join(f"{i}. {h}" if i else h for i, h in enumerate(hints))

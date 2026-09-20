"""Teste de integracao do pipeline usando um provider em memoria."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from musicgen.config import Settings
from musicgen.domain.models import GenerationRequest, JobStatus, StyleSpec
from musicgen.persistence.repository import JobRepository
from musicgen.providers.base import MusicProvider, ProviderError, ProviderHealth


class FakeProvider(MusicProvider):
    """Provider deterministico: devolve sucesso apos N polls e grava um WAV real."""

    name = "fake"

    def __init__(self, *, polls_until_done: int = 1, fail: bool = False) -> None:
        self.polls_until_done = polls_until_done
        self.fail = fail
        self._calls = 0
        self.submitted: GenerationRequest | None = None

    def health(self) -> ProviderHealth:
        return ProviderHealth(available=True, version="fake")

    def submit(self, request: GenerationRequest) -> str:
        if self.fail:
            raise ProviderError("backend recusou")
        self.submitted = request
        return "task-1"

    def poll(self, remote_id: str):
        self._calls += 1
        if self._calls < self.polls_until_done:
            return JobStatus.RUNNING, {}
        return JobStatus.SUCCEEDED, {
            "files": ["/v1/audio?path=/tmp/fake.wav"],
            "metas": {"bpm": 96, "keyscale": "A minor"},
            "seeds": [123, 456],
        }

    def fetch_artifacts(self, payload: dict, dest_dir: Path) -> list[Path]:
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / "take_1.wav"
        sr = 44100
        tone = 0.2 * np.sin(2 * np.pi * 220 * np.arange(sr * 2) / sr)
        sf.write(str(out), np.column_stack([tone, tone]), sr)
        return [out]


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    s = Settings(
        data_dir=tmp_path / "data",
        db_path=tmp_path / "data" / "db.sqlite",
        poll_interval_s=0.05,
        job_timeout_s=30,
        enable_stems=False,
    )
    s.ensure_dirs()
    return s


def _service(settings: Settings, provider: MusicProvider):
    from musicgen.services.generation import GenerationService

    return GenerationService(
        settings=settings, provider=provider, repository=JobRepository(settings.db_path)
    )


def _request() -> GenerationRequest:
    return GenerationRequest(
        lyrics="[Verse 1]\numa linha\n\n[Chorus]\no gancho",
        style=StyleSpec(genres=["samba"]),
        title="teste",
    )


def test_happy_path_produces_normalized_track(settings: Settings):
    provider = FakeProvider(polls_until_done=2)
    events = list(_service(settings, provider).run(_request()))

    assert events[-1].stage == "done"
    job = events[-1].job
    assert job.status is JobStatus.SUCCEEDED
    assert len(job.tracks) == 1
    track = job.tracks[0]
    assert track.path.exists()
    assert track.duration_s == pytest.approx(2.0, abs=0.1)
    assert track.lufs is not None and -20 < track.lufs < -8
    assert track.seed == 123
    assert job.resolved_meta["bpm"] == 96


def test_lyrics_are_normalized_before_submit(settings: Settings):
    provider = FakeProvider()
    list(_service(settings, provider).run(_request()))
    assert provider.submitted is not None
    assert provider.submitted.lyrics.startswith("[Verse 1]")
    # duracao foi inferida da densidade da letra
    assert provider.submitted.musical.duration_s is not None


def test_provider_failure_is_persisted(settings: Settings):
    service = _service(settings, FakeProvider(fail=True))
    events = list(service.run(_request()))

    assert events[-1].stage == "failed"
    job = events[-1].job
    assert job.status is JobStatus.FAILED
    stored = service.repo.get(job.id)
    assert stored is not None and stored.status is JobStatus.FAILED
    assert "recusou" in stored.error


def test_job_is_persisted_and_listable(settings: Settings):
    service = _service(settings, FakeProvider())
    list(service.run(_request()))
    recent = service.repo.list_recent(limit=5)
    assert len(recent) == 1
    assert recent[0].request.title == "teste"
    assert recent[0].tracks[0].path.exists()


def test_validate_rejects_empty_lyrics(settings: Settings):
    service = _service(settings, FakeProvider())
    request = _request()
    request.lyrics = "   "
    with pytest.raises(ValueError):
        service.validate(request)


def test_progress_fractions_are_monotonic(settings: Settings):
    events = list(_service(settings, FakeProvider(polls_until_done=3)).run(_request()))
    fractions = [e.fraction for e in events]
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0


class TestFailureExplanation:
    """O ACE-Step relanca erro de capacidade com mensagem vazia; repassar o texto
    cru deixaria o usuario sem acao possivel."""

    @staticmethod
    def _req(batch=1, duration=None, thinking=False):
        from musicgen.domain.models import InferenceSpec, MusicalSpec

        return GenerationRequest(
            lyrics="[Chorus]\nhook",
            musical=MusicalSpec(duration_s=duration),
            inference=InferenceSpec(batch_size=batch, thinking=thinking),
        )

    def test_empty_error_is_treated_as_capacity_problem(self):
        from musicgen.services.generation import explain_failure

        assert "VRAM" in explain_failure("", self._req())
        assert "VRAM" in explain_failure(None, self._req())

    def test_codes_generation_error_is_recognized(self):
        from musicgen.services.generation import explain_failure

        out = explain_failure("Error in batch codes generation: ", self._req())
        assert "audio codes" in out

    def test_batch_hint_only_when_batch_above_one(self):
        from musicgen.services.generation import explain_failure

        assert "variacoes" in explain_failure("", self._req(batch=2))
        assert "variacoes" not in explain_failure("", self._req(batch=1))

    def test_duration_hint_only_for_long_songs(self):
        from musicgen.services.generation import explain_failure

        assert "duracao" in explain_failure("", self._req(duration=281))
        assert "duracao" not in explain_failure("", self._req(duration=120))

    def test_thinking_hint_only_when_enabled(self):
        from musicgen.services.generation import explain_failure

        assert "thinking" in explain_failure("", self._req(thinking=True))
        assert "thinking" not in explain_failure("", self._req(thinking=False))

    def test_lm_profile_hint_is_always_present_for_capacity(self):
        from musicgen.services.generation import explain_failure

        assert "LM" in explain_failure("", self._req())

    def test_original_message_is_preserved(self):
        from musicgen.services.generation import explain_failure

        assert "cublas boom" in explain_failure("cublas boom", self._req())

    def test_unrelated_error_passes_through_untouched(self):
        from musicgen.services.generation import explain_failure

        assert explain_failure("letra invalida", self._req()) == "letra invalida"

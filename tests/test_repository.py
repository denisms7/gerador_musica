from pathlib import Path

import pytest

from musicgen.domain.models import (
    AudioTrack,
    GenerationJob,
    GenerationRequest,
    JobStatus,
    MusicalSpec,
    StyleSpec,
    VocalGender,
)
from musicgen.persistence.repository import JobRepository


@pytest.fixture()
def repo(tmp_path: Path) -> JobRepository:
    return JobRepository(tmp_path / "test.db")


def _job(title: str = "t") -> GenerationJob:
    return GenerationJob(
        request=GenerationRequest(
            lyrics="[Chorus]\nhook",
            style=StyleSpec(genres=["samba"], vocal_gender=VocalGender.MALE),
            musical=MusicalSpec(bpm=100),
            title=title,
        )
    )


def test_save_and_get_roundtrip(repo: JobRepository):
    job = _job("minha musica")
    job.tracks = [AudioTrack(path=Path("/tmp/a.wav"), duration_s=12.5, lufs=-14.0, seed=42)]
    job.mark(JobStatus.SUCCEEDED)
    repo.save(job)

    loaded = repo.get(job.id)
    assert loaded is not None
    assert loaded.request.title == "minha musica"
    assert loaded.request.style.vocal_gender is VocalGender.MALE
    assert loaded.request.musical.bpm == 100
    assert loaded.status is JobStatus.SUCCEEDED
    assert loaded.tracks[0].seed == 42


def test_save_is_idempotent_upsert(repo: JobRepository):
    job = _job()
    job.tracks = [AudioTrack(path=Path("/tmp/a.wav"))]
    repo.save(job)
    repo.save(job)
    assert len(repo.get(job.id).tracks) == 1


def test_list_recent_filters_by_status(repo: JobRepository):
    ok, bad = _job("ok"), _job("bad")
    ok.mark(JobStatus.SUCCEEDED)
    bad.mark(JobStatus.FAILED, error="boom")
    repo.save(ok)
    repo.save(bad)

    assert [j.request.title for j in repo.list_recent(status=JobStatus.SUCCEEDED)] == ["ok"]
    assert repo.get(bad.id).error == "boom"


def test_stats_aggregates(repo: JobRepository):
    job = _job()
    job.tracks = [AudioTrack(path=Path("/tmp/a.wav"), duration_s=60.0)]
    job.mark(JobStatus.SUCCEEDED)
    repo.save(job)

    stats = repo.stats()
    assert stats["jobs_total"] == 1
    assert stats["tracks"] == 1
    assert stats["audio_minutes"] == 1.0


def test_delete_removes_cascade(repo: JobRepository):
    job = _job()
    job.tracks = [AudioTrack(path=Path("/tmp/a.wav"))]
    repo.save(job)
    repo.delete(job.id)
    assert repo.get(job.id) is None

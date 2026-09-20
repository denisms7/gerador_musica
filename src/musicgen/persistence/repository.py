"""Repositorio de jobs e faixas. Traduz entre dominio e linhas do SQLite."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from musicgen.domain.models import (
    AudioTrack,
    GenerationJob,
    GenerationRequest,
    InferenceSpec,
    JobStatus,
    MusicalSpec,
    StyleSpec,
    TaskType,
    VocalGender,
)
from musicgen.persistence.db import get_connection, init_schema, transaction


def _request_to_json(req: GenerationRequest) -> str:
    payload = asdict(req)
    payload["style"]["vocal_gender"] = req.style.vocal_gender.value
    payload["task_type"] = req.task_type.value
    return json.dumps(payload, ensure_ascii=False)


def _request_from_json(raw: str) -> GenerationRequest:
    d = json.loads(raw)
    style = d.get("style", {})
    style["vocal_gender"] = VocalGender(style.get("vocal_gender", "unset"))
    return GenerationRequest(
        lyrics=d["lyrics"],
        style=StyleSpec(**style),
        musical=MusicalSpec(**d.get("musical", {})),
        inference=InferenceSpec(**d.get("inference", {})),
        title=d.get("title", "Sem titulo"),
        vocal_language=d.get("vocal_language", "portuguese"),
        instrumental=d.get("instrumental", False),
        task_type=TaskType(d.get("task_type", "text2music")),
        audio_format=d.get("audio_format", "wav"),
    )


class JobRepository:
    """Persistencia de jobs. Idempotente: ``save`` faz upsert."""

    def __init__(self, db_path: Path) -> None:
        self._db = db_path
        init_schema(db_path)

    # -- escrita --------------------------------------------------------------

    def save(self, job: GenerationJob) -> GenerationJob:
        with transaction(self._db) as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, title, provider, remote_id, status, created_at,
                                  updated_at, request_json, result_json, error)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    remote_id=excluded.remote_id,
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    result_json=excluded.result_json,
                    error=excluded.error
                """,
                (
                    job.id,
                    job.request.title,
                    job.provider,
                    job.remote_id,
                    job.status.value,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                    _request_to_json(job.request),
                    json.dumps(job.resolved_meta, ensure_ascii=False),
                    job.error,
                ),
            )
            conn.execute("DELETE FROM tracks WHERE job_id = ?", (job.id,))
            conn.executemany(
                """
                INSERT INTO tracks (job_id, path, sample_rate, duration_s, lufs, seed, stems_json)
                VALUES (?,?,?,?,?,?,?)
                """,
                [
                    (
                        job.id,
                        str(t.path),
                        t.sample_rate,
                        t.duration_s,
                        t.lufs,
                        t.seed,
                        json.dumps({k: str(v) for k, v in t.stems.items()}),
                    )
                    for t in job.tracks
                ],
            )
        return job

    def set_favorite(self, track_id: int, favorite: bool) -> None:
        with transaction(self._db) as conn:
            conn.execute("UPDATE tracks SET favorite=? WHERE id=?", (int(favorite), track_id))

    def delete(self, job_id: str, *, remove_files: bool = False) -> None:
        job = self.get(job_id)
        with transaction(self._db) as conn:
            conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        if remove_files and job:
            for track in job.tracks:
                track.path.unlink(missing_ok=True)

    # -- leitura --------------------------------------------------------------

    def _hydrate(self, row) -> GenerationJob:
        conn = get_connection(self._db)
        tracks = [
            AudioTrack(
                path=Path(t["path"]),
                sample_rate=t["sample_rate"],
                duration_s=t["duration_s"],
                lufs=t["lufs"],
                seed=t["seed"],
                stems={k: Path(v) for k, v in json.loads(t["stems_json"] or "{}").items()},
            )
            for t in conn.execute(
                "SELECT * FROM tracks WHERE job_id=? ORDER BY id", (row["id"],)
            ).fetchall()
        ]
        job = GenerationJob(
            request=_request_from_json(row["request_json"]),
            id=row["id"],
            provider=row["provider"],
            remote_id=row["remote_id"],
            status=JobStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            tracks=tracks,
            resolved_meta=json.loads(row["result_json"] or "{}"),
            error=row["error"],
        )
        return job

    def get(self, job_id: str) -> GenerationJob | None:
        conn = get_connection(self._db)
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._hydrate(row) if row else None

    def list_recent(
        self, *, limit: int = 50, status: JobStatus | None = None
    ) -> list[GenerationJob]:
        conn = get_connection(self._db)
        if status:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status.value, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._hydrate(r) for r in rows]

    def stats(self) -> dict:
        conn = get_connection(self._db)
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(status='succeeded') AS ok,
                   SUM(status='failed')    AS fail
            FROM jobs
            """
        ).fetchone()
        tracks = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(duration_s),0) AS secs FROM tracks"
        ).fetchone()
        return {
            "jobs_total": row["total"] or 0,
            "jobs_ok": row["ok"] or 0,
            "jobs_fail": row["fail"] or 0,
            "tracks": tracks["n"] or 0,
            "audio_minutes": round((tracks["secs"] or 0) / 60.0, 1),
        }

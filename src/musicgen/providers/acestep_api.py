"""Provider que fala com o servidor REST do ACE-Step 1.5 (``uv run acestep-api``).

Rodar a inferencia num processo separado e deliberado:

* o modelo fica residente na VRAM entre geracoes (carregar custa dezenas de segundos);
* o Streamlit reexecuta o script a cada interacao — carregar o modelo no processo
  da UI seria fatal;
* as dependencias pesadas (torch/vLLM/CUDA) ficam isoladas no venv do ACE-Step,
  sem conflitar com o venv do app.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import httpx

from musicgen.domain.models import GenerationRequest, JobStatus
from musicgen.providers.base import (
    MusicProvider,
    ProviderError,
    ProviderHealth,
    ProviderUnavailable,
)
from musicgen.services.prompt_builder import build_caption

logger = logging.getLogger(__name__)

_REMOTE_STATUS = {0: JobStatus.RUNNING, 1: JobStatus.SUCCEEDED, 2: JobStatus.FAILED}

#: Chaves em que os diferentes builds do servidor devolvem o caminho do audio.
_FILE_KEYS = ("file", "files", "audio", "audio_path", "path")


def _coerce_json(value: object) -> object:
    """Decodifica string JSON; devolve o valor intacto se nao for JSON."""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return value
    return value


def _flatten_entries(raw: object) -> list[Mapping]:
    """Achata o campo ``result`` numa lista de objetos.

    O servidor devolve ora um objeto unico, ora uma lista com um objeto por take
    (``batch_size`` > 1), ora uma string JSON de qualquer um dos dois. Achatar
    aqui mantem um contrato unico para o resto do pipeline.
    """
    raw = _coerce_json(raw)
    if isinstance(raw, Mapping):
        return [raw]
    if isinstance(raw, list):
        out: list[Mapping] = []
        for item in raw:
            out.extend(_flatten_entries(item))
        return out
    return []


def _extract_files(entry: Mapping) -> list[str]:
    found: list[str] = []
    for key in _FILE_KEYS:
        value = entry.get(key)
        if isinstance(value, str) and value:
            found.append(value)
        elif isinstance(value, list):
            found.extend(v for v in value if isinstance(v, str) and v)
        if found:
            break
    return found


def _normalize_result(raw: object) -> dict:
    """Forma canonica do resultado, independente do shape que o backend mandou.

    Returns:
        ``{"files": [...], "metas": {...}, "seeds": [...]}`` — sempre com essas
        chaves, mesmo vazias. ``entries`` guarda os objetos originais para
        diagnostico.
    """
    entries = _flatten_entries(raw)
    if not entries:
        return {"files": [], "metas": {}, "seeds": []}

    files: list[str] = []
    seeds: list[int] = []
    metas: dict = {}
    errors: list[str] = []

    for entry in entries:
        for key in ("error", "status_message", "message", "detail"):
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                errors.append(value.strip())
        files.extend(_extract_files(entry))
        if not metas and isinstance(entry.get("metas"), Mapping):
            metas = dict(entry["metas"])
        raw_seed = entry.get("seed_value", entry.get("seed"))
        if isinstance(raw_seed, (int, float)):
            seeds.append(int(raw_seed))
        elif isinstance(raw_seed, str):
            seeds.extend(
                int(part.strip())
                for part in raw_seed.split(",")
                if part.strip().lstrip("-").isdigit()
            )
        elif isinstance(raw_seed, list):
            seeds.extend(int(s) for s in raw_seed if isinstance(s, (int, float)))

    # dedupe preservando ordem: takes repetidos nao devem virar downloads duplicados
    seen: set[str] = set()
    unique_files = [f for f in files if not (f in seen or seen.add(f))]

    if not unique_files:
        logger.warning(
            "resultado do backend sem caminho de audio; chaves vistas: %s",
            sorted({k for e in entries for k in e}),
        )

    # dedupe preservando ordem tambem nos erros: o backend repete a mesma causa
    # em cada item do batch
    seen_err: set[str] = set()
    unique_errors = [e for e in errors if not (e in seen_err or seen_err.add(e))]

    return {
        "files": unique_files,
        "metas": metas,
        "seeds": seeds,
        "errors": unique_errors,
        "entries": entries,
    }


class AceStepApiProvider(MusicProvider):
    name = "acestep-api"

    def __init__(
        self,
        base_url: str,
        *,
        dit_model: str | None = None,
        api_key: str | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._dit_model = dit_model
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout_s

    # -- infraestrutura -------------------------------------------------------

    def _client(self, timeout: float | None = None) -> httpx.Client:
        return httpx.Client(
            base_url=self._base_url,
            headers=self._headers,
            timeout=timeout or self._timeout,
        )

    def _unwrap(self, response: httpx.Response) -> dict:
        response.raise_for_status()
        body = response.json()
        if body.get("code") != 200 or body.get("error"):
            raise ProviderError(f"ACE-Step retornou erro: {body.get('error') or body}")
        return body.get("data") or {}

    # -- contrato -------------------------------------------------------------

    def health(self) -> ProviderHealth:
        try:
            with self._client(timeout=5.0) as c:
                info = self._unwrap(c.get("/health"))
                stats, jobs = self._safe_get(c, "/v1/stats"), {}
                jobs = stats.get("jobs", {}) if isinstance(stats, Mapping) else {}
                models_payload = self._safe_get(c, "/v1/models")

            entries = models_payload.get("models", []) if isinstance(models_payload, Mapping) else []
            models = [m["name"] for m in entries if isinstance(m, Mapping) and m.get("name")]
            active = models_payload.get("default_model") or next(
                (m["name"] for m in entries if isinstance(m, Mapping) and m.get("is_default")),
                None,
            )

            return ProviderHealth(
                available=info.get("status") == "ok",
                version=info.get("version"),
                models=models,
                queued=jobs.get("queued", 0),
                running=jobs.get("running", 0),
                avg_job_seconds=stats.get("avg_job_seconds") if isinstance(stats, Mapping) else None,
                active_model=active,
            )
        except Exception as exc:
            return ProviderHealth(available=False, detail=str(exc))

    @staticmethod
    def _safe_get(client: httpx.Client, path: str) -> dict:
        """GET tolerante: endpoints acessorios nao podem derrubar o health."""
        try:
            response = client.get(path)
            response.raise_for_status()
            body = response.json()
            data = body.get("data") if isinstance(body, Mapping) else None
            return data if isinstance(data, Mapping) else {}
        except Exception:
            return {}

    def submit(self, request: GenerationRequest) -> str:
        payload: dict = {
            "prompt": build_caption(request.style, vocal_language=request.vocal_language),
            "lyrics": "" if request.instrumental else request.lyrics,
            "task_type": request.task_type.value,
            "audio_format": request.audio_format,
            "inference_steps": request.inference.steps,
            "guidance_scale": request.inference.guidance_scale,
            "batch_size": request.inference.batch_size,
            "thinking": request.inference.thinking,
        }
        if self._dit_model:
            payload["model"] = self._dit_model
        if request.inference.seed is not None:
            payload["seed"] = request.inference.seed
        if request.musical.bpm is not None:
            payload["bpm"] = request.musical.bpm
        if request.musical.key_scale:
            payload["key_scale"] = request.musical.key_scale
        if request.musical.time_signature:
            payload["time_signature"] = request.musical.time_signature
        if request.musical.duration_s is not None:
            payload["audio_duration"] = request.musical.duration_s

        try:
            with self._client() as c:
                data = self._unwrap(c.post("/release_task", json=payload))
        except httpx.ConnectError as exc:
            raise ProviderUnavailable(
                f"Servidor ACE-Step inacessivel em {self._base_url}. "
                "Inicie-o com `uv run acestep-api` na pasta do ACE-Step."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Falha ao enfileirar tarefa: {exc}") from exc

        task_id = data.get("task_id")
        if not task_id:
            raise ProviderError(f"Resposta sem task_id: {data}")
        logger.info("tarefa %s enfileirada (posicao %s)", task_id, data.get("queue_position"))
        return task_id

    def poll(self, remote_id: str) -> tuple[JobStatus, dict]:
        try:
            with self._client() as c:
                data = self._unwrap(c.post("/query_result", json={"task_id_list": [remote_id]}))
        except httpx.ConnectError as exc:
            raise ProviderUnavailable("Conexao com o servidor ACE-Step perdida.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Falha ao consultar tarefa: {exc}") from exc

        entries = data if isinstance(data, list) else data.get("data", [])
        entry = next((e for e in entries if e.get("task_id") == remote_id), None)
        if entry is None:
            raise ProviderError(f"Tarefa {remote_id} desconhecida pelo servidor.")

        status = _REMOTE_STATUS.get(int(entry.get("status", 0)), JobStatus.RUNNING)
        return status, _normalize_result(entry.get("result"))

    def fetch_artifacts(self, payload: dict, dest_dir: Path) -> list[Path]:
        files = payload.get("files") or []
        if not files:
            raise ProviderError(
                "Resultado sem arquivos de audio. "
                f"Chaves recebidas do backend: {sorted(payload)}"
            )

        dest_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        with self._client(timeout=300.0) as c:
            for idx, ref in enumerate(files):
                url, name = self._resolve_download(ref, idx)
                response = c.get(url)
                response.raise_for_status()
                target = dest_dir / name
                target.write_bytes(response.content)
                saved.append(target)
        return saved

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _resolve_download(ref: str, idx: int) -> tuple[str, str]:
        """Converte a referencia devolvida pelo backend em (url, nome de arquivo)."""
        parsed = urlparse(ref)
        raw_path = parse_qs(parsed.query).get("path", [None])[0]
        if raw_path:
            suffix = Path(raw_path).suffix or ".wav"
            return f"/v1/audio?path={quote(raw_path, safe='')}", f"take_{idx + 1}{suffix}"
        suffix = Path(parsed.path).suffix or ".wav"
        if parsed.path.startswith("/v1/audio"):
            return ref, f"take_{idx + 1}{suffix}"
        return f"/v1/audio?path={quote(ref, safe='')}", f"take_{idx + 1}{suffix}"

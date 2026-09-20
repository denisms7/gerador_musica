import json
from pathlib import Path

import httpx
import pytest

from musicgen.domain.models import GenerationRequest, JobStatus, StyleSpec
from musicgen.providers.acestep_api import AceStepApiProvider
from musicgen.providers.base import ProviderError, ProviderUnavailable


class _MockTransport(httpx.MockTransport):
    pass


def _provider(handler) -> AceStepApiProvider:
    p = AceStepApiProvider("http://test", dit_model="acestep-v15-turbo")
    p._client = lambda timeout=None: httpx.Client(  # type: ignore[method-assign]
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    return p


def _ok(data) -> httpx.Response:
    return httpx.Response(200, json={"data": data, "code": 200, "error": None})


def test_submit_returns_task_id_and_sends_expected_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return _ok({"task_id": "abc", "status": "queued", "queue_position": 0})

    req = GenerationRequest(lyrics="[Chorus]\nhook", style=StyleSpec(genres=["samba"]))
    assert _provider(handler).submit(req) == "abc"
    assert captured["model"] == "acestep-v15-turbo"
    assert "samba" in captured["prompt"]
    assert captured["lyrics"] == "[Chorus]\nhook"


def test_submit_without_server_raises_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderUnavailable):
        _provider(handler).submit(GenerationRequest(lyrics="x"))


def test_poll_maps_remote_status_codes():
    cases = {0: JobStatus.RUNNING, 1: JobStatus.SUCCEEDED, 2: JobStatus.FAILED}
    for code, expected in cases.items():
        def handler(request, code=code):
            return _ok([{"task_id": "abc", "status": code,
                         "result": json.dumps({"file": "/v1/audio?path=/tmp/x.wav"})}])
        status, payload = _provider(handler).poll("abc")
        assert status is expected
        assert payload["files"] == ["/v1/audio?path=/tmp/x.wav"]


def test_poll_unknown_task_raises():
    def handler(request):
        return _ok([])

    with pytest.raises(ProviderError):
        _provider(handler).poll("nope")


def test_error_envelope_is_surfaced():
    def handler(request):
        return httpx.Response(200, json={"data": None, "code": 500, "error": "oom"})

    with pytest.raises(ProviderError, match="oom"):
        _provider(handler).submit(GenerationRequest(lyrics="x"))


def test_fetch_artifacts_downloads_and_names_files(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/audio"
        return httpx.Response(200, content=b"RIFFfake")

    saved = _provider(handler).fetch_artifacts(
        {"files": ["/v1/audio?path=/tmp/a.wav", "/v1/audio?path=/tmp/b.wav"]}, tmp_path
    )
    assert [p.name for p in saved] == ["take_1.wav", "take_2.wav"]
    assert saved[0].read_bytes() == b"RIFFfake"


def test_fetch_artifacts_without_files_raises(tmp_path: Path):
    with pytest.raises(ProviderError):
        _provider(lambda r: _ok({})).fetch_artifacts({}, tmp_path)


def test_health_never_raises():
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    health = _provider(handler).health()
    assert health.available is False
    assert health.detail


class TestResultNormalization:
    """O backend devolve `result` em shapes diferentes conforme build e batch_size.

    O servidor real entrega uma LISTA de objetos quando batch_size > 1 — a doc
    so descreve o objeto unico. Normalizar no provider mantem um contrato unico
    para o pipeline.
    """

    @staticmethod
    def _norm(raw):
        from musicgen.providers.acestep_api import _normalize_result

        return _normalize_result(raw)

    def test_single_object(self):
        out = self._norm({"file": "/v1/audio?path=/a.wav", "metas": {"bpm": 90},
                          "seed_value": "7"})
        assert out["files"] == ["/v1/audio?path=/a.wav"]
        assert out["metas"] == {"bpm": 90}
        assert out["seeds"] == [7]

    def test_list_of_objects_is_flattened(self):
        out = self._norm([
            {"file": "/a.wav", "metas": {"bpm": 90}, "seed_value": "1"},
            {"file": "/b.wav", "seed_value": "2"},
        ])
        assert out["files"] == ["/a.wav", "/b.wav"]
        assert out["metas"] == {"bpm": 90}
        assert out["seeds"] == [1, 2]

    def test_json_encoded_string_is_decoded(self):
        out = self._norm('[{"file": "/a.wav", "seed_value": "5"}]')
        assert out["files"] == ["/a.wav"]
        assert out["seeds"] == [5]

    def test_nested_lists_are_flattened(self):
        assert self._norm([[{"file": "/a.wav"}], [{"file": "/b.wav"}]])["files"] == [
            "/a.wav", "/b.wav"
        ]

    def test_file_as_list_inside_object(self):
        assert self._norm({"file": ["/a.wav", "/b.wav"]})["files"] == ["/a.wav", "/b.wav"]

    def test_alternate_file_keys(self):
        for key in ("files", "audio", "audio_path", "path"):
            assert self._norm({key: "/a.wav"})["files"] == ["/a.wav"], key

    def test_duplicate_files_are_deduped_preserving_order(self):
        out = self._norm([{"file": "/a.wav"}, {"file": "/a.wav"}, {"file": "/b.wav"}])
        assert out["files"] == ["/a.wav", "/b.wav"]

    def test_seed_variants(self):
        assert self._norm({"file": "/a.wav", "seed_value": "1,2,3"})["seeds"] == [1, 2, 3]
        assert self._norm({"file": "/a.wav", "seed": 42})["seeds"] == [42]
        assert self._norm({"file": "/a.wav", "seed_value": [8, 9]})["seeds"] == [8, 9]

    def test_garbage_seed_is_ignored_not_fatal(self):
        assert self._norm({"file": "/a.wav", "seed_value": "aleatoria"})["seeds"] == []

    def test_empty_and_malformed_inputs_return_canonical_empty(self):
        for raw in (None, "", "[]", [], {}, "nao é json", 42):
            out = self._norm(raw)
            assert out["files"] == [] and out["metas"] == {} and out["seeds"] == []

    def test_result_without_audio_keeps_keys_for_diagnosis(self):
        out = self._norm({"status": 1, "prompt": "x"})
        assert out["files"] == []
        assert out["entries"][0]["prompt"] == "x"


def test_poll_accepts_list_result_from_real_server():
    """Regressao: `result` como lista quebrava com AttributeError em base.wait."""
    def handler(request):
        return _ok([{
            "task_id": "abc",
            "status": 1,
            "result": json.dumps([
                {"file": "/v1/audio?path=/t/1.wav", "metas": {"bpm": 96}, "seed_value": "11"},
                {"file": "/v1/audio?path=/t/2.wav", "seed_value": "22"},
            ]),
        }])

    status, payload = _provider(handler).poll("abc")
    assert status is JobStatus.SUCCEEDED
    assert len(payload["files"]) == 2
    assert payload["seeds"] == [11, 22]


def test_wait_survives_non_mapping_payload():
    """base.wait nao pode assumir que o payload e um dict."""
    from musicgen.domain.models import GenerationJob
    from musicgen.providers.base import MusicProvider, ProviderHealth

    class Weird(MusicProvider):
        name = "weird"

        def health(self):
            return ProviderHealth(available=True)

        def submit(self, request):
            return "id"

        def poll(self, remote_id):
            return JobStatus.SUCCEEDED, []  # lista crua, nao dict

        def fetch_artifacts(self, payload, dest_dir):
            return []

    job = GenerationJob(request=GenerationRequest(lyrics="x"))
    job.remote_id = "id"
    states = list(Weird().wait(job, poll_interval_s=0.05, timeout_s=30))
    assert states[-1].status is JobStatus.SUCCEEDED


def test_health_reports_active_model():
    """Saber o modelo REALMENTE carregado distingue '.env errado' de 'backend nao
    reiniciado' — sintomas identicos na tela, causas opostas."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return _ok({"status": "ok", "version": "1.5"})
        if request.url.path == "/v1/models":
            return _ok({
                "models": [{"name": "acestep-v15-turbo", "is_default": True}],
                "default_model": "acestep-v15-turbo",
            })
        return _ok({})

    health = _provider(handler).health()
    assert health.available
    assert health.active_model == "acestep-v15-turbo"
    assert health.models == ["acestep-v15-turbo"]


def test_health_falls_back_to_is_default_flag():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return _ok({"status": "ok"})
        if request.url.path == "/v1/models":
            return _ok({"models": [{"name": "a", "is_default": False},
                                   {"name": "b", "is_default": True}]})
        return _ok({})

    assert _provider(handler).health().active_model == "b"


def test_health_survives_missing_optional_endpoints():
    """/v1/stats e /v1/models sao acessorios: sua ausencia nao pode derrubar o
    health, senao a UI declara o backend offline com ele no ar."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return _ok({"status": "ok"})
        return httpx.Response(404)

    health = _provider(handler).health()
    assert health.available
    assert health.active_model is None
    assert health.models == []

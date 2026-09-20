"""Supervisao do processo do servidor de inferencia ACE-Step.

Permite iniciar/parar o backend a partir da UI, sem que o usuario precise de um
segundo terminal. O processo e desacoplado (novo grupo de processos) para que
fechar o Streamlit nao mate o servidor a meio de uma geracao.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass(slots=True)
class ServerState:
    running: bool
    pid: int | None = None
    detail: str = ""


class AceStepSupervisor:
    def __init__(self, home: Path | None, base_url: str) -> None:
        self.home = Path(home) if home else None
        self.base_url = base_url.rstrip("/")
        self._proc: subprocess.Popen | None = None

    # -- estado ---------------------------------------------------------------

    def is_up(self, timeout: float = 3.0) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/health", timeout=timeout)
            return r.status_code == 200
        except Exception:
            return False

    def state(self) -> ServerState:
        if self.is_up():
            return ServerState(True, self._proc.pid if self._proc else None, "servidor respondendo")
        if self._proc and self._proc.poll() is None:
            return ServerState(False, self._proc.pid, "processo subindo (carregando modelo)")
        return ServerState(False, None, "servidor parado")

    # -- controle -------------------------------------------------------------

    def diagnose(self) -> list[str]:
        """Passos concretos para tirar o backend do estado atual.

        Distingue os tres motivos reais de um backend offline, que a mensagem
        generica de erro de conexao nao separa: ambiente nunca preparado,
        preparado mas parado, ou rodando em outro endereco.
        """
        if self.is_up():
            return []

        if self.home is None:
            return [
                "O `.env` nao aponta para o ACE-Step "
                "(`MUSICGEN_ACESTEP_HOME` ausente ou vazio).",
                "Se ainda nao instalou o backend, rode uma vez: "
                "`powershell -ExecutionPolicy Bypass -File scripts\\setup.ps1`",
                "Se ja instalou, copie `.env.example` para `.env` e preencha "
                "`MUSICGEN_ACESTEP_HOME` com a pasta do ACE-Step.",
            ]

        if not self.home.exists():
            return [
                f"A pasta do ACE-Step nao existe: `{self.home}`.",
                "Rode `scripts\\setup.ps1` para clonar e sincronizar o backend, "
                "ou corrija `MUSICGEN_ACESTEP_HOME` no `.env`.",
            ]

        if not (self.home / "pyproject.toml").exists():
            return [
                f"`{self.home}` existe mas nao parece o repositorio do ACE-Step "
                "(sem `pyproject.toml`).",
                "Confira o caminho em `MUSICGEN_ACESTEP_HOME`.",
            ]

        steps = [
            f"O backend esta instalado em `{self.home}` mas nao esta rodando.",
            "Inicie com: `.\\scripts\\start-backend.ps1` "
            f"(ou `cd {self.home}` e entao `uv run acestep-api` — esse comando "
            "NAO funciona na pasta do app).",
            "No primeiro start os pesos sao baixados (varios GB) antes de a porta abrir — "
            "acompanhe o terminal.",
        ]
        if not shutil.which("uv"):
            steps.insert(1, "`uv` nao esta no PATH desta sessao. Instale: https://astral.sh/uv")
        steps.append(
            f"Se o servidor ja esta ativo em outra porta, ajuste "
            f"`MUSICGEN_ACESTEP_BASE_URL` (atual: {self.base_url})."
        )
        return steps

    def preflight(self) -> list[str]:
        """Lista de problemas que impedem o start. Vazia = pronto."""
        problems: list[str] = []
        if not self.home:
            problems.append("MUSICGEN_ACESTEP_HOME nao configurado no .env")
            return problems
        if not self.home.exists():
            problems.append(f"Pasta do ACE-Step nao encontrada: {self.home}")
        elif not (self.home / "pyproject.toml").exists():
            problems.append(f"{self.home} nao parece ser o repositorio do ACE-Step")
        if not shutil.which("uv"):
            problems.append("`uv` nao esta no PATH. Instale: https://astral.sh/uv")
        return problems

    def start(self, *, dit_model: str | None = None, lm_model: str | None = None) -> ServerState:
        if self.is_up():
            return ServerState(True, None, "ja estava rodando")
        problems = self.preflight()
        if problems:
            return ServerState(False, None, "; ".join(problems))

        env = os.environ.copy()
        if dit_model:
            env["ACESTEP_CONFIG_PATH"] = dit_model
        if lm_model:
            env["ACESTEP_LM_MODEL_PATH"] = lm_model

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(
                subprocess, "DETACHED_PROCESS", 0
            )

        log_path = Path(self.home) / "acestep-api.log"  # type: ignore[arg-type]
        self._proc = subprocess.Popen(
            ["uv", "run", "acestep-api"],
            cwd=str(self.home),
            env=env,
            stdout=log_path.open("ab"),
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            start_new_session=(sys.platform != "win32"),
        )
        return ServerState(
            False,
            self._proc.pid,
            f"iniciado (pid {self._proc.pid}); o primeiro start baixa os modelos e pode levar "
            f"varios minutos. Log: {log_path}",
        )

    def stop(self) -> ServerState:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            return ServerState(False, None, "processo encerrado")
        return ServerState(False, None, "nenhum processo sob supervisao desta sessao")

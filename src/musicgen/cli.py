"""CLI do MusicGen. Permite geracao em lote e automacao sem abrir a UI.

Exemplos:
    musicgen doctor
    musicgen generate letra.txt --preset "MPB acustica" --title "Minha musica"
    musicgen list --limit 10
"""
from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from musicgen.config import get_settings
from musicgen.domain import lyrics as lyrics_mod
from musicgen.domain.models import (
    GenerationRequest,
    InferenceSpec,
    MusicalSpec,
    StyleSpec,
    VocalGender,
)
from musicgen.persistence.repository import JobRepository
from musicgen.providers.registry import get_provider
from musicgen.services.generation import GenerationService
from musicgen.services.prompt_builder import LANGUAGES, STYLE_PRESETS, build_caption

app = typer.Typer(add_completion=False, help="Gerador local de musica a partir de letra.")
console = Console()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@app.command()
def doctor() -> None:
    """Verifica configuracao e disponibilidade do backend."""
    settings = get_settings()
    health = get_provider(settings=settings).health()
    table = Table(title="MusicGen - diagnostico")
    table.add_column("Item")
    table.add_column("Valor")
    table.add_row("Backend", settings.acestep_base_url)
    table.add_row("Online", "sim" if health.available else f"NAO ({health.detail})")
    table.add_row("Modelo DiT", settings.dit_model)
    table.add_row("Modelo LM", settings.lm_model)
    table.add_row("Modelos no servidor", ", ".join(health.models) or "--")
    table.add_row("Fila / executando", f"{health.queued} / {health.running}")
    table.add_row("Banco", str(settings.db_path.resolve()))
    console.print(table)
    raise typer.Exit(0 if health.available else 1)


@app.command()
def lint(lyrics_file: Path) -> None:
    """Valida a estrutura de um arquivo de letra."""
    doc = lyrics_mod.parse(lyrics_file.read_text(encoding="utf-8"))
    for issue in doc.issues:
        console.print(f"[{issue.severity.value}] {issue.message}")
    console.print(
        f"\n{len(doc.sections)} secoes, {doc.total_words} palavras, "
        f"~{doc.estimated_duration_s():.0f}s estimados"
    )
    console.print("  ".join(s.header for s in doc.sections))
    raise typer.Exit(1 if doc.has_errors else 0)


@app.command()
def generate(
    lyrics_file: Path = typer.Argument(..., help="Arquivo .txt com a letra"),
    title: str = typer.Option("Sem titulo", "--title", "-t"),
    preset: str = typer.Option(None, "--preset", "-p", help=f"Um de: {list(STYLE_PRESETS)}"),
    prompt: str = typer.Option(None, "--prompt", help="Descricao de estilo livre (ingles)"),
    language: str = typer.Option("portuguese", "--language", "-l"),
    bpm: int = typer.Option(None, "--bpm"),
    duration: float = typer.Option(None, "--duration", "-d"),
    steps: int = typer.Option(None, "--steps"),
    batch: int = typer.Option(None, "--batch", "-b", help="Numero de variacoes"),
    seed: int = typer.Option(None, "--seed"),
    instrumental: bool = typer.Option(False, "--instrumental"),
) -> None:
    """Gera musica a partir de um arquivo de letra."""
    settings = get_settings()
    style = (
        StyleSpec(free_text=prompt)
        if prompt
        else STYLE_PRESETS.get(preset or "", StyleSpec(vocal_gender=VocalGender.UNSET))
    )
    request = GenerationRequest(
        lyrics=lyrics_file.read_text(encoding="utf-8") if not instrumental else "",
        style=style,
        musical=MusicalSpec(bpm=bpm, duration_s=duration),
        inference=InferenceSpec(
            steps=steps or settings.default_steps,
            guidance_scale=settings.default_guidance,
            shift=3.0 if "turbo" in settings.dit_model else 1.0,
            seed=seed,
            batch_size=batch or settings.default_batch,
        ),
        title=title,
        vocal_language=LANGUAGES.get(language, language),
        instrumental=instrumental,
        audio_format=settings.audio_format,
    )
    console.print(f"[bold]Prompt:[/bold] {build_caption(style, vocal_language=language)}")

    service = GenerationService(settings=settings)
    with console.status("gerando...") as status:
        for event in service.run(request):
            status.update(f"{event.stage}: {event.detail}")
            if event.stage == "failed":
                console.print(f"[red]FALHOU:[/red] {event.detail}")
                raise typer.Exit(1)
            if event.stage == "done":
                for track in event.job.tracks:
                    console.print(f"[green]OK[/green] {track.path}")


@app.command("list")
def list_jobs(limit: int = typer.Option(20, "--limit", "-n")) -> None:
    """Lista as geracoes recentes."""
    repo = JobRepository(get_settings().db_path)
    table = Table(title="Geracoes recentes")
    for col in ("id", "titulo", "status", "faixas", "quando"):
        table.add_column(col)
    for job in repo.list_recent(limit=limit):
        table.add_row(
            job.id,
            job.request.title,
            job.status.value,
            str(len(job.tracks)),
            job.created_at.astimezone().strftime("%d/%m %H:%M"),
        )
    console.print(table)


if __name__ == "__main__":
    app()

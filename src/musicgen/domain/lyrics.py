"""Parsing, validacao e normalizacao de letras com tags de estrutura.

O ACE-Step interpreta tags de secao entre colchetes (``[Verse]``, ``[Chorus]``...)
para controlar a forma da musica. Este modulo garante que a letra entregue ao
modelo esteja bem formada e oferece diagnosticos acionaveis para a UI.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

_TAG_RE = re.compile(r"^\s*\[([^\[\]]{1,60})\]\s*$", re.MULTILINE)

#: Tags canonicas reconhecidas pelo modelo. O sufixo numerico (``Verse 2``) e o
#: modificador apos hifen (``Chorus - anthemic``) sao aceitos e normalizados.
CANONICAL_TAGS: tuple[str, ...] = (
    "Intro",
    "Verse",
    "Pre-Chorus",
    "Chorus",
    "Post-Chorus",
    "Bridge",
    "Build",
    "Drop",
    "Breakdown",
    "Instrumental",
    "Guitar Solo",
    "Piano Interlude",
    "Hook",
    "Refrain",
    "Outro",
    "Fade Out",
    "Silence",
)

_CANON_LOOKUP = {t.lower(): t for t in CANONICAL_TAGS}

#: Traducao PT-BR -> tag canonica, para letras escritas em portugues.
_PT_ALIASES = {
    "introducao": "Intro",
    "intro": "Intro",
    "verso": "Verse",
    "estrofe": "Verse",
    "pre-refrao": "Pre-Chorus",
    "pre refrao": "Pre-Chorus",
    "refrao": "Chorus",
    "coro": "Chorus",
    "ponte": "Bridge",
    "solo": "Guitar Solo",
    "instrumental": "Instrumental",
    "final": "Outro",
    "encerramento": "Outro",
    "fim": "Outro",
}


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(slots=True)
class Issue:
    severity: Severity
    message: str
    line: int | None = None


@dataclass(slots=True)
class Section:
    tag: str
    modifier: str | None
    lines: list[str] = field(default_factory=list)

    @property
    def header(self) -> str:
        return f"[{self.tag} - {self.modifier}]" if self.modifier else f"[{self.tag}]"

    @property
    def word_count(self) -> int:
        return sum(len(line.split()) for line in self.lines)

    @property
    def is_instrumental(self) -> bool:
        return self.tag in {"Instrumental", "Guitar Solo", "Piano Interlude", "Silence"}


@dataclass(slots=True)
class LyricsDocument:
    sections: list[Section]
    issues: list[Issue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity is Severity.ERROR for i in self.issues)

    @property
    def total_words(self) -> int:
        return sum(s.word_count for s in self.sections)

    def estimated_duration_s(self, *, words_per_minute: float = 70.0) -> float:
        """Estimativa grosseira de duracao cantada.

        ~70 palavras/minuto cobre a densidade tipica de pop/MPB. Secoes
        instrumentais recebem 15s fixos.
        """
        sung = self.total_words / words_per_minute * 60.0
        instrumental = sum(15.0 for s in self.sections if s.is_instrumental)
        return round(max(30.0, sung + instrumental), 1)

    def render(self) -> str:
        """Serializa de volta para o formato esperado pelo modelo."""
        blocks: list[str] = []
        for s in self.sections:
            body = "\n".join(s.lines).strip()
            blocks.append(f"{s.header}\n{body}".strip())
        return "\n\n".join(blocks)


def _canonicalize(raw: str) -> tuple[str, str | None, bool]:
    """Normaliza o conteudo de uma tag.

    Returns:
        (tag_canonica, modificador, foi_reconhecida)
    """
    raw = raw.strip()
    modifier: str | None = None
    # O separador e o hifen CERCADO DE ESPACOS ("Chorus - anthemic"). Tratar
    # qualquer hifen como separador quebraria as tags compostas do proprio
    # modelo (Pre-Chorus, Post-Chorus, Fade Out).
    head, sep, tail = raw.partition(" - ")
    if sep and tail.strip():
        raw, modifier = head.strip(), tail.strip()

    # separa sufixo numerico: "Verse 2" -> ("Verse", "2")
    m = re.match(r"^(.*?)[\s_]*(\d+)$", raw)
    number = None
    if m and m.group(1).strip():
        raw, number = m.group(1).strip(), m.group(2)

    key = raw.lower().replace("_", " ").strip()
    canon = _CANON_LOOKUP.get(key) or _PT_ALIASES.get(key)
    recognized = canon is not None
    tag = canon or raw.title()
    if number:
        tag = f"{tag} {number}"
    return tag, modifier, recognized


def parse(text: str) -> LyricsDocument:
    """Converte texto livre em um documento estruturado com diagnosticos."""
    issues: list[Issue] = []
    text = text.replace("\r\n", "\n").strip()

    if not text:
        return LyricsDocument(sections=[], issues=[Issue(Severity.ERROR, "Letra vazia.")])

    matches = list(_TAG_RE.finditer(text))

    if not matches:
        issues.append(
            Issue(
                Severity.WARNING,
                "Nenhuma tag de estrutura encontrada. O modelo vai inferir a forma "
                "sozinho; marcar [Verse]/[Chorus] da muito mais controle.",
            )
        )
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        return LyricsDocument(sections=[Section("Verse", None, lines)], issues=issues)

    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            issues.append(
                Issue(Severity.WARNING, "Texto antes da primeira tag foi movido para [Intro].", 1)
            )
            matches = None  # type: ignore[assignment]
            text = f"[Intro]\n{preamble}\n\n" + text[len(preamble) :].lstrip()
            matches = list(_TAG_RE.finditer(text))

    sections: list[Section] = []
    for i, m in enumerate(matches):
        tag, modifier, recognized = _canonicalize(m.group(1))
        line_no = text[: m.start()].count("\n") + 1
        if not recognized:
            issues.append(
                Issue(
                    Severity.WARNING,
                    f"Tag '{m.group(1)}' nao e canonica; o modelo pode ignora-la. "
                    f"Use uma de: {', '.join(CANONICAL_TAGS[:8])}...",
                    line_no,
                )
            )
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end]
        lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
        section = Section(tag, modifier, lines)
        if not lines and not section.is_instrumental:
            issues.append(
                Issue(Severity.WARNING, f"Secao {section.header} esta sem letra.", line_no)
            )
        sections.append(section)

    doc = LyricsDocument(sections=sections, issues=issues)

    if doc.total_words > 600:
        issues.append(
            Issue(
                Severity.WARNING,
                f"{doc.total_words} palavras excedem o que cabe confortavelmente em 600s. "
                "Considere cortar secoes.",
            )
        )
    if not any(s.tag.startswith("Chorus") for s in sections):
        issues.append(
            Issue(Severity.INFO, "Sem [Chorus]: a musica tende a soar sem gancho memoravel.")
        )
    return doc


def normalize(text: str) -> str:
    """Atalho: parse + render, devolvendo a letra pronta para o modelo."""
    return parse(text).render()

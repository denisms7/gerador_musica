"""Definicao das paginas da UI como dados puros.

Separado de ``app.py`` de proposito: o Streamlit so valida a navegacao quando o
runtime esta ativo e um cliente conecta (em bare mode ``st.navigation`` e um
no-op), entao um erro de rota duplicada nao aparece em teste de import nem no
log do servidor. Mantendo a especificacao como dados, a invariante que importa
- pathnames unicos, exatamente uma pagina default - fica testavel sem runtime.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from musicgen.ui.views import diagnostics, generate, home, library


@dataclass(frozen=True, slots=True)
class PageSpec:
    """Uma entrada de navegacao.

    Attributes:
        view: callable que renderiza a pagina.
        title: rotulo na sidebar.
        icon: icone Material.
        url_path: pathname explicito. Obrigatorio em toda pagina nao-default,
            porque o Streamlit infere o pathname do nome do callable e todas as
            views expoem ``render`` - sem isso elas colidem. A pagina default
            precisa de pathname vazio.
        default: se e a pagina inicial.
    """

    view: Callable[[], None]
    title: str
    icon: str
    url_path: str = ""
    default: bool = False


PAGES: tuple[PageSpec, ...] = (
    PageSpec(home.render, "Visao geral", ":material/dashboard:", default=True),
    PageSpec(generate.render, "Gerar musica", ":material/graphic_eq:", "gerar"),
    PageSpec(library.render, "Biblioteca", ":material/library_music:", "biblioteca"),
    PageSpec(diagnostics.render, "Diagnostico", ":material/monitor_heart:", "diagnostico"),
)


def validate(pages: tuple[PageSpec, ...] = PAGES) -> None:
    """Falha cedo se a navegacao violar as regras do Streamlit.

    Raises:
        ValueError: pathname duplicado, pathname ausente em pagina nao-default,
            pathname preenchido na default, ou numero de defaults diferente de 1.
    """
    defaults = [p for p in pages if p.default]
    if len(defaults) != 1:
        raise ValueError(f"esperada exatamente 1 pagina default, encontradas {len(defaults)}")
    if defaults[0].url_path:
        raise ValueError("a pagina default precisa ter url_path vazio")

    paths = [p.url_path for p in pages if not p.default]
    if any(not p for p in paths):
        raise ValueError("toda pagina nao-default precisa de url_path explicito")
    if len(set(paths)) != len(paths):
        dupes = {p for p in paths if paths.count(p) > 1}
        raise ValueError(f"url_path duplicado: {sorted(dupes)}")

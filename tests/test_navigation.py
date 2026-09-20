"""Regressao da navegacao.

O Streamlit infere o pathname de cada pagina do nome do callable; como todas as
views expoem ``render``, faltar ``url_path`` derruba o app com
``Multiple Pages specified with URL pathname render``. Esse erro so aparece com
o runtime ativo e um cliente conectado, entao a invariante e testada aqui.
"""
from __future__ import annotations

import pytest

from musicgen.ui.navigation import PAGES, PageSpec, validate


def test_shipped_navigation_is_valid():
    validate()


def test_all_views_are_named_render():
    # premissa do bug: se isso mudar, o url_path explicito deixa de ser critico
    assert {p.view.__name__ for p in PAGES} == {"render"}


def test_exactly_one_default_page():
    assert sum(p.default for p in PAGES) == 1


def test_duplicate_url_path_is_rejected():
    pages = (
        PageSpec(lambda: None, "A", "i", default=True),
        PageSpec(lambda: None, "B", "i", "x"),
        PageSpec(lambda: None, "C", "i", "x"),
    )
    with pytest.raises(ValueError, match="duplicado"):
        validate(pages)


def test_missing_url_path_is_rejected():
    pages = (
        PageSpec(lambda: None, "A", "i", default=True),
        PageSpec(lambda: None, "B", "i"),
    )
    with pytest.raises(ValueError, match="url_path explicito"):
        validate(pages)


def test_default_page_with_url_path_is_rejected():
    pages = (PageSpec(lambda: None, "A", "i", "home", default=True),)
    with pytest.raises(ValueError, match="url_path vazio"):
        validate(pages)


@pytest.mark.parametrize("count", [0, 2])
def test_wrong_number_of_defaults_is_rejected(count: int):
    pages = tuple(
        PageSpec(lambda: None, f"P{i}", "i", f"p{i}", default=i < count) for i in range(3)
    )
    with pytest.raises(ValueError, match="exatamente 1 pagina default"):
        validate(pages)


class TestSupervisorDiagnose:
    """O backend offline tem tres causas distintas; a UI precisa separa-las."""

    @staticmethod
    def _sup(home, *, up=False):
        from musicgen.server.supervisor import AceStepSupervisor

        sup = AceStepSupervisor(home, "http://127.0.0.1:8001")
        sup.is_up = lambda timeout=3.0: up  # type: ignore[method-assign]
        return sup

    def test_running_backend_has_no_steps(self):
        assert self._sup(None, up=True).diagnose() == []

    def test_unconfigured_home_points_to_setup_script(self):
        steps = self._sup(None).diagnose()
        assert any("setup.ps1" in s for s in steps)
        assert any("MUSICGEN_ACESTEP_HOME" in s for s in steps)

    def test_missing_folder_is_distinguished(self, tmp_path):
        steps = self._sup(tmp_path / "nao-existe").diagnose()
        assert any("nao existe" in s for s in steps)

    def test_wrong_folder_is_distinguished(self, tmp_path):
        steps = self._sup(tmp_path).diagnose()
        assert any("pyproject.toml" in s for s in steps)

    def test_installed_but_stopped_gives_start_command(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        steps = self._sup(tmp_path).diagnose()
        assert any("uv run acestep-api" in s for s in steps)
        assert any("MUSICGEN_ACESTEP_BASE_URL" in s for s in steps)

"""Sanitização de HTML (AutoSEO / BabyLoveGrowth / CEO / HeyCatch) e chave HeyCatch só no ambiente."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from html_safe import sanitize_html

SUJO = ('<h1>T</h1><p onclick="x()">olá <a href="javascript:alert(1)">l</a> '
        '<a href="https://ext.com/x">e</a></p><script>alert(1)</script><iframe src="//e"></iframe>'
        '<img src="data:text/html,x" onerror="y()" alt="a"><style>p{}</style><svg onload="z()"></svg>')


def test_remove_vetores_xss():
    out = sanitize_html(SUJO)
    for bad in ("<script", "<iframe", "onclick", "onerror", "onload", "javascript:", "data:", "<style", "<svg", "<h1"):
        assert bad not in out
    assert "olá" in out and 'rel="noopener noreferrer"' in out


def test_conserva_conteudo_legitimo():
    out = sanitize_html('<h2 id="a">Título</h2><ul><li><strong>x</strong></li></ul><table><tr><td>1</td></tr></table>')
    assert '<h2 id="a">' in out and "<li>" in out and "<td>1</td>" in out


def test_vazio():
    assert sanitize_html("") == "" and sanitize_html(None) == ""


def test_chave_heycatch_so_no_ambiente(monkeypatch):
    import pytest
    pytest.importorskip("httpx")
    import routes.heycatch_blog as hb
    monkeypatch.delenv("HEYCATCH_API_KEY", raising=False)
    assert hb._key() == ""
    monkeypatch.setenv("HEYCATCH_API_KEY", " abc ")
    assert hb._key() == "abc"
    assert "hck_lv_" not in Path(hb.__file__).read_text()

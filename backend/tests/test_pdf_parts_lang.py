"""20/11: ZIP para PDF > 30 folhas; ficheiros do orçamento na língua do documento/empresa; imagens ligadas por defeito."""
import io
import zipfile

import pymupdf

from engines import images3d
from engines.assistant_quote_exports import _export_lang
from engines.pdf_parts import split_zip


def _pdf(n):
    d = pymupdf.open()
    for i in range(n):
        d.new_page().insert_text((72, 72), f"folha {i + 1}")
    return d.tobytes()


def test_pdf_ate_30_folhas_sem_zip():
    assert split_zip(_pdf(30), "Processo.pdf") is None


def test_pdf_com_61_folhas_da_zip_com_completo_e_3_partes():
    z = zipfile.ZipFile(io.BytesIO(split_zip(_pdf(61), "Processo_de_estudo.pdf")))
    names = sorted(z.namelist())
    assert "Processo_de_estudo.pdf" in names and len(names) == 4
    parts = [n for n in names if "_parte_" in n]
    pages = [pymupdf.open(stream=z.read(n), filetype="pdf").page_count for n in sorted(parts)]
    assert sorted(pages) == [1, 30, 30] and any("folhas_31-60" in n for n in parts)


def test_lingua_dos_ficheiros_e_a_do_documento_e_da_empresa_nao_a_do_ecra():
    assert _export_lang({}, {"country": "PT"}, "fr-FR") == "pt"           # ecrã em francês, empresa portuguesa → PT
    assert _export_lang({"lang": "fr"}, {"country": "PT"}, "fr-FR") == "fr"  # documento francês explícito
    assert _export_lang({}, {"country": "FR"}, None) == "fr"
    assert _export_lang({}, {"country": "PT"}, "en") == "en"              # inglês escolhido no ecrã


def test_imagens_3d_ligadas_por_defeito(monkeypatch):
    monkeypatch.delenv("CP_3D_IMAGES", raising=False)
    assert images3d.enabled()
    monkeypatch.setenv("CP_3D_IMAGES", "0")
    assert not images3d.enabled()

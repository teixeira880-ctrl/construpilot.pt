"""Correções do Assistente trazidas do .fr: motores disponíveis para todas as contas, regras de encaminhamento,
argumentos null preenchidos, documentos com tabelas verdadeiras e sem caracteres vazios."""
import os

import pytest

for _k, _v in {"MONGO_URL": "mongodb://localhost:27017", "DB_NAME": "t", "JWT_SECRET": "x"}.items():
    os.environ.setdefault(_k, _v)


def test_fill_nullable():
    from engines.assistant_workspace import _fill_nullable
    sch = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": ["number", "null"]}}, "required": ["a", "b"]}
    args = {"a": "x"}
    _fill_nullable(sch, args)
    assert args == {"a": "x", "b": None}


def test_protocolo_encaminha_para_os_motores():
    from engines.assistant_state import PROTOCOL
    for tool in ("calcul_piso_radiante", "calcul_lotes_tecnicos", "pre_certificado_reh", "calcul_structure", "draw_window_detail"):
        assert tool in PROTOCOL
    assert "planta cotada" in PROTOCOL


def test_documento_tabela_real_sem_emojis():
    fitz = pytest.importorskip("fitz")
    from engines.assistant_files import build_document_pdf
    pdf = build_document_pdf("Teste", "| A | B |\n|---|---|\n| 1 | 2 |\n\n```\n┌──┐\n└──┘\n```\nok ✅ 🔥")
    txt = fitz.open(stream=pdf, filetype="pdf")[0].get_text()
    assert "A" in txt and "|" not in txt.split("Teste", 1)[1].split("+")[0] and "🔥" not in txt and "página 1" in txt


def test_motores_para_particulares_e_profissionais():
    A = pytest.importorskip("routes.assistant")
    for u in ({"user_id": "u", "account_type": "particulier"}, {"user_id": "u", "account_type": "pro", "role": "admin"}):
        names = {t.get("name") for t in A.tools_for(u)}
        assert {"calcul_piso_radiante", "calcul_lotes_tecnicos", "draw_window_detail", "edit_image_from_photo"} <= names

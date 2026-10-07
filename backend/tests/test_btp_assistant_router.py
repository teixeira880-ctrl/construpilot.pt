"""Testes de classificação de modo e lógica base do router do Assistente BTP."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.btp_assistant.router import classificar_modo  # noqa: E402
from engines.btp_assistant.types import Attachment  # noqa: E402


class TestClassificarModo:
    @pytest.mark.parametrize(
        "prompt",
        [
            "Qual é a altura mínima de pé-direito?",
            "Explica-me o Eurocódigo 2.",
            "Como se arma uma laje maciça?",
            "O que é o betão C25/30?",
        ],
    )
    def test_perguntas_abertas_viram_conversa(self, prompt):
        assert classificar_modo(user_prompt=prompt, anexos=None) == "conversa"

    @pytest.mark.parametrize(
        "prompt",
        [
            "Cria um orçamento de teste para o cliente Silva",
            "Calcula o metrado desta parede",
            "Estimar custo de obra T3 150 m²",
            "Quanto custa o bloco PP 20?",
            "Preço do cimento hoje",
            "Abre o módulo de orçamentos",
            "Exporta para Excel",
            "Adiciona 10 un de pilar ao último orçamento",
        ],
    )
    def test_pedidos_com_accao_viram_calculo(self, prompt):
        assert classificar_modo(user_prompt=prompt, anexos=None) == "calculo"

    @pytest.mark.parametrize(
        "prompt",
        [
            "Analisa esta planta",
            "Esta é uma planta Autodesk em Revit",
            "Explicação geométrica",
        ],
    )
    def test_pedidos_sobre_planta_sem_anexo_viram_plano(self, prompt):
        assert classificar_modo(user_prompt=prompt, anexos=None) == "plano"

    def test_qualquer_anexo_forca_modo_plano(self):
        a = Attachment(
            filename="x.png", mime_type="image/png", data_b64="aGVsbG8=",
        )
        # Mesmo que o prompt seria 'conversa', anexo força 'plano'
        assert classificar_modo(
            user_prompt="Isto é só uma pergunta geral", anexos=[a],
        ) == "plano"

"""Gerador de fixture sintética PT para o BET-PT Agent (L1.6).

Produz:
    - `arquitectura.pdf` — moradia unifamiliar típica PT (cave + R/C + 1º
      andar + sótão habitável), estrutura reticulada BA, lajes aligeiradas,
      cobertura inclinada telha cerâmica, alvenaria tijolo cerâmico furado.
    - `geotecnico.pdf` — estudo com tensão admissível, cota fundação, nível
      freático, contenções.
    - `brief.json` — hipóteses do utilizador (laje aligeirada obrigatória,
      tijolo furado 15 cm, zona sísmica, classe de solo).
    - `fixture_defects.md` — documenta cada defeito intencional.

Gera-se de forma determinística (sem randomness). Executar:
    python -m tests.fixtures.bet_agent.generate_moradia_pt

Zero PII. Zero dados reais. Zero dependências LLM.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


FIXTURE_DIR = Path(__file__).parent / "moradia_pt_reticular_r2_cave_sotao"

PAGE_W, PAGE_H = landscape(A3)  # 420 × 297 mm aprox


def _header(c: canvas.Canvas, title: str, page: int) -> None:
    c.setFont("Helvetica-Bold", 14)
    c.drawString(15 * mm, (PAGE_H / mm - 15) * mm, title)
    c.setFont("Helvetica", 8)
    c.drawString(15 * mm, (PAGE_H / mm - 22) * mm,
                 "Fixture sintética bet_agent — ZERO PII — página " + str(page))


def _footer(c: canvas.Canvas) -> None:
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(15 * mm, 8 * mm,
                 "Fixture gerada para testes — não constitui projecto real.")


# ---------------------------------------------------------------------------
# Planta R/C (defeitos intencionais 1, 2 e 5)
# ---------------------------------------------------------------------------

def _page_planta_rc(c: canvas.Canvas) -> None:
    _header(c, "Planta R/C — Moradia Martins Fixture", 1)
    # Desenha contorno externo da casa 12 × 8 m (escala 1:50 ⇒ 240 × 160 mm)
    x0, y0 = 30 * mm, 50 * mm
    w, h = 240 * mm, 160 * mm
    c.setLineWidth(1.5)
    c.rect(x0, y0, w, h)

    # Divisões internas
    c.setLineWidth(0.5)
    # Parede intermédia horizontal a 5m (100 mm) do fundo
    c.line(x0, y0 + 100 * mm, x0 + w, y0 + 100 * mm)
    # Parede vertical a 6m (120 mm) do inicio
    c.line(x0 + 120 * mm, y0, x0 + 120 * mm, y0 + 100 * mm)

    # Portão de garagem (defeito 1: contado 2x em R/C e Cave)
    c.setLineWidth(1.0)
    c.rect(x0 + 10 * mm, y0, 60 * mm, 2 * mm)  # abertura 3m na parede inferior
    c.setFont("Helvetica", 7)
    c.drawString(x0 + 20 * mm, y0 - 6 * mm, "Portao garagem 3.00m")

    # Vão janela com nembo negativo (defeito 2)
    c.rect(x0 + 150 * mm, y0, 80 * mm, 2 * mm)  # abertura janela larga 4m
    c.rect(x0 + 155 * mm, y0, 70 * mm, 2 * mm)  # abertura sobreposta ⇒ nembo "entre" é negativo
    c.drawString(x0 + 160 * mm, y0 - 6 * mm, "Janela com nembo A CONFIRMAR")

    # Cotas parciais vs total (defeito 5): parciais 3.00 + 4.00 declaradas,
    # mas total declarado 7.50 (soma = 7.00, delta = 50 cm > 2 cm).
    c.setFont("Helvetica", 8)
    c.drawString(x0 + 5 * mm, y0 + h + 12 * mm, "3.00")
    c.line(x0, y0 + h + 10 * mm, x0 + 60 * mm, y0 + h + 10 * mm)
    c.drawString(x0 + 65 * mm, y0 + h + 12 * mm, "4.00")
    c.line(x0 + 60 * mm, y0 + h + 10 * mm, x0 + 140 * mm, y0 + h + 10 * mm)
    c.drawString(x0 + 60 * mm, y0 + h + 18 * mm, "TOTAL = 7.50 (declarado)")
    c.line(x0, y0 + h + 15 * mm, x0 + 140 * mm, y0 + h + 15 * mm)

    # Legenda compartimentos
    c.setFont("Helvetica", 8)
    c.drawString(x0 + 20 * mm, y0 + 40 * mm, "Sala")
    c.drawString(x0 + 20 * mm, y0 + 130 * mm, "Cozinha")
    c.drawString(x0 + 170 * mm, y0 + 40 * mm, "WC")
    c.drawString(x0 + 170 * mm, y0 + 130 * mm, "Garagem")

    _footer(c)


# ---------------------------------------------------------------------------
# Planta Cave (defeito 1: portão de garagem repetido aqui)
# ---------------------------------------------------------------------------

def _page_planta_cave(c: canvas.Canvas) -> None:
    _header(c, "Planta Cave — Moradia Martins Fixture", 2)
    x0, y0 = 30 * mm, 50 * mm
    w, h = 240 * mm, 160 * mm
    c.setLineWidth(1.5)
    c.rect(x0, y0, w, h)
    c.setFont("Helvetica", 8)
    c.drawString(x0 + 100 * mm, y0 + 80 * mm, "Garagem / arrumos")

    # Portão de garagem DUPLICADO na mesma parede (defeito 1).
    c.setLineWidth(1.0)
    c.rect(x0 + 10 * mm, y0, 60 * mm, 2 * mm)  # igual à R/C
    c.setFont("Helvetica", 7)
    c.drawString(x0 + 20 * mm, y0 - 6 * mm, "Portao garagem 3.00m (DUP)")

    _footer(c)


# ---------------------------------------------------------------------------
# Planta Sótão (defeito 3: cota ambígua)
# ---------------------------------------------------------------------------

def _page_planta_sotao(c: canvas.Canvas) -> None:
    _header(c, "Planta Sotao — Moradia Martins Fixture", 3)
    x0, y0 = 30 * mm, 50 * mm
    w, h = 240 * mm, 100 * mm
    c.setLineWidth(1.5)
    c.rect(x0, y0, w, h)
    c.setFont("Helvetica", 8)
    c.drawString(x0 + 100 * mm, y0 + 50 * mm, "Sotao habitavel (?)")
    # Defeito 3: altura livre mal cotada (texto ambíguo)
    c.drawString(x0 + 10 * mm, y0 - 10 * mm,
                 "Altura livre: 1.70 a 2.20 m (variavel) - A CONFIRMAR em corte")
    _footer(c)


# ---------------------------------------------------------------------------
# Corte com escada mal dimensionada (defeito 4)
# ---------------------------------------------------------------------------

def _page_corte_escada(c: canvas.Canvas) -> None:
    _header(c, "Corte AA — Escada Moradia Martins Fixture", 4)
    x0, y0 = 30 * mm, 60 * mm
    c.setLineWidth(1.5)
    # Marca cotas
    c.setFont("Helvetica", 9)
    c.drawString(x0, y0 - 10 * mm, "Pé-direito R/C = 2.70 m")
    c.drawString(x0, y0 + 150 * mm, "Pé-direito 1º andar = 2.70 m")
    # Escada: abertura só 1.20 m (defeito 4). Delta_h = 3.0 m ⇒ precisa ~4 m.
    c.drawString(x0, y0 + 30 * mm,
                 "Escada: abertura disponivel = 1.20 m, delta_h = 3.00 m")
    c.rect(x0 + 60 * mm, y0 + 30 * mm, 40 * mm, 60 * mm)
    _footer(c)


def _page_quadro_areas(c: canvas.Canvas) -> None:
    _header(c, "Quadro de areas — Moradia Martins Fixture", 5)
    c.setFont("Helvetica", 10)
    data = [
        ("Compartimento", "Area (m2)"),
        ("Sala", "25.00"),
        ("Cozinha", "15.00"),
        ("WC", "4.50"),
        ("Garagem", "30.00"),
        ("Quarto 1", "14.00"),
        ("Quarto 2", "12.00"),
        ("Sotao", "40.00"),
    ]
    y = 220 * mm
    for row in data:
        c.drawString(30 * mm, y, row[0])
        c.drawString(100 * mm, y, row[1])
        y -= 8 * mm
    _footer(c)


# ---------------------------------------------------------------------------
# Geotécnico
# ---------------------------------------------------------------------------

def _page_geotecnico(c: canvas.Canvas) -> None:
    _header(c, "Estudo geotecnico — Moradia Martins Fixture", 1)
    c.setFont("Helvetica", 10)
    lines = [
        "Lote: moradia unifamiliar, 2 pisos acima do solo + cave.",
        "Prof. de reconhecimento: 8.00 m.",
        "Nivel freatico detectado a: -4.00 m (abaixo do terreno natural).",
        "Tensao admissivel na cota de fundacao (-2.50 m): 200 kPa.",
        "Classe de solo (NP EN 1998-1): C.",
        "Contencoes previstas: muro em betao armado em perimetro da cave.",
        "Observacoes: proximidade de edificio vizinho a Oeste a 2.5 m.",
    ]
    y = 220 * mm
    for ln in lines:
        c.drawString(30 * mm, y, ln)
        y -= 10 * mm
    _footer(c)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def build_fixture(target_dir: Path | None = None) -> dict[str, Path]:
    tgt = Path(target_dir) if target_dir else FIXTURE_DIR
    tgt.mkdir(parents=True, exist_ok=True)

    # Arquitectura (5 páginas).
    arch_path = tgt / "arquitectura.pdf"
    c = canvas.Canvas(str(arch_path), pagesize=landscape(A3))
    _page_planta_rc(c);           c.showPage()
    _page_planta_cave(c);         c.showPage()
    _page_planta_sotao(c);        c.showPage()
    _page_corte_escada(c);        c.showPage()
    _page_quadro_areas(c);        c.showPage()
    c.save()

    # Geotecnico (1 página).
    geo_path = tgt / "geotecnico.pdf"
    c = canvas.Canvas(str(geo_path), pagesize=landscape(A3))
    _page_geotecnico(c)
    c.showPage()
    c.save()

    # Brief do utilizador.
    brief = {
        "materials": {
            "slab_type": "aligeirada_vigotas_abobadilhas",
            "masonry_type": "tijolo_ceramico_furado_15",
            "concrete_class": "C25/30",
            "steel_class": "A500 NR",
            "roof_type": "inclinada_telha_ceramica",
        },
        "water_table_depth_m": 4.0,
        "seismic": {"zone": "1.3", "soil_class": "C", "municipio": "Lisboa"},
        "room_uses": {
            "sala": "sala",
            "cozinha": "cozinha",
            "wc": "wc",
            "garagem": "garagem",
            "quarto_1": "quarto",
            "quarto_2": "quarto",
            "sotao": "sotao_habitavel",
        },
        "requested_deliverables": [
            "memoria_descritiva",
            "planta_fundacoes",
            "plantas_estrutura_piso",
            "quadro_pilares",
            "mapa_armaduras",
            "cortes_pormenores",
            "cobertura",
            "rede_aguas",
            "rede_esgotos_domesticos",
            "rede_aguas_pluviais",
            "ited_simplificado",
            "verificacao_sismica_np_en_1998_1",
            "orcamento_ligado_mapa",
            "minuta_termo_responsabilidade",
        ],
        "notes": "Moradia unifamiliar reticulada. Pretende-se tambem analise termica REH (fora de ambito).",
    }
    brief_path = tgt / "brief.json"
    brief_path.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")

    # Documentação dos defeitos.
    defects = """# Defeitos intencionais na fixture Moradia Martins

Esta fixture é sintética e contém 5 defeitos propositadamente colocados para
validar os checks determinísticos do BET-PT Agent.

| # | Defeito | Página | Check esperado | Severidade |
|---|---------|--------|----------------|------------|
| 1 | Portão de garagem contado 2× (R/C + Cave) | arquitectura.pdf p.1 e p.2 | GEO-002 | grave |
| 2 | Nembo entre janelas com largura ≤ 0 (abertura sobreposta) | arquitectura.pdf p.1 | GEO-001 | grave |
| 3 | Sótão com cota ambígua "1.70 a 2.20 m" | arquitectura.pdf p.3 | SEM-002 ou pergunta on-the-fly | grave |
| 4 | Escada com abertura 1.20 m para delta_h = 3.00 m (não cabe) | arquitectura.pdf p.4 | GEO-004 | bloqueante |
| 5 | Cotas parciais 3.00 + 4.00 = 7.00 mas total declarado 7.50 | arquitectura.pdf p.1 | GEO-007 | grave |

Também inclui, no brief.json, um pedido fora de âmbito ("análise térmica REH")
para validar SEM-005 (aviso).

Nenhum destes defeitos são bugs do gerador — são defeitos **deliberados** para
testar que o pipeline os detecta.
"""
    (tgt / "fixture_defects.md").write_text(defects, encoding="utf-8")

    return {
        "arquitectura": arch_path,
        "geotecnico": geo_path,
        "brief": brief_path,
        "defects": tgt / "fixture_defects.md",
    }


if __name__ == "__main__":  # pragma: no cover
    paths = build_fixture()
    for k, v in paths.items():
        print(f"{k}: {v}")

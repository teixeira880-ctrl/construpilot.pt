"""Seed idempotente da colecção `materials_pt_prices` (Fase c).

Executa:
    python -m scripts.seed_materials_pt_prices
    # ou
    python scripts/seed_materials_pt_prices.py

Cada doc é actualizado por `upsert` com chave `nome_normalizado`.
A tool `obter_preco_material` espera o campo `nome` (regex-search) e
`preco_eur`, portanto garantimos esses dois campos como "canónicos" e
mantemos os metadados extra (`preco_min_eur`, `preco_max_eur`,
`categoria`, `nome_display_pt`, `fonte`, `actualizado_em`) para o
front-end e relatórios futuros.

Fonte: estimativas de mercado residencial/comercial PT para 2026
(construção nova e remodelação). Decisão 3a: apenas `regiao_pt =
"nacional"`, 1 doc por material (~50 docs totais).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# Garante que o `backend/` está no sys.path quando executado directamente
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("seed.materials_pt_prices")

# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
# Cada tuplo: (categoria, nome_display_pt, unidade, min, med, max, notas_pt)
MATERIAIS: list[tuple[str, str, str, float, float, float, str]] = [
    # ----- Betão (€/m³, central dosada entregue em obra, PT 2026) -----
    ("betao", "Betão C12/15",   "m3", 70.0,  78.0,  88.0,  "Enchimento, regularização, não estrutural."),
    ("betao", "Betão C16/20",   "m3", 75.0,  82.0,  92.0,  "Pavimentos leves e massames."),
    ("betao", "Betão C20/25",   "m3", 80.0,  88.0,  98.0,  "Fundações correntes residenciais."),
    ("betao", "Betão C25/30",   "m3", 85.0,  95.0,  110.0, "Estrutura corrente residencial (lajes, pilares)."),
    ("betao", "Betão C30/37",   "m3", 95.0,  108.0, 125.0, "Elementos expostos, pré-esforço leve."),
    ("betao", "Betão C35/45",   "m3", 110.0, 125.0, 145.0, "Obras de arte, elementos de grande solicitação."),

    # ----- Aço A500NR (€/kg, mercado spot PT 2026) -----
    ("aco", "Aço A500NR ∅6",   "kg", 1.05, 1.20, 1.40, "Varão nervurado para armaduras ligeiras."),
    ("aco", "Aço A500NR ∅8",   "kg", 1.00, 1.15, 1.35, "Varão nervurado estribos e armaduras correntes."),
    ("aco", "Aço A500NR ∅10",  "kg", 0.95, 1.10, 1.30, "Varão corrente lajes/pilares."),
    ("aco", "Aço A500NR ∅12",  "kg", 0.95, 1.08, 1.28, "Varão corrente estrutural."),
    ("aco", "Aço A500NR ∅16",  "kg", 0.95, 1.08, 1.28, "Varão principal estrutura."),
    ("aco", "Aço A500NR ∅20",  "kg", 0.95, 1.10, 1.30, "Pilares e vigas de maior inércia."),
    ("aco", "Aço A500NR ∅25",  "kg", 1.00, 1.15, 1.35, "Elementos muito solicitados."),

    # ----- Alvenaria (€/m² acabado, mão-de-obra NÃO incluída) -----
    ("alvenaria", "Tijolo cerâmico 7 cm",      "m2", 7.0,  9.0,  12.0, "Divisórias leves interiores."),
    ("alvenaria", "Tijolo cerâmico 11 cm",     "m2", 9.0,  12.0, 15.0, "Paredes interiores correntes."),
    ("alvenaria", "Tijolo cerâmico 15 cm",     "m2", 12.0, 15.0, 18.0, "Panos exteriores de parede dupla."),
    ("alvenaria", "Tijolo cerâmico 22 cm",     "m2", 16.0, 20.0, 24.0, "Paredes exteriores em pano simples."),
    ("alvenaria", "Tijolo cerâmico 30 cm",     "m2", 22.0, 26.0, 32.0, "Paredes resistentes com elevado isolamento."),
    ("alvenaria", "Bloco térmico 25 cm",       "m2", 24.0, 29.0, 36.0, "Alvenaria térmica melhorada."),
    ("alvenaria", "Bloco térmico 30 cm",       "m2", 28.0, 34.0, 42.0, "Pano simples alto desempenho térmico."),

    # ----- Isolamento (€/m² material, não inclui aplicação) -----
    ("isolamento", "XPS 3 cm",  "m2", 6.0,  7.5,  9.5,  "Isolamento sob pavimento ou paredes enterradas."),
    ("isolamento", "XPS 4 cm",  "m2", 7.5,  9.0,  11.5, "Isolamento ETICS fachada ventilada."),
    ("isolamento", "XPS 5 cm",  "m2", 9.0,  11.0, 13.5, "ETICS corrente."),
    ("isolamento", "XPS 6 cm",  "m2", 10.5, 13.0, 16.0, "ETICS elevado desempenho."),
    ("isolamento", "EPS 3 cm",  "m2", 2.5,  3.5,  4.5,  "Isolamento leve interior / tectos."),
    ("isolamento", "EPS 5 cm",  "m2", 4.0,  5.5,  7.0,  "Isolamento ETICS economia."),
    ("isolamento", "EPS 6 cm",  "m2", 5.0,  6.5,  8.5,  "ETICS reforçada."),
    ("isolamento", "Lã mineral 4 cm", "m2", 4.5, 6.0, 8.0,  "Isolamento acústico/divisórias."),
    ("isolamento", "Lã mineral 6 cm", "m2", 6.0, 8.0, 10.5, "Isolamento térmico tectos falsos."),
    ("isolamento", "Lã mineral 10 cm","m2", 9.0, 12.0, 15.0, "Coberturas inclinadas, bons desempenhos."),

    # ----- Revestimentos (€/m², material + consumíveis) -----
    ("revestimento", "Reboco de cimento",        "m2", 5.5,  7.5,  10.0, "Reboco corrente paredes exteriores."),
    ("revestimento", "Reboco de cal hidráulica", "m2", 7.0,  9.5,  13.0, "Reabilitação, paredes antigas."),
    ("revestimento", "Pintura silicatos",        "m2", 6.0,  8.5,  12.0, "Fachadas permeáveis ao vapor."),
    ("revestimento", "Pintura plástica interior","m2", 2.5,  4.0,  6.5,  "Pintura corrente, 2 demãos."),
    ("revestimento", "Azulejo cerâmico padrão",  "m2", 12.0, 18.0, 28.0, "Casa de banho / cozinha standard."),
    ("revestimento", "Mosaico cerâmico",         "m2", 10.0, 16.0, 25.0, "Pavimento ou parede."),

    # ----- Cobertura (€/m²) -----
    ("cobertura", "Telha lusa",     "m2", 8.5,  11.0, 14.0, "Cobertura inclinada tradicional."),
    ("cobertura", "Telha marselha", "m2", 10.0, 13.0, 17.0, "Cobertura inclinada, cor sob consulta."),
    ("cobertura", "Subtelha",       "m2", 6.5,  8.5,  11.0, "Painel sub-cobertura."),

    # ----- Carpintaria (€/unidade padrão) -----
    ("carpintaria", "Porta interior lacada",  "unid", 150.0, 220.0, 320.0, "Folha + aro + ferragens."),
    ("carpintaria", "Porta blindada entrada", "unid", 650.0, 950.0, 1500.0, "Classe 3+ anti-arrombamento."),
    ("carpintaria", "Janela PVC dupla",       "unid", 320.0, 450.0, 650.0, "1200×1200 batente ou oscilo-batente."),
    ("carpintaria", "Janela alumínio dupla",  "unid", 420.0, 580.0, 850.0, "1200×1200 corte térmico."),

    # ----- Sanitários (€/unidade, só peça) -----
    ("sanitario", "Sanita suspensa",        "unid", 220.0, 320.0, 480.0, "Cerâmica branca + autoclismo embutido."),
    ("sanitario", "Lavatório padrão",       "unid", 90.0,  140.0, 220.0, "Cerâmica branca, apoio móvel."),
    ("sanitario", "Torneira monocomando",   "unid", 60.0,  95.0,  180.0, "Lavatório ou bidé, gama média."),
    ("sanitario", "Base de duche cerâmica", "unid", 180.0, 260.0, 400.0, "90×90 cm ou 90×120 cm."),

    # ----- Pavimentos (€/m², só material) -----
    ("pavimento", "Soalho flutuante AC4",    "m2", 15.0, 22.0, 32.0, "Laminado residencial corrente."),
    ("pavimento", "Vinílico LVT clicado",    "m2", 20.0, 28.0, 42.0, "Alto tráfego residencial."),
    ("pavimento", "Microcimento aplicado",   "m2", 60.0, 85.0, 120.0, "Material + fundo + protecção."),
    ("pavimento", "Pedra calcária 2 cm",     "m2", 35.0, 50.0, 75.0, "Pavimentos interiores nobres."),
    ("pavimento", "Argamassa de regularização","m2", 4.5, 6.5, 9.0, "Enchimento 3 cm para pavimentos."),
]


def _slug(txt: str) -> str:
    norm = unicodedata.normalize("NFKD", txt)
    norm = norm.encode("ascii", "ignore").decode("ascii").lower()
    out = []
    for ch in norm:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "/", "_", ".", "∅"):
            out.append("_")
    while "__" in "".join(out):
        out = list("".join(out).replace("__", "_"))
    return "".join(out).strip("_")


async def seed() -> None:
    # Imports locais para apanhar o `.env` dinamicamente
    from core.db import db  # noqa: WPS433

    agora = datetime.now(timezone.utc)
    inserted = 0
    updated = 0
    for categoria, nome_display, unidade, pmin, pmed, pmax, notas in MATERIAIS:
        nome_norm = _slug(nome_display)
        doc = {
            "nome_normalizado": nome_norm,
            "nome": nome_display,  # usado por `obter_preco_material` (regex)
            "nome_display_pt": nome_display,
            "categoria": categoria,
            "unidade": unidade,
            "preco_eur": pmed,  # chave canónica lida pela tool
            "preco_medio_eur": pmed,
            "preco_min_eur": pmin,
            "preco_max_eur": pmax,
            "regiao_pt": "nacional",
            "regiao": "nacional",  # alias retrocompat
            "fonte_dado": "mercado_pt_2026_estimativa",  # NÃO usar `fonte` — colide com a tool
            "actualizado_em": agora,
            "notas_pt": notas,
        }
        res = await db.materials_pt_prices.update_one(
            {"nome_normalizado": nome_norm, "regiao_pt": "nacional"},
            {"$set": doc, "$setOnInsert": {"criado_em": agora}},
            upsert=True,
        )
        if res.upserted_id is not None:
            inserted += 1
        elif res.modified_count > 0:
            updated += 1

    total = await db.materials_pt_prices.count_documents({})
    logger.info(
        "Seed concluído — inseridos=%d, actualizados=%d, total colecção=%d",
        inserted, updated, total,
    )
    assert total >= 50, f"Esperado >= 50 docs, obtido {total}."


if __name__ == "__main__":
    # Carrega .env (quando corrido fora do uvicorn)
    try:
        from dotenv import load_dotenv  # noqa: WPS433
        load_dotenv(_BACKEND_DIR / ".env")
    except ImportError:
        pass
    if not os.environ.get("MONGO_URL"):
        os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    if not os.environ.get("DB_NAME"):
        os.environ.setdefault("DB_NAME", "test_database")
    asyncio.run(seed())

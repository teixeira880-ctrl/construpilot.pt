"""Importa a biblioteca PT 2026 (`biblioteca_pt_2026.xlsx`) para MongoDB.

Estratégia A1: merge aditivo em `shared_library_items` por `code`
(PT-XX-YYY-ZZZZ). Items existentes sem `code` correspondente ficam intactos.

Estratégia C1: adiciona os coeficientes regionais PT
(`coef_lisboa/coef_porto/coef_algarve/coef_interior`) sem remover os antigos.

Execução:
    CLI:  python -m scripts.import_biblioteca_pt_2026
    HTTP: POST /api/admin/migrations/run  (Bearer admin)
"""
from __future__ import annotations

import asyncio
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

XLSX_PATH = Path("/app/backend/assets/biblioteca_pt_2026.xlsx")

# Mapa gama Excel → sufixo dos preços na base
_GAMA_KEY = {"Económico": "low", "Standard": "mid", "Premium": "high"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(v: Any) -> float | None:
    if v in (None, "", "None"):
        return None
    try:
        return round(float(str(v).replace(",", ".")), 2)
    except Exception:
        return None


def _parse_coeficientes(ws) -> dict:
    """Extrai coeficientes regionais da folha COEFICIENTES.
    Retorna {'lisboa': 1.15, 'porto': 1.08, 'algarve': 1.1, 'interior': 0.9}
    (fallback razoável se alguma linha estiver ausente)."""
    coefs = {"lisboa": None, "porto": None, "algarve": None, "interior": None}
    for r in range(2, ws.max_row + 1):
        zona = (ws.cell(row=r, column=1).value or "").lower()
        coef = _num(ws.cell(row=r, column=2).value)
        if coef is None:
            continue
        if "lisboa" in zona or "cascais" in zona:
            coefs["lisboa"] = coef
        elif "porto" in zona or "gaia" in zona:
            coefs["porto"] = coef
        elif "algarve" in zona or "faro" in zona:
            coefs["algarve"] = coef
        elif "interior" in zona or "alentejo" in zona or "beira" in zona:
            coefs["interior"] = coef
    # fallbacks
    coefs["lisboa"] = coefs["lisboa"] or 1.15
    coefs["porto"] = coefs["porto"] or 1.08
    coefs["algarve"] = coefs["algarve"] or 1.10
    coefs["interior"] = coefs["interior"] or 0.90
    return coefs


def _parse_biblioteca_precos(ws) -> list[dict]:
    """Colapsa as 3 gamas de cada trabalho num único doc.

    O `Código` no Excel é único por (trabalho, gama) (`PT-01-001-0001` Económico,
    `PT-01-001-0002` Standard, `PT-01-001-0003` Premium). O prefixo `PT-XX-YYY`
    (sem o sufixo `-ZZZZ`) identifica o trabalho e é usado como chave.
    """
    grouped: dict[str, dict] = {}
    for r in range(2, ws.max_row + 1):
        code_full = (ws.cell(row=r, column=1).value or "").strip()
        if not code_full:
            continue
        # PT-01-001-0001 → chave PT-01-001
        code_base = code_full.rsplit("-", 1)[0] if "-" in code_full else code_full
        categoria = (ws.cell(row=r, column=2).value or "").strip() or "Diversos"
        designation = (ws.cell(row=r, column=3).value or "").strip()
        if not designation:
            continue
        gama = (ws.cell(row=r, column=4).value or "").strip()
        unit = (ws.cell(row=r, column=5).value or "u").strip()
        preco_med = _num(ws.cell(row=r, column=8).value)
        mat = _num(ws.cell(row=r, column=10).value)
        mao = _num(ws.cell(row=r, column=11).value)
        equip = _num(ws.cell(row=r, column=12).value)
        fonte = (ws.cell(row=r, column=19).value or "").strip() or None
        url_fonte = (ws.cell(row=r, column=20).value or "").strip() or None
        obs = (ws.cell(row=r, column=21).value or "").strip() or None
        ref_date = (ws.cell(row=r, column=17).value or "").strip() or None

        doc = grouped.setdefault(code_base, {
            "code": code_base, "category": categoria,
            "designation": designation, "unit": unit,
            "vat_rate": 23,
            "source": fonte, "source_url": url_fonte,
            "ref_date": ref_date, "notes": obs,
        })

        suffix = _GAMA_KEY.get(gama)
        if suffix and preco_med is not None:
            doc[f"price_{suffix}"] = preco_med
            if mat is not None:
                doc[f"mat_{suffix}"] = mat
            if mao is not None:
                doc[f"labor_{suffix}"] = mao
            if equip is not None:
                doc[f"equip_{suffix}"] = equip
    return list(grouped.values())


def _parse_piscinas_construcao(ws) -> list[dict]:
    """Estrutura já achatada: 1 linha por trabalho com low/med/high."""
    out = []
    for r in range(2, ws.max_row + 1):
        code = (ws.cell(row=r, column=1).value or "").strip()
        if not code:
            continue
        categoria = (ws.cell(row=r, column=2).value or "Piscinas – Construção e Equipamentos").strip()
        designation = (ws.cell(row=r, column=3).value or "").strip()
        if not designation:
            continue
        unit = (ws.cell(row=r, column=4).value or "u").strip()
        p_low = _num(ws.cell(row=r, column=5).value)
        p_mid = _num(ws.cell(row=r, column=6).value)
        p_high = _num(ws.cell(row=r, column=7).value)
        mat = _num(ws.cell(row=r, column=8).value)
        mao = _num(ws.cell(row=r, column=9).value)
        equip = _num(ws.cell(row=r, column=10).value)
        obs = (ws.cell(row=r, column=13).value or "").strip() or None

        doc = {
            "code": code, "category": categoria,
            "designation": designation, "unit": unit,
            "vat_rate": 23,
            "price_low": p_low, "price_mid": p_mid, "price_high": p_high,
            "mat_mid": mat, "labor_mid": mao, "equip_mid": equip,
            "notes": obs, "ref_date": "2026-09",
        }
        out.append(doc)
    return out


def _load_docs() -> tuple[list[dict], dict]:
    import openpyxl  # lazy import
    if not XLSX_PATH.exists():
        raise FileNotFoundError(f"Ficheiro não encontrado: {XLSX_PATH}")
    wb = openpyxl.load_workbook(str(XLSX_PATH), data_only=True)
    docs = _parse_biblioteca_precos(wb["BIBLIOTECA_PRECOS"])
    docs.extend(_parse_piscinas_construcao(wb["PISCINAS_CONSTRUCAO"]))
    coefs = _parse_coeficientes(wb["COEFICIENTES"])
    return docs, coefs


async def run(db=None) -> dict:
    """Merge aditivo (upsert por `code`). Docs sem `code` correspondente ficam intactos."""
    client = None
    if db is None:
        try:
            from dotenv import load_dotenv
            env_path = Path(__file__).resolve().parents[1] / ".env"
            if env_path.exists():
                load_dotenv(env_path)
        except Exception:
            pass
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ.get("DB_NAME") or "construpilot"]

    docs, coefs = _load_docs()

    inserted = updated = 0
    for d in docs:
        # coeficientes regionais em todos os docs
        d["coef_lisboa"] = coefs["lisboa"]
        d["coef_porto"] = coefs["porto"]
        d["coef_algarve"] = coefs["algarve"]
        d["coef_interior"] = coefs["interior"]
        d["lang"] = "pt"
        d["updated_at"] = _now()

        result = await db.shared_library_items.update_one(
            {"code": d["code"]},
            {"$set": d,
             "$setOnInsert": {"item_id": "shl_" + secrets.token_hex(6),
                              "created_at": _now()}},
            upsert=True,
        )
        if result.upserted_id is not None:
            inserted += 1
        elif result.modified_count > 0 or result.matched_count > 0:
            updated += 1

    all_codes = [d["code"] for d in docs]
    preserved = await db.shared_library_items.count_documents({
        "$or": [{"code": {"$exists": False}}, {"code": {"$nin": all_codes}}]
    })
    total_in_db = await db.shared_library_items.count_documents({})
    categories = len(await db.shared_library_items.distinct("category"))

    await db.app_settings.update_one(
        {"key": "shared_library_meta"},
        {"$set": {
            "key": "shared_library_meta",
            "count": total_in_db,
            "source": "biblioteca_pt_2026.xlsx",
            "imported_at": _now(),
            "categories": categories,
        }},
        upsert=True,
    )

    if client is not None:
        client.close()

    return {
        "canonical_items": len(docs),
        "inserted": inserted,
        "updated": updated,
        "preserved": preserved,
        "total_in_db": total_in_db,
        "categories": categories,
        "regional_coefs": coefs,
    }


async def _main_cli() -> None:
    result = await run()
    print(f"[import_biblioteca_pt_2026] {result}")


if __name__ == "__main__":
    asyncio.run(_main_cli())

"""E2E Excel export: usa um plano existente ou cria um fake no DB → chama endpoint → valida xlsx."""
from __future__ import annotations

import asyncio
import io
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API = os.environ.get("REACT_APP_BACKEND_URL") or "https://construpilot-recon.preview.emergentagent.com"
EMAIL = "info@construpilot.pt"
PASSWORD = "uFuBb6Q5h1QUxCmc"


async def _ensure_fake_plan(user_id: str) -> str:
    """Cria um plano fake no DB com análise simulada, se ainda não existir."""
    from core.db import db
    plan_id = "pln_e2e_excel"
    doc = {
        "plan_id": plan_id,
        "user_id": user_id,
        "project_id": "e2e-excel-test",
        "file_name": "e2e_casa.dwg",
        "file_type": "dwg",
        "autodesk_urn": "dXJuOmFkc2sub2JqZWN0czpvcy5vYmplY3Q6ZTJl",
        "translation_status": "success",
        "model_used": "claude-opus-5-5",
        "quantities": {
            "Paredes": {"count": 40, "source": "layers"},
            "Lajes": {"count": 2, "source": "categories"},
        },
        "ai_analysis": {
            "vision": {"plan_type": "planta"},
            "synthesis": {
                "resumo": "E2E — Habitação T2 80m² em betão armado.",
                "ouvrages": [
                    {"nome": "Fundações C25/30", "quantidade": 15, "unidade": "m³", "pu_eur": 180.0, "observacoes": "E2E"},
                    {"nome": "Laje térrea massame armado", "quantidade": 80, "unidade": "m²", "pu_eur": 45.0, "observacoes": "E2E"},
                    {"nome": "Alvenaria tijolo 15cm", "quantidade": 100, "unidade": "m²", "pu_eur": 32.0, "observacoes": "E2E"},
                ],
                "normas_aplicaveis": ["RGEU", "Eurocódigo 2", "REH"],
            },
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.plans_pro.update_one({"plan_id": plan_id, "user_id": user_id}, {"$set": doc}, upsert=True)
    return plan_id


async def main() -> int:
    print(f"[STEP] Login {EMAIL}…")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{API}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if r.status_code != 200:
            print(f"[FAIL] login status={r.status_code}")
            return 1
        token = r.json()["token"]
        user_id = r.json()["user"]["user_id"]
        print(f"[OK] login OK, user_id={user_id}")

        print("[STEP] Seed plano fake no DB…")
        plan_id = await _ensure_fake_plan(user_id)
        print(f"[OK] plan_id={plan_id}")

        for iva in ("23", "6", "22"):
            print(f"\n[STEP] GET /export-excel?iva_rate={iva}")
            r = await client.get(
                f"{API}/api/plans-pro/{plan_id}/export-excel",
                params={"iva_rate": iva},
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code != 200:
                print(f"[FAIL] status={r.status_code} body={r.text[:200]}")
                return 2
            size = len(r.content)
            disp = r.headers.get("content-disposition", "")
            numero = r.headers.get("x-orc-numero")
            ht = r.headers.get("x-orc-total-ht")
            ttc = r.headers.get("x-orc-total-ttc")
            print(f"[OK] IVA {iva}% — size={size}B, Nº orç={numero}, HT={ht}€, TTC={ttc}€")
            print(f"     Content-Disposition: {disp}")

            # Guarda ficheiro
            out = f"/tmp/test_export_iva{iva}.xlsx"
            with open(out, "wb") as f:
                f.write(r.content)

            # Valida estrutura
            wb = load_workbook(io.BytesIO(r.content))
            assert wb.sheetnames == ["Resumo", "Orçamento", "Quantidades"], f"sheets inesperados: {wb.sheetnames}"
            ws = wb["Orçamento"]
            headers = [ws.cell(row=1, column=c).value for c in range(1, 10)]
            assert headers[0] == "Designação", f"header[0]={headers[0]}"
            # Verifica que IVA no cabeçalho mostra a taxa correta
            assert f"IVA ({iva}%)" == headers[5], f"IVA header: {headers[5]}"
            # 3 linhas de ouvrages
            assert ws.cell(row=2, column=1).value == "Fundações C25/30"
            print(f"[OK] Estrutura validada → guardado em {out}")

        print("\n[SUMMARY]")
        print("  Login: OK")
        print("  Seed plano: OK")
        print("  Export IVA 23%: OK")
        print("  Export IVA 6% (ARU/Madeira low): OK")
        print("  Export IVA 22% (Açores): OK")
        return 0


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)

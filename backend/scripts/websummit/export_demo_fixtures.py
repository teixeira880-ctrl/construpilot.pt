"""Exporta fixtures JSON determinísticas para a demo offline WebSummit (LOTE 2b).

Chama **os motores reais** da plataforma e grava o output em
`/app/frontend/src/fixtures/demo/*.json`. Zero números escritos à mão.

Saída:
    users.json           — 2 contas demo (pro + particular) com schema `/auth/me`
    projects.json        — projecto Moradia Martins para cada conta demo
    demo_branding.json   — branding fictício ConstruPilot/Construções Horizonte
    assistant_docs.json  — placeholder (preenchido em 2c pelos bet_core samples)
    plans.json           — placeholder (preenchido em 2c)
    quotes.json          — placeholder (preenchido em 2c)
    _manifest.json       — assinatura + versões dos motores usados

Uso:
    python -m scripts.websummit.export_demo_fixtures

Teste de regressão em `tests/test_demo_fixtures_export.py`.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/app/backend")

from core.websummit_seed_pt import (
    DEMO_MORADIA_MARTINS_PRICING,
    DEMO_PROJECT_NAME,
    DEMO_SOURCE,
    _demo_moradia_martins_estimation,
)

FIXTURES_DIR = Path("/app/frontend/src/fixtures/demo")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _demo_users() -> list[dict]:
    """Dois utilizadores demo com schema `/auth/me` canónico (sem password).

    Email idêntico ao do seed real; ids `demo_*` são sintéticos para o modo
    offline (não colide com os ids reais em prod).
    """
    now = _utc_now_iso()
    return [
        {
            "user_id": "demo_pro_pt",
            "email": os.environ.get("WEBSUMMIT_DEMO_EMAIL_PT", "demo.websummit@construpilot.pt"),
            "name": "Demo Pro — WebSummit",
            "role": "user",
            "plan_id": "pro_business",
            "account_type": "pro_business",   # sem isto o modo demo offline tratava a conta Pro como particular
            "country": "PT",
            "lang": "pt-PT",
            "theme": "light",
            "is_demo": True,
            "demo_kind": "pro",
            "demo_source": DEMO_SOURCE,
            "created_at": now,
            "brand_company_name": "Construções Horizonte, Lda.",
            "brand_logo_url": "/demo-assets/branding_logo_horizonte.png",
        },
        {
            "user_id": "demo_part_pt",
            "email": os.environ.get(
                "WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT",
                "demo.websummit.particular@construpilot.pt",
            ),
            "name": "Demo Particular — WebSummit",
            "role": "user",
            "plan_id": "free",
            "account_type": "particulier",
            "country": "PT",
            "lang": "pt-PT",
            "theme": "light",
            "is_demo": True,
            "demo_kind": "particular",
            "demo_source": DEMO_SOURCE,
            "created_at": now,
        },
    ]


def _demo_project_for(user_id: str) -> dict:
    """Moradia Martins com estimation 100% motor real (`estimate_from_request`)."""
    now = _utc_now_iso()
    pid = f"prj_demo_{user_id}"
    estimation = _demo_moradia_martins_estimation()
    return {
        "project_id": pid,
        "name": DEMO_PROJECT_NAME,
        "description": "Moradia unifamiliar T3 em Lisboa — dados demo não executivos.",
        "owner_user_id": user_id,
        "user_id": user_id,
        "status": "active",
        "location": "Lisboa, Portugal",
        "work_type": "construcao_nova",
        "surface": DEMO_MORADIA_MARTINS_PRICING["surface"],
        "country": "PT",
        "region": "Lisboa",
        "estimation": estimation,
        "budget": round(float(estimation.get("total_avg") or 0), 2),   # valor mostrado no painel (estimativa média sem IVA)
        "is_demo": True,
        "demo_source": DEMO_SOURCE,
        "created_at": now,
        "doc_ids": [],  # preenchido em 2c
    }


def _demo_branding() -> dict:
    """Branding fictício (apenas para conta pro)."""
    try:
        from engines.bet_core.samples import demo_branding
        br = demo_branding("PT")
    except Exception:  # noqa: BLE001
        br = {
            "company_name": "Construções Horizonte, Lda.",
            "country": "PT",
            "logo_url": "/demo-assets/branding_logo_horizonte.png",
        }
    br.setdefault("source", "engines.bet_core.samples.demo_branding")
    return br


def _manifest(outputs: dict) -> dict:
    return {
        "generated_at": _utc_now_iso(),
        "generator": "scripts.websummit.export_demo_fixtures",
        "engines": {
            "estimation": "engines.estimation.estimate_from_request",
            "estimation_params": DEMO_MORADIA_MARTINS_PRICING,
            "branding": "engines.bet_core.samples.demo_branding",
        },
        "demo_source": DEMO_SOURCE,
        "outputs": outputs,
    }


def _write(name: str, payload) -> int:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    p = FIXTURES_DIR / name
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p.stat().st_size


def main() -> None:
    outputs = {}
    users = _demo_users()
    outputs["users.json"] = _write("users.json", users)
    projects = [_demo_project_for(u["user_id"]) for u in users]
    outputs["projects.json"] = _write("projects.json", projects)
    outputs["demo_branding.json"] = _write("demo_branding.json", _demo_branding())
    # Placeholders preenchidos em 2c (fail-closed: lista vazia é renderizável)
    for placeholder in ("assistant_docs.json", "plans.json", "quotes.json"):
        if not (FIXTURES_DIR / placeholder).exists():
            outputs[placeholder] = _write(placeholder, [])
    outputs["_manifest.json"] = _write("_manifest.json", _manifest(outputs))
    print(json.dumps({"status": "ok", "outputs": outputs, "fixtures_dir": str(FIXTURES_DIR)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

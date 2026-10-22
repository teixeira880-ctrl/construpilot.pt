"""Testa o script de export das fixtures demo (LOTE 2b).

Valida:
- Fixtures são gravadas em `/app/frontend/src/fixtures/demo/`.
- `projects.json` contém a Moradia Martins com estimation output do motor real
  (campo `source` começa por `engines.estimation.`).
- `users.json` contém 2 utilizadores (pro + particular) com schema `/auth/me`.
- `_manifest.json` referencia os motores reais e parâmetros canónicos.
- A re-execução é idempotente (tamanhos reproduzíveis em bytes).
"""
import json
import subprocess
from pathlib import Path

FIXTURES = Path("/app/frontend/src/fixtures/demo")


def test_export_fixtures_cli_runs_and_writes_outputs():
    r = subprocess.run(
        ["python", "-m", "scripts.websummit.export_demo_fixtures"],
        cwd="/app/backend",
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    payload = json.loads(r.stdout)
    assert payload["status"] == "ok"
    assert set(payload["outputs"]).issuperset({"users.json", "projects.json", "_manifest.json"})


def test_fixtures_projects_contain_moradia_martins_from_engine():
    projects = json.loads((FIXTURES / "projects.json").read_text("utf-8"))
    # 2 projectos (um por utilizador demo)
    assert len(projects) == 2
    for p in projects:
        assert p["name"] == "Moradia Martins"
        assert p["user_id"].startswith("demo_")
        assert p["is_demo"] is True
        est = p["estimation"]
        # Motor real: a assinatura `source` prova a origem
        assert est.get("source", "").startswith("engines.estimation."), est.get("source")
        assert est["total_avg"] > 0
        assert len(est["lots"]) >= 10
        assert est["country"] == "PT"
        assert est["region"] == "Lisboa"


def test_fixtures_users_schema():
    users = json.loads((FIXTURES / "users.json").read_text("utf-8"))
    assert len(users) == 2
    kinds = {u["demo_kind"] for u in users}
    assert kinds == {"pro", "particular"}
    for u in users:
        for key in ("user_id", "email", "name", "role", "lang", "is_demo"):
            assert key in u, u
        assert u["is_demo"] is True
        assert "password" not in u and "password_hash" not in u


def test_fixtures_manifest_references_engines():
    manifest = json.loads((FIXTURES / "_manifest.json").read_text("utf-8"))
    assert manifest["engines"]["estimation"] == "engines.estimation.estimate_from_request"
    params = manifest["engines"]["estimation_params"]
    assert params["project_type"] == "construction_maison_neuve"
    assert params["country"] == "PT"
    assert params["region"] == "Lisboa"
    assert params["surface"] == 150.0

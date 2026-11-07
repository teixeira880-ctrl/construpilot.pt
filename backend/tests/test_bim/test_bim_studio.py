"""Testes automatizados do ConstruPilot BIM Studio.

Executar (a partir de backend/):
    python -m pytest tests/test_bim -n 0 -q

Modelos IFC: gerados por ``bim_studio.sample_models`` (origem própria, sem licenças de terceiros).
Base de dados: mongomock-motor (sem rede). Armazenamento: diretório local temporário.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import subprocess
import sys
import tempfile
import time

import pytest

_TMP = tempfile.mkdtemp(prefix="bimtest_")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:1")
os.environ.setdefault("DB_NAME", "bim_test")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ["ENV"] = "development"
os.environ["BIM_STORAGE"] = "local"
os.environ["BIM_LOCAL_STORAGE_DIR"] = os.path.join(_TMP, "store")
os.environ["BIM_WORK_DIR"] = os.path.join(_TMP, "work")
os.environ.pop("BIM_STUDIO_ENABLED", None)

from fastapi import APIRouter, FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

from bim_studio import budget as bud  # noqa: E402
from bim_studio import config, engine, jobs, store  # noqa: E402
from bim_studio.sample_models import SMALL_HOUSE_EXPECTED, large_model, small_house  # noqa: E402
from core.security import pro_required  # noqa: E402
import routes.bim_studio as bim_routes  # noqa: E402

USERS = {
    "pro_a": {"user_id": "u_a", "name": "Ana Arquiteta", "role": "user", "account_type": "pro"},
    "pro_b": {"user_id": "u_b", "name": "Bruno Outra Empresa", "role": "user", "account_type": "pro"},
    "org_admin": {"user_id": "u_c", "name": "Carla", "organization_id": "org1", "org_role": "admin"},
    "org_ouvrier": {"user_id": "u_d", "name": "Duarte", "organization_id": "org1", "org_role": "ouvrier"},
}


@pytest.fixture(scope="module")
def ctx():
    mock = AsyncMongoMockClient()["bim_test"]
    store.set_db(mock)
    import routes.library as lib
    lib.db = mock  # o catálogo inicial da biblioteca existente é semeado na base de testes

    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(bim_routes.router)
    api.include_router(bim_routes.files_router)
    app.include_router(api)

    async def fake_user(request: Request):
        return dict(USERS[request.headers.get("x-test-user", "pro_a")])

    app.dependency_overrides[pro_required] = fake_user
    with TestClient(app) as client:
        client.portal.call(_seed_users, mock)
        yield client, mock


async def _seed_users(db):
    for u in USERS.values():
        await db.users.insert_one(dict(u))


def _ifc_bytes(model) -> bytes:
    p = os.path.join(_TMP, f"m_{time.time_ns()}.ifc")
    model.write(p)
    with open(p, "rb") as fh:
        return fh.read()


def _upload(client, data: bytes, user="pro_a", name="moradia.ifc", **form):
    return client.post("/api/bim/models", files={"file": (name, data, "application/octet-stream")},
                       data=form, headers={"x-test-user": user})


def _process_all(client):
    while True:
        v = client.portal.call(jobs._claim)
        if not v:
            return
        client.portal.call(jobs.run_job, v)


@pytest.fixture(scope="module")
def house(ctx):
    client, _ = ctx
    r = _upload(client, _ifc_bytes(small_house(units="mm")))
    assert r.status_code == 200, r.text
    _process_all(client)
    return r.json()["model_id"]


def H(user="pro_a"):
    return {"x-test-user": user}


# 1. Upload de IFC válido
def test_upload_valid_ifc(ctx, house):
    client, _ = ctx
    r = client.get(f"/api/bim/models/{house}/versions/1", headers=H())
    assert r.status_code == 200
    v = r.json()
    assert v["status"] == "done", v
    assert v["schema"] == "IFC4" and v["chunks"] >= 1 and v["duration_s"] is not None


# 2. Rejeição de ficheiros inválidos
@pytest.mark.parametrize("name,data,code", [
    ("planta.pdf", b"%PDF-1.7 ...", 415),
    ("modelo.ifczip", b"PK\x03\x04", 415),
    ("modelo.ifc", b"", 422),
    ("modelo.ifc", b"isto nao e um ifc" * 10, 422),
    ("modelo.ifc", b"ISO-10303-21;\nHEADER;FILE_SCHEMA(('IFC9'));ENDSEC;\nDATA;ENDSEC;\nEND-ISO-10303-21;", 422),
    ("modelo.ifc", b"ISO-10303-21;\nHEADER;FILE_SCHEMA(('IFC4'));ENDSEC;\nDATA;\n#1=IFCWALL(" + b"x" * 100, 422),
])
def test_reject_invalid_files(ctx, name, data, code):
    client, _ = ctx
    assert _upload(client, data, name=name).status_code == code


def test_reject_too_large(ctx, monkeypatch):
    client, _ = ctx
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 0)
    assert _upload(client, _ifc_bytes(small_house())).status_code == 413


# 3. Extração de elementos BIM
def test_element_extraction_counts(ctx, house):
    client, _ = ctx
    v = client.get(f"/api/bim/models/{house}/versions/1", headers=H()).json()
    assert v["stats"]["by_category"] == SMALL_HOUSE_EXPECTED["counts"]
    walls = client.get(f"/api/bim/models/{house}/versions/1/elements?category=paredes", headers=H()).json()
    assert walls["total"] == 5
    assert {s["name"] for s in v["storeys"]} == {"Piso 0", "Piso 1"}


# 4. Leitura de propriedades
def test_properties(ctx, house):
    client, _ = ctx
    items = client.get(f"/api/bim/models/{house}/versions/1/elements?q=Parede Norte", headers=H()).json()["items"]
    gid = items[0]["gid"]
    e = client.get(f"/api/bim/models/{house}/versions/1/elements/{gid}", headers=H()).json()
    assert e["properties"]["Pset_WallCommon"]["FireRating"] == "EI60"
    assert e["properties"]["Pset_WallCommon"]["IsExternal"] is True
    assert e["materials"] == ["Bloco de betão"] and e["storey"] == "Piso 0" and e["ifc_class"] == "IfcWall"


def _by_name(client, model_id, name, version=1):
    items = client.get(f"/api/bim/models/{model_id}/versions/{version}/elements?q={name}&limit=50",
                       headers=H()).json()["items"]
    return next(e for e in items if e["name"] == name)


# 5. Áreas e volumes (valores exatos conhecidos)
def test_areas_and_volumes(ctx, house):
    client, _ = ctx
    E = SMALL_HOUSE_EXPECTED
    north = _by_name(client, house, "Parede Norte")["quantities"]
    assert north["area"]["value"] == pytest.approx(E["wall_north_area_m2"])
    assert north["area"]["origin"] == "declared"
    assert north["volume"]["value"] == pytest.approx(E["wall_north_volume_m3"])
    inner = _by_name(client, house, "Divisória interior")["quantities"]
    assert inner["volume"]["origin"] == "calculated"
    assert inner["volume"]["value"] == pytest.approx(E["interior_wall_volume_m3"], rel=1e-3)
    assert inner["area"]["value"] == pytest.approx(14.0, rel=1e-3)
    assert inner["length"]["origin"] == "estimated"
    assert _by_name(client, house, "Laje térrea")["quantities"]["area"]["value"] == pytest.approx(E["slab_ground_area_m2"])
    roof = _by_name(client, house, "Laje de cobertura")
    assert roof["category"] == "coberturas"
    assert roof["quantities"]["volume"]["value"] == pytest.approx(E["roof_slab_volume_m3"], rel=1e-3)
    assert _by_name(client, house, "Pilar P1")["quantities"]["volume"]["value"] == pytest.approx(E["column_volume_m3"], rel=1e-3)
    assert _by_name(client, house, "Viga V1")["quantities"]["volume"]["value"] == pytest.approx(E["beam_volume_m3"], rel=1e-3)
    assert _by_name(client, house, "Sala")["quantities"]["area"]["value"] == pytest.approx(E["space_area_m2"])
    # Nenhuma quantidade do motor é apresentada como verificada
    assert all(not q["verified"] for q in north.values())


# 6. Conversão de unidades (modelo em mm == modelo em m)
def test_unit_conversion_mm_vs_m(tmp_path):
    res = {}
    for units in ("mm", "m"):
        p = tmp_path / f"h_{units}.ifc"
        small_house(units=units).write(str(p))
        r = engine.process(str(p), str(tmp_path / f"out_{units}"))
        res[units] = {e["name"]: {k: q["value"] for k, q in e["quantities"].items()} for e in r["elements"]}
        assert r["units"]["names"]["LENGTHUNIT"] == ("MILLIMETRE" if units == "mm" else "METRE")
    for name, qs in res["m"].items():
        for k, v in qs.items():
            assert res["mm"][name][k] == pytest.approx(v, rel=1e-4, abs=1e-6), (name, k)
    north = [e for e in engine.process(str(tmp_path / "h_mm.ifc"), str(tmp_path / "o2"))["elements"]
             if e["name"] == "Parede Norte"][0]
    assert north["quantities"]["length"]["original"]["value"] == pytest.approx(10000.0)  # valor original preservado


# 7. Deteção de quantidades em falta
def test_missing_quantities(ctx, house):
    client, _ = ctx
    miss = client.get(f"/api/bim/models/{house}/versions/1/elements?missing=true", headers=H()).json()
    names = {e["name"]: e["missing"] for e in miss["items"]}
    assert "material" in names["Porta de entrada"]
    assert "material" in names["Elemento sem dados"]
    proxy = _by_name(client, house, "Elemento sem dados")
    assert proxy["has_geometry"] is False
    assert "Cobertura" not in names  # agregador não reporta dados em falta


def test_no_double_counting(ctx, house):
    client, _ = ctx
    roof = _by_name(client, house, "Cobertura")
    assert roof["counted"] is False and roof["included"] is False
    groups = client.get(f"/api/bim/models/{house}/versions/1/groups", headers=H()).json()["groups"]
    cov = [g for g in groups if g["category"] == "coberturas"]
    assert sum(g["included"] for g in cov) == 1  # só a laje filha conta
    r = client.patch(f"/api/bim/models/{house}/versions/1/elements/{roof['gid']}", json={"included": True}, headers=H())
    assert r.status_code == 409


# Correção e validação humana
def test_manual_correction_and_validation(ctx, house):
    client, mock = ctx
    inner = _by_name(client, house, "Divisória interior")
    url = f"/api/bim/models/{house}/versions/1/elements/{inner['gid']}"
    r = client.patch(url, json={"quantities": {"area": {"value": 13.5, "note": "medido em obra"}}}, headers=H())
    assert r.status_code == 200
    q = r.json()["quantities"]["area"]
    assert q["value"] == 13.5 and q["origin"] == "manual" and q["verified"] is True
    north = _by_name(client, house, "Parede Norte")
    r = client.patch(f"/api/bim/models/{house}/versions/1/elements/{north['gid']}",
                     json={"validate": ["area"]}, headers=H())
    assert r.json()["quantities"]["area"]["verified"] is True
    assert r.json()["quantities"]["area"]["origin"] == "declared"
    # reposição do valor do motor
    r = client.patch(url, json={"quantities": {"area": {"reset": True}}}, headers=H())
    assert r.json()["quantities"]["area"]["origin"] == "calculated"
    audit = client.get(f"/api/bim/models/{house}/audit", headers=H()).json()["items"]
    assert any(a["action"] == "edit_element" for a in audit)


# 8. Associação a artigos + 9. Geração de orçamento
def test_mapping_and_quote(ctx, house):
    client, mock = ctx
    r = client.post(f"/api/bim/models/{house}/versions/1/mappings/suggest", headers=H())
    assert r.status_code == 200 and r.json()["suggested"] >= 1
    groups = client.get(f"/api/bim/models/{house}/versions/1/groups", headers=H()).json()["groups"]
    slab = next(g for g in groups if g["label"] == "Laje térrea")
    assert slab["mapping"]["status"] == "suggested"
    # Sugestões não entram no orçamento até serem confirmadas
    b = client.get(f"/api/bim/models/{house}/versions/1/budget", headers=H()).json()
    assert b["lines"] == [] and b["total_ht"] == 0
    item = client.portal.call(mock.library_items.find_one, {"user_id": "u_a", "designation": "Laje de betão armado"})
    assert item and item["unit"] == "m²"
    r = client.put(f"/api/bim/models/{house}/versions/1/mappings",
                   json={"group_key": slab["group_key"], "item_id": item["item_id"]}, headers=H())
    assert r.status_code == 200 and r.json()["quantity_key"] == "area"
    walls = next(g for g in groups if g["label"] == "Parede Norte")
    wall_item = client.portal.call(mock.library_items.find_one, {"user_id": "u_a", "designation": "Parede de bloco de cimento 20 cm"})
    client.put(f"/api/bim/models/{house}/versions/1/mappings",
               json={"group_key": walls["group_key"], "item_id": wall_item["item_id"]}, headers=H())
    b = client.get(f"/api/bim/models/{house}/versions/1/budget", headers=H()).json()
    by = {l["bim_label"]: l for l in b["lines"]}
    assert by["Laje térrea"]["qty"] == pytest.approx(80.0)
    assert by["Laje térrea"]["total_ht"] == pytest.approx(80.0 * item["unit_price_ht"])
    assert by["Parede Norte"]["qty"] == pytest.approx(28.0)
    assert b["total_ht"] == pytest.approx(80 * item["unit_price_ht"] + 28 * wall_item["unit_price_ht"])
    assert b["subtotals_by_storey"]["Piso 0"] == pytest.approx(b["total_ht"])
    assert "Obra grossa" not in b["subtotals_by_category"] and "Lajes" in b["subtotals_by_category"]
    assert any(u["label"] == "Pilar P1" for u in b["unmapped"])
    # Orçamento criado na coleção existente de documentos (editável)
    r = client.post(f"/api/bim/models/{house}/versions/1/budget/quote", json={}, headers=H())
    assert r.status_code == 200, r.text
    doc = client.portal.call(mock.pro_documents.find_one, {"doc_id": r.json()["doc_id"]})
    assert doc["doc_type"] == "quote" and doc["status"] == "draft" and doc["source"] == "bim_studio"
    assert doc["totals"]["ht"] == pytest.approx(b["total_ht"])
    lines = [l for l in doc["lines"] if l["kind"] == "line"]
    assert all(l["price_source"] == "bim_studio" and l["price_reference"].startswith("map_") for l in lines)
    trace = client.portal.call(mock.bim_quote_traces.find_one, {"doc_id": doc["doc_id"]})
    assert trace and len(trace["lines"]) == len(lines) and trace["lines"][0]["gids"]


def test_price_missing_flag(ctx, house):
    client, mock = ctx
    client.portal.call(mock.library_items.insert_one, {
        "item_id": "lib_zero", "user_id": "u_a", "type": "ouvrage", "category": "Estrutura",
        "designation": "Pilar sem preço", "unit": "m³", "unit_price_ht": 0, "vat_rate": 23})
    groups = client.get(f"/api/bim/models/{house}/versions/1/groups", headers=H()).json()["groups"]
    col = next(g for g in groups if g["label"] == "Pilar P1")
    client.put(f"/api/bim/models/{house}/versions/1/mappings",
               json={"group_key": col["group_key"], "item_id": "lib_zero"}, headers=H())
    b = client.get(f"/api/bim/models/{house}/versions/1/budget", headers=H()).json()
    line = next(l for l in b["lines"] if l["bim_label"] == "Pilar P1")
    assert line["price_missing"] is True and line["total_ht"] == 0
    assert any("sem preço" in w for w in b["warnings"])


def test_exports(ctx, house):
    client, _ = ctx
    r = client.get(f"/api/bim/models/{house}/versions/1/export.csv", headers=H())
    assert r.status_code == 200 and "Mapa_quantidades" in r.headers["content-disposition"]
    assert "Categoria;Grupo BIM" in r.content.decode("utf-8-sig")
    r = client.get(f"/api/bim/models/{house}/versions/1/export.xlsx", headers=H())
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Mapa de quantidades", "Subtotais"]


# 10. Isolamento entre organizações
def test_isolation_between_companies(ctx, house):
    client, _ = ctx
    assert client.get("/api/bim/models", headers=H("pro_b")).json()["items"] == []
    for path in ("", "/versions/1", "/versions/1/elements", "/versions/1/geometry/0", "/versions/1/budget",
                 "/versions/1/groups", "/audit", "/versions/1/export.csv"):
        assert client.get(f"/api/bim/models/{house}{path}", headers=H("pro_b")).status_code == 404, path
    assert client.delete(f"/api/bim/models/{house}", headers=H("pro_b")).status_code == 404
    assert _upload(client, _ifc_bytes(small_house()), user="pro_b", model_id=house).status_code == 404
    # URL assinado: válido para o dono, inútil se adulterado ou expirado
    url = client.get(f"/api/bim/models/{house}/versions/1/download-url", headers=H()).json()["url"]
    ok = client.get(url)
    assert ok.status_code == 200 and ok.content.startswith(b"ISO-10303-21")
    tok = url.rsplit("/", 1)[1]
    assert client.get(url[:-3] + ("AAA" if not tok.endswith("AAA") else "BBB")).status_code == 403
    expired = bim_routes.make_token(store.tenant_of(USERS["pro_a"]), house, 1, ttl=-1)
    assert client.get(f"/api/bim/files/{expired}").status_code == 410
    forged = bim_routes.make_token(store.tenant_of(USERS["pro_b"]), house, 1)
    assert client.get(f"/api/bim/files/{forged}").status_code == 404


# 11. Permissões de acesso
def test_permissions(ctx):
    client, _ = ctx
    assert _upload(client, _ifc_bytes(small_house()), user="org_ouvrier").status_code == 403
    r = _upload(client, _ifc_bytes(small_house()), user="org_admin")
    assert r.status_code == 200
    mid = r.json()["model_id"]
    # mesmo tenant (organização): o ouvrier vê mas não altera
    assert client.get(f"/api/bim/models/{mid}", headers=H("org_ouvrier")).status_code == 200
    assert client.delete(f"/api/bim/models/{mid}", headers=H("org_ouvrier")).status_code == 403
    assert client.post(f"/api/bim/models/{mid}/versions/1/cancel", headers=H("org_ouvrier")).status_code == 403
    assert client.get(f"/api/bim/models/{mid}", headers=H("pro_a")).status_code == 404
    client.post(f"/api/bim/models/{mid}/versions/1/cancel", headers=H("org_admin"))


def test_feature_flag_and_market(ctx, monkeypatch):
    client, _ = ctx
    monkeypatch.setenv("BIM_STUDIO_ENABLED", "0")
    assert client.get("/api/bim/models", headers=H()).status_code == 404
    assert client.get("/api/bim/config", headers=H()).json()["enabled"] is False
    monkeypatch.delenv("BIM_STUDIO_ENABLED")
    monkeypatch.setattr(config, "SITE_COUNTRY", "FR")
    assert config.enabled() is False  # nunca ativo fora de Portugal
    monkeypatch.setattr(config, "SITE_COUNTRY", "PT")
    import core.environment as envmod
    monkeypatch.setattr(envmod, "ENVIRONMENT", "production")
    assert config.enabled() is False  # produção: desligado até aprovação explícita
    monkeypatch.setenv("BIM_STUDIO_ENABLED", "1")
    assert config.enabled() is True


# 12. Modelos de grandes dimensões
def test_large_model(ctx):
    client, _ = ctx
    data = _ifc_bytes(large_model(1500))
    r = _upload(client, data, name="grande.ifc")
    mid = r.json()["model_id"]
    t0 = time.monotonic()
    _process_all(client)
    elapsed = time.monotonic() - t0
    v = client.get(f"/api/bim/models/{mid}/versions/1", headers=H()).json()
    assert v["status"] == "done", v
    assert v["stats"]["by_category"]["paredes"] == 1500
    page = client.get(f"/api/bim/models/{mid}/versions/1/elements?limit=1000&skip=1000", headers=H()).json()
    assert page["total"] == 1500 and len(page["items"]) == 500
    print(f"\n[modelo grande] {len(data)/1e6:.1f} MB, 1500 paredes, {elapsed:.1f} s, {v['stats']['triangles']} triângulos")
    assert elapsed < 300


def test_large_model_element_limit(tmp_path):
    p = tmp_path / "g.ifc"
    large_model(400).write(str(p))
    with pytest.raises(engine.LimitExceeded):
        engine.process(str(p), str(tmp_path / "o"), max_elements=100)


# 13. Falhas de processamento
def test_processing_failure_corrupt_body(ctx):
    client, _ = ctx
    good = _ifc_bytes(small_house())
    corrupt = good.replace(b"DATA;", b"DATA;\n#999999=IFCNONSENSE($,$,(;\n")
    r = _upload(client, corrupt, name="corrompido.ifc")
    assert r.status_code == 200  # cabeçalho válido → aceite, falha controlada no worker
    mid = r.json()["model_id"]
    _process_all(client)
    v = client.get(f"/api/bim/models/{mid}/versions/1", headers=H()).json()
    assert v["status"] == "failed" and v["error_code"] == "empty", v
    assert "corrompido" in v["error"] and "Traceback" not in v["error"]
    assert client.post(f"/api/bim/models/{mid}/versions/1/retry", headers=H()).status_code == 200
    client.post(f"/api/bim/models/{mid}/versions/1/cancel", headers=H())


def test_worker_memory_limit(tmp_path):
    p = tmp_path / "h.ifc"
    small_house().write(str(p))
    worker = os.path.join(os.path.dirname(engine.__file__), "worker_main.py")
    out = subprocess.run([sys.executable, "-I", worker, str(p), str(tmp_path / "o"),
                          json.dumps({"memory_mb": 150})], capture_output=True, text=True, timeout=120)
    # Processo morto pelo sistema (sinal) ou erro de memória controlado — nunca "concluído"
    last = [json.loads(l) for l in out.stdout.splitlines() if l.startswith("{")]
    assert out.returncode < 0 or (last and last[-1].get("code") == "memory"), (out.returncode, last[-1:])


def test_worker_isolated_success(tmp_path):
    p = tmp_path / "h.ifc"
    small_house().write(str(p))
    worker = os.path.join(os.path.dirname(engine.__file__), "worker_main.py")
    out = subprocess.run([sys.executable, "-I", worker, str(p), str(tmp_path / "o"),
                          json.dumps({"memory_mb": 3072, "cpu_seconds": 120})],
                         capture_output=True, text=True, timeout=180, cwd=str(tmp_path))
    msgs = [json.loads(l) for l in out.stdout.splitlines()]
    assert out.returncode == 0 and msgs[-1]["done"] is True
    assert any("progress" in m for m in msgs)


def test_cancel_and_timeout(ctx, monkeypatch):
    client, _ = ctx
    r = _upload(client, _ifc_bytes(small_house()), name="anular.ifc")
    mid = r.json()["model_id"]
    assert client.post(f"/api/bim/models/{mid}/versions/1/cancel", headers=H()).status_code == 200
    assert client.get(f"/api/bim/models/{mid}/versions/1", headers=H()).json()["status"] == "cancelled"
    assert client.post(f"/api/bim/models/{mid}/versions/1/retry", headers=H()).status_code == 200
    monkeypatch.setattr(config, "JOB_TIMEOUT_S", 0.01)
    _process_all(client)
    v = client.get(f"/api/bim/models/{mid}/versions/1", headers=H()).json()
    assert v["status"] == "failed" and v["error_code"] == "timeout"


def test_versions_and_compare(ctx, house):
    client, _ = ctx
    m2 = small_house()
    import ifcopenshell.api.root
    w = [e for e in m2.by_type("IfcWall") if e.Name == "Divisória interior"][0]
    ifcopenshell.api.root.remove_product(m2, product=w)
    # GlobalIds novos por construção → comparar a mesma geração exige reutilizar o ficheiro original
    r = _upload(client, _ifc_bytes(m2), model_id=house)
    assert r.json()["version"] == 2
    _process_all(client)
    res = client.get(f"/api/bim/models/{house}/compare?a=1&b=2", headers=H()).json()
    assert res["summary"]["added"] + res["summary"]["removed"] > 0
    model = client.get(f"/api/bim/models/{house}", headers=H()).json()
    assert [v["version"] for v in model["versions"]] == [2, 1]


def test_compare_logic_same_gids():
    old = [{"gid": "a", "quantities": {"area": {"value": 10}}}, {"gid": "b", "quantities": {}}]
    new = [{"gid": "a", "quantities": {"area": {"value": 12}}}, {"gid": "c", "quantities": {}}]
    res = bud.compare(old, new)
    assert res["summary"] == {"added": 1, "removed": 1, "changed": 1, "unchanged": 0}
    assert res["changed"][0]["changes"]["area"] == {"before": 10, "after": 12}


# 14. Visualização 3D (contrato dos dados de geometria)
def test_geometry_chunks(ctx, house):
    client, _ = ctx
    r = client.get(f"/api/bim/models/{house}/versions/1/geometry/0", headers=H())
    assert r.status_code == 200 and r.headers.get("content-encoding") == "gzip"
    payload = r.json()  # o cliente HTTP descomprime como o navegador
    els = payload["elements"]
    gids = {e["gid"] for e in client.get(f"/api/bim/models/{house}/versions/1/elements?limit=100",
                                         headers=H()).json()["items"]}
    assert els and all(e["gid"] in gids for e in els)
    for e in els:
        assert len(e["p"]) % 3 == 0 and len(e["i"]) % 3 == 0 and max(e["i"]) < len(e["p"]) // 3
        assert len(e["c"]) == 3
    assert client.get(f"/api/bim/models/{house}/versions/1/geometry/99", headers=H()).status_code == 404


def test_storage_paths_are_pt_scoped(ctx, house):
    from bim_studio import storage
    k = storage.key_for("usr_u_a", house, 1, "model.ifc")
    assert k.startswith("pt/bim/usr_u_a/")
    with pytest.raises(ValueError):
        storage.key_for("../fr", house, 1, "x")


def test_prefs_profile(ctx):
    client, _ = ctx
    assert client.put("/api/bim/prefs", json={"profile": "simples"}, headers=H()).status_code == 200
    assert client.get("/api/bim/config", headers=H()).json()["profile"] == "simples"
    assert client.put("/api/bim/prefs", json={"profile": "hacker"}, headers=H()).status_code == 422


def test_ifc2x3_schema_supported(ctx):
    client, _ = ctx
    r = _upload(client, _ifc_bytes(small_house(schema="IFC2X3")), name="moradia_2x3.ifc")
    assert r.status_code == 200 and r.json()["schema"] == "IFC2X3"
    mid = r.json()["model_id"]
    _process_all(client)
    v = client.get(f"/api/bim/models/{mid}/versions/1", headers=H()).json()
    assert v["status"] == "done" and v["stats"]["by_category"] == SMALL_HOUSE_EXPECTED["counts"]
    assert _by_name(client, mid, "Parede Norte")["quantities"]["area"]["value"] == pytest.approx(28.0)


# 16. Verificação de ausência de alterações na versão francesa
def test_french_platform_untouched():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script = os.path.join(os.path.dirname(root), "scripts", "bim_studio", "check_isolation.py")
    out = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr

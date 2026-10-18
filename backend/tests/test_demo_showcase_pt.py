"""Testes do showcase BET-core nas contas demo WebSummit.

Valida:
- `apply_demo_showcase_pt` instala 2 PDF em `assistant_docs` com cartucho
  "Moradia Martins" para contas pro + particular.
- Branding "Construções Horizonte, Lda." aplicado SÓ à conta pro.
- Documentos ligados ao projecto `Moradia Martins` em `db.projects` (array
  `doc_ids` + `user_id` sincronizado para `/api/projects`).
- Idempotência: 2 execuções seguidas não duplicam documentos nem ligações.
- Fail-closed: sem config no env, salta a conta.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, "/app/backend")


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if _match(d, q):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, q, upd):
        for d in self.docs:
            if _match(d, q):
                d.update(upd.get("$set") or {})
                return
        return

    async def delete_many(self, q):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _match(d, q)]
        class _R:  # noqa: E701
            deleted_count = before - len(self.docs)
        return _R()


def _match(doc, query):
    for k, v in query.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in v):
                return False
        elif doc.get(k) != v:
            return False
    return True


class _DB:
    def __init__(self):
        self.users = _Coll()
        self.assistant_docs = _Coll()
        self.projects = _Coll()


@pytest.fixture
def env_demo(monkeypatch):
    monkeypatch.setenv("WEBSUMMIT_DEMO_PASSWORD_PT", "x")
    monkeypatch.setenv("WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT", "y")


@pytest.fixture
def env_only_pro(monkeypatch):
    monkeypatch.setenv("WEBSUMMIT_DEMO_PASSWORD_PT", "x")
    monkeypatch.delenv("WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT", raising=False)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if sys.version_info < (3, 10) else asyncio.run(coro)


def _seed_demo_users(db, with_particular=True):
    from core.websummit_seed_pt import DEMO_SOURCE
    _run(db.users.insert_one({"user_id": "u-pro", "email": "demo.websummit@construpilot.pt",
                              "is_demo": True, "demo_source": DEMO_SOURCE, "account_type": "pro"}))
    if with_particular:
        _run(db.users.insert_one({"user_id": "u-part", "email": "demo.websummit.particular@construpilot.pt",
                                  "is_demo": True, "demo_source": DEMO_SOURCE, "account_type": "particulier"}))


def _seed_moradia_martins(db, user_id, project_id="prj_test"):
    from core.websummit_seed_pt import DEMO_PROJECT_NAME, DEMO_SOURCE
    _run(db.projects.insert_one({
        "project_id": project_id,
        "name": DEMO_PROJECT_NAME,
        "description": "Moradia unifamiliar T3 em Lisboa — dados demo não executivos.",
        "owner_user_id": user_id,
        "status": "active",
        "location": "Lisboa, Portugal",
        "work_type": "construcao_nova",
        "is_demo": True,
        "demo_source": DEMO_SOURCE,
    }))


def test_showcase_installs_docs_with_moradia_martins_identity(env_demo):
    """Pro + Particular: 2 PDF com cartucho Moradia Martins, ligados ao projecto."""
    from core.websummit_seed_pt import apply_demo_showcase_pt

    db = _DB()
    _seed_demo_users(db)
    _seed_moradia_martins(db, "u-pro", project_id="prj_pro_moradia")
    _seed_moradia_martins(db, "u-part", project_id="prj_part_moradia")

    summary = _run(apply_demo_showcase_pt(db))
    assert "error" not in summary, summary

    for kind, uid in (("pro", "u-pro"), ("particular", "u-part")):
        docs = [d for d in db.assistant_docs.docs if d["user_id"] == uid]
        assert len(docs) == 2, f"{kind}: esperados 2 docs, obtidos {len(docs)}"
        # Nome do ficheiro contém Moradia_Martins
        names = sorted(d["filename"] for d in docs)
        assert all("Moradia_Martins" in n for n in names), names
        assert any("arquitetura" in n for n in names), names
        assert any("geotecnico" in n for n in names), names

    # Branding só pro
    pro_user = _run(db.users.find_one({"user_id": "u-pro"}))
    assert pro_user.get("brand_company_name") == "Construções Horizonte, Lda."
    part_user = _run(db.users.find_one({"user_id": "u-part"}))
    assert "brand_company_name" not in part_user

    # Projecto Moradia Martins com doc_ids ligados
    for uid, pid in (("u-pro", "prj_pro_moradia"), ("u-part", "prj_part_moradia")):
        proj = _run(db.projects.find_one({"project_id": pid}))
        assert len(proj.get("doc_ids") or []) == 2, proj
        assert proj.get("user_id") == uid  # sincronizado para /api/projects
        # Projecto Moradia Martins preservado
        assert proj["name"] == "Moradia Martins"
        assert proj["status"] == "active"
        assert proj["description"].startswith("Moradia unifamiliar T3")


def test_showcase_is_idempotent(env_demo):
    """Executar 2× não duplica documentos nem ligações."""
    from core.websummit_seed_pt import apply_demo_showcase_pt

    db = _DB()
    _seed_demo_users(db)
    _seed_moradia_martins(db, "u-pro", project_id="prj_pro_moradia")
    _seed_moradia_martins(db, "u-part", project_id="prj_part_moradia")

    _run(apply_demo_showcase_pt(db))
    first_doc_count = len(db.assistant_docs.docs)
    first_links_pro = len(_run(db.projects.find_one({"project_id": "prj_pro_moradia"})).get("doc_ids") or [])

    _run(apply_demo_showcase_pt(db))
    second_doc_count = len(db.assistant_docs.docs)
    second_links_pro = len(_run(db.projects.find_one({"project_id": "prj_pro_moradia"})).get("doc_ids") or [])

    assert first_doc_count == 4
    assert second_doc_count == 4, f"idempotência docs quebrada: {first_doc_count} → {second_doc_count}"
    assert first_links_pro == 2
    assert second_links_pro == 2, f"idempotência ligações quebrada: {first_links_pro} → {second_links_pro}"


def test_showcase_creates_moradia_martins_for_particular(env_demo):
    """Addendum 3.5: se Moradia Martins faltar na conta particular, é criada.

    A versão pro (pré-existente, com orçamentos e histórico) é preservada.
    """
    from core.websummit_seed_pt import DEMO_PROJECT_NAME, DEMO_SOURCE, apply_demo_showcase_pt

    db = _DB()
    _seed_demo_users(db)
    # pro: Moradia Martins pré-existente com extras (simula orçamentos)
    _run(db.projects.insert_one({
        "project_id": "prj_pro_moradia",
        "name": DEMO_PROJECT_NAME,
        "description": "Moradia unifamiliar T3 em Lisboa — dados demo não executivos.",
        "owner_user_id": "u-pro",
        "status": "active",
        "location": "Lisboa, Portugal",
        "work_type": "construcao_nova",
        "is_demo": True,
        "demo_source": DEMO_SOURCE,
        "custom_quotes": ["Q-001", "Q-002"],  # dado pro-only que deve ser preservado
    }))
    # particular: SEM projecto Moradia Martins
    assert not _run(db.projects.find_one({"name": DEMO_PROJECT_NAME, "owner_user_id": "u-part"}))

    summary = _run(apply_demo_showcase_pt(db))
    assert "error" not in summary

    # Pro: Moradia Martins preservada + user_id sincronizado + doc_ids ligados
    pro_proj = _run(db.projects.find_one({"owner_user_id": "u-pro", "name": DEMO_PROJECT_NAME}))
    assert pro_proj.get("user_id") == "u-pro"
    assert pro_proj.get("custom_quotes") == ["Q-001", "Q-002"]  # pro-only preservado
    assert len(pro_proj.get("doc_ids") or []) == 2
    assert summary["docs"]["pro"]["count"] == 2
    assert summary["branding"]["pro"] == "applied"

    # Particular: Moradia Martins CRIADA (addendum 3.5) + doc_ids ligados
    part_proj = _run(db.projects.find_one({"owner_user_id": "u-part", "name": DEMO_PROJECT_NAME}))
    assert part_proj is not None, "Moradia Martins devia ter sido criada para o particular"
    assert part_proj.get("user_id") == "u-part"
    assert part_proj.get("owner_user_id") == "u-part"
    assert part_proj["name"] == "Moradia Martins"
    assert part_proj["is_demo"] is True
    assert part_proj["demo_source"] == DEMO_SOURCE
    assert part_proj["location"] == "Lisboa, Portugal"
    assert len(part_proj.get("doc_ids") or []) == 2
    # Zero dado pro-only no particular
    assert "custom_quotes" not in part_proj
    assert "brand_company_name" not in _run(db.users.find_one({"user_id": "u-part"}))
    assert summary["docs"]["particular"]["count"] == 2


def test_showcase_fail_closed_missing_particular_config(env_only_pro):
    """Config particular ausente → só pro recebe docs."""
    from core.websummit_seed_pt import apply_demo_showcase_pt

    db = _DB()
    _seed_demo_users(db, with_particular=False)
    _seed_moradia_martins(db, "u-pro", project_id="prj_pro_moradia")

    summary = _run(apply_demo_showcase_pt(db))
    assert summary["docs"]["pro"]["count"] == 2
    assert summary["docs"]["particular"] == "skipped_missing_config"
    assert summary["branding"]["pro"] == "applied"

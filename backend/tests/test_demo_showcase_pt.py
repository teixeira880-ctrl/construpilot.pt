"""Testes do showcase BET-core nas contas demo WebSummit.

Valida:
- `apply_demo_showcase_pt` instala 2 PDF em `assistant_docs` para contas pro + particular.
- Branding "Construções Horizonte, Lda." aplicado SÓ à conta pro.
- Idempotência: 2 execuções seguidas não duplicam documentos.
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
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, q, upd):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(upd.get("$set") or {})
                return
        # upsert não suportado — não é usado nesta função
        return

    async def delete_many(self, q):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not all(d.get(k) == v for k, v in q.items())]
        class _R:  # noqa: E701
            deleted_count = before - len(self.docs)
        return _R()


class _DB:
    def __init__(self):
        self.users = _Coll()
        self.assistant_docs = _Coll()

    def __getitem__(self, name):
        if not hasattr(self, name):
            setattr(self, name, _Coll())
        return getattr(self, name)


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


def test_showcase_installs_docs_and_branding(env_demo):
    """Pro: 2 PDF + branding. Particular: 2 PDF, sem branding."""
    from core.websummit_seed_pt import DEMO_SOURCE, apply_demo_showcase_pt

    db = _DB()
    # pré-criar contas demo
    _run(db.users.insert_one({"user_id": "u-pro", "email": "demo.websummit@construpilot.pt",
                              "is_demo": True, "demo_source": DEMO_SOURCE, "account_type": "pro"}))
    _run(db.users.insert_one({"user_id": "u-part", "email": "demo.websummit.particular@construpilot.pt",
                              "is_demo": True, "demo_source": DEMO_SOURCE, "account_type": "particulier"}))

    summary = _run(apply_demo_showcase_pt(db))
    assert "error" not in summary, summary

    # 2 PDF em cada conta
    pro_docs = [d for d in db.assistant_docs.docs if d["user_id"] == "u-pro"]
    part_docs = [d for d in db.assistant_docs.docs if d["user_id"] == "u-part"]
    assert len(pro_docs) == 2, f"esperados 2 docs pro, obtidos {len(pro_docs)}"
    assert len(part_docs) == 2, f"esperados 2 docs particular, obtidos {len(part_docs)}"

    # Nomes dos ficheiros correctos (DEMO visível)
    pro_names = sorted(d["filename"] for d in pro_docs)
    assert any("DEMO" in n for n in pro_names), pro_names
    assert any("arquitetura" in n for n in pro_names), pro_names
    assert any("geotecnico" in n for n in pro_names), pro_names

    # Formato inline b64
    for d in pro_docs + part_docs:
        assert d["mime"] == "application/pdf"
        assert "data_b64" in d
        assert d["is_demo"] is True
        assert d["demo_source"] == DEMO_SOURCE

    # Branding na conta pro (brand_* presentes)
    pro_user = _run(db.users.find_one({"user_id": "u-pro"}))
    assert pro_user.get("brand_company_name") == "Construções Horizonte, Lda."
    assert pro_user.get("brand_nif") == "500 000 000"
    assert pro_user.get("brand_accent_color") == "#0E4D4A"
    assert pro_user.get("brand_logo_b64", "").startswith("data:image/png;base64,")

    # Branding NÃO aplicado à conta particular
    part_user = _run(db.users.find_one({"user_id": "u-part"}))
    assert "brand_company_name" not in part_user
    assert "brand_logo_b64" not in part_user


def test_showcase_is_idempotent(env_demo):
    """Executar 2× não duplica documentos."""
    from core.websummit_seed_pt import DEMO_SOURCE, apply_demo_showcase_pt

    db = _DB()
    _run(db.users.insert_one({"user_id": "u-pro", "email": "demo.websummit@construpilot.pt",
                              "is_demo": True, "demo_source": DEMO_SOURCE, "account_type": "pro"}))
    _run(db.users.insert_one({"user_id": "u-part", "email": "demo.websummit.particular@construpilot.pt",
                              "is_demo": True, "demo_source": DEMO_SOURCE, "account_type": "particulier"}))

    _run(apply_demo_showcase_pt(db))
    first_count = len(db.assistant_docs.docs)
    _run(apply_demo_showcase_pt(db))
    second_count = len(db.assistant_docs.docs)

    assert first_count == 4, f"esperados 4 docs (2 pro + 2 part), obtidos {first_count}"
    assert second_count == 4, f"idempotência quebrada: {first_count} → {second_count}"


def test_showcase_fail_closed_missing_particular_config(env_only_pro):
    """Se config particular ausente, só a conta pro recebe docs."""
    from core.websummit_seed_pt import DEMO_SOURCE, apply_demo_showcase_pt

    db = _DB()
    _run(db.users.insert_one({"user_id": "u-pro", "email": "demo.websummit@construpilot.pt",
                              "is_demo": True, "demo_source": DEMO_SOURCE, "account_type": "pro"}))

    summary = _run(apply_demo_showcase_pt(db))
    assert summary["docs"]["pro"]["count"] == 2
    assert summary["docs"]["particular"] == "skipped_missing_config"
    assert summary["branding"]["pro"] == "applied"
    # particular foi skipped early (missing_config) → branding nem sequer é avaliado
    assert "particular" not in summary["branding"]

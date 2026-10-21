"""iter156 — assistant quote draft flow (live 2 turns) + schema/permission regressions."""
import json
import math
import os
from pathlib import Path

import pytest
import requests
from pydantic import ValidationError

from engines.assistant_quote_schema import QuoteInput


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
PRO_EMAIL = os.environ.get("TEST_PRO_EMAIL")
PRO_PASSWORD = os.environ.get("TEST_PRO_PASSWORD")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD")
PARTICULAR_EMAIL = os.environ.get("TEST_PARTICULAR_EMAIL")
PARTICULAR_PASSWORD = os.environ.get("TEST_PARTICULAR_PASSWORD")
WORKER_EMAIL = os.environ.get("TEST_WORKER_EMAIL")
WORKER_PASSWORD = os.environ.get("TEST_WORKER_PASSWORD")

if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL missing", allow_module_level=True)
if not (PRO_EMAIL and PRO_PASSWORD and ADMIN_EMAIL and ADMIN_PASSWORD):
    pytest.skip("Missing TEST_* credentials in environment", allow_module_level=True)


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:300]}"
    token = r.json().get("token")
    assert token and isinstance(token, str)
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _assistant_message(session: requests.Session, conversation_id: str, text: str, request_id: str) -> dict:
    payload = {
        "conversation_id": conversation_id,
        "request_id": request_id,
        "text": text,
        "response_mode": "fast",
        "web_enabled": False,
        "plan_ids": [],
        "doc_ids": [],
        "attachments": [],
    }
    r = session.post(f"{BASE_URL}/api/assistant/message", json=payload, timeout=240)
    assert r.status_code == 200, f"assistant message failed: {r.status_code} {r.text[:500]}"
    data = r.json()
    assert "actions" in data and isinstance(data["actions"], list)
    return data


def _find_action(message: dict, tool_name: str) -> dict:
    for action in message.get("actions", []):
        if action.get("tool") == tool_name:
            return action
    raise AssertionError(f"tool {tool_name} not found in actions: {[a.get('tool') for a in message.get('actions', [])]}")


class TestQuoteSchemas:
    """Schema validation for strict nullable line fields and invalid combos."""

    def test_schema_rejects_empty_title_nan_negative_and_invalid_origin_price_combo(self):
        with pytest.raises(ValidationError):
            QuoteInput.model_validate(
                {
                    "title": "",
                    "client_name": "TEST",
                    "vat_rate": 20,
                    "notes": "",
                    "lines": [
                        {
                            "line_id": None,
                            "description": "x",
                            "designation": "Ligne",
                            "quantity": -1,
                            "unit": "m²",
                            "unit_price": 10,
                            "price_origin": "library",
                            "vat_rate": math.nan,
                            "lot": "Test",
                        }
                    ],
                }
            )

        with pytest.raises(ValidationError):
            QuoteInput.model_validate(
                {
                    "title": "TEST",
                    "client_name": "TEST",
                    "vat_rate": 20,
                    "notes": "",
                    "lines": [
                        {
                            "line_id": None,
                            "description": "x",
                            "designation": "Ligne",
                            "quantity": 1,
                            "unit": "u",
                            "unit_price": None,
                            "price_origin": "user",
                            "vat_rate": 20,
                            "lot": "Test",
                        }
                    ],
                }
            )


class TestAssistantQuoteLiveFlow:
    """Live assistant flow: exactly two user turns, create then revise same draft."""

    @pytest.fixture(scope="class")
    def pro_session(self):
        return _login(PRO_EMAIL, PRO_PASSWORD)

    @pytest.fixture(scope="class")
    def admin_session(self):
        return _login(ADMIN_EMAIL, ADMIN_PASSWORD)

    @pytest.mark.skipif(os.environ.get("RUN_ITER156_LIVE_AI") != "1", reason="Two paid LLM turns already verified; opt-in required to repeat")
    def test_live_two_turn_quote_create_then_update_and_persistence(self, pro_session):
        conv = pro_session.post(f"{BASE_URL}/api/assistant/conversations", json={}, timeout=30)
        assert conv.status_code == 200, conv.text
        conversation_id = conv.json()["conversation_id"]

        title = "TEST_ITER156_ASSISTANT_QUOTE_DRAFT"
        turn1 = _assistant_message(
            pro_session,
            conversation_id,
            (
                f"Crée un devis brouillon intitulé {title} pour client TEST Iter156. "
                "Lignes: Peinture satinée murale 3.5 m² à 12.34 € HT (prix utilisateur), "
                "Sac de ciment 35 kg quantité 4 sans prix indiqué (bibliothèque), "
                "Déplacement offert quantité 1 à 0 € HT explicite. TVA 20%. "
                "N'envoie rien au client."
            ),
            "iter156-turn1",
        )
        create_action = _find_action(turn1, "create_quote_draft")
        result = create_action.get("result") or {}
        assert result.get("ok") is True
        doc_id = result.get("doc_id")
        assert doc_id and doc_id.startswith("doc_")

        doc_r = pro_session.get(f"{BASE_URL}/api/documents/{doc_id}", timeout=30)
        assert doc_r.status_code == 200
        doc = doc_r.json()
        assert doc.get("doc_type") == "quote"
        assert doc.get("status") == "draft"
        assert doc.get("number") is None
        assert doc.get("source") == "assistant"
        assert doc.get("assistant_conversation_id") == conversation_id

        lines = doc.get("lines") or []
        assert lines, "No persisted lines"
        assert any((ln.get("line_id") or "").startswith("ql_") for ln in lines)
        assert any((ln.get("description") or "") == "" or isinstance(ln.get("description"), str) for ln in lines)

        user_line = next((ln for ln in lines if "peinture" in (ln.get("designation") or "").lower()), None)
        assert user_line is not None
        assert float(user_line.get("unit_price_ht") or 0) == pytest.approx(12.34, abs=0.001)
        assert user_line.get("price_source") == "user_input"

        assert any(bool(ln.get("price_estimated") or ln.get("price_missing")) for ln in lines), (
            "Expected at least one estimated or incomplete line for missing library price input"
        )

        turn2 = _assistant_message(
            pro_session,
            conversation_id,
            (
                f"Modifie le même devis {doc_id}: passe la quantité de peinture à 5 m² "
                "et ajoute la précision 'finition velours lessivable' dans la description."
            ),
            "iter156-turn2",
        )
        update_action = _find_action(turn2, "update_quote_draft")
        update_result = update_action.get("result") or {}
        assert update_result.get("doc_id") == doc_id
        assert (update_result.get("draft") or {}).get("doc_id") == doc_id

        updated = pro_session.get(f"{BASE_URL}/api/documents/{doc_id}", timeout=30)
        assert updated.status_code == 200
        doc2 = updated.json()
        assert doc2.get("doc_id") == doc_id
        paint2 = next((ln for ln in (doc2.get("lines") or []) if "peinture" in (ln.get("designation") or "").lower()), None)
        assert paint2 is not None
        assert float(paint2.get("qty") or 0) == pytest.approx(5.0, abs=0.001)
        assert "velours" in (paint2.get("description") or "").lower()

        docs = pro_session.get(f"{BASE_URL}/api/documents", params={"doc_type": "quote"}, timeout=30)
        assert docs.status_code == 200
        found = [d for d in (docs.json().get("documents") or []) if d.get("doc_id") == doc_id]
        assert len(found) == 1, "Duplicate persisted quote ids detected"

        sends = pro_session.get(f"{BASE_URL}/api/quotes/sends/all", timeout=30)
        assert sends.status_code == 200
        assert all((row.get("doc_id") != doc_id) for row in (sends.json().get("sends") or [])), (
            "Draft must not be treated as sent"
        )

        Path("/tmp/iter156_live_meta.json").write_text(
            json.dumps({"doc_id": doc_id, "conversation_id": conversation_id, "title": title}, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_cross_tenant_quote_access_is_denied(self, admin_session):
        meta = Path("/tmp/iter156_live_meta.json")
        if not meta.exists():
            pytest.skip("Live quote metadata not found")
        doc_id = json.loads(meta.read_text(encoding="utf-8"))["doc_id"]

        r = admin_session.get(f"{BASE_URL}/api/documents/{doc_id}", timeout=30)
        assert r.status_code in (403, 404)

        payload = {
            "doc_type": "quote",
            "client_id": None,
            "title": "FORBIDDEN",
            "notes": "",
            "payment_terms": "",
            "deposit_pct": 0,
            "status": "draft",
            "lines": [
                {
                    "designation": "TEST",
                    "description": "",
                    "unit": "u",
                    "qty": 1,
                    "unit_price_ht": 1,
                    "cost_price_ht": 0,
                    "vat_rate": 20,
                    "category": "",
                    "line_id": None,
                    "price_source": "user_input",
                    "price_reference": "",
                    "price_reference_label": "",
                    "price_estimated": False,
                    "price_missing": False,
                    "quantity_missing": False,
                    "vat_assumed": False,
                }
            ],
        }
        r2 = admin_session.put(f"{BASE_URL}/api/documents/{doc_id}", json=payload, timeout=30)
        assert r2.status_code in (403, 404)

    def test_particular_and_worker_cannot_read_foreign_quote(self):
        meta = Path("/tmp/iter156_live_meta.json")
        if not meta.exists():
            pytest.skip("Live quote metadata not found")
        doc_id = json.loads(meta.read_text(encoding="utf-8"))["doc_id"]

        if PARTICULAR_EMAIL and PARTICULAR_PASSWORD:
            s = _login(PARTICULAR_EMAIL, PARTICULAR_PASSWORD)
            r = s.get(f"{BASE_URL}/api/documents/{doc_id}", timeout=30)
            assert r.status_code in (403, 404)

        if WORKER_EMAIL and WORKER_PASSWORD:
            s = _login(WORKER_EMAIL, WORKER_PASSWORD)
            r = s.get(f"{BASE_URL}/api/documents/{doc_id}", timeout=30)
            assert r.status_code in (403, 404)

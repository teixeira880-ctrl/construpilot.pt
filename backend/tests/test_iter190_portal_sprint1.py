"""Iter 190 — Espace Client & Sous-traitant, Sprint 1 : invitations, session participant, jalons, publication, isolation."""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def pro():
    return _login("pro@construpilot.fr", "Pro2026!")


@pytest.fixture(scope="module")
def collegue():
    return _login("collegue@construpilot.fr", "Collegue2026!")


@pytest.fixture(scope="module")
def ctx(pro):
    a = pro.post(f"{BASE_URL}/api/chantiers", json={"name": "Iter190 Portail A", "city": "Nantes"}).json()
    b = pro.post(f"{BASE_URL}/api/chantiers", json={"name": "Iter190 Portail B"}).json()
    yield {"a": a, "b": b}
    for c in (a, b):
        pro.delete(f"{BASE_URL}/api/chantiers/{c['chantier_id']}")


@pytest.fixture(scope="module")
def invite(pro, ctx):
    email = f"client-{uuid.uuid4().hex[:8]}@example.com"
    r = pro.post(f"{BASE_URL}/api/chantiers/{ctx['a']['chantier_id']}/participants", json={"role": "client", "email": email, "name": "Sophie Cliente"})
    assert r.status_code == 201, r.text
    dup = pro.post(f"{BASE_URL}/api/chantiers/{ctx['a']['chantier_id']}/participants", json={"role": "client", "email": email.upper()})
    return {**r.json(), "_dup_status": dup.status_code}


class TestInvitations:
    def test_invite_creates_ref_and_link(self, invite):
        assert invite["status"] == "invited" and invite["role"] == "client"
        assert invite["chantier_ref"].startswith("CP-") and len(invite["chantier_ref"]) == 12
        assert "/espace/invitation/" in invite["invite_link"]
        assert invite["invite_email_status"] in ("sent", "failed")
        assert "invite_token_hash" not in invite
        assert invite["permissions"]["quotes"] is True and invite["permissions"]["post_reports"] is False

    def test_duplicate_email_409(self, invite):
        assert invite["_dup_status"] == 409

    def test_list_and_permissions(self, pro, ctx, invite):
        lst = pro.get(f"{BASE_URL}/api/chantiers/{ctx['a']['chantier_id']}/participants").json()
        assert lst["ref"] == invite["chantier_ref"]
        assert any(p["participant_id"] == invite["participant_id"] for p in lst["participants"])
        r = pro.put(f"{BASE_URL}/api/chantiers/{ctx['a']['chantier_id']}/participants/{invite['participant_id']}/permissions", json={"permissions": {"photos": False, "unknown": True}})
        assert r.status_code == 200 and r.json()["permissions"]["photos"] is False and "unknown" not in r.json()["permissions"]
        pro.put(f"{BASE_URL}/api/chantiers/{ctx['a']['chantier_id']}/participants/{invite['participant_id']}/permissions", json={"permissions": {"photos": True}})

    def test_other_pro_cannot_manage(self, collegue, ctx, invite):
        assert collegue.get(f"{BASE_URL}/api/chantiers/{ctx['a']['chantier_id']}/participants").status_code == 404
        assert collegue.post(f"{BASE_URL}/api/chantiers/{ctx['a']['chantier_id']}/participants/{invite['participant_id']}/revoke").status_code == 404


class TestParticipantSession:
    @pytest.fixture(scope="class")
    def guest(self, invite):
        token = invite["invite_link"].rsplit("/", 1)[-1]
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/portal/accept/{token}", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["participant"]["status"] == "active"
        assert "participant_session" in s.cookies
        return s

    def test_token_reuse_only_within_grace_then_dead(self, invite, guest):
        """Double appel navigateur toléré 15 min ; au-delà (simulé en base) le lien est définitivement mort."""
        token = invite["invite_link"].rsplit("/", 1)[-1]
        assert requests.post(f"{BASE_URL}/api/portal/accept/{token}", timeout=30).status_code == 200
        import asyncio, os
        from dotenv import load_dotenv
        from motor.motor_asyncio import AsyncIOMotorClient
        load_dotenv("/app/backend/.env")
        async def age():
            db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
            await db.chantier_participants.update_one({"participant_id": invite["participant_id"]}, {"$set": {"accepted_at": "2020-01-01T00:00:00+00:00"}})
        asyncio.new_event_loop().run_until_complete(age())
        assert requests.post(f"{BASE_URL}/api/portal/accept/{token}", timeout=30).status_code == 404
        assert requests.post(f"{BASE_URL}/api/portal/accept/{token}", timeout=30).status_code == 404

    def test_me_and_overview(self, pro, ctx, invite, guest):
        cid = ctx["a"]["chantier_id"]
        ms = pro.post(f"{BASE_URL}/api/chantiers/{cid}/milestones", json={"title": "Démolition", "status": "done", "progress_pct": 100}).json()
        pro.post(f"{BASE_URL}/api/chantiers/{cid}/milestones", json={"title": "Plâtrerie", "status": "in_progress", "progress_pct": 50})
        pro.post(f"{BASE_URL}/api/chantiers/{cid}/milestones", json={"title": "Secret", "visible": False, "progress_pct": 0})
        rep = pro.post(f"{BASE_URL}/api/site/reports", json={"project": "Iter190 Portail A", "title": "CR interne", "notes": "note", "photos": [], "chantier_id": cid})
        report_id = rep.json().get("report_id") if rep.status_code == 200 else None
        me = guest.get(f"{BASE_URL}/api/portal/me").json()
        assert me["participant"]["participant_id"] == invite["participant_id"]
        assert any(c["ref"] == invite["chantier_ref"] for c in me["chantiers"])
        ov = guest.get(f"{BASE_URL}/api/portal/{invite['chantier_ref']}/overview").json()
        assert ov["chantier"]["name"] == "Iter190 Portail A" and ov["progress_pct"] == 75
        assert [m["title"] for m in ov["milestones"]] == ["Démolition", "Plâtrerie"], "jalon masqué ne doit pas apparaître"
        assert ov["reports"] == [], "compte rendu non publié = invisible"
        if report_id:
            assert pro.put(f"{BASE_URL}/api/chantiers/{cid}/reports/{report_id}/publish", json={"published": True}).status_code == 200
            ov = guest.get(f"{BASE_URL}/api/portal/{invite['chantier_ref']}/overview").json()
            assert [r["report_id"] for r in ov["reports"]] == [report_id]
            pro.delete(f"{BASE_URL}/api/site/reports/{report_id}")
        pro.delete(f"{BASE_URL}/api/chantiers/{cid}/milestones/{ms['milestone_id']}")

    def test_isolation_other_chantier(self, guest, ctx, pro):
        other_ref = pro.get(f"{BASE_URL}/api/chantiers/{ctx['b']['chantier_id']}/participants").json()["ref"]
        r = guest.get(f"{BASE_URL}/api/portal/{other_ref or 'CP-ZZZZ-ZZZZ'}/overview")
        assert r.status_code in (403, 404)
        assert guest.get(f"{BASE_URL}/api/portal/{ctx['a']['ref'] if ctx['a'].get('ref') else 'CP-AAAA-AAAA'}/photo", params={"path": "x"}).status_code in (403, 404)

    def test_otp_flow_wrong_code(self, invite):
        r = requests.post(f"{BASE_URL}/api/portal/login", json={"ref": invite["chantier_ref"].lower(), "email": invite["email"]}, timeout=30)
        assert r.status_code == 200 and r.json()["ok"]
        r2 = requests.post(f"{BASE_URL}/api/portal/login", json={"ref": invite["chantier_ref"], "email": "nobody@example.com"}, timeout=30)
        assert r2.status_code == 200 and r2.json() == r.json(), "réponse identique : pas d'énumération"
        v = requests.post(f"{BASE_URL}/api/portal/verify", json={"ref": invite["chantier_ref"], "email": invite["email"], "code": "000000"}, timeout=30)
        assert v.status_code == 401

    def test_revoke_cuts_session(self, pro, ctx, invite, guest):
        assert guest.get(f"{BASE_URL}/api/portal/me").status_code == 200
        assert pro.post(f"{BASE_URL}/api/chantiers/{ctx['a']['chantier_id']}/participants/{invite['participant_id']}/revoke").status_code == 200
        assert guest.get(f"{BASE_URL}/api/portal/me").status_code == 401
        assert guest.get(f"{BASE_URL}/api/portal/{invite['chantier_ref']}/overview").status_code == 401

    def test_anonymous_blocked(self, invite):
        assert requests.get(f"{BASE_URL}/api/portal/me", timeout=30).status_code == 401
        assert requests.get(f"{BASE_URL}/api/portal/{invite['chantier_ref']}/overview", timeout=30).status_code == 401

"""Sprint 2 portail : messagerie par canaux + pièces jointes, signalement → réserve, confirmation client, dictée portail (auth)."""
import io
import os

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL") or (open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].splitlines()[0].strip() + "/api")
PRO = (os.environ.get("TEST_PRO_EMAIL", "pro@construpilot.fr"), os.environ.get("TEST_PRO_PASSWORD", "Pro2026!"))
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0300050001f6d8c9d10000000049454e44ae426082")


@pytest.fixture(scope="module")
def pro():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": PRO[0], "password": PRO[1]})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def chantier(pro):
    r = pro.post(f"{BASE}/chantiers", json={"name": "TEST S2 Portail", "status": "en_cours", "city": "Paris"})
    assert r.status_code in (200, 201), r.text
    c = r.json()
    yield c
    pro.delete(f"{BASE}/chantiers/{c['chantier_id']}")


@pytest.fixture(scope="module")
def guest(pro, chantier):
    r = pro.post(f"{BASE}/chantiers/{chantier['chantier_id']}/participants", json={"role": "client", "email": "delivered@resend.dev", "name": "Sophie Test"})
    assert r.status_code == 201, r.text
    part = r.json()
    token = part["invite_link"].rsplit("/", 1)[1]
    g = requests.Session()
    a = g.post(f"{BASE}/portal/accept/{token}")
    assert a.status_code == 200, a.text
    return g, part


@pytest.fixture(scope="module")
def other_guest(pro):
    """Participant d'un AUTRE chantier : ne doit rien voir du premier."""
    r = pro.post(f"{BASE}/chantiers", json={"name": "TEST S2 Autre", "status": "en_cours"})
    c = r.json()
    p = pro.post(f"{BASE}/chantiers/{c['chantier_id']}/participants", json={"role": "client", "email": "delivered@resend.dev"}).json()
    g = requests.Session()
    assert g.post(f"{BASE}/portal/accept/{p['invite_link'].rsplit('/', 1)[1]}").status_code == 200
    yield g, p
    pro.delete(f"{BASE}/chantiers/{c['chantier_id']}")


class TestMessages:
    def test_guest_sends_with_attachment(self, guest, chantier, pro):
        g, part = guest
        ref = part["chantier_ref"]
        r = g.post(f"{BASE}/portal/{ref}/messages", data={"body": "Bonjour, quand posez-vous le carrelage ?"}, files=[("files", ("photo.png", io.BytesIO(PNG), "image/png"))])
        assert r.status_code == 201, r.text
        m = r.json()
        assert m["channel"] == "client" and m["author_type"] == "participant" and len(m["attachments"]) == 1
        # le pro voit le message dans le canal client, compteur non lu = 1 avant lecture
        inbox = pro.get(f"{BASE}/chantiers/{chantier['chantier_id']}/inbox").json()
        assert inbox["unread"]["client"] >= 1
        lst = pro.get(f"{BASE}/chantiers/{chantier['chantier_id']}/messages", params={"channel": "client"}).json()["messages"]
        assert any(x["message_id"] == m["message_id"] for x in lst)
        assert pro.get(f"{BASE}/chantiers/{chantier['chantier_id']}/inbox").json()["unread"]["client"] == 0
        # pièce jointe servie au pro et à l'invité, pas au canal sous-traitants
        path = m["attachments"][0]["path"]
        assert pro.get(f"{BASE}/chantiers/{chantier['chantier_id']}/messages/file", params={"path": path}).status_code == 200
        assert g.get(f"{BASE}/portal/{ref}/messages/file", params={"path": path}).status_code == 200
        # notification cloche créée pour le pro
        notifs = pro.get(f"{BASE}/notifications").json()
        items = notifs if isinstance(notifs, list) else notifs.get("items") or notifs.get("notifications") or []
        assert any(n.get("type") == "portal_message" for n in items)

    def test_pro_reply_and_channels_isolated(self, guest, chantier, pro):
        g, part = guest
        r = pro.post(f"{BASE}/chantiers/{chantier['chantier_id']}/messages", data={"channel": "client", "body": "La semaine prochaine, mardi."})
        assert r.status_code == 201, r.text
        r2 = pro.post(f"{BASE}/chantiers/{chantier['chantier_id']}/messages", data={"channel": "subcontractors", "body": "Secret sous-traitants"})
        assert r2.status_code == 201
        msgs = g.get(f"{BASE}/portal/{part['chantier_ref']}/messages").json()["messages"]
        bodies = [m["body"] for m in msgs]
        assert "La semaine prochaine, mardi." in bodies and "Secret sous-traitants" not in bodies

    def test_rejects_empty_and_bad_type(self, guest):
        g, part = guest
        assert g.post(f"{BASE}/portal/{part['chantier_ref']}/messages", data={"body": ""}).status_code == 422
        r = g.post(f"{BASE}/portal/{part['chantier_ref']}/messages", data={"body": "x"}, files=[("files", ("a.exe", io.BytesIO(b"MZ"), "application/octet-stream"))])
        assert r.status_code == 415

    def test_other_chantier_isolated(self, other_guest, guest):
        g2, _ = other_guest
        _, part = guest
        assert g2.get(f"{BASE}/portal/{part['chantier_ref']}/messages").status_code == 403
        assert g2.post(f"{BASE}/portal/{part['chantier_ref']}/messages", data={"body": "intrus"}).status_code == 403

    def test_chat_permission_enforced(self, guest, chantier, pro):
        g, part = guest
        pid, cid = part["participant_id"], chantier["chantier_id"]
        assert pro.put(f"{BASE}/chantiers/{cid}/participants/{pid}/permissions", json={"permissions": {"chat": False}}).status_code == 200
        assert g.get(f"{BASE}/portal/{part['chantier_ref']}/messages").status_code == 403
        pro.put(f"{BASE}/chantiers/{cid}/participants/{pid}/permissions", json={"permissions": {"chat": True}})


class TestIssues:
    def test_report_creates_reserve(self, guest, chantier, pro):
        g, part = guest
        ref, cid = part["chantier_ref"], chantier["chantier_id"]
        r = g.post(f"{BASE}/portal/{ref}/issues", data={"title": "Fuite sous l'évier", "description": "Depuis hier soir", "location": "Cuisine", "urgency": "high"},
                   files=[("files", ("fuite.png", io.BytesIO(PNG), "image/png"))])
        assert r.status_code == 201, r.text
        issue = r.json()
        assert issue["status"] == "new" and issue["reserve_id"] and len(issue["photos"]) == 1
        reserves = pro.get(f"{BASE}/site/reserves", params={"project": chantier["name"]}).json()
        rs = next(x for x in reserves if x["reserve_id"] == issue["reserve_id"])
        assert rs["status"] == "open" and rs["lot"] == "Cuisine" and "Fuite" in rs["description"] and rs.get("chantier_id") == cid
        dossier = pro.get(f"{BASE}/chantiers/{cid}").json()
        assert dossier["kpis"]["open_reserves"] >= 1
        inbox = pro.get(f"{BASE}/chantiers/{cid}/inbox").json()
        assert inbox["new_issues"] >= 1
        pytest.issue = issue

    def test_pro_updates_and_client_confirms(self, guest, chantier, pro):
        g, part = guest
        ref, cid, iid = part["chantier_ref"], chantier["chantier_id"], pytest.issue["issue_id"]
        r = pro.put(f"{BASE}/chantiers/{cid}/issues/{iid}", json={"status": "in_progress", "assignee": "Plombier Karim", "pro_response": "Intervention mardi matin."})
        assert r.status_code == 200 and r.json()["status"] == "in_progress"
        # tant que non résolu, le client ne peut pas confirmer
        assert g.post(f"{BASE}/portal/{ref}/issues/{iid}/confirm", json={"resolved": True}).status_code == 409
        pro.put(f"{BASE}/chantiers/{cid}/issues/{iid}", json={"status": "resolved"})
        reserves = pro.get(f"{BASE}/site/reserves", params={"project": chantier["name"]}).json()
        assert next(x for x in reserves if x["reserve_id"] == pytest.issue["reserve_id"])["status"] == "lifted"
        mine = g.get(f"{BASE}/portal/{ref}/issues").json()["issues"]
        me = next(x for x in mine if x["issue_id"] == iid)
        assert me["status"] == "resolved" and me["pro_response"] == "Intervention mardi matin." and "history" not in me
        # client : pas réglé → réserve rouverte
        assert g.post(f"{BASE}/portal/{ref}/issues/{iid}/confirm", json={"resolved": False, "comment": "Ça goutte encore"}).status_code == 200
        reserves = pro.get(f"{BASE}/site/reserves", params={"project": chantier["name"]}).json()
        assert next(x for x in reserves if x["reserve_id"] == pytest.issue["reserve_id"])["status"] == "open"
        assert pro.get(f"{BASE}/chantiers/{cid}/issues").json()["issues"][0]["client_confirmed"] is False
        # puis réglé → clôturé
        pro.put(f"{BASE}/chantiers/{cid}/issues/{iid}", json={"status": "resolved"})
        r = g.post(f"{BASE}/portal/{ref}/issues/{iid}/confirm", json={"resolved": True})
        assert r.status_code == 200 and r.json()["status"] == "closed"

    def test_issue_isolation(self, other_guest, guest):
        g2, _ = other_guest
        _, part = guest
        assert g2.get(f"{BASE}/portal/{part['chantier_ref']}/issues").status_code == 403
        assert g2.post(f"{BASE}/portal/{part['chantier_ref']}/issues/{pytest.issue['issue_id']}/confirm", json={"resolved": True}).status_code == 403
        assert g2.get(f"{BASE}/portal/{part['chantier_ref']}/messages/file", params={"path": pytest.issue["photos"][0]["path"]}).status_code == 403


def test_portal_transcribe_requires_session():
    r = requests.post(f"{BASE}/speech/portal/transcribe", files={"file": ("a.webm", b"x", "audio/webm")})
    assert r.status_code == 401

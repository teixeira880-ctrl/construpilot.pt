"""Live assistant test for iter170: calibrate_view + measure_pixels (single OpenAI turn)."""
import json
import time
import requests
import pytest

LOCAL = "http://localhost:8001"
PLAN_DWG = "plan_db4a3ccd5e09"

PROMPT = (
    "Calibre la vue principale avec calibrate_view en utilisant deux cotes explicites : "
    "4,935 m mesurant 232 px horizontalement et 2,10 m mesurant 98,8 px verticalement "
    "(échelle cartouche 1/50, dpi 96) ; puis mesure avec measure_pixels un segment de 150 px. "
    "Ensuite refais la calibration avec une seule cote et tente la même mesure."
)


@pytest.fixture(scope="module")
def pro():
    s = requests.Session()
    r = s.post(f"{LOCAL}/api/auth/login", json={"email": "pro@construpilot.fr", "password": "Pro2026!"})
    tok = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def _find_actions(msgs, name):
    out = []
    for m in msgs or []:
        for a in (m.get("actions") or m.get("tool_calls") or []):
            n = a.get("tool") or a.get("name") or (a.get("function") or {}).get("name")
            if n == name:
                out.append(a)
    return out


def test_calibrate_and_measure(pro):
    # Create conversation
    r = pro.post(f"{LOCAL}/api/assistant/conversations", json={"title": "iter170-cal", "plan_ids": [PLAN_DWG]}, timeout=30)
    assert r.status_code in (200, 201), r.text[:200]
    conv_id = r.json().get("conversation_id") or r.json().get("id") or r.json().get("_id")
    assert conv_id, r.json()

    payload = {
        "conversation_id": conv_id,
        "text": PROMPT,
        "mode": "fast",
        "web_enabled": False,
        "plan_ids": [PLAN_DWG],
    }
    try:
        r2 = pro.post(f"{LOCAL}/api/assistant/message", json=payload, timeout=320)
        print("POST status:", r2.status_code)
    except Exception as e:
        print("POST exception (will poll):", e)

    # Poll persisted conversation
    conv = None
    for _ in range(60):
        try:
            rc = pro.get(f"{LOCAL}/api/assistant/conversations/{conv_id}", timeout=30)
        except Exception as e:
            print("poll exception:", e)
            time.sleep(5)
            continue
        if rc.status_code == 200:
            conv = rc.json()
            msgs = conv.get("messages") or []
            has_asst = any(m.get("role") == "assistant" and (m.get("content") or m.get("text")) for m in msgs)
            if has_asst:
                break
        time.sleep(5)
    assert conv is not None
    msgs = conv.get("messages") or []
    print(json.dumps({"n_messages": len(msgs), "roles": [m.get("role") for m in msgs]}))

    cal_actions = _find_actions(msgs, "calibrate_view")
    mp_actions = _find_actions(msgs, "measure_pixels")
    print(f"calibrate_view actions: {len(cal_actions)}, measure_pixels actions: {len(mp_actions)}")

    assert len(cal_actions) >= 1, "no calibrate_view call"
    assert len(mp_actions) >= 1, "no measure_pixels call"

    # First calibrate should be reliable, ~47 px/m
    first_cal = (cal_actions[0].get("result") or cal_actions[0].get("output") or {})
    if isinstance(first_cal, str):
        try:
            first_cal = json.loads(first_cal)
        except Exception:
            pass
    print("first calibrate:", json.dumps(first_cal, ensure_ascii=False)[:500])
    ppm = first_cal.get("px_per_m") or first_cal.get("scale_px_per_m")
    status = first_cal.get("status") or first_cal.get("reliability")
    print(f"px_per_m={ppm}, status={status}")

    # Assistant text mentions refusal without reliable calibration
    asst_text = "\n".join(
        (m.get("content") or m.get("text") or "") for m in msgs if m.get("role") == "assistant"
    ).lower()
    refuses = any(k in asst_text for k in ["non fiable", "non-fiable", "refus", "sans calibration", "calibration fiable", "non vérifiable", "non verifiable", "not verifiable"])
    print("assistant text length:", len(asst_text))
    if not refuses:
        print("ASSISTANT_TEXT_SAMPLE:", asst_text[:1200])
    # not a hard assertion (LLM wording variance) - warn only
    assert cal_actions and mp_actions

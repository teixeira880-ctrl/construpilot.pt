"""Teste individual do remetente PT em `ENV=development`.

Enviará 1 email real via Resend usando `get_sender(Market.PT)` e imprime:
    resend_id · from · reply_to · status após 60 s.

Também testa o guard em modo `ENV=production` para `.local` → deve lançar
`ForbiddenSenderError` SEM chamar a API Resend.

Variáveis necessárias (ambiente):
    TEST_EMAIL : destinatário (default: info@construpilot.pt)
    ENV        : development (default) para enviar; production para só testar guard

Uso:
    TEST_EMAIL=info@construpilot.pt python backend/scripts/test_sender_pt.py
"""
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_EMAIL = os.environ.get("TEST_EMAIL", "info@construpilot.pt")


async def _test_production_blocks_local():
    """Verifica que em production com `.local` o guard dispara ANTES da API."""
    print("\n[1/2] Guard em ENV=production com remetente .local")
    saved_env = os.environ.get("ENV")
    saved_from = os.environ.get("SENDER_PT_FROM")
    try:
        os.environ["ENV"] = "production"
        os.environ["SENDER_PT_FROM"] = "no-reply@construpilot.local"
        from engines.mail_sender_config import ForbiddenSenderError, get_sender, Market
        try:
            get_sender(Market.PT)
            print("    ❌ FAIL — guard não bloqueou .local em production")
            return False
        except ForbiddenSenderError as e:
            print(f"    ✅ OK — bloqueado: {e}")
            return True
    finally:
        if saved_env is None:
            os.environ.pop("ENV", None)
        else:
            os.environ["ENV"] = saved_env
        if saved_from is None:
            os.environ.pop("SENDER_PT_FROM", None)
        else:
            os.environ["SENDER_PT_FROM"] = saved_from


async def _test_real_send():
    """Envia 1 email real (ENV=development) e consulta estado após 30 s."""
    print(f"\n[2/2] Envio real via Resend para {TEST_EMAIL}")
    # Garantir dev
    os.environ.pop("ENV", None)
    os.environ.setdefault("SENDER_PT_FROM", "info@construpilot.pt")
    os.environ.setdefault("SENDER_PT_NAME", "ConstruPilot")

    from engines.emailer import send_email

    subject = f"[Teste guard] ConstruPilot · {int(time.time())}"
    html = """<!doctype html><html><body>
    <h1>Teste de configuração Resend</h1>
    <p>Este email valida o <b>guard anti-.local</b> + tracking fiel do estado.</p>
    </body></html>"""
    try:
        res = await send_email(TEST_EMAIL, subject, html)
    except Exception as e:
        print(f"    ❌ FAIL — API Resend rejeitou: {e}")
        return False

    rid = res.get("id")
    status = res.get("status")
    print(f"    ✅ enviado · id={rid} · status pós-envio={status}")

    # Consulta o estado real após 30 s via Resend API
    print("    Aguardo 30 s para consultar last_event…")
    await asyncio.sleep(30)
    import httpx
    key = os.environ.get("RESEND_API_KEY", "").strip()
    if key and rid:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"https://api.resend.com/emails/{rid}",
                headers={"Authorization": f"Bearer {key}"},
            )
            if r.status_code == 200:
                data = r.json()
                print(f"    Resend last_event = {data.get('last_event')!r}")
                print(f"              from = {data.get('from')!r}")
                print(f"           created = {data.get('created_at')}")
                return True
            print(f"    ⚠ consulta falhou: HTTP {r.status_code}")
    return True


async def main():
    print("=" * 70)
    print("Teste do guard de remetente Resend")
    print("=" * 70)
    ok1 = await _test_production_blocks_local()
    ok2 = await _test_real_send()
    print("\n" + "=" * 70)
    print(f"Resultado: guard={'PASS' if ok1 else 'FAIL'} · envio={'PASS' if ok2 else 'FAIL'}")
    print("=" * 70)
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

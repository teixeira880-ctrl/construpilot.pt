"""Ativa a conversão DWG→DXF com o AutoCAD da Autodesk (Automation API) para a aplicação Autodesk já ligada (AUTODESK_CLIENT_ID).

Uso (no pod, a partir de /app/backend):  python3 scripts/aps_provision_dwg.py [--create]
- sem --create: só verifica o acesso (token + lista de motores AutoCAD) e mostra o motor mais recente. Nada é criado.
- com --create: cria (ou confirma) a activity «ConstruPilotDwgToDxf» com o alias «prod» e o bucket temporário.
Nunca imprime client id, secret ou token. Nenhum WorkItem é submetido (zero conversão, zero consumo de tokens Flex).
No fim imprime as 4 linhas a colar no painel Live (valores não secretos)."""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

ACTIVITY_ID = "ConstruPilotDwgToDxf"
ALIAS = "prod"


def _latest_autocad(engine_ids):
    def key(e):
        m = re.search(r"\+(\d+)(?:_(\d+))?", e)
        return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)
    cad = [e for e in engine_ids if e.startswith("Autodesk.AutoCAD+")]
    return max(cad, key=key) if cad else None


async def main(create: bool):
    from engines.autodesk_client import AutodeskError, api_base, config, request
    if not config("APS_CLIENT_ID") or not config("APS_CLIENT_SECRET"):
        print(json.dumps({"ok": False, "erro": "credenciais Autodesk ausentes no .env (AUTODESK_CLIENT_ID / AUTODESK_CLIENT_SECRET)"}))
        raise SystemExit(1)
    out = {"ok": False, "criado": False, "workitems_submetidos": 0}
    try:
        engines, page = [], None
        for _ in range(10):
            url = f"{api_base()}/engines" + (f"?page={page}" if page else "")
            body = (await request("GET", url)).json()
            engines += body.get("data", []) if isinstance(body, dict) else body
            page = body.get("paginationToken") if isinstance(body, dict) else None
            if not page:
                break
        engine = _latest_autocad(engines)
        out["motores_autocad"] = sorted(e for e in engines if e.startswith("Autodesk.AutoCAD+"))
        out["motor_escolhido"] = engine
        if not engine:
            out["erro"] = "nenhum motor AutoCAD disponível para esta aplicação"
            print(json.dumps(out, ensure_ascii=False)); raise SystemExit(1)
        if not create:
            out["ok"] = True
            out["nota"] = "acesso OK; relançar com --create para criar a activity"
            print(json.dumps(out, ensure_ascii=False)); return
        os.environ.update({"APS_ACTIVITY_ID": ACTIVITY_ID, "APS_ACTIVITY_ALIAS": ALIAS, "APS_ENGINE": engine})
        from engines.autodesk_activity import provision
        res = await provision()
        out.update(ok=True, criado=bool(res.get("created")), versao=res.get("version"),
                   painel_live={"APS_ACTIVITY_ID": ACTIVITY_ID, "APS_ACTIVITY_ALIAS": ALIAS, "APS_ENGINE": engine,
                                "APS_ACTIVITY_QUALIFIED": "(copiar do .env da preview; começa pelo namespace da aplicação)"})
        # O nome qualificado começa pelo namespace da aplicação (apelido ou client id): não é secreto, mas pode ser o client id.
        # Escreve-o só no .env da preview; para o Live, o operador copia-o de lá sem o mostrar em relatórios.
        from dotenv import set_key
        for k, v in {"APS_ACTIVITY_ID": ACTIVITY_ID, "APS_ACTIVITY_ALIAS": ALIAS, "APS_ENGINE": engine,
                     "APS_ACTIVITY_QUALIFIED": res["qualified_activity"]}.items():
            set_key(str(ROOT / ".env"), k, v)
        out["env_preview_atualizado"] = ["APS_ACTIVITY_ID", "APS_ACTIVITY_ALIAS", "APS_ENGINE", "APS_ACTIVITY_QUALIFIED"]
        print(json.dumps(out, ensure_ascii=False))
    except AutodeskError as exc:
        out["erro"] = {"codigo": exc.code, "http": exc.status, "mensagem": str(exc)}
        print(json.dumps(out, ensure_ascii=False)); raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main("--create" in sys.argv))

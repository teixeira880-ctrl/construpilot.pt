"""Operator-only provisioning; never creates resources during a plan upload."""
import hashlib
import json
from urllib.parse import quote

from engines.autodesk_client import AutodeskError, api_base, config, request
from engines.autodesk_storage import ensure_bucket

SCRIPT = "FILEDIA\n0\nCMDDIA\n0\n_.DXFOUT\nresult.dxf\n\n"


def definition():
    return {"id": config("APS_ACTIVITY_ID"), "engine": config("APS_ENGINE"),
        "description": "ConstruPilot native DWG to DXF export", "appbundles": [],
        "commandLine": ['"$(engine.path)\\accoreconsole.exe" /i "$(args[inputFile].path)" /s "$(settings[script].path)"'],
        "parameters": {"inputFile": {"verb": "get", "required": True, "localName": "input.dwg"},
                       "outputFile": {"verb": "put", "required": True, "localName": "result.dxf"}},
        "settings": {"script": {"value": SCRIPT}}}


def specification_hash():
    return hashlib.sha256(json.dumps(definition(), sort_keys=True).encode()).hexdigest()


async def provision():
    """Only own named activity/alias/bucket. No app renaming or WorkItems."""
    name = (await request("GET", f"{api_base()}/forgeapps/me")).json()
    if not isinstance(name, str) or not name:
        raise AutodeskError("namespace_missing", "Espaço Autodesk não definido: configuração de administrador necessária.", fallback_safe=True)
    desired = definition()
    endpoint = f"{api_base()}/activities/{quote(desired['id'], safe='')}"
    # Full-activity GET resolves namespace.name+alias, not a numeric version label.
    response = await request("GET", f"{endpoint}/versions", accepted=(404,))
    created = response.status_code == 404
    if created:
        activity = (await request("POST", f"{api_base()}/activities", json=desired)).json()
    else:
        body = response.json()
        versions = body.get("data", []) if isinstance(body, dict) else body
        if not versions:
            raise AutodeskError("activity_versions_missing", "Versões Autodesk não encontradas.", fallback_safe=True)
        version = max(int(v["version"] if isinstance(v, dict) else v) for v in versions)
        qualified = quote(f"{name}.{desired['id']}+{config('APS_ACTIVITY_ALIAS')}", safe="")
        activity = (await request("GET", f"{api_base()}/activities/{qualified}")).json()
        if activity.get("version") != version:
            raise AutodeskError("alias_mismatch", "O alias Autodesk não aponta para a versão esperada.", fallback_safe=True)
    actual_script = activity.get("settings", {}).get("script")
    if isinstance(actual_script, dict):
        actual_script = actual_script.get("value")
    if activity.get("engine") != desired["engine"] or actual_script != SCRIPT or activity.get("commandLine") != desired["commandLine"]:
        raise AutodeskError("activity_mismatch", "A atividade Autodesk existente difere do script aprovado.", fallback_safe=True)
    aliases = (await request("GET", f"{endpoint}/aliases")).json()
    entries = aliases.get("data", []) if isinstance(aliases, dict) else aliases
    alias_name = config("APS_ACTIVITY_ALIAS")
    alias = next((a for a in entries if a.get("id") == alias_name), None)
    if alias and alias.get("version") != activity.get("version"):
        raise AutodeskError("alias_mismatch", "O alias Autodesk aponta para outra versão.", fallback_safe=True)
    if not alias:
        await request("POST", f"{endpoint}/aliases", json={"id": alias_name, "version": activity["version"]})
    await ensure_bucket()
    return {"qualified_activity": f"{name}.{desired['id']}+{alias_name}", "engine": desired["engine"],
            "version": activity["version"], "specification_sha256": specification_hash(), "created": created}
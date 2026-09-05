"""Conversion DWG → DXF via l'API CloudConvert v2.

Le DWG est un format AutoCAD propriétaire binaire qu'aucune lib Python ne lit
directement. On délègue la conversion à CloudConvert : création d'un job
(import/upload → convert dwg→dxf → export/url), upload des octets, attente
synchrone, puis téléchargement du DXF résultant.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("dwg_convert")

API_BASE = "https://api.cloudconvert.com/v2"
SYNC_BASE = "https://sync.api.cloudconvert.com/v2"


def is_configured() -> bool:
    return bool(os.environ.get("CLOUDCONVERT_API_KEY"))


async def dwg_to_dxf(dwg_bytes: bytes, filename: str = "plan.dwg") -> bytes:
    """Convertit des octets DWG en octets DXF. Lève RuntimeError si échec."""
    api_key = os.environ.get("CLOUDCONVERT_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Conversion DWG indisponible : convertissez le fichier en DXF (LibreCAD, "
            "AutoCAD « Enregistrer sous → DXF ») puis réimportez-le."
        )

    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    timeout = httpx.Timeout(connect=20.0, read=180.0, write=120.0, pool=20.0)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        job_payload = {
            "tasks": {
                "upload-dwg": {"operation": "import/upload"},
                "convert-dxf": {
                    "operation": "convert",
                    "input": "upload-dwg",
                    "input_format": "dwg",
                    "output_format": "dxf",
                    "filename": "converted.dxf",
                },
                "export-dxf": {"operation": "export/url", "input": "convert-dxf"},
            }
        }
        create = await client.post(f"{API_BASE}/jobs", headers=headers, json=job_payload)
        if create.status_code == 429:
            raise RuntimeError("Service de conversion DWG saturé — réessayez dans un instant.")
        if not create.is_success:
            logger.error("CloudConvert job creation failed %s: %s", create.status_code, create.text[:300])
            raise RuntimeError("Conversion DWG impossible (création du job).")

        job = create.json()["data"]
        job_id = job["id"]
        upload_task = next(t for t in job["tasks"] if t["name"] == "upload-dwg")
        form = upload_task["result"]["form"]

        form_data = {str(k): str(v) for k, v in form["parameters"].items()}
        up_name = filename if filename.lower().endswith(".dwg") else "input.dwg"
        files = {"file": (up_name, dwg_bytes, "application/acad")}
        uploaded = await client.post(form["url"], data=form_data, files=files)
        if not uploaded.is_success:
            logger.error("CloudConvert upload failed %s: %s", uploaded.status_code, uploaded.text[:300])
            raise RuntimeError("Conversion DWG impossible (envoi du fichier).")

        waited = await client.get(f"{SYNC_BASE}/jobs/{job_id}", headers=headers)
        if not waited.is_success:
            logger.error("CloudConvert wait failed %s: %s", waited.status_code, waited.text[:300])
            raise RuntimeError("Conversion DWG impossible (attente).")

        finished = waited.json()["data"]
        if finished.get("status") != "finished":
            errs = [
                f"{t.get('name')}: {t.get('code') or t.get('message') or t.get('status')}"
                for t in finished.get("tasks", []) if t.get("status") == "error"
            ]
            logger.error("CloudConvert conversion error: %s", "; ".join(errs))
            raise RuntimeError("Le fichier DWG n'a pas pu être converti (fichier corrompu ou non supporté).")

        export_task = next(t for t in finished["tasks"] if t["name"] == "export-dxf")
        out_files = export_task.get("result", {}).get("files", [])
        if not out_files or not out_files[0].get("url"):
            raise RuntimeError("Conversion DWG impossible (aucun DXF produit).")

        download = await client.get(out_files[0]["url"])
        if not download.is_success:
            raise RuntimeError("Conversion DWG impossible (téléchargement du DXF).")
        return download.content

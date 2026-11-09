"""Conversion DWG → DXF : ODA local, Autodesk si activé, puis CloudConvert historique.

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

API_BASE = os.environ["CLOUDCONVERT_API_BASE"].rstrip("/")
SYNC_BASE = os.environ["CLOUDCONVERT_SYNC_BASE"].rstrip("/")


def is_configured() -> bool:
    return bool(os.environ.get("ODA_FILE_CONVERTER") or os.environ.get("CLOUDCONVERT_API_KEY") or
                (os.environ.get("APS_DWG_ENABLED") == "true" and os.environ.get("APS_ACTIVITY_QUALIFIED")))


async def dwg_to_dxf(dwg_bytes: bytes, filename: str = "plan.dwg", *, user_id=None, provenance=None) -> bytes:
    """Convertit des octets DWG en octets DXF. Lève RuntimeError si échec."""
    import asyncio
    import re
    if not re.match(rb"AC10[0-9]{2}",dwg_bytes[:6]):
        raise RuntimeError("O ficheiro não tem uma assinatura DWG AutoCAD reconhecida")
    if os.environ.get("ODA_FILE_CONVERTER"):
        output = await asyncio.to_thread(_local_dwg_to_dxf,dwg_bytes)
        if provenance is not None: provenance.update(provider="oda", status="converted")
        return output
    if os.environ.get("APS_DWG_ENABLED") == "true":
        from engines.autodesk_client import AutodeskError
        from engines.autodesk_dwg import convert
        try:
            output, metadata = await convert(dwg_bytes, user_id=user_id)
            if provenance is not None: provenance.update(metadata)
            return output
        except AutodeskError as exc:
            if not exc.fallback_safe or os.environ.get("APS_DWG_FALLBACK_ENABLED") != "true":
                raise
            if provenance is not None: provenance.update(fallback_reason=exc.code)
    api_key = os.environ.get("CLOUDCONVERT_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Conversão DWG indisponível: converta o ficheiro em DXF (LibreCAD, AutoCAD «Guardar como → DXF») e volte a importá-lo."
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
            raise RuntimeError("Serviço de conversão DWG saturado — tente novamente dentro de instantes.")
        if not create.is_success:
            logger.error("CloudConvert job creation failed %s: %s", create.status_code, "payload masqué")
            raise RuntimeError("Conversão DWG impossível (criação do job).")

        job = create.json()["data"]
        job_id = job["id"]
        try:
            upload_task = next(t for t in job["tasks"] if t["name"] == "upload-dwg")
            form = upload_task["result"]["form"]
    
            form_data = {str(k): str(v) for k, v in form["parameters"].items()}
            up_name = filename if filename.lower().endswith(".dwg") else "input.dwg"
            files = {"file": (up_name, dwg_bytes, "application/acad")}
            uploaded = await client.post(form["url"], data=form_data, files=files)
            if not uploaded.is_success:
                logger.error("CloudConvert upload failed %s: %s", uploaded.status_code, "payload masqué")
                raise RuntimeError("Conversão DWG impossível (envio do ficheiro).")
    
            waited = await client.get(f"{SYNC_BASE}/jobs/{job_id}", headers=headers)
            if not waited.is_success:
                logger.error("CloudConvert wait failed %s: %s", waited.status_code, "payload masqué")
                raise RuntimeError("Conversão DWG impossível (espera).")
    
            finished = waited.json()["data"]
            if finished.get("status") != "finished":
                errs = [
                    f"{t.get('name')}: {t.get('code') or t.get('message') or t.get('status')}"
                    for t in finished.get("tasks", []) if t.get("status") == "error"
                ]
                logger.error("CloudConvert conversion failed (details withheld)")
                raise RuntimeError("Não foi possível converter o ficheiro DWG (ficheiro danificado ou não suportado).")
    
            export_task = next(t for t in finished["tasks"] if t["name"] == "export-dxf")
            out_files = export_task.get("result", {}).get("files", [])
            if not out_files or not out_files[0].get("url"):
                raise RuntimeError("Conversão DWG impossível (nenhum DXF produzido).")
    
            async with client.stream("GET",out_files[0]["url"]) as download:
                if not download.is_success:raise RuntimeError("Conversão DWG impossível (transferência do DXF).")
                chunks=[];size=0
                async for chunk in download.aiter_bytes():
                    size+=len(chunk)
                    if size>50*1024*1024:raise RuntimeError("DXF convertido demasiado volumoso (>50 MB)")
                    chunks.append(chunk)
                result=b"".join(chunks)
            _validate_dxf(result)
            if provenance is not None: provenance.update(provider="cloudconvert", status="converted")
            return result
        finally:
            try: await client.delete(f"{API_BASE}/jobs/{job_id}",headers=headers)
            except httpx.HTTPError: logger.warning("Nettoyage du job de conversion différé")


def _validate_dxf(data):
    if not data or (b"SECTION" not in data[:4096] and not data.startswith(b"AutoCAD Binary DXF")):
        raise RuntimeError("O conversor não produziu um ficheiro DXF reconhecido")


def _local_dwg_to_dxf(data):
    """ODA installé par l'administrateur ; aucun téléchargement ou shell implicite."""
    import subprocess
    import tempfile
    from pathlib import Path
    executable=Path(os.environ["ODA_FILE_CONVERTER"])
    if not executable.is_absolute() or not executable.is_file():
        raise RuntimeError("Caminho ODA_FILE_CONVERTER inválido no servidor")
    with tempfile.TemporaryDirectory(prefix="cp-cad-") as temp:
        source=Path(temp)/"input";destination=Path(temp)/"output"
        source.mkdir();destination.mkdir();(source/"plan.dwg").write_bytes(data)
        try:
            subprocess.run([str(executable),str(source),str(destination),"ACAD2018","DXF","0","1","plan.dwg"],
                           check=True,timeout=120,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except (OSError,subprocess.SubprocessError):
            raise RuntimeError("Conversão DWG local impossível: verificar o conversor ODA instalado") from None
        outputs=list(destination.glob("*.dxf"))+list(destination.glob("*.DXF"))
        if len(outputs)!=1:raise RuntimeError("O conversor local não produziu um DXF único")
        if outputs[0].stat().st_size>50*1024*1024:raise RuntimeError("DXF convertido demasiado volumoso")
        result=outputs[0].read_bytes();_validate_dxf(result);return result

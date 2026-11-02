"""Dossier demo « Moradia Ferreira » para a conta demo Pro do .pt.

Conteúdo (gerado por scripts/build_demo_ferreira_pt.py, ficheiro data/demo_dossier_pt.json):
  - planta de arquiteto fictícia (R/C, 1/50) importada e calibrada, com os 9 compartimentos medidos;
  - orçamento enviado de 61 940,19 € s/ IVA calculado a partir desse levantamento (catálogo ConstruPilot);
  - 3 clientes, 3 obras, um orçamento em rascunho, um orçamento assinado e a fatura de adiantamento paga.

Regras:
  - Só toca na conta demo Pro (user_id passado pelo chamador, que já verificou is_demo).
  - Arranque: $setOnInsert (não reescreve o que já existe).
  - Reset diário: restore=True repõe os documentos no estado original.
  - Todos os documentos ficam marcados is_demo=True + demo_source.
"""
from __future__ import annotations

import json
import logging
import pathlib

logger = logging.getLogger("demo_dossier_pt")

DATA_FILE = pathlib.Path(__file__).resolve().parents[1] / "data" / "demo_dossier_pt.json"
PLACEHOLDER = "__PRO_UID__"
IDKEY = {"clients": "client_id", "chantiers": "chantier_id",
         "plans_takeoff": "plan_id", "pro_documents": "doc_id"}


def load_dossier(pro_uid: str) -> dict:
    raw = DATA_FILE.read_text(encoding="utf-8").replace(PLACEHOLDER, pro_uid)
    return json.loads(raw).get("pro", {})


async def apply_demo_dossier_pt(db, pro_uid: str | None, demo_source: str, restore: bool = False) -> dict:
    if not pro_uid:
        return {"status": "skipped_no_user"}
    if not DATA_FILE.exists():
        logger.info("demo dossier pt: ficheiro ausente — ignorado")
        return {"status": "skipped_no_file"}
    data = load_dossier(pro_uid)
    counts: dict = {}
    for coll, docs in data.items():
        idkey = IDKEY.get(coll)
        if not idkey:
            continue
        n = 0
        for doc in docs:
            doc = {**doc, "user_id": pro_uid, "is_demo": True, "demo_source": demo_source}
            flt = {idkey: doc[idkey], "user_id": pro_uid}
            if restore:
                await db[coll].replace_one(flt, doc, upsert=True)
                n += 1
            else:
                res = await db[coll].update_one(flt, {"$setOnInsert": doc}, upsert=True)
                if getattr(res, "upserted_id", None) is not None:
                    n += 1
        counts[coll] = n
    logger.info("demo dossier pt aplicado (restore=%s): %s", restore, counts)
    return {"status": "ok", "restore": restore, "written": counts}

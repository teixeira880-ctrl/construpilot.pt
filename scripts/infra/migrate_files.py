"""Copia todos os ficheiros do Emergent Object Storage para um armazenamento S3/R2, sem apagar nada.

A API da Emergent não permite listar ficheiros: a lista é reconstruída a partir das referências guardadas
no MongoDB (qualquer texto que comece por "construpilot/", em qualquer coleção e a qualquer profundidade).

Para cada ficheiro: se já existe no S3 → ignorado (o script pode ser relançado); senão é lido na Emergent,
escrito no S3, relido e comparado por SHA-256. No fim, um relatório JSON lista copiados, já presentes e em falta.

Uso (na VM, dentro do contentor do backend, com EMERGENT_LLM_KEY e as variáveis S3_* definidas):
    docker compose exec backend_pt python /app/scripts_infra/migrate_files.py --report /app/data/files.json
    (ou: python scripts/infra/migrate_files.py a partir de backend/, com PYTHONPATH=backend)
Opções: --dry-run (só lista), --workers 4
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

for _cand in (os.path.join(os.path.dirname(__file__), "..", "..", "backend"), "/app/backend"):   # repo ou contentor
    if os.path.isdir(_cand):
        sys.path.insert(0, os.path.abspath(_cand))
        break

from pymongo import MongoClient  # noqa: E402

from engines import object_storage as obj  # noqa: E402

PREFIX = obj.APP_NAME + "/"


def _walk(value, out: set[str]) -> None:
    if isinstance(value, str):
        if value.startswith(PREFIX) and len(value) < 1024 and "\n" not in value:
            out.add(value)
    elif isinstance(value, dict):
        for v in value.values():
            _walk(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _walk(v, out)


def collect_paths(mongo_url: str, db_name: str) -> dict[str, list[str]]:
    db = MongoClient(mongo_url)[db_name]
    found: dict[str, set[str]] = {}
    for name in sorted(db.list_collection_names()):
        paths: set[str] = set()
        for doc in db[name].find({}, batch_size=200):
            _walk(doc, paths)
        if paths:
            found[name] = paths
    return {k: sorted(v) for k, v in found.items()}


def copy_one(path: str, dry: bool) -> tuple[str, str, int]:
    if obj.s3_exists(path):
        return path, "ja_presente", 0
    if dry:
        return path, "a_copiar", 0
    try:
        data, ctype = obj.emergent_get(path)
    except Exception as exc:  # noqa: BLE001
        return path, f"em_falta_na_emergent: {type(exc).__name__}", 0
    obj.s3_put(path, data, ctype)
    back, _ = obj.s3_get(path)
    if hashlib.sha256(back).hexdigest() != hashlib.sha256(data).hexdigest():
        return path, "ERRO_hash_diferente", len(data)
    return path, "copiado", len(data)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="files_migration_report.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    mongo_url, db_name = os.environ["MONGO_URL"], os.environ["DB_NAME"]
    t0 = time.time()
    by_coll = collect_paths(mongo_url, db_name)
    paths = sorted({p for v in by_coll.values() for p in v})
    print(f"{len(paths)} ficheiros referenciados em {len(by_coll)} coleções")
    results: dict[str, list] = {}
    total_bytes = 0
    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        futs = [ex.submit(copy_one, p, a.dry_run) for p in paths]
        for i, f in enumerate(as_completed(futs), 1):
            path, status, size = f.result()
            results.setdefault(status.split(":")[0], []).append(path if ":" not in status else f"{path} ({status})")
            total_bytes += size
            if i % 50 == 0:
                print(f"  {i}/{len(paths)}")
    summary = {k: len(v) for k, v in results.items()}
    report = {"db": db_name, "segundos": round(time.time() - t0, 1), "bytes_copiados": total_bytes,
              "resumo": summary, "por_colecao": {k: len(v) for k, v in by_coll.items()}, "detalhe": results}
    with open(a.report, "w") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False))
    bad = sum(len(v) for k, v in results.items() if k.startswith(("ERRO", "em_falta")))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

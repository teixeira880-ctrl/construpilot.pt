"""Catálogo do Discovery Engine: carregamento, validação estrutural e vistas.

O ficheiro `catalog.json` é a fonte única; o frontend tem uma cópia byte-a-byte
(`frontend/src/connect/catalog.json`) verificada por teste para funcionar offline no stand.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LANGS = ("pt", "en", "fr")
PUBLIC_STATUSES = ("VERIFICADA", "PARCIAL")
CATALOG_PATH = Path(__file__).with_name("catalog.json")


class CatalogError(ValueError):
    pass


def _check_i18n(obj: dict, where: str) -> None:
    if not isinstance(obj, dict) or any(not str(obj.get(l) or "").strip() for l in LANGS):
        raise CatalogError(f"texto em falta (pt/en/fr) em {where}")


def _check_list_i18n(obj: dict, where: str) -> None:
    if not isinstance(obj, dict) or any(not obj.get(l) for l in LANGS):
        raise CatalogError(f"lista em falta (pt/en/fr) em {where}")
    lens = {len(obj[l]) for l in LANGS}
    if len(lens) != 1:
        raise CatalogError(f"listas com tamanhos diferentes entre idiomas em {where}")


def validate(cat: dict) -> dict:
    caps = {c["id"]: c for c in cat["capabilities"]}
    demos = {d["id"]: d for d in cat["demos"]}
    statuses = set(cat["statuses"])
    for a in cat["activities"]:
        _check_i18n(a["label"], f"activity {a['id']}")
        if a["group"] not in cat["volume_questions"]:
            raise CatalogError(f"grupo sem pergunta de volume: {a['group']}")
    for p in cat["pains"]:
        _check_i18n(p["label"], f"pain {p['id']}")
        _check_i18n(p["summary"], f"pain summary {p['id']}")
        if p["case"] is not None and p["case"] not in cat["deep_questions"]:
            raise CatalogError(f"caso desconhecido {p['case']}")
        for cid in p["capabilities"]:
            if cid not in caps:
                raise CatalogError(f"capacidade desconhecida {cid} em {p['id']}")
    tool_ids = {t["id"] for t in cat["tools"]}
    for case, qs in cat["deep_questions"].items():
        for q in qs:
            _check_i18n(q["label"], f"deep {case}.{q['id']}")
            opts = cat["tools"] if q["options"] == "@tools" else q["options"]
            for o in opts:
                _check_i18n(o["label"], f"option {case}.{q['id']}.{o['id']}")
    for c in caps.values():
        if c["status"] not in statuses:
            raise CatalogError(f"estado inválido {c['status']} em {c['id']}")
        for k in ("name", "description", "inputs", "limitations", "human_checks"):
            _check_i18n(c[k], f"{c['id']}.{k}")
        if not c.get("evidence") or not c.get("validated_at"):
            raise CatalogError(f"evidência/data em falta em {c['id']}")
    for d in demos.values():
        _check_i18n(d["title"], f"demo {d['id']}")
        for cid in d["capabilities"]:
            if cid not in caps:
                raise CatalogError(f"capacidade desconhecida {cid} na demo {d['id']}")
        if d["kind"] == "engine" and not all(caps[c]["status"] in PUBLIC_STATUSES for c in d["capabilities"]):
            raise CatalogError(f"demo {d['id']} usa capacidade não pública")
    for k, v in {**cat["case_demo"], **cat["track_demo"]}.items():
        if v not in demos:
            raise CatalogError(f"demo desconhecida {v} ({k})")
    for k, v in cat["process"]["current"].items():
        if k not in tool_ids:
            raise CatalogError(f"processo atual para ferramenta desconhecida {k}")
        _check_list_i18n(v, f"process.current.{k}")
    for k in ("with", "with_tracking", "with_billing"):
        _check_list_i18n(cat["process"][k], f"process.{k}")
    for k, v in cat["partner"]["use_cases"].items():
        if v not in caps:
            raise CatalogError(f"use case com capacidade desconhecida {v}")
    return cat


@lru_cache(maxsize=1)
def load() -> dict:
    with CATALOG_PATH.open(encoding="utf-8") as fh:
        return validate(json.load(fh))


def caps_by_id() -> dict:
    return {c["id"]: c for c in load()["capabilities"]}


def pains_by_id() -> dict:
    return {p["id"]: p for p in load()["pains"]}


def activities_by_id() -> dict:
    return {a["id"]: a for a in load()["activities"]}


def public_capability(c: dict) -> dict:
    """Vista pública: sem a nota interna de evidência (o estado e a data ficam visíveis)."""
    return {k: v for k, v in c.items() if k != "evidence"}


def question_option_ids(case: str, qid: str) -> set[str] | None:
    cat = load()
    for q in cat["deep_questions"].get(case, []):
        if q["id"] == qid:
            opts = cat["tools"] if q["options"] == "@tools" else q["options"]
            return {o["id"] for o in opts}
    return None


def all_deep_question_ids() -> dict[str, set[str]]:
    """{question_id: option_ids} sobre todos os casos (as perguntas `tools` repetem-se com as mesmas opções)."""
    cat = load()
    out: dict[str, set[str]] = {}
    for case, qs in cat["deep_questions"].items():
        for q in qs:
            opts = cat["tools"] if q["options"] == "@tools" else q["options"]
            out.setdefault(q["id"], set()).update(o["id"] for o in opts)
    return out

"""Pipeline réutilisable : BuildingModel (dict) → contrôles → calculs → plans PDF/DXF → devis → vérificateur → dossier.

Utilisé par l'Assistant (assistant_tool.py) et par la ligne de commande (run.py).
Aucun appel IA ici : tout est déterministe.
"""
from __future__ import annotations

import inspect
import threading
import json
import re
import unicodedata
import zipfile
from datetime import date as _date
from pathlib import Path

from pypdf import PdfReader, PdfWriter

_RENDER_LOCK = threading.Lock()   # brand / i18n sont des états de rendu globaux : un seul rendu à la fois

from . import brand, checks, devis, draw, i18n, mep, model, report, sheets, structure, timber


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return (s[:40] or "Projet")


def _call(fn, *args, lang="fr"):
    """Passe `lang` uniquement si le moteur de rendu le supporte (compatibilité ascendante)."""
    if "lang" in inspect.signature(fn).parameters:
        return fn(*args, lang=lang)
    return fn(*args)


def validate(raw: dict) -> tuple[model.Model | None, list[dict]]:
    """Charge et contrôle le modèle. Retourne (modèle, anomalies) ; modèle None si la structure JSON est inutilisable."""
    try:
        from . import spec as _spec
        _spec.apply_defaults(raw)
        m = model.from_dict(raw)
    except Exception as exc:  # noqa: BLE001 — JSON incomplet : on renvoie l'erreur comme anomalie bloquante
        return None, [{"code": "MODEL-00", "level": checks.BLOCK, "message": f"Modèle bâtiment incomplet : {type(exc).__name__}: {exc}"}]
    try:
        return m, checks.run_all(m)
    except Exception as exc:  # noqa: BLE001
        return m, [{"code": "MODEL-01", "level": checks.BLOCK, "message": f"Contrôle impossible : {type(exc).__name__}: {exc}"}]


def run(raw: dict, out: str | Path, date: str | None = None, lang: str | None = None, stem: str | None = None,
        branding: dict | None = None) -> dict:
    """branding = identité de l'entreprise (company_name, logo_b64, accent_color, contact_line, siret…) ; None = ConstruPilot."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    m, anomalies = validate(raw)
    blocking = [a for a in anomalies if a.get("level") == checks.BLOCK]
    if m is None or blocking:
        return {"status": "MODELE_INVALIDE", "blocking": len(blocking), "anomalies": anomalies, "files": {}}
    country = (raw.get("project") or {}).get("country", "FR")
    lang = lang or ("pt" if country == "PT" else "fr")
    date = date or _date.today().strftime("%d/%m/%Y")
    stem = stem or _slug((raw.get("project") or {}).get("name", "Projet"))

    try:
        r = structure.compute(m)
        tim = timber.compute(m, r["loads"])
        e = mep.electrical(m)
        p = mep.plumbing(m)
        shs = sheets.all_sheets(m, r, tim, e, p)
    except Exception as exc:  # noqa: BLE001 — relevé hors domaine : on rend une question, jamais un dossier faux ni un plantage
        return {"status": "MODELE_INVALIDE", "blocking": 1, "files": {},
                "anomalies": anomalies + [{"code": "CALC-00", "level": checks.BLOCK,
                                           "message": f"Calcul impossible sur ce relevé ({type(exc).__name__}: {str(exc)[:300]})",
                                           "fix": "Vérifier que les documents sont bien le PC d'une maison (plans de niveaux, coupes, façades) et préciser les murs porteurs."}]}
    lines = devis.build_lines(m, r, tim, e, p)
    tot = devis.totals(lines)
    anomalies += checks.check_hypotheses(m, r)
    rev = report.review(m, r, tim, e, p, lines, shs, anomalies)
    m.raw["project"]["date"] = date
    proj = dict(m.raw["project"], date=date)

    with _RENDER_LOCK:
        brand.use(branding, country)
        i18n.KEEP_NORMS[0] = lang == "pt" and country != "PT"     # projet français lu en portugais : normes françaises conservées
        try:
            return _render(m, r, tim, e, p, shs, lines, tot, rev, proj, out, lang, stem, anomalies)
        finally:
            brand.use(None, "FR")
            i18n.KEEP_NORMS[0] = False


def _render(m, r, tim, e, p, shs, lines, tot, rev, proj, out, lang, stem, anomalies):
    names = {"fr": ("Dossier_etude", "Plans_DXF", "Devis_metre"), "pt": ("Processo_estudo", "Desenhos_DXF", "Medicoes_orcamento")}[lang]
    note, plans = out / "_note.pdf", out / "_plans.pdf"
    _call(report.write_note, note, m, r, tim, e, p, tot, rev, shs, lang=lang)
    _call(draw.render_pdf, shs, plans, proj, lang=lang)
    w = PdfWriter()
    for f in (note, plans):
        for pg in PdfReader(str(f)).pages:
            w.add_page(pg)
    pdf = out / f"{names[0]}_{stem}.pdf"
    with open(pdf, "wb") as fh:
        w.write(fh)
    note.unlink()
    plans.unlink()
    files = _call(draw.render_dxf, shs, out / "dxf", lang=lang)
    zp = out / f"{names[1]}_{stem}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.name)
    xlsx = out / f"{names[2]}_{stem}.xlsx"
    _call(devis.write_xlsx, xlsx, m, r, tim, e, p, lines, lang=lang)
    (out / "resultats.json").write_text(json.dumps({"structure": r, "charpente": tim, "electricite": {k: v for k, v in e.items() if k != "levels"},
                                                     "plomberie": p, "devis": tot, "revue": rev}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return {"status": rev["status"], "blocking": rev["blocking"], "lang": lang, "sheets": [s.code + " " + s.title for s in shs],
            "devis_ht": tot["ht"], "devis_ttc": tot["ttc"], "anomalies": [a for a in anomalies if a.get("level") != checks.BLOCK],
            "review": [i for i in rev["items"] if str(i.get("level", "")).upper() != "OK"][:40],
            "files": {"pdf": str(pdf), "zip": str(zp), "xlsx": str(xlsx)}}

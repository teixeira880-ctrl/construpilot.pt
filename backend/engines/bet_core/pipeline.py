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
    """Charge et contrôle le modèle. Retourne (modèle, anomalies) ; modèle None si la structure JSON est inutilisable.
    Étapes avant tout calcul : conformité au schéma typé (schema.py) → défauts → chargement → contrôles de cohérence."""
    from . import schema as _schema
    from . import complete as _complete
    try:
        _complete.complete(raw)                 # nulls / textes / comble fantôme → règles BET tracées dans _decisions
    except Exception:  # noqa: BLE001 — la complétion ne doit jamais masquer l'erreur de schéma d'origine
        pass
    schema_errors = _schema.validate(raw)
    try:
        from . import spec as _spec
        _spec.apply_defaults(raw)
        geo_defaults = _spec.complete_geotech(raw) + _spec.complete_project(raw)
        raw.setdefault("schema_version", _schema.SCHEMA_VERSION)
        m = model.from_dict(raw)
    except Exception as exc:  # noqa: BLE001 — JSON incomplet : on renvoie l'erreur comme anomalie bloquante
        anis = [{"code": "MODEL-00", "level": checks.BLOCK, "message": f"Modèle bâtiment incomplet : {type(exc).__name__}: {exc}"}]
        if schema_errors:
            anis.append({"code": "SCHEMA", "level": checks.BLOCK,
                         "message": "Relevé non conforme au schéma : " + " ; ".join(schema_errors[:6]),
                         "fix": "Respecter le schéma du relevé (types et champs requis)."})
        return None, anis
    anomalies = []
    if geo_defaults:
        anomalies.append({"code": "GEO-HYP", "level": checks.WARN,
                          "message": "Données incomplètes : valeurs prudentes retenues par défaut — " + " ; ".join(geo_defaults[:10]),
                          "fix": "À confirmer ou corriger avec l'étude G2 (joindre la G2 ou préciser ces valeurs dans la demande)."})
    if schema_errors:
        anomalies.append({"code": "SCHEMA", "level": checks.BLOCK,
                          "message": "Relevé non conforme au schéma : " + " ; ".join(schema_errors[:6]),
                          "fix": "Respecter le schéma du relevé (types et champs requis)."})
    try:
        return m, anomalies + checks.run_all(m)
    except Exception as exc:  # noqa: BLE001
        return m, anomalies + [{"code": "MODEL-01", "level": checks.BLOCK, "message": f"Contrôle impossible : {type(exc).__name__}: {exc}"}]


def thermal_first(raw: dict, m, anomalies: list):
    """Étude thermique d'abord : sans étude fournie, le moteur RE2020 dimensionne l'isolation, puis l'épaisseur des murs
    est reportée dans le relevé et le modèle est rechargé. Renvoie (modèle, anomalies, étude | None)."""
    from . import thermal
    if thermal.has_client_study(raw):
        return m, anomalies, None
    try:
        th = thermal.size(m)
        thermal.apply(raw, m, th)
    except Exception as exc:  # noqa: BLE001 — l'étude thermique ne bloque pas la structure : on garde le relevé et on le signale
        return m, anomalies + [{"code": "TH-01", "level": checks.WARN,
                                "message": f"Étude thermique automatique impossible ({type(exc).__name__}: {str(exc)[:200]}) : épaisseurs du PC conservées",
                                "fix": "Joindre l'étude thermique ou préciser l'isolant (ex. « doublage 10+120 »)."}], None
    m2, an2 = validate(raw)
    seen = {(a.get("code"), a.get("message")) for a in an2}
    kept = [a for a in anomalies if a.get("level") != checks.BLOCK and (a.get("code"), a.get("message")) not in seen]
    return m2, kept + an2, th


def thermal_note(th: dict, out: Path, stem: str) -> Path:
    """PDF de la pré-étude RE2020 (même moteur que l'outil etude_re2020 de l'Assistant)."""
    from engines.calc_lots import re2020
    o = re2020.note(dict(th["params"]))
    dst = Path(out) / f"Etude_thermique_RE2020_{stem}.pdf"
    src = o["pdf"]
    if isinstance(src, (bytes, bytearray)):
        dst.write_bytes(src)
    else:
        dst.write_bytes(Path(src).read_bytes())
    return dst


def where(exc: BaseException) -> str:
    """Dernier cadre du moteur ConstruPilot dans la pile (fichier:ligne fonction) — pour diagnostiquer sans les logs serveur."""
    import traceback
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if "bet_core" in (f.filename or "")] or \
        traceback.extract_tb(exc.__traceback__)
    if not frames:
        return ""
    f = frames[-1]
    return f"{Path(f.filename).name}:{f.lineno} {f.name} — {(f.line or '').strip()[:160]}"


def dry_run(m) -> dict | None:
    """Calculs à blanc (sans rendu) : renvoie une anomalie bloquante CALC-00 si le relevé fait planter un moteur.
    Utilisé par la boucle de relecture de l'IA (reader) pour corriger le relevé AVANT de lancer l'étude."""
    try:
        r = structure.compute(m)
        tim = timber.compute(m, r["loads"])
        e = mep.electrical(m)
        p = mep.plumbing(m)
        shs = sheets.all_sheets(m, r, tim, e, p)
        lines = devis.build_lines(m, r, tim, e, p)
        devis.totals(lines)
        hyp = checks.check_hypotheses(m, r)
        report.review(m, r, tim, e, p, lines, shs, hyp)
    except Exception as exc:  # noqa: BLE001
        return {"code": "CALC-00", "level": checks.BLOCK,
                "message": f"Calcul impossible sur ce relevé ({type(exc).__name__}: {str(exc)[:300]} — à {where(exc)})",
                "fix": "Compléter dans le JSON le champ cité (valeur de la G2, des plans ou hypothèse prudente notée dans _decisions)."}
    return None


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
    th = None
    if country == "FR":
        m, anomalies, th = thermal_first(raw, m, anomalies)
        if m is None or any(a.get("level") == checks.BLOCK for a in anomalies):
            return {"status": "MODELE_INVALIDE", "blocking": sum(a.get("level") == checks.BLOCK for a in anomalies), "anomalies": anomalies, "files": {}}

    try:
        r = structure.compute(m)
        tim = timber.compute(m, r["loads"])
        e = mep.electrical(m)
        p = mep.plumbing(m)
        shs = sheets.all_sheets(m, r, tim, e, p)
    except Exception as exc:  # noqa: BLE001 — relevé hors domaine : on rend une question, jamais un dossier faux ni un plantage
        return {"status": "MODELE_INVALIDE", "blocking": 1, "files": {},
                "anomalies": anomalies + [{"code": "CALC-00", "level": checks.BLOCK,
                                           "message": f"Calcul impossible sur ce relevé ({type(exc).__name__}: {str(exc)[:300]} — à {where(exc)})",
                                           "fix": "Vérifier que les documents sont bien le PC d'une maison (plans de niveaux, coupes, façades) et préciser les murs porteurs."}]}
    try:
        lines = devis.build_lines(m, r, tim, e, p)
        tot = devis.totals(lines)
        anomalies += checks.check_hypotheses(m, r)
        rev = report.review(m, r, tim, e, p, lines, shs, anomalies)
    except Exception as exc:  # noqa: BLE001 — même règle : une anomalie lisible, jamais un plantage muet
        return {"status": "MODELE_INVALIDE", "blocking": 1, "files": {},
                "anomalies": anomalies + [{"code": "CALC-01", "level": checks.BLOCK,
                                           "message": f"Devis ou contrôle impossible sur ce relevé ({type(exc).__name__}: {str(exc)[:300]} — à {where(exc)})",
                                           "fix": "Compléter le champ du relevé en cause (voir l'emplacement indiqué)."}]}
    m.raw["project"]["date"] = date
    proj = dict(m.raw["project"], date=date)

    with _RENDER_LOCK:
        brand.use(branding, country)
        i18n.KEEP_NORMS[0] = lang == "pt" and country != "PT"     # projet français lu en portugais : normes françaises conservées
        try:
            res = _render(m, r, tim, e, p, shs, lines, tot, rev, proj, out, lang, stem, anomalies)
            if th is not None:
                try:
                    res["files"]["re2020_pdf"] = str(thermal_note(th, out, stem))
                except Exception as exc:  # noqa: BLE001 — la note thermique ne bloque jamais le dossier
                    res["anomalies"].append({"code": "TH-02", "level": checks.WARN, "message": f"Note RE2020 non produite ({type(exc).__name__}: {str(exc)[:160]})"})
                res["thermal"] = m.raw.get("thermal")
            return res
        except Exception as exc:  # noqa: BLE001 — rendu impossible : anomalie lisible avec l'emplacement, jamais un plantage muet
            return {"status": "MODELE_INVALIDE", "blocking": 1, "files": {},
                    "anomalies": anomalies + [{"code": "CALC-02", "level": checks.BLOCK,
                                               "message": f"Plans ou dossier impossibles à produire ({type(exc).__name__}: {str(exc)[:300]} — à {where(exc)})",
                                               "fix": "Compléter le champ du relevé en cause (voir l'emplacement indiqué)."}]}
        finally:
            brand.use(None, "FR")
            i18n.KEEP_NORMS[0] = False


def _render(m, r, tim, e, p, shs, lines, tot, rev, proj, out, lang, stem, anomalies):
    names = {"fr": ("Dossier_etude", "Plans_DXF", "Devis_metre", "Plans_PDF"),
             "pt": ("Processo_estudo", "Desenhos_DXF", "Medicoes_orcamento", "Desenhos_PDF")}[lang]
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
    plans_pdf = out / f"{names[3]}_{stem}.pdf"          # plans seuls, à imprimer / transmettre aux entreprises
    plans.replace(plans_pdf)
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
            "files": {"pdf": str(pdf), "plans_pdf": str(plans_pdf), "zip": str(zp), "xlsx": str(xlsx)}}


LOT_KINDS = {
    "electricite": ("elec", "elec_panel"),
    "plomberie": ("plumb", "plumb_riser"),
    "ventilation": ("vmc", "vmc_schema"),
    "chauffage": ("pc", "hydro", "pc_detail"),
    "coupes": ("coupe",),
    "gros_oeuvre": ("fond", "level", "floor", "coupe", "facade", "detail", "charpente"),
    "schemas": ("elec_panel", "plumb_riser", "vmc_schema", "hydro", "pc_detail"),
}


def render_lots(raw: dict, lots: list[str], out: str | Path, date: str | None = None, lang: str | None = None,
                branding: dict | None = None) -> dict:
    """Plans d'un ou plusieurs lots (électricité, plomberie, ventilation, chauffage, coupes, schémas…) en un PDF A3,
    depuis le modèle bâtiment d'une étude déjà faite. Rapide (pas de note ni de devis)."""
    out = Path(out)
    m, anomalies = validate(raw)
    blocking = [a for a in anomalies if a.get("level") == checks.BLOCK]
    if m is None or blocking:
        return {"ok": False, "anomalies": blocking or anomalies}
    country = (raw.get("project") or {}).get("country", "FR")
    lang = lang or ("pt" if country == "PT" else "fr")
    date = date or _date.today().strftime("%d/%m/%Y")
    r = structure.compute(m)
    tim = timber.compute(m, r["loads"])
    e, p = mep.electrical(m), mep.plumbing(m)
    shs = sheets.all_sheets(m, r, tim, e, p)
    kinds = {k for lot in lots for k in LOT_KINDS.get(lot, ())}
    sel = [s for s in shs if getattr(s, "kind", "") in kinds]
    if not sel:
        return {"ok": False, "anomalies": [{"message": "Aucune planche pour ces lots sur ce projet."}]}
    proj = dict(m.raw["project"], date=date)
    with _RENDER_LOCK:
        brand.use(branding, country)
        try:
            _call(draw.render_pdf, sel, out, proj, lang=lang)
        finally:
            brand.use(None, "FR")
    return {"ok": True, "path": str(out), "sheets": [s.code + " " + s.title for s in sel]}

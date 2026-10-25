"""FrameModel (dict) → contrôles → calculs → planches PDF/DXF → note → devis → dossier. Déterministe (aucun appel IA)."""
from __future__ import annotations

import json
import threading
import zipfile
from datetime import date as _date
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from engines.bet_core import brand, draw, i18n
from engines.bet_core.pipeline import _RENDER_LOCK, _slug, where

from . import calc, devis, mep, model, report, sheets
from .lang import _, use_lang

_LOCK = threading.Lock()


def is_frame(raw: dict | None) -> bool:
    return bool(raw) and raw.get("kind") == "frame"


def validate(raw: dict) -> tuple[model.Frame | None, list[dict]]:
    try:
        m = model.from_dict(raw)
    except Exception as exc:  # noqa: BLE001
        return None, [{"code": "MODEL-00", "level": model.BLOCK,
                       "message": _(f"Relevé incomplet : {type(exc).__name__}: {exc}", f"Levantamento incompleto: {type(exc).__name__}: {exc}"),
                       "fix": _("Compléter la trame, les niveaux et la structure.", "Completar a trama, os pisos e a estrutura.")}]
    try:
        return m, model.check(m)
    except Exception as exc:  # noqa: BLE001
        return m, [{"code": "MODEL-01", "level": model.BLOCK, "message": f"{type(exc).__name__}: {exc}"}]


def dry_run(raw: dict, lang: str = "fr") -> dict | None:
    with use_lang(lang):
        m, an = validate(raw)
        if m is None or model.has_block(an):
            return None
        try:
            r = calc.compute(m)
            e = mep.compute(m)
            sheets.all_sheets(m, r, e)
        except Exception as exc:  # noqa: BLE001
            return {"code": "CALC-00", "level": model.BLOCK, "message": f"{type(exc).__name__}: {str(exc)[:300]} — {where(exc)}"}
    return None


def _render_pdf(shs, path, proj, lang):
    """Rendu avec les textes de la planche déclarés « natifs » (déjà dans la langue) le temps du rendu."""
    add = sheets.NAT - i18n.NATIVE
    i18n.NATIVE.update(add)
    from engines.bet_core.i18n_pt import TEMPLATES
    extra = {k: v for k, v in (("LÉGENDE", "LEGENDA"),) if k not in TEMPLATES}
    TEMPLATES.update(extra)
    try:
        draw.render_pdf(shs, path, proj, lang=lang)
        return draw.render_dxf(shs, Path(path).parent / "dxf", lang=lang)
    finally:
        i18n.NATIVE.difference_update(add)
        for k in extra:
            TEMPLATES.pop(k, None)


def run(raw: dict, out: str | Path, date: str | None = None, lang: str | None = None, stem: str | None = None,
        branding: dict | None = None, lots: list[str] | None = None) -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    country = (raw.get("project") or {}).get("country", "FR")
    lang = lang or ("pt" if country == "PT" else "fr")
    date = date or _date.today().strftime("%d/%m/%Y")
    stem = stem or _slug((raw.get("project") or {}).get("name", "Projet"))
    with _LOCK, use_lang(lang):
        m, anomalies = validate(raw)
        if m is None or model.has_block(anomalies):
            return {"status": "MODELE_INVALIDE", "blocking": sum(a.get("level") == model.BLOCK for a in anomalies), "anomalies": anomalies, "files": {}}
        try:
            r = calc.compute(m)
            e = mep.compute(m)
            shs = sheets.all_sheets(m, r, e)
            lines = devis.build_lines(m, r, e)
            tot = devis.totals(lines, m.country)
            rev = report.review(m, r, e, anomalies)
        except Exception as exc:  # noqa: BLE001 — jamais de plantage muet : une anomalie lisible
            return {"status": "MODELE_INVALIDE", "blocking": 1, "files": {},
                    "anomalies": anomalies + [{"code": "CALC-00", "level": model.BLOCK,
                                               "message": _(f"Calcul impossible ({type(exc).__name__}: {str(exc)[:300]} — à {where(exc)})",
                                                            f"Cálculo impossível ({type(exc).__name__}: {str(exc)[:300]} — em {where(exc)})"),
                                               "fix": _("Vérifier la trame, les niveaux et les sections relevés.", "Verificar a trama, os pisos e as secções relevadas.")}]}
        proj = dict(m.project, date=date)
        if lots:
            kinds = {k for lot in lots for k in LOT_KINDS.get(lot, ())}
            shs = [s for s in shs if getattr(s, "kind", "") in kinds]
            if not shs:
                return {"ok": False, "anomalies": [{"message": _("Aucune planche pour ces lots sur ce projet.", "Nenhum desenho para estas especialidades neste projeto.")}]}
        names = {"fr": ("Dossier_etude", "Plans_DXF", "Devis_metre", "Plans_PDF"), "pt": ("Processo_estudo", "Desenhos_DXF", "Medicoes_orcamento", "Desenhos_PDF")}[lang]
        with _RENDER_LOCK:
            brand.use(branding, country)
            try:
                plans_pdf = out / f"{names[3]}_{stem}.pdf"
                dxf = _render_pdf(shs, plans_pdf, proj, lang)
                if lots:
                    return {"ok": True, "path": str(plans_pdf), "sheets": [s.code + " " + s.title for s in shs]}
                note = out / "_note.pdf"
                report.write_note(note, m, r, e, tot, rev, shs)
            finally:
                brand.use(None, "FR")
        w = PdfWriter()
        for f in (note, plans_pdf):
            for pg in PdfReader(str(f)).pages:
                w.add_page(pg)
        pdf = out / f"{names[0]}_{stem}.pdf"
        with open(pdf, "wb") as fh:
            w.write(fh)
        note.unlink()
        zp = out / f"{names[1]}_{stem}.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for f in dxf:
                z.write(f, f.name)
        xlsx = out / f"{names[2]}_{stem}.xlsx"
        devis.write_xlsx(xlsx, m, lines)
        (out / "resultats.json").write_text(json.dumps({"decisions": r["decisions"], "review": rev, "devis": tot,
                                                        "columns": [{k: c[k] for k in ("name", "b", "h")} for c in r["columns"]]},
                                                       ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        return {"status": rev["status"], "blocking": rev["blocking"], "lang": lang, "kind": "frame",
                "sheets": [s.code + " " + s.title for s in shs], "devis_ht": tot["ht"], "devis_ttc": tot["ttc"],
                "decisions": r["decisions"], "anomalies": [a for a in anomalies + r["issues"] if a.get("level") != model.BLOCK],
                "review": [i for i in rev["items"] if str(i.get("level", "")).upper() != "OK"][:40],
                "files": {"pdf": str(pdf), "plans_pdf": str(plans_pdf), "zip": str(zp), "xlsx": str(xlsx)}}


LOT_KINDS = {
    "plomberie": ("plumb", "plumb_riser"), "electricite": ("plumb_riser", "table"), "coupes": ("coupe",),
    "gros_oeuvre": ("fond", "floor", "coupe", "table"), "schemas": ("plumb_riser",), "ventilation": ("plumb_riser",),
    "chauffage": ("plumb_riser",),
}


def render_lots(raw: dict, lots: list[str], out_pdf: str | Path, date: str | None = None, lang: str | None = None, branding: dict | None = None) -> dict:
    """Planches d'un ou plusieurs lots depuis le relevé d'une étude ossature déjà faite (rapide, sans note ni devis)."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        res = run(raw, tmp, date, lang, None, branding, lots=lots)
        if not res.get("ok"):
            return res
        Path(out_pdf).write_bytes(Path(res["path"]).read_bytes())
        return {"ok": True, "path": str(out_pdf), "sheets": res["sheets"]}

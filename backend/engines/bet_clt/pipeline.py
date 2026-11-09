"""Relevé (FrameModel JSON, structure.system = post_beam | walls) → contrôles → calcul bois massif → planches PDF/DXF →
note de calcul → devis Excel → dossier. Déterministe, sans appel IA. Une étude peut sortir en plusieurs langues
(ex. compte ukrainien : ["en", "uk"]) : chaque langue a ses propres fichiers, calculs identiques."""
from __future__ import annotations

import json
import threading
import zipfile
from datetime import date as _date
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from engines.bet_core import brand, draw
from engines.bet_core.pipeline import _RENDER_LOCK, _slug
from engines.bet_frame import model

from . import calc, devis, report, sheets
from .lang import LANGS, pick_lang, t, use_lang

_LOCK = threading.Lock()
_KEEP = {"GRID-01", "GRID-02", "GRID-03", "LEV-01", "LEV-02", "LEV-03", "CORE-01", "VOID-01"}

CART = {
    "Planche": ("Planche", "Desenho", "Sheet", "Аркуш"), "Échelle": ("Échelle", "Escala", "Scale", "Масштаб"),
    "Indice / date": ("Indice / date", "Revisão / data", "Revision / date", "Ревізія / дата"), "NOTES": ("NOTES", "NOTAS", "NOTES", "ПРИМІТКИ"),
    "PRÉ-DIMENSIONNEMENT — À VISER ET SIGNER PAR UN": ("PRÉ-DIMENSIONNEMENT — À VISER ET SIGNER PAR UN", "PRÉ-DIMENSIONAMENTO — A VERIFICAR E ASSINAR POR",
                                                      "PRELIMINARY DESIGN — TO BE CHECKED AND SIGNED BY A", "ПОПЕРЕДНІЙ РОЗРАХУНОК — ПЕРЕВІРЯЄ І ПІДПИСУЄ"),
    "INGÉNIEUR STRUCTURE AVANT EXÉCUTION": ("INGÉNIEUR STRUCTURE AVANT EXÉCUTION", "ENGENHEIRO DE ESTRUTURAS ANTES DA EXECUÇÃO",
                                            "STRUCTURAL ENGINEER BEFORE CONSTRUCTION", "ІНЖЕНЕР-КОНСТРУКТОР ДО ПОЧАТКУ РОБІТ"),
    "Bureau d'études intégré": ("Bureau d'études intégré", "Gabinete de engenharia integrado", "Integrated engineering office", "Інтегроване проєктне бюро"),
    "étude ConstruPilot": ("étude ConstruPilot", "estudo ConstruPilot", "ConstruPilot study", "розрахунок ConstruPilot"),
    "LÉGENDE": ("LÉGENDE", "LEGENDA", "LEGEND", "ЛЕГЕНДА"),
}
_IDX = {"fr": 0, "pt": 1, "en": 2, "uk": 3}


def _T(lang):
    def f(s):
        n = getattr(s, "n", 0)
        v = CART.get(str(s))
        out = v[_IDX[lang]] if v else str(s)
        return out[:n] if n else out
    return f


class _render_ctx:
    """Rendu des planches : textes déjà rédigés dans la langue (aucune retraduction) ; police de titre cyrillique en UK."""

    def __init__(self, lang):
        self.lang = lang

    def __enter__(self):
        self.T = draw.T
        draw.T = _T(self.lang)
        if self.lang == "uk":
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            pdfmetrics.registerFont(TTFont("TT", str(brand.FONTS / "Inter_700Bold.ttf")))
            pdfmetrics.registerFont(TTFont("TTS", str(brand.FONTS / "Inter_600SemiBold.ttf")))
        return self

    def __exit__(self, *a):
        draw.T = self.T
        if self.lang == "uk":
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            pdfmetrics.registerFont(TTFont("TT", str(brand.FONTS / "BarlowSemiCondensed_700Bold.ttf")))
            pdfmetrics.registerFont(TTFont("TTS", str(brand.FONTS / "BarlowSemiCondensed_600SemiBold.ttf")))


def validate(raw: dict) -> tuple[model.Frame | None, list[dict]]:
    try:
        m = model.from_dict(raw)
    except Exception as exc:  # noqa: BLE001
        return None, [{"code": "MODEL-00", "level": model.BLOCK, "message": t(f"Relevé incomplet : {type(exc).__name__}: {exc}",
                                                                            f"Levantamento incompleto: {type(exc).__name__}: {exc}",
                                                                            f"Incomplete survey: {type(exc).__name__}: {exc}",
                                                                            f"Неповні вихідні дані: {type(exc).__name__}: {exc}")}]
    out = []
    try:
        for a in model.check(m):
            if a["code"] in _KEEP or (a["code"] == "COL-01" and calc.system(m) == "post_beam"):
                out.append(a)
    except Exception as exc:  # noqa: BLE001
        out.append({"code": "MODEL-01", "level": model.BLOCK, "message": f"{type(exc).__name__}: {exc}"})
    if m.country not in ("FR", "PT", "UA"):
        out.append({"code": "CTRY", "level": model.WARN, "message": t(f"Pays {m.country} : valeurs FR appliquées (Eurocodes).",
                                                                    f"País {m.country}: valores FR aplicados (Eurocódigos).",
                                                                    f"Country {m.country}: French (Eurocode) values applied.",
                                                                    f"Країна {m.country}: застосовано значення Єврокодів (FR).")})
    return m, out


def _one(raw: dict, out: Path, date: str, lang: str, stem: str, branding: dict | None) -> dict:
    with use_lang(lang):
        m, anomalies = validate(raw)
        if m is None or model.has_block(anomalies):
            return {"status": "MODELE_INVALIDE", "blocking": sum(a.get("level") == model.BLOCK for a in anomalies), "anomalies": anomalies, "files": {}}
        try:
            r = calc.compute(m)
            shs = sheets.all_sheets(m, r)
            lines = devis.build_lines(m, r)
            tot = devis.totals(lines, r["country"])
            rev = report.review(m, r, anomalies)
        except Exception as exc:  # noqa: BLE001 — jamais de plantage muet
            import traceback
            fr = traceback.extract_tb(exc.__traceback__)[-1]
            return {"status": "MODELE_INVALIDE", "blocking": 1, "files": {},
                    "anomalies": anomalies + [{"code": "CALC-00", "level": model.BLOCK,
                                               "message": t("Calcul impossible", "Cálculo impossível", "Calculation failed", "Розрахунок неможливий")
                                               + f" ({type(exc).__name__}: {str(exc)[:240]} — {Path(fr.filename).name}:{fr.lineno})"}]}
        proj = dict(m.project, date=date)
        names = {"fr": ("Dossier_CLT", "Plans_DXF", "Devis_CLT", "Plans_CLT"), "pt": ("Processo_CLT", "Desenhos_DXF", "Orcamento_CLT", "Desenhos_CLT"),
                 "en": ("CLT_Study", "Drawings_DXF", "CLT_Estimate", "CLT_Drawings"), "uk": ("CLT_Rozrakhunok_UK", "Kreslennia_DXF_UK", "Koshtorys_CLT_UK", "Kreslennia_CLT_UK")}[lang]
        sfx = "" if lang in ("fr", "pt") else f"_{lang.upper()}"
        with _RENDER_LOCK:
            brand.use(branding, m.country if m.country in ("FR", "PT") else "FR")
            try:
                plans_pdf = out / f"{names[3]}_{stem}{sfx}.pdf"
                with _render_ctx(lang):
                    draw.render_pdf(shs, plans_pdf, proj, lang=lang)
                    dxf = draw.render_dxf([s for s in shs if getattr(s, "dxf", True) is not False], out / f"dxf_{lang}", lang=lang)
                note = out / f"_note_{lang}.pdf"
                report.write_note(note, m, r, tot, rev, shs)
            finally:
                brand.use(None, "FR")
        w = PdfWriter()
        for f in (note, plans_pdf):
            for pg in PdfReader(str(f)).pages:
                w.add_page(pg)
        pdf = out / f"{names[0]}_{stem}{sfx}.pdf"
        with open(pdf, "wb") as fh:
            w.write(fh)
        note.unlink()
        zp = out / f"{names[1]}_{stem}{sfx}.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for f in dxf:
                z.write(f, f.name)
        xlsx = out / f"{names[2]}_{stem}{sfx}.xlsx"
        devis.write_xlsx(xlsx, m, lines, r["country"])
        summary = {"system": r["system"], "scheme": {k: v for k, v in r["scheme"].items() if k != "cands"}, "R": r["R"],
                   "floors": [{"name": f["name"], "clt": f["clt"]["name"], "u": f["clt"]["u_max"], "gov": f["clt"]["governing"], "panels": len(f["panels"]),
                               "beams": len(f["beams"])} for f in r["floors"]],
                   "columns": [{"name": c["name"], "segs": [(s["level"], s["b"], s["h"], s["grade"], s["NEd"]) for s in c["segs"]]} for c in r["columns"]],
                   "walls": [{"id": w_["id"], "segs": [(s["level"], s["layup"], s["u"]) for s in w_["segs"]]} for w_ in r["walls"]],
                   "quantities": r["quantities"], "devis": tot, "review": rev}
        (out / f"resultats_{lang}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        return {"status": rev["status"], "blocking": rev["blocking"], "lang": lang, "kind": "clt", "sheets": [s.code + " " + s.title for s in shs],
                "devis_ht": tot["ht"], "devis_ttc": tot["ttc"], "decisions": r["decisions"],
                "anomalies": [a for a in anomalies + r["issues"] if a.get("level") != model.BLOCK],
                "review": [i for i in rev["items"] if str(i.get("level", "")).upper() != "OK"][:40], "summary": summary,
                "files": {"pdf": str(pdf), "plans_pdf": str(plans_pdf), "zip": str(zp), "xlsx": str(xlsx)}}


def run(raw: dict, out: str | Path, date: str | None = None, lang: str | None = None, stem: str | None = None,
        branding: dict | None = None, langs: list[str] | None = None) -> dict:
    """Étude complète. `langs` : plusieurs langues de livrables (la première est la principale)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    country = ((raw.get("project") or {}).get("country") or "FR").upper()
    main = pick_lang(country, lang)
    todo = [main] + [x for x in (langs or []) if x in LANGS and x != main]
    date = date or _date.today().strftime("%d/%m/%Y")
    stem = stem or _slug((raw.get("project") or {}).get("name", "Projet"))
    res = None
    extra = {}
    with _LOCK:
        for lg in todo:
            r_ = _one(json.loads(json.dumps(raw)), out, date, lg, stem, branding)
            if res is None:
                res = r_
                if r_["status"] == "MODELE_INVALIDE":
                    return r_
            else:
                for k, v in (r_.get("files") or {}).items():
                    extra[f"{k}_{lg}"] = v
    res["files"].update(extra)
    res["langs"] = todo
    return res

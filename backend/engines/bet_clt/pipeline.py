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
        self.saved = {}
        if self.lang == "uk":                      # Barlow n'a pas de cyrillique : titres en Inter le temps du rendu
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            for alias, src, fname in (("TTU", "TT", "Inter_700Bold.ttf"), ("TTSU", "TTS", "Inter_600SemiBold.ttf")):
                try:
                    pdfmetrics.getFont(alias)
                except KeyError:
                    pdfmetrics.registerFont(TTFont(alias, str(brand.FONTS / fname)))
                self.saved[src] = pdfmetrics._fonts[src]
                pdfmetrics._fonts[src] = pdfmetrics.getFont(alias)
        return self

    def __exit__(self, *a):
        draw.T = self.T
        if self.saved:
            from reportlab.pdfbase import pdfmetrics
            pdfmetrics._fonts.update(self.saved)


def normalize(raw: dict) -> list[str]:
    """Complète un relevé incomplet de façon traçable (niveaux sans hauteur / cote, identifiants manquants)."""
    notes = []
    need = {"units": ("x0", "y0", "x1", "y1"), "cores": ("x0", "y0", "x1", "y1"), "risers": ("x", "y"), "balconies": ("side",)}
    for key, fields in need.items():                 # éléments secondaires sans coordonnées : écartés (inutiles au calcul CLT)
        items = raw.get(key)
        if isinstance(items, list):
            ok = [x for x in items if isinstance(x, dict) and all(x.get(f) not in (None, "") for f in fields)]
            if len(ok) != len(items):
                notes.append(t(f"{len(items) - len(ok)} élément(s) « {key} » sans coordonnées écarté(s).",
                               f"{len(items) - len(ok)} elemento(s) « {key} » sem coordenadas ignorado(s).",
                               f"{len(items) - len(ok)} « {key} » item(s) without coordinates ignored.",
                               f"{len(items) - len(ok)} елемент(ів) « {key} » без координат пропущено."))
            raw[key] = ok
    st = raw.get("structure") if isinstance(raw.get("structure"), dict) else {}
    for k in ("beam", "column"):                     # sections BA du relevé : sans objet en bois massif, gardées seulement si valides
        v = st.get(k)
        if v is not None and not (isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)):
            st.pop(k, None)
    if "columns_omit" in st:
        st["columns_omit"] = [x for x in (st.get("columns_omit") or []) if isinstance(x, (list, tuple)) and len(x) == 2]
    if "void_cells" in st:
        st["void_cells"] = [x for x in (st.get("void_cells") or []) if isinstance(x, (list, tuple)) and len(x) == 2]
    if isinstance(st.get("column_sections"), dict):
        st["column_sections"] = {k: v for k, v in st["column_sections"].items() if isinstance(v, (list, tuple)) and len(v) == 2}
    for slab_key in ("slab",):
        if slab_key in st and not isinstance(st[slab_key], (int, float)):
            st.pop(slab_key, None)
    g = raw.get("grid") if isinstance(raw.get("grid"), dict) else {}
    for ax, labk in (("x", "x_labels"), ("y", "y_labels")):
        vals = g.get(ax)
        if isinstance(vals, list):
            g[ax] = sorted({round(float(v), 4) for v in vals if isinstance(v, (int, float)) or str(v).replace(".", "", 1).lstrip("-").isdigit()})
            if len(g.get(labk) or []) != len(g[ax]):
                g.pop(labk, None)
    lv = [d for d in (raw.get("levels") or []) if isinstance(d, dict)]
    for d in lv:
        if not isinstance(d.get("void_cells", []), list):
            d["void_cells"] = []
        d["void_cells"] = [x for x in (d.get("void_cells") or []) if isinstance(x, (list, tuple)) and len(x) == 2]
    if not lv:
        return notes
    if lv[0].get("floor_top") in (None, ""):
        lv[0]["floor_top"] = 0.0
    for k, d in enumerate(lv):
        d.setdefault("id", f"N{k}")
        d.setdefault("name", str(d["id"]))
        if not d.get("use"):
            d["use"] = "habitation"
        if d.get("floor_top") in (None, "") and k > 0:
            prev = lv[k - 1]
            d["floor_top"] = round(float(prev["floor_top"]) + float(prev.get("height") or 2.8), 3)
    for k, d in enumerate(lv):
        if d.get("height") in (None, "", 0):
            nxt = next((x for x in lv[k + 1:] if x.get("floor_top") not in (None, "")), None)
            h = float(nxt["floor_top"]) - float(d["floor_top"]) if nxt else float((raw.get("roof") or {}).get("storey_height") or 2.8)
            d["height"] = round(h if 2.2 <= h <= 9.0 else 2.8, 3)
            notes.append(t(f"Hauteur d'étage de {d['name']} non relevée : {d['height']} m retenus.",
                           f"Pé-direito de {d['name']} não relevado: {d['height']} m admitidos.",
                           f"Storey height of {d['name']} not read: {d['height']} m assumed.",
                           f"Висоту поверху {d['name']} не зчитано: прийнято {d['height']} м."))
    raw["levels"] = lv
    return notes


def validate(raw: dict) -> tuple[model.Frame | None, list[dict]]:
    try:
        fixes = normalize(raw)
    except Exception:  # noqa: BLE001
        fixes = []
    try:
        m = model.from_dict(raw)
    except Exception as exc:  # noqa: BLE001
        return None, [{"code": "MODEL-00", "level": model.BLOCK, "message": t(f"Relevé incomplet : {type(exc).__name__}: {exc}",
                                                                            f"Levantamento incompleto: {type(exc).__name__}: {exc}",
                                                                            f"Incomplete survey: {type(exc).__name__}: {exc}",
                                                                            f"Неповні вихідні дані: {type(exc).__name__}: {exc}")}]
    out = [{"code": "MODEL-FIX", "level": model.WARN, "message": f} for f in fixes]
    try:
        for a in model.check(m):
            if a["code"] in _KEEP or (a["code"] == "COL-01" and calc.system(m) == "post_beam"):
                out.append(a)
    except Exception as exc:  # noqa: BLE001 — contrôles génériques du relevé BA : jamais bloquants pour le bois massif
        out.append({"code": "MODEL-01", "level": model.WARN, "message": f"{type(exc).__name__}: {exc}"})
    if len(m.gx) < 2 or len(m.gy) < 2:
        out.append({"code": "GRID-01", "level": model.BLOCK, "message": t("Trame incomplète : au moins 2 files dans chaque sens.",
                                                                        "Trama incompleta: pelo menos 2 alinhamentos em cada direção.",
                                                                        "Incomplete grid: at least 2 gridlines in each direction.",
                                                                        "Неповна сітка осей: щонайменше 2 осі в кожному напрямку.")})
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
            try:
                from . import thermal
                house = str(m.raw.get("building_type", "")).lower() in ("maison", "moradia", "house", "maison_individuelle")
                r["thermal"] = thermal.compute(m) if (house or m.raw.get("envelope")) else None     # moradia / maison individuelle
            except Exception as exc:  # noqa: BLE001 — l'étude thermique complète le dossier, son échec est signalé, pas bloquant
                r["thermal"] = None
                r["issues"].append({"code": "TH-00", "level": model.WARN, "message": t("Étude thermique non produite", "Estudo térmico não produzido",
                                                                                      "Thermal study not produced", "Теплотехнічний розрахунок не виконано")
                                    + f" ({type(exc).__name__}: {str(exc)[:160]})"})
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
        est_files = {}
        if str((m.raw.get("estimate") or {}).get("market") or "").upper() == "UA":       # devis final aux prix ukrainiens (грн + €)
            from . import estimate
            est = estimate.build(m, r, r.get("thermal"))
            en = {"fr": "Devis_final_UA", "pt": "Orcamento_final_UA", "en": "Final_Estimate_UA", "uk": "Koshtorys_final_UA"}[lang]
            with _RENDER_LOCK:
                brand.use(branding, m.country if m.country in ("FR", "PT") else "FR")
                try:
                    est_files["estimate_pdf"] = str(estimate.write_pdf(out / f"{en}_{stem}{sfx}.pdf", m, est))
                finally:
                    brand.use(None, "FR")
            est_files["estimate_xlsx"] = str(estimate.write_xlsx(out / f"{en}_{stem}{sfx}.xlsx", m, est))
            tot = dict(tot, ua_ht_uah=est["ht"], ua_ttc_uah=est["ttc"], ua_ht_eur=round(est["ht"] / est["eur"], 2), ua_per_m2=est["per_m2"])
        summary = {"system": r["system"], "scheme": {k: v for k, v in r["scheme"].items() if k != "cands"}, "R": r["R"],
                   "floors": [{"name": f["name"], "clt": f["clt"]["name"], "u": f["clt"]["u_max"], "gov": f["clt"]["governing"], "panels": len(f["panels"]),
                               "beams": len(f["beams"])} for f in r["floors"]],
                   "columns": [{"name": c["name"], "segs": [(s["level"], s["b"], s["h"], s["grade"], s["NEd"]) for s in c["segs"]]} for c in r["columns"]],
                   "walls": [{"id": w_["id"], "segs": [(s["level"], s["layup"], s["u"]) for s in w_["segs"]]} for w_ in r["walls"]],
                   "quantities": r["quantities"], "devis": tot, "review": rev,
                   "thermal": _th_summary(r.get("thermal"))}
        (out / f"resultats_{lang}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        return {"status": rev["status"], "blocking": rev["blocking"], "lang": lang, "kind": "clt", "sheets": [s.code + " " + s.title for s in shs],
                "devis_ht": tot["ht"], "devis_ttc": tot["ttc"], "decisions": r["decisions"],
                "anomalies": [a for a in anomalies + r["issues"] if a.get("level") != model.BLOCK],
                "review": [i for i in rev["items"] if str(i.get("level", "")).upper() != "OK"][:40], "summary": summary,
                "files": {"pdf": str(pdf), "plans_pdf": str(plans_pdf), "zip": str(zp), "xlsx": str(xlsx), **est_files}}


def _th_summary(th: dict | None) -> dict | None:
    if not th:
        return None
    out = {"U": {k: v["U"] for k, v in th["solutions"].items()}, "Ap": th["Ap"], "phi_kw": round(th["phi_w"] / 1000, 2), "ok": th["ok"], "fails": th["fails"]}
    if th.get("reh"):
        out.update({k: th["reh"][k] for k in ("Nic", "Ni", "Nvc", "Nv", "Ntc", "Nt", "RNt", "classe")})
    if th.get("re2020") and "error" not in th["re2020"]:
        out.update({k: th["re2020"][k] for k in ("Bbio", "Cep", "Cep_nr", "DH", "Ic_energie", "Ic_construction", "conforme")})
    return out


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

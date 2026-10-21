"""Conjunto de avaliação — importa os planos autorizados, corre o motor determinístico e escreve um relatório de leitura por plano.

Uso (a partir de /app/backend):
  python3 scripts/run_eval_set.py --upload            # importa os ficheiros de tests/fixtures/eval/plans (DWG = 1 tarefa Autodesk real)
  python3 scripts/run_eval_set.py --analyze           # leitura nativa (identidade, nomenclaturas, cadeias) — sem custo IA
  python3 scripts/run_eval_set.py --vision            # leitura visual das páginas sem texto nativo (1 chamada IA por página)
Saída: /app/test_reports/eval/<plano>.json, RELATORIO_LEITURA.md e <plano>.truth.json (esboço a validar).
"""
import argparse
import asyncio
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import httpx  # noqa: E402
import pymupdf  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from engines.eval_harness import evaluate_plan, summary  # noqa: E402
from engines.metre.altimetry_dxf import altimetry_labels  # noqa: E402
from engines.metre.coffrage_dxf import coffrage_takeoff  # noqa: E402
from engines.metre.heights import volumes_from_takeoff  # noqa: E402
from engines.metre.level_symbols import levels_from_symbols, parse_level_symbols, words_from_pdf_page  # noqa: E402
from engines.metre.steel_ratio import pair_beams, ratio_lines  # noqa: E402
from engines.metre.treillis_labels import panel_labels  # noqa: E402
from engines.metre.nappes_cross import cross_nappes  # noqa: E402
from engines.metre.oblique_dims import match_labels  # noqa: E402
from engines.metre.rebar_schedule import extract_rebar_schedule  # noqa: E402
from engines.plan_sources import load_cad_source  # noqa: E402
from engines.plan_vector_pdf import pt_per_m_from_scale  # noqa: E402
from engines.metre.rebar_vision import analyze_pdf, is_vision_needed  # noqa: E402
from engines.native_chains import native_chains_for_page  # noqa: E402
from engines.plan_identity import identify_document  # noqa: E402
from engines.plan_sources import load_plan_source  # noqa: E402

PLANS_DIR = Path("/app/tests/fixtures/eval/plans")
TRUTH_DIR = Path("/app/tests/fixtures/eval")
OUT_DIR = Path("/app/test_reports/eval")
REGISTRY = PLANS_DIR / "registry.json"
UPLOAD_NAMES = {"RDC.bak": "RDC.dwg"}


def _registry() -> dict:
    return json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}


async def _login(client: httpx.AsyncClient) -> str:
    email, password = os.environ["TEST_ADMIN_EMAIL"], os.environ["TEST_ADMIN_PASSWORD"]
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["token"]


async def upload_all(base_url: str) -> dict:
    reg = _registry()
    async with httpx.AsyncClient(base_url=base_url, timeout=600) as client:
        token = await _login(client)
        for path in sorted(PLANS_DIR.iterdir()):
            if path.name in ("registry.json",) or path.name in reg:
                continue
            upload_name = UPLOAD_NAMES.get(path.name, path.name)
            mime = "application/pdf" if upload_name.endswith(".pdf") else "application/octet-stream"
            r = await client.post("/api/takeoffs/upload", files={"file": (upload_name, path.read_bytes(), mime)},
                                  headers={"Authorization": f"Bearer {token}"})
            if r.status_code >= 400:
                print(f"[upload] {path.name}: HTTP {r.status_code} {r.text[:300]}")
                continue
            data = r.json()
            reg[path.name] = {"plan_id": data["plan_id"], "page_count": data.get("page_count"), "kind": "dwg" if upload_name.endswith(".dwg") else "pdf",
                              "uploaded_at": datetime.now(timezone.utc).isoformat(), "cad_import": bool(data.get("cad_import"))}
            print(f"[upload] {path.name} → {data['plan_id']} ({data.get('page_count')} page(s))")
            REGISTRY.write_text(json.dumps(reg, indent=1, ensure_ascii=False))
    return reg


async def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _merge_vision(prev: dict | None, new: dict) -> dict:
    if not prev:
        return new
    from engines.metre.rebar_vision import summarize
    by_page = {s["page"]: s for s in prev["sheets"]}
    by_page.update({s["page"]: s for s in new["sheets"]})
    sheets = [by_page[k] for k in sorted(by_page)]
    return {**prev, "pages": len(sheets), "sheets": sheets, "summary": summarize(sheets)}


async def analyze(name: str, entry: dict, db, *, user_id: str, vision: bool, pages: list[int] | None = None) -> dict:
    plan_id = entry["plan_id"]
    plan = await db.plans_takeoff.find_one({"plan_id": plan_id}, {"_id": 0, "pages.image_png_b64": 0, "pages.vectors": 0})
    src = await load_plan_source(db, plan_id, user_id)
    pdf = base64.b64decode(src["data_b64"]) if src else None
    out = {"name": name, "plan_id": plan_id, "kind": entry["kind"], "analyzed_at": datetime.now(timezone.utc).isoformat(), "pages": []}
    if entry["kind"] == "dwg":
        pg = (plan.get("pages") or [{}])[0]
        chains = native_chains_for_page(pg, plan_id=plan_id, page_index=0)
        cad = plan.get("cad_import") or {}
        out["identity"] = identify_document(" ".join(t.get("text", "") for t in pg.get("text_blocks") or []))
        out["dwg"] = {"conversion": {k: cad.get(k) for k in ("provider", "engine", "job_id", "converted_at", "source_sha256") if k in cad},
                      "units": plan.get("dxf_units"), "unit_to_m": pg.get("unit_to_m"), "dimensions": pg.get("dimensions_count"),
                      "text_blocks": len(pg.get("text_blocks") or []), "vectors_total": pg.get("vectors_total"), "layers": cad.get("layers") or cad.get("layer_stats"),
                      "walls": (pg.get("walls_analysis") or {}).get("count") if isinstance(pg.get("walls_analysis"), dict) else None,
                      "chains": {k: v for k, v in chains.items() if k not in ("chains",)}, "chain_samples": chains.get("chains", [])[:6],
                      "structural_metre": plan.get("structural_metre")}
        dxf = await load_cad_source(db, plan_id, user_id, "converted_dxf")
        if dxf:
            raw = dxf if isinstance(dxf, (bytes, bytearray)) else base64.b64decode(dxf["data_b64"])
            out["coffrage"] = coffrage_takeoff(raw)
            out["altimetry"] = altimetry_labels(raw)
            out["altimetry"]["levels"] = out["altimetry"]["levels"][:20]
        return out
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        first = doc[0]
        out["identity"] = identify_document(first.get_text(), first.get_text("words"))
        sym = parse_level_symbols(words_from_pdf_page(first))
        if sym["symbols"]:
            out["level_symbols"] = sym
            from engines.metre.coupe_marks import locate_coupe_marks
            marks = locate_coupe_marks(first)
            out["coupe_marks"] = {k: v for k, v in marks.items() if k != "unpaired_heads"} | {"unpaired_heads": len(marks["unpaired_heads"])}
        for i, page in enumerate(doc):
            if len(page.get_text().strip()) >= 20:
                native = extract_rebar_schedule(page)
                pdf_dims = ((plan.get("pages") or [{}])[i] if i < len(plan.get("pages") or []) else {}).get("pdf_dimensions") or []
                scale = out["identity"].get("declared_scale") or ""
                denom = int(scale.split("/")[1]) if "/" in scale else None
                tables = [r["bbox_pt"] for tbl in ("ha_bars", "mesh") for r in ((native.get(tbl) or {}).get("rows") or [])]
                tables += [r["bbox_pt"] for r in ((native.get("mesh_recap") or {}).get("rows") or [])]
                excl = [(b[0] - 6, b[1] - 4, b[2] + 6, b[3] + 4) for b in tables]
                oblique = match_labels(page, pt_per_m_from_scale(denom), exclude_rects=excl) if denom else None
                panels = panel_labels(page, pt_per_m_from_scale(denom), (native.get("mesh") or {}).get("rows", []), excl) if denom and native.get("mesh") else None
                if oblique:
                    oblique["unmatched_by_text"] = dict(sorted(((k, sum(1 for u in oblique["unmatched"] if u["raw_text"] == k)) for k in {u["raw_text"] for u in oblique["unmatched"]}), key=lambda kv: -kv[1])[:10])
                    oblique["unmatched"] = oblique["unmatched"][:40]
                out["pages"].append({"page": i, "mode": "native_text", "rebar": native, "pdf_dimensions_count": len(pdf_dims),
                                     "pdf_dimensions_sample": [round(d.get("measured_m") or d.get("value_m") or 0, 3) for d in pdf_dims[:12]], "oblique_dimensions": oblique, "panel_labels": panels})
    if not out["pages"] and pdf and is_vision_needed(pdf, 0):
        out["vision_required"] = True
        if vision:
            from engines.openai_studies import _log_usage
            out["vision"] = await analyze_pdf(pdf, user_id=user_id, plan_id=plan_id, pages=pages, log_usage=_log_usage)
    return out


def _truth_stub(report: dict) -> dict:
    stub = {"verified": False, "notes": "A VALIDAR pelo utilizador : valores lidos automaticamente, a corrigir onde necessário.",
            "document": {k: report.get("identity", {}).get(k) for k in ("revision_index", "revision_date", "declared_scale", "document_code")}}
    for pg in report.get("pages", []):
        rb = pg.get("rebar") or {}
        ha, mesh, recap = rb.get("ha_bars") or {}, rb.get("mesh") or {}, rb.get("mesh_recap") or {}
        if ha or mesh:
            stub["rebar"] = {"ha_rows": ha.get("count"), "ha_mass_kg": ha.get("total_mass_kg"), "mesh_rows": mesh.get("count"),
                             "mesh_mass_kg": mesh.get("rows_mass_kg"), "mass_laid_kg": recap.get("mass_laid_kg"),
                             "rows": {str(r["mark"]): {"total_count": r["total_count"], "unit_length_cm": r["unit_length_cm"], "total_length_cm": r["total_length_cm"]}
                                      for r in (ha.get("rows") or [])[:5]}}
        break
    if report.get("vision"):
        s = report["vision"]["summary"]
        stub["beams"] = {"elements": s["elements"], "total_steel_kg": s["total_steel_kg"], "total_concrete_m3": s["total_concrete_m3"], "labels": s["labels"]}
    return stub


def volumes_markdown(full: dict, formwork_name: str) -> str:
    reg, scope = full.get("registration") or {}, full.get("scope") or {}
    fw = (full.get("sources") or {}).get("formwork_pdf") or {}
    dxw = ((full.get("sources") or {}).get("dxf") or {}).get("walls") or {}
    comp = dxw.get("completion") or {}
    md = f"\n### Coupes localizadas no plano de coffrage ({formwork_name}) e volumes do bâtiment desenhado\n\n"
    md += (f"- Têtes de coupe (numeral + equerre + ponto) : {fw.get('coupe_marks', {}).get('traces')} traçados para as coupes {fw.get('coupe_marks', {}).get('names')} · "
           f"cabeças sem par : {fw.get('coupe_marks', {}).get('unpaired_heads')}\n")
    if reg.get("ok"):
        md += f"- Recalage plano ↔ DXF pelos eixos {', '.join(reg['common_axes'])} ({', '.join(reg['intersections_used'])}) : resíduo {reg['residual_m'] * 1000:.0f} mm · escala medida/declarada {reg['scale_vs_declared']} ({reg['scale_state']})\n"
    else:
        md += f"- Recalage plano ↔ DXF : **impossível** — {reg.get('error')}\n"
    md += "\n| Coupe | inst. | traçado m | murs DXF atravessados (ép. cm) | poutres | ép. voiles impressas (coupe) | níveis de base (coupe) | h mur (coupe) | controle ép. |\n|---|---|---|---|---|---|---|---|---|\n"
    for c in full.get("coupes_located") or []:
        sh = c.get("sheet") or {}
        md += (f"| {c['name']} | {c['instance']} | {c['length_m']} | {c['walls_crossed']} {c['wall_thicknesses_dxf_cm']} | {c['beams_crossed']} | {sh.get('wall_thickness_cm')} | "
               f"{sh.get('base_levels_m')} | {sh.get('h_mur_m')} | {(c.get('thickness_check') or {}).get('state')} {(c.get('thickness_check') or {}).get('common_cm')} |\n")
    md += (f"\n- **Murs completados** : {dxw.get('closed_faces_only', {}).get('length_total_m')} ml em faces fechadas + {comp.get('added_length_m')} ml por pares de linhas paralelas às espessuras das coupes "
           f"{comp.get('thicknesses_used_cm')} → **{dxw.get('length_total_m')} ml** ({dxw.get('plan_area_m2')} m² em planta) · por espessura : {dxw.get('length_by_thickness_m')} · "
           f"linhas sem par (não contadas) : {comp.get('unpaired', {}).get('count')} / {comp.get('unpaired', {}).get('length_m')} ml\n")
    md += f"- Âmbito : {'emprise do plano de coffrage (bâtiment desenhado) ' + str(scope.get('extent_m')) if scope.get('clipped_to_plan') else 'nível completo do DXF'}\n"
    wz = full.get("walls_by_zone") or {}
    md += f"- Murs por zona de coupe (m³) : {wz.get('volume_by_coupe_m3')} · confirmado {wz.get('volume_confirmed_m3')} m³ · a esclarecer {wz.get('volume_to_clarify_m3')} m³ ({wz.get('walls_in_extent')} corpos)\n"
    for l in full.get("lines") or []:
        md += f"- {l['element']} : {l['formula'] or '—'} → **{l['net'] if l['net'] is not None else 'indeterminado'} {l['unit']}** ({l['state']})" + (f" · falta : {', '.join(l['missing'])}" if l.get("missing") else "") + "\n"
    if full.get("total_m3") is not None:
        incl = " + ".join(l["element"].split(" — ")[0].split(" appariées")[0].lower() for l in full.get("lines") or [] if l.get("net") is not None)
        md += f"- **Total béton ({incl}, bâtiment do plano) : {full['total_m3']} m³**\n"
    for f in full.get("findings") or []:
        md += f"- ℹ {f['subject']} : {f['explanation']}\n"
    return md


def _fmt(v, unit=""):
    return "—" if v is None else f"{v:g}{unit}"


def markdown(reports: list[dict], eval_summary: dict | None) -> str:
    L = ["# Relatório de leitura — conjunto de avaliação", "", f"Gerado em {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC · {len(reports)} plano(s).",
         "", "Todos os valores abaixo foram **lidos** (texto nativo do PDF, DWG nativo ou leitura visual IA) — nenhum foi inventado nem corrigido. ",
         "Por favor valide/corrija os ficheiros `tests/fixtures/eval/<plano>.truth.json` (campo `verified: true` quando confirmado).", ""]
    for r in reports:
        ident = r.get("identity", {})
        L += [f"## {r['name']}", "", f"- `plan_id` : `{r['plan_id']}` · tipo : {r['kind']}",
              f"- Identidade lida : código **{ident.get('document_code') or '—'}** · índice **{ident.get('revision_index') or '—'}** ({ident.get('revision_label') or '—'}) "
              f"de **{ident.get('revision_date') or '—'}** · escala {ident.get('declared_scale') or '—'} · nível {ident.get('level') or '—'} · título « {ident.get('title') or '—'} »"]
        for pg in r.get("pages", []):
            rb = pg["rebar"]
            ha, mesh, recap, steel = rb.get("ha_bars"), rb.get("mesh"), rb.get("mesh_recap"), rb.get("steel_recap")
            L.append(f"- Página {pg['page'] + 1} (texto nativo) · cotas vetoriais detetadas : {pg['pdf_dimensions_count']}" + (" · nomenclatura **parcial**" if rb.get("partial") else ""))
            if ha:
                L.append(f"  - **Aciers HA** : {ha['count']} repères lidos · massa teórica **{ha['total_mass_kg']} kg** · por ∅ : " +
                         ", ".join(f"{k} {v['length_m']:g} m / {v['mass_kg']:g} kg" for k, v in ha["by_diameter"].items()))
                L.append(f"  - Controles aritméticos : {len(ha['checks'])} verificados, **{len(ha['inconsistencies'])} incoerência(s)**" +
                         ("" if not ha["inconsistencies"] else " → " + "; ".join(f"repère {c['mark']} : {c['formula']} ≠ {c['declared']:g}" for c in ha["inconsistencies"][:5])))
                if ha.get("comparison"):
                    c = ha["comparison"]
                    L.append(f"  - Σ nomenclatura HA {c['a_kg']:g} kg vs récap aciers {c['b_kg']:g} kg → écart **{c['difference_kg']:+g} kg**")
                if steel:
                    L.append(f"  - Récap aciers impresso : façonnés {_fmt(steel.get('ha_shaped_kg'), ' kg')} · non façonnés {_fmt(steel.get('ha_straight_kg'), ' kg')}")
            if mesh:
                L.append(f"  - **Treillis soudés** : {mesh['count']} panneaux lidos · Σ masses **{mesh['rows_mass_kg']} kg** · por tipo : " +
                         ", ".join(f"{k} ×{v['count']} ({v['mass_kg']:g} kg)" for k, v in mesh["by_panel"].items()))
                for c in mesh.get("comparisons", []):
                    L.append(f"  - {c['a']} {c['a_kg']:g} kg vs {c['b']} {c['b_kg']:g} kg → écart **{c['difference_kg']:+g} kg**" + (f" ({c['meaning']})" if c.get("meaning") else ""))
            if recap:
                L.append(f"  - Récapitulatif treillis : {len(recap['rows'])} linhas · Σ {_fmt(recap.get('sum_mass_kg'), ' kg')} · masse totale {_fmt(recap.get('mass_total_kg'), ' kg')} · masse posée {_fmt(recap.get('mass_laid_kg'), ' kg')}")
            for f in rb.get("findings", []):
                L.append(f"  - ⚠ {f['subject']} — {f['explanation']}")
            ob = pg.get("oblique_dimensions")
            if ob:
                cal = ob["calibration"]
                L.append(f"  - **Cotas desenhadas (obliquas/tracejadas)** : {len(ob['dimensions'])} confirmadas em {ob['labels']} etiquetas numéricas · escala real do tirage "
                         f"{'auto-calibrada ×' + str(cal.get('print_ratio')) if cal.get('self_calibrated') else 'igual à declarada'} ({cal.get('samples')} amostras) · "
                         f"não confirmadas por valor : {ob['unmatched_by_text']}")
                worst = sorted(ob["dimensions"], key=lambda d: -abs(d["difference_mm"]))[:3]
                L.append("  - Exemplos confirmados : " + "; ".join(f"{d['raw_text']} → {d['measured_m']:.3f} m ({d['difference_mm']:+.0f} mm, {d['bounds_source']})" for d in worst))
            pl = pg.get("panel_labels")
            if pl:
                c = pl["counts"]
                L.append(f"  - **Etiquetas dos painéis treillis (cruz Arche)** : {pl['marks_in_drawing']} repères Tnn no desenho · {c['confirmed_by_geometry']} etiquetas confirmadas pela geometria, "
                         f"{c['confirmed_by_schedule']} pela nomenclatura (découpes/recouvrements), **{c['to_clarify']} a esclarecer** · repères fora da nomenclatura : {c['marks_not_in_schedule']}")
                miss = [r for r in pl["rows"] if r["missing_expected_cm"]]
                L.append(f"  - Painéis cujas dimensões de découpe não aparecem todas no desenho : {len(miss)} (ex. " + "; ".join(f"{r['mark']} {r['panel']} falta {r['missing_expected_cm']}" for r in miss[:4]) + ")")
        if r.get("vision_required") and not r.get("vision"):
            L.append("- Páginas **sem texto nativo** (texto vetorizado) : leitura visual IA necessária (`--vision`).")
        if r.get("vision"):
            v, s = r["vision"], r["vision"]["summary"]
            tb = s.get("title_block") or {}
            L += [f"- Leitura visual IA ({v['model']}) : {v['pages']} páginas · rotação {v['rotation_deg']}°",
                  f"  - Cartouche (leitura visual) : código **{tb.get('document_code') or '—'}** · índice **{tb.get('revision_index') or '—'}** de **{tb.get('revision_date') or '—'}** · "
                  f"affaire {tb.get('project') or '—'} ({tb.get('project_ref') or '—'}) · nível {tb.get('level') or '—'} · {tb.get('author') or '—'}",
                  f"  - **{s['elements']} feuilles d'éléments** lidas : {', '.join(x or '?' for x in s['labels'])}",
                  f"  - Σ Acier **{s['total_steel_kg']} kg** · Σ Béton **{s['total_concrete_m3']} m³**" + (f" · repères vistos em várias folhas (referências a confirmar) : {', '.join(s['duplicate_labels'])}" if s["duplicate_labels"] else ""),
                  f"  - Feuilles com incoerência aritmética (Σ barras ≠ Lg/Poids impresso) : {', '.join(s['sheets_with_inconsistencies']) or 'nenhuma'}",
                  f"  - Feuilles com valores ilegíveis : {', '.join(s['sheets_with_missing_values']) or 'nenhuma'}"]
            if s.get("schedule_sheets"):
                L.append(f"  - **{s['schedule_sheets']} feuilles à nomenclature** (BN / PV / attentes) : {s['schedule_rows']} repères HA lidos · massa teórica **{s['schedule_steel_kg']} kg** · "
                         f"elementos : {', '.join(s['schedule_elements']) or '—'}")
            if s.get("comparison"):
                c = s["comparison"]
                L.append(f"  - {c['a']} {c['a_kg']:g} kg vs {c['b']} {c['b_kg']:g} kg → écart **{c['difference_kg']:+g} kg** ({c['note']})")
            L.append("")
            L.append("  | Página | Elemento | Nível | Béton m³ | Acier kg | d kg/m³ | Section | Barres | Controles | Ilegível |")
            L.append("  |---|---|---|---|---|---|---|---|---|---|")
            for sh in v["sheets"]:
                el, chk = sh.get("element") or {}, sh.get("checks") or {}
                if sh.get("page_kind") == "schedule_sheet":
                    sc = chk.get("schedule") or {}
                    L.append(f"  | {sh['page'] + 1} | {', '.join(e.get('label') or '?' for e in sh.get('elements') or [])} | — | — | {sc.get('total_mass_kg', '—')} (théorique) | — | — | "
                             f"{sc.get('rows', 0)} repères | {len(chk.get('checks', [])) - len(chk.get('inconsistencies', []))}/{len(chk.get('checks', []))} ok | {len(sh.get('unreadable') or [])} |")
                    continue
                if sh.get("page_kind") != "element_sheet":
                    L.append(f"  | {sh['page'] + 1} | *{sh.get('page_kind')}* {', '.join(e.get('label') or '?' for e in sh.get('elements') or [])} | | | | | | {len(sh.get('bars') or [])} | | {len(sh.get('unreadable') or [])} |")
                    continue
                sec = f"{_fmt(el.get('width_cm'))}×{_fmt(el.get('height_cm'))}"
                state = f"{len(chk.get('checks', [])) - len(chk.get('inconsistencies', []))}/{len(chk.get('checks', []))} ok"
                L.append(f"  | {sh['page'] + 1} | {el.get('label') or '?'} | {el.get('level') or '—'} | {_fmt(el.get('concrete_m3'))} | {_fmt(el.get('steel_kg'))} | "
                         f"{_fmt(el.get('ratio_kg_m3'))} | {sec} | {len(sh.get('bars') or [])} | {state} | {len(sh.get('unreadable') or [])} |")
            n_el = len([x for x in v["sheets"] if x.get("page_kind") == "element_sheet"])
            if n_el and len(s["sheets_with_inconsistencies"]) >= n_el / 2:
                L.append("  - Nota : o desvio Σ(nombre × Lg) ≠ Lg/Poids é **sistemático nas barras façonnées** das folhas Arche (método de cálculo da longueur développée do "
                         "software) — a esclarecer com o BET ; nenhum valor impresso foi alterado.")
            for sh in v["sheets"]:
                for c in (sh.get("checks") or {}).get("inconsistencies", []):
                    el = sh.get("element") or {}
                    tag = f"HA{c['diameter_mm']}" if c.get("diameter_mm") else f"repère {c.get('mark')}" if c.get("mark") is not None else ""
                    L.append(f"  - ⚠ p.{sh['page'] + 1} {el.get('label') or ''} {tag} : {c['check']} → {c.get('formula')} vs {c.get('declared')} impresso")
        if r.get("dwg"):
            d, sm = r["dwg"], r["dwg"].get("structural_metre") or {}
            L += [f"- DWG convertido (Autodesk APS, DWG→DXF) : unidade CAO→m {d.get('unit_to_m')} · {d.get('vectors_total')} vetores · {d.get('text_blocks')} textos · "
                  f"**{d.get('dimensions')} entidades DIMENSION nativas** · cadeias de cotas construídas : {d['chains'].get('chains_total', 0)}",
                  f"  - Camadas ({len(d.get('layers') or [])}) : {', '.join(l['name'] for l in (d.get('layers') or [])[:24])}",
                  f"  - Métré estrutural por camadas (a validar) : murs {sm.get('walls_ml')} ml (ép. dominante {(sm.get('detected') or {}).get('wall_thickness_m')} m) · poutres {sm.get('beams_ml')} ml · "
                  f"poteaux {sm.get('columns_count')} · emprise {sm.get('footprint_m2')} m² · portes {(sm.get('openings') or {}).get('portes')} · fenêtres {(sm.get('openings') or {}).get('fenetres')}",
                  "  - ⚠ Sem cartouche nem cotas de texto no ficheiro (exportação Revit do espace objet) : identidade/revisão e cadeias de cotas **não determináveis** a partir deste DWG ; só geometria."]
            co = r.get("coffrage")
            if co:
                e = co["elements"]
                L += ["  - **Métré coffrage por elemento (faces fechadas dos calques nativos)** :",
                      f"    - Poteaux : **{e['columns']['count']}** · Σ secções {e['columns']['section_total_m2']} m² · secções : " + ", ".join(sorted({f"{c['w_cm']:g}×{c['h_cm']:g}" for c in e['columns']['rows']})[:12]),
                      f"    - Murs : **{e['walls']['count']}** corpos fechados · {e['walls']['length_total_m']} ml · por espessura : {e['walls']['length_by_thickness_m']}",
                      f"    - Poutres : **{e['beams']['count']}** · {e['beams']['length_total_m']} ml · larguras : " + ", ".join(sorted({f"{b['width_m'] * 100:.0f} cm" for b in e['beams']['rows']})),
                      f"    - Dalle : {e['slab']['net_area_m2'] if e['slab'] else '—'} m² ({e['slab']['panels'] if e['slab'] else 0} painéis, {e['slab']['openings_count'] if e['slab'] else 0} aberturas) · Linteaux : {e['lintels']['count_blocks']} blocos",
                      "    - Volumes : **indeterminados** (faltam hauteur sous dalle, épaisseur dalle, retombées) — linhas de prova em `coffrage.lines`"]
                for row in e["walls"]["rows"][:5]:
                    L.append(f"    - {row['ref']} : {row['formula']}")
                for row in e["beams"]["rows"][:3]:
                    L.append(f"    - {row['ref']} : {row['formula']}")
            al = r.get("altimetry")
            if al:
                L.append(f"  - **Altimetrias (AI/AS)** : {al['ai_count']} etiquetas AI (arase inférieure, {al['ai_range_m']} m NGF) · {al['as_count']} AS · alturas de elementos dedutíveis : {len(al['element_heights'])} · "
                         f"reservas com dimensões : {len(al['reservations'])} (ex. " + "; ".join(f"{x['w_cm']}×{x['h_cm']} AI {x['ai_m']}" for x in al["reservations"][:3]) + ")")
                for f in al["findings"]:
                    L.append(f"  - ⚠ {f['subject']} — {f['explanation']}")
            for ch in d.get("chain_samples", []):
                L.append(f"  - cadeia : {json.dumps({k: ch[k] for k in ch if k in ('kind', 'formula', 'result', 'declared', 'state', 'axis')}, ensure_ascii=False)}")
        if r.get("level_symbols"):
            ls = r["level_symbols"]
            L.append(f"- **Símbolos de nível NGF** : {len(ls['symbols'])} (AS plancher brut {ls['distinct_as_plancher_m']} m · épaisseurs {ls['distinct_epaisseur_cm']} cm · dominante {ls['dominant']}) · "
                     f"têtes de coupe (numeral + equerre + ponto) : {len((r.get('coupe_marks') or {}).get('coupes', []))} traçados → coupes {(r.get('coupe_marks') or {}).get('names')}")
            for sy in ls["symbols"][:8]:
                L.append(f"  - {sy['raw']} → AS brut {sy['as_plancher_m']} · fini {sy['as_fini_m']} · ép. {sy['epaisseur_cm']} cm · AI {sy['ai_plancher_m']}")
        if r.get("evaluation"):
            L.append(f"- Avaliação vs truth : {json.dumps({k: v for k, v in r['evaluation'].items() if k in ('identity', 'rebar')}, ensure_ascii=False)[:600]}")
        L.append("")
    if eval_summary:
        L += ["## Síntese da avaliação (apenas planos com truth verificado)", "", "```json", json.dumps(eval_summary, ensure_ascii=False, indent=1), "```"]
    return "\n".join(L)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--vision", action="store_true")
    ap.add_argument("--only", default=None)
    ap.add_argument("--pages", default=None, help="ex. 15-37 (índices 0-based) : só estas páginas na leitura visual, fundidas com o resultado anterior")
    args = ap.parse_args()
    base_url = os.environ.get("EVAL_API_URL") or "http://localhost:8001"
    reg = await upload_all(base_url) if args.upload else _registry()
    if not (args.analyze or args.vision):
        return
    db = await _db()
    admin = await db.users.find_one({"email": os.environ["TEST_ADMIN_EMAIL"]}, {"_id": 0, "user_id": 1})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    reports, evals = [], {}
    for name, entry in reg.items():
        if args.only and args.only not in name:
            continue
        stem = Path(name).stem
        pages = None
        if args.pages:
            a, _, b = args.pages.partition("-")
            pages = list(range(int(a), int(b or a) + 1))
        report = await analyze(name, entry, db, user_id=admin["user_id"], vision=args.vision, pages=pages)
        if (OUT_DIR / f"{stem}.json").exists():
            prev = json.loads((OUT_DIR / f"{stem}.json").read_text())
            if prev.get("vision"):
                report["vision"] = _merge_vision(prev["vision"], report["vision"]) if report.get("vision") else prev["vision"]
        truth_path = TRUTH_DIR / f"{stem}.truth.json"
        if truth_path.exists() and json.loads(truth_path.read_text()).get("verified"):
            truth = json.loads(truth_path.read_text())
            first = (report.get("pages") or [{}])[0]
            report["evaluation"] = evaluate_plan("", truth, rebar=(first.get("rebar") if first else None))
            report["evaluation"]["identity"] = {"fields": {f: {"expected": truth["document"].get(f), "read": report["identity"].get(f), "ok": truth["document"].get(f) == report["identity"].get(f)}
                                                           for f in truth.get("document", {})}}
            report["evaluation"]["identity"].update(correct=sum(1 for c in report["evaluation"]["identity"]["fields"].values() if c["ok"]), total=len(report["evaluation"]["identity"]["fields"]))
            evals[stem] = report["evaluation"]
        elif not truth_path.exists():
            truth_path.write_text(json.dumps(_truth_stub(report), ensure_ascii=False, indent=1))
        (OUT_DIR / f"{stem}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
        reports.append(report)
        print(f"[analyze] {name}: pages={len(report['pages'])} vision={'yes' if report.get('vision') else 'no'} dwg={'yes' if report.get('dwg') else 'no'}")
    by_stem = {Path(r["name"]).stem: r for r in reports}
    lower, upper, rdc = (by_stem.get(k) for k in ("GO-B3-R0-302_nappe_inferieure", "GO-B3-R0-303_nappe_superieure", "RDC"))
    cross = None
    if lower and upper and lower.get("pages") and upper.get("pages"):
        slab = ((rdc or {}).get("coffrage") or {}).get("elements", {}).get("slab") or {}
        cross = cross_nappes(lower["pages"][0]["rebar"], upper["pages"][0]["rebar"], slab_area_m2=slab.get("net_area_m2"))
        (OUT_DIR / "cross_nappes.json").write_text(json.dumps(cross, ensure_ascii=False, indent=1))
    poutre = by_stem.get("GO-B3-R0-301_poutre_BN_PV")
    pairing = None
    if poutre and poutre.get("vision") and rdc and rdc.get("coffrage"):
        pairing = pair_beams(poutre["vision"], rdc["coffrage"]["elements"]["beams"]["rows"])
        pairing["lines"] = ratio_lines(pairing, poutre["vision"]["summary"].get("schedule_steel_kg"))
        (OUT_DIR / "steel_ratio.json").write_text(json.dumps(pairing, ensure_ascii=False, indent=1))
    md = markdown(reports, summary(evals) if evals else None)
    levels_path = TRUTH_DIR / "levels_RDC.json"
    if rdc and rdc.get("coffrage"):
        levels = json.loads(levels_path.read_text()) if levels_path.exists() else {}
        coffrage_pdf = next((r for r in reports if r.get("level_symbols") and "coffrage" in r["name"].lower()), None)
        coupes_path = OUT_DIR / "coupes_PH_RDC.json"
        coupes = None
        if coupes_path.exists():
            from engines.metre.coupes_vision import recheck
            res = recheck(json.loads(coupes_path.read_text()), (coffrage_pdf or {}).get("level_symbols", {}).get("dominant", {}).get("as_plancher_m"))
            coupes_path.write_text(json.dumps(res, ensure_ascii=False, indent=1))
            coupes = res["summary"]
        md_note = None
        if not levels and coffrage_pdf:
            base = (coupes or {}).get("dominant", {}).get("niveau_base_murs_m")
            levels = levels_from_symbols(coffrage_pdf["level_symbols"], base_level_m=base, source=f"symboles NGF du plan {coffrage_pdf['name']}" + (" + niveau de base des coupes" if base else ""))
            md_note = (f"- Níveis lidos automaticamente : símbolos NGF de {coffrage_pdf['name']} → {coffrage_pdf['level_symbols']['dominant']} ; "
                       f"nível de base dos murs (coupes, dominante) → {base} ; níveis de base por zona nas coupes : {(coupes or {}).get('base_levels_m')}")
        if coupes:
            md_note = (md_note or "") + (f"\n- **Coupes GO-B3-R0-200** : {len(coupes['coupes'])} coupes lidas ({', '.join(c or '?' for c in coupes['coupes'])}) · AS plancher haut B : {coupes['as_plancher_haut_m']} · "
                                          f"épaisseurs dalle : {coupes['slab_thickness_cm']} · épaisseurs voiles : {coupes['wall_thickness_cm']} · écarts de níveis confirmados pela cadeia vertical impressa : "
                                          f"{coupes['confirmed_level_gaps']} / {coupes['confirmed_level_gaps'] + coupes['unconfirmed_level_gaps']}")
            for hgt in coupes["heights"][:12]:
                md_note += f"\n  - h mur = {hgt['formula']} · prova (cotas verticais) : {hgt['chain_proof_cm'] or 'não encontrada'}"
        vols = volumes_from_takeoff(rdc["coffrage"], levels, pairing)
        (OUT_DIR / "volumes_RDC.json").write_text(json.dumps(vols, ensure_ascii=False, indent=1))
        md += "\n\n## Volumes de betão RDC (regra : AS murs = AI plancher haut)\n\n"
        if md_note:
            md += md_note + "\n"
        md += f"- Níveis fornecidos : {json.dumps(levels, ensure_ascii=False) if levels else '**nenhum** (`tests/fixtures/eval/levels_RDC.json` ausente)'} · alturas derivadas : h murs/poteaux {vols['heights']['h_murs_m']} m · AI plancher {vols['heights']['ai_plancher_haut_m']} m\n"
        md += "- Nível completo do DXF, só faces fechadas (referência histórica) :\n"
        for l in vols["lines"]:
            md += f"  - {l['element']} : {l['formula'] or '—'} → **{l['net'] if l['net'] is not None else 'indeterminado'} {l['unit']}** ({l['state']})\n"
        if vols["total_m3"] is not None:
            md += f"  - Total béton nível DXF completo : {vols['total_m3']} m³\n"
        # coupes located on the formwork plan, walls completed, scope = building drawn on the formwork plan
        full = None
        if coffrage_pdf and coupes_path.exists():
            from engines.metre.volumes_tool import compact_for_llm, compute_volumes
            plan_rdc = await db.plans_takeoff.find_one({"plan_id": rdc["plan_id"]}, {"_id": 0, "user_id": 1})
            dxf_raw = await load_cad_source(db, rdc["plan_id"], plan_rdc["user_id"], "converted_dxf")
            dxf_raw = dxf_raw if isinstance(dxf_raw, (bytes, bytearray)) else base64.b64decode(dxf_raw["data_b64"])
            pdf_src = await load_plan_source(db, coffrage_pdf["plan_id"], plan_rdc["user_id"])
            full = compact_for_llm(compute_volumes(dxf_raw, base64.b64decode(pdf_src["data_b64"]), json.loads(coupes_path.read_text()), beams_pairing=pairing))
            (OUT_DIR / "volumes_RDC_coupes.json").write_text(json.dumps(full, ensure_ascii=False, indent=1))
            md += volumes_markdown(full, coffrage_pdf["name"])
        al = rdc.get("altimetry") or {}
        if al.get("ai_range_m"):
            md += f"- Indício (não utilizado) : AI das reservas entre {al['ai_range_m'][0]} e {al['ai_range_m'][1]} m NGF — a confirmar com o plano de coffrage.\n"
    if pairing:
        md += "\n\n## Rácio aço/betão — folhas Arche ↔ poutres do DXF RDC\n\n" + pairing["note"] + "\n\n"
        md += f"- Emparelhadas **{pairing['paired']}** / {len(pairing['rows'])} folhas · sem par : {', '.join(pairing['unpaired_sheets']) or '—'} · corpos DXF sem folha : {pairing['unpaired_dxf_beams']} / {pairing['dxf_beams']}\n"
        md += f"- Agregado do nível : **{pairing['aggregate']['ratio_kg_m3']} kg/m³** ({pairing['aggregate']['formula']})\n\n"
        md += "| Poutre | b×h cm | portée cm | Béton m³ | Acier kg | d impresso | d calculado | Par DXF | Vol. DXF (L×b×h) | Δ m³ |\n|---|---|---|---|---|---|---|---|---|---|\n"
        for r in pairing["rows"]:
            d = r["dxf"] or {}
            md += f"| {r['label']} | {r['b_cm']:g}×{r['h_cm']:g} | {r['span_cm']:g} | {r['concrete_m3']} | {r['steel_kg']} | {r['ratio_kg_m3_printed']} | {r.get('ratio_kg_m3_calc')} | {d.get('ref') or 'sem par'} | {d.get('volume_m3_with_arche_h') or '—'} | {d.get('difference_m3') if d else '—'} |\n"
        md += "\nΔ negativo esperado : o béton Arche inclui os apoios ; o volume DXF é entre faces de apoio.\n"
        for l in pairing["lines"]:
            if l["state"] != "confirmed":
                md += f"- {l['element']} : {l['formula']} = {l['net']} {l['unit']} → **{l['state']}**" + (f" (falta : {', '.join(l['missing'])})" if l.get("missing") else "") + "\n"
    if cross:
        md += "\n\n## Cruzamento nappes ↔ coffrage RDC\n\n" + cross["note"] + "\n"
        for label, info in cross["layers"].items():
            md += f"- **{label}** : {info['mesh_rows']} painéis · posée {info['mesh_laid_kg']} kg · {info['mesh_pieces_from_cuts']} peças = {info['mesh_laid_area_m2_from_cuts']} m² (découpes) · commandé {info['mesh_ordered_area_m2_from_recap']} m² (récap) · HA {info['ha_rows']} repères {info['ha_mass_kg']} kg\n"
        for kind, d in cross["duplicates"].items():
            md += f"- Repères {kind.upper()} comuns às duas nappes : {d['common_marks']} (idênticos {d['identical']}, diferentes {len(d['different'])})\n"
        for c in cross["coverage"]:
            md += f"- {c['layer']} — {c['quantity']} : {c['area_m2']} m² / dalle {c['slab_area_m2']} m² → ratio **{c['ratio']}**\n"
        for f in cross["findings"]:
            md += f"- ⚠ {f['subject']} — {f['explanation']}\n"
    (OUT_DIR / "RELATORIO_LEITURA.md").write_text(md)
    print(f"→ {OUT_DIR / 'RELATORIO_LEITURA.md'}")


if __name__ == "__main__":
    asyncio.run(main())

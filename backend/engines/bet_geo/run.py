"""Estudo completo sobre geometria real: leitura → cotas (cortes) → cálculo → peças → quantidades.

Usado pelo estudo BET do Assistente quando a planta não é retangular (antes: só "peças de origem").
"""
from __future__ import annotations

import asyncio
import logging
import zipfile
from pathlib import Path

from . import levels_ai, outputs, pdf_vector, structure

log = logging.getLogger(__name__)


def _plan_page(docs):
    plans = pdf_vector.find_plans(docs)
    return plans[0].page if plans else None


async def read_any(docs, hypotheses: str, country: str, llm=None):
    """Melhor leitor disponível, por ordem de exatidão: IFC → DWG/DXF → PDF vetorial → raster (scan/imagem/foto)."""
    from . import cad, raster

    def raw(kind):
        return [d for d in docs if getattr(d, "kind", None) == kind and getattr(d, "raw", None)]

    for d in raw("ifc"):
        try:
            b = await asyncio.to_thread(cad.read_ifc, d.raw, country, d[0])
            if b is not None and b.footprint.area >= 20:
                return b
        except Exception:  # noqa: BLE001
            log.warning("bet_geo: IFC %s ilegível", d[0], exc_info=True)
    for kind, fn in (("dxf", cad.read_dxf), ("dwg", cad.read_dwg)):
        for d in raw(kind):
            try:
                b = await fn(d.raw, llm=llm, country=country, name=d[0])
                if b is not None and b.footprint.area >= 20:
                    return b
            except Exception:  # noqa: BLE001
                log.warning("bet_geo: %s %s ilegível", kind.upper(), d[0], exc_info=True)
    b = await asyncio.to_thread(pdf_vector.read, docs, hypotheses, country)
    if b is not None and b.footprint.area >= 20:
        return b
    # raster: imagens anexadas e páginas sem desenho vetorial (digitalizações), a IA escolhe a planta
    if llm is None:
        return None
    import pymupdf

    candidates = [(d[0], d.raw, 0) for d in raw("image")]
    for name, data in docs:
        try:
            pdf = pymupdf.open(stream=data, filetype="pdf")
        except Exception:  # noqa: BLE001
            continue
        for i, page in enumerate(pdf):
            if len(page.get_drawings()) < 50:              # página sem desenho vetorial → raster
                candidates.append((name, data, i))
    for name, data, i in candidates[:10]:
        try:
            img, _ = raster.load_gray(data, i, dpi=110)
            lay = await raster.ask_layout(llm, img)
            if lay.get("is_floor_plan") and lay.get("outline"):
                b = await raster.read(data, llm=llm, page_index=i, country=country, name=name, layout=lay)
                if b is not None and b.footprint.area >= 20:
                    return b
        except Exception:  # noqa: BLE001
            log.warning("bet_geo: raster %s p.%d ilegível", name, i + 1, exc_info=True)
    return None


async def study(docs, hypotheses: str, country: str, out_dir: Path, *, llm=None, meta: dict | None = None,
                on_step=None, images_fn=None) -> dict:
    """Estudo COMPLETO sobre a geometria real: estrutura, arquitetura cotada, cortes, alçados, especialidades,
    comportamento térmico REH, custo-benefício, medições e orçamento — e as imagens reais em todos os PDF.
    images_fn: async (Building, slab_h) → {vista: JPEG/PNG} (no Assistente: as mesmas imagens do orçamento)."""
    from . import costs, covers, drawings, especialidades, rooms

    async def step(label):
        if on_step:
            await on_step(label)

    await step("A ler a geometria real das plantas (IFC, DWG/DXF, PDF vetorial, digitalização ou fotografia)")
    b = await read_any(docs, hypotheses, country, llm)
    if b is None or b.footprint.area < 20:
        return {"ok": False, "reason": "geometria não legível em nenhum dos formatos recebidos"}
    await step("A ler cotas e terras suportadas nos cortes")
    if b.hypotheses.get("_reader") == "ifc":
        warns = ["Cotas lidas no modelo IFC. Terras suportadas não constam do modelo: confirmar muros de suporte."]
    else:
        warns = await levels_ai.read_levels(b, docs, llm, _plan_page(docs))
    await step("A calcular laje, vigas, pilares, fundações e muros sobre o contorno real")
    R = await asyncio.to_thread(structure.design, b)
    R.warnings = warns + R.warnings
    slab_h = R.slab["h"]
    await step("A ler divisões, quadro de áreas e mapa de vãos")
    lay = await rooms.read_layout(b, docs, llm)
    meta = {"obra": (meta or {}).get("obra") or "Moradia", **(meta or {})}
    pt = str(country).upper() == "PT"
    esp: dict = {}
    if pt:
        await step("Comportamento térmico REH, custo-benefício e especialidades (eletricidade, águas, AVAC, ventilação)")
        try:
            esp = await asyncio.to_thread(especialidades.run_all, b, lay, docs, hypotheses, meta, slab_h)
        except Exception as exc:  # noqa: BLE001 — o estudo de estrutura e as peças continuam
            log.warning("bet_geo especialidades failed", exc_info=True)
            R.warnings.append(f"Estudo térmico/especialidades não produzido ({type(exc).__name__}: {str(exc)[:160]})")
    if not esp:
        env = especialidades.envelope(b, lay, slab_h)
        esp = {"env": env, "solution": especialidades.Solution(100, 120, 100, 1.4, "bc"), "warnings": []}
    meta.setdefault("local", esp.get("concelho") or "")
    lines = costs.quote_lines(b, R, lay, esp)
    await step("A calcular as imagens reais do edifício (geometria real)")
    images: dict = {}
    try:
        import os as _os
        guard = float(_os.environ.get("STUDY_IMG_GUARD") or 240)        # o estudo nunca espera mais do que isto pelas imagens
        images = (await asyncio.wait_for(images_fn(b, slab_h), guard)) if images_fn else \
            await asyncio.to_thread(covers.local_views, b, slab_h)
    except Exception:  # noqa: BLE001 — sem imagens o estudo sai na mesma (vistas calculadas)
        log.warning("bet_geo study images failed", exc_info=True)
        try:
            images = await asyncio.to_thread(covers.local_views, b, slab_h)
        except Exception:  # noqa: BLE001
            images = {}
    out_dir.mkdir(parents=True, exist_ok=True)
    await step("A desenhar as peças de execução cotadas e a montar o processo")
    try:
        from engines.bet_core import brand as _brand
        meta["brand"] = _brand.from_branding(meta.get("branding"), "PT" if pt else "FR")
    except Exception:  # noqa: BLE001
        meta["brand"] = None
    meta["thumb"] = (images or {}).get("main")
    dpath, sheets = await asyncio.to_thread(drawings.write_drawings, b, R, lay, esp, out_dir / "Desenhos_de_execucao.pdf", meta, slab_h)
    report = outputs.write_report_pdf(b, R, out_dir / "Nota_de_calculo_estrutura.pdf", meta)
    xlsx = outputs.write_full_xlsx(lines, R, lay, out_dir / "Medicoes_e_orcamento.xlsx", meta)
    dxf = outputs.write_dxf(b, R, out_dir / "Estrutura_fundacoes.dxf")
    zpath = out_dir / "Desenhos_DXF.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(dxf, dxf.name)
    total = costs.total(lines)
    best = esp.get("best") or {}
    sol = esp["solution"]
    env = esp["env"]
    kp_lines = [f"Área de construção {b.footprint.area:.1f} m² · área útil {lay.useful_area:.1f} m²".replace(".", ","),
                f"Estrutura: laje {slab_h:.2f} m, {len(R.beams)} vigas, {len(R.columns)} pilares, {len(R.footings)} sapatas".replace(".", ",")]
    if best:
        kp_lines.append(f"REH: classe {best['classe']} · {especialidades.SYSTEMS[sol.system][0]}")
    kp_lines.append(f"Orçamento estimado: {total:,.0f} € sem IVA".replace(",", " "))
    files = []

    from engines import pdf_premium as PP
    branding = meta.get("branding")
    kpis = [("Área de construção", f"{b.footprint.area:.1f}".replace(".", ","), "m²"),
            ("Área útil aquecida", f"{lay.useful_area:.1f}".replace(".", ","), "m²"),
            ("Classe energética (REH)", best.get("classe") or "—", ""),
            ("Orçamento estimado", f"{total:,.0f}".replace(",", " "), "€ s/ IVA"),
            ("Pilares / vigas / sapatas", f"{len(R.columns)} / {len(R.beams)} / {len(R.footings)}", ""),
            ("Laje maciça", f"{slab_h:.2f}".replace(".", ","), "m"),
            ("Divisões / vãos", f"{len(lay.rooms)} / {len(lay.windows)}", ""),
            ("Folhas de desenho", str(len(sheets)), "grupos A3")]
    INDICE = ["Memória descritiva e justificativa", "Imagens do edifício — geometria real", "Nota de cálculo — pré-dimensionamento estrutural",
              "Pré-certificado energético (REH", "especialidades técnicas da habitação",
              str((esp.get("vent") or {}).get("titre") or "Ventilação"), "Análise custo-benefício — envolvente",
              "Planta de arquitetura — piso térreo (cotada)", "Planta parcial 1 — 1:50", "Cortes AA' e BB'", "Alçados Sul e Norte",
              "Alçados Nascente e Poente", "Desenho de execução da estrutura e alvenarias", "Planta de montagem e cofragem — laje",
              "Planta de fundações (cotada)", "Quadros de armaduras e betões", "Pormenores de execução — fundações",
              "Eletricidade — tomadas", "Esquema unifilar do quadro", "Águas (AF/AQ) e esgotos", "Ventilação — admissão e extração",
              "Aquecimento — piso radiante", "Esquema hidráulico de princípio"]

    def add(kind, path, label, title, subtitle, lines_=(), a3=False):
        """Acabamento IGUAL ao dos orçamentos e do dossier anterior: capa com a imagem real e indicadores, índice,
        logótipo da empresa no rodapé, MARCA D'ÁGUA da empresa em todas as folhas, numeração."""
        data = path.read_bytes()
        capa = {"tipo": title, "titulo": meta.get("obra") or title, "subtitulo": subtitle + (" · " + " · ".join(lines_[:2]) if lines_ else ""),
                "local": meta.get("local") or "", "data": __import__("datetime").date.today().strftime("%d/%m/%Y"),
                "kpis": kpis, "indice": INDICE, "imagem": (images or {}).get("main")}
        try:
            out = PP.acabar(data, capa, PP.com_cor(branding) if branding is not None else {}, "pt" if pt else "fr", paginas="completo")
        except Exception:  # noqa: BLE001
            out = data
        if out is data and images:                   # acabamento desligado pela empresa: capa simples com a imagem
            covers.prepend(path, covers.cover_pdf(images, title, subtitle, meta, list(lines_), landscape_a3=a3))
        else:
            path.write_bytes(out)
        files.append((kind, path, label))
    parts = []
    summary = _summary_pdf(b, R, lay, esp, lines, meta, sheets)
    # processo completo (como o dossier anterior: tudo num só PDF)
    proc = out_dir / "Processo_de_estudo.pdf"
    gal = covers.gallery_pdf(images, meta) if images else None
    parts = [summary, gal, report]
    for k in ("reh_pdf", "mep_pdf", "vent_pdf", "cb_pdf"):
        if esp.get(k):
            parts.append(esp[k])
    parts.append(dpath)
    covers.merge(parts, proc)
    add("pdf", proc, "Processo de estudo completo (memória, cálculos, térmica, especialidades, custo-benefício, desenhos)",
        "Processo de estudo", "Estudo completo sobre a geometria real", kp_lines)
    add("plans_pdf", dpath, "Desenhos de execução cotados (arquitetura, cortes, alçados, estrutura, especialidades)",
        "Desenhos de execução", f"{len(sheets)} grupos de folhas A3 cotadas", [s for s in sheets][:12], a3=True)
    if esp.get("reh_pdf"):
        p = out_dir / "Estudo_termico_REH.pdf"
        p.write_bytes(esp["reh_pdf"])
        add("re2020_pdf", p, "Estudo térmico REH (Portaria 138-I/2021) — pré-certificado", "Comportamento térmico",
            "REH — DL 101-D/2020, Portaria 138-I/2021", [f"Classe {best.get('classe', '-')} (RNt {best.get('RNt', 0):.2f})".replace(".", ","),
                                                       f"Concelho: {esp.get('concelho') or 'não indicado (clima admitido)'}"])
    if esp.get("cb_pdf"):
        p = out_dir / "Analise_custo_beneficio.pdf"
        p.write_bytes(esp["cb_pdf"])
        add("pdf", p, "Análise custo-benefício (isolamento, caixilharia, sistemas, fotovoltaico)", "Custo-benefício",
            f"{len(esp.get('options') or [])} soluções comparadas em 20 anos",
            [f"Recomendada: {especialidades.SYSTEMS[sol.system][0]}", f"ETICS {sol.etics} mm · Uw {sol.uw:g} · vidro g {sol.g:g}".replace(".", ",")])
    if esp.get("mep_pdf"):
        p = out_dir / "Especialidades_nota_de_calculo.pdf"
        covers.merge([esp["mep_pdf"], esp.get("vent_pdf")], p)
        add("pdf", p, "Especialidades: aquecimento, piso radiante, bomba de calor, eletricidade, águas, ventilação",
            "Especialidades", "Notas de cálculo (EN 12831, EN 1264, RTIEBT, DR 23/95, Portaria 138-I)")
    add("pdf", report, "Nota de cálculo — estrutura (geometria real)", "Estrutura", "Nota de cálculo e verificações")
    files.append(("xlsx", xlsx, "Medições e orçamento completos (Excel, fórmulas)"))
    files.append(("zip", zpath, "Desenhos DXF da estrutura"))
    for k, data in (images or {}).items():
        ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
        ip = out_dir / f"Imagem_{k}{ext}"
        ip.write_bytes(data)
        files.append(("render_png", ip, f"Imagem real do edifício — {covers.LABELS.get(k, k)}"))
    # PDF com mais de 30 folhas → também um ZIP (PDF completo + partes de 30 folhas) — pedido de 20/11
    from engines.pdf_parts import split_zip
    for kind, path, label in list(files):
        if path.suffix.lower() == ".pdf":
            z = split_zip(path.read_bytes(), path.name, lang="pt" if pt else "fr")
            if z:
                zp = path.with_suffix(".zip")
                zp.write_bytes(z)
                files.append(("zip", zp, f"{label} — ZIP (completo + partes de 30 folhas)"))
    checks_all = [*R.checks, *b.checks, *lay.checks]
    ok_checks = all(c.get("ok") is not False for c in checks_all)
    return {
        "ok": True, "building": b, "result": R, "layout": lay, "esp": esp, "lines": lines, "checks_ok": ok_checks,
        "files": files, "sheets": sheets, "images": images,
        "summary": {
            "area": round(b.footprint.area, 2), "area_util": lay.useful_area, "slab_h": slab_h, "pilares": len(R.columns),
            "vigas": len(R.beams), "sapatas": len(R.footings), "muros": len(R.retaining),
            "aco_kg": round(sum(q["aco_kg"] for q in R.quantities)),
            "betao_m3": round(sum(q["qtd"] for q in R.quantities if q["un"] == "m³" and "C" in q["item"]), 1),
            "classe": best.get("classe"), "sistema": especialidades.SYSTEMS[sol.system][0] if best else None,
            "total_ht": total, "divisoes": len(lay.rooms), "vaos": len(lay.windows),
        },
    }


def _summary_pdf(b, R, lay, esp, lines, meta, sheets) -> bytes:
    """Memória descritiva e justificativa resumida (primeira peça do processo)."""
    from engines.calc_lots import notes

    from . import costs, especialidades
    W = notes.W
    sol, env = esp["solution"], esp["env"]
    best = esp.get("best") or {}
    total = costs.total(lines)
    f = lambda x, d=1: f"{x:,.{d}f}".replace(",", " ").replace(".", ",")  # noqa: E731
    kp = [{"label": "Área de construção", "value": f(b.footprint.area), "unit": "m²"},
          {"label": "Área útil aquecida", "value": f(lay.useful_area), "unit": "m²"},
          {"label": "Classe energética (REH)", "value": best.get("classe") or "—", "ok": best.get("ok", "x") if best else "x"},
          {"label": "Orçamento estimado", "value": f(total, 0), "unit": "€ s/ IVA"}]
    lots: dict = {}
    for l in lines:
        lots[l["lot"]] = lots.get(l["lot"], 0.0) + l["qty"] * l["pu"]
    blocs = [("kpis", kp),
             ("p", "Estudo completo produzido sobre a geometria REAL lida nas peças desenhadas (qualquer forma, pátios descontados): "
                   "nenhuma envolvente retangular de substituição. Todas as quantidades e todos os desenhos derivam do mesmo modelo."),
             ("h2", "1. Edifício"),
             ("table", ["Elemento", "Valor"], [
                 ["Contorno lido", f"{f(b.footprint.area)} m², {len(b.footprint.interiors)} pátio(s), fachada {f(env.perimeter)} m"],
                 ["Fontes", "; ".join(b.sources)[:120] or "—"],
                 ["Cotas", f"pavimento {b.floor_level:+.2f}, laje {b.roof_level:+.2f}, pé-direito livre {env.hsp:.2f} m".replace(".", ",")],
                 ["Divisões", f"{len(lay.rooms)} ({sum(1 for r in lay.rooms if r.placed)} localizadas na planta)"],
                 ["Vãos", f"{len(lay.windows)} no mapa de vãos, {f(sum(w.area for w in lay.windows))} m²" if lay.windows else
                  f"{len(lay.openings)} troços de fachada sem parede"]], [45 * W, 125 * W]),
             ("h2", "2. Estrutura"),
             ("p", f"Laje maciça de cobertura C30/37 e = {R.slab['h']:.2f} m; {len(R.beams)} vigas, {len(R.columns)} pilares, "
                   f"{len(R.footings)} sapatas isoladas, {len(R.tie_beams)} vigas de fundação".replace(".", ",")
                   + (f", {len(R.retaining)} muros de suporte." if R.retaining else ".")),
             ("h2", "3. Solução térmica e sistemas (escolhida por custo-benefício, REH)"),
             ("p", f"{especialidades.SYSTEMS[sol.system][0]}; ETICS EPS {sol.etics} mm, cobertura XPS {sol.roof} mm, pavimento XPS {sol.floor} mm, "
                   f"caixilharia Uw {str(sol.uw).replace('.', ',')}, vidro g {str(sol.g).replace('.', ',')}."
                   + (f" Classe {best['classe']} (RNt {best['RNt']:.2f}".replace(".", ",") + ")." if best else " (estudo térmico não produzido)")),
             ("h2", "4. Orçamento por capítulo"),
             ("table", ["Capítulo", "Total € s/ IVA"], [[k, f(v, 0)] for k, v in lots.items()] + [["TOTAL", f(total, 0)]], [110 * W, 50 * W]),
             ("h2", "5. Peças desenhadas"), ("p", " · ".join(s for s in sheets)),
             ("h2", "6. Confrontações (duas fontes independentes)"),
             ("controls", [{"ref": c.get("check") or c.get("name") or "confrontação", "exigence": " vs ".join(c.get("sources") or []) or "—",
                            "valeur": str(c.get("value", "")), "ok": c.get("ok")} for c in [*b.checks, *lay.checks, *R.checks]][:20])]
    hyp = list(R.warnings) + list(lay.notes) + list(esp.get("warnings") or []) + list((esp.get("reh") or {}).get("hipoteses") or [])[:6]
    pdf, _ = notes.pdf("Memória descritiva e justificativa", f"{meta.get('obra', 'Moradia')} · {meta.get('local') or ''}", blocs, hyp)
    return pdf


def _obra_name(docs, hypotheses: str) -> str:
    import re
    m = re.search(r"(?i)(moradia|habita[çc][ãa]o|edif[ií]cio|maison|immeuble)[^\n.;]{0,60}", hypotheses or "")
    if m:
        return m.group(0).strip()[:80]
    from .rooms import doc_texts
    for _, _, t in doc_texts(docs)[:5]:
        m = re.search(r"(?im)^\s*(?:obra|projeto|projecto|designa[çc][ãa]o)\s*[:\-]\s*(.{4,80})$", t)
        if m:
            return m.group(1).strip()
    return "Moradia"


async def handle(db, job_id, uid, cid, request_id, docs, hypotheses, country, *, step, store, llm=None, branding=None) -> bool:
    """Gancho do estudo BET (assistant_tool). True = estudo entregue; False = deixar o fluxo anterior."""
    import os
    import tempfile

    if str(country).upper() not in ("PT", "FR"):
        return False

    async def on_step(label):
        await step(label)

    async def images_fn(b, slab_h):
        """Imagens dos PDF do estudo SEM fazer esperar o estudo pelas 4 vistas HD (20/11: estudo parado 20 min no passo
        «imagens»): 1) imagens HD já em cache para esta geometria → usadas; 2) senão, a perspetiva principal física
        1600×900 num processo separado com prazo (STUDY_IMG_TIMEOUT, 150 s) + vistas calculadas; 3) as 4 vistas HD do
        orçamento continuam em segundo plano (cache por geometria)."""
        from engines import quote_building, render_worker
        geo = {**b.to_dict(), "slab_h": slab_h}
        raw = {"_geo": geo}
        try:
            hit = await db.house_renders.find_one({"key": quote_building.geometry_key(raw)}, {"_id": 0}) if db is not None else None
        except Exception:  # noqa: BLE001
            hit = None
        if hit and hit.get("views") and hit.get("quality") not in (None, "pbr_partial"):
            import base64 as _b64
            return {k: _b64.b64decode(v) for k, v in hit["views"].items()}
        from . import covers
        out = await asyncio.to_thread(covers.local_views, b, slab_h, ("main", "side", "rear", "aerial"))
        main = await render_worker.render("geo", geo, "main", 1600, 900, int(os.environ.get("STUDY_IMG_SPP") or 24),
                                          float(os.environ.get("STUDY_IMG_TIMEOUT") or 150))
        if main:
            out["main"] = main
        try:                                       # vistas HD do orçamento: em segundo plano, nunca esperadas aqui
            await asyncio.wait_for(quote_building.views(db, raw, 0), 30)
        except Exception:  # noqa: BLE001
            log.warning("bet_geo: arranque das vistas HD falhou", exc_info=True)
        return out

    meta = {"obra": _obra_name(docs, hypotheses), "branding": branding}
    with tempfile.TemporaryDirectory(prefix="cp_geo_") as tmp:
        try:
            res = await study(docs, hypotheses, country, Path(tmp), llm=llm, on_step=on_step, meta=meta, images_fn=images_fn)
        except Exception:  # noqa: BLE001
            log.exception("bet_geo study failed for %s", job_id)
            return False
        if not res.get("ok"):
            log.info("bet_geo: %s", res.get("reason"))
            return False
        arts = []
        for kind, path, label in res["files"]:
            try:
                arts.append(await store(db, uid, cid, request_id, kind, path, label))
            except Exception:  # noqa: BLE001 — um ficheiro grande demais não impede os outros
                log.warning("bet_geo store %s failed", path.name, exc_info=True)
    R, s, b = res["result"], res["summary"], res["building"]
    esp, lay = res["esp"], res["layout"]
    points = [
        f"Geometria real: {s['area']:.1f} m² de construção, {s['area_util']:.1f} m² úteis aquecidos, {s['divisoes']} divisões".replace(".", ",")
        + (f", {s['vaos']} vãos" if s["vaos"] else "") + ".",
        f"Estrutura: laje maciça e = {s['slab_h']:.2f} m, {s['vigas']} vigas, {s['pilares']} pilares, "
        f"{s['sapatas']} sapatas" + (f", {s['muros']} muro(s) de suporte" if s["muros"] else "") + ".",
        f"Betão estrutural ≈ {s['betao_m3']:.1f} m³ · aço A500 ≈ {s['aco_kg']} kg.".replace(".", ",", 1),
    ]
    if s.get("classe"):
        sol = esp["solution"]
        points.append(f"REH: classe {s['classe']} com {s['sistema']}; ETICS {sol.etics} mm, Uw {str(sol.uw).replace('.', ',')}, "
                      f"vidro g {str(sol.g).replace('.', ',')} (menor custo a 20 anos entre as soluções que cumprem).")
    points.append(f"Orçamento estimado (preços de referência): {s['total_ht']:,.0f} € sem IVA.".replace(",", " "))
    points += R.warnings + lay.notes + list(esp.get("warnings") or [])
    review = ("Estudo completo sobre geometria real — confrontações OK. Projetos a assinar pelos técnicos responsáveis."
              if res["checks_ok"] else
              "Estudo completo sobre geometria real — há confrontações a rever (ver avisos).")
    geo = {**b.to_dict(), "slab_h": R.slab["h"]}
    extra = {"thermal": {"classe": s.get("classe"), "RNt": (esp.get("best") or {}).get("RNt"), "concelho": esp.get("concelho")}
             if s.get("classe") else None}
    await step("Estudo completo concluído (geometria real)", status="done", review_status=review, artifacts=arts,
               points=points, questions=[], geometry_verified=True, execution_verified=False,
               geo_engine={"summary": s, "checks": R.checks, "geometry_checks": b.checks, "layout_checks": lay.checks,
                           "rooms": [r.to_dict() for r in lay.rooms], "sheets": res["sheets"]},
               geo_building=geo, devis_ht=s["total_ht"], **extra)
    # orçamento OFICIAL (PDF/Excel do orçamento e da medição, com as imagens reais) a partir das mesmas linhas
    try:
        from engines.bet_core.assistant_tool import study_quote
        name = meta["obra"] + (f" — {esp.get('concelho')}" if esp.get("concelho") else "")
        qid, qarts = await asyncio.wait_for(
            study_quote(db, uid, cid, job_id, {"lines": res["lines"], "lang": "pt" if str(country).upper() == "PT" else "fr"},
                        country, {"project": {"name": name}}, building_model={"_geo": geo}),
            float(os.environ.get("BET_QUOTE_TIMEOUT") or 300))
        if qid:
            await step("Estudo completo concluído (geometria real)", artifacts=arts + list(qarts), quote_doc_id=qid)
    except Exception:  # noqa: BLE001 — o orçamento oficial nunca bloqueia o estudo já entregue
        log.warning("bet_geo study quote failed for %s", job_id, exc_info=True)
    return True


async def geo_first(db, job_id, uid, cid, request_id, docs, hypotheses, country, step, store, llm=None, *,
                    when_irregular_only=False, branding=None) -> bool:
    """Ponto de entrada no estudo BET. False = seguir o fluxo anterior; nunca levanta exceção.

    when_irregular_only: só atua se a planta não for retangular (o motor bet_core trata os retângulos).
    Desligar em produção sem deploy: BET_GEO_ENGINE=0.
    """
    import os

    if str(os.environ.get("BET_GEO_ENGINE", "1")).lower() in ("0", "false", "no"):
        return False
    try:
        exact = any(getattr(d, "kind", None) in ("ifc", "dxf", "dwg") for d in docs)
        if when_irregular_only and not exact:
            from engines.bet_core import geometry_review as _gr
            if await asyncio.to_thread(_gr.inspect, docs, hypotheses) is None:
                return False
        if llm is None:
            from engines.bet_core.reader import _default_llm as llm
        return await handle(db, job_id, uid, cid, request_id, docs, hypotheses, country, branding=branding,
                            step=step, store=store, llm=llm)
    except Exception:  # noqa: BLE001 — nunca estraga o estudo: volta ao fluxo anterior
        log.warning("bet_geo failed for %s", job_id, exc_info=True)
        return False

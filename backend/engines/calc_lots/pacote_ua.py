"""Pacote completo de um caso já lido nos planos (casos/*.json com divisões e especialidades): planos de execução UK / EN
(GO-01…08 do dossier + EL / WS / HT + GO-09, capa premium com render) e orçamento detalhado UK / EN (PDF premium).

Usado pela ferramenta calcul_ucrania quando `caso` é indicado — o mesmo resultado que o pacote preparado para o cliente."""
from __future__ import annotations

import copy
import json
import os
import re

CASOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "casos")
PROJ = {"uk": "Житловий будинок, секція А — Rezult CLT", "en": "Residential house, Unit A — Rezult CLT"}
LOC = {"uk": "Київ, Україна", "en": "Kyiv, Ukraine"}


def listar() -> list[str]:
    return sorted(f[:-5] for f in os.listdir(CASOS) if f.endswith(".json")) if os.path.isdir(CASOS) else []


def carregar(caso: str) -> dict:
    fn = os.path.join(CASOS, f"{caso}.json")
    if caso not in listar():
        raise ValueError(f"caso desconhecido {caso!r} ({', '.join(listar())})")
    return json.load(open(fn, encoding="utf-8"))


def renders_fixos(caso: str) -> list | None:
    """Fotos realistas já validadas do caso (casos/<caso>_renders/principal|terraco|aerea.jpg) → entrega imediata, sem
    render nem IA no momento do pedido. None se a pasta não existir ou estiver incompleta."""
    pasta = os.path.join(CASOS, f"{caso}_renders")
    out = []
    for nome in ("principal", "terraco", "aerea"):
        fn = next((os.path.join(pasta, nome + ext) for ext in (".jpg", ".png") if os.path.exists(os.path.join(pasta, nome + ext))), None)
        if not fn:
            return None
        out.append((nome, open(fn, "rb").read()))
    return out


def parametros(caso: str) -> dict:
    """Parâmetros de calcul_ucrania para o caso (geometria lida nos planos)."""
    c = carregar(caso)
    mod = {k: v for k, v in c.items() if k not in ("divisoes", "mep", "envolvente", "render_opcoes", "fonte", "parametros")}
    p = {"cidade": "kyiv", "uso": "residencial", "area_aquecida_m2": 200, "volume_m3": 560, "sistema": "clt", "produto_clt": "rezult_clt",
         "fogo_min": 60, "empresa": "clt-rezult", "projeto_uk": PROJ["uk"], "projeto_en": PROJ["en"]}
    p.update(c.get("parametros") or {})
    p.update(elementos=c.get("envolvente") or [], modelo_estrutural=mod, render_opcoes=c.get("render_opcoes"))
    return p


def _tr(lg):
    return lambda s: (s.split(" / ")[1] if lg == "en" and " / " in s else (s.split(" / ")[0] if " / " in s else s))


def pacote(caso: str, dossiers: dict, renders: list, p: dict) -> list[tuple[str, str, bytes]]:
    """→ [(rótulo, título, pdf)]: Drawings-UK / -EN e Estimate-UK / -EN."""
    import pymupdf

    from . import devis_ua as DV
    from . import especialidades as E
    from . import gros_oeuvre as G
    from . import lingua_ucrania as LU
    from . import planos_especialidades as PE
    from . import premium as PR
    from . import ucrania
    c = carregar(caso)
    if not c.get("divisoes") or not c.get("mep"):
        return []
    nv = ucrania.navantazhennya(ucrania.clima(p.get("cidade") or "kyiv"))
    emp = PR.marca(p.get("empresa") or "clt-rezult")
    proj = {"uk": p.get("projeto_uk") or PROJ["uk"], "en": p.get("projeto_en") or PROJ["en"]}
    out = []
    for lg in ("uk", "en"):
        T = (lambda en, uk, lg=lg: uk if lg == "uk" else en)
        m = copy.deepcopy({k: v for k, v in c.items() if k not in ("envolvente", "render_opcoes", "fonte", "parametros")})
        if lg == "en":                                   # eixos latinos A…E no inglês
            for g, n in zip(m["grelhas_y"], "ABCDEFGHIJ"):
                g["nome"] = n
        m.update(projeto=proj[lg], local=LOC[lg], neve_kn_m2=round(nv["sm_kpa"], 2), produto_clt=p.get("produto_clt") or "rezult_clt",
                 fogo_min=p.get("fogo_min") or 60)
        if lg == "en":
            m = LU.modelo_en(m)
        ver = G.verificar(m)
        r = E.calcular(m)
        d = pymupdf.open()
        go = (dossiers.get(lg) or {}).get("go") or {}
        if go.get("planos_pdf"):
            d.insert_pdf(pymupdf.open(stream=go["planos_pdf"], filetype="pdf"))
        d.insert_pdf(pymupdf.open(stream=PE.planos(m, r, ver, None, lg), filetype="pdf"))
        nomes = [next((x for x in pg.get_text().split("\n") if re.match(r"^(GO|EL|WS|HT)-\d\d · ", x)), "—") for pg in d]
        q = r["quantidades"]
        capa = {"titulo": T("Construction drawings", "Робочі креслення"),
                "subtitulo": T(f"{proj['en']} · structure, electrical, water & drainage, heating", f"{proj['uk']} · конструкції, електрика, ВК, опалення"),
                "local": LOC[lg], "data": "", "capa_imagem": renders[0][1] if renders else None,
                "kpis": [(T("Drawings", "Аркушів"), str(len(d)), T("A1 sheets", "аркуші A1")),
                         (T("Heat loss", "Тепловтрати"), f"{r['phi_total_w'] / 1000:.1f}", T("kW at −22 °C", "кВт при −22 °C")),
                         (T("Circuits", "Груп"), str(len(r["eletricidade"]["circuitos"])), T(f"{q['tomadas']} sockets", f"{q['tomadas']} розеток")),
                         (T("UFH loops", "Контурів ТП"), str(q["circuitos_pr"]), f"{q['piso_radiante_m2']:.0f} m²")],
                "indice": [(x[:70], i + 2) for i, x in enumerate(nomes)][:28]}
        plan = PR.embelezar(d.tobytes(garbage=3, deflate=True), capa, emp, n_nota=0, tr=_tr(lg))
        out.append((f"Drawings-{lg.upper()}", capa["titulo"] + " — " + proj[lg], plan))
        dv = DV.build(m, r, PE.conectores(m), c.get("orcamento_env") or {"xps_pavimento_m2": 147})
        body = DV.pdf(dv, lg, proj[lg], LOC[lg])
        nb = len(pymupdf.open(stream=body, filetype="pdf"))
        capa2 = {"titulo": T("Cost estimate", "Кошторис"),
                 "subtitulo": T(f"{proj['en']} · detailed bill of quantities, Ukrainian prices, VAT 20 %", f"{proj['uk']} · детальна відомість обсягів, ПДВ 20 %"),
                 "local": LOC[lg], "data": "", "capa_imagem": renders[1][1] if len(renders) > 1 else (renders[0][1] if renders else None),
                 "kpis": [(T("Total incl. VAT", "Разом з ПДВ"), f"{dv['ttc'] / 1e6:.2f} M", T("UAH", "грн")),
                          (T("≈ euro", "≈ євро"), f"{dv['ttc'] / dv['eur'] / 1000:.0f} k", T("€ (NBU rate)", "€ (курс НБУ)")),
                          (T("Per m² gross", "За м²"), f"{dv['per_m2_ttc']:,.0f}".replace(",", " "), T("UAH/m² incl. VAT", "грн/м² з ПДВ")),
                          (T("Line items", "Позицій"), str(len(dv["lines"])), T(f"{len(dv['lots'])} packages", f"{len(dv['lots'])} розділів"))],
                 "indice": [((lt[1] if lg == "uk" else lt[0])[:70], "") for lt, _ in dv["lots"]]}
        est = PR.embelezar(body, capa2, emp, n_nota=nb, tr=_tr(lg))
        out.append((f"Estimate-{lg.upper()}", capa2["titulo"] + " — " + proj[lg], est))
        if lg == "en":
            p["_devis_ttc"] = dv["ttc"]
    return out

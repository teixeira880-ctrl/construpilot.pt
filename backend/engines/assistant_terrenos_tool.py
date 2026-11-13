"""Ferramentas do Assistente BTP (e da Aurora, que lhe delega) — Terrenos: PDM, RAN, REN, CAOP, cadastro, BUPi, declives.

O assistente consegue:
- analisar um terreno (gravado, desenhado, ou só um ponto/morada já geolocalizada) com as fontes oficiais;
- gravar um terreno (limite do cadastro no ponto, ou vértices dados) na página Terrenos do utilizador;
- listar os terrenos do utilizador;
- e lançar o licenciamento automático da moradia nesse terreno (licenciamento_automatico com terreno_id).
Os números vêm sempre do motor (engines.terrenos_pt); o assistente nunca os inventa.
"""
from __future__ import annotations

import asyncio
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.assistant_workspace import function

N = lambda t: {"type": [t, "null"]}  # noqa: E731

TERRENOS_TOOLS = [
    function(
        "terreno_ficha",
        "Ficha oficial de um terreno em Portugal: freguesia e DICOFRE (CAOP), classe e categoria do PDM em % da área (CRUS), "
        "RAN, REN, domínio hídrico, linhas de água e outras servidões em m² e % (SRUP da DGT), prédios do cadastro, RGG já "
        "submetidas no BUPi, declives (MDT LiDAR da DGT ou Copernicus) e alertas. Usar sempre que perguntarem «posso construir "
        "aqui?», pelo PDM, RAN, REN, condicionantes de um terreno, ou antes de um licenciamento. Dar terreno_id (terreno gravado) "
        "OU lat/lon (usa o limite do cadastro nesse ponto, senão o da RGG do BUPi; se não houver nenhum, um quadrado com area_m2, por omissão 500 m²).",
        {"terreno_id": N("string"), "lat": N("number"), "lon": N("number"), "area_m2": N("number")},
    ),
    function(
        "terreno_gravar",
        "Grava um terreno na página Terrenos do utilizador: com anel_latlon (vértices [[lat, lon], …] por ordem) ou com lat/lon "
        "(usa o limite oficial do cadastro nesse ponto, senão o da RGG do BUPi). Devolve terreno_id, área e perímetro medidos em PT-TM06.",
        {"nome": N("string"), "lat": N("number"), "lon": N("number"),
         "anel_latlon": {"type": ["array", "null"], "items": {"type": "array", "items": {"type": "number"}}},
         "artigo_matricial": N("string")},
    ),
    function("terrenos_listar", "Lista os terrenos gravados pelo utilizador (id, nome, área, freguesia, alertas críticos).", {}),
]
TERRENOS_TOOL_NAMES = {t["name"] for t in TERRENOS_TOOLS}

TERRENOS_INSTRUCTIONS = (
    "\nTERRENOS (PDM, RAN, REN, CAOP/DICOFRE, cadastro, BUPi, declives): para «posso construir neste terreno?», «está em RAN/"
    "REN?», «qual é o PDM?», condicionantes ou ficha de um terreno, chama terreno_ficha (com terreno_id se o terreno estiver "
    "gravado, senão com lat/lon). Apresenta: freguesia + DICOFRE, PDM em %, RAN/REN/domínio hídrico em m² e %, RGG do BUPi, "
    "declive e os alertas, com a fonte. Um tema «por confirmar» NÃO é «sem restrições»: diz que o serviço oficial não respondeu "
    "e que é preciso refazer. Para guardar um terreno usa terreno_gravar; para os terrenos do utilizador terrenos_listar. "
    "Para construir uma moradia num terreno gravado chama licenciamento_automatico com terreno_id (a morada passa a ser "
    "opcional). Páginas: /terrenos (mapa OrtoSat 2023 + RGG do BUPi, desenho, GPS, KML para o BUPi), /mdt (MDT LiDAR, curvas, "
    "linhas de água, 3D) e /maquete-3d (maquete 3D do distrito de Braga com PDM municipal). Lembra sempre que a ficha é "
    "indicativa e não substitui a RGG no BUPi, a certidão do PDM nem o levantamento topográfico.\n"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _quadrado(lat: float, lon: float, area_m2: float) -> List[List[float]]:
    from engines.terrenos_pt import geometria as GM
    x, y = GM.tm06(lat, lon)
    h = math.sqrt(max(50.0, min(area_m2, 200_000.0))) / 2
    return [list(GM.tm06_inv(x + dx, y + dy)) for dx, dy in ((-h, -h), (h, -h), (h, h), (-h, h))]


async def _anel_no_ponto(lat: float, lon: float, area_m2: Optional[float]) -> Dict[str, Any]:
    from engines.urbanismo_pt.auto import geo as G
    try:
        cad = await asyncio.wait_for(G.cadastro(lat, lon), timeout=40)
    except asyncio.TimeoutError:
        cad = {"ok": False}
    if cad.get("ok") and len((cad.get("data") or {}).get("anel_lonlat") or []) >= 4:
        return {"anel": [[p[1], p[0]] for p in cad["data"]["anel_lonlat"]], "origem": "cadastro",
                "nota": "Limite do prédio da Carta Cadastral (DGT)."}
    try:
        from engines.terrenos_pt import rgg_limite as RL
        rl = await asyncio.wait_for(RL.limite_no_ponto(lat, lon), timeout=30)
    except Exception:  # noqa: BLE001
        rl = {"ok": False}
    if rl.get("ok"):
        return {"anel": rl["data"]["anel_latlon"], "origem": "rgg",
                "nota": "Limite da RGG do BUPi (declarado pelo proprietário, não é cadastro)." + (" " + rl["nota"] if rl.get("nota") else "")}
    return {"anel": _quadrado(lat, lon, area_m2 or 500.0), "origem": "hipotese",
            "nota": f"Sem cadastro geométrico neste ponto: analisado um quadrado de {round(area_m2 or 500)} m² centrado no ponto. "
                    "Desenhe o terreno em /terrenos para a análise exata."}


def resumo(a: Dict[str, Any]) -> Dict[str, Any]:
    """Resumo curto da análise para o modelo (sem geometrias pesadas)."""
    g = a["geometria"]
    d = lambda k: (a.get(k) or {}).get("data") or {}  # noqa: E731
    caop, cad, rgg, pdm, srv, dcl = d("caop"), d("cadastro"), d("bupi"), d("pdm"), d("servidoes"), d("declives")
    fx = lambda e: {"tema": e["titulo"], "tipo": e["tipo"], "area_m2": e["area_afetada_m2"], "pct": round(e["fracao"] * 100, 1),  # noqa: E731
                    "distancia_m": e["distancia_m"]}
    return {
        "area_m2": g["area_m2"], "perimetro_m": g["perimetro_m"], "centroide_latlon": g["centroide"],
        "estado_fontes": a["estado"],
        "freguesias": [{k: f.get(k) for k in ("freguesia", "concelho", "distrito", "dicofre")} | {"pct": round(f["fracao"] * 100, 1)}
                       for f in caop.get("freguesias", [])],
        "pdm": [{"solo": c["solo"], "classe": c.get("classe"), "categoria": c.get("categoria"), "pct": round(c["fracao"] * 100, 1)}
                for c in pdm.get("classes", [])],
        "ran": [fx(e) for e in srv.get("ran", [])], "ren": [fx(e) for e in srv.get("ren", [])],
        "recursos_hidricos": [fx(e) for e in srv.get("hidricos", [])],
        "outras_servidoes": [fx(e) for e in srv.get("afeta", []) if e["tipo"] not in ("RAN", "REN", "recursos_hidricos")][:8],
        "servidoes_por_confirmar": [e["titulo"] for e in srv.get("por_confirmar", [])][:10],
        "cadastro": ({"melhor": {k: (cad.get("melhor_correspondencia") or {}).get(k) for k in ("referencia", "area_predio_m2", "iou")}}
                     if cad.get("melhor_correspondencia") else {"predios_cruzados": len(cad.get("predios", []))}) if cad else None,
        "bupi_rgg": [{"id": r["id"], "pct_amostras": round(r["fracao_amostras"] * 100)} for r in rgg.get("rgg", [])] if rgg else None,
        "declives": ({k: dcl.get(k) for k in ("declive_medio_pct", "declive_max_pct", "classe", "desnivel_m", "exposicao",
                                              "com_desnivel", "tipo_modelo", "resolucao_m")}
                     | {"fonte": (a.get("declives") or {}).get("fonte")}) if dcl else None,
        "alertas": a["alertas"],
        "aviso_legal": a["aviso_legal"],
    }


async def run_terrenos_tool(name: str, args: Dict[str, Any], user: Dict[str, Any], db) -> Dict[str, Any]:
    from engines.terrenos_pt import analise as A
    from engines.terrenos_pt import geometria as GM
    args = {k: v for k, v in (args or {}).items() if v is not None}
    uid = user["user_id"]
    try:
        if name == "terrenos_listar":
            cur = db.terrenos.find({"user_id": uid}, {"_id": 0, "terreno_id": 1, "nome": 1, "area_m2": 1, "analise.caop": 1,
                                                       "analise.alertas": 1, "atualizado": 1}).sort("atualizado", -1).limit(50)
            out = []
            async for t in cur:
                cp = (((t.get("analise") or {}).get("caop") or {}).get("data") or {}).get("principal") or {}
                out.append({"terreno_id": t["terreno_id"], "nome": t.get("nome"), "area_m2": t.get("area_m2"),
                            "freguesia": cp.get("freguesia"), "concelho": cp.get("concelho"),
                            "alertas_criticos": sum(1 for x in (t.get("analise") or {}).get("alertas", []) if x.get("nivel") == "critico")})
            return {"ok": True, "terrenos": out, "pagina": "/terrenos"}

        if name == "terreno_gravar":
            origem, nota = "desenho", None
            anel = args.get("anel_latlon")
            if not anel:
                if "lat" not in args or "lon" not in args:
                    return {"ok": False, "error": "Indique os vértices (anel_latlon) ou um ponto (lat, lon)."}
                r = await _anel_no_ponto(float(args["lat"]), float(args["lon"]), None)
                if r["origem"] not in ("cadastro", "rgg"):
                    return {"ok": False, "error": "Não há cadastro geométrico nem RGG do BUPi neste ponto: desenhe o terreno em /terrenos.",
                            "pagina": "/terrenos"}
                anel, origem, nota = r["anel"], r["origem"], r["nota"]
            m = GM.medir(anel)
            now = _now()
            doc = {"terreno_id": uuid.uuid4().hex[:16], "user_id": uid, "nome": (args.get("nome") or "").strip()[:120] or "Terreno",
                   "origem": origem, "notas": "", "artigo_matricial": (args.get("artigo_matricial") or "").strip()[:60],
                   "anel_latlon": m["anel_latlon"], "area_m2": m["area_m2"], "perimetro_m": m["perimetro_m"],
                   "centroide": m["centroide"], "geometria": m, "analise": None, "analisado_em": None, "criado": now, "atualizado": now}
            await db.terrenos.insert_one(dict(doc))
            return {"ok": True, "terreno_id": doc["terreno_id"], "nome": doc["nome"], "area_m2": m["area_m2"],
                    "perimetro_m": m["perimetro_m"], "origem": origem, "nota": nota, "pagina": "/terrenos"}

        if name == "terreno_ficha":
            tid, nota, origem = args.get("terreno_id"), None, None
            if tid:
                t = await db.terrenos.find_one({"terreno_id": str(tid), "user_id": uid}, {"_id": 0, "anel_latlon": 1})
                if not t:
                    return {"ok": False, "error": "Terreno não encontrado."}
                anel, origem = t["anel_latlon"], "terreno_gravado"
            elif "lat" in args and "lon" in args:
                r = await _anel_no_ponto(float(args["lat"]), float(args["lon"]), args.get("area_m2"))
                anel, nota, origem = r["anel"], r["nota"], r["origem"]
            else:
                return {"ok": False, "error": "Indique terreno_id ou lat/lon."}
            res = await asyncio.wait_for(A.analisar(anel, prazo_s=80), timeout=110)
            if tid:
                now = _now()
                await db.terrenos.update_one({"terreno_id": str(tid), "user_id": uid},
                                             {"$set": {"analise": res, "analisado_em": now, "atualizado": now}})
            return {"ok": True, "origem_limite": origem, "nota_limite": nota, "terreno_id": tid, **resumo(res),
                    "paginas": {"terrenos": "/terrenos", "mdt": "/mdt", "maquete_3d": "/maquete-3d"}}
    except GM.GeometriaInvalida as e:
        return {"ok": False, "error": str(e)}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Os serviços oficiais (DGT/BUPi) estão lentos; tente de novo dentro de momentos."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(getattr(e, "detail", e))[:300]}
    return {"ok": False, "error": "tool_desconhecida"}

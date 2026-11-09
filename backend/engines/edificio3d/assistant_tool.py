"""Ferramentas do Assistente BTP (e da Aurora, que usa o Assistente) — Edifício 3D georreferenciado.

Com um simples prompt («gera uma moradia contemporânea de 2 pisos em 41.56, -8.40 com a fachada a sul»),
o assistente lança o motor Blender (+ ArcGIS Pro se houver posto), acompanha o trabalho e pede o
acabamento fotorrealista do ConstruPilot sobre os renders Blender.
"""
from __future__ import annotations

from typing import Any, Dict

from engines.assistant_workspace import function
from engines.edificio3d import servico as S

N = {"type": ["number", "null"]}
TXT = {"type": ["string", "null"]}

TOOLS = [
    function(
        "edificio3d_gerar",
        "Gera um edifício 3D REAL georreferenciado: o Blender constrói o modelo (paredes com vãos, caixilharia, "
        "cobertura de duas águas, beirais), exporta o GLB e produz renders Cycles das fachadas, vista aérea e antes/depois; "
        "opcionalmente o ArcGIS Pro implanta-o no terreno. Usar quando pedirem um edifício/casa/moradia em 3D, renders, "
        "fachadas ou implantação num local (coordenadas ou morada). Parâmetros nulos = valores por omissão "
        "(12 x 9 m, 2 pisos de 3 m, telhado 30°, beiral 0,6 m, fachada a sul).",
        {"nome": TXT, "morada": TXT, "latitude": N, "longitude": N, "altitude_m": N,
         "azimute_fachada_graus": N, "largura_m": N, "profundidade_m": N, "pisos": {"type": ["integer", "null"]},
         "pe_direito_m": N, "inclinacao_telhado_graus": N, "beiral_m": N,
         "usar_arcgis": {"type": ["boolean", "null"]},
         "qualidade": {"type": ["string", "null"], "enum": ["rapida", "normal", "alta", None]}},
    ),
    function(
        "edificio3d_estado",
        "Estado de um projeto Edifício 3D (etapas, renders disponíveis, GLB, ArcGIS, acabamentos fotorrealistas). "
        "Se job_id for nulo, devolve os projetos mais recentes da conta. Não ficar em ciclo: dar a ligação /edificio-3d/<id>.",
        {"job_id": TXT},
    ),
    function(
        "edificio3d_fotorrealista",
        "Acabamento fotorrealista (motor de imagem ConstruPilot) SOBRE os renders Blender de um projeto concluído: "
        "mesma câmara e geometria, original preservado. vista = perspetiva | fachada_frente | fachada_tardoz | "
        "fachada_esquerda | fachada_direita | aerea_telhado | aerea_envolvente | todas.",
        {"job_id": {"type": "string"}, "vista": {"type": "string"}, "ambiente": TXT},
    ),
]
TOOL_NAMES = {t["name"] for t in TOOLS}
STATUS = {"edificio3d_gerar": "A lançar o Blender: modelo 3D, materiais e renders…",
          "edificio3d_estado": "A verificar o projeto 3D…",
          "edificio3d_fotorrealista": "A aplicar o acabamento fotorrealista sobre o render Blender…"}
INSTRUCTIONS = (
    "\nEDIFÍCIO 3D GEORREFERENCIADO (Blender + ArcGIS Pro): quando pedirem um edifício, casa ou moradia em 3D, renders, "
    "fachadas, vista aérea, antes/depois ou implantação num local, chama edificio3d_gerar IMEDIATAMENTE com o que já "
    "souberes (coordenadas ou morada, dimensões, pisos, orientação); não perguntes o que tem valor por omissão. "
    "O trabalho corre em segundo plano (minutos): dá a ligação /edificio-3d/<job_id> e usa edificio3d_estado para ver o "
    "progresso. Quando estiver concluído e pedirem imagens mais realistas/fotográficas, usa edificio3d_fotorrealista "
    "(vista concreta ou «todas»). Diz sempre que os renders e o modelo são produzidos pelo Blender (e ArcGIS Pro, se pedido) "
    "e que o acabamento fotorrealista é aplicado por cima do render Blender, que fica como referência técnica. "
    "Nunca inventes números de geometria: usa só os devolvidos.\n"
)
VISTAS = ["perspetiva", "fachada_frente", "fachada_tardoz", "fachada_esquerda", "fachada_direita",
          "aerea_telhado", "aerea_envolvente"]


def _resumo(j: Dict[str, Any]) -> Dict[str, Any]:
    m = j.get("manifesto") or {}
    return {"job_id": j["job_id"], "nome": j.get("nome"), "estado": j.get("estado"), "modo": j.get("modo"),
            "link": f"/edificio-3d/{j['job_id']}", "etapas": [e["texto"] for e in (j.get("etapas") or [])][-6:],
            "erro": j.get("erro"), "renders": list((m.get("imagens") or {}).keys()),
            "geometria": m.get("geometria"), "dimensoes": m.get("dimensoes"),
            "arcgis": {k: (j.get("arcgis") or {}).get(k) for k in ("ok", "erro", "implantacao")} if j.get("usar_arcgis") else None,
            "fotorrealistas": j.get("fotorrealistas") or {},
            "parametros": {k: (j.get("params") or {}).get(k) for k in ("latitude", "longitude", "altitude_m", "azimute_fachada_graus",
                                                                        "largura_m", "profundidade_m", "pisos")}}


async def execute(name: str, args: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    from routes import edificio3d as R
    a = {k: v for k, v in (args or {}).items() if v is not None}
    uid = user["user_id"]
    if name == "edificio3d_gerar":
        if a.get("latitude") is None and not (a.get("morada") or "").strip():
            return {"ok": False, "error": "Indicar coordenadas (latitude/longitude) ou uma morada."}
        try:
            body = R.ProjetoIn(**a)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"Parâmetros inválidos: {e}"}
        p = body.model_dump()
        usar_arcgis = p.pop("usar_arcgis")
        p["render"] = R.QUAL[p.pop("qualidade")]
        j = await S.criar_trabalho(uid, p, usar_arcgis)
        servidor = S.blender_no_servidor() is not None
        return {"ok": True, "job_id": j["job_id"], "link": f"/edificio-3d/{j['job_id']}",
                "execucao": "Blender neste servidor" if servidor and not usar_arcgis else "posto Blender/ArcGIS Pro (fila)",
                "nota": "Trabalho em segundo plano; acompanhar com edificio3d_estado ou na ligação."}
    if name == "edificio3d_estado":
        if not a.get("job_id"):
            it = await S.db[S.COL].find({"user_id": uid}, {"_id": 0, "job_id": 1, "nome": 1, "estado": 1, "criado_em": 1}
                                        ).sort("criado_em", -1).to_list(5)
            return {"ok": True, "projetos": [{**x, "link": f"/edificio-3d/{x['job_id']}"} for x in it]}
        j = await S.db[S.COL].find_one({"job_id": a["job_id"], "user_id": uid}, {"_id": 0})
        return {"ok": True, **_resumo(j)} if j else {"ok": False, "error": "Projeto não encontrado nesta conta."}
    if name == "edificio3d_fotorrealista":
        j = await S.db[S.COL].find_one({"job_id": a.get("job_id"), "user_id": uid}, {"_id": 0, "estado": 1, "manifesto": 1})
        if not j:
            return {"ok": False, "error": "Projeto não encontrado nesta conta."}
        if j.get("estado") != "concluido":
            return {"ok": False, "error": f"O projeto ainda não está concluído (estado: {j.get('estado')})."}
        disponiveis = (j.get("manifesto") or {}).get("imagens") or {}
        vistas = [v for v in VISTAS if v in disponiveis] if a.get("vista") == "todas" else [a.get("vista")]
        feitos, falhas = {}, {}
        for v in vistas:
            try:
                r = await S.gerar_fotorrealista(a["job_id"], v, a.get("ambiente") or "")
                feitos[v] = r["ficheiro"]
            except Exception as e:  # noqa: BLE001
                falhas[v] = str(e)[:200]
        return {"ok": bool(feitos), "fotorrealistas": feitos, "falhas": falhas, "link": f"/edificio-3d/{a['job_id']}"}
    return {"ok": False, "error": "ferramenta desconhecida"}

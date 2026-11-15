"""Modelo de estudo comum aos três motores (LSF, CLT, construção tradicional): um só formato para o visualizador
com 3D, alçados, mapa de quantidades, lista de corte, planos de corte, estudo, avisos e projeto.

Cada motor tem o seu adaptador (engines/lsf/modelo.py, bim_studio/clt_modelo.py, …) que converte o resultado do
cálculo neste formato; a página «EstudoWorkbench» do frontend só conhece este formato. Geometria em milímetros,
eixo Z para cima. Nada aqui calcula: só organiza o que o motor já mediu.

    {versao, motor, titulo, subtitulo, kpi: [texto], camadas: [{id, nome, visivel}],
     solidos: [caixa | perfil], alcados: [{titulo, L, H, rects, linhas}],
     quantidades: [{capitulo, item, qtd, un, nota}], lista_corte: [{grupo, peca, comprimento, largura, espessura, n}],
     planos_corte: [{titulo, W, H, pecas: [{x, y, w, h, rotulo}], aproveitamento}],
     estudo: [[rótulo, valor]], avisos: [texto], projeto: {…}}
"""
from __future__ import annotations

VERSAO = "estudo-modelo-1"
MOTORES = ("lsf", "clt", "tradicional")


def novo(motor: str, titulo: str, subtitulo: str = "", camadas=()) -> dict:
    if motor not in MOTORES:
        raise ValueError(f"Motor desconhecido: {motor}")
    return {"versao": VERSAO, "motor": motor, "titulo": titulo, "subtitulo": subtitulo, "kpi": [],
            "camadas": [{"id": i, "nome": n, "visivel": bool(v)} for i, n, v in camadas], "solidos": [], "alcados": [], "quantidades": [],
            "lista_corte": [], "planos_corte": [], "estudo": [], "avisos": [], "projeto": {}}


def _r(v, d=1):
    return [round(float(x), d) for x in v]


def caixa(camada, cor, o, a, b, c, titulo, linhas=(), opacidade=1.0) -> dict:
    """Paralelepípedo: origem o e as três arestas a, b, c (mm). titulo e linhas aparecem ao clicar na peça."""
    return {"t": "caixa", "camada": camada, "cor": cor, "op": opacidade, "o": _r(o), "a": _r(a), "b": _r(b), "c": _r(c),
            "info": {"titulo": titulo, "linhas": [str(x) for x in linhas if x]}}


def perfil(camada, cor, o, u, v, w, sec, comprimento, titulo, linhas=()) -> dict:
    """Perfil extrudido pela sua secção real (C, U ou chapa): origem o, eixos da secção u e v, eixo do perfil w."""
    return {"t": "perfil", "camada": camada, "cor": cor, "op": 1.0, "o": _r(o), "u": _r(u, 5), "v": _r(v, 5), "w": _r(w, 5),
            "sec": {k: sec[k] for k in ("tipo", "h", "b", "c", "t") if sec.get(k) is not None}, "L": round(float(comprimento), 1),
            "info": {"titulo": titulo, "linhas": [str(x) for x in linhas if x]}}


def linha(capitulo, item, qtd, un, nota="") -> dict:
    return {"capitulo": capitulo, "item": item, "qtd": round(float(qtd), 3), "un": un, "nota": nota}


def validar(m: dict) -> list[str]:
    """Erros de formato (lista vazia = modelo válido). Usado nos testes de cada adaptador."""
    e = []
    if m.get("versao") != VERSAO or m.get("motor") not in MOTORES:
        e.append("versão ou motor inválido")
    ids = {c["id"] for c in m.get("camadas") or []}
    for i, s in enumerate(m.get("solidos") or []):
        if s.get("camada") not in ids:
            e.append(f"sólido {i}: camada «{s.get('camada')}» não declarada")
        chaves = ("o", "a", "b", "c") if s.get("t") == "caixa" else ("o", "u", "v", "w") if s.get("t") == "perfil" else None
        if not chaves or any(len(s.get(k) or ()) != 3 for k in chaves):
            e.append(f"sólido {i}: geometria incompleta")
        if not (s.get("info") or {}).get("titulo"):
            e.append(f"sólido {i}: sem título")
    for i, p in enumerate(m.get("planos_corte") or []):
        for q in p["pecas"]:
            if q["x"] < -0.5 or q["y"] < -0.5 or q["x"] + q["w"] > p["W"] + 0.5 or q["y"] + q["h"] > p["H"] + 0.5:
                e.append(f"plano de corte {i} ({p['titulo']}): peça {q.get('rotulo')} fora da chapa")
    for i, a in enumerate(m.get("alcados") or []):
        if not a.get("L") or not a.get("H"):
            e.append(f"alçado {i}: sem dimensões")
    for k in ("quantidades", "lista_corte", "estudo", "avisos"):
        if not isinstance(m.get(k), list):
            e.append(f"{k}: tem de ser uma lista")
    return e

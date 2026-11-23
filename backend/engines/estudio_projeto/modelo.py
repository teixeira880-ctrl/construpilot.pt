"""Esquema do modelo único, validação e criação a partir de um processo do piloto automático.

Unidades: metros. Referencial: x ao longo da frente do terreno, y para o tardoz, z = cota (soleira = 0).
Uma parede é o seu eixo (a → b) num piso; a espessura é a soma das camadas do tipo de parede.
Um vão pertence a uma parede: `pos_m` é a distância do ponto `a` ao centro do vão, medida no eixo.
A parede vai do pavimento acabado do piso (AS) até à face inferior da laje de cima (AI): altura = pé-direito.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

VERSAO = 1
LIM = {"pisos": 6, "paredes": 600, "vaos": 900, "tipos": 60, "camadas": 8, "rotulos": 300, "coord": 500.0}
COBERTURAS = ("plana", "uma_agua", "duas_aguas", "quatro_aguas")
TIPOS_VAO = ("porta", "janela", "portada")
VAO_BASE = {"porta": {"largura_m": 0.90, "altura_m": 2.10, "peitoril_m": 0.0},
            "janela": {"largura_m": 1.20, "altura_m": 1.20, "peitoril_m": 0.90},
            "portada": {"largura_m": 1.80, "altura_m": 2.20, "peitoril_m": 0.0}}
LADOS = ("frente", "tardoz", "esquerda", "direita")

# Tipos de parede de partida (prática corrente em habitação em Portugal). São hipóteses editáveis, não leituras.
TIPOS_BASE: Dict[str, Dict[str, Any]] = {
    "ext_30": {"nome": "Parede exterior 30 cm (tijolo 22 + ETICS)", "exterior": True, "camadas": [
        {"material": "Reboco interior", "esp_m": 0.015},
        {"material": "Alvenaria de tijolo cerâmico 22", "esp_m": 0.22},
        {"material": "Isolamento térmico pelo exterior (EPS)", "esp_m": 0.06},
        {"material": "Acabamento exterior armado", "esp_m": 0.005}]},
    "int_12": {"nome": "Parede interior 12 cm (tijolo 10 rebocado)", "exterior": False, "camadas": [
        {"material": "Reboco", "esp_m": 0.01},
        {"material": "Alvenaria de tijolo cerâmico 10", "esp_m": 0.10},
        {"material": "Reboco", "esp_m": 0.01}]},
    "int_20": {"nome": "Parede interior resistente 20 cm (betão armado)", "exterior": False, "camadas": [
        {"material": "Betão armado", "esp_m": 0.20}]},
}

_ID = re.compile(r"^[A-Za-z0-9_\-]{1,32}$")


class ErroModelo(ValueError):
    """O modelo recebido não pode ser lido (estrutura, tipos ou limites)."""


def _f(v: Any, nome: str, lo: float, hi: float, default: Optional[float] = None) -> float:
    if v is None and default is not None:
        return default
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ErroModelo(f"«{nome}» tem de ser um número.")
    if not math.isfinite(x) or x < lo - 1e-9 or x > hi + 1e-9:
        raise ErroModelo(f"«{nome}» fora dos limites ({lo} a {hi}).")
    return round(x, 4)


def _id(v: Any, nome: str) -> str:
    s = str(v or "")
    if not _ID.match(s):
        raise ErroModelo(f"Identificador inválido em «{nome}».")
    return s


def _txt(v: Any, n: int = 80) -> str:
    return re.sub(r"[\x00-\x1f<>]", " ", str(v or "")).strip()[:n]


def _pt(v: Any, nome: str) -> List[float]:
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        raise ErroModelo(f"«{nome}» tem de ser um ponto [x, y].")
    c = LIM["coord"]
    return [round(_f(v[0], nome, -c, c), 3), round(_f(v[1], nome, -c, c), 3)]


def espessura(tipo: Dict[str, Any]) -> float:
    return round(sum(c["esp_m"] for c in tipo["camadas"]), 4)


def normalizar(m: Any) -> Dict[str, Any]:
    """Devolve o modelo limpo ou levanta `ErroModelo`. Problemas geométricos (vão que não cabe, paredes soltas…)
    não são erro aqui: aparecem em `derivar(...)["erros"]` para o editor os mostrar sem bloquear o desenho."""
    if not isinstance(m, dict):
        raise ErroModelo("Modelo em falta.")
    pisos_in = m.get("pisos")
    if not isinstance(pisos_in, list) or not 1 <= len(pisos_in) <= LIM["pisos"]:
        raise ErroModelo(f"O modelo precisa de 1 a {LIM['pisos']} pisos.")
    pisos, ids = [], set()
    for k, p in enumerate(pisos_in):
        if not isinstance(p, dict):
            raise ErroModelo("Piso inválido.")
        pid = _id(p.get("id") or f"p{k}", "piso")
        if pid in ids:
            raise ErroModelo("Pisos com o mesmo identificador.")
        ids.add(pid)
        pisos.append({"id": pid, "nome": _txt(p.get("nome")) or ("Rés-do-chão" if k == 0 else f"{k}.º andar"),
                      "pe_direito_m": _f(p.get("pe_direito_m"), "pé-direito", 2.0, 6.0, 2.70),
                      "laje_m": _f(p.get("laje_m"), "espessura da laje", 0.08, 1.0, 0.25)})

    tipos: Dict[str, Dict[str, Any]] = {}
    tin = m.get("tipos_parede") or {}
    if not isinstance(tin, dict) or len(tin) > LIM["tipos"]:
        raise ErroModelo("Tipos de parede inválidos.")
    for tid, t in {**TIPOS_BASE, **tin}.items():
        tid = _id(tid, "tipo de parede")
        cam = (t or {}).get("camadas") if isinstance(t, dict) else None
        if not isinstance(cam, list) or not 1 <= len(cam) <= LIM["camadas"]:
            raise ErroModelo(f"O tipo de parede «{tid}» precisa de 1 a {LIM['camadas']} camadas.")
        camadas = [{"material": _txt((c or {}).get("material"), 60) or "Camada",
                    "esp_m": _f((c or {}).get("esp_m"), "espessura da camada", 0.0001, 1.0)} for c in cam]
        tipos[tid] = {"nome": _txt(t.get("nome")) or tid, "exterior": bool(t.get("exterior")), "camadas": camadas}
        if not 0.03 <= espessura(tipos[tid]) <= 1.5:
            raise ErroModelo(f"A espessura total do tipo «{tid}» tem de estar entre 3 cm e 1,5 m.")

    paredes_in = m.get("paredes") or []
    if not isinstance(paredes_in, list) or len(paredes_in) > LIM["paredes"]:
        raise ErroModelo(f"Máximo de {LIM['paredes']} paredes.")
    paredes, wids = [], set()
    for w in paredes_in:
        if not isinstance(w, dict):
            raise ErroModelo("Parede inválida.")
        wid = _id(w.get("id"), "parede")
        if wid in wids:
            raise ErroModelo("Paredes com o mesmo identificador.")
        wids.add(wid)
        piso = str(w.get("piso") or "")
        if piso not in ids:
            raise ErroModelo(f"A parede «{wid}» refere um piso que não existe.")
        tipo = str(w.get("tipo") or "")
        if tipo not in tipos:
            raise ErroModelo(f"A parede «{wid}» refere um tipo de parede que não existe.")
        paredes.append({"id": wid, "piso": piso, "a": _pt(w.get("a"), "parede.a"), "b": _pt(w.get("b"), "parede.b"), "tipo": tipo})

    vaos_in = m.get("vaos") or []
    if not isinstance(vaos_in, list) or len(vaos_in) > LIM["vaos"]:
        raise ErroModelo(f"Máximo de {LIM['vaos']} vãos.")
    vaos, vids = [], set()
    for v in vaos_in:
        if not isinstance(v, dict):
            raise ErroModelo("Vão inválido.")
        vid = _id(v.get("id"), "vão")
        if vid in vids:
            raise ErroModelo("Vãos com o mesmo identificador.")
        vids.add(vid)
        if str(v.get("parede") or "") not in wids:
            raise ErroModelo(f"O vão «{vid}» refere uma parede que não existe.")
        tipo = v.get("tipo") if v.get("tipo") in TIPOS_VAO else "janela"
        base = VAO_BASE[tipo]
        vaos.append({"id": vid, "parede": str(v["parede"]), "tipo": tipo,
                     "pos_m": _f(v.get("pos_m"), "posição do vão", 0.0, 1000.0),
                     "largura_m": _f(v.get("largura_m"), "largura do vão", 0.3, 12.0, base["largura_m"]),
                     "altura_m": _f(v.get("altura_m"), "altura do vão", 0.3, 5.0, base["altura_m"]),
                     "peitoril_m": _f(v.get("peitoril_m"), "peitoril", 0.0, 4.0, base["peitoril_m"]),
                     "lado": -1 if v.get("lado") == -1 else 1, "dobradica": "b" if v.get("dobradica") == "b" else "a"})

    c = m.get("cobertura") if isinstance(m.get("cobertura"), dict) else {}
    cobertura = {"tipo": c.get("tipo") if c.get("tipo") in COBERTURAS else "duas_aguas",
                 "inclinacao_graus": _f(c.get("inclinacao_graus"), "inclinação da cobertura", 3.0, 60.0, 22.0),
                 "beiral_m": _f(c.get("beiral_m"), "beiral", 0.0, 1.5, 0.5),
                 "laje_m": _f(c.get("laje_m"), "laje de cobertura", 0.08, 1.0, 0.25),
                 "cumeeira": c.get("cumeeira") if c.get("cumeeira") in ("auto", "x", "y") else "auto",
                 "lado_baixo": c.get("lado_baixo") if c.get("lado_baixo") in LADOS else "frente"}

    rot_in = m.get("rotulos") or []
    if not isinstance(rot_in, list) or len(rot_in) > LIM["rotulos"]:
        raise ErroModelo("Rótulos inválidos.")
    rotulos = []
    for r in rot_in:
        if isinstance(r, dict) and str(r.get("piso") or "") in ids and _txt(r.get("nome"), 40):
            p = _pt([r.get("x"), r.get("y")], "rótulo")
            rotulos.append({"piso": str(r["piso"]), "x": p[0], "y": p[1], "nome": _txt(r.get("nome"), 40)})

    mat = m.get("materiais") if isinstance(m.get("materiais"), dict) else {}
    return {"versao": VERSAO, "pisos": pisos, "tipos_parede": tipos, "paredes": paredes, "vaos": vaos,
            "cobertura": cobertura, "rotulos": rotulos,
            "laje_terrea_m": _f(m.get("laje_terrea_m"), "laje térrea", 0.08, 1.0, 0.20),
            "materiais": {k: _txt(mat.get(k), 40) for k in ("fachada", "cobertura", "caixilharia", "pavimento", "parede_interior", "teto")
                          if mat.get(k)},
            "origem": _txt(m.get("origem"), 40) or "manual"}


def modelo_vazio() -> Dict[str, Any]:
    return normalizar({"pisos": [{"id": "p0"}], "paredes": [], "vaos": []})


# ---------------------------------------------------------------- a partir do processo do piloto automático
def _fundir(segs: List[tuple]) -> List[tuple]:
    """Funde segmentos colineares sobrepostos ou contíguos: [(c, t0, t1)] → [(c, t0, t1)]."""
    out: List[tuple] = []
    for c, t0, t1 in sorted((round(c, 3), min(a, b), max(a, b)) for c, a, b in segs):
        if out and abs(out[-1][0] - c) < 1e-6 and t0 <= out[-1][2] + 1e-6:
            out[-1] = (c, out[-1][1], max(out[-1][2], t1))
        else:
            out.append((c, t0, t1))
    return out


def de_processo(d: Dict[str, Any]) -> Dict[str, Any]:
    """Modelo inicial a partir do processo (mesmas medidas da implantação, plantas e vãos). Devolve
    {"modelo", "avisos"}; o que o processo não tem (portas interiores, escada, anexos) fica em aviso, não é inventado."""
    from engines.urbanismo_pt import volumes as V
    a = d.get("auto") or {}
    plan = a.get("plantas") or {}
    if not plan.get("pisos") or not plan.get("casa_rect"):
        raise ErroModelo("O processo ainda não tem plantas para abrir no Estúdio.")
    vol = d.get("volume") or {}
    hh = V.heights(vol)
    x0, y0, x1, y1 = [float(v) for v in plan["casa_rect"]]
    te, ti = espessura(TIPOS_BASE["ext_30"]), espessura(TIPOS_BASE["int_12"])
    h = te / 2
    sh = float(hh["storey_h_m"])
    laje = 0.30 if sh >= 2.6 else 0.25
    pd = round(sh - laje, 3)
    pisos, paredes, vaos, rotulos, avisos = [], [], [], [], []
    for p in plan["pisos"]:
        k = int(p["piso"])
        pid = f"p{k}"
        pisos.append({"id": pid, "nome": p.get("nome"), "pe_direito_m": pd, "laje_m": laje})
        ax0, ay0, ax1, ay1 = x0 + h, y0 + h, x1 - h, y1 - h
        for lado, pa, pb in (("frente", (ax0, ay0), (ax1, ay0)), ("direita", (ax1, ay0), (ax1, ay1)),
                             ("tardoz", (ax1, ay1), (ax0, ay1)), ("esquerda", (ax0, ay1), (ax0, ay0))):
            paredes.append({"id": f"{pid}_{lado}", "piso": pid, "a": list(pa), "b": list(pb), "tipo": "ext_30"})
        vert, horiz = [], []
        for c in p["compartimentos"]:
            for xx in (c["x0"], c["x1"]):
                if x0 + 0.05 < xx < x1 - 0.05:
                    vert.append((xx, c["y0"], c["y1"]))
            for yy in (c["y0"], c["y1"]):
                if y0 + 0.05 < yy < y1 - 0.05:
                    horiz.append((yy, c["x0"], c["x1"]))
            rotulos.append({"piso": pid, "x": (c["x0"] + c["x1"]) / 2, "y": (c["y0"] + c["y1"]) / 2, "nome": c["nome"]})
        n = 0
        for xx, t0, t1 in _fundir(vert):
            n += 1
            paredes.append({"id": f"{pid}_i{n}", "piso": pid, "a": [xx, max(t0, ay0)], "b": [xx, min(t1, ay1)], "tipo": "int_12"})
        for yy, t0, t1 in _fundir(horiz):
            n += 1
            paredes.append({"id": f"{pid}_i{n}", "piso": pid, "a": [max(t0, ax0), yy], "b": [min(t1, ax1), yy], "tipo": "int_12"})
    for i, o in enumerate(a.get("vaos") or []):
        k = int(o.get("piso") or 0)
        lado = o.get("fachada")
        if lado not in ("frente", "tardoz") or k >= len(pisos):
            continue
        cx, larg = (o["x0"] + o["x1"]) / 2, o["x1"] - o["x0"]
        pos = cx - (x0 + h) if lado == "frente" else (x1 - h) - cx
        tipo = {"porta": "porta", "envidracado": "portada"}.get(o.get("tipo"), "janela")
        peit = max(0.0, o["z0"] - k * sh)
        vaos.append({"id": f"v{i + 1}", "parede": f"p{k}_{lado}", "tipo": tipo, "pos_m": pos, "largura_m": larg,
                     "altura_m": min(o["z1"] - o["z0"], pd - peit), "peitoril_m": peit})
    L, W = x1 - x0, y1 - y0
    rt = hh["roof_type"]
    tipo_cob = {"plana": "plana", "uma_agua": "uma_agua", "quatro_aguas": "quatro_aguas"}.get(rt, "duas_aguas")
    incl = 22.0
    if tipo_cob != "plana" and hh["roof_h_m"] > 0.05:
        vao = (min(L, W) / 2) if tipo_cob != "uma_agua" else min(L, W)
        incl = max(3.0, min(60.0, math.degrees(math.atan2(hh["roof_h_m"], vao))))
    avisos.append("As portas interiores e a escada não existem no processo: coloque-as no Estúdio.")
    if any(p.get("annexe") for p in V.building_polygons(vol)):
        avisos.append("A garagem / anexo do processo ainda não é importada para o Estúdio.")
    modelo = normalizar({"pisos": pisos, "paredes": paredes, "vaos": vaos, "rotulos": rotulos,
                         "cobertura": {"tipo": tipo_cob, "inclinacao_graus": round(incl, 2), "beiral_m": 0.5, "laje_m": laje},
                         "materiais": a.get("materiais") or {}, "origem": "processo"})
    _ = ti
    return {"modelo": modelo, "avisos": avisos}

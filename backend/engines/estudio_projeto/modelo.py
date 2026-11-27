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
LIM = {"pisos": 6, "paredes": 600, "vaos": 900, "tipos": 60, "camadas": 8, "rotulos": 300, "escadas": 12, "objetos": 600,
       "cotas": 300, "notas": 200, "coord": 500.0}
TIPOS_ESCADA = ("reta", "l", "u")
COBERTURAS = ("plana", "uma_agua", "duas_aguas", "quatro_aguas")
TIPOS_VAO = ("porta", "janela", "portada", "portao")
VAO_BASE = {"porta": {"largura_m": 0.90, "altura_m": 2.10, "peitoril_m": 0.0},
            "janela": {"largura_m": 1.20, "altura_m": 1.20, "peitoril_m": 0.90},
            "portada": {"largura_m": 1.80, "altura_m": 2.20, "peitoril_m": 0.0},
            "portao": {"largura_m": 2.40, "altura_m": 2.10, "peitoril_m": 0.0}}
LADOS = ("frente", "tardoz", "esquerda", "direita")
ACABAMENTOS_DIVISAO = ("pavimento", "parede_interior", "teto")

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

# País do site: em França as paredes de partida são as correntes no país (ver sitio.py); em Portugal, as de cima.
from engines.estudio_projeto import sitio as _sitio  # noqa: E402

TIPOS_PT = TIPOS_BASE
TIPOS_BASE = _sitio.tipos_base(TIPOS_PT)

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
        par = {"id": wid, "piso": piso, "a": _pt(w.get("a"), "parede.a"), "b": _pt(w.get("b"), "parede.b"), "tipo": tipo}
        if w.get("fachada"):                     # acabamento exterior próprio desta parede (vazio = o da casa)
            par["fachada"] = _txt(w.get("fachada"), 40)
        paredes.append(par)

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
        if v.get("caixilharia"):                 # caixilharia própria deste vão (vazio = a da casa)
            vaos[-1]["caixilharia"] = _txt(v.get("caixilharia"), 40)
        if v.get("modelo"):                      # modelo de abertura (batente, correr, oscilobatente…)
            vaos[-1]["modelo"] = _txt(v.get("modelo"), 30)
        if v.get("protecao"):                    # proteção solar (estore, portadas…)
            vaos[-1]["protecao"] = _txt(v.get("protecao"), 30)

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
            rt = {"piso": str(r["piso"]), "x": p[0], "y": p[1], "nome": _txt(r.get("nome"), 40)}
            for k in ACABAMENTOS_DIVISAO:           # acabamentos próprios da divisão (vazio = os da casa)
                if r.get(k):
                    rt[k] = _txt(r.get(k), 40)
            rotulos.append(rt)

    esc_in = m.get("escadas") or []
    if not isinstance(esc_in, list) or len(esc_in) > LIM["escadas"]:
        raise ErroModelo(f"Máximo de {LIM['escadas']} escadas.")
    escadas, eids = [], set()
    for e in esc_in:
        if not isinstance(e, dict):
            raise ErroModelo("Escada inválida.")
        eid = _id(e.get("id"), "escada")
        if eid in eids:
            raise ErroModelo("Escadas com o mesmo identificador.")
        eids.add(eid)
        if str(e.get("piso") or "") not in ids:
            raise ErroModelo(f"A escada «{eid}» refere um piso que não existe.")
        p = _pt([e.get("x"), e.get("y")], "escada")
        escadas.append({"id": eid, "piso": str(e["piso"]), "tipo": e.get("tipo") if e.get("tipo") in TIPOS_ESCADA else "reta",
                        "x": p[0], "y": p[1], "rot": round(_f(e.get("rot"), "rotação da escada", -360.0, 720.0, 0.0) % 360.0, 2),
                        "largura_m": _f(e.get("largura_m"), "largura da escada", 0.60, 2.50, 0.90),
                        "cobertor_m": _f(e.get("cobertor_m"), "cobertor", 0.22, 0.40, 0.25),
                        "sentido": "esq" if e.get("sentido") == "esq" else "dir"})

    from engines.estudio_projeto.objetos import OBJETOS
    obj_in = m.get("objetos") or []
    if not isinstance(obj_in, list) or len(obj_in) > LIM["objetos"]:
        raise ErroModelo(f"Máximo de {LIM['objetos']} objetos.")
    objetos, oids = [], set()
    for o in obj_in:
        if not isinstance(o, dict) or o.get("tipo") not in OBJETOS or str(o.get("piso") or "") not in ids:
            raise ErroModelo("Objeto inválido (tipo ou piso desconhecido).")
        oid = _id(o.get("id"), "objeto")
        if oid in oids:
            raise ErroModelo("Objetos com o mesmo identificador.")
        oids.add(oid)
        p = _pt([o.get("x"), o.get("y")], "objeto")
        base = OBJETOS[o["tipo"]]
        objetos.append({"id": oid, "piso": str(o["piso"]), "tipo": o["tipo"], "x": p[0], "y": p[1],
                        "rot": round(_f(o.get("rot"), "rotação do objeto", -360.0, 720.0, 0.0) % 360.0, 2),
                        "largura_m": _f(o.get("largura_m"), "largura do objeto", 0.05, 40.0, base["largura_m"]),
                        "prof_m": _f(o.get("prof_m"), "profundidade do objeto", 0.05, 40.0, base["prof_m"])})

    cot_in = m.get("cotas") or []
    if not isinstance(cot_in, list) or len(cot_in) > LIM["cotas"]:
        raise ErroModelo(f"Máximo de {LIM['cotas']} cotas.")
    cotas_, cids = [], set()
    for c_ in cot_in:
        if not isinstance(c_, dict) or str(c_.get("piso") or "") not in ids:
            raise ErroModelo("Cota inválida.")
        cid = _id(c_.get("id"), "cota")
        if cid in cids:
            raise ErroModelo("Cotas com o mesmo identificador.")
        cids.add(cid)
        cotas_.append({"id": cid, "piso": str(c_["piso"]), "a": _pt(c_.get("a"), "cota.a"), "b": _pt(c_.get("b"), "cota.b"),
                       "afastamento_m": _f(c_.get("afastamento_m"), "afastamento da cota", -20.0, 20.0, 0.6)})

    not_in = m.get("notas") or []
    if not isinstance(not_in, list) or len(not_in) > LIM["notas"]:
        raise ErroModelo(f"Máximo de {LIM['notas']} notas.")
    notas, nids = [], set()
    for n_ in not_in:
        if not isinstance(n_, dict) or str(n_.get("piso") or "") not in ids or not _txt(n_.get("texto"), 120):
            raise ErroModelo("Nota inválida.")
        nid = _id(n_.get("id"), "nota")
        if nid in nids:
            raise ErroModelo("Notas com o mesmo identificador.")
        nids.add(nid)
        p = _pt([n_.get("x"), n_.get("y")], "nota")
        notas.append({"id": nid, "piso": str(n_["piso"]), "x": p[0], "y": p[1], "texto": _txt(n_.get("texto"), 120)})

    mat = dict(m.get("materiais")) if isinstance(m.get("materiais"), dict) else {}
    # revestimento coerente com a forma da cobertura: telha numa cobertura plana (ou seixo num telhado inclinado)
    # dava medições, desenhos e renders impossíveis
    _so_inclinado = ("telha", "ardosia", "xisto", "shingle", "colmo", "sandwich_telha", "fibrocimento", "madeira_ripas")
    cob_mat = str(mat.get("cobertura") or "")
    if (cobertura or {}).get("tipo") == "plana":
        if not cob_mat or cob_mat.startswith(_so_inclinado):   # telhas, ardósia… não existem numa cobertura plana
            mat["cobertura"] = "plana_seixo"
    elif cob_mat.startswith("plana_"):
        mat["cobertura"] = "telha_ceramica"
    return {"versao": VERSAO, "pisos": pisos, "tipos_parede": tipos, "paredes": paredes, "vaos": vaos,
            "cobertura": cobertura, "rotulos": rotulos, "escadas": escadas,
            "objetos": objetos, "cotas": cotas_, "notas": notas,
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
    escadas, sem_escada = [], False
    n_pisos = len(plan["pisos"])
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
            if k + 1 < n_pisos and str(c["nome"]).lower().startswith("escada"):
                # escada proposta dentro do compartimento «Escada» do processo (entre faces das paredes)
                from engines.estudio_projeto.escadas import propor
                faces = (max(c["x0"], x0 + te - ti / 2) + ti / 2, max(c["y0"], y0 + te - ti / 2) + ti / 2,
                         min(c["x1"], x1 - te + ti / 2) - ti / 2, min(c["y1"], y1 - te + ti / 2) - ti / 2)
                pr = propor(faces, sh, folga=0.02)
                if pr:
                    escadas.append({"id": f"e{k + 1}", "piso": pid, **pr})
                else:
                    sem_escada = True
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
    avisos.append("As portas interiores não existem no processo: coloque-as no Estúdio.")
    if escadas:
        avisos.append("Escada proposta no compartimento «Escada» do processo: confirme o tipo e a posição.")
    if sem_escada or (n_pisos > 1 and not escadas):
        avisos.append("Não coube uma escada regulamentar no compartimento «Escada» do processo: coloque-a no Estúdio.")
    # garagem / anexos do processo: paredes no rés-do-chão (mesma implantação); o lado encostado à casa não é duplicado
    for n_an, pol in enumerate([p for p in V.building_polygons(vol) if p.get("annexe")], 1):
        xs, ys = [q[0] for q in pol["pts"]], [q[1] for q in pol["pts"]]
        if len(pol["pts"]) != 4:
            avisos.append(f"O anexo «{pol.get('name')}» não é retangular e não foi importado.")
            continue
        gx0, gy0, gx1, gy1 = min(xs), min(ys), max(xs), max(ys)
        toca = {"esq": abs(gx0 - x1) < 0.06 and gy0 < y1 and gy1 > y0, "dir": abs(gx1 - x0) < 0.06 and gy0 < y1 and gy1 > y0,
                "frente": abs(gy0 - y1) < 0.06 and gx0 < x1 and gx1 > x0, "tardoz": abs(gy1 - y0) < 0.06 and gx0 < x1 and gx1 > x0}
        ex0 = (x1 - h) if toca["esq"] else gx0 + h          # onde encosta, as paredes vão até ao eixo da parede da casa
        ex1 = (x0 + h) if toca["dir"] else gx1 - h
        ey0 = (y1 - h) if toca["frente"] else gy0 + h
        ey1 = (y0 + h) if toca["tardoz"] else gy1 - h
        lados = (("frente", (ex0, ey0), (ex1, ey0)), ("dir", (ex1, ey0), (ex1, ey1)), ("tardoz", (ex1, ey1), (ex0, ey1)), ("esq", (ex0, ey1), (ex0, ey0)))
        for lado, pa, pb in lados:
            if not toca[lado]:
                paredes.append({"id": f"an{n_an}_{lado}", "piso": "p0", "a": list(pa), "b": list(pb), "tipo": "ext_30"})
        nome = str(pol.get("name") or "Anexo")
        rotulos.append({"piso": "p0", "x": (gx0 + gx1) / 2, "y": (gy0 + gy1) / 2, "nome": nome})
        if "garag" in nome.lower() and not toca["frente"] and (ex1 - ex0) >= 3.0:
            larg = min(gx1 - gx0 - 0.9, ex1 - ex0 - 0.6)       # como no processo: 0,45 m a cada lado do portão
            vaos.append({"id": f"pg{n_an}", "parede": f"an{n_an}_frente", "tipo": "portao", "pos_m": (ex1 - ex0) / 2,
                         "largura_m": larg, "altura_m": min(2.40, pd - 0.05), "peitoril_m": 0.0})
        if pol.get("h_m") and abs(float(pol["h_m"]) - sh) > 0.10:
            avisos.append(f"«{nome}»: no processo tem {float(pol['h_m']):.2f} m de altura; no Estúdio fica com a altura do rés-do-chão ({sh:.2f} m).")
    modelo = normalizar({"pisos": pisos, "paredes": paredes, "vaos": vaos, "rotulos": rotulos, "escadas": escadas,
                         "cobertura": {"tipo": tipo_cob, "inclinacao_graus": round(incl, 2), "beiral_m": 0.5, "laje_m": laje},
                         "materiais": a.get("materiais") or {}, "origem": "processo"})
    _ = ti
    return {"modelo": modelo, "avisos": avisos}

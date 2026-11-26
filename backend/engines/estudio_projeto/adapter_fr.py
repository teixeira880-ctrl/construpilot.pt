"""França — modelo inicial do Estúdio a partir de um dossier d'urbanisme (equivalente a `modelo.de_processo` em Portugal).

A origem é a mesma das peças gráficas do permis de construire (`engines/urbanism/pc_plans.House`): mesma implantação
L × l, mesmos níveis e pé-direito, mesma distribuição, mesmas portas e janelas, mesma escada, mesma cobertura. O Estúdio
abre portanto com as medidas do carnet PC; a partir daí o utilizador edita, e as diferenças ficam visíveis em
«Diferenças para o processo».

Referencial: o do carnet PC — origem no canto dianteiro esquerdo do edifício, x ao longo da fachada da rua (S), y para o
jardim (N). Fachada S = «frente», N = «tardoz», O = «esquerda», E = «direita».

Nada é inventado: o que o dossier não tem, ou o que o modelo não representa (soco de 30 cm, platibanda de 20 cm),
sai em aviso.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from engines.estudio_projeto.modelo import ErroModelo, TIPOS_BASE, _fundir, espessura, normalizar

TIPOS_COM_EDIFICIO = ("maison_neuve", "extension", "garage_abri")
_COBERTURA = {"deux_pentes": "duas_aguas", "monopente": "uma_agua", "toit_plat": "plana"}
_VAO = {"porte": "porta", "fenetre": "janela", "baie": "portada"}
_NOMES = {"S.D.B.": "Salle de bains", "S.D.E.": "Salle d'eau", "DÉG.": "Dégagement", "PLAC.": "Placard", "WC": "WC"}
ALTURA_PORTA = 2.04          # porta interior corrente em França (bloc-porte de 204 cm)


def _nome(n: str) -> str:
    n = str(n or "").strip()
    return _NOMES.get(n) or (n[:1].upper() + n[1:].lower())


def materiais_do_dossier(d: Dict[str, Any], cobertura_plana: bool) -> Dict[str, str]:
    """Acabamentos do dossier (texto das peças PC) → identificadores do Estúdio. O que já foi levado do Estúdio para o
    dossier (`materiaux_studio`) tem prioridade: é a escolha explícita do utilizador."""
    from engines.estudio_projeto import materiais as MAT
    from engines.urbanism import pc_plans
    txt = pc_plans.materials({k: v for k, v in d.items() if k != "materiaux"})
    toit, fac, men = txt["toiture"].lower(), txt["facade"].lower(), txt["menuiseries"].lower()
    out = {
        "fachada": "reboco_creme" if "pierre" in fac else "reboco_branco",
        "cobertura": ("plana_seixo" if cobertura_plana else "zinco_quartzo" if "zinc" in toit else "ardosia_natural" if toit.startswith("ardoise")
                      else "telha_cinza" if "ardois" in toit else "telha_ceramica"),
        "caixilharia": ("aluminio_antracite" if "anthracite" in men else "aluminio_cinza" if "alu" in men else "madeira" if "bois" in men
                        else "pvc_branco"),
    }
    for k, v in (d.get("materiaux_studio") or {}).items():
        if k in MAT.ACABAMENTOS and any(x["id"] == v for x in MAT.ACABAMENTOS[k]):
            out[k] = v
    return out


def _paredes_interiores(pid: str, rooms: List[dict], L: float, W: float, e: float, h: float, ei: float) -> List[dict]:
    """Eixos das divisórias: a meio do intervalo (E_INT) entre duas divisões do carnet PC."""
    x0, y0, x1, y1 = e, e, L - e, W - e
    m = ei / 2
    vert: List[Tuple[float, float, float]] = []
    horiz: List[Tuple[float, float, float]] = []

    def pontas(a: float, b: float, lo: float, hi: float, eixo_lo: float, eixo_hi: float) -> Tuple[float, float]:
        # até ao eixo da parede exterior quando a divisão lá chega; senão até ao eixo da divisória perpendicular
        return (eixo_lo if abs(a - lo) < 1e-6 else a - m), (eixo_hi if abs(b - hi) < 1e-6 else b + m)

    for rr in rooms:
        rx0, ry0, rx1, ry1 = (float(v) for v in rr["r"])
        ya, yb = pontas(ry0, ry1, y0, y1, h, W - h)
        xa, xb = pontas(rx0, rx1, x0, x1, h, L - h)
        if rx0 > x0 + 1e-6 and not rr.get("open_left"):
            vert.append((rx0 - m, ya, yb))
        if rx1 < x1 - 1e-6 and not rr.get("open_right"):
            vert.append((rx1 + m, ya, yb))
        if ry0 > y0 + 1e-6:
            horiz.append((ry0 - m, xa, xb))
        if ry1 < y1 - 1e-6:
            horiz.append((ry1 + m, xa, xb))
    out, n = [], 0
    for xx, t0, t1 in _fundir(vert):
        n += 1
        out.append({"id": f"{pid}_i{n}", "piso": pid, "a": [xx, t0], "b": [xx, t1], "tipo": "int_12"})
    for yy, t0, t1 in _fundir(horiz):
        n += 1
        out.append({"id": f"{pid}_i{n}", "piso": pid, "a": [t0, yy], "b": [t1, yy], "tipo": "int_12"})
    return out


def _porta_interior(paredes: List[dict], pid: str, o: str, cx: float, cy: float) -> Tuple[str, float] | None:
    """Parede interior onde cai a porta (orientação «v» / «h», centro) e a distância do ponto `a` ao centro."""
    for w in paredes:
        if w["piso"] != pid or w["tipo"] != "int_12":
            continue
        (ax, ay), (bx, by) = w["a"], w["b"]
        if o == "v" and abs(ax - bx) < 1e-6 and abs(ax - cx) < 0.03 and min(ay, by) < cy < max(ay, by):
            return w["id"], abs(cy - ay)
        if o == "h" and abs(ay - by) < 1e-6 and abs(ay - cy) < 0.03 and min(ax, bx) < cx < max(ax, bx):
            return w["id"], abs(cx - ax)
    return None


def de_dossier(d: Dict[str, Any]) -> Dict[str, Any]:
    """Modelo inicial a partir do dossier d'urbanisme. Devolve {"modelo", "avisos"} (avisos em português, chaves estáveis,
    traduzidos à saída como os restantes textos do motor)."""
    from engines.urbanism import pc_plans as PC
    from engines.urbanism import volumes as V
    vol = d.get("volume") or {}
    if not vol or not vol.get("footprint_l_m") or not vol.get("footprint_w_m"):
        raise ErroModelo("O dossier ainda não tem volumes: defina primeiro as dimensões do edifício.")
    hs = PC.House(d)
    te = espessura(TIPOS_BASE["ext_30"])
    h = te / 2
    e, ei = PC.E_EXT, PC.E_INT
    L, W = hs.L, hs.W
    pd, laje = round(hs.hsp, 3), PC.FLOOR
    forma = str(vol.get("shape") or "rectangle").lower()
    trocado = float(vol.get("footprint_w_m") or 0) > float(vol.get("footprint_l_m") or 0)
    niveis_dossier = int(float(vol.get("levels") or 1))
    avisos: List[str] = []
    pisos, paredes, vaos, rotulos, escadas = [], [], [], [], []
    portas_sobrepostas = 0

    if forma in ("l", "t"):
        # contorno real do dossier (L ou T); a distribuição do carnet PC é desenhada para um retângulo e não é copiada
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        corpo = unary_union([Polygon(p["pts"]) for p in V.building_polygons(vol) if not p.get("annexe")])
        if corpo.geom_type != "Polygon" or corpo.is_empty:
            raise ErroModelo("O contorno do edifício do dossier não é um polígono simples.")
        mnx, mny = corpo.bounds[0], corpo.bounds[1]
        eixo = corpo.buffer(-h, join_style=2)
        if eixo.geom_type != "Polygon" or eixo.is_empty:
            raise ErroModelo("O edifício do dossier é demasiado estreito para as paredes exteriores de partida.")
        pts = [(round(x - mnx, 3), round(y - mny, 3)) for x, y in list(eixo.exterior.coords)[:-1]]
        niveis = max(1, min(niveis_dossier, 6))
        for k in range(niveis):
            pid = f"p{k}"
            pisos.append({"id": pid, "nome": "Rés-do-chão" if k == 0 else f"{k}.º andar", "pe_direito_m": pd, "laje_m": laje})
            for i, (pa, pb) in enumerate(zip(pts, pts[1:] + pts[:1]), 1):
                paredes.append({"id": f"{pid}_e{i}", "piso": pid, "a": list(pa), "b": list(pb), "tipo": "ext_30"})
        avisos.append("Volume em L ou em T: o Estúdio retoma o contorno real do dossier; a distribuição interior e os vãos "
                      "(desenhados para uma planta retangular nas peças PC) ficam por desenhar no Estúdio.")
        if niveis > 1:
            avisos.append("Escada por colocar no Estúdio.")
    else:
        niveis = hs.levels
        if niveis_dossier > niveis:
            avisos.append(f"O dossier indica {niveis_dossier} níveis; as peças PC e o Estúdio partem de {niveis}: acrescente os restantes no Estúdio.")
        for k in range(niveis):
            pid = f"p{k}"
            pisos.append({"id": pid, "nome": "Rés-do-chão" if k == 0 else f"{k}.º andar", "pe_direito_m": pd, "laje_m": laje})
            ax0, ay0, ax1, ay1 = h, h, L - h, W - h
            for lado, pa, pb in (("frente", (ax0, ay0), (ax1, ay0)), ("direita", (ax1, ay0), (ax1, ay1)),
                                 ("tardoz", (ax1, ay1), (ax0, ay1)), ("esquerda", (ax0, ay1), (ax0, ay0))):
                paredes.append({"id": f"{pid}_{lado}", "piso": pid, "a": list(pa), "b": list(pb), "tipo": "ext_30"})
            rooms = hs.rooms.get(k) or []
            paredes += _paredes_interiores(pid, rooms, L, W, e, h, ei)
            aberta = [rr for rr in rooms if rr.get("open_left") or rr.get("open_right")]
            for rr in rooms:
                rx0, ry0, rx1, ry1 = rr["r"]
                if rr.get("open_left"):
                    continue                              # espaço único com a divisão da esquerda: um só rótulo
                nome = _nome(rr["name"])
                if rr.get("open_right"):                  # « Séjour / salon / cuisine »
                    nome = " / ".join([nome] + [_nome(x["name"]).lower() for x in aberta if x is not rr])
                cx = (hs.stair[2] + rx1) / 2 if rr["name"] in ("ENTRÉE", "PALIER") else (rx0 + rx1) / 2
                rotulos.append({"piso": pid, "x": cx, "y": (ry0 + ry1) / 2, "nome": nome[:40]})
            for n, (o, cx, cy, larg, _sens) in enumerate(hs.doors.get(k) or [], 1):
                alvo = _porta_interior(paredes, pid, o, cx, cy)
                if not alvo:
                    continue
                if any(v["parede"] == alvo[0] and abs(v["pos_m"] - alvo[1]) < (v["largura_m"] + larg) / 2 + 0.02 for v in vaos):
                    portas_sobrepostas += 1               # a proposta-tipo põe duas portas no mesmo sítio: só a primeira entra
                    continue
                vaos.append({"id": f"{pid}_pi{n}", "parede": alvo[0], "tipo": "porta", "pos_m": alvo[1], "largura_m": larg,
                             "altura_m": min(ALTURA_PORTA, pd - 0.05), "peitoril_m": 0.0})
            if k + 1 < niveis:
                sx0, sy0, sx1, _sy1 = hs.stair
                escadas.append({"id": f"e{k + 1}", "piso": pid, "tipo": "reta", "x": (sx0 + sx1) / 2, "y": sy0, "rot": 0.0,
                                "largura_m": round(sx1 - sx0, 3), "cobertor_m": round(min(0.40, max(0.22, hs.stair_going)), 3), "sentido": "dir"})
        for n, (fac, pos, larg, alt, peit, tipo, k) in enumerate(hs.openings, 1):
            if k >= niveis:
                continue
            parede, pos_m = {"S": (f"p{k}_frente", pos - h), "N": (f"p{k}_tardoz", (L - h) - pos),
                             "O": (f"p{k}_esquerda", (W - h) - pos), "E": (f"p{k}_direita", pos - h)}[fac]
            peit = max(0.0, float(peit))
            vaos.append({"id": f"v{n}", "parede": parede, "tipo": _VAO.get(tipo, "janela"), "pos_m": pos_m, "largura_m": larg,
                         "altura_m": min(float(alt), pd - peit), "peitoril_m": peit})
        avisos.append("Distribuição, portas e janelas: proposta-tipo das peças PC (a adaptar pelo arquiteto), não um levantamento. "
                      "Verifique que cada divisão tem porta.")
        if portas_sobrepostas:
            avisos.append(f"{portas_sobrepostas} porta(s) interior(es) das peças PC sobrepunham-se a outra e não foram importadas: coloque-as no Estúdio.")
        if escadas:
            avisos.append("Escada retomada das peças PC (posição e largura); o número de degraus é recalculado pelo Estúdio "
                          "(espelho ≤ 18,5 cm).")

    # anexos do dossier (blocks): paredes no rés-do-chão; o lado encostado à casa não é duplicado
    x0, y0, x1, y1 = 0.0, 0.0, L, W
    ss, sf = V._num(vol.get("setback_side_m"), 3), V._num(vol.get("setback_front_m"), 5)
    blocos = [p for p in V.building_polygons(vol) if p.get("annexe")]
    if blocos and (trocado or forma in ("l", "t")):
        avisos.append("Os anexos do dossier não foram importados (implantação rodada ou em L / T): desenhe-os no Estúdio.")
        blocos = []
    for n_an, pol in enumerate(blocos, 1):
        xs, ys = [q[0] - ss for q in pol["pts"]], [q[1] - sf for q in pol["pts"]]
        gx0, gy0, gx1, gy1 = min(xs), min(ys), max(xs), max(ys)
        nome = str(pol.get("name") or "Annexe")[:40]
        if gx0 < x1 - 0.06 and gx1 > x0 + 0.06 and gy0 < y1 - 0.06 and gy1 > y0 + 0.06:
            avisos.append(f"O anexo «{nome}» sobrepõe-se à casa no dossier e não foi importado.")
            continue
        if min(gx1 - gx0, gy1 - gy0) < 2 * te + 0.3:
            avisos.append(f"O anexo «{nome}» é demasiado estreito para paredes de 30 cm e não foi importado.")
            continue
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
        rotulos.append({"piso": "p0", "x": (gx0 + gx1) / 2, "y": (gy0 + gy1) / 2, "nome": nome})
        if "garag" in nome.lower() and not toca["frente"] and (ex1 - ex0) >= 3.0:
            larg = min(gx1 - gx0 - 0.9, ex1 - ex0 - 0.6)
            vaos.append({"id": f"pg{n_an}", "parede": f"an{n_an}_frente", "tipo": "portao", "pos_m": (ex1 - ex0) / 2,
                         "largura_m": larg, "altura_m": min(2.00, pd - 0.05), "peitoril_m": 0.0})
        avisos.append(f"«{nome}»: importado com a altura do rés-do-chão ({pd + laje:.2f} m de piso a piso).")

    tipo_cob = _COBERTURA.get(hs.roof, "duas_aguas")
    incl = 22.0 if tipo_cob == "plana" else max(3.0, min(60.0, float(hs.pitch_deg)))
    avisos.append("Alturas: o Estúdio assenta a cobertura na laje do último teto e parte do pavimento acabado do rés-do-chão (±0,00). "
                  "O soco de 0,30 m acima do terreno e os 0,20 m de arase do corte PC não são modelados: as cotas de beirado e de "
                  "cumeeira do Estúdio não coincidem com as do corte PC, medidas a partir do terreno.")
    if tipo_cob == "plana":
        avisos.append("Cobertura plana: a platibanda de 0,40 m das peças PC não é modelada.")
    avisos.append("Paredes de partida: hipóteses editáveis (bloco de betão 20 + isolamento interior colado; divisórias de 10 cm). "
                  "A verificar com o estudo térmico RE2020.")
    modelo = normalizar({"pisos": pisos, "paredes": paredes, "vaos": vaos, "rotulos": rotulos, "escadas": escadas,
                         "cobertura": {"tipo": tipo_cob, "inclinacao_graus": round(incl, 2), "beiral_m": float(hs.overhang), "laje_m": laje,
                                       "cumeeira": "x", "lado_baixo": "frente"},
                         "materiais": materiais_do_dossier(d, tipo_cob == "plana"), "origem": "processo"})
    return {"modelo": modelo, "avisos": avisos}

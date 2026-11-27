"""Forma da casa e estilo, pedidos por frase: «faz a casa em L com vários recortes», «interior provençal».

Forma em L (determinística, sempre editável no Estúdio):
- o corpo principal (entrada, sala, cozinha, WC, escritório…) é gerado pelo gerador de três bandas;
- os quartos e casas de banho passam para uma ala perpendicular, ligada ao hall por uma galeria virada para o pátio
  interior do L, com os quartos na fachada exterior da ala (todas as divisões habitáveis com janela);
- a ala começa recuada em relação à fachada principal (recorte na frente) e prolonga-se para lá do tardoz (L).
O programa é lido do modelo atual (nomes e áreas das divisões, pisos, garagem, cobertura, exteriores, acabamentos):
as edições de áreas e nomes feitas no Estúdio mantêm-se.
"""
from __future__ import annotations

import copy
import math
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from engines import estudio_projeto as EP
from engines.atelier_archi import generateur as GEN
from engines.atelier_archi import programme as PROG
from engines.estudio_projeto import materiais as MAT
from engines.estudio_projeto import sitio

PAIS = sitio.PAIS
NOITE = ("suite", "sde", "dressing", "chambre", "sdb")
GALERIA = 1.35          # eixo a eixo: ~1,14 m livres entre a fachada (30 cm) e a divisória (12 cm)
PROF_ALA = 4.00         # eixo a eixo: ~3,79 m livres
NET_ALA = PROF_ALA - 0.06 - 0.15
_IGNORAR = ("hall", "corredor", "degagement", "dégagement", "galeria", "galerie", "arrumo", "placard", "escada", "escalier",
            "passagem", "passage", "rangement", "piece a affecter", "divisao a definir")


class Falha(ValueError):
    pass


def _t(fr: str, pt: str) -> str:
    return fr if PAIS == "FR" else pt


def _fold(s: Any) -> str:
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().strip()


def R(x: float) -> float:
    return round(round(x / 0.05) * 0.05, 2)


# ------------------------------------------------------------------------------------------------ programa
def programa_do_modelo(m: Dict[str, Any]) -> Dict[str, Any]:
    """O programa da casa tal como está no modelo (o que o utilizador editou no Estúdio conta)."""
    m = EP.normalizar(m)
    der = EP.derivar(m)
    ordem = {p["id"]: i for i, p in enumerate(m["pisos"])}
    pieces: List[Dict[str, Any]] = []
    garage = None
    for d in der["divisoes"]:
        nf = _fold(d["nome"])
        if any(nf.startswith(x) for x in _IGNORAR):
            continue
        cle = PROG._tipo(nf)
        if not cle or cle == "_circ":
            continue
        if cle == "_garage":
            garage = {"nom": d["nome"], "surface": d["area_m2"], "largeur": R(max(3.0, d["area_m2"] / GEN.PROF_GARAGE - 0.3))}
            continue
        niv = min(ordem.get(d["piso"], 0), 1)
        pieces.append({"cle": cle, "nom": d["nome"], "zone": PROG.PIECES.get(cle, (0, 0, 0, "jour"))[3],
                       "surface": round(float(d["area_m2"]), 1), "niveau": niv})
    if not pieces:
        raise Falha(_t("Aucune pièce reconnue dans la maquette.", "Nenhuma divisão reconhecida no modelo."))
    if not any(p["cle"] == "entree" for p in pieces):
        pieces.insert(0, {"cle": "entree", "nom": PROG.nom("entree"), "zone": "jour", "surface": 4.0, "niveau": 0})
    niveaux = 2 if any(p["niveau"] == 1 for p in pieces) else 1
    ext: Dict[str, Any] = {}
    for o in m.get("objetos") or []:
        t = o["tipo"]
        if t.startswith("piscina"):
            ext["piscina"] = (float(o.get("largura_m") or 8), float(o.get("prof_m") or 4))
            ext["piscina_medidas_dadas"] = True
            ext["transbordo"] = "infinita" in t
        elif t.startswith("terraco"):
            ext["terraco"] = True
        elif t == "pergola":
            ext["pergola"] = True
        elif t in ("mesa_exterior", "cozinha_exterior"):
            ext["refeicoes"] = True
        elif t == "relvado":
            ext["jardim"] = True
    if ext.get("pergola") or ext.get("refeicoes"):
        ext["terraco"] = True
    return {"pieces": pieces, "niveaux": niveaux, "garage": garage, "toiture": (m.get("cobertura") or {}).get("tipo") or "duas_aguas",
            "exteriores": ext, "hypotheses": [], "materiais": copy.deepcopy(m.get("materiais") or {}),
            "pe_direito": (m["pisos"][0] or {}).get("pe_direito_m")}


def _finalizar(modelo: Dict[str, Any], prog: Dict[str, Any]) -> Dict[str, Any]:
    if prog.get("materiais"):
        modelo["materiais"] = {**(modelo.get("materiais") or {}), **prog["materiais"]}
    return modelo


# ------------------------------------------------------------------------------------------------ retangular
def retangular(m: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    prog = programa_do_modelo(m)
    r = GEN.generer(prog)
    novo = EP.normalizar(_finalizar(r["modelo"], prog))
    return novo, _t("Plan refait en rectangle avec le même programme.", "Planta refeita em retângulo com o mesmo programa.")


# ------------------------------------------------------------------------------------------------ em L
def _ordem_ala(ala: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    suites = [p for p in ala if p["cle"] == "suite"]
    sde = [p for p in ala if p["cle"] == "sde"]
    dress = [p for p in ala if p["cle"] == "dressing"]
    quartos = [p for p in ala if p["cle"] == "chambre"]
    banhos = [p for p in ala if p["cle"] == "sdb"]
    seq = suites[:1] + dress[:1] + sde[:1] + suites[1:] + dress[1:] + sde[1:]
    while quartos or banhos:                     # quarto, quarto, casa de banho, quarto… (banho a servir dois quartos)
        seq += quartos[:2]
        quartos = quartos[2:]
        if banhos:
            seq.append(banhos.pop(0))
    return seq


def em_l(m: Dict[str, Any]) -> Tuple[Dict[str, Any], str, List[str]]:
    prog = programa_do_modelo(m)
    pcs = [dict(p) for p in prog["pieces"]]
    avisos: List[str] = []
    ala = [p for p in pcs if p["niveau"] == 0 and p["cle"] in NOITE]
    if not ala and prog["niveaux"] == 2:
        # casa de dois pisos sem quartos no rés-do-chão: a suite (ou o maior quarto) desce para a ala, com a sua casa de banho
        cima = [p for p in pcs if p["niveau"] == 1]
        q = sorted([p for p in cima if p["cle"] in ("suite", "chambre")], key=lambda p: (p["cle"] != "suite", -p["surface"]))
        b = [p for p in cima if p["cle"] in ("sde", "sdb")]
        if q:
            ala = q[:1] + b[:1]
            for p in ala:
                p["niveau"] = 0
            if not [p for p in pcs if p["niveau"] == 1 and p["cle"] in ("suite", "chambre")]:
                for p in pcs:
                    p["niveau"] = 0
                ala = [p for p in pcs if p["cle"] in NOITE]
                prog["niveaux"] = 1
            avisos.append(_t("Maison à étage : la suite descend dans l'aile du L (plain-pied).",
                             "Casa de dois pisos: a suite passa para a ala do L, no rés-do-chão."))
    if not ala:
        ala = [p for p in pcs if p["niveau"] == 0 and p["cle"] in ("bureau", "buanderie")]
    if not ala:
        raise Falha(_t("Pas de pièces à mettre dans l'aile du L (chambres, salles d'eau, bureau).",
                       "Não há divisões para a ala do L (quartos, casas de banho, escritório)."))
    # corpo principal equilibrado: se faltar comprimento numa das bandas («divisão a definir»), a divisão mais pequena da
    # ala volta para o corpo principal (até a ala ficar com 2 divisões)
    filler = _t("Pièce à affecter", "Divisão a definir")
    while True:
        ids = {id(p) for p in ala}
        prog_a = {**prog, "pieces": [p for p in pcs if id(p) not in ids]}
        r = GEN.generer(prog_a)
        vazio = any(rt["nome"] == filler for rt in r["modelo"]["rotulos"])
        if not vazio or len(ala) <= 2:
            break
        volta = min((p for p in ala if p["cle"] in ("chambre", "sdb", "bureau", "buanderie")), key=lambda p: p["surface"], default=None)
        if volta is None:
            break
        ala = [p for p in ala if p is not volta]
    mod = copy.deepcopy(r["modelo"])
    W, D, PA, H = r["geo"]["W"], r["geo"]["D"], r["geo"]["PA"], r["geo"]["HALL"]

    paredes, vaos, rotulos = mod["paredes"], mod["vaos"], mod["rotulos"]
    # 1) abertura na fachada lateral, no topo do hall: o hall continua pela galeria da ala
    dr = next((w for w in paredes if w["id"] == "p0_droite"), None)
    if dr is None:
        raise Falha(_t("Façade latérale introuvable.", "Fachada lateral não encontrada."))
    paredes.remove(dr)
    paredes += [{"id": "p0_droite", "piso": "p0", "a": [W, 0.0], "b": [W, PA], "tipo": dr["tipo"]},
                {"id": "p0_droite_b", "piso": "p0", "a": [W, R(PA + H)], "b": [W, D], "tipo": dr["tipo"]}]
    for v in [v for v in vaos if v["parede"] == "p0_droite"]:
        if v["pos_m"] + v["largura_m"] / 2 <= PA - 0.05:
            continue
        if v["pos_m"] - v["largura_m"] / 2 >= PA + H + 0.05:
            v["parede"], v["pos_m"] = "p0_droite_b", R(v["pos_m"] - PA - H)
        else:
            vaos.remove(v)

    # 2) ala: galeria do lado do pátio, quartos do lado de fora
    x0, xg, xf = W, R(W + GALERIA), R(W + GALERIA + PROF_ALA)
    seq = _ordem_ala(ala)
    ys = [PA]
    for p in seq:
        minimo = GEN.LARG_MIN.get(p["cle"], 1.6)
        ys.append(R(ys[-1] + max(minimo, float(p["surface"] or 0) / NET_ALA + 0.12)))
    y_fim = ys[-1]
    if y_fim < D + 2.5:                          # ala curta: prolonga-se até formar o L (a última divisão cresce)
        y_fim = ys[-1] = R(D + 2.5)
    paredes += [
        {"id": "ala_frente", "piso": "p0", "a": [x0, PA], "b": [xf, PA], "tipo": "ext_30"},
        {"id": "ala_fachada", "piso": "p0", "a": [xf, PA], "b": [xf, y_fim], "tipo": "ext_30"},
        {"id": "ala_topo", "piso": "p0", "a": [xf, y_fim], "b": [x0, y_fim], "tipo": "ext_30"},
        {"id": "ala_patio", "piso": "p0", "a": [x0, D], "b": [x0, y_fim], "tipo": "ext_30"},
        {"id": "ala_galeria", "piso": "p0", "a": [xg, PA], "b": [xg, y_fim], "tipo": "int_12"},
    ]
    for k, y in enumerate(ys[1:-1], 1):
        paredes.append({"id": f"ala_d{k}", "piso": "p0", "a": [xg, y], "b": [xf, y], "tipo": "int_12"})
    nv = [0]

    def vao(parede: str, pos: float, tipo: str, larg: float, alt: Optional[float] = None, peit: Optional[float] = None) -> None:
        nv[0] += 1
        v = {"id": f"va{nv[0]}", "parede": parede, "tipo": tipo, "pos_m": R(pos), "largura_m": round(larg, 2)}
        if alt is not None:
            v["altura_m"] = alt
        if peit is not None:
            v["peitoril_m"] = peit
        vaos.append(v)

    for p, ya, yb in zip(seq, ys, ys[1:]):
        L = yb - ya
        yc = (ya + yb) / 2
        rotulos.append({"piso": "p0", "x": R((xg + xf) / 2), "y": R(yc), "nome": p["nom"]})
        molhada = p["cle"] in ("sdb", "sde", "dressing")
        vao("ala_galeria", yc - PA, "porta", min(0.80 if molhada else 0.90, L - 0.3))
        if p["cle"] == "dressing":
            continue
        if molhada:
            vao("ala_fachada", yc - PA, "janela", min(0.60, L - 0.6), 0.60, 1.50)
        else:
            area = (L - 0.12) * NET_ALA
            larg = min(max(1.20, GEN.RATIO_VITRAGE * area / 1.25 + 0.05, 1.08 / 1.25 if PAIS == "PT" else 0), 2.40, L - 0.6)
            vao("ala_fachada", yc - PA, "janela", R(larg), 1.25, 0.95)
    # janelas da galeria para o pátio do L
    comp = y_fim - D
    n = int(comp // 3.5)
    for i in range(n):
        y = D + comp * (i + 1) / (n + 1)
        vao("ala_patio", y - D, "janela", 1.20, 1.25, 0.95)

    novo = _finalizar(mod, prog)
    try:
        novo = EP.normalizar(novo)
    except EP.ErroModelo as e:
        raise Falha(str(e)) from e
    der = EP.derivar(novo)
    if der.get("erros"):
        raise Falha(_t("La forme en L casserait la maquette : ", "A forma em L partiria o modelo: ") + der["erros"][0]["msg"])
    nomes = ", ".join(p["nom"] for p in seq)
    msg = _t(f"Maison refaite en L : aile de {y_fim - PA:.1f} m ({nomes}) desservie par une galerie sur le patio, en retrait de "
             f"{PA:.1f} m sur la façade avant.",
             f"Casa refeita em L: ala de {y_fim - PA:.1f} m ({nomes}) servida por uma galeria virada para o pátio, recuada {PA:.1f} m "
             f"em relação à fachada principal.")
    return novo, msg, avisos


# ------------------------------------------------------------------------------------------------ estilos
ESTILOS: Dict[str, Dict[str, Dict[str, str]]] = {
    "provencal": {"interior": {"pavimento": "tijoleira", "parede_interior": "pintura_creme", "teto": "teto_vigas_madeira"},
                  "exterior": {"fachada": "reboco_ocre", "cobertura": "telha_canudo", "caixilharia": "madeira_lacada_azul"},
                  "molhadas": {"parede_interior": "azulejo_cor", "pavimento": "mosaico_hidraulico"}},
    "rustico": {"interior": {"pavimento": "soalho_castanho", "parede_interior": "pedra_vista", "teto": "teto_vigas_madeira"},
                "exterior": {"fachada": "granito", "cobertura": "telha_envelhecida", "caixilharia": "madeira"},
                "molhadas": {"parede_interior": "azulejo_branco_int", "pavimento": "tijoleira"}},
    "mediterranico": {"interior": {"pavimento": "tijoleira", "parede_interior": "pintura_branca", "teto": "teto_estuque"},
                      "exterior": {"fachada": "cal_branca", "cobertura": "telha_lusa", "caixilharia": "madeira_lacada_azul"},
                      "molhadas": {"parede_interior": "azulejo_cor", "pavimento": "mosaico_hidraulico"}},
    "moderno": {"interior": {"pavimento": "gres_cinza", "parede_interior": "pintura_branca", "teto": "teto_gesso_cartonado"},
                "exterior": {"fachada": "reboco_branco", "cobertura": "plana_seixo", "caixilharia": "aluminio_antracite"},
                "molhadas": {"parede_interior": "gres_parede", "pavimento": "gres_antracite"}},
    "minimalista": {"interior": {"pavimento": "microcimento_pav", "parede_interior": "pintura_branca", "teto": "teto_gesso_cartonado"},
                    "exterior": {"fachada": "betao_branco", "cobertura": "plana_branca", "caixilharia": "aluminio_minimalista"},
                    "molhadas": {"parede_interior": "microcimento_parede", "pavimento": "microcimento_pav"}},
    "escandinavo": {"interior": {"pavimento": "soalho_pinho", "parede_interior": "pintura_branca", "teto": "teto_madeira"},
                    "exterior": {"fachada": "madeira_pintada_branca", "cobertura": "telha_preta", "caixilharia": "pvc_branco"},
                    "molhadas": {"parede_interior": "azulejo_branco_int", "pavimento": "gres_bege"}},
    "industrial": {"interior": {"pavimento": "betao_afagado", "parede_interior": "tijolo_vista_int", "teto": "teto_betao"},
                   "exterior": {"fachada": "tijolo", "cobertura": "zinco_antracite_cob",
                                "caixilharia": "aco_preto"},
                   "molhadas": {"parede_interior": "microcimento_parede", "pavimento": "betao_afagado"}},
    "classico": {"interior": {"pavimento": "parquet_espinha", "parede_interior": "estuque", "teto": "teto_estuque"},
                 "exterior": {"fachada": "reboco_creme", "cobertura": "telha_marselha", "caixilharia": "madeira_lacada_branca"},
                 "molhadas": {"parede_interior": "azulejo_branco_int", "pavimento": "marmore_pav"}},
    "contemporaneo": {"interior": {"pavimento": "soalho_carvalho", "parede_interior": "pintura_cinza_claro", "teto": "teto_gesso_cartonado"},
                      "exterior": {"fachada": "misto_madeira_reboco", "cobertura": "telha_cinza", "caixilharia": "aluminio_antracite"},
                      "molhadas": {"parede_interior": "gres_parede", "pavimento": "gres_cinza"}},
    "tradicional": {"interior": {"pavimento": "soalho_pinho", "parede_interior": "estuque", "teto": "teto_estuque"},
                    "exterior": {"fachada": "reboco_branco", "cobertura": "telha_lusa", "caixilharia": "madeira"},
                    "molhadas": {"parede_interior": "azulejo_branco_int", "pavimento": "tijoleira"}},
}
NOMES_ESTILO = {"provencal": ("provençal", "provençal"), "rustico": ("rustique", "rústico"), "mediterranico": ("méditerranéen", "mediterrânico"),
                "moderno": ("moderne", "moderno"), "minimalista": ("minimaliste", "minimalista"), "escandinavo": ("scandinave", "escandinavo"),
                "industrial": ("industriel", "industrial"), "classico": ("classique", "clássico"), "contemporaneo": ("contemporain", "contemporâneo"),
                "tradicional": ("traditionnel", "tradicional")}
RX_ESTILO = {"provencal": r"proven[cç]|provence", "rustico": r"rusti", "mediterranico": r"mediterr", "moderno": r"\bmodern",
             "minimalista": r"minimal", "escandinavo": r"escandinav|scandinav|nordi", "industrial": r"industri", "classico": r"classic|classiqu",
             "contemporaneo": r"contempor", "tradicional": r"tradici|tradition"}
_MOLHADAS = ("sdb", "sde", "wc", "buanderie")


def estilo(m: Dict[str, Any], nome: str, ambito: str = "tudo") -> Tuple[Dict[str, Any], str]:
    if nome not in ESTILOS:
        raise Falha(_t(f"Style inconnu « {nome} ».", f"Estilo desconhecido «{nome}»."))
    m = EP.normalizar(copy.deepcopy(m))
    e = ESTILOS[nome]
    mats = {}
    if ambito in ("interior", "tudo"):
        mats.update(e["interior"])
    if ambito in ("exterior", "tudo"):
        mats.update(e["exterior"])
    if (m.get("cobertura") or {}).get("tipo") == "plana" and "cobertura" in mats and not mats["cobertura"].startswith("plana"):
        mats.pop("cobertura")                    # cobertura plana: o revestimento de telhado inclinado não se aplica
    if (m.get("cobertura") or {}).get("tipo") != "plana" and mats.get("cobertura", "").startswith("plana"):
        mats["cobertura"] = "telha_cinza"
    m["materiais"] = {**(m.get("materiais") or {}), **{k: v for k, v in mats.items() if k in MAT.ACABAMENTOS}}
    if ambito in ("interior", "tudo"):           # o estilo vale para todas as divisões; as casas de banho ficam com cerâmica
        der = EP.derivar(m)
        from shapely.geometry import Point, Polygon
        for d in der["divisoes"]:
            molhada = PROG._tipo(_fold(d["nome"])) in _MOLHADAS
            pl = Polygon(d["pts"])
            rt = next((r for r in m["rotulos"] if r["piso"] == d["piso"] and pl.contains(Point(r["x"], r["y"]))), None)
            if rt is None:
                continue
            for k in ("pavimento", "parede_interior", "teto"):
                rt.pop(k, None)
            if molhada:
                rt.update(e["molhadas"])
    m = EP.normalizar(m)
    fr, pt = NOMES_ESTILO[nome]
    alvo = {"interior": _t("intérieur", "interior"), "exterior": _t("extérieur", "exterior"), "tudo": _t("intérieur et extérieur", "interior e exterior")}[ambito]
    lista = "; ".join(f"{k.replace('_', ' ')}: {MAT.acabamento(k, v)['nome']}" for k, v in mats.items() if k in MAT.ACABAMENTOS)
    return m, _t(f"Style {fr} ({alvo}) — {lista}.", f"Estilo {pt} ({alvo}) — {lista}.")

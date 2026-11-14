"""Modelos de casa por estilo, adaptados ao terreno (Estúdio de Projeto — 14/11).

Pedido do Martinho: «pedir modelos de casas (modernas, contemporâneas, moradias…) e meter a casa adaptada ao terreno».
Cada variante sai dos MESMOS motores do licenciamento automático — programa (RGEU), implantação (afastamentos, índices,
orientação solar, declive) e plantas — com a linguagem de um estilo (estilos.py: cobertura, materiais, proporção dos
vãos). Nada é copiado de projetos de terceiros: os estilos são sínteses da arquitetura portuguesa.

Opção 2 (descrição / imagem): a frase é lida pelo intérprete do pedido (tipologia, pisos, garagem, materiais, área) e
pelo detetor de estilos; uma imagem de referência é descrita por um modelo de visão só em PARÂMETROS (estilo, pisos,
telhado, fachada) — a geometria continua a sair dos motores.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from engines.urbanismo_pt.auto import estilos as E
from engines.urbanismo_pt.auto import implantacao as I
from engines.urbanismo_pt.auto import pecas_auto as PA
from engines.urbanismo_pt.auto import plantas as PL
from engines.urbanismo_pt.auto import programa as PG

FACHADA_VALIDA = {"misto_granito_madeira": "granito"}
TIPOS = {"moradia_isolada": "Moradia isolada"}          # geminada, em banda e prédios: fases seguintes


def _fachada(f: str) -> str:
    f = FACHADA_VALIDA.get(f, f)
    return f if f in PA.MATERIAIS_FACHADA else "reboco_branco"


def _tip_n(t: Any) -> int:
    try:
        return max(1, min(5, int(str(t).upper().lstrip("T"))))
    except (TypeError, ValueError):
        return 3


def combinacoes(estilo: Dict[str, Any], pedido: Dict[str, Any]) -> List[tuple]:
    """(tipologia, pisos, garagem, lugares) por ordem de preferência — o pedido primeiro, depois alternativas plausíveis."""
    t = _tip_n(pedido.get("tipologia") or 3)
    terreo = estilo["id"] in ("alentejano", "algarvio") or pedido.get("pisos") == 1
    pisos = [1] if terreo else [pedido.get("pisos") or 2, 1 if (pedido.get("pisos") or 2) == 2 else 2]
    gar = pedido.get("garagem")
    gars = [bool(gar)] if gar is not None else [True, False]
    out = []
    for np_ in pisos:
        for g in gars:
            out.append((f"T{t}", np_, g, 2 if g else 0))
    out += [(f"T{t + 1}", pisos[0], gars[0], 2 if gars[0] else 0), (f"T{max(1, t - 1)}", pisos[0], gars[0], 2 if gars[0] else 0)]
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def _terreno(d: Dict[str, Any]) -> Dict[str, Any]:
    t = (d.get("auto") or {}).get("terreno") or {}
    if not t.get("poligono_m"):
        raise ValueError("Processo sem terreno georreferenciado: os modelos adaptados precisam da morada ou do terreno.")
    return {k: t.get(k) for k in ("poligono_m", "plot_l_m", "plot_w_m", "azimutes", "area_m2")}


def _vaos_estilo(vaos: List[Dict[str, Any]], fator: float, casa_rect) -> List[Dict[str, Any]]:
    """Proporção dos vãos do estilo: reduz janelas nos estilos tradicionais, alarga envidraçados nos contemporâneos
    (sem sair da fachada)."""
    x0, _, x1, _ = casa_rect
    out = []
    for v in vaos:
        w = v["x1"] - v["x0"]
        nw = w * fator if fator < 1 else (w + min(0.6, w * (fator - 1) * 2) if v["tipo"] == "envidracado" else w)
        c = (v["x0"] + v["x1"]) / 2
        a, b = max(x0 + 0.3, c - nw / 2), min(x1 - 0.3, c + nw / 2)
        if b - a >= 0.5:
            out.append({**v, "x0": round(a, 3), "x1": round(b, 3)})
    return out


def gerar(d: Dict[str, Any], estilos: List[str], pedido: Optional[Dict[str, Any]] = None, n: int = 4) -> Dict[str, Any]:
    """Até `n` variantes que cabem no terreno, alternando estilos e programas. Cada uma com o seu porquê."""
    ter = _terreno(d)
    a = d.get("auto") or {}
    topo = a.get("topografia") if (a.get("topografia") or {}).get("ok") else None
    alv = a.get("alvos") or I.alvos({})
    pedido = {**(a.get("pedido") or {}), **(pedido or {})}
    try:
        area = float(pedido.get("area_casa_m2") or 0) or None
    except (TypeError, ValueError):
        area = None
    ids = [e for e in estilos if e in E.ESTILOS] or [E.ESTILO_PADRAO]
    variantes, falhas, tentados = [], [], set()
    # variedade: cada estilo começa num programa diferente (o pedido primeiro, depois térrea / sem garagem / +1 quarto…),
    # e as rondas seguintes percorrem o resto — assim 4 variantes não são 4 vezes a mesma casa com outra fachada
    combos = {eid: combinacoes(E.obter(eid), pedido) for eid in ids}
    ordem = []
    for r in range(max(len(c) for c in combos.values())):
        for k, eid in enumerate(ids):
            c = combos[eid]
            ordem.append((eid, c[(r + k) % len(c)]))
    # terreno apertado: se nada couber, as mesmas casas com a área reduzida (nunca abaixo do mínimo do RGEU)
    reduzidas = [(eid, c, f) for f in (0.8, 0.65) for eid in ids for c in combos[eid][:3]]
    for eid, (tip, np_, gar, lug), *fat in [(e_, c) for e_, c in ordem] + [(e_, c, f) for e_, c, f in reduzidas]:
        if len(variantes) >= n or (fat and variantes):
            break
        est = E.obter(eid)
        alvo = area
        if fat:
            base_area = area or PG.programa(tip, np_, gar, lug, escritorio=False)["area_bruta_total_m2"]
            alvo = base_area * fat[0]
        prog = PG.programa(tip, np_, gar, lug, escritorio=False, area_alvo_m2=alvo)
        if fat and prog.get("limitado_pelo_rgeu"):
            continue

        def validar(r, prog=prog):
            pl = PL.distribuir(r["volume"], prog, r["fachada_sol"], r["lado_garagem"])
            if not pl.get("ok"):
                return False, pl["motivo"]
            if pl["nao_conformes"]:
                return False, "; ".join(pl["nao_conformes"][:2])
            r["plantas"] = pl
            return True, ""
        res = I.implantar(ter, topo, prog, alv, validar=validar)
        if not res.get("ok"):
            falhas.append(f"{est['nome']} {tip} {np_} piso(s){' com garagem' if gar else ''}: {res.get('motivo')}")
            continue
        chave = (eid, round(res["volume"]["footprint_l_m"], 1), round(res["volume"]["footprint_w_m"], 1), res["n_pisos"])
        if chave in tentados:
            continue
        tentados.add(chave)
        plan = res["plantas"]
        telhado = est["cobertura"]["tipo"]
        volume = {**res["volume"], "roof_type": "plana" if telhado == "plana" else "duas_aguas"}
        vaos = _vaos_estilo(PA.vaos(plan, volume, res["fachada_sol"]), float(est.get("envidracado") or 1.0), plan["casa_rect"])
        mats = {"fachada": _fachada(est["fachada"]), "cobertura": est["cobertura"]["material"], "caixilharia": est["caixilharia"]}
        variantes.append({
            "id": f"v{len(variantes) + 1}",
            "titulo": f"{est['nome']} — {prog['tipologia']}, {res['n_pisos']} piso{'s' if res['n_pisos'] > 1 else ''}"
                      + (" com garagem" if gar else ""),
            "estilo": eid, "estilo_nome": est["nome"], "descricao": est["descricao"], "elementos": est["elementos"],
            "tipologia": prog["tipologia"], "pisos": res["n_pisos"], "garagem": bool(gar),
            "area_bruta_m2": prog["area_bruta_total_m2"],
            "area_implantacao_m2": round(res["volume"]["footprint_l_m"] * res["volume"]["footprint_w_m"], 1),
            "volume": volume, "plantas": {"pisos": plan["pisos"], "casa_rect": plan["casa_rect"]},
            "implantacao": {k: res.get(k) for k in ("fachada_sol", "lado_garagem", "cota_soleira_m", "terras", "decisoes",
                                                     "casa_rect", "garagem_rect", "declive_profundidade_pct")},
            "programa": {k: prog[k] for k in ("tipologia", "n_pisos", "area_bruta_total_m2", "minimo_area_bruta_m2", "garagem",
                                              "fonte_minimos")},
            "vaos": vaos, "materiais": mats,
            "estudio": {"telhado": telhado, **mats},
        })
    return {"variantes": variantes, "nao_couberam": falhas[:6],
            "nota": "Variantes geradas pelos motores do ConstruPilot (programa RGEU, implantação com afastamentos e índices, "
                    "plantas) com a linguagem de cada estilo — nenhuma planta de terceiros foi copiada."}


# ── Opção 2: descrição em texto / imagem de referência → parâmetros ────────────────────────────────────────────────────
def ler_descricao(texto: str) -> Dict[str, Any]:
    from engines.urbanismo_pt.auto.pipeline import interpretar_pedido
    p = interpretar_pedido(texto or "")
    p.pop("morada", None)
    p.pop("area_terreno_m2", None)
    est = E.detectar(texto or "")
    t = (texto or "").lower()
    if re.search(r"cobertura plana|telhado plano|terra[cç]o", t) and not est:
        est = "contemporaneo"
    return {"pedido": p, "estilo": est}


SISTEMA_VISAO = (
    "És arquiteto. Descreve a casa da imagem SÓ com parâmetros, em JSON estrito, sem texto à volta: "
    '{"estilo": um de ' + json.dumps(list(E.ESTILOS)) + ', "pisos": 1 ou 2, "telhado": "plana"|"duas_aguas", '
    '"fachada": um de ' + json.dumps(list(PA.MATERIAIS_FACHADA)) + ', "caixilharia": um de ' + json.dumps(list(PA.CAIXILHARIA))
    + ', "garagem": true|false|null}. Não inventes dimensões.')


async def ler_imagem(imagem_b64: str) -> Dict[str, Any]:
    """Imagem de referência → parâmetros de estilo (modelo de visão). Falha em silêncio: devolve {} e o motivo."""
    try:
        from engines import anthropic_native as AN
        if not AN.native_available():
            return {"erro": "Leitura de imagens indisponível neste servidor."}
        txt = await AN.complete(SISTEMA_VISAO, "Parâmetros desta casa:", images=[imagem_b64.split(",", 1)[-1]], max_tokens=300)
        m = re.search(r"\{.*\}", txt or "", re.S)
        j = json.loads(m.group(0)) if m else {}
    except Exception as e:  # noqa: BLE001
        return {"erro": f"Imagem não lida ({type(e).__name__})."}
    out: Dict[str, Any] = {}
    if j.get("estilo") in E.ESTILOS:
        out["estilo"] = j["estilo"]
    if j.get("pisos") in (1, 2):
        out["pisos"] = j["pisos"]
    if isinstance(j.get("garagem"), bool):
        out["garagem"] = j["garagem"]
    for k, tab in (("fachada", PA.MATERIAIS_FACHADA), ("caixilharia", PA.CAIXILHARIA)):
        if j.get(k) in tab:
            out[k] = j[k]
    if j.get("telhado") in ("plana", "duas_aguas"):
        out["telhado"] = j["telhado"]
    return out

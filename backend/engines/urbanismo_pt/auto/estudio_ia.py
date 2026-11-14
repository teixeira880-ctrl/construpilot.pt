"""Assistente IA do Estúdio de Projeto: pedido em linguagem livre → alterações VALIDADAS da casa.

O modelo só propõe alterações num formato fechado (JSON); este módulo valida cada campo (valores permitidos, limites,
casa dentro do lote com os afastamentos) e devolve só o que passou, com o que foi recusado e porquê. Nada é gravado
aqui: o Estúdio aplica (com «desfazer») e o utilizador grava — a verificação regulamentar corre na gravação.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

FACHADA = ["reboco_branco", "granito", "madeira", "xisto", "tijolo", "betao", "misto_granito_reboco", "misto_madeira_reboco"]
COBERTURA = ["telha_ceramica", "telha_preta", "zinco", "plana_seixo"]
CAIXILHARIA = ["aluminio_antracite", "aluminio_branco", "madeira", "pvc_branco"]
TELHADO = ["duas_aguas", "quatro_aguas", "uma_agua", "plana"]
FACHADAS_V = ["frente", "tardoz", "esquerda", "direita"]
TIPOS_VAO = ["janela", "envidracado", "porta"]
LIM_VOL = {"footprint_l_m": (4.0, 60.0), "footprint_w_m": (4.0, 60.0), "levels": (1, 4), "storey_h_m": (2.4, 4.5),
           "setback_front_m": (0.0, 60.0), "setback_side_m": (0.0, 60.0)}
LIM_EST = {"inclinacao_pct": (0.0, 70.0), "beiral_m": (0.0, 1.5)}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

SISTEMA = (
    "És o arquiteto do Estúdio de Projeto ConstruPilot (Portugal). O utilizador pede alterações à casa em linguagem livre. "
    "Responde SÓ com um objeto JSON, sem texto à volta, com esta forma:\n"
    '{"vol": {"footprint_l_m": número (frente da casa, m), "footprint_w_m": número (profundidade, m), "levels": inteiro 1-4, '
    '"storey_h_m": número (piso a piso), "setback_front_m": número, "setback_side_m": número},\n'
    ' "estilo": {"telhado": ' + json.dumps(TELHADO) + ', "inclinacao_pct": número, "beiral_m": número, "fachada": ' + json.dumps(FACHADA)
    + ', "cobertura": ' + json.dumps(COBERTURA) + ', "caixilharia": ' + json.dumps(CAIXILHARIA)
    + ', "cor_fachada": "#rrggbb", "cor_cobertura": "#rrggbb", "cor_caixilharia": "#rrggbb"},\n'
    ' "vaos": {"acrescentar": [{"fachada": ' + json.dumps(FACHADAS_V) + ', "piso": inteiro (0 = R/C), "tipo": ' + json.dumps(TIPOS_VAO)
    + ', "compartimento": texto, "largura_m": número, "altura_m": número, "peitoril_m": número, "posicao": "centro"|"esquerda"|"direita"}],'
    ' "remover": [índices da lista atual], "alterar": [{"indice": inteiro, "largura_m": número, "altura_m": número, "tipo": ..., "piso": ...}]},\n'
    ' "resposta": "1 a 3 frases em português de Portugal a dizer o que mudaste e porquê"}\n'
    "Regras: põe só as chaves que mudam. Mantém a casa dentro do lote (frente + 2 × afastamento lateral ≤ largura do lote; "
    "profundidade + afastamento frontal ≤ profundidade do lote). Interpreta estilos («mais moderna» = cobertura plana ou 1 água, "
    "envidraçados grandes, caixilharia antracite, reboco branco/madeira; «tradicional minhota» = granito, telha cerâmica, 2 ou 4 águas…). "
    "Uma pergunta sem pedido de alteração → só \"resposta\". Nunca inventes regras legais: a verificação do RJUE/PDM é feita ao gravar.")


def _num(x, lo, hi, inteiro=False):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v or not (lo <= v <= hi):
        return None
    return int(round(v)) if inteiro else round(v, 2)


def validar(prop: Dict[str, Any], estado: Dict[str, Any]) -> Dict[str, Any]:
    """Proposta do modelo → alterações aceites + recusadas (com motivo). Função pura (testável sem IA)."""
    vol0 = estado.get("vol") or {}
    vaos0 = estado.get("vaos") or []
    ok_vol, ok_est, recusas = {}, {}, []
    for k, v in (prop.get("vol") or {}).items():
        if k not in LIM_VOL:
            recusas.append(f"{k}: campo desconhecido")
            continue
        val = _num(v, *LIM_VOL[k], inteiro=(k == "levels"))
        if val is None:
            recusas.append(f"{k} = {v}: fora dos limites {LIM_VOL[k]}")
        else:
            ok_vol[k] = val
    # casa dentro do lote
    novo = {**vol0, **ok_vol}
    pl, pw = float(novo.get("plot_l_m") or 0), float(novo.get("plot_w_m") or 0)
    if pl and pw:
        L, W = float(novo.get("footprint_l_m") or 0), float(novo.get("footprint_w_m") or 0)
        sl, sf = float(novo.get("setback_side_m") or 0), float(novo.get("setback_front_m") or 0)
        if L + 2 * sl > pl + 1e-6 or W + sf > pw + 1e-6:
            for k in ("footprint_l_m", "footprint_w_m", "setback_front_m", "setback_side_m"):
                ok_vol.pop(k, None)
            recusas.append(f"a casa não cabe no lote ({pl:g} × {pw:g} m) com esses afastamentos — dimensões mantidas")
    for k, v in (prop.get("estilo") or {}).items():
        tab = {"telhado": TELHADO, "fachada": FACHADA, "cobertura": COBERTURA, "caixilharia": CAIXILHARIA}.get(k)
        if tab is not None:
            (ok_est.__setitem__(k, v) if v in tab else recusas.append(f"{k} = {v}: valor não disponível"))
        elif k in LIM_EST:
            val = _num(v, *LIM_EST[k])
            (ok_est.__setitem__(k, val) if val is not None else recusas.append(f"{k} = {v}: fora dos limites"))
        elif k in ("cor_fachada", "cor_cobertura", "cor_caixilharia"):
            (ok_est.__setitem__(k, v) if isinstance(v, str) and HEX.match(v) else recusas.append(f"{k} = {v}: cor inválida"))
        else:
            recusas.append(f"{k}: campo desconhecido")
    if ok_est.get("telhado") == "plana" and "cobertura" not in ok_est:
        ok_est["cobertura"] = "plana_seixo"
    pisos = int(ok_vol.get("levels") or vol0.get("levels") or 1)
    sh = float(ok_vol.get("storey_h_m") or vol0.get("storey_h_m") or 2.8)
    va = prop.get("vaos") or {}
    acrescentar = []
    for o in va.get("acrescentar") or []:
        if not isinstance(o, dict) or o.get("fachada") not in FACHADAS_V:
            recusas.append("vão sem fachada válida")
            continue
        tipo = o.get("tipo") if o.get("tipo") in TIPOS_VAO else "janela"
        piso = _num(o.get("piso", 0), 0, pisos - 1, inteiro=True)
        larg = _num(o.get("largura_m", 1.2), 0.4, 12.0)
        alt = _num(o.get("altura_m", 2.1 if tipo != "janela" else 1.4), 0.4, sh - 0.2)
        peit = 0.0 if tipo in ("porta", "envidracado") else _num(o.get("peitoril_m", 0.9), 0.0, sh - 0.6)
        if None in (piso, larg, alt, peit):
            recusas.append(f"vão na fachada {o.get('fachada')}: piso/dimensões fora dos limites")
            continue
        acrescentar.append({"fachada": o["fachada"], "piso": piso, "tipo": tipo, "compartimento": str(o.get("compartimento") or "")[:40],
                            "largura_m": larg, "altura_m": alt, "peitoril_m": peit,
                            "posicao": o.get("posicao") if o.get("posicao") in ("centro", "esquerda", "direita") else "centro"})
    remover = sorted({int(i) for i in va.get("remover") or [] if isinstance(i, (int, float)) and 0 <= int(i) < len(vaos0)})
    alterar = []
    for a in va.get("alterar") or []:
        if not isinstance(a, dict) or not isinstance(a.get("indice"), (int, float)) or not (0 <= int(a["indice"]) < len(vaos0)):
            recusas.append("alteração de vão com índice inválido")
            continue
        q = {"indice": int(a["indice"])}
        if "largura_m" in a and _num(a["largura_m"], 0.4, 12.0) is not None:
            q["largura_m"] = _num(a["largura_m"], 0.4, 12.0)
        if "altura_m" in a and _num(a["altura_m"], 0.4, sh - 0.2) is not None:
            q["altura_m"] = _num(a["altura_m"], 0.4, sh - 0.2)
        if a.get("tipo") in TIPOS_VAO:
            q["tipo"] = a["tipo"]
        if len(q) > 1:
            alterar.append(q)
    resposta = str(prop.get("resposta") or "").strip()[:600]
    return {"vol": ok_vol, "estilo": ok_est, "vaos": {"acrescentar": acrescentar, "remover": remover, "alterar": alterar},
            "resposta": resposta, "recusas": recusas,
            "alterou": bool(ok_vol or ok_est or acrescentar or remover or alterar)}


def _resumo_estado(estado: Dict[str, Any]) -> str:
    vol = {k: (estado.get("vol") or {}).get(k) for k in ("plot_l_m", "plot_w_m", "footprint_l_m", "footprint_w_m", "levels", "storey_h_m",
                                                      "setback_front_m", "setback_side_m", "uso")}
    vaos = [{"indice": i, **{k: o.get(k) for k in ("fachada", "piso", "tipo", "compartimento")},
             "largura_m": round(float(o.get("x1", 0)) - float(o.get("x0", 0)), 2)} for i, o in enumerate(estado.get("vaos") or [])][:60]
    return json.dumps({"lote_e_casa": vol, "estilo": estado.get("estilo") or {}, "vaos_atuais": vaos}, ensure_ascii=False)


async def interpretar(texto: str, estado: Dict[str, Any], historico: List[Dict[str, str]] | None = None) -> Dict[str, Any]:
    from engines import anthropic_native as AN
    if not AN.native_available():
        return {"erro": "Assistente IA indisponível neste servidor — use os comandos simples (ex.: «telhado de 4 águas»)."}
    conversa = "".join(f"\nUtilizador: {h.get('eu', '')}\nEstúdio: {h.get('resp', '')}" for h in (historico or [])[-6:])
    pedido = f"Estado atual da casa (JSON): {_resumo_estado(estado)}\nConversa anterior:{conversa or ' (nenhuma)'}\nPedido: {texto}"
    try:
        txt = await AN.complete(SISTEMA, pedido, max_tokens=1200)
        m = re.search(r"\{.*\}", txt or "", re.S)
        prop = json.loads(m.group(0)) if m else {}
    except Exception as e:  # noqa: BLE001
        return {"erro": f"Pedido não interpretado ({type(e).__name__}). Tente reformular."}
    if not isinstance(prop, dict):
        return {"erro": "Resposta do assistente ilegível. Tente reformular."}
    return validar(prop, estado)

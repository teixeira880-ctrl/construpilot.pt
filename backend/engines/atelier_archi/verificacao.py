"""Verificação do projeto antes de validar (Ateliê Arquiteto) — determinística, a partir do modelo único do Estúdio.

Só regras com fonte escrita; cada resultado diz a regra, o artigo, o valor medido e o limite.
Portugal: RGEU (DL 38 382/1951) — art. 65.º (pé-direito), 66.º (áreas mínimas por tipologia), 68.º (instalações
sanitárias), 69.º (dimensões mínimas), 71.º (vãos ≥ 1/10 da área e ≥ 1,08 m²).
França: décret 2002-120 (logement décent) art. 2 et 4, règlement sanitaire départemental type art. 40.3 (à vérifier
selon le département).
Mais o controlo do programa: áreas obtidas vs pedidas, áreas por piso, divisões por definir, erros do modelo.
Nada aqui substitui a verificação por um técnico habilitado: é dito em cada relatório.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from engines.atelier_archi.programme import _fold, _tipo
from engines.estudio_projeto import sitio

PAIS = sitio.PAIS
HABITAVEIS = {"chambre", "suite", "sejour", "sejour_cuisine", "cuisine", "bureau"}
SANITARIAS = {"sdb", "sde", "wc"}


def _t(fr: str, pt: str) -> str:
    return fr if PAIS == "FR" else pt


def _r(x: float, n: int = 2) -> float:
    return round(float(x), n)


def _dims(pts: List[List[float]]) -> tuple:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    a, b = max(xs) - min(xs), max(ys) - min(ys)
    return min(a, b), max(a, b)


def _cle(nome: str) -> Optional[str]:
    return _tipo(_fold(nome))


def _vaos_ext(modelo: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Vãos de iluminação (janelas e portas envidraçadas) em paredes exteriores."""
    tipos = modelo.get("tipos_parede") or {}
    ext = set()
    for w in modelo.get("paredes") or []:
        t = tipos.get(w.get("tipo")) or {}
        if t.get("exterior") or str(w.get("tipo", "")).startswith("ext"):
            ext.add(w["id"])
    return {v["id"]: v for v in modelo.get("vaos") or [] if v.get("parede") in ext and v.get("tipo") in ("janela", "portada")}


def verificar(modelo: Dict[str, Any], der: Dict[str, Any], programme: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    res: List[Dict[str, Any]] = []

    def add(estado: str, regra: str, fonte: str, msg: str, divisao: str = "", valor: Any = None, limite: Any = None) -> None:
        res.append({"estado": estado, "regra": regra, "fonte": fonte, "divisao": divisao, "valor": valor, "limite": limite, "msg": msg})

    _nomes = {"p0": _t("Rez-de-chaussée", "Rés-do-chão"), "p1": _t("Étage", "1.º andar"), "p2": _t("2e étage", "2.º andar")}
    pisos = {p["id"]: {**p, "nome": _nomes.get(p["id"], p.get("nome") or p["id"])} for p in modelo.get("pisos") or []}
    vext = _vaos_ext(modelo)
    divs = []
    for d in der.get("divisoes") or []:
        cle = _cle(d.get("nome") or "")
        mn, mx = _dims(d["pts"]) if d.get("pts") else (0.0, 0.0)
        luz = 0.0
        for f in d.get("faces") or []:
            for v in f.get("vaos") or []:
                if v.get("id") in vext:
                    luz += max(0.0, (v["u1"] - v["u0"]) * (v["z1"] - v["z0"]))
        divs.append({"nome": d["nome"], "piso": d["piso"], "area": float(d["area_m2"]), "cle": cle, "min": mn, "max": mx, "luz": luz})

    # ---- erros do próprio modelo
    for e in der.get("erros") or []:
        add("falha", _t("Maquette", "Modelo"), _t("Studio de projet", "Estúdio de Projeto"), e.get("msg") if isinstance(e, dict) else str(e))
    for d in divs:
        if "definir" in _fold(d["nome"]) or "affecter" in _fold(d["nome"]):
            add("aviso", _t("Programme", "Programa"), _t("Programme", "Programa"),
                _t(f"« {d['nome']} » ({d['area']:.1f} m²) : pièce sans fonction — à affecter ou supprimer.",
                   f"«{d['nome']}» ({d['area']:.1f} m²): divisão sem função — atribuir ou eliminar."), d["nome"], d["area"])

    quartos = sorted([d for d in divs if d["cle"] in ("chambre", "suite")], key=lambda d: -d["area"])
    T = len(quartos)

    if PAIS == "PT":
        # art. 65.º — pé-direito livre ≥ 2,40 m (habitáveis); piso a piso ≥ 2,70 m
        for p in pisos.values():
            pd, laje = float(p.get("pe_direito_m") or 0), float(p.get("laje_m") or 0)
            ok = pd >= 2.40 - 1e-6
            add("ok" if ok else "falha", _t("Hauteur libre", "Pé-direito livre"), "RGEU art. 65.º, n.º 1",
                f"{p['nome']}: {pd:.2f} m {'≥' if ok else '<'} 2,40 m", p["nome"], pd, 2.40)
            if len(pisos) > 1:
                pp = pd + laje
                ok2 = pp >= 2.70 - 1e-6
                add("ok" if ok2 else "falha", "Altura piso a piso", "RGEU art. 65.º, n.º 1",
                    f"{p['nome']}: {pp:.2f} m {'≥' if ok2 else '<'} 2,70 m", p["nome"], _r(pp), 2.70)
        # art. 66.º — áreas mínimas
        sala_min = 10.0 if T <= 1 else (12.0 if T <= 4 else 16.0)
        for d in divs:
            if d["cle"] == "sejour":
                ok = d["area"] >= sala_min
                add("ok" if ok else "falha", "Área mínima da sala", "RGEU art. 66.º", f"{d['nome']}: {d['area']:.1f} m² (mín. {sala_min:g} m² em T{T})",
                    d["nome"], d["area"], sala_min)
            elif d["cle"] == "cuisine":
                ok = d["area"] >= 6.0
                add("ok" if ok else "falha", "Área mínima da cozinha", "RGEU art. 66.º", f"{d['nome']}: {d['area']:.1f} m² (mín. 6 m²)", d["nome"], d["area"], 6.0)
            elif d["cle"] == "sejour_cuisine":
                lim = sala_min + 6.0
                ok = d["area"] >= lim
                add("ok" if ok else "falha", "Sala + cozinha integradas", "RGEU art. 66.º",
                    f"{d['nome']}: {d['area']:.1f} m² (mín. {lim:g} m² = sala {sala_min:g} + cozinha 6)", d["nome"], d["area"], lim)
        for i, q in enumerate(quartos):
            lim = 10.5 if i == 0 else (6.5 if (T >= 4 and i == T - 1) else 9.0)
            tipo = "casal" if i == 0 else ("simples" if lim == 6.5 else "duplo")
            ok = q["area"] >= lim
            add("ok" if ok else "falha", f"Área mínima — quarto {tipo}", "RGEU art. 66.º",
                f"{q['nome']}: {q['area']:.1f} m² (mín. {lim:g} m²)", q["nome"], q["area"], lim)
        # art. 68.º — instalações sanitárias
        ins = [d for d in divs if d["cle"] in SANITARIAS]
        tot = sum(d["area"] for d in ins)
        lim, n_min = (3.5, 1) if T <= 2 else ((4.5, 2) if T <= 4 else (6.0, 2))
        ok = tot >= lim and len(ins) >= n_min
        add("ok" if ok else "falha", "Instalações sanitárias", "RGEU art. 68.º",
            f"{len(ins)} espaço(s), {tot:.1f} m² (mín. {lim:g} m² em {n_min} espaço(s) para T{T})", "", _r(tot), lim)
        # art. 69.º — dimensões mínimas
        for d in divs:
            if d["cle"] not in HABITAVEIS:
                continue
            if d["cle"] == "cuisine":
                lim = 1.70
                ok = d["min"] >= lim
                add("ok" if ok else "falha", "Dimensão mínima da cozinha", "RGEU art. 69.º",
                    f"{d['nome']}: {d['min']:.2f} m (mín. {lim:.2f} m)", d["nome"], _r(d["min"]), lim)
                continue
            a = d["area"]
            if a >= 15.0:
                ok = d["max"] <= 2 * d["min"] + 1e-6
                add("ok" if ok else "aviso", "Proporção (comprimento ≤ 2 × largura)", "RGEU art. 69.º",
                    f"{d['nome']}: {d['max']:.2f} × {d['min']:.2f} m" + ("" if ok else " — salvo vãos em paredes opostas"), d["nome"], _r(d["max"] / max(d["min"], 0.01)), 2.0)
            else:
                lim = 2.10 if a < 9.5 else (2.40 if a < 12.0 else 2.70)
                ok = d["min"] >= lim - 1e-6
                add("ok" if ok else "falha", "Dimensão mínima", "RGEU art. 69.º",
                    f"{d['nome']}: largura {d['min']:.2f} m (mín. {lim:.2f} m para {a:.1f} m²)", d["nome"], _r(d["min"]), lim)
        # art. 71.º — vãos ≥ 1/10 da área e ≥ 1,08 m²
        for d in divs:
            if d["cle"] not in HABITAVEIS:
                continue
            lim = max(d["area"] / 10.0, 1.08)
            ok = d["luz"] >= lim - 1e-6
            add("ok" if ok else "falha", "Iluminação e ventilação natural", "RGEU art. 71.º",
                f"{d['nome']}: vãos {d['luz']:.2f} m² (mín. {lim:.2f} m²)", d["nome"], _r(d["luz"]), _r(lim))
    else:
        principais = [d for d in divs if d["cle"] in ("chambre", "suite", "sejour", "sejour_cuisine", "bureau")]
        hsp = min([float(p.get("pe_direito_m") or 0) for p in pisos.values()] or [0])
        ok = any(d["area"] >= 9.0 for d in principais) and hsp >= 2.20
        add("ok" if ok else "falha", "Pièce principale ≥ 9 m² et HSP ≥ 2,20 m", "Décret 2002-120, art. 4",
            f"Plus grande pièce principale : {max([d['area'] for d in principais] or [0]):.1f} m² ; HSP {hsp:.2f} m", "", None, 9.0)
        for p in pisos.values():
            pd = float(p.get("pe_direito_m") or 0)
            ok = pd >= 2.20 - 1e-6
            add("ok" if ok else "falha", "Hauteur sous plafond", "RSD type, art. 40.3 (à vérifier selon le département)",
                f"{p['nome']} : {pd:.2f} m (min. 2,20 m)", p["nome"], pd, 2.20)
        for d in principais:
            ok = d["area"] >= 7.0
            add("ok" if ok else "falha", "Surface des pièces d'habitation", "RSD type, art. 40.3 (à vérifier selon le département)",
                f"{d['nome']} : {d['area']:.1f} m² (min. 7 m²)", d["nome"], d["area"], 7.0)
        for d in principais + [x for x in divs if x["cle"] == "cuisine"]:
            ok = d["luz"] > 0
            add("ok" if ok else "falha", "Éclairement naturel et ouvrant", "Décret 2002-120, art. 2, 7°",
                f"{d['nome']} : {d['luz']:.2f} m² de baies sur l'extérieur", d["nome"], _r(d["luz"]), None)
            if ok and d["luz"] < d["area"] / 6.0 and d["cle"] != "cuisine":
                add("aviso", "Vitrage ≥ 1/6 de la surface (règle de l'art)", "Pratique courante (non réglementaire)",
                    f"{d['nome']} : {d['luz']:.2f} m² pour {d['area'] / 6:.2f} m² conseillés", d["nome"], _r(d["luz"]), _r(d["area"] / 6))

    # ---- programa pedido vs modelo
    if programme:
        obtidas = {d["nome"]: d["area"] for d in divs}
        for p in programme.get("pieces") or []:
            a = obtidas.get(p["nom"])
            if a is None or not p.get("surface"):
                continue
            dif = (a - p["surface"]) / p["surface"]
            est = "ok" if abs(dif) <= 0.10 else "aviso"
            add(est, _t("Surface demandée", "Área pedida"), _t("Programme", "Programa"),
                _t(f"{p['nom']} : {a:.1f} m² pour {p['surface']:g} m² demandés ({dif:+.0%})",
                   f"{p['nom']}: {a:.1f} m² para {p['surface']:g} m² pedidos ({dif:+.0%})"), p["nom"], a, p["surface"])
        ped = programme.get("pisos_indicados") or {}
        quadro = (der.get("medicoes") or {}).get("quadro_areas") or []
        for niv, alvo in ped.items():
            k = int(niv)
            if k < len(quadro):
                q = {**quadro[k], "piso": _nomes.get(f"p{k}", quadro[k]["piso"])}
                bruta = q["area_bruta_m2"]
                if k == 0 and (programme.get("garage") or {}).get("surface"):
                    bruta -= float(programme["garage"]["surface"])
                dif = (bruta - alvo) / alvo if alvo else 0
                add("ok" if abs(dif) <= 0.10 else "aviso", _t("Surface par niveau", "Área por piso"), _t("Programme", "Programa"),
                    _t(f"{q['piso']} : {bruta:.0f} m² construits (hors garage) pour {alvo:g} m² indiqués ({dif:+.0%})",
                       f"{q['piso']}: {bruta:.0f} m² de construção (sem garagem) para {alvo:g} m² indicados ({dif:+.0%})"),
                    q["piso"], _r(bruta, 1), alvo)

        # circulações + paredes: o que o programa reserva vs o que a planta precisa
        circ_ped = programme.get("circulacao_indicada") or {}
        for niv, alvo in circ_ped.items():
            k = int(niv)
            if k >= len(quadro):
                continue
            pid = f"p{k}"
            circ = sum(d["area"] for d in divs if d["piso"] == pid and _fold(d["nome"]).strip() in ("hall", "corredor", "degagement"))
            paredes = float(quadro[k].get("paredes_e_vazios_m2") or 0)
            tot = circ + paredes
            ok = tot <= alvo * 1.10
            nome = _nomes.get(pid, pid)
            add("ok" if ok else "aviso", _t("Circulations et murs", "Circulações e paredes"), _t("Programme", "Programa"),
                _t(f"{nome} : circulations {circ:.1f} m² + murs et trémies {paredes:.1f} m² = {tot:.1f} m² pour {alvo:g} m² prévus"
                   + ("" if ok else " — le programme réserve trop peu de place aux murs et aux dégagements ; réduire les pièces "
                      "ou accepter une surface construite plus grande."),
                   f"{nome}: circulações {circ:.1f} m² + paredes e vazios {paredes:.1f} m² = {tot:.1f} m² para {alvo:g} m² previstos"
                   + ("" if ok else " — o programa reserva pouco espaço para paredes e circulação; reduzir divisões "
                      "ou aceitar uma área de construção maior.")), nome, _r(tot, 1), alvo)

    n = {k: sum(1 for r in res if r["estado"] == k) for k in ("ok", "aviso", "falha")}
    return {"pais": PAIS, "resultados": res, "resumo": n,
            "conforme": n["falha"] == 0,
            "nota": _t("Contrôle automatique indicatif : il ne remplace pas la vérification par un professionnel habilité "
                       "(architecte, bureau d'études) ni les règles locales (PLU, RSD du département).",
                       "Controlo automático indicativo: não substitui a verificação por técnico habilitado (arquiteto, engenheiro) "
                       "nem as regras locais (PDM, regulamentos municipais).")}

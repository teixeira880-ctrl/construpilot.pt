"""Pipeline do estudo de um edifício multifamiliar em betão armado : modelo → controlos → estrutura (→ 3D) → medições →
orçamento → especialidades → desenhos e notas PDF + Excel. Sem IA : mesma entrada → mesmos resultados.
"""
from __future__ import annotations

import copy
import re
import traceback
import unicodedata
from pathlib import Path

from . import estrutura as ES
from . import fem3d, grelha, modelo
from .modelo import BLOCK
from .textos import fmt


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:40] or "Edificio"


def _where(w) -> str:
    if w["axis"] == "Y":
        return f"X = {fmt(w['x0'])}, Y {fmt(w['y0'])} → {fmt(w['y1'])}"
    return f"Y = {fmt(w['y0'])}, X {fmt(w['x0'])} → {fmt(w['x1'])}"


def calcular(S: modelo.Spec, use_fem: bool = True) -> dict:
    """Cálculo estrutural completo → R."""
    R = {"anomalies": [], "decisions": list(S.decisions)}
    proposed = []
    if S.auto_walls and ES.seismic_required(S):
        reg0 = ES.regularity(S, ES.lateral_elements(S)) if ES.lateral_elements(S) else {"ok": False}
        if not reg0.get("ok"):
            proposed = ES.propose_walls(S)
            for w in proposed:
                R["decisions"].append(S.t(
                    f"Parede resistente {w['id']} PROPOSTA ({_where(w)}, {fmt(w['Lw'])} × {fmt(w['t'])} m) para controlar a torção sísmica — "
                    "a compatibilizar com a arquitetura (vãos).",
                    f"Voile {w['id']} PROPOSÉ ({_where(w)}, {fmt(w['Lw'])} × {fmt(w['t'])} m) pour maîtriser la torsion sismique — à coordonner avec l'architecte (baies)."))
    R["proposed_walls"] = [w["id"] for w in proposed]
    R["reg0"] = ES.regularity(S, ES.lateral_elements(S)) if ES.lateral_elements(S) else {"ok": False}
    lines = grelha.beam_lines(S)
    segs = grelha.beam_segments(S, lines)
    pans = grelha.panels(S, segs)
    gpans = grelha.panels(S, segs, garage=True)
    R.update(lines=lines, segs=segs, panels=pans, gpanels=gpans, gbeams=grelha.garage_beams(S))
    R["slabs"] = ES.slabs(S, pans, gpans)
    R["cant"] = {d: ES.cantilever(S, d) for d in sorted({b["depth"] for b in S.balconies})}
    els, trib = grelha.tributary(S)
    R["trib"] = trib
    R["rows"] = ES.load_takedown(S, trib)
    R["cols"] = ES.size_columns(S, R["rows"])
    R["beams"] = ES.beams(S, segs, pans)
    gsegs = [{"name": g["id"], "line": g["id"], "a": g["a"], "b": g["b"], "L": round(((g["a"][0] - g["b"][0]) ** 2 + (g["a"][1] - g["b"][1]) ** 2) ** 0.5, 2),
              "facade": None, "cont": False} for g in R["gbeams"]]
    R["gbeam_design"] = ES.beams(S, gsegs, gpans, garden=True) if gsegs else []
    R["seis"] = ES.seismic(S, R["rows"])
    R["fem"] = None
    if use_fem and R["seis"].get("ok") and R["seis"].get("required") and fem3d.available():
        try:
            F = fem3d.run(S, R)
            fem3d.apply(S, R, F)
            R["_F"] = F
        except Exception as exc:  # noqa: BLE001 — o modelo 3D é um complemento : o estudo segue com o método simplificado
            R["fem"] = None
            R["fem_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            R["decisions"].append(S.t("Modelo 3D não concluído : esforços sísmicos pelo método das forças laterais.",
                                      "Modèle 3D non abouti : efforts sismiques par la méthode des forces latérales."))
    R["bwalls"] = ES.basement_walls(S) if S.basement else []
    R["foots"] = ES.footings(S, R["cols"])
    R["rafts"] = ES.rafts(S, R["seis"], R["rows"]) if R["seis"].get("ok") else []
    R["fnd"], R["foots"] = ES.merge_foundations(R["rafts"], R["foots"], S.soil["sigma_rd"])
    R["anomalies"] += _checks(S, R)
    return R


def _checks(S, R) -> list[dict]:
    """Verificações de resultado (não bloqueiam : listadas no relatório)."""
    A = []
    for s in R["slabs"]:
        if s["lx"] > 8.0:
            A.append({"level": "aviso", "code": "SLAB-SPAN", "message": S.t(f"Painel {s['name']} com vão {s['lx']:.2f} m > 8 m : rever o sistema de lajes.",
                                                                             f"Panneau {s['name']} de portée {s['lx']:.2f} m > 8 m : revoir le système de dalles.")})
    for c in R["cols"]:
        for tag in ("base", "topo"):
            if c.get(tag) and not c[tag]["ok"]:
                A.append({"level": "aviso", "code": "COL-NU", "message": S.t(f"Pilar {c['id']} ({tag}) : ν = {c[tag]['nu']:.2f} > 0,65 com a maior secção corrente.",
                                                                             f"Poteau {c['id']} ({tag}) : ν = {c[tag]['nu']:.2f} > 0,65 avec la plus grande section courante.")})
    for b in R["beams"]:
        if not b["ok"]:
            A.append({"level": "aviso", "code": "BEAM", "message": S.t(f"Viga {b['name']} ({b['L']:.2f} m) não verificada com h ≤ 0,80 m.",
                                                                       f"Poutre {b['name']} ({b['L']:.2f} m) non vérifiée avec h ≤ 0,80 m.")})
    if not R["seis"].get("ok"):
        A.append({"level": BLOCK, "code": "NO-LATERAL", "message": S.t("Sem núcleos nem paredes : contraventamento sísmico impossível de verificar pelo método.",
                                                                       "Ni noyau ni voile : contreventement sismique non vérifiable par la méthode.")})
    elif R["seis"].get("required") and not R["seis"]["reg"]["ok"]:
        A.append({"level": "aviso", "code": "TORSION", "message": S.t("Regularidade em planta não verificada (torção) : rever a posição das paredes.",
                                                                      "Régularité en plan non vérifiée (torsion) : revoir la position des voiles.")})
    s = R["seis"]
    if s.get("ok"):
        dsrc = s.get("drift_fem") or s["drift"]
        for d, v in dsrc.items():
            if v["nu_dr_mm"] > v["lim_mm"]:
                A.append({"level": BLOCK, "code": "DRIFT", "message": S.t(
                    f"Deriva entre pisos {d} : ν·d_r = {v['nu_dr_mm']:.1f} mm > {v['lim_mm']:.0f} mm — aumentar a rigidez (paredes / núcleos).",
                    f"Déplacement entre niveaux {d} : ν·d_r = {v['nu_dr_mm']:.1f} mm > {v['lim_mm']:.0f} mm — rigidifier (voiles / noyaux).")})
        for dsg in s["cores"] + s["walls"]:
            if s.get("required") and dsg["nu_sis"] > 0.40:
                A.append({"level": BLOCK, "code": "WALL-NU", "message": S.t(
                    f"{dsg['id']} : esforço normal reduzido sísmico ν_d = {dsg['nu_sis']:.2f} > 0,40 (EN 1998-1 §5.4.3.4.1) — aumentar a espessura.",
                    f"{dsg['id']} : effort normal réduit sismique ν_d = {dsg['nu_sis']:.2f} > 0,40 (EN 1998-1 §5.4.3.4.1) — épaissir.")})
            for d in ("X", "Y"):
                v = dsg[d]
                if v["Lw"] < 1.0:
                    continue
                if not v.get("shear_ok", True):
                    A.append({"level": BLOCK, "code": "WALL-SHEAR", "message": S.t(
                        f"{dsg['id']} ({d}) : 1,5·V_Ed = {1.5 * v['V']:.0f} kN > V_Rd,max = {v['VRdmax']:.0f} kN — aumentar a espessura ou acrescentar paredes.",
                        f"{dsg['id']} ({d}) : 1,5·V_Ed = {1.5 * v['V']:.0f} kN > V_Rd,max = {v['VRdmax']:.0f} kN — épaissir ou ajouter des voiles.")})
                if not v.get("rho_ok", True):
                    A.append({"level": BLOCK, "code": "WALL-STEEL", "message": S.t(
                        f"{dsg['id']} ({d}) : armadura de extremidade {v['As_ext_cm2']:.0f} cm² (ρ = {v['rho_end'] * 100:.1f} % > 4 %) — rever o contraventamento.",
                        f"{dsg['id']} ({d}) : aciers d'about {v['As_ext_cm2']:.0f} cm² (ρ = {v['rho_end'] * 100:.1f} % > 4 %) — revoir le contreventement.")})
    for c in R["cant"].values():
        if not c.get("ok", True):
            A.append({"level": "aviso", "code": "BALCONY", "message": S.t(
                f"Varanda em consola {c['depth']:.2f} m não verificada com h = 0,20 (flecha {c['w_mm']:.0f} mm / esforço) : prever viga em consola ou rotura com apoio.",
                f"Balcon en console {c['depth']:.2f} m non vérifié avec h = 0,20 (flèche {c['w_mm']:.0f} mm / effort) : prévoir une poutre console.")})
    for b in R.get("gbeam_design") or []:
        if not b["ok"]:
            A.append({"level": "aviso", "code": "BEAM", "message": S.t(f"Viga {b['name']} (laje sobre a cave) não verificada.", f"Poutre {b['name']} (dalle sur sous-sol) non vérifiée.")})
    for fz in R["fnd"]:
        if not fz.get("ok", True):
            A.append({"level": "aviso", "code": "RAFT-SIGMA", "message": S.t(
                f"Ensoleiramento {fz['id']} : σ = {fz['sigma_grav']:.0f} kPa > σ_Rd — fundação a rever (estudo geotécnico).",
                f"Radier {fz['id']} : σ = {fz['sigma_grav']:.0f} kPa > σ_Rd — fondations à revoir (étude G2).")})
    for r in R["rafts"]:
        if r.get("fail"):
            A.append({"level": "aviso", "code": "RAFT", "message": S.t(f"Ensoleiramento sob {r['id']} não encontrado até 5 m de aba : fundação indireta a estudar.",
                                                                       f"Radier sous {r['id']} non trouvé jusqu'à 5 m de débord : fondations profondes à étudier.")})
    return A


def _sp(S):
    """Módulo de especialidades do país (PT : REH / DR 23/95 / RTIEBT ; FR : RE2020 / DTU 60.11 / NF C 15-100)."""
    if S.country == "FR":
        from . import especialidades_fr as SP
    else:
        from . import especialidades as SP
    return SP


def run(raw: dict, out_dir: str | Path | None = None, use_fem: bool = True, especialidades: bool = True) -> dict:
    """Estudo completo. → {status, anomalies, decisions, files {kind: path}, summary, R}."""
    from . import desenhos, excel, medicoes, relatorios
    raw = copy.deepcopy(raw)
    try:
        S = modelo.load(raw)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return {"status": "MODELO_INVALIDO", "files": {}, "decisions": [],
                "anomalies": [{"level": BLOCK, "code": "INPUT", "message": f"Modelo incompleto ou mal formado ({type(exc).__name__}: {exc})",
                               "fix": "completar pilares (x, y), núcleos (x0, y0, x1, y1) e paredes"}]}
    anomalies = modelo.validate(S)
    if any(a["level"] == BLOCK for a in anomalies):
        return {"status": "MODELO_INVALIDO", "anomalies": anomalies, "decisions": S.decisions, "files": {}}
    R = calcular(S, use_fem=use_fem)
    R["anomalies"] = anomalies + R["anomalies"]
    Q = medicoes.medir(S, R)
    O = medicoes.orcamento(S, R, Q)
    MEP = None
    if especialidades and S.units:
        try:
            SP = _sp(S)
            MEP = SP.calcular(S, R)
        except Exception as exc:  # noqa: BLE001 — especialidades indisponíveis nesta plataforma : o estudo de estrutura segue
            R["anomalies"].append({"level": "aviso", "code": "MEP", "message": S.t(
                f"Especialidades não calculadas ({type(exc).__name__}: {str(exc)[:120]}).",
                f"Lots techniques non calculés ({type(exc).__name__}: {str(exc)[:120]}).")})
    files = {}
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        stem = slug(S.name)
        files["memoria"] = relatorios.memoria(S, R, out / f"{S.t('Memoria_estrutura', 'Note_calcul_structure')}_{stem}.pdf", out)
        files["desenhos"] = desenhos.build(S, R, out / f"{S.t('Desenhos_estrutura', 'Plans_structure')}_{stem}.pdf")
        files["medicoes"] = relatorios.medicoes_pdf(S, R, Q, out / f"{S.t('Medicoes', 'Metre')}_{stem}.pdf")
        files["orcamento"] = relatorios.orcamento_pdf(S, R, Q, O, out / f"{S.t('Orcamento', 'Estimation')}_{stem}.pdf")
        files["quantidades"] = relatorios.quantidades_pdf(S, R, Q, out / f"{S.t('Quantidades', 'Quantitatifs')}_{stem}.pdf")
        files["xlsx"] = excel.build(S, R, Q, O, out / f"{S.t('Medicoes_orcamento', 'Metre_estimation')}_{stem}.xlsx")
        if MEP:
            files.update(_sp(S).pdfs(S, R, MEP, out, stem))
    status = "PRONTO" if not any(a["level"] == BLOCK for a in R["anomalies"]) else "NAO_PRONTO"
    return {"status": status, "anomalies": R["anomalies"], "decisions": R["decisions"], "files": {k: str(v) for k, v in files.items() if v},
            "summary": summary(S, R, Q, O, MEP), "R": R, "S": S}


def summary(S, R, Q, O, MEP=None) -> dict:
    s = R["seis"]
    out = {"pisos": S.n, "cave": S.basement, "area_bruta_m2": round(Q["areas"]["bruta"], 0), "betao_m3": round(Q["totais"]["betao"], 0),
           "aco_t": round(Q["totais"]["aco"] / 1000, 1), "cofragem_m2": round(Q["totais"]["cofragem"], 0),
           "estrutura_eur": round(O["tot_s"], 0), "total_sem_iva_eur": round(O["sub"], 0), "eur_m2": round(O["m2"], 0),
           "paredes_propostas": R["proposed_walls"], "modelo_3d": bool(R.get("fem")), "T1_s": s.get("T1"),
           "Fb_kN": (s.get("gov") or {}).get("Fb"), "fundacoes": len(R["fnd"]) + len(R["foots"])}
    if R.get("fem"):
        out["T_modos_s"] = [round(m["T"], 3) for m in R["fem"]["modes"][:3]]
        out["Vb_3d_kN"] = R["fem"]["Vb"]
    if MEP:
        out["especialidades"] = MEP.get("summary")
    return out


def where(exc: BaseException) -> str:
    tb = traceback.extract_tb(exc.__traceback__)
    for fr in reversed(tb):
        if "edificio_ba" in fr.filename:
            return f"{Path(fr.filename).name}:{fr.lineno}"
    return "?"

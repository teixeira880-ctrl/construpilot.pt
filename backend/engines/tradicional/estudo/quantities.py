"""Mapa de quantidades da construção tradicional — por piso, das fundações à cobertura, a partir dos elementos calculados
(nada estimado por rácios). Primeiro as quantidades; o preço só entra pela biblioteca da empresa / projeto / mercado real
(mesma lógica que os motores LSF e CLT: engines.lsf.quantities.precificar)."""
from __future__ import annotations

from engines.lsf.quantities import _slug

MERCADO_UNIDADE = ()            # artigos de obra (m³, m², kg): sem preço de mercado online por unidade comparável


def linhas(res: dict, lang: str = "pt") -> list[dict]:
    out = []
    R = res["regras"]
    fc = f"C{R['fck']}/{R['fck'] + 5}"

    def add(cat, code, des, un, qtd, detalhe="", refs=None):
        if not qtd:
            return
        out.append({"code": code, "cat": cat, "designacao": des, "un": un, "qtd": round(qtd, 3 if un in ("m", "m²", "m³", "kg") else 0),
                    "detalhe": detalhe, "refs": refs or []})

    ordem = 1
    # ---- fundações
    cat = f"{ordem:02d} Fundações"
    S, VF = res["sapatas"], res["vigasFundacao"]
    add(cat, "FUN-ESC", "Escavação para sapatas e vigas de fundação (com folga de trabalho)", "m³", sum(s["escavacao"] for s in S) + sum(v["escavacao"] for v in VF),
        f"{len(S)} sapatas + {len(VF)} vigas de fundação")
    add(cat, "FUN-LIMP", f"Betão de limpeza C12/15 ({R['limpeza']:.0f} mm)", "m³", sum(s["limpeza"] for s in S) + sum(v["limpeza"] for v in VF))
    add(cat, "FUN-SAP-BET", f"Betão {fc} em sapatas isoladas", "m³", sum(s["m3"] for s in S), ", ".join(f"{s['id']} {s['B'] / 1000:.2f}×{s['B'] / 1000:.2f}×{s['hs'] / 1000:.2f}" for s in S)[:300],
        [s["id"] for s in S])
    add(cat, "FUN-SAP-ACO", "Aço A500 NR em sapatas (varões calculados)", "kg", sum(s["kg"] for s in S), "; ".join(f"{s['id']}: {s['armadura']}" for s in S)[:300])
    add(cat, "FUN-SAP-COF", "Cofragem lateral de sapatas", "m²", sum(s["cofragem"] for s in S))
    add(cat, "FUN-VF-BET", f"Betão {fc} em vigas de fundação", "m³", sum(v["m3"] for v in VF), ", ".join(v["id"] for v in VF), [v["id"] for v in VF])
    add(cat, "FUN-VF-ACO", "Aço A500 NR em vigas de fundação (varões e estribos calculados)", "kg", sum(v["kg"] for v in VF),
        "; ".join(f"{v['id']}: {v['armadura']}, {v['estribos']}" for v in VF)[:300])
    add(cat, "FUN-VF-COF", "Cofragem de vigas de fundação", "m²", sum(v["cofragem"] for v in VF))
    t = res.get("terreo")
    if t:
        ordem += 1
        cat = f"{ordem:02d} Pavimento térreo"
        add(cat, "TER-ENR", f"Enrocamento / tout-venant ({R['enrocamento']:.0f} mm)", "m³", t["enrocamento"])
        add(cat, "TER-FILME", "Filme de polietileno sob o massame", "m²", t["area"])
        add(cat, "TER-BET", f"Betão {fc} em massame ({R['massameH']:.0f} mm)", "m³", t["m3"])
        add(cat, "TER-ACO", f"Aço em massame — {t['malha']}", "kg", t["kg"])
    # ---- por piso
    for nv in res["niveis"]:
        ordem += 1
        cat = f"{ordem:02d} {nv} — betão armado"
        P = [p for p in res["pilares"] if p.get("nivel") == nv]
        ids_w = {w["id"] for w in res["paredes"] if w.get("nivel") == nv}
        V = [v for v in res["vigas"] if v["parede"] in ids_w]
        G = [g for g in res["vergas"] if g["parede"] in ids_w]
        add(cat, f"PIL-BET-{_slug(nv)}", f"Betão {fc} em pilares", "m³", sum(p["m3"] for p in P), ", ".join(p["id"] for p in P)[:300], [p["id"] for p in P])
        add(cat, f"PIL-ACO-{_slug(nv)}", "Aço A500 NR em pilares (varões e estribos calculados)", "kg", sum(p["kg"] for p in P),
            "; ".join(f"{p['pilar']}: {p['armadura']}" for p in P)[:300])
        add(cat, f"PIL-COF-{_slug(nv)}", "Cofragem de pilares", "m²", sum(p["cofragem"] for p in P))
        add(cat, f"VIG-BET-{_slug(nv)}", f"Betão {fc} em vigas", "m³", sum(v["m3"] for v in V), ", ".join(f"{v['id']} {v['b'] / 10:.0f}×{v['h'] / 10:.0f}" for v in V)[:300],
            [v["id"] for v in V])
        add(cat, f"VIG-ACO-{_slug(nv)}", "Aço A500 NR em vigas (varões e estribos calculados)", "kg", sum(v["kg"] for v in V),
            "; ".join(f"{v['id']}: {v['armadura']}" for v in V)[:300])
        add(cat, f"VIG-COF-{_slug(nv)}", "Cofragem de vigas (fundo e faces)", "m²", sum(v["cofragem"] for v in V))
        add(cat, f"VRG-BET-{_slug(nv)}", f"Betão {fc} em vergas", "m³", sum(g["m3"] for g in G), f"{len(G)} vergas", [g["id"] for g in G])
        add(cat, f"VRG-ACO-{_slug(nv)}", "Aço em vergas (armadura construtiva)", "kg", sum(g["kg"] for g in G))
        add(cat, f"VRG-COF-{_slug(nv)}", "Cofragem de vergas", "m²", sum(g["cofragem"] for g in G))
        cat2 = f"{ordem:02d} {nv} — alvenarias"
        W = [w for w in res["paredes"] if w.get("nivel") == nv]
        por_un = {}
        for w in W:
            e = por_un.setdefault(w["unidade"], {"un": 0, "m2": 0.0, "arg": 0.0, "ids": []})
            e["un"] += w["unidades"]
            e["m2"] += w["areaAlv"]
            e["arg"] += w["argamassa"]
            e["ids"].append(f"{w['id']} {w['unidades']}")
        compra = {}
        for x in res.get("alvenariaResumo") or []:            # motor de alvenaria unidade a unidade: unidades a comprar com os cortes
            if x["nivel"] == nv:
                c = compra.setdefault(x["unidade"], {"a_comprar": 0, "inteiras": 0, "cortes": 0, "unidades_para_cortes": 0, "cortadas_a_altura": 0})
                for k in c:
                    c[k] += x[k]
        for u, e in por_un.items():
            c = compra.get(u)
            if c:
                add(cat2, f"ALV-{_slug(u)}-{_slug(nv)}", u, "un", c["a_comprar"],
                    f"{c['inteiras']} inteiras + {c['unidades_para_cortes']} para {c['cortes']} cortes + {c['cortadas_a_altura']} cortadas à altura · "
                    f"{e['m2']:.2f} m² · por parede: " + ", ".join(e["ids"])[:200], [i.split()[0] for i in e["ids"]])
            else:
                add(cat2, f"ALV-{_slug(u)}-{_slug(nv)}", u, "un", e["un"], f"{e['m2']:.2f} m² · por parede: " + ", ".join(e["ids"])[:260], [i.split()[0] for i in e["ids"]])
            add(cat2, f"ALV-ARG-{_slug(u)}-{_slug(nv)}", f"Argamassa de assentamento — {u}", "m³", e["arg"])
        # lajes no topo deste piso
        zt = max((w["z0"] + w["H"] for w in W), default=None)
        L = [f for f in res["lajes"] if zt is not None and abs(f["z"] - zt) < 5]
        if L:
            cat3 = f"{ordem:02d} {nv} — laje superior"
            add(cat3, f"LAJ-BET-{_slug(nv)}", f"Betão {fc} em lajes maciças", "m³", sum(f["m3"] for f in L), ", ".join(f"{f['id']} h={f['h']:.0f}" for f in L), [f["id"] for f in L])
            add(cat3, f"LAJ-ACO-{_slug(nv)}", "Aço em lajes (malhas calculadas: vãos e apoios)", "kg", sum(f["kg"] for f in L))
            add(cat3, f"LAJ-COF-{_slug(nv)}", "Cofragem de lajes (incl. escoramento)", "m²", sum(f["cofragem"] for f in L))
    # ---- cobertura
    for c in res["coberturas"]:
        ordem += 1
        cat = f"{ordem:02d} Cobertura"
        add(cat, "COB-BET", f"Betão {fc} em lajes inclinadas ({c['h']:.0f} mm)", "m³", c["m3"])
        add(cat, "COB-ACO", "Aço em lajes inclinadas (malhas calculadas)", "kg", c["kg"])
        add(cat, "COB-COF", "Cofragem de lajes inclinadas", "m²", c["cofragem"])
        add(cat, "COB-TELHA", "Telha cerâmica (contagem fiada a fiada)", "un", c["telhas"], f"{c['area']:.1f} m² de cobertura")
        e = c.get("empenas") or {}
        add(cat, "COB-EMP", f"Empenas — {e.get('unidade', '')}", "un", e.get("unidades"), f"{e.get('area', 0):.2f} m²")
    # ---- acabamentos / fachada
    agg = {}
    for x in res["extras"]:
        k = (x["cat"], x["item"], x["un"])
        agg[k] = agg.get(k, 0.0) + x["qtd"]
    for (c_, item, un), q in sorted(agg.items()):
        ordem_c = 90 if c_ == "Fachada" else 91
        add(f"{ordem_c:02d} {c_}", "ACB-" + _slug(c_ + " " + item), item, un, q)
    out.sort(key=lambda r: (int(r["cat"].split()[0]), r["code"]))
    return out

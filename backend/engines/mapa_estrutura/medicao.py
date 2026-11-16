"""Do desenho lido ao mapa de quantidades : níveis, tramos de pilares/paredes/núcleos, lajes (maciça + aligeirada), vigas,
cofragem e aço estimado. Regras de medição :
 • elementos verticais : secção × altura livre entre lajes (face superior da laje de baixo → face inferior da laje de cima) ;
   a planta de um nível mostra, a cheio, os elementos que SUPORTAM essa laje ;
 • lajes : área bruta dentro do contorno, menos aberturas ; os pilares e paredes não são deduzidos ;
 • zona aligeirada : nº de moldes × módulo² ; betão = espessura equivalente e − (módulo − nervura)² × (e − lâmina) / módulo² ;
 • vigas : só o volume ABAIXO da laje (b × (h − e) × vão livre), para não contar duas vezes o betão da laje ;
 • aço : estimativa por taxas kg/m³ enquanto não houver desenhos de armaduras.
Tudo o que não vem no desenho fica em `pressupostos` (valor assumido, editável no Excel) ou em `perguntas`."""
from __future__ import annotations

import re
from collections import Counter, defaultdict

PADRAO = {"cota_base": 0.0, "h_vigas": 0.60, "nervura": 0.16, "lamina": 0.075, "e_laje": 0.20, "pe_direito": 3.00,
          "taxa_lajes": 100.0, "taxa_pilares": 150.0, "taxa_paredes": 110.0, "taxa_vigas": 130.0}
RE_LAMINA = re.compile(r"l[âa]mina[^\d\n]{0,60}?(\d+(?:[.,]\d+)?)\s*cm", re.I)


def _r(v, n=2):
    return round(float(v) + 1e-9, n)


def espessura_equivalente(e, lamina, modulo, nervura):
    """Betão por m² de laje aligeirada com moldes recuperáveis : laje cheia menos o vazio de um molde por módulo."""
    if not modulo or modulo <= nervura:
        return e
    return e - (modulo - nervura) ** 2 * max(e - lamina, 0.0) / modulo ** 2


def consolidar(leituras: list, cota_base=None, h_vigas=None, textos: str = "") -> dict:
    """Junta as plantas lidas (uma ou várias folhas) num modelo de medição com quantidades, pressupostos e perguntas."""
    par = dict(PADRAO)
    pressupostos, perguntas, avisos = [], [], []
    plantas = [p for l in leituras for p in l.get("plantas", [])]
    for l in leituras:
        avisos += l.get("avisos", [])
    if not plantas:
        return {"ok": False, "avisos": avisos or ["Nenhuma planta estrutural legível."], "perguntas": [], "pressupostos": []}
    m = RE_LAMINA.search(textos or "")
    if m:
        par["lamina"] = float(m.group(1).replace(",", ".")) / 100

    # níveis
    niveis, sem_cotas = [], 0
    for ip, p in enumerate(plantas):
        if p.get("niveis"):
            for n in p["niveis"]:
                niveis.append({"nome": n.get("nome") or f"Nível {n['zsup']:.2f}", "zsup": n["zsup"], "zinf": n.get("zinf"), "e": n.get("e"), "planta": ip})
        else:
            sem_cotas += 1
            niveis.append({"nome": f"Planta {ip + 1}", "zsup": None, "zinf": None, "e": None, "planta": ip})
    if sem_cotas:
        base = max([n["zsup"] for n in niveis if n["zsup"] is not None], default=0.0)
        for n in niveis:
            if n["zsup"] is None:
                base += par["pe_direito"]
                n["zsup"] = base
                n["assumido"] = True
        perguntas.append(f"{sem_cotas} planta(s) sem caixa de nível (Zsup / e) : indique as cotas dos pisos. "
                         f"Assumi {par['pe_direito']:.2f} m entre lajes.")
        pressupostos.append({"nome": "Altura entre pisos sem cota no desenho", "valor": par["pe_direito"], "un": "m"})
    niveis.sort(key=lambda n: n["zsup"])
    for n in niveis:
        if n["e"] is None:
            n["e"] = par["e_laje"]
            n["e_assumida"] = True
            perguntas.append(f"Espessura da laje de «{n['nome']}» não indicada : assumi {par['e_laje']:.2f} m.")
        if n["zinf"] is not None and abs(n["zsup"] - n["zinf"] - n["e"]) > 0.011:
            avisos.append(f"{n['nome']} : Zinf = {n['zinf']:.3f} não bate com Zsup − e = {n['zsup'] - n['e']:.3f}. Usei a espessura e = {n['e']:.3f} m.")
        n["zinf"] = n["zsup"] - n["e"]
    if cota_base is None:
        cota_base = par["cota_base"]
        perguntas.append(f"Cota de arranque dos pilares e paredes (topo das fundações ou piso inferior) não está nestas plantas : assumi {cota_base:.2f} m.")
        pressupostos.append({"nome": "Cota de arranque dos elementos verticais", "valor": cota_base, "un": "m"})
    par["cota_base"] = float(cota_base)
    for i, n in enumerate(niveis):
        n["h_livre"] = _r(n["zinf"] - (niveis[i - 1]["zsup"] if i else par["cota_base"]), 3)
        n["base"] = i == 0
        if n["h_livre"] <= 0:
            avisos.append(f"{n['nome']} : altura livre ≤ 0 com as cotas lidas. Verifique as cotas.")
    idx_de = defaultdict(list)                              # planta → índices dos níveis que representa
    for i, n in enumerate(niveis):
        idx_de[n["planta"]].append(i)

    # secção de referência de cada etiqueta (a mais frequente entre as tramas completas)
    vistas = defaultdict(list)
    for p in plantas:
        for e in p["elementos"]:
            if e["etiquetado"] and e["com_trama"] and (e["retangular"] or e["tipo"] != "Pilar"):
                vistas[e["nome"]].append((e["a"], e["b"], e["area"], e["perimetro"], e["retangular"]))
    ref = {}
    for nome, lst in vistas.items():
        (a, b), _ = Counter((x[0], x[1]) for x in lst).most_common(1)[0]
        ref[nome] = next(x for x in lst if (x[0], x[1]) == (a, b))

    # presença de cada etiqueta por nível : "cheio", "parcial", "vazio" (só contorno) ou "sem" (só a etiqueta)
    estado, proprio = defaultdict(dict), {}
    for ip, p in enumerate(plantas):
        for e in p["elementos"]:
            if not e["etiquetado"]:
                continue
            parcial = e["com_trama"] and e["tipo"] == "Pilar" and not e["retangular"]
            est = "vazio" if not e["com_trama"] else "parcial" if parcial else "cheio"
            for i in idx_de[ip]:
                estado[e["nome"]][i] = est
            proprio[(e["nome"], ip)] = e
        for nome in p.get("etiquetas_sem_peca", []):
            for i in idx_de[ip]:
                estado[nome].setdefault(i, "sem")

    tramos = defaultdict(lambda: {"niveis": [], "notas": set()})    # (nome, tipo, a, b, área, perímetro) → tramos
    tipo_de = {}
    for ip, p in enumerate(plantas):
        for e in p["elementos"]:
            tipo_de.setdefault(e["nome"], e["tipo"])

    def tipo_etiqueta(nome):
        return tipo_de.get(nome) or ("Parede" if nome.lower().startswith(("par", "pa", "m", "w")) else "Pilar")
    for nome, por_nivel in estado.items():
        cheios = [i for i, s in por_nivel.items() if s in ("cheio", "parcial")]
        incompletos = sorted(i for i, s in por_nivel.items() if s in ("vazio", "sem"))
        nasce = None
        if cheios and len(incompletos) == 1 and incompletos[0] < min(cheios):
            nasce = incompletos[0]                          # desenhado só em contorno no nível onde arranca : ainda não existe abaixo
        for i, est in sorted(por_nivel.items()):
            ip = niveis[i]["planta"]
            e = proprio.get((nome, ip))
            nota = None
            if i == nasce:
                continue
            if est == "cheio":
                sec, r0 = (e["a"], e["b"], e["area"], e["perimetro"], e["retangular"]), ref.get(nome)
                if r0 and abs(r0[0] - e["a"]) <= 0.02 and abs(r0[1] - e["b"]) <= 0.02:
                    sec = r0                                # mesma secção noutra planta, a menos do erro de leitura (1 cm)
            elif est == "parcial":
                r0 = ref.get(nome)
                if r0 and abs(r0[0] - e["a"]) <= 0.05:
                    sec, nota = r0, "trama parcial neste piso : secção igual à dos outros pisos"
                else:
                    sec, nota = (e["a"], e["b"], e["a"] * e["b"], 2 * (e["a"] + e["b"]), True), "trama parcial no desenho : considerado o retângulo envolvente"
            elif nome in ref:
                sec, nota = ref[nome], "sem trama neste piso : secção igual à dos outros pisos"
            elif est == "vazio":
                sec, nota = (e["a"], e["b"], e["area"], e["perimetro"], True), "desenhado só em contorno (sem trama)"
            else:
                perguntas.append(f"{nome} ({niveis[i]['nome']}) : etiqueta sem secção desenhada. Indique a secção.")
                continue
            ch = (nome, tipo_etiqueta(nome), sec[0], sec[1], _r(sec[2], 3), _r(sec[3], 2), bool(sec[4]))
            tramos[ch]["niveis"].append(i)
            if nota:
                tramos[ch]["notas"].add(nota)
        if nasce is not None:
            for ch, t in tramos.items():
                if ch[0] == nome:
                    t["notas"].add(f"nasce em «{niveis[nasce]['nome']}»")
    n_anon = 0
    for ip, p in enumerate(plantas):                        # peças sem etiqueta : contadas na sua planta, assinaladas
        for e in p["elementos"]:
            if e["etiquetado"]:
                continue
            n_anon += 1
            ch = (f"sem etiqueta {n_anon} ({niveis[idx_de[ip][0]]['nome']})", e["tipo"], e["a"], e["b"], _r(e["area"], 3), _r(e["perimetro"], 2), e["retangular"])
            tramos[ch]["niveis"] += idx_de[ip]
            tramos[ch]["notas"].add("sem etiqueta no desenho : confirmar se é estrutural")
    if n_anon:
        avisos.append(f"{n_anon} secção(ões) com trama mas sem etiqueta : contadas e assinaladas no mapa.")

    def ordem(ch):
        t = {"Pilar": 0, "Parede": 1, "Núcleo": 2}.get(ch[1], 3)
        return (t, re.sub(r"\d", "", ch[0]), int(re.sub(r"\D", "", ch[0].split("+")[0]) or 0), ch[0])
    verticais = []
    for ch in sorted(tramos, key=ordem):
        t = tramos[ch]
        ns = sorted(set(t["niveis"]))
        h_fixa = sum(niveis[i]["h_livre"] for i in ns if not niveis[i]["base"])
        na_base = any(niveis[i]["base"] for i in ns)
        h = h_fixa + (niveis[0]["h_livre"] if na_base else 0.0)
        verticais.append({"nome": ch[0], "tipo": ch[1], "a": ch[2], "b": ch[3], "area": ch[4], "perimetro": ch[5], "retangular": ch[6],
                          "niveis": [niveis[i]["nome"] for i in ns], "h_fixa": _r(h_fixa, 3), "tramo_base": na_base, "altura": _r(h, 3),
                          "betao": _r(ch[4] * h, 3), "cofragem": _r(ch[5] * h, 2), "notas": sorted(t["notas"])})

    # lajes
    lajes = []
    for i, n in enumerate(niveis):
        lj = plantas[n["planta"]]["laje"]
        aber = _r(sum(a["area"] for a in lj["aberturas"]))
        mod = lj["modulo"] or 0.0
        a_alig = _r(lj["moldes"] * mod * mod)
        a_liq = _r(lj["area_bruta"] - aber)
        e_eq = espessura_equivalente(n["e"], par["lamina"], mod, par["nervura"]) if lj["moldes"] else n["e"]
        betao = (a_liq - a_alig) * n["e"] + a_alig * e_eq
        lajes.append({"nivel": n["nome"], "zsup": n["zsup"], "e": n["e"], "area_bruta": lj["area_bruta"], "aberturas": aber,
                      "area": a_liq, "fora_do_perimetro": lj["area_fora_do_perimetro"], "moldes": lj["moldes"], "modulo": mod,
                      "area_aligeirada": a_alig, "area_macica": _r(a_liq - a_alig), "e_equivalente": _r(e_eq, 4), "betao": _r(betao, 2),
                      "perimetro": lj["perimetro"], "cofragem_fundo": a_liq, "cofragem_bordo": _r(lj["perimetro"] * n["e"])})
    if any(l["moldes"] for l in lajes):
        pressupostos.append({"nome": "Largura média da nervura entre moldes (para o betão da zona aligeirada)", "valor": par["nervura"], "un": "m"})
        pressupostos.append({"nome": "Lâmina de betão sobre os moldes" + ("" if m else " (não lida no desenho)"), "valor": par["lamina"], "un": "m"})
        perguntas.append("Zona aligeirada : confirme o betão por m² com a ficha do fabricante dos moldes "
                         f"(calculei com nervura média de {par['nervura']:.2f} m e lâmina de {par['lamina'] * 100:.1f} cm).")
    if any(l["aberturas"] for l in lajes):
        avisos.append("Aberturas deduzidas = interior dos núcleos (escadas / elevador). Confirme no desenho de controlo.")
    if any(l["fora_do_perimetro"] >= 1 for l in lajes):
        avisos.append("Há laje fora do perímetro dos pilares (consolas / varandas) : está contada com a espessura da laje. Confirme no desenho de controlo.")

    # vigas
    if h_vigas is not None:
        par["h_vigas"] = float(h_vigas)
    vigas, sem_h, sem_medida = [], 0, []
    for ip, p in enumerate(plantas):
        ns = idx_de[ip]
        if not ns:
            continue
        e = niveis[ns[0]]["e"]
        for v in p["vigas"]:
            h_lida = v["h"] is not None
            b = v["b"] if v["b"] is not None else v["b_medido"]
            h = v["h"] if h_lida else par["h_vigas"]
            sem_h += 0 if h_lida else 1
            queda = max(h - e, 0.0)
            vigas.append({"nome": v["nome"], "niveis": [niveis[i]["nome"] for i in ns], "n": len(ns), "b": b, "h": h, "h_lida": h_lida,
                          "b_lida": v["b"] is not None, "vao": v["vao"], "e_laje": e, "betao": _r(b * queda * v["vao"] * len(ns), 3),
                          "cofragem": _r(2 * queda * v["vao"] * len(ns), 2)})
        sem_medida += [f"{nome} ({niveis[ns[0]]['nome']})" for nome in p.get("vigas_sem_medida", [])]
    if sem_h:
        pressupostos.append({"nome": "Altura das vigas sem secção indicada", "valor": par["h_vigas"], "un": "m"})
        perguntas.append(f"{sem_h} viga(s) sem secção no desenho : medi a largura e assumi a altura de {par['h_vigas']:.2f} m. Indique a altura real.")
    if sem_medida:
        avisos.append("Vigas com etiqueta mas sem vão medido (traçado não reconhecido) : " + ", ".join(sem_medida[:20]) + ".")

    def soma(lst, k, cond=lambda x: True):
        return _r(sum(x[k] for x in lst if cond(x)))
    bp, bw = soma(verticais, "betao", lambda x: x["tipo"] == "Pilar"), soma(verticais, "betao", lambda x: x["tipo"] != "Pilar")
    bl, bv = soma(lajes, "betao"), soma(vigas, "betao")
    resumo = {"betao_pilares_m3": bp, "betao_paredes_nucleos_m3": bw, "betao_lajes_m3": bl, "betao_vigas_m3": bv, "betao_total_m3": _r(bp + bw + bl + bv),
              "cofragem_pilares_m2": soma(verticais, "cofragem", lambda x: x["tipo"] == "Pilar"),
              "cofragem_paredes_nucleos_m2": soma(verticais, "cofragem", lambda x: x["tipo"] != "Pilar"),
              "cofragem_lajes_fundo_m2": soma(lajes, "cofragem_fundo"), "cofragem_lajes_bordo_m2": soma(lajes, "cofragem_bordo"),
              "cofragem_vigas_m2": soma(vigas, "cofragem"), "moldes_un": int(sum(l["moldes"] for l in lajes)),
              "area_lajes_m2": soma(lajes, "area"),
              "aco_estimado_kg": round(bp * par["taxa_pilares"] + bw * par["taxa_paredes"] + bl * par["taxa_lajes"] + bv * par["taxa_vigas"]),
              "n_pilares": len({v["nome"] for v in verticais if v["tipo"] == "Pilar"}), "n_niveis": len(niveis), "n_vigas": len(vigas)}
    resumo["cofragem_total_m2"] = _r(sum(resumo[k] for k in resumo if k.startswith("cofragem_")))
    pressupostos.append({"nome": "Taxas de aço (estimativa, sem desenhos de armaduras) : lajes / pilares / paredes / vigas",
                         "valor": f"{par['taxa_lajes']:.0f} / {par['taxa_pilares']:.0f} / {par['taxa_paredes']:.0f} / {par['taxa_vigas']:.0f}", "un": "kg/m³"})
    return {"ok": True, "escala": leituras[0].get("escala"), "parametros": par, "niveis": niveis, "verticais": verticais, "lajes": lajes,
            "vigas": vigas, "resumo": resumo, "pressupostos": pressupostos, "perguntas": list(dict.fromkeys(perguntas)),
            "avisos": list(dict.fromkeys(avisos)),
            "fora_do_ambito": ["fundações (sapatas, betão de regularização)", "escadas", "armaduras detalhadas", "pisos que não estão nas plantas fornecidas"]}

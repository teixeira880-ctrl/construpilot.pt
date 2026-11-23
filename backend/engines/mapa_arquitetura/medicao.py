"""Consolidação : lê todas as folhas do DWFX, mede as plantas e os alçados e devolve o modelo do mapa de quantidades.
Só o que está desenhado : sem rácios. O que não se consegue medir fica nas perguntas / no «não incluído»."""
from __future__ import annotations

import re
from collections import Counter, defaultdict


from . import alcados, camadas, dwfx, plantas

PLANTA = re.compile(r"planta", re.I)
NAO_PISO = re.compile(r"implanta|arranjo|espa[cç]o p|cobertura|layer|caldeira|interven|localiza|perfil|pormenor", re.I)
ALCADO = re.compile(r"al[cç]ado", re.I)
MAX_FOLHAS = 40


def _nome_piso(nome: str) -> str:
    n = re.sub(r"^\s*planta\s+d[aoe]s?\s+", "", nome, flags=re.I).strip()
    return n[:1].upper() + n[1:] if n else nome


def medir(data: bytes, pe_direito: float | None = None, mapa_camadas: dict | None = None, nome_ficheiro: str = "") -> dict:
    if not dwfx.e_dwfx(data):
        return {"ok": False, "avisos": [f"{nome_ficheiro or 'ficheiro'} não é um DWFX (exportação DWFx do AutoCAD)."]}
    z = dwfx.abrir(data)
    lista = dwfx.folhas(z)
    pisos, vistas, avisos, sem_escala, papeis_usados = [], [], [], [], {}
    larguras = None
    lidas = []
    for i, (_, _, nome) in enumerate(lista[:MAX_FOLHAS]):
        if PLANTA.search(nome) and not NAO_PISO.search(nome):
            lidas.append(("planta", i, nome))
        elif ALCADO.search(nome) and not re.search(r"conjunto", nome, re.I):
            lidas.append(("alcado", i, nome))
    if len(lista) > MAX_FOLHAS:
        avisos.append(f"Só as primeiras {MAX_FOLHAS} folhas foram lidas.")
    for tipo, i, nome in [x for x in lidas if x[0] == "planta"]:
        f = dwfx.ler(z, i, lista)
        if not f.upm:
            sem_escala.append(nome); continue
        pap = camadas.mapa(f.camadas, mapa_camadas)
        papeis_usados.update({c: p for c, p in pap.items() if p})
        r = plantas.medir(f, pap)
        if not r.get("ok") or not r["compartimentos"]:
            avisos.append(f"{nome} : {r.get('aviso') or 'nenhum compartimento fechado'}.")
            continue
        pisos.append({"piso": _nome_piso(nome), "folha": nome, **r})
    # planta tipo = piso com mais área interior (fora cave/sótão) : dá a largura das fachadas para isolar o edifício nos alçados
    tipo = [p for p in pisos if not re.search(r"cave|s[oó]t[aã]o|garag|subsolo|desv[aã]o", p["piso"], re.I)] or pisos
    dims = Counter(p["_dims"] for p in tipo if p.get("_dims"))
    if dims:                                   # piso tipo = dimensões que se repetem ; senão o de menor envolvente
        larguras = dims.most_common(1)[0][0] if dims.most_common(1)[0][1] > 1 else min(dims, key=lambda d: d[0] * d[1])
    for p in pisos:
        p.pop("_dims", None)
    for tipo_, i, nome in [x for x in lidas if x[0] == "alcado"]:
        f = dwfx.ler(z, i, lista)
        if not f.upm:
            sem_escala.append(nome); continue
        pap = camadas.mapa(f.camadas, mapa_camadas)
        for v in alcados.medir(f, pap, larguras=larguras):
            if v["vaos"]:
                vistas.append(v)
    vistas, repetidas = alcados.sem_repetidas(vistas)
    for v in repetidas:
        avisos.append(f"{v['vista']} : mesma fachada que «{v['repete']}» — não somada (conferir).")
    if not pisos and not vistas:
        return {"ok": False, "avisos": avisos + (["Folhas sem escala do modelo (Units) : " + ", ".join(sem_escala)] if sem_escala else [])
                + ["Nenhuma planta nem alçado mensurável : confirmar que o DWFX foi exportado do espaço do modelo / layouts com escala."]}
    if sem_escala:
        avisos.append("Folhas sem escala, não medidas : " + ", ".join(sem_escala))
    alturas(pisos, pe_direito)
    if not pe_direito:
        try:                                     # cortes verticais : altura entre lajes medida na geometria (mais exata)
            from . import cortes
            ent = cortes.alturas_entre_lajes(z, lista, pisos, mapa_camadas)
            for p in pisos:
                el = ent.get(p["piso"]) if p.get("altura") else None
                if el:
                    p["piso_a_piso"] = p["altura"]
                    p["altura"] = el["entre_lajes"]
                    p["espessura_laje"] = el["espessura_laje"]
                    p["altura_origem"] = (f"cortes : entre lajes (laje {el['espessura_laje']:.2f}) ; cotas {p['cota']['valor']:.2f}, "
                                          f"piso a piso {p['piso_a_piso']:.2f}")
            for p in pisos:                      # último piso (sótão) : da laje à face inferior da cobertura, no corte
                c = (p.get("cota") or {}).get("valor")
                if p.get("altura") or c is None or not p["paredes"]:
                    continue
                pc = cortes.perfil_cobertura(z, lista, c, mapa_camadas)
                if pc:
                    p["altura"], p["perfil_cobertura"] = pc["h_media"], pc
                    p["altura_origem"] = (f"{pc['corte']} : laje → face inferior da cobertura, beirado {pc['h_min']:.2f}, cumeeira "
                                          f"{pc['h_max']:.2f}, média {pc['h_media']:.2f} em {pc['vao']:.2f} m ; empena sob a cobertura "
                                          f"{pc['area_perfil']:.2f} m² (triângulo + faixa)")
        except Exception as exc:  # noqa: BLE001
            avisos.append(f"Cortes não lidos ({type(exc).__name__}) : alturas piso a piso das cotas das plantas.")
    return _resumo(pisos, vistas, avisos, pe_direito, papeis_usados, [n for _, _, n in lista])


def alturas(pisos: list, pe_direito: float | None = None) -> None:
    """Altura das paredes de cada piso, sem perguntar : diferença entre a cota do pavimento deste piso e a do piso de cima
    (cotas escritas nas plantas). Cotas escolhidas em sequência crescente (cada piso acima do anterior). O último piso não tem
    piso de cima : fica sem altura (não se inventa). pe_direito indicado pelo utilizador sobrepõe-se a tudo."""
    # sequência de cotas : cada piso escolhe um candidato ; ligação entre pisos seguidos vale +5 se a diferença for 2–6 m
    # (pé-direito plausível) — as áreas escritas (27,75 m²…) e as cotas dos outros pisos não formam a sequência
    cands = [list(((p.get("cota") or {}).get("candidatos") or {}).items())[:8] + [(None, 0)] for p in pisos]
    best = [{v: (n, [v]) for v, n in cands[0]}] if pisos else []
    for i in range(1, len(pisos)):
        cur = {}
        for v, n in cands[i]:
            opts = []
            for u, (sc, path) in best[-1].items():
                ligado = u is not None and v is not None and 2.0 <= v - u <= 6.0
                incoerente = u is not None and v is not None and v <= u
                opts.append((sc + n + (5 if ligado else 0) - (100 if incoerente else 0), path + [v]))
            cur[v] = max(opts, key=lambda t: t[0])
        best.append(cur)
    escolha = max(best[-1].values(), key=lambda t: t[0])[1] if best else []
    for p, v in zip(pisos, escolha):
        cand = (p.get("cota") or {}).get("candidatos") or {}
        p["cota"] = {"valor": v, "ocorrencias": cand.get(v, 0) if v is not None else 0, "candidatos": cand}
    for i, p in enumerate(pisos):
        if pe_direito:
            p["altura"], p["altura_origem"] = pe_direito, "indicada pelo utilizador"
            continue
        a = p["cota"]["valor"]
        b = next((q["cota"]["valor"] for q in pisos[i + 1:] if q["cota"]["valor"] is not None), None)
        h = round(b - a, 2) if a is not None and b is not None else None
        if h is not None and 2.0 <= h <= 6.0:
            p["altura"], p["altura_origem"] = h, f"cotas das plantas {a:.2f} → {b:.2f} (piso a piso)"
        else:
            p["altura"], p["altura_origem"] = None, "sem cota do piso de cima nas plantas"


def _resumo(pisos, vistas, avisos, pe_direito, papeis, folhas_nomes) -> dict:
    interior = sum(c["area"] for p in pisos for c in p["compartimentos"] if not c["exterior"] and c["nome"] != "Caixa do elevador")
    exterior = sum(c["area"] for p in pisos for c in p["compartimentos"] if c["exterior"])
    sanit = sum(c["area"] for p in pisos for c in p["compartimentos"] if re.search(r"instala[cç][aã]o sanit|\bi\.?s\.?\b|wc|casa de banho", c["nome"], re.I))
    par = defaultdict(float)
    for p in pisos:
        for w in p["paredes"]:
            par[w["tipo"]] += w["comprimento"]
    portas_int = Counter(d["L"] for p in pisos for d in p["portas"] if d["tipo"] == "interior")
    vaos = [d for v in vistas for d in v["vaos"]]
    resumo = [
        {"artigo": "Pavimento interior (sem caixa do elevador)", "un": "m²", "qtd": round(interior, 2)},
        {"artigo": "  dos quais instalações sanitárias", "un": "m²", "qtd": round(sanit, 2)},
        {"artigo": "Varandas, terraços e áreas exteriores fechadas", "un": "m²", "qtd": round(exterior, 2)},
        {"artigo": "Tetos interiores (= pavimento interior)", "un": "m²", "qtd": round(interior, 2)},
        {"artigo": "Paredes de fachada (comprimento)", "un": "m", "qtd": round(par["fachada"], 2)},
        {"artigo": "Paredes interiores (comprimento)", "un": "m", "qtd": round(par["interior"], 2)},
        {"artigo": "Portas interiores", "un": "un", "qtd": sum(portas_int.values())},
        {"artigo": "Vãos exteriores nos alçados", "un": "un", "qtd": len(vaos)},
        {"artigo": "Vãos exteriores nos alçados (área)", "un": "m²", "qtd": round(sum(d["L"] * d["H"] for d in vaos), 2)},
    ]
    area = defaultdict(float)
    for p in pisos:
        if p.get("altura"):
            for w in p["paredes"]:
                area[w["tipo"]] += w["comprimento"] * p["altura"]
    if area:
        sem = [p["piso"] for p in pisos if not p.get("altura") and p["paredes"]]
        nota = f" (sem os pisos {', '.join(sem)} : sem altura)" if sem else ""
        resumo.insert(5, {"artigo": "Paredes de fachada — área bruta (altura de cada piso : folha Pressupostos), sem dedução de vãos" + nota, "un": "m²", "qtd": round(area["fachada"], 2)})
        resumo.insert(7, {"artigo": "Paredes interiores — área bruta (altura de cada piso : folha Pressupostos), sem dedução de portas" + nota, "un": "m²", "qtd": round(area["interior"], 2)})
    perguntas = [f"{v['vista']} : edifício isolado por estimativa — conferir os vãos no desenho de controlo." for v in vistas
                  if v.get("isolamento", "").startswith("estimado")]
    pressupostos = [
        "Medido no DWFX com a escala do modelo (Units do W2X) e as camadas do CAD ; nada estimado por rácio.",
        "Compartimentos fechados pelas paredes e pelas linhas de vão que tocam as paredes ; área à face interior das paredes.",
        "Nome do compartimento = rótulo da planta ; sem rótulo : loiças (instalação sanitária), equipamento (cozinha) ou paredes de 0,25 (caixa do elevador).",
        "Controlo cruzado : quando o arquiteto escreveu a área dentro do compartimento, ela aparece ao lado da medida (folha Compartimentos).",
        "Paredes = pares de linhas paralelas (0,07–0,45 m) na camada de paredes ; fachada / interior pelo lado dos compartimentos.",
        "Portas = arcos de abertura (largura = raio) ; a menos de 0,6 m do contorno exterior contam como porta de fachada.",
        "Vãos dos alçados = retângulo exterior do aro ; folhas encostadas juntas num vão ; o edifício é isolado na vista pelo seu contorno "
        "(duas linhas verticais com a largura da fachada lida na planta e o mesmo cimo) : vizinhos, chaminés acima das paredes e retângulos "
        "cheios de trama de terreno ficam de fora ; a mesma fachada desenhada duas vezes conta uma vez.",
    ]
    sem = [p["piso"] for p in pisos if not p.get("altura") and p["paredes"]]
    if sem:
        perguntas.append(f"Pisos sem cota do piso de cima nas plantas ({', '.join(sem)}) : altura das paredes por indicar (as outras foram lidas nas cotas).")
    pressupostos.append("Altura das paredes : cotas altimétricas de pavimento de cada piso lidas nas plantas (sequência coerente) ; "
                        "quando há cortes, a altura ENTRE LAJES é medida nas lajes cortadas (topo da laje do piso → face inferior da laje de "
                        "cima) ; sem corte, fica a altura piso a piso das cotas. Folha Pressupostos : origem de cada altura.")
    if not vistas:
        avisos.append("Nenhum alçado com vãos mensuráveis : vãos exteriores não medidos.")
    nao = ["ETICS / revestimentos de fachada por cor (rótulos de legenda por alçado)", "cobertura (pendentes lidas nos cortes), rufos, caleiras e tubos de queda",
           "fachadas da cave e empenas do sótão", "estrutura (usar medir_planta_estrutural com o PDF da estrutura)"]
    return {"ok": True, "resumo": resumo, "pisos": pisos, "alcados": vistas, "pe_direito": pe_direito,
            "camadas": papeis, "folhas": folhas_nomes, "pressupostos": pressupostos, "perguntas": perguntas,
            "avisos": avisos, "nao_incluido": nao}

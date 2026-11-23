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
    if not pisos and not vistas:
        return {"ok": False, "avisos": avisos + (["Folhas sem escala do modelo (Units) : " + ", ".join(sem_escala)] if sem_escala else [])
                + ["Nenhuma planta nem alçado mensurável : confirmar que o DWFX foi exportado do espaço do modelo / layouts com escala."]}
    if sem_escala:
        avisos.append("Folhas sem escala, não medidas : " + ", ".join(sem_escala))
    return _resumo(pisos, vistas, avisos, pe_direito, papeis_usados, [n for _, _, n in lista])


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
    if pe_direito:
        resumo.insert(6, {"artigo": f"Paredes interiores (área bruta, altura {pe_direito:.2f} m, sem dedução de portas)", "un": "m²",
                          "qtd": round(par["interior"] * pe_direito, 2)})
    perguntas, pressupostos = [], [
        "Medido no DWFX com a escala do modelo (Units do W2X) e as camadas do CAD ; nada estimado por rácio.",
        "Compartimentos fechados pelas paredes e pelas linhas de vão que tocam as paredes ; área à face interior das paredes.",
        "Nome do compartimento = rótulo da planta ; sem rótulo : loiças (instalação sanitária), equipamento (cozinha) ou paredes de 0,25 (caixa do elevador).",
        "Controlo cruzado : quando o arquiteto escreveu a área dentro do compartimento, ela aparece ao lado da medida (folha Compartimentos).",
        "Paredes = pares de linhas paralelas (0,07–0,45 m) na camada de paredes ; fachada / interior pelo lado dos compartimentos.",
        "Portas = arcos de abertura (largura = raio) ; a menos de 0,6 m do contorno exterior contam como porta de fachada.",
        "Vãos dos alçados = retângulo exterior do aro ; folhas encostadas juntas num vão ; vizinhos separados pela largura da fachada da planta tipo.",
    ]
    if not pe_direito:
        perguntas.append("Qual é a altura entre lajes (ou o pé-direito) para passar as paredes de metros a m² ?")
    if any(v for v in vistas):
        perguntas.append("Conferir no desenho de controlo se cada alçado ficou só com o edifício (sem vizinhos nem muros).")
    if not vistas:
        avisos.append("Nenhum alçado com vãos mensuráveis : vãos exteriores não medidos.")
    nao = ["ETICS / revestimentos de fachada por cor (rótulos de legenda por alçado)", "cobertura (pendentes lidas nos cortes), rufos, caleiras e tubos de queda",
           "fachadas da cave e empenas do sótão", "estrutura (usar medir_planta_estrutural com o PDF da estrutura)"]
    return {"ok": True, "resumo": resumo, "pisos": pisos, "alcados": vistas, "pe_direito": pe_direito,
            "camadas": papeis, "folhas": folhas_nomes, "pressupostos": pressupostos, "perguntas": perguntas,
            "avisos": avisos, "nao_incluido": nao}

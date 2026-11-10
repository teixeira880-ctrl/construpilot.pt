"""Rastreio ao vivo do piloto automático de licenciamento (página /acompanhamento-calculo, conta CLT Rezult).

Só escreve quando há um tracer ativo (engines.calc_live); para todas as outras contas cada função sai logo.
Nada aqui calcula de novo: mostra os valores que os motores usaram, com a fonte, a fórmula e o porquê.
"""
from __future__ import annotations

from typing import Any, Dict, List

from engines import calc_live as CL
from engines.urbanismo_pt.auto import programa as PG

ev, n = CL.ev, CL.num
M = "licenciamento_automatico"


def _fonte(r: Dict[str, Any]) -> str:
    return (r or {}).get("fonte") or ""


async def pedido(p: Dict[str, Any]) -> None:
    if not CL.ativo():
        return
    await ev("etapa", "0. Ler o pedido", motor=M)
    vals = {k: (v if not isinstance(v, dict) else ", ".join(f"{a}={b}" for a, b in v.items()))
            for k, v in p.items() if k not in ("texto",) and v not in (None, "")}
    await ev("dado", "Dados extraídos do pedido (frase do utilizador + argumentos do Assistente)", valores=vals,
             porque="O motor usa só o que foi dito; tudo o que falta é assumido de forma prudente e registado como pressuposto.")


async def localizacao(geo: Dict[str, Any], g: Dict[str, Any]) -> None:
    if not CL.ativo():
        return
    await ev("etapa", "1. Localizar o terreno", motor=M)
    await ev("dado", "Morada localizada", fonte=_fonte(g), url=g.get("url"),
             valores={"morada encontrada": geo.get("morada_formatada"), "latitude": n(geo.get("lat"), 6),
                      "longitude": n(geo.get("lon"), 6), "freguesia": geo.get("freguesia"), "concelho": geo.get("concelho"),
                      "código postal": geo.get("codigo_postal"), "precisão": geo.get("precisao")},
             porque="Este ponto é a base de todas as consultas oficiais (PDM, servidões, cadastro, altimetria, ortofoto).")
    if geo.get("precisao") != "porta":
        await ev("aviso", f"Porta exata não encontrada: usada a {geo.get('precisao')} como referência — confirmar o terreno no mapa.")


async def dados_oficiais(mun, crus, srup, cad, via, orto) -> None:
    if not CL.ativo():
        return
    await ev("etapa", "2. Ler os dados oficiais (consultas em paralelo)", motor=M)
    nomes = (("Município / freguesia (CAOP)", mun), ("Classe de espaço do PDM (CRUS, DGT)", crus),
             ("Servidões e restrições (REN, RAN, domínio hídrico…)", srup), ("Cadastro predial", cad),
             ("Via pública mais próxima", via), ("Ortofotomapa oficial", orto))
    for titulo, r in nomes:
        d = (r or {}).get("data") or {}
        vals: Dict[str, Any] = {"estado": "lido" if r.get("ok") else "indisponível"}
        if titulo.startswith("Município"):
            vals.update({"concelho": d.get("concelho"), "freguesia": d.get("freguesia"), "distrito": d.get("distrito")})
        elif titulo.startswith("Classe"):
            vals.update({"solo": d.get("solo"), "classe": d.get("classe"), "categoria": d.get("categoria")})
        elif titulo.startswith("Servidões"):
            vals["restrições encontradas"] = len(d.get("afetado_por") or [])
            if d.get("incompleta"):
                vals["camadas sem resposta"] = len(d.get("nao_consultadas") or [])
        elif titulo.startswith("Via"):
            vals.update({"nome": d.get("nome"), "distância ao ponto": n(d.get("distancia_m"), 1, "m")})
        elif titulo.startswith("Cadastro") and d:
            vals.update({k: d.get(k) for k in ("area_m2", "referencia", "fonte_parcela") if d.get(k) is not None})
        if (d.get("copia_local")):
            vals["origem"] = "cópia local dos dados DGT (serviço sem resposta)"
        await ev("dado", titulo, fonte=_fonte(r), url=(r or {}).get("url"), valores=vals,
                 nota=(r or {}).get("nota") if not r.get("ok") else None)
    for h in (srup.get("data") or {}).get("afetado_por") or []:
        await ev("dado", f"Restrição na envolvente: {h.get('titulo') or h.get('id')}", fonte=_fonte(srup))


async def viabilidade(classe, bloqueios: List[str], avisos: List[str], por_confirmar: List[str]) -> None:
    if not CL.ativo():
        return
    await ev("etapa", "3. Viabilidade: posso construir aqui?", motor=M)
    if classe:
        await ev("verificacao", "Solo urbano (moradia nova admitida pelo PDM)", ok=classe.get("solo") != "rustico",
                 valores={"classe do PDM": " — ".join(x for x in (classe.get("classe"), classe.get("categoria")) if x) or classe.get("solo")},
                 norma="RJIGT (DL 80/2015) — classificação do solo; regulamento do PDM",
                 porque="Em solo rústico uma moradia nova só é admitida em casos excecionais.")
    else:
        await ev("verificacao", "Classe do PDM confirmada", ok=None, porque="CRUS (DGT) sem resposta: fica por confirmar na planta de ordenamento.")
    for b in bloqueios:
        await ev("verificacao", b, ok=False)
    if not bloqueios:
        await ev("verificacao", "Sem REN / RAN sobre o terreno", ok=None if por_confirmar else True,
                 porque="Nenhuma servidão impeditiva encontrada" + (f"; por confirmar: {', '.join(por_confirmar)}" if por_confirmar else "."))


async def terreno(ter: Dict[str, Any], topo: Dict[str, Any], el: Dict[str, Any]) -> None:
    if not CL.ativo():
        return
    await ev("etapa", "4. Terreno e topografia", motor=M)
    await ev("calculo", "Área do terreno", resultado=n(ter.get("area_m2"), 1, "m²"),
             valores={"origem da área": ter.get("area_origem"), "frente": n(ter.get("plot_l_m"), 2, "m"),
                      "profundidade": n(ter.get("plot_w_m"), 2, "m"), "frente obtida de": ter.get("frente_fonte"),
                      "retangular": ter.get("retangular")},
             formula="polígono do terreno (frente × profundidade ajustadas à área)",
             porque="A área declarada pelo utilizador manda; sem ela usa-se o cadastro; sem cadastro é uma hipótese marcada.")
    if topo and topo.get("ok"):
        await ev("calculo", "Declive do terreno", resultado=n(topo.get("declive_pct"), 1, "%"),
                 formula="plano de regressão z = a + b·x + c·y pelos mínimos quadrados (grelha 9 × 9 de cotas)",
                 valores={"cota mínima": n(topo.get("z_min"), 2, "m"), "cota máxima": n(topo.get("z_max"), 2, "m"),
                          "cota média": n(topo.get("z_medio"), 2, "m"), "erro RMS do plano": n(topo.get("rms_m"), 2, "m"),
                          "o terreno desce para": topo.get("descida")},
                 fonte=(el or {}).get("fonte"))
    else:
        await ev("pressuposto", "Altimetria indisponível: terreno assumido plano (o levantamento topográfico é obrigatório).")


async def alvos(alv: Dict[str, Any]) -> None:
    if not CL.ativo():
        return
    await ev("etapa", "5. Programa, implantação e plantas", motor=M)
    for k, v in (alv.get("valores") or {}).items():
        await ev("pressuposto", f"{k.replace('_', ' ')} = {n(v, 2)}", valores={"origem": (alv.get("origem") or {}).get(k)},
                 porque="Parâmetro do PDM quando existe em dados abertos; senão o valor prudente.")


async def programa(prog: Dict[str, Any], np_: int, gar_: bool, lug_: int) -> None:
    if not CL.ativo():
        return
    await ev("calculo", f"Programa {prog['tipologia']} em {np_} piso(s)" + (f", garagem {lug_} lugar(es)" if gar_ else ", sem garagem"),
             formula=f"área bruta = Σ áreas úteis × (1 + {n(PG.CIRCULACAO, 2)} circulação) × {n(PG.COEF_BRUTA, 2)} (paredes)",
             resultado=n(prog.get("area_bruta_total_m2"), 1, "m²"),
             valores={"compartimentos": len(prog.get("compartimentos") or []),
                      "área bruta por piso": n(prog.get("area_bruta_por_piso_m2"), 1, "m²"),
                      "mínimo RGEU": n(prog.get("minimo_area_bruta_m2"), 1, "m²"),
                      "área pedida (alvo desta tentativa)": n(prog.get("area_alvo_m2"), 1, "m²") if prog.get("area_alvo_m2") else None,
                      "fator aplicado às áreas de conforto": n(prog.get("escala_areas"), 3) if prog.get("escala_areas") else None},
             norma=prog.get("fonte_minimos"))
    if prog.get("minimo_area_bruta_m2"):
        await ev("verificacao", "Área bruta ≥ mínimo do RGEU para a tipologia", ok=prog["area_bruta_total_m2"] >= prog["minimo_area_bruta_m2"],
                 valores={"obtido": n(prog["area_bruta_total_m2"], 1, "m²"), "mínimo": n(prog["minimo_area_bruta_m2"], 1, "m²")},
                 norma=prog.get("fonte_minimos"))


async def variante(np_: int, gar_: bool, lug_: int, res: Dict[str, Any]) -> None:
    if not CL.ativo():
        return
    desc = f"{np_} piso(s)" + (f" + garagem {lug_}" if gar_ else " sem garagem")
    if res.get("ok"):
        await ev("decisao", f"Variante aceite: {desc}", porque="Cabe na zona edificável com os afastamentos e as plantas cumprem os mínimos.")
    else:
        await ev("decisao", f"Variante rejeitada: {desc}", porque=res.get("motivo") or "não cabe")


async def implantacao(res: Dict[str, Any], plan: Dict[str, Any]) -> None:
    if not CL.ativo():
        return
    v = res.get("volume") or {}
    await ev("calculo", "Implantação da moradia", resultado=f"{n(v.get('footprint_l_m'), 2)} × {n(v.get('footprint_w_m'), 2)} m",
             valores={"zona edificável (terreno − afastamentos)": n(res.get("zona_edificavel_m2"), 1, "m²"),
                      "recuo frontal": n(v.get("setback_front_m"), 2, "m"), "recuo lateral": n(v.get("setback_side_m"), 2, "m"),
                      "pisos": v.get("levels"), "pé-direito piso a piso": n(v.get("storey_h_m"), 2, "m"),
                      "cota de soleira": n(res.get("cota_soleira_m"), 2, "m"), "fachada ao sol": res.get("fachada_sol"),
                      "garagem do lado": res.get("lado_garagem") if v.get("blocks") else "—"},
             formula="maior retângulo que cabe na zona edificável, rodado para a melhor exposição solar")
    t = res.get("terras") or {}
    if t:
        await ev("calculo", "Movimento de terras (plano médio)", valores={k.replace("_", " "): n(x, 1) if isinstance(x, (int, float)) else x for k, x in t.items()})
    for d in res.get("decisoes") or []:
        await ev("decisao", d)
    for p in (plan or {}).get("pisos") or []:
        comps = p.get("compartimentos") or []
        await ev("resultado", f"Planta do piso {p.get('piso', '')}: {len(comps)} compartimentos",
                 valores={c.get("nome") or c.get("tipo"): n((c["x1"] - c["x0"]) * (c["y1"] - c["y0"]), 1, "m²") for c in comps[:30] if "x1" in c})


async def verificacao(verif: Dict[str, Any]) -> None:
    if not CL.ativo():
        return
    await ev("etapa", "6. Verificação urbanística (PDM, RGEU, RJUE)", motor=M)
    q = verif.get("quadro") or {}
    if q:
        at = q.get("area_terreno_m2")
        await ev("calculo", "Índice de ocupação (Io)", formula="Io = área de implantação / área do terreno × 100",
                 valores={"área de implantação": n(q.get("area_implantacao_m2"), 2, "m²"), "área do terreno": n(at, 2, "m²")},
                 resultado=n(q.get("indice_ocupacao_pct"), 2, "%"))
        await ev("calculo", "Índice de utilização (Iu)", formula="Iu = área de construção / área do terreno",
                 valores={"área de construção": n(q.get("area_construcao_m2"), 2, "m²"), "área do terreno": n(at, 2, "m²")},
                 resultado=n(q.get("indice_utilizacao"), 3, "m²/m²"))
        await ev("calculo", "Alturas", valores={"altura da fachada": n(q.get("altura_fachada_m"), 2, "m"),
                                               "altura total": n(q.get("altura_total_m"), 2, "m"), "pisos": q.get("n_pisos")})
    for i in verif.get("verificacoes") or []:
        r = i.get("resultado")
        f = i.get("fonte") or {}
        await ev("verificacao", i.get("titulo") or i.get("codigo"),
                 ok=True if r == "conforme" else (False if r == "nao_conforme" else None),
                 valores={"obtido": n(i.get("valor"), 2, i.get("unidade") or ""), "limite": n(i.get("limite"), 2, i.get("unidade") or ""),
                          "resultado": (r or "").replace("_", " ")},
                 norma=" — ".join(x for x in (f.get("diploma"), f.get("artigo")) if x), nota=i.get("nota"))
    rj = verif.get("rjue") or {}
    await ev("decisao", f"Procedimento: {str(rj.get('procedimento') or '').replace('_', ' ')}",
             porque=rj.get("titulo_regra"), norma=rj.get("fundamento_legal"),
             valores={"técnicos obrigatórios": ", ".join(rj.get("tecnicos_obrigatorios") or []) or None})


async def memoria(sem_fonte: List[str]) -> None:
    if not CL.ativo():
        return
    await ev("etapa", "7. Memória descritiva (texto determinístico)", motor=M)
    await ev("verificacao", "Todos os números da memória existem nos dados do processo", ok=not sem_fonte,
             valores={"números sem fonte": ", ".join(map(str, sem_fonte)) or "nenhum"},
             porque="Nunca há números inventados num documento: cada número citado é procurado nos resultados dos motores.")


async def coerencia(coer: Dict[str, Any]) -> None:
    if not CL.ativo():
        return
    await ev("etapa", "8. Coerência entre motores (recálculo independente)", motor=M)
    await ev("dado", "Método", porque="Cada número final é refeito por um caminho independente (geometria exata com shapely, a partir dos "
             "polígonos e das plantas) e comparado com o do motor; tolerância 0,5 % / 2 cm.")
    for c in coer.get("checks") or coer.get("verificacoes") or []:
        await ev("verificacao", c.get("descricao") or c.get("codigo"), ok=c.get("ok"),
                 valores={"recalculado": n(c.get("esperado"), 2) if not isinstance(c.get("esperado"), (list, dict)) else str(c.get("esperado"))[:200],
                          "do motor": n(c.get("obtido"), 2) if not isinstance(c.get("obtido"), (list, dict)) else str(c.get("obtido"))[:200]},
                 nota=c.get("nota"))
    await ev("resultado", f"Coerência: {coer.get('aprovados')}/{coer.get('total')} verificações aprovadas")


async def fim(estado: str, pressupostos: List[str], avisos: List[str], perguntas: List[str]) -> None:
    if not CL.ativo():
        return
    await ev("etapa", "9. Conclusão", motor=M)
    for p in pressupostos:
        await ev("pressuposto", p)
    for a in avisos:
        await ev("aviso", a)
    for q in perguntas:
        await ev("aviso", "Pergunta ao utilizador: " + q)
    await ev("resultado", "Processo " + ("PRONTO" if estado == "pronto" else "a REVER antes de exportar"),
             porque="«Pronto» só com coerência total, sem bloqueios e com PDM / servidões confirmados.")

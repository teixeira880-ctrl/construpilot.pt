"""Confiança por divisão e verificações cruzadas — cada número diz em que se apoia.

Verde: escala confirmada E área calculada = área escrita (≤ 2 %), ou escala confirmada numa fonte vetorial exata.
Laranja: geometria fechada mas só uma fonte de escala, ou sem área escrita para comparar numa digitalização.
Vermelho: área escrita em desacordo (> 5 %), escala em conflito, ou divisão estreita / suspeita.
"""
from __future__ import annotations

TOL_VERDE, TOL_VERMELHO = .02, .05


def avaliar(analise: dict, escala: dict, fonte: str, cotas_globais: list[float] | None = None) -> dict:
    estado_escala = escala.get("estado")
    exata = fonte in ("dxf", "pdf_vetorial")
    divisoes = []
    for d in analise.get("divisoes", []):
        motivos = []
        escrita = d.get("areas_escritas_m2") or []
        area = d["area_m2"]
        desvio = None
        if escrita:
            alvo = min(escrita, key=lambda a: abs(a - area))
            desvio = (area - alvo) / alvo
        if estado_escala in ("conflito", "desconhecida"):
            nivel = "vermelho"
            motivos.append("escala não estabelecida")
        elif desvio is not None and abs(desvio) > TOL_VERMELHO:
            nivel = "vermelho"
            motivos.append(f"área escrita {alvo:.2f} m² ≠ calculada {area:.2f} m² ({desvio * 100:+.1f} %)")
        elif desvio is not None and abs(desvio) <= TOL_VERDE and estado_escala == "confirmada":
            nivel = "verde"
            motivos.append(f"área escrita confirmada ({desvio * 100:+.1f} %)")
        elif estado_escala == "confirmada" and exata:
            nivel = "verde"
            motivos.append("geometria vetorial exata, escala confirmada")
        else:
            nivel = "laranja"
            if desvio is not None:
                motivos.append(f"área escrita a {desvio * 100:+.1f} %")
            if estado_escala != "confirmada":
                motivos.append("escala de uma só fonte")
            if not exata:
                motivos.append("leitura de imagem: confirmar visualmente")
        divisoes.append({"nivel": nivel, "motivos": motivos, "desvio_area_escrita": None if desvio is None else round(desvio, 4)})
    verificacoes = []
    impl = analise.get("area_implantacao_m2")
    par = analise.get("paredes") or {}
    soma = sum(d["area_m2"] for d in analise.get("divisoes", []))
    if impl:
        verificacoes.append({"id": "fecho_areas", "ok": abs(soma + (par.get("area_paredes_m2") or 0) - impl) <= .005 * impl,
                             "texto": f"divisões {soma:.2f} + paredes {par.get('area_paredes_m2', 0):.2f} = implantação {impl:.2f} m²"})
    caixa = analise.get("caixa_m")
    if caixa and cotas_globais:
        for lado, nome in ((max(caixa), "comprimento"), (min(caixa), "largura")):
            perto = min(cotas_globais, key=lambda c: abs(c - lado))
            ok = abs(perto - lado) <= max(.02, .005 * lado)
            verificacoes.append({"id": f"cota_{nome}", "ok": ok,
                                 "texto": f"{nome} exterior medido {lado:.2f} m {'=' if ok else '≠'} cota {perto:.2f} m"})
    esp = par.get("espessura_exterior_m")
    if esp is not None:
        verificacoes.append({"id": "espessura_exterior", "ok": .08 <= esp <= .65, "texto": f"parede exterior {esp * 100:.0f} cm"})
    sem_nome = sum(1 for d in analise.get("divisoes", []) if not d.get("nomes"))
    if analise.get("divisoes"):
        verificacoes.append({"id": "nomes", "ok": sem_nome == 0, "texto": f"{len(analise['divisoes']) - sem_nome}/{len(analise['divisoes'])} divisões com nome lido"})
    niveis = [d["nivel"] for d in divisoes]
    resumo = {n: niveis.count(n) for n in ("verde", "laranja", "vermelho")}
    global_ = "vermelho" if resumo["vermelho"] else ("laranja" if resumo["laranja"] else ("verde" if niveis else "vermelho"))
    if any(not v["ok"] for v in verificacoes if v["id"].startswith("cota_") or v["id"] == "fecho_areas") and global_ == "verde":
        global_ = "laranja"
    return {"divisoes": divisoes, "verificacoes": verificacoes, "resumo": resumo, "nivel_global": global_}

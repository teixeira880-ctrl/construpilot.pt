"""Piloto automático: pedido simples → processo de licenciamento completo, verificado.

Etapas: localizar → dados oficiais (PDM, servidões, cadastro, via, ortofoto) → viabilidade → terreno e topografia →
programa → implantação + plantas (com variantes até caber) → processo → verificação (urbanismo + RJUE) → memória →
guarda de coerência. Cada etapa fica registada (`etapas`), cada hipótese em `pressupostos`, cada fonte em `fontes`.
"""
from __future__ import annotations

import asyncio
import os
import base64
import io
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from engines.urbanismo_pt import regras as R
from engines.urbanismo_pt.auto import coerencia as C
from engines.urbanismo_pt.auto import geo as G
from engines.urbanismo_pt.auto import implantacao as I
from engines.urbanismo_pt.auto import pecas_auto as PA
from engines.urbanismo_pt.auto import plantas as PL
from engines.urbanismo_pt.auto import programa as PG
from engines.urbanismo_pt.auto import terreno as T

Emit = Optional[Callable[[str, str], Awaitable[None]]]

ETAPAS = ["localizar", "dados_oficiais", "viabilidade", "terreno", "projeto", "verificacao", "documentos", "coerencia"]


def _bool(v, d=None):
    if isinstance(v, bool):
        return v
    if v is None or v == "":
        return d
    return str(v).strip().lower() in ("1", "true", "sim", "yes", "s", "y", "oui")


def interpretar_pedido(texto: str) -> Dict[str, Any]:
    """Extrai de uma frase simples os dados que já estão lá (morada, tipologia, pisos, garagem, materiais)."""
    t = texto or ""
    out: Dict[str, Any] = {}
    m = re.search(r"\b[Tt]\s?([0-6])\b", t)
    if m:
        out["tipologia"] = f"T{m.group(1)}"
    if re.search(r"t[ée]rrea|um s[óo] piso|1 piso|plain-pied", t, re.I):
        out["pisos"] = 1
    elif re.search(r"\b(2|dois) pisos\b|andar", t, re.I):
        out["pisos"] = 2
    if re.search(r"sem garagem", t, re.I):
        out["garagem"] = False
    elif re.search(r"garagem", t, re.I):
        out["garagem"] = True
    for k, rgx in (("fachada", r"(granito|madeira|xisto|tijolo|bet[ãa]o|reboco|branc[ao])"),):
        found = re.findall(rgx, t, re.I)
        if found:
            out[k] = " ".join(found)
    m = re.search(r"(\d[\d .]*)\s*m(?:²|2|etros quadrados)", t, re.I)
    if m:
        try:
            out["area_terreno_m2"] = float(m.group(1).replace(" ", "").replace(".", ""))
        except ValueError:
            pass
    # morada: depois de «na/no/em» até ao fim (sem «município de»)
    m = re.search(r"\b(?:na|no|em|sito em|situad[oa] em)\s+((?:rua|avenida|av\.|travessa|largo|estrada|caminho|lugar|praça|"
                  r"urbaniza[çc][ãa]o|quinta)\b.+)$", t, re.I)
    if m:
        out["morada"] = re.sub(r"\s+", " ", m.group(1)).strip(" .")
    return out


async def executar(pedido: Dict[str, Any], emit: Emit = None) -> Dict[str, Any]:
    p = {**interpretar_pedido(pedido.get("texto") or ""), **{k: v for k, v in pedido.items() if v not in (None, "")}}
    etapas: List[Dict[str, Any]] = []
    pressupostos: List[str] = []
    fontes: List[Dict[str, Any]] = []
    avisos: List[str] = []

    async def passo(nome, estado, detalhe=""):
        etapas.append({"etapa": nome, "estado": estado, "detalhe": detalhe})
        if emit:
            try:
                await emit(nome, detalhe or estado)
            except Exception:  # noqa: BLE001
                pass

    def fonte(r):
        if r and r.get("ok") and r.get("fonte"):
            fontes.append({"fonte": r["fonte"], "url": r.get("url")})

    morada = (p.get("morada") or "").strip()
    if not morada:
        return {"ok": False, "estado": "falta_morada", "perguntas": ["Qual é a morada do terreno (rua, número, freguesia e concelho)?"]}

    # 1. localizar
    g = await G.geocode(morada)
    if not g["ok"]:
        inacessivel = "inacess" in (g.get("nota") or "")
        await passo("localizar", "falhou", g.get("nota") or "morada não encontrada")
        if inacessivel:
            return {"ok": False, "estado": "servico_indisponivel", "etapas": etapas, "motivo": g.get("nota"),
                    "perguntas": ["Os serviços de mapas não responderam agora. Tente de novo dentro de um minuto."]}
        return {"ok": False, "estado": "morada_nao_encontrada", "etapas": etapas, "motivo": g.get("nota"),
                "perguntas": ["Não encontrei esta morada. Pode indicar o código postal ou um ponto de referência próximo?"]}
    geo = g["data"]
    fonte(g)
    if geo.get("freguesia_divergente"):
        if geo.get("freguesia_motivo") == "vizinha":
            pressupostos.append(f"A rua indicada fica na freguesia vizinha ({geo.get('freguesia') or geo.get('morada_formatada')}), "
                                f"não em {geo['freguesia_divergente']}: é a única com este nome no concelho, a cerca de "
                                f"{geo.get('distancia_freguesia_m', 0) / 1000:.1f} km. Confirme no mapa que é o seu terreno.")
        else:
            pressupostos.append(f"O OpenStreetMap indica outra freguesia para esta rua («{geo.get('morada_formatada')}»), mas a "
                                f"carta oficial de freguesias (CAOP) confirma que o ponto fica em {geo.get('freguesia')}.")
    if geo.get("precisao") != "porta":
        pressupostos.append(f"A localização exata da porta não foi encontrada: usou-se o ponto da {geo.get('precisao')} "
                            f"«{geo.get('morada_formatada')}». Confirme o terreno no mapa.")
    await passo("localizar", "ok", geo.get("morada_formatada", ""))
    lat, lon = geo["lat"], geo["lon"]

    # 2. dados oficiais em paralelo
    mun, crus, srup, cad, via, orto = await asyncio.gather(
        G.municipio(lat, lon), G.crus(lat, lon), G.servidoes(lat, lon), G.cadastro(lat, lon), G.via_proxima(lat, lon),
        G.ortofoto(lat, lon))
    if not via["ok"] and geo.get("via_geom"):
        via = G.via_de_geometria(lat, lon, geo["via_geom"], geo.get("rua"))
    if not via["ok"] and geo.get("precisao") != "localidade":
        via = await G.via_reversa(lat, lon)
    # DGT em baixo (ocorre por minutos): uma nova tentativa da classe do PDM e das servidões antes de desistir
    if not crus["ok"] and "indispon" in (crus.get("nota") or "") or not srup["ok"]:
        await asyncio.sleep(8)
        G._COLLECTIONS.update(t=0.0)
        if not crus["ok"]:
            crus = await G.crus(lat, lon)
        if not srup["ok"]:
            srup = await G.servidoes(lat, lon)
        if not mun["ok"]:
            mun = await G.municipio(lat, lon)
        if not orto["ok"]:
            orto = await G.ortofoto(lat, lon)
    for r in (mun, crus, srup, cad, via, orto):
        fonte(r)
    copias = [ (r.get("data") or {}).get("copia_local") for r in (crus, srup) if r["ok"] ]
    copias = [c for c in copias if c]
    if copias:
        avisos.append("O serviço da DGT não respondeu: a classe do PDM e as servidões vêm da cópia local de "
                      f"{G.CACHE.data_txt(min(copias))} (dados oficiais da DGT). Confirme se houve alteração do PDM desde então.")
    elif crus["ok"] and G._fetch is G._http and os.environ.get("DGT_PREFETCH", "1") != "0":
        # a DGT está a responder: guardar a zona para quando falhar (em segundo plano, não atrasa o pedido)
        asyncio.get_running_loop().create_task(G.prefetch_zona(lat, lon))
    concelho = (mun.get("data") or {}).get("concelho") if mun["ok"] else None
    concelho = concelho or geo.get("concelho")
    await passo("dados_oficiais", "ok", ", ".join(f["fonte"] for f in fontes))

    # 3. viabilidade (sem esconder nada)
    bloqueios: List[str] = []
    classe = crus.get("data") if crus["ok"] else None
    if classe and classe["solo"] == "rustico":
        bloqueios.append(f"O PDM classifica o terreno como SOLO RÚSTICO ({classe.get('categoria') or classe.get('classe') or ''}). "
                         "Em solo rústico a construção de uma moradia nova só é admitida em situações excecionais previstas no "
                         "regulamento do PDM (p. ex. explorações agrícolas). Não é possível preparar um licenciamento normal.")
    elif not classe:
        avisos.append("A classe de espaço do PDM não pôde ser confirmada automaticamente (CRUS indisponível): "
                      "confirmar na planta de ordenamento do PDM antes de avançar.")
    hits = (srup.get("data") or {}).get("afetado_por") if srup["ok"] else []
    for h in hits or []:
        tit = (h.get("titulo") or h.get("id") or "").lower()
        if re.search(r"\bren\b|reserva ecol", tit) or re.search(r"\bran\b|reserva agr", tit):
            bloqueios.append(f"O terreno (ou a sua envolvente próxima) está abrangido por «{h['titulo'] or h['id']}». "
                             "Construir em REN/RAN exige parecer prévio da entidade competente e, em regra, não é permitido.")
        else:
            avisos.append(f"Servidão ou restrição na envolvente: «{h['titulo'] or h['id']}» — confirmar a distância e o parecer necessário.")
    if not srup["ok"]:
        avisos.append("Não foi possível consultar as servidões e restrições (REN, RAN, domínio hídrico…): confirmar na câmara.")
    elif (srup.get("data") or {}).get("incompleta"):
        falt = ", ".join(c.get("titulo") or c.get("id") for c in srup["data"].get("nao_consultadas", [])[:6])
        avisos.append(f"Algumas servidões não responderam e ficaram por confirmar ({falt}): confirmar na câmara antes de avançar.")
    if geo.get("precisao") == "localidade":
        avisos.append("Só foi encontrada a localidade, não a rua: a classe do PDM e as servidões referem-se ao centro da localidade, "
                      "não ao terreno. Confirme a localização exata antes de usar este estudo.")
    # dados críticos que não puderam ser confirmados: o processo nunca é dado como «pronto» sem eles
    por_confirmar = ([] if classe else ["classe do PDM (CRUS)"]) \
        + ([] if srup["ok"] and not (srup.get("data") or {}).get("incompleta") else ["servidões e restrições (REN, RAN…)"]) \
        + (["localização do terreno"] if geo.get("precisao") == "localidade" else [])
    criticos_por_confirmar = bool(por_confirmar)
    await passo("viabilidade", "bloqueado" if bloqueios else ("atencao" if criticos_por_confirmar else "ok"), "; ".join(bloqueios)[:300])
    if bloqueios and not _bool(p.get("forcar_estudo"), False):
        return {"ok": False, "estado": "inviavel", "bloqueios": bloqueios, "avisos": avisos, "etapas": etapas,
                "fontes": fontes, "localizacao": geo,
                "resposta": "Encontrei um impedimento sério antes de desenhar a casa: " + " ".join(bloqueios)}

    # 4. terreno e topografia
    ter = T.construir_terreno(geo, via, cad, p.get("area_terreno_m2"), p.get("frente_m"))
    pressupostos += ter["pressupostos"]
    pts = T.grelha_pontos(ter, 9)
    el = await G.elevacoes([(q[2], q[3]) for q in pts])
    topo = T.topografia(pts, el["data"]["z"], el["fonte"], el.get("nota")) if el["ok"] else {"ok": False}
    if el["ok"]:
        fonte(el)
    else:
        pressupostos.append("Altimetria indisponível: assumiu-se terreno plano. O levantamento topográfico é indispensável.")
    await passo("terreno", "ok", f"{ter['area_m2']:.0f} m², declive {topo.get('declive_pct', 0) if topo.get('ok') else '?'} %")

    # 5. programa + implantação + plantas (variantes até caber, cada mudança registada)
    pdm_conhecido: Dict[str, Any] = {}
    alv = I.alvos(pdm_conhecido)
    pressupostos.append("Parâmetros numéricos do PDM não disponíveis em dados abertos: a casa foi desenhada com alvos prudentes "
                        "(implantação ≤ 30 % do terreno, índice ≤ 0,60, fachada ≤ 6,5 m, 2 pisos, afastamentos 5 / 3 / 6 m) "
                        "— a confirmar no regulamento do PDM.")
    tip = p.get("tipologia") or "T3"
    if not p.get("tipologia"):
        pressupostos.append("Tipologia não indicada: assumiu-se T3 (sala, cozinha, 3 quartos com uma suite).")
    pisos_pref = p.get("pisos")
    garagem = _bool(p.get("garagem"), True)
    if p.get("garagem") in (None, ""):
        pressupostos.append("Garagem não indicada: previu-se garagem para 2 carros.")
    lugares = int(p.get("lugares") or 2)
    variantes = [(pisos_pref or 2, garagem, lugares)]
    if (pisos_pref or 2) == 1:
        variantes.append((2, garagem, lugares))
    if garagem:
        variantes += [(2, True, 1), (2, False, 0)]
    res = prog = None
    motivos = []
    for (np_, gar_, lug_) in variantes:
        prog = PG.programa(tip, np_, gar_, lug_, escritorio=_bool(p.get("escritorio"), False))

        def validar(r, prog=prog):
            pl = PL.distribuir(r["volume"], prog, r["fachada_sol"], r["lado_garagem"])
            if not pl.get("ok"):
                return False, pl["motivo"]
            if pl["nao_conformes"]:
                return False, "; ".join(pl["nao_conformes"][:2])
            r["plantas"] = pl
            return True, ""
        res = I.implantar(ter, topo, prog, alv, validar=validar)
        if res["ok"]:
            if (np_, gar_, lug_) != variantes[0]:
                pressupostos.append(f"Para caber no terreno com os afastamentos, passou-se a {np_} {'piso' if np_ == 1 else 'pisos'}"
                                    + ((f" e garagem para {lug_} {'carro' if lug_ == 1 else 'carros'}") if gar_
                                       else " sem garagem (estacionamento no logradouro)") + ".")
            break
        motivos.append(res.get("motivo"))
    if not res or not res["ok"]:
        await passo("projeto", "falhou", motivos[-1] if motivos else "")
        return {"ok": False, "estado": "nao_cabe", "motivo": motivos[-1] if motivos else "", "pressupostos": pressupostos,
                "etapas": etapas, "fontes": fontes,
                "perguntas": ["Quer uma casa mais pequena (por exemplo T2) ou sem garagem?",
                              "Sabe a área exata do terreno (está na caderneta predial)?"]}
    plan = res["plantas"]
    await passo("projeto", "ok", f"{prog['tipologia']} em {res['n_pisos']} piso(s)")

    # 6. processo (formato do motor de urbanismo — a mesma verdade para todos)
    mats = {"fachada": PA.material_fachada(p.get("fachada")),
            "cobertura": p.get("cobertura") if p.get("cobertura") in PA.MATERIAIS_COBERTURA else "telha_ceramica",
            "caixilharia": p.get("caixilharia") if p.get("caixilharia") in PA.CAIXILHARIA else "aluminio_antracite"}
    if not p.get("fachada"):
        pressupostos.append("Material de fachada não indicado: reboco branco (pode pedir granito, madeira, xisto…).")
    ref, loc = ter["_ref"], ter["_local"]

    def to_ll(pts_m):
        return [list(loc.ll(*ref.para_en(x, y))) for x, y in pts_m]
    from engines.urbanismo_pt import volumes as V
    casa_ll = [to_ll(pp["pts"]) for pp in V.building_polygons(res["volume"])]
    orto_b64 = None
    if orto["ok"]:
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(orto["data"]["png"])).convert("RGB")
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
            orto_b64 = base64.b64encode(buf.getvalue()).decode()
        except Exception:  # noqa: BLE001
            orto_b64 = None
    req = p.get("requerente") or {}
    processo = {
        "title": f"Moradia {prog['tipologia']} — {geo.get('rua') or morada}"[:150],
        "tipo_obra": "moradia_nova",
        "requerente": {"nome": req.get("nome", ""), "nif": req.get("nif", ""), "morada": req.get("morada", ""),
                       "telefone": req.get("telefone", ""), "email": req.get("email", "")},
        "terreno": {"morada": geo.get("morada_formatada") or morada, "codigo_postal": geo.get("codigo_postal") or "",
                    "concelho": concelho or "", "freguesia": geo.get("freguesia") or "",
                    "artigo_matricial": p.get("artigo_matricial", ""), "descricao_predial": p.get("descricao_predial", ""),
                    "area_terreno_m2": ter["area_m2"] if ter["area_origem"] != "hipótese" else None},
        "enquadramento": {"zona_protegida": any(re.search(r"patrim|monument", (h.get("titulo") or "").lower()) for h in hits or []),
                          "imovel_classificado": False,
                          "confina_via_publica": bool(via["ok"] and via["data"]["distancia_m"] <= 20),
                          "tem_edificacao_principal": False, "tem_pdm_com_parametros": False, "tem_loteamento_pip": False,
                          "zona_urbana_consolidada": False},
        "pdm": {"plano": f"PDM de {concelho}" if concelho else "PDM", "classe_espaco":
                " — ".join(x for x in ((classe or {}).get("classe"), (classe or {}).get("categoria")) if x) or None,
                "fonte_artigos": "Classe de espaço: CRUS (DGT). Parâmetros numéricos: a confirmar no regulamento do PDM."},
        "volume": res["volume"], "parametros": {},
        "auto": {
            "versao": "auto-1.0", "pedido": {k: v for k, v in p.items() if k != "requerente"},
            "localizacao": {k: geo.get(k) for k in ("lat", "lon", "morada_formatada", "precisao")},
            "terreno": {k: ter[k] for k in ("poligono_m", "poligono_latlon", "area_m2", "area_origem", "plot_l_m", "plot_w_m",
                                             "azimutes", "frente_fonte")},
            "topografia": topo, "classe_solo": classe, "servidoes": hits or [], "alvos": alv,
            "programa": {k: prog[k] for k in ("tipologia", "n_pisos", "area_bruta_total_m2", "minimo_area_bruta_m2", "garagem",
                                              "fonte_minimos")},
            "implantacao": {k: res[k] for k in ("fachada_sol", "lado_garagem", "cota_soleira_m", "terras", "decisoes",
                                                 "casa_rect", "garagem_rect", "declive_profundidade_pct")},
            "plantas": {"pisos": plan["pisos"], "casa_rect": plan["casa_rect"]},
            "vaos": PA.vaos(plan, res["volume"], res["fachada_sol"]),
            "materiais": mats, "casa_latlon": casa_ll,
            "orto": {"b64": orto_b64, "bbox": (orto.get("data") or {}).get("bbox"), "fonte": orto.get("fonte")} if orto_b64 else None,
            "fontes": fontes, "pressupostos": pressupostos, "avisos": avisos, "bloqueios": bloqueios, "etapas": etapas,
        },
    }
    if processo["terreno"]["area_terreno_m2"] is None:   # área assumida: entra no quadro mas marcada
        processo["terreno"]["area_terreno_m2"] = ter["area_m2"]
        processo["auto"]["area_terreno_hipotese"] = True

    # 7. verificação (motores existentes) — a única fonte dos números finais
    verif = R.verificar(processo)
    await passo("verificacao", "ok", verif["rjue"]["procedimento"])

    # 8. documentos: memória determinística, com controlo de números
    mem = PA.memoria_descritiva(processo, verif)
    sem_fonte = C.numeros_sem_fonte(mem, C.numeros_permitidos(verif["quadro"], processo["volume"], plan, processo["auto"]["implantacao"],
                                                               processo["auto"]["programa"], processo["auto"]["alvos"],
                                                               {k: v for k, v in (topo or {}).items() if k != "grelha"}))
    processo["memoria_texto"] = mem
    await passo("documentos", "ok" if not sem_fonte else "atencao", "; ".join(sem_fonte))

    # 9. coerência entre motores
    processo["auto"]["assinatura"] = C.assinatura(processo)
    coer = C.verificar(processo, verif)
    if sem_fonte:
        coer["ok"] = False
        coer["falhas"].append({"codigo": "MEMORIA_NUMEROS", "descricao": "Números da memória sem correspondência nos dados",
                               "obtido": sem_fonte, "ok": False, "critico": True})
    processo["auto"]["coerencia"] = coer
    await passo("coerencia", "ok" if coer["ok"] else "falhou", f"{coer['aprovados']}/{coer['total']}")

    perguntas = []
    processo["auto"]["por_confirmar"] = por_confirmar
    if por_confirmar and any("PDM" in x or "servid" in x for x in por_confirmar):
        perguntas.append("Os serviços oficiais da DGT não responderam agora (PDM / REN / RAN). Peça «refazer» daqui a uns minutos "
                         "para confirmar — até lá o processo não pode ser exportado.")
    if geo.get("precisao") in ("localidade", "rua"):
        perguntas.append("Encontrei a " + ("localidade" if geo.get("precisao") == "localidade" else "rua") +
                         " mas não a porta exata: confirme ou mova o terreno no mapa (ou indique o código postal).")
    if not req.get("nome"):
        perguntas.append("Em nome de quem fica o pedido (nome e NIF do requerente)?")
    if processo["auto"].get("area_terreno_hipotese") or ter["area_origem"] == "hipótese":
        perguntas.append("Qual é a área do terreno indicada na caderneta predial? (assim ajusto a casa ao terreno real)")
    if not p.get("artigo_matricial"):
        perguntas.append("Tem o número do artigo matricial ou da descrição predial? (está na caderneta / certidão)")
    return {"ok": True, "estado": "pronto" if coer["ok"] and not bloqueios and not criticos_por_confirmar else "revisao", "processo": processo, "verificacao": verif,
            "coerencia": coer, "pressupostos": pressupostos, "avisos": avisos, "bloqueios": bloqueios, "fontes": fontes,
            "perguntas": perguntas, "etapas": etapas}


def resumo_publico(r: Dict[str, Any], processo_id: Optional[str] = None) -> Dict[str, Any]:
    """Resumo curto (para o Assistente BTP, a Aurora e o ecrã)."""
    if not r.get("ok"):
        return {k: r.get(k) for k in ("ok", "estado", "motivo", "bloqueios", "avisos", "perguntas", "resposta", "pressupostos") if r.get(k)}
    v, q, a = r["verificacao"], r["verificacao"]["quadro"], r["processo"]["auto"]
    return {
        "ok": True, "estado": r["estado"], "processo_id": processo_id,
        "pagina": f"/urbanismo/processos/{processo_id}" if processo_id else None,
        "procedimento": v["rjue"]["procedimento"], "procedimento_label": R.PROCEDIMENTO_LABEL.get(v["rjue"]["procedimento"]),
        "fundamento": v["rjue"].get("fundamento_legal"), "tecnicos_obrigatorios": v["rjue"].get("tecnicos_obrigatorios"),
        "casa": {"tipologia": a["programa"]["tipologia"], "pisos": q["n_pisos"], "area_construcao_m2": q["area_construcao_m2"],
                 "area_implantacao_m2": q["area_implantacao_m2"], "area_terreno_m2": q["area_terreno_m2"],
                 "garagem": bool(r["processo"]["volume"].get("blocks")), "fachada": a["materiais"]["fachada"]},
        "classe_solo": (a.get("classe_solo") or {}).get("categoria") or (a.get("classe_solo") or {}).get("classe"),
        "decisoes": a["implantacao"]["decisoes"], "pressupostos": r["pressupostos"], "avisos": r["avisos"],
        "coerencia": {"ok": r["coerencia"]["ok"], "aprovados": r["coerencia"]["aprovados"], "total": r["coerencia"]["total"],
                      "falhas": [f["descricao"] for f in r["coerencia"]["falhas"]]},
        "perguntas": r["perguntas"], "fontes": [f["fonte"] for f in r["fontes"]],
        "proximo_passo": "Rever no ecrã, responder às perguntas e pedir a subscrição por arquiteto/engenheiro (termos de responsabilidade).",
    }

"""Agente de estudo CLT do Assistente BTP: o modelo comanda os motores passo a passo e verifica antes de entregar.

O Assistente (Claude) faz o que um engenheiro faz à mão com os motores ConstruPilot:

    1. clt_agente_estado          → abre ou retoma o estudo da conversa e diz qual é o passo seguinte;
    2. clt_agente_ler_planta      → lê as paredes de uma folha (PDF vetorial ou imagem) e devolve uma imagem de
                                    controlo (paredes detetadas a vermelho, lintéis a azul) para o modelo comparar
                                    com a planta;
    3. clt_agente_corrigir_paredes→ corrige o que a leitura falhou (parede em falta, parede a mais, espessura), cada
                                    correção com o seu motivo, guardada no registo do estudo;
    4. clt_agente_definir_piso    → divisões, vãos, laje, cobertura, portas e altura lidas na planta, com a fonte;
    5. clt_agente_calcular        → cadeia determinística: rede de paredes e juntas → peças de produção → plano de
                                    corte → modelo IFC verificado (OpenCascade) → orçamento com os parâmetros e a
                                    biblioteca de preços da empresa → verificações cruzadas entre motores;
    6. clt_agente_dossier         → só com a verificação da revisão atual sem falhas bloqueantes: dossier premium
                                    (estudo_clt_completo, com o Anexo A dos desenhos cotados).

O modelo nunca calcula números: lê, decide, corrige e explica. Cada número vem de um motor e leva a sua origem
(medido no desenho, regra técnica publicada, preço da biblioteca com fonte, ou hipótese editável).
O estado do estudo fica em db.clt_agent_studies, isolado por empresa (tenant), utilizador e conversa.
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
from datetime import datetime, timezone

SYSTEMS = ["clt", "alvenaria_tijolo", "alvenaria_bloco", "betao_armado", "ossatura_madeira", "ossatura_metalica", "divisoria_gesso"]

TOOLS = [
    {
        "type": "function", "name": "clt_agente_estado",
        "description": "Estudo passo a passo de uma casa, em CLT ou construção tradicional (planta → paredes → custos → verificação → dossier). Abre ou retoma o estudo desta "
                       "conversa e devolve os pisos lidos, as correções feitas, o resultado da última verificação e o PASSO SEGUINTE. "
                       "Chama-o primeiro em qualquer estudo CLT a partir de plantas, e sempre que não souberes em que passo estás.",
        "parameters": {"type": "object", "properties": {
            "reiniciar": {"type": ["boolean", "null"], "description": "true apaga o estudo desta conversa e começa de novo"}},
            "required": ["reiniciar"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function", "name": "clt_agente_ler_planta",
        "description": "Lê as paredes CLT de UMA folha de planta anexada (PDF vetorial ou imagem) com o motor de leitura e guarda-as "
                       "como um piso do estudo. Devolve as paredes, as cores candidatas, os lintéis e uma IMAGEM DE CONTROLO (paredes "
                       "detetadas a vermelho, lintéis a azul) que DEVES comparar com a planta antes de avançar. Para uma imagem "
                       "(JPG/PNG) indica pixels_por_metro lidos na barra gráfica ou numa cota. altura_m = null quando a planta não "
                       "marca alturas (usa-se a altura standard da empresa: RDC 3,00 m, outros pisos 2,50 m).",
        "parameters": {"type": "object", "properties": {
            "document_id": {"type": "string", "description": "doc_… do ficheiro anexado"},
            "pagina": {"type": ["integer", "null"], "description": "página do PDF (1 = primeira); null para imagens"},
            "piso": {"type": "string", "description": "nome do piso, p. ex. 'RDC' ou 'Piso 1'"},
            "ordem": {"type": "integer", "description": "0 = piso térreo (RDC), 1 = primeiro andar, …"},
            "altura_m": {"type": ["number", "null"], "description": "altura estrutural marcada no corte; null = standard"},
            "escala": {"type": ["integer", "null"], "description": "N de 1:N quando a folha não tem uma só escala legível"},
            "cor_paredes": {"type": ["string", "null"], "description": "#rrggbb das paredes CLT quando há várias cores candidatas"},
            "cor_linteis": {"type": ["string", "null"], "description": "#rrggbb dos lintéis CLT (tracejado), se confirmada na legenda"},
            "camadas": {"type": ["integer", "null"], "description": "camadas do painel de parede (legenda); null = 5"},
            "pixels_por_metro": {"type": ["number", "null"], "description": "só para imagens: escala lida na barra gráfica"},
            "plan_id": {"type": ["string", "null"], "description": "plans_… de uma planta já medida no módulo de medições (construção "
                        "tradicional: paredes de duas faces, qualquer espessura). Com plan_id, document_id pode ser ''"}},
            "required": ["document_id", "pagina", "piso", "ordem", "altura_m", "escala", "cor_paredes", "cor_linteis", "camadas",
                         "pixels_por_metro", "plan_id"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function", "name": "clt_agente_corrigir_paredes",
        "description": "Corrige as paredes de um piso depois de comparares a imagem de controlo com a planta: remover paredes "
                       "detetadas a mais, acrescentar paredes em falta (eixo em metros no MESMO referencial das paredes lidas), mudar "
                       "a espessura ou as camadas. Cada correção exige o motivo (o que se vê na planta) e fica no registo do dossier.",
        "parameters": {"type": "object", "properties": {
            "piso": {"type": "string"},
            "remover_ids": {"type": "array", "items": {"type": "string"}},
            "acrescentar": {"type": "array", "items": {"type": "object", "properties": {
                "x1": {"type": "number"}, "y1": {"type": "number"}, "x2": {"type": "number"}, "y2": {"type": "number"},
                "espessura_mm": {"type": "number"}, "camadas": {"type": ["integer", "null"]}},
                "required": ["x1", "y1", "x2", "y2", "espessura_mm", "camadas"], "additionalProperties": False}},
            "alterar": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "espessura_mm": {"type": ["number", "null"]}, "camadas": {"type": ["integer", "null"]}},
                "required": ["id", "espessura_mm", "camadas"], "additionalProperties": False}},
            "motivo": {"type": "string", "description": "o que a planta mostra e justifica a correção"}},
            "required": ["piso", "remover_ids", "acrescentar", "alterar", "motivo"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function", "name": "clt_agente_definir_piso",
        "description": "Completa um piso com o que a planta mostra além das paredes: divisões (nome, tipo, retângulo em metros ou área "
                       "escrita na planta, aparelhos sanitários), vãos exteriores (largura), portas interiores, laje e cobertura CLT, "
                       "altura e prumada. Indica a fonte de cada dado (p. ex. 'área escrita na planta', 'lido no corte A-A'). Campos "
                       "null ficam como estão; o que nunca for indicado é derivado pelo motor e marcado como hipótese.",
        "parameters": {"type": "object", "properties": {
            "piso": {"type": "string"},
            "altura_m": {"type": ["number", "null"]},
            "divisoes": {"type": ["array", "null"], "items": {"type": "object", "properties": {
                "nome": {"type": "string"},
                "tipo": {"type": "string", "enum": ["sala", "quarto", "cozinha", "casa_de_banho", "lavandaria", "corredor",
                                                    "escritorio", "arrumos", "exterior"]},
                "rect_m": {"type": ["array", "null"], "items": {"type": "number"}, "description": "[x0, y0, x1, y1] em metros"},
                "area_m2": {"type": ["number", "null"], "description": "área escrita na planta (prevalece sobre o retângulo)"},
                "aparelhos": {"type": "array", "items": {"type": "string", "enum": [
                    "lavatorio", "bide", "banheira", "chuveiro", "autoclismo", "lava_loica", "maquina_lavar_loica",
                    "maquina_lavar_roupa", "tanque", "torneira_exterior"]}}},
                "required": ["nome", "tipo", "rect_m", "area_m2", "aparelhos"], "additionalProperties": False}},
            "vaos": {"type": ["array", "null"], "items": {"type": "object", "properties": {
                "largura_m": {"type": "number"}, "tipo": {"type": "string", "enum": ["janela", "vao_envidracado"]},
                "sobre": {"type": ["string", "null"], "enum": ["lintel", "viga", None]}},
                "required": ["largura_m", "tipo", "sobre"], "additionalProperties": False}},
            "portas_interiores": {"type": ["integer", "null"]},
            "laje": {"type": ["object", "null"], "properties": {
                "poligono_m": {"type": ["array", "null"], "items": {"type": "array", "items": {"type": "number"}}},
                "area_m2": {"type": ["number", "null"]}, "espessura_mm": {"type": "number"}, "camadas": {"type": "integer"},
                "vazios_m2": {"type": ["number", "null"], "description": "abertura da escada e outros vazios a descontar"}},
                "required": ["poligono_m", "area_m2", "espessura_mm", "camadas", "vazios_m2"], "additionalProperties": False},
            "cobertura": {"type": ["object", "null"], "properties": {
                "poligono_m": {"type": ["array", "null"], "items": {"type": "array", "items": {"type": "number"}}},
                "area_m2": {"type": ["number", "null"]}, "espessura_mm": {"type": "number"}, "camadas": {"type": "integer"}},
                "required": ["poligono_m", "area_m2", "espessura_mm", "camadas"], "additionalProperties": False},
            "prumada_m": {"type": ["array", "null"], "items": {"type": "number"}, "description": "[x, y] da coluna técnica"},
            "fonte": {"type": "string", "description": "de onde vêm estes dados (folha, legenda, corte, cotas escritas)"}},
            "required": ["piso", "altura_m", "divisoes", "vaos", "portas_interiores", "laje", "cobertura", "prumada_m", "fonte"],
            "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function", "name": "clt_agente_calcular",
        "description": "Corre a cadeia de motores sobre o estudo atual: rede de paredes e juntas L/T/X, peças de produção ≤ formato "
                       "da prensa, plano de corte (OR-Tools), modelo IFC verificado (OpenCascade), orçamento com os parâmetros e a "
                       "biblioteca de preços da empresa, e as VERIFICAÇÕES CRUZADAS entre motores. Devolve cada verificação com "
                       "ok/falha, o nível (bloqueante/aviso) e como corrigir. Volta a chamar depois de cada correção.",
        "parameters": {"type": "object", "properties": {
            "regime_iva": {"type": ["string", "null"], "enum": ["pt", "ua", "ua_export", None],
                           "description": "pt = Portugal 23 %; ua = obra na Ucrânia 20 %; ua_export = 0 %; null = pt"},
            "inicio": {"type": ["string", "null"], "description": "data de início AAAA-MM-DD; null = hoje"},
            "modo_inicio": {"type": ["string", "null"], "enum": ["compra", "fabrico", None]},
            "sistema": {"type": ["string", "null"], "enum": [*SYSTEMS, None],
                        "description": "sistema construtivo das paredes; null = o já escolhido (por defeito clt). Fora de clt usa o "
                                       "motor geral (construção tradicional) com os parâmetros e a biblioteca de medições da empresa"},
            "pais": {"type": ["string", "null"], "enum": ["PT", "FR", "UA", None], "description": "IVA do motor geral; null = PT"}},
            "required": ["regime_iva", "inicio", "modo_inicio", "sistema", "pais"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function", "name": "clt_agente_dossier",
        "description": "Gera o dossier CLT premium (quantidades, preços, plano, rentabilidade, Anexo A dos desenhos cotados) do estudo "
                       "verificado. Recusa enquanto a última verificação tiver falhas bloqueantes ou não for da revisão atual.",
        "parameters": {"type": "object", "properties": {
            "titulo": {"type": "string"}, "local": {"type": ["string", "null"]},
            "lingua": {"type": ["string", "null"], "enum": ["pt", "en", "uk", "fr", None]},
            "empresa": {"type": ["string", "null"], "enum": ["clt-rezult", None]}},
            "required": ["titulo", "local", "lingua", "empresa"], "additionalProperties": False},
        "strict": True,
    },
]
NAMES = {t["name"] for t in TOOLS}

STATUS = {
    "clt_agente_estado": "A abrir o estudo CLT e a ver o passo seguinte…",
    "clt_agente_ler_planta": "A ler as paredes CLT da planta…",
    "clt_agente_corrigir_paredes": "A corrigir as paredes do piso…",
    "clt_agente_definir_piso": "A registar divisões, vãos, laje e cobertura…",
    "clt_agente_calcular": "A correr os motores (juntas, peças, corte, IFC, custos) e a verificar…",
    "clt_agente_dossier": "A gerar o dossier CLT verificado…",
}

INSTRUCTIONS = """

ESTUDO PASSO A PASSO (agente de motores). Quando o utilizador pede um estudo, medição, orçamento ou dossier de uma casa a partir
de plantas, em CLT ou em construção tradicional (alvenaria, betão armado, ossatura de madeira ou metálica: escolhe `sistema` em
clt_agente_calcular; uma planta já medida no módulo de medições lê-se com plan_id), trabalha como um engenheiro que comanda os
motores, por esta ordem, sem saltar passos:
1. PLANEAR: chama clt_agente_estado. Lê o passo seguinte que ele indica. Identifica as folhas (uma por piso), a escala, a legenda
   (cores das paredes CLT, espessuras e camadas, lintéis) e o corte (alturas). Se a planta não marca alturas, altura_m = null.
2. LER: clt_agente_ler_planta para cada piso. OLHA para a imagem de controlo devolvida e compara-a com a planta: paredes em falta,
   paredes a mais (mobiliário, cotas, caixilharia), espessuras erradas, lintéis por confirmar. Se houver várias cores
   candidatas, escolhe a da legenda e volta a ler.
3. CORRIGIR: clt_agente_corrigir_paredes com o motivo visível na planta. Nunca inventes paredes que a planta não mostra.
4. COMPLETAR: clt_agente_definir_piso com as divisões (tipo, retângulo ou área escrita, aparelhos sanitários), vãos exteriores,
   portas interiores, laje dos pisos elevados (descontando a escada) e cobertura, sempre com a fonte.
5. CALCULAR E VERIFICAR: clt_agente_calcular. Para cada verificação em falha, faz a correção que ela indica e volta a calcular.
   Máximo 3 ciclos de correção: se ainda houver falhas bloqueantes, para e explica ao utilizador o que falta, com a folha e a zona.
6. ENTREGAR: só quando não há falhas bloqueantes, clt_agente_dossier. Depois resume: totais (m³ CLT, custo, venda, margem, prazo),
   verificações aprovadas, avisos, hipóteses a confirmar pela empresa (editáveis em /clt-industrial › Custos, preços e plano) e as
   correções que fizeste.
Regras: os números vêm SEMPRE dos motores (não recalcules nem arredondes por tua conta); distingue medido / derivado / hipótese;
alturas standard RDC 3,00 m e outros pisos 2,50 m quando a planta não as marca; sem betão nem cálculo estrutural; cada empresa só
vê os seus dados. Uma imagem (JPG/PNG) dá só uma estimativa (±1 píxel): diz-o. Avança sem perguntas enquanto a planta responder;
pergunta só o que nenhuma folha mostra e bloqueia o estudo.
"""

COLLECTION = "clt_agent_studies"
TOL_OK, TOL_BLOCK = 2.0, 5.0            # % entre motores: ≤ 2 % aprovado (limite do projeto), 2–5 % aviso, > 5 % bloqueante
DEFAULT_SLAB = (240, 7)                 # laje CLT por defeito (a da Home A): hipótese até a planta a indicar
DEFAULT_ROOF = (140, 5)                 # cobertura CLT por defeito (a da Home A): hipótese
LINTEL_HEAD_M = 2.30                    # topo dos vãos quando a planta não o marca (motor clt_fitout, OPENING_H lintel)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _key(user, conv):
    from bim_studio.store import tenant_of
    return {"_id": f"{tenant_of(user)}:{conv['conversation_id']}", "tenant_id": tenant_of(user), "user_id": user["user_id"]}


async def _load(db, user, conv):
    k = _key(user, conv)
    doc = await db[COLLECTION].find_one(k)
    if not doc:
        doc = {**k, "conversation_id": conv["conversation_id"], "revisao": 0, "pisos": {}, "registo": [], "criado": _now()}
    return doc


async def _save(db, doc, *, changed=True):
    if changed:
        doc["revisao"] = int(doc.get("revisao", 0)) + 1
    doc["atualizado"] = _now()
    await db[COLLECTION].replace_one({"_id": doc["_id"], "tenant_id": doc["tenant_id"], "user_id": doc["user_id"]}, doc, upsert=True)


async def _company(db, user):
    from bim_studio.clt_economics import library_merged, merged
    from bim_studio.store import tenant_of
    tenant = tenant_of(user)
    params = await db.clt_parameters.find_one({"_id": tenant}) or {}
    library = await db.clt_library.find_one({"_id": tenant}) or {}
    return merged(params.get("values")), library_merged(library.get("items", {}))


def _standard_height(params, ordem):
    key = "standard_height_ground_m" if ordem == 0 else "standard_height_upper_m"
    return float((params.get(key) or {}).get("value", 3.0 if ordem == 0 else 2.5))


def _floors(doc):
    return sorted(doc["pisos"].values(), key=lambda p: p["ordem"])


# ---------------------------------------------------------------------------------------------------------------------
# next step
# ---------------------------------------------------------------------------------------------------------------------
def next_step(doc):
    floors = _floors(doc)
    if not floors:
        return "Ler a primeira folha: clt_agente_ler_planta (uma chamada por piso)."
    empty = [p["nome"] for p in floors if not p.get("paredes")]
    if empty:
        return f"Pisos sem paredes ({', '.join(empty)}): reler com outra cor/escala ou acrescentar as paredes com o motivo."
    missing = [p["nome"] for p in floors if not p.get("divisoes")]
    if missing:
        return f"Completar {', '.join(missing)} com clt_agente_definir_piso (divisões, vãos, laje, cobertura) e depois calcular."
    ver = doc.get("verificacao") or {}
    if ver.get("revisao") != doc.get("revisao"):
        return "Correr clt_agente_calcular (a última verificação não corresponde ao estudo atual)."
    blocking = [c for c in ver.get("checks", []) if not c["ok"] and c["nivel"] == "bloqueante"]
    if blocking:
        return "Corrigir as falhas bloqueantes: " + "; ".join(f"{c['id']} → {c['como_corrigir']}" for c in blocking)
    if not doc.get("dossier") or doc["dossier"].get("revisao") != doc.get("revisao"):
        return "Estudo verificado: gerar o dossier com clt_agente_dossier."
    return "Dossier entregue para a revisão atual. Resumir resultados, avisos e hipóteses ao utilizador."


def _public(doc):
    floors = []
    for p in _floors(doc):
        by_t = {}
        for w in p.get("paredes", []):
            L = math.hypot(w["x2"] - w["x1"], w["y2"] - w["y1"])
            by_t[w["thickness_mm"]] = by_t.get(w["thickness_mm"], 0) + L
        floors.append({"piso": p["nome"], "ordem": p["ordem"], "fonte": p.get("fonte_paredes"), "estado": p.get("estado"),
                       "altura_m": p.get("altura_m"), "altura_origem": p.get("altura_origem"),
                       "paredes": len(p.get("paredes", [])), "comprimento_por_espessura_m": {f"{k:g}": round(v, 3) for k, v in by_t.items()},
                       "linteis": len(p.get("linteis", [])), "divisoes": len(p.get("divisoes") or []), "vaos": len(p.get("vaos") or []),
                       "laje": bool(p.get("laje")), "cobertura": bool(p.get("cobertura"))})
    ver = doc.get("verificacao") or {}
    return {"revisao": doc.get("revisao", 0), "pisos": floors, "correcoes": doc.get("registo", [])[-20:],
            "verificacao": {"revisao": ver.get("revisao"), "aprovadas": ver.get("aprovadas"), "total": ver.get("total"),
                            "falhas": [c for c in ver.get("checks", []) if not c["ok"]]} if ver else None,
            "passo_seguinte": next_step(doc)}


# ---------------------------------------------------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------------------------------------------------
def _png_data_url(png: bytes):
    return {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(png).decode(), "detail": "high"}


def overlay_pdf(data: bytes, page_number: int, result: dict, max_px=1600) -> bytes:
    """Page render with the detected walls (red, labelled) and the lintels (blue): the model checks it against the plan.
    Drawn on the rendered image in page.rect coordinates (the reader's space, rotation applied)."""
    import cv2
    import fitz
    import numpy as np
    from bim_studio.clt_pdf_walls import POINT_MM
    with fitz.open(stream=data, filetype="pdf") as doc:
        page = doc[page_number - 1]
        W, H = page.rect.width, page.rect.height
        zoom = min(2.0, max_px / max(W, H))
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3][:, :, ::-1].copy()
    layer = img.copy()
    labels = []
    for m in result.get("marcadores", []):
        x0, y0, x1, y1 = m["rect"]
        p0, p1 = (int(x0 * W * zoom), int(y0 * H * zoom)), (int(x1 * W * zoom), int(y1 * H * zoom))
        cv2.rectangle(layer, p0, p1, (0, 0, 255), -1)
        labels.append((m["id"].split("-")[-1], p0))
    factor = POINT_MM * result["escala"] / 1000
    for li in result.get("linteis", []):
        x0, y0, x1, y1 = li["rect_m"]
        p0 = (int(min(x0, x1) / factor * zoom), int(-max(y0, y1) / factor * zoom))
        p1 = (int(max(x0, x1) / factor * zoom), int(-min(y0, y1) / factor * zoom))
        cv2.rectangle(layer, p0, p1, (255, 80, 0), -1)
    img = cv2.addWeighted(layer, 0.55, img, 0.45, 0)
    for text, (x, y) in labels:
        cv2.putText(img, text, (x, max(10, y - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 180), 1, cv2.LINE_AA)
    return cv2.imencode(".png", img)[1].tobytes()


def overlay_image(data: bytes, result: dict, max_px=1600) -> bytes:
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    layer = img.copy()
    for i, (a, b, c, d) in enumerate(result.get("bandas_px", []), 1):
        cv2.rectangle(layer, (a, b), (c, d), (0, 0, 255), -1)
    img = cv2.addWeighted(layer, 0.5, img, 0.5, 0)
    for i, (a, b, c, d) in enumerate(result.get("bandas_px", []), 1):
        cv2.putText(img, str(i), (a, max(10, b - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 200), 1)
    scale = min(1.0, max_px / max(img.shape[:2]))
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return cv2.imencode(".png", img)[1].tobytes()


def read_sheet(data: bytes, mime: str, a: dict, height_m: float):
    """Runs the right reader. Returns (floor fields, summary for the model, control image png)."""
    is_pdf = data[:5] == b"%PDF-" or "pdf" in (mime or "")
    if is_pdf:
        from bim_studio.clt_pdf_walls import detect
        if not a.get("pagina"):
            raise ValueError("Indique a página do PDF (pagina).")
        r = detect(data, a["pagina"], scale=a.get("escala"), height_m=height_m, layers=a.get("camadas") or 5,
                   colour=a.get("cor_paredes"), lintel_colour=a.get("cor_linteis"))
        png = overlay_pdf(data, a["pagina"], r)
        source = f"PDF p.{a['pagina']}, {r['origem_escala']}, cor {r.get('cor_usada')}"
        state = "medido (vetorial), por confirmar na imagem de controlo"
        lintels = [{"ref": f"L{i + 1}", "rect_m": li["rect_m"], "head_m": li.get("head_m") or LINTEL_HEAD_M,
                    "thickness_mm": li.get("thickness_mm"), "origem": li.get("origem_altura") or "topo do vão standard 2,30 m (hipótese)"}
                   for i, li in enumerate(r.get("linteis", []))]
        summary = {"escala": r["escala"], "origem_escala": r["origem_escala"], "cores_candidatas": r["cores_candidatas"],
                   "cor_usada": r["cor_usada"], "rejeitados": r["rejeitados"][:20],
                   "tracejados_por_confirmar": r["tracejados_por_confirmar"][:20], "cores_linteis": r.get("cores_linteis"),
                   "notas_rede": (r.get("rede") or {}).get("notas", [])[:20],
                   "verificacao_volume": (r.get("analise") or {}).get("verificacao_volume")}
    else:
        from bim_studio.clt_raster_walls import detect
        if not a.get("pixels_por_metro"):
            raise ValueError("Imagem: indique pixels_por_metro (lidos na barra gráfica ou numa cota conhecida).")
        r = detect(data, pixels_per_metre=float(a["pixels_por_metro"]), height_m=height_m)
        png = overlay_image(data, r)
        source = f"imagem, {a['pixels_por_metro']} px/m"
        state = "estimativa de imagem (±1 píxel), por confirmar na imagem de controlo"
        lintels = []
        summary = {"incerteza": r["incerteza"], "rejeitados": r["rejeitados"][:20],
                   "verificacao_volume": (r.get("analise") or {}).get("verificacao_volume"),
                   "nota": "Os números na imagem de controlo são a ordem das bandas: parede I<n> = banda n."}
    walls = r["paredes"]
    if a.get("camadas"):
        for w in walls:
            w["layers"] = a["camadas"]
    return {"paredes": walls, "linteis": lintels, "fonte_paredes": source, "estado": state}, summary, png


# ---------------------------------------------------------------------------------------------------------------------
# estimate input (the CLT page format) built from the study
# ---------------------------------------------------------------------------------------------------------------------
def _axis(w):
    from bim_studio.clt_walls import WallAxis
    return WallAxis.model_validate(w)


CLOSE_M = 3.5                           # closes door and window gaps up to 7 m when the outline is derived from the walls
                                        # (Home A +1: 76.41 m² vs 76.22 m² of the reviewed take-off)


def _shell(walls):
    """Outer outline of a floor derived from the walls: union of the footprints, closed over the openings
    (morphological closing, mitre joins keep the corners square) with the rooms inside filled. An estimate:
    the plan's own outline (laje/cobertura polygon) replaces it when the model gives it."""
    from shapely import union_all
    from shapely.geometry import Polygon
    u = union_all([w.footprint() for w in walls]).buffer(CLOSE_M, join_style="mitre").buffer(-CLOSE_M, join_style="mitre")
    polys = list(u.geoms) if hasattr(u, "geoms") else [u]
    return union_all([Polygon(p.exterior) for p in polys if not p.is_empty])


def _hull(walls):
    from shapely.geometry import MultiPoint
    return MultiPoint([pt for w in walls for pt in w.footprint().exterior.coords]).convex_hull.area


def _area(poly_or_area, fallback):
    from shapely.geometry import Polygon
    if poly_or_area.get("area_m2"):
        return float(poly_or_area["area_m2"]), "área indicada"
    if poly_or_area.get("poligono_m") and len(poly_or_area["poligono_m"]) >= 3:
        return Polygon(poly_or_area["poligono_m"]).area, "polígono lido na planta"
    return fallback, None


def build_input(doc, params, regime="pt", start=None, start_mode="compra"):
    """EstimateInput (format of the CLT page) + the origin of every derived quantity."""
    from shapely.ops import unary_union
    floors, origins, hyp = [], [], []
    ordered = _floors(doc)
    shells = {}
    for p in ordered:
        walls = [_axis(w) for w in p["paredes"]]
        shells[p["nome"]] = _shell(walls) if walls else None
    top = ordered[-1]["nome"] if ordered else None
    for i, p in enumerate(ordered):
        walls = [_axis(w) for w in p["paredes"]]
        h = p.get("altura_m") or _standard_height(params, p["ordem"])
        shell = shells[p["nome"]]
        by_t, segs, ext_len, inner = {}, [], 0.0, 0.0
        for w in walls:
            by_t.setdefault((w.thickness_mm, w.layers), 0.0)
            by_t[(w.thickness_mm, w.layers)] += w.length
            x0, y0, x1, y1 = w.footprint().bounds
            segs.append({"ref": w.id, "thickness_mm": str(w.thickness_mm), "length_m": str(round(w.length, 3)),
                         "rect_m": [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]})
            from shapely.geometry import LineString
            edge = shell.boundary.buffer(w.thickness_m / 2 + 0.06)
            exterior = LineString([(w.x1, w.y1), (w.x2, w.y2)]).intersection(edge).length >= 0.5 * w.length
            ext_len += w.length if exterior else 0.0
            inner += w.length * (1 if exterior else 2)
        panels, beam = [], 0.0
        for li in p.get("linteis", []):
            x0, y0, x1, y1 = li["rect_m"]
            span = max(abs(x1 - x0), abs(y1 - y0))
            t = li.get("thickness_mm") or min(abs(x1 - x0), abs(y1 - y0)) * 1000
            depth = h - float(li["head_m"])
            if depth > 0:
                nominal = min(by_t, key=lambda k: abs(k[0] - t))[0] if by_t else round(t)
                layers = next((k[1] for k in by_t if k[0] == nominal), 5)
                panels.append({"kind": "lintel", "label": f"Lintel CLT {nominal:g} {li['ref']} ({span:.2f} m)",
                               "thickness_mm": str(nominal), "layers": layers, "area_m2": str(round(span * depth, 3))})
        vaos = p.get("vaos") or []
        for v in vaos:
            if v.get("sobre") == "viga":
                beam += float(v["largura_m"])
        rooms = []
        for r in p.get("divisoes") or []:
            rect = r.get("rect_m")
            w_, l_ = (abs(rect[2] - rect[0]), abs(rect[3] - rect[1])) if rect and len(rect) == 4 else (0, 0)
            area = r.get("area_m2") or w_ * l_
            if area <= 0:
                continue
            per = 2 * (w_ + l_) if w_ else 4 * math.sqrt(area)
            room = {"nome": r["nome"][:80], "tipo": r["tipo"], "area_m2": str(round(area, 2)), "perimetro_m": str(round(per, 2)),
                    "comprimento_m": str(round(max(w_, l_) or math.sqrt(area), 2)), "aparelhos": r.get("aparelhos") or []}
            if rect and len(rect) == 4:
                room["rect_m"] = [min(rect[0], rect[2]), min(rect[1], rect[3]), max(rect[0], rect[2]), max(rect[1], rect[3])]
            rooms.append(room)
        foot = shell.area if shell is not None else 0.0
        slab_m2 = roof_m2 = 0.0
        if p["ordem"] > 0:
            s = p.get("laje")
            if s:
                area, how = _area(s, foot)
                area -= float(s.get("vazios_m2") or 0)
                t, n = s["espessura_mm"], s["camadas"]
                origins.append(f"{p['nome']}: laje {area:.2f} m² ({how or 'contorno exterior das paredes'})")
            else:
                area, (t, n) = foot, DEFAULT_SLAB
                hyp.append(f"{p['nome']}: laje CLT {t} mm {n} camadas = contorno exterior das paredes ({area:.2f} m²; envolvente "
                           f"convexa {_hull(walls):.2f} m²), sem descontar a escada (hipótese: indicar com clt_agente_definir_piso)")
            slab_m2 = area
            panels.append({"kind": "laje", "label": f"Laje CLT {t:g} de {p['nome']}", "thickness_mm": str(t), "layers": n,
                           "area_m2": str(round(area, 3))})
        c = p.get("cobertura")
        above = [shells[q["nome"]] for q in ordered[i + 1:] if shells.get(q["nome"]) is not None]
        uncovered = shell.difference(unary_union(above)).area if (shell is not None and above) else 0.0
        if c or p["nome"] == top or uncovered > 1.0:
            if c:
                area, how = _area(c, foot)
                t, n = c["espessura_mm"], c["camadas"]
                origins.append(f"{p['nome']}: cobertura {area:.2f} m² ({how or 'contorno exterior das paredes'})")
            elif p["nome"] == top:
                area, (t, n) = foot, DEFAULT_ROOF
                hyp.append(f"{p['nome']}: cobertura CLT {t} mm {n} camadas = contorno exterior das paredes ({area:.2f} m²; envolvente "
                           f"convexa {_hull(walls):.2f} m²) (hipótese: indicar com clt_agente_definir_piso)")
            else:
                area, (t, n) = uncovered, DEFAULT_ROOF
                hyp.append(f"{p['nome']}: cobertura CLT {t} mm {n} camadas sobre a parte sem piso por cima = contorno de {p['nome']} "
                           f"menos os pisos superiores ({area:.2f} m²) (hipótese: indicar com clt_agente_definir_piso)")
            roof_m2 = area
            panels.append({"kind": "cobertura", "label": f"Cobertura CLT {t:g} de {p['nome']}", "thickness_mm": str(t), "layers": n,
                           "area_m2": str(round(area, 3))})
        faces = inner * h
        ceiling = sum(float(r["area_m2"]) for r in rooms if r["tipo"] != "exterior")
        floor = {
            "name": p["nome"], "height_m": str(p["altura_m"]) if p.get("altura_m") else None,
            "walls": [{"thickness_mm": str(t), "layers": n, "length_m": str(round(L, 3))} for (t, n), L in by_t.items()],
            "panels": panels, "board_layers_m2": str(round(2 * faces, 2)), "paint_m2": str(round(faces + ceiling, 2)),
            "ceiling_m2": str(round(ceiling, 2)), "facade_m2": str(round(ext_len * h, 2)), "steel_beam_m": str(round(beam, 2)),
            "slab_buildup_m2": str(round(slab_m2, 2)), "roof_buildup_m2": str(round(roof_m2, 2)),
            "rooms": rooms, "windows": [{"largura_m": str(v["largura_m"]), "sobre": v.get("sobre"), "tipo": v["tipo"]} for v in vaos],
            "interior_doors": int(p.get("portas_interiores") or 0), "ceiling_height_m": str(h),
            "segments": segs, "lintels": [{k: li[k] for k in ("ref", "rect_m", "head_m", "thickness_mm")} for li in p.get("linteis", [])],
        }
        if p.get("prumada_m"):
            floor["riser_m"] = p["prumada_m"][:2]
        floors.append(floor)
        origins.append(f"{p['nome']}: placa 2 camadas × faces interiores ({faces:.1f} m²), fachada = paredes exteriores "
                       f"{ext_len:.2f} m × {h} m (derivado da rede de paredes)")
    body = {"floors": floors, "vat_regime": regime or "pt", "start_mode": start_mode or "compra"}
    if start:
        body["start"] = start
    return body, origins, hyp


# ---------------------------------------------------------------------------------------------------------------------
# engines chain and cross-checks
# ---------------------------------------------------------------------------------------------------------------------
def _pct(a, b):
    return abs(a - b) * 100 / b if b else (0.0 if not a else 100.0)


def _level(diff):
    return "ok" if diff <= TOL_OK else ("aviso" if diff <= TOL_BLOCK else "bloqueante")


def run_chain(doc, params, library, regime="pt", start=None, start_mode="compra"):
    """Geometry engines → estimate → cross-checks. Pure function (no DB): tested on Home A."""
    from bim_studio.clt_economics import EstimateInput, estimate
    from routes.clt_engines import EngineFloor, Project, _run

    ordered = _floors(doc)
    checks = []

    def check(cid, ok, nivel, valor, limite, como, origem=""):
        checks.append({"id": cid, "ok": bool(ok), "nivel": nivel, "valor": valor, "limite": limite, "como_corrigir": como, "motores": origem})

    if not ordered or any(not p.get("paredes") for p in ordered):
        check("pisos_com_paredes", False, "bloqueante", [p["nome"] for p in ordered if not p.get("paredes")], "≥ 1 parede por piso",
              "clt_agente_ler_planta (outra cor/escala) ou clt_agente_corrigir_paredes", "leitura")
        return {"checks": checks}
    # 1. geometry: network, pieces, cutting plan, IFC check
    elev, eng_floors = 0.0, []
    heights = {}
    for p in ordered:
        h = float(p.get("altura_m") or _standard_height(params, p["ordem"]))
        heights[p["nome"]] = h
        walls = [{**w, "height_m": h, "base_z_m": 0.0} for w in p["paredes"]]
        eng_floors.append(EngineFloor(name=p["nome"], elevation_m=elev, walls=walls,
                                      lintels=[{k: li[k] for k in ("ref", "rect_m", "head_m", "thickness_mm")} for li in p.get("linteis", [])]))
        elev += h
    press = (float((params.get("press_length_m") or {}).get("value", 18)), float((params.get("press_width_m") or {}).get("value", 3.5)))
    try:
        project = Project(name="Estudo CLT", floors=eng_floors, cutting={"blank_length_m": press[0], "blank_width_m": press[1]})
        geo = _run(project, ifc=True)
    except ValueError as exc:                     # duplicated walls, openings outside a wall, walls taller than the press…
        check("motores_geometria", False, "bloqueante", str(exc)[:300], "rede de paredes válida",
              "corrigir com clt_agente_corrigir_paredes a parede indicada no erro (duplicada, vão fora da parede, altura)",
              "clt_walls / clt_nesting / clt_ifc")
        return {"checks": checks}
    geo.pop("ifc", None)
    for a in geo["pisos"]:
        v = a["verificacao_volume"]
        check(f"pecas_vs_planta[{a['piso']}]", v["passed"], "bloqueante" if not v["passed"] else "ok",
              {"pecas_m3": a["metodos"]["volume_pecas_m3"], "uniao_planta_m3": a["metodos"]["volume_uniao_planta_m3"]}, "≤ 2 %",
              "paredes sobrepostas ou duplicadas: ver a imagem de controlo e remover duplicados", "clt_walls (peças) × GEOS (união)")
        notes = (a.get("rede") or {}).get("notas") or []
        check(f"linteis_ligados[{a['piso']}]", not notes, "aviso", notes[:10], "todos os lintéis dentro de uma peça",
              "confirmar a cor dos lintéis (cor_linteis) ou deixar como painel à parte", "clt_walls.connect")
    v3d = geo.get("verificacao_3d") or {}
    check("ifc_opencascade", v3d.get("passed"), "bloqueante", {k: v for k, v in v3d.items() if k != "pecas"}, "≤ 2 %",
          "o modelo 3D não confere com as peças: rever paredes com vãos fora da parede ou alturas", "clt_ifc × OpenCascade")
    cut = geo["corte"]["total"]
    vol_pieces = sum(a["totais"]["volume_bruto_m3"] for a in geo["pisos"])
    check("corte_cobre_pecas", cut["volume_paineis_m3"] + 1e-6 >= vol_pieces, "bloqueante",
          {"paineis_m3": cut["volume_paineis_m3"], "pecas_m3": round(vol_pieces, 4)}, "painéis ≥ peças",
          "erro no plano de corte: reportar", "clt_nesting × clt_walls")
    check("desperdicio_corte", cut["desperdicio_percent"] <= 20, "aviso", cut["desperdicio_percent"], "≤ 20 %",
          "rever o formato da prensa nos parâmetros da empresa", "clt_nesting")
    # 2. estimate with the company's parameters and price library
    body, origins, hyp = build_input(doc, params, regime, start, start_mode)
    est = estimate(EstimateInput.model_validate(body), params, library)
    # 3. cross-checks between the take-off (estimate) and the production pieces (geometry)
    for a, row, fl in zip(geo["pisos"], est["pisos"], body["floors"]):
        h = heights[fl["name"]]
        walls_m3 = sum(float(w["length_m"]) * h * float(w["thickness_mm"]) / 1000 for w in fl["walls"])
        lint_m3 = sum(float(pn["area_m2"]) * float(pn["thickness_mm"]) / 1000 for pn in fl["panels"] if pn["kind"] == "lintel")
        net = a["totais"]["volume_liquido_m3"]
        d = _pct(walls_m3 + lint_m3, net)
        check(f"orcamento_vs_pecas[{fl['name']}]", _level(d) != "bloqueante", _level(d) if _level(d) != "ok" else "ok",
              {"orcamento_paredes_linteis_m3": round(walls_m3 + lint_m3, 4), "pecas_liquido_m3": net, "diferenca_percent": round(d, 2)},
              "≤ 2 % (aviso até 5 %)", "uma parede ou lintel contado de um lado e não do outro: comparar a imagem de controlo",
              "clt_economics × clt_walls")
        seg = sum(float(s["length_m"]) for s in fl["segments"])
        tot = sum(float(w["length_m"]) for w in fl["walls"])
        check(f"segmentos_vs_paredes[{fl['name']}]", _pct(seg, tot) < 0.1, "bloqueante", {"segmentos_m": round(seg, 3), "paredes_m": round(tot, 3)},
              "igual", "reportar (erro interno)", "take-off")
        foot = _shell([_axis(w) for w in doc["pisos"][fl["name"]]["paredes"]]).area
        rooms = sum(float(r["area_m2"]) for r in fl["rooms"] if r["tipo"] != "exterior")
        check(f"divisoes_definidas[{fl['name']}]", bool(fl["rooms"]), "aviso", len(fl["rooms"]), "≥ 1",
              "clt_agente_definir_piso com as divisões (eletricidade, canalização, tetos e pintura dependem delas)", "clt_fitout")
        if fl["rooms"]:
            check(f"divisoes_dentro_do_contorno[{fl['name']}]", rooms <= foot * 1.05, "aviso",
                  {"divisoes_m2": round(rooms, 2), "contorno_m2": round(foot, 2)}, "divisões ≤ contorno exterior",
                  "divisão duplicada ou retângulo errado: rever as divisões", "clt_fitout × contorno das paredes")
            ratio = rooms / foot if foot else 0
            check(f"ocupacao_divisoes[{fl['name']}]", 0.6 <= ratio <= 1.02, "aviso", round(ratio, 3), "60–100 % do contorno",
                  "faltam divisões (corredores, arrumos?) ou a escala está errada", "clt_fitout × contorno das paredes")
        wet = [r["nome"] for r in fl["rooms"] if r["tipo"] in ("casa_de_banho", "cozinha", "lavandaria") and not r["aparelhos"]]
        check(f"aparelhos_sanitarios[{fl['name']}]", not wet, "aviso", wet, "zonas húmidas com aparelhos",
              "indicar os aparelhos visíveis na planta", "clt_fitout (canalização)")
        check(f"vaos_definidos[{fl['name']}]", bool(fl["windows"]), "aviso", len(fl["windows"]), "≥ 1 vão exterior",
              "indicar os vãos exteriores (caixilharia)", "clt_fitout (caixilharia)")
        density = tot / foot if foot else 0
        check(f"densidade_paredes[{fl['name']}]", 0.25 <= density <= 1.6, "aviso", round(density, 3), "0,25–1,6 m de parede por m²",
              "escala ou leitura suspeita: confirmar a escala e a imagem de controlo", "plausibilidade")
    # 4. traceability of every price and parameter
    used = [l for l in est["linhas"] if l["quantidade"]]
    no_price = [l["codigo"] for l in used if not l["custo_unitario_eur"] and l["fase"] != "venda"]
    check("precos_com_valor", not no_price, "aviso", no_price[:20], "todas as linhas usadas com preço",
          "a empresa deve preencher estes preços na biblioteca (/clt-industrial)", "biblioteca da empresa")
    hyp_lines = [f"{l['codigo']} · {l['designacao']}" for l in used if l["origem"] == "hipotese"]
    check("precos_rastreaveis", True, "aviso", {"com_fonte": len(used) - len(hyp_lines), "hipotese": len(hyp_lines)},
          "hipóteses listadas no dossier", "a empresa confirma as hipóteses em /clt-industrial › Custos, preços e plano", "biblioteca")
    concrete = [l["designacao"] for l in used if "betão" in l["designacao"].lower() and "leve" not in l["designacao"].lower()
                and l["custo_eur"]]
    check("sem_betao", not concrete, "aviso", concrete, "betão e lajes de betão fora do orçamento de venda",
          "retirar a linha de betão da biblioteca da empresa", "âmbito")
    check("venda_definida", (est["total"]["receita_eur"] or 0) > 0, "bloqueante", est["total"]["receita_eur"], "> 0",
          "a biblioteca não tem preços de venda: completar em /clt-industrial", "biblioteca")
    ok = sum(c["ok"] for c in checks)
    return {"checks": checks, "aprovadas": ok, "total": len(checks), "entrada": body, "origens": origins, "hipoteses_geometria": hyp,
            "geometria": {"total_m3_pecas": round(vol_pieces, 4), "paineis": cut["paineis"], "desperdicio_percent": cut["desperdicio_percent"],
                          "juntas": {a["piso"]: len(a["juntas"]) for a in geo["pisos"]}, "pecas": {a["piso"]: len(a["pecas"]) for a in geo["pisos"]}},
            "orcamento": {"total": est["total"], "pisos": [{k: r[k] for k in ("piso", "altura_m", "fabrico_m3", "montagem_m2", "custo_total_eur",
                                                                                "receita_eur", "margem_percent")} for r in est["pisos"]],
                          "plano": est["plano"], "notas": est["notas_quantidades"], "hipoteses_por_confirmar": est["hipoteses_por_confirmar"][:40],
                          "status": est["status"]}}



# ---------------------------------------------------------------------------------------------------------------------
# general engine (traditional construction and every system): engines.takeoff_core
# ---------------------------------------------------------------------------------------------------------------------
def _takeoff():
    try:
        from engines.takeoff_core import adaptadores, dossier, estudo
    except ImportError:
        return None
    return estudo, dossier, adaptadores


def read_takeoff_page(plan: dict, pagina: int, piso: str, ordem: int):
    """A page already measured in the take-off module (two-face walls of any thickness) → floor fields + control image."""
    t = _takeoff()
    if t is None:
        raise ValueError("O motor geral (construção tradicional) ainda não está instalado nesta versão.")
    _estudo, _dossier, adaptadores = t
    pages = {pg.get("index", i): pg for i, pg in enumerate(plan.get("pages") or [])}
    page = pages.get(pagina - 1)
    if not page:
        raise ValueError(f"A página {pagina} não existe nesta planta.")
    rooms = [r for r in plan.get("rooms") or [] if r.get("page_index", 0) == pagina - 1]
    cal = (plan.get("calibrations") or {}).get(str(pagina - 1)) or {}
    floor, notes = adaptadores.from_plan_page(page, name=piso, nivel=ordem, rooms=rooms, room_ppm=cal.get("pixels_per_meter"),
                                              ref=f"{plan.get('filename', plan.get('plan_id'))} p.{pagina}")
    walls = [{"id": w["id"], "x1": w["x1"], "y1": w["y1"], "x2": w["x2"], "y2": w["y2"], "thickness_mm": w["thickness_mm"],
              "layers": 5, "height_m": 3.0, "base_z_m": 0.0, "openings": [], "source": w.get("source", "")} for w in floor["paredes"]]
    png = None
    if page.get("image_png_b64"):
        import cv2
        import numpy as np
        img = cv2.imdecode(np.frombuffer(base64.b64decode(page["image_png_b64"]), np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            for w in (page.get("walls_analysis") or {}).get("walls") or []:
                a = w.get("axis") or {}
                if a and not w.get("is_post"):
                    cv2.line(img, (int(a["x1"]), int(a["y1"])), (int(a["x2"]), int(a["y2"])), (0, 0, 255), 4)
                    cv2.putText(img, str(w.get("wall_id", "")), (int(a["x1"]), int(a["y1"]) - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                                (0, 0, 180), 1, cv2.LINE_AA)
            scale = min(1.0, 1600 / max(img.shape[:2]))
            if scale < 1:
                img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            png = cv2.imencode(".png", img)[1].tobytes()
    fields = {"paredes": walls, "linteis": [], "fonte_paredes": f"módulo de medições, {plan.get('filename', '')} p.{pagina}",
              "estado": "medido no módulo de medições (" + floor.get("leitura", "vetorial") + "), vãos inferidos dos intervalos",
              "leitura": floor.get("leitura", "vetorial"), "divisoes_poligono": floor.get("divisoes", [])}
    return fields, {"notas_leitura": notes[:30]}, png


def _rect_poly(rect):
    x0, y0, x1, y1 = rect
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def general_project(doc, sistema, pais="PT"):
    estudo = _takeoff()[0]
    floors = []
    for p in _floors(doc):
        rooms = [{"nome": r["nome"][:60], "poligono": _rect_poly(r["rect_m"])} for r in p.get("divisoes") or [] if r.get("rect_m")]
        if not rooms:
            rooms = p.get("divisoes_poligono") or []
        walls = [{"id": w["id"], "x1": w["x1"], "y1": w["y1"], "x2": w["x2"], "y2": w["y2"], "thickness_mm": w["thickness_mm"],
                  "layers": w.get("layers") if sistema == "clt" else None, "openings": w.get("openings") or [],
                  "source": w.get("source", "")[:200]} for w in p["paredes"]]
        floors.append({"nome": p["nome"], "nivel": p["ordem"], "altura_m": p.get("altura_m"),
                       "altura_fonte": p.get("altura_origem") if p.get("altura_m") else "", "paredes": walls,
                       "linteis": [{k: li[k] for k in ("ref", "rect_m", "head_m", "thickness_mm")} for li in p.get("linteis", [])],
                       "divisoes": rooms, "ligar": True, "inferir_vaos": p.get("leitura") in ("vetorial", "dxf") and not p.get("linteis"),
                       "leitura": {"imagem": "imagem"}.get(p.get("leitura"), p.get("leitura") or "vetorial")})
    return estudo.Project(nome="Estudo", pais=pais or "PT", sistema=sistema, pisos=floors)


def run_general(doc, sistema, pais, values, library):
    """Same method on the general engine: quantities with origin, its own cross-checks, prices with sources."""
    estudo = _takeoff()[0]
    checks = []

    def check(cid, ok, nivel, valor, limite, como, origem=""):
        checks.append({"id": cid, "ok": bool(ok), "nivel": nivel, "valor": valor, "limite": limite, "como_corrigir": como, "motores": origem})

    try:
        result = estudo.run(general_project(doc, sistema, pais), values, library)
    except ValueError as exc:
        check("motores_geometria", False, "bloqueante", str(exc)[:300], "rede de paredes válida",
              "corrigir com clt_agente_corrigir_paredes a parede indicada no erro", "takeoff_core")
        return {"checks": checks}
    for c in result["verificacoes"]:
        if c.get("informativo"):
            continue
        check(f"{c['verificacao']}[{c['piso']}]", c["passou"], "bloqueante", {"a": c["a"], "b": c["b"], "erro_pct": c.get("erro_pct")},
              "≤ 2 %", "paredes duplicadas ou vãos fora da parede: ver a imagem de controlo", "takeoff_core.rede")
    for f in result["pisos"]:
        notes = (f.get("rede") or {}).get("notas") or []
        check(f"vaos_inferidos[{f['nome']}]", not f["vaos_inferidos"], "aviso", len(f["vaos_inferidos"]), "vãos lidos na planta",
              "vãos inferidos dos intervalos entre paredes ficam estimativa: confirmar na planta", "takeoff_core.rede")
        if notes:
            check(f"rede[{f['nome']}]", False, "aviso", notes[:10], "", "rever as ligações indicadas", "takeoff_core.rede")
    budget = result.get("orcamento")
    check("biblioteca_de_precos", bool(budget), "aviso", bool(budget), "biblioteca da empresa preenchida",
          "a empresa preenche a biblioteca de medições (/metodos/biblioteca); sem ela só há quantidades", "biblioteca")
    if budget:
        check("precos_em_falta", not budget["sem_preco"], "aviso", budget["sem_preco"][:20], "todas as quantidades com preço",
              "completar a biblioteca com os códigos indicados", "biblioteca")
    hyp = [f"{h['chave']}: {h.get('valor')} {h.get('unidade', '')} ({h.get('origem')}; {h.get('fonte', '')})" for h in result["hipoteses"]][:40]
    pub = estudo.public(result)
    ok = sum(c["ok"] for c in checks)
    return {"checks": checks, "aprovadas": ok, "total": len(checks), "hipoteses_geometria": hyp,
            "geometria": {"sistemas": pub["sistemas_usados"], "pisos": {f["nome"]: {"altura": f["altura"], "pecas": len(f["analise"]["pecas"])}
                                                                         for f in pub["pisos"]}},
            "orcamento": {"quantidades": pub["totais"][:60], "total": budget and {k: budget[k] for k in ("subtotal", "iva_pct", "iva", "total",
                                                                                                         "parte_estimativa", "iva_fonte")}}}


async def _takeoff_company(db, user):
    from bim_studio.store import tenant_of
    estudo = _takeoff()[0]
    doc = await db.takeoff_parameters.find_one({"_id": tenant_of(user)}) or {}
    lib = await db.takeoff_library.find_one({"_id": tenant_of(user)}) or {}
    return doc.get("valores") or {}, [estudo.PriceItem(**i) for i in lib.get("itens") or []]


def _brand(user):
    from engines.takeoff_core import dossier
    try:
        from bim_studio.clt_access import is_pilot
        from engines.calc_lots.premium import marca
        if is_pilot(user):
            b = marca("clt-rezult")
            if b:
                return {"nome": b["nome"], "cor": b["cor"], "logo_bytes": b.get("logo_bytes"), "site": b.get("site", "")}
    except Exception:  # noqa: BLE001 - the brand never blocks a dossier
        pass
    return dict(dossier.CONSTRUPILOT)


async def _general_dossier(doc, args, user, conv, db):
    import hashlib
    import uuid
    estudo, dossier, _a = _takeoff()
    values, library = await _takeoff_company(db, user)
    result = await asyncio.to_thread(estudo.run, general_project(doc, doc["sistema"], doc.get("pais")), values, library)
    pdf = await asyncio.to_thread(dossier.build, result, brand=_brand(user), lang=args.get("lingua") or "pt", title=args["titulo"])
    rid = conv.get("_quote_request_id") or conv["conversation_id"]
    aid = "file_" + hashlib.sha256(f"{rid}{doc['_id']}{doc['revisao']}{args}".encode()).hexdigest()[:27] + "g"
    art = {"artifact_id": aid, "user_id": user["user_id"], "conversation_id": conv["conversation_id"], "request_id": rid,
           "title": args["titulo"], "body": "", "filename": f"ConstruPilot_Dossier_{uuid.uuid4().hex[:6]}.pdf", "format": "pdf",
           "kind": "calc_note", "mime": "application/pdf", "size": len(pdf), "data_b64": base64.b64encode(pdf).decode(),
           "source_artifact_ids": [], "created_at": _now(), "illustrative": False, "calc_note": "metodos_comuns",
           "download": f"/assistant/artifacts/{aid}/content"}
    await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": user["user_id"]}, {"$setOnInsert": art}, upsert=True)
    pub = estudo.public(result)
    return {"ok": True, "artifact": {k: art[k] for k in ("artifact_id", "title", "filename", "format", "kind", "mime", "size", "download")},
            "resumo": {"sistemas": pub["sistemas_usados"], "orcamento": pub["orcamento"] and {k: pub["orcamento"][k] for k in ("subtotal", "iva", "total")}},
            "note": "Dossier produzido pelo motor geral. Restitui os resultados-chave e as hipóteses; não recalcules."}


# ---------------------------------------------------------------------------------------------------------------------
# tool execution
# ---------------------------------------------------------------------------------------------------------------------
async def execute(name, args, user, conv, db, load_doc):
    from bim_studio.clt_access import allowed, is_pilot
    if not allowed(user):
        return {"ok": False, "error": "O estudo CLT só está disponível nas contas da app PT."}
    doc = await _load(db, user, conv)
    if name == "clt_agente_estado":
        if args.get("reiniciar"):
            await db[COLLECTION].delete_one({"_id": doc["_id"], "tenant_id": doc["tenant_id"], "user_id": doc["user_id"]})
            doc = await _load(db, user, conv)
        return {"ok": True, **_public(doc)}

    if name == "clt_agente_ler_planta":
        params, _lib = await _company(db, user)
        h = args.get("altura_m") or _standard_height(params, args["ordem"])
        try:
            if args.get("plan_id"):
                plan = await db.plans_takeoff.find_one({"plan_id": args["plan_id"], "user_id": user["user_id"]},
                                                       {"_id": 0, "pages.vectors": 0, "pages.text_blocks": 0})
                if not plan:
                    return {"ok": False, "error": "Planta inacessível para esta conta."}
                fields, summary, png = await asyncio.to_thread(read_takeoff_page, plan, args.get("pagina") or 1, args["piso"][:60],
                                                               int(args["ordem"]))
                for w in fields["paredes"]:
                    w["height_m"] = h
            else:
                src = await load_doc(args["document_id"], user["user_id"])
                data = base64.b64decode(src.get("data_b64") or "")
                if not data or len(data) > 20 * 1024 * 1024:
                    return {"ok": False, "error": "Ficheiro vazio ou acima de 20 MB."}
                fields, summary, png = await asyncio.to_thread(read_sheet, data, src.get("mime", ""), args, h)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)[:400]}
        piso = {"nome": args["piso"][:60], "ordem": int(args["ordem"]), "document_id": args["document_id"], "pagina": args.get("pagina"),
                "altura_m": args.get("altura_m"), "altura_origem": "planta/corte" if args.get("altura_m") else f"standard da empresa ({h} m)",
                **fields}
        old = doc["pisos"].get(piso["nome"]) or {}
        for keep in ("divisoes_poligono",):
            if keep in piso and not piso[keep]:
                piso.pop(keep)
        for keep in ("divisoes", "vaos", "portas_interiores", "laje", "cobertura", "prumada_m", "fonte_piso"):
            if keep in old:
                piso[keep] = old[keep]
        doc["pisos"][piso["nome"]] = piso
        doc["registo"].append({"quando": _now(), "piso": piso["nome"], "acao": "leitura", "detalhe": f"{len(fields['paredes'])} paredes; {fields['fonte_paredes']}"})
        await _save(db, doc)
        walls = [{"id": w["id"], "x1": round(w["x1"], 3), "y1": round(w["y1"], 3), "x2": round(w["x2"], 3), "y2": round(w["y2"], 3),
                  "esp_mm": w["thickness_mm"], "L_m": round(math.hypot(w["x2"] - w["x1"], w["y2"] - w["y1"]), 3)} for w in fields["paredes"]]
        return {"ok": True, "piso": piso["nome"], "estado": fields["estado"], "altura_usada_m": h, "altura_origem": piso["altura_origem"],
                "paredes": walls[:150], "linteis": [{k: li[k] for k in ("ref", "rect_m", "head_m")} for li in fields["linteis"]],
                **summary, "controlo": "Imagem anexa: vermelho = paredes detetadas (número = id), azul = lintéis. Compara com a planta.",
                "passo_seguinte": next_step(doc), **({"_model_attachments": [_png_data_url(png)]} if png else {})}

    piso = doc["pisos"].get(args.get("piso") or "")
    if name in ("clt_agente_corrigir_paredes", "clt_agente_definir_piso") and not piso:
        return {"ok": False, "error": f"Piso desconhecido. Pisos do estudo: {list(doc['pisos'])}."}

    if name == "clt_agente_corrigir_paredes":
        from bim_studio.clt_walls import WallAxis
        motivo = (args.get("motivo") or "").strip()
        if len(motivo) < 8:
            return {"ok": False, "error": "Indique o motivo visível na planta (folha, zona, legenda)."}
        ids = {w["id"] for w in piso["paredes"]}
        unknown = [i for i in args.get("remover_ids", []) + [c["id"] for c in args.get("alterar", [])] if i not in ids]
        if unknown:
            return {"ok": False, "error": f"Paredes inexistentes: {unknown}."}
        walls = [w for w in piso["paredes"] if w["id"] not in set(args.get("remover_ids", []))]
        for c in args.get("alterar", []):
            for w in walls:
                if w["id"] == c["id"]:
                    if c.get("espessura_mm"):
                        w["thickness_mm"] = float(c["espessura_mm"])
                    if c.get("camadas"):
                        w["layers"] = int(c["camadas"])
                    w["source"] = (w.get("source", "") + f"; corrigido: {motivo}")[:200]
        h = walls[0]["height_m"] if walls else (piso.get("altura_m") or 3.0)
        n = 1 + max([int(w["id"].rsplit("C", 1)[1]) for w in walls if "-C" in w["id"] and w["id"].rsplit("C", 1)[1].isdigit()] or [0])
        for k, a in enumerate(args.get("acrescentar", [])):
            try:
                w = WallAxis(id=f"{piso['nome'][:20]}-C{n + k}", x1=a["x1"], y1=a["y1"], x2=a["x2"], y2=a["y2"], thickness_mm=a["espessura_mm"],
                             layers=a.get("camadas") or 5, height_m=h, source=f"acrescentada pelo assistente: {motivo}"[:200])
            except ValueError as exc:
                return {"ok": False, "error": str(exc)[:300]}
            walls.append(w.model_dump())
        if not walls:
            return {"ok": False, "error": "O piso ficaria sem paredes."}
        piso["paredes"] = walls
        piso["estado"] = "corrigido pelo assistente, por confirmar"
        doc["registo"].append({"quando": _now(), "piso": piso["nome"], "acao": "correcao", "detalhe": motivo[:300],
                               "removidas": args.get("remover_ids", []), "acrescentadas": len(args.get("acrescentar", [])),
                               "alteradas": [c["id"] for c in args.get("alterar", [])]})
        await _save(db, doc)
        return {"ok": True, **_public(doc)}

    if name == "clt_agente_definir_piso":
        fonte = (args.get("fonte") or "").strip()[:200]
        for key, field in (("divisoes", "divisoes"), ("vaos", "vaos"), ("portas_interiores", "portas_interiores"), ("laje", "laje"),
                           ("cobertura", "cobertura"), ("prumada_m", "prumada_m")):
            if args.get(key) is not None:
                piso[field] = args[key]
        if args.get("altura_m"):
            piso["altura_m"] = float(args["altura_m"])
            piso["altura_origem"] = f"planta/corte ({fonte})"
            for w in piso["paredes"]:
                w["height_m"] = piso["altura_m"]
        piso["fonte_piso"] = fonte
        doc["registo"].append({"quando": _now(), "piso": piso["nome"], "acao": "definicao",
                               "detalhe": f"{', '.join(k for k in ('divisoes', 'vaos', 'portas_interiores', 'laje', 'cobertura', 'altura_m', 'prumada_m') if args.get(k) is not None)}; fonte: {fonte}"})
        await _save(db, doc)
        return {"ok": True, **_public(doc)}

    if name == "clt_agente_calcular":
        if args.get("sistema") and args["sistema"] != doc.get("sistema", "clt"):
            doc["sistema"] = args["sistema"]
            doc["registo"].append({"quando": _now(), "acao": "sistema", "detalhe": args["sistema"]})
            await _save(db, doc)
        if args.get("pais"):
            doc["pais"] = args["pais"]
        sistema = doc.get("sistema", "clt")
        try:
            if sistema == "clt":
                params, library = await _company(db, user)
                out = await asyncio.to_thread(run_chain, doc, params, library, args.get("regime_iva") or "pt", args.get("inicio"),
                                              args.get("modo_inicio") or "compra")
            else:
                if _takeoff() is None:
                    return {"ok": False, "error": "O motor geral (construção tradicional) ainda não está instalado nesta versão."}
                values, library = await _takeoff_company(db, user)
                out = await asyncio.to_thread(run_general, doc, sistema, doc.get("pais") or "PT", values, library)
                out["entrada"] = {"sistema": sistema}
        except ValueError as exc:
            out = {"checks": [{"id": "motores", "ok": False, "nivel": "bloqueante", "valor": str(exc)[:300], "limite": "",
                               "como_corrigir": "corrigir o dado indicado no erro", "motores": "validação"}]}
        out.setdefault("aprovadas", sum(c["ok"] for c in out["checks"]))
        out.setdefault("total", len(out["checks"]))
        doc["verificacao"] = {"revisao": doc["revisao"], "checks": out["checks"], "aprovadas": out["aprovadas"], "total": out["total"],
                              "quando": _now()}
        if out.get("entrada"):
            doc["entrada"] = out["entrada"]
            doc["entrada_revisao"] = doc["revisao"]
        await _save(db, doc, changed=False)
        failed = [c for c in out["checks"] if not c["ok"]]
        return {"ok": True, "revisao": doc["revisao"], "sistema": sistema, "aprovadas": out["aprovadas"], "total": out["total"],
                "bloqueantes": [c for c in failed if c["nivel"] == "bloqueante"], "avisos": [c for c in failed if c["nivel"] != "bloqueante"],
                "aprovadas_ids": [c["id"] for c in out["checks"] if c["ok"]],
                **{k: out[k] for k in ("geometria", "orcamento", "origens", "hipoteses_geometria") if k in out},
                "passo_seguinte": next_step(doc), "note": "Números dos motores: restitui-os sem recalcular."}

    if name == "clt_agente_dossier":
        ver = doc.get("verificacao") or {}
        if ver.get("revisao") != doc.get("revisao") or doc.get("entrada_revisao") != doc.get("revisao"):
            return {"ok": False, "error": "O estudo mudou desde a última verificação: chama clt_agente_calcular primeiro."}
        blocking = [c for c in ver.get("checks", []) if not c["ok"] and c["nivel"] == "bloqueante"]
        if blocking:
            return {"ok": False, "error": "Verificação com falhas bloqueantes: corrige-as antes do dossier.", "bloqueantes": blocking}
        if doc.get("sistema", "clt") != "clt":
            res = await _general_dossier(doc, args, user, conv, db)
            doc["dossier"] = {"revisao": doc["revisao"], "artifact_id": res["artifact"]["artifact_id"], "quando": _now()}
            await _save(db, doc, changed=False)
            res["verificacao"] = {"aprovadas": ver.get("aprovadas"), "total": ver.get("total"),
                                  "avisos": [c["id"] for c in ver.get("checks", []) if not c["ok"]]}
            res["correcoes"] = doc.get("registo", [])[-20:]
            return res
        from engines.calc_lots.assistant_bridge import execute_calc_tool
        empresa = args.get("empresa") if args.get("empresa") != "clt-rezult" or is_pilot(user) else None
        res = await execute_calc_tool("estudo_clt_completo", {"titulo": args["titulo"], "local": args.get("local"), "empresa": empresa,
                                                              "regime_iva": doc["entrada"].get("vat_regime"), "lingua": args.get("lingua") or "pt",
                                                              "pisos_json": json.dumps(doc["entrada"], ensure_ascii=False)}, user, conv, db)
        if res.get("ok"):
            doc["dossier"] = {"revisao": doc["revisao"], "artifact_id": (res.get("artifact") or {}).get("artifact_id"), "quando": _now()}
            await _save(db, doc, changed=False)
            res["verificacao"] = {"aprovadas": ver.get("aprovadas"), "total": ver.get("total"),
                                  "avisos": [c["id"] for c in ver.get("checks", []) if not c["ok"]]}
            res["correcoes"] = doc.get("registo", [])[-20:]
        return res
    return {"ok": False, "error": "Ferramenta do agente CLT desconhecida."}

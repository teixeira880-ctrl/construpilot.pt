"""Leitura das plantas de arquitetura por IA (visão) → modelo JSON do edifício multifamiliar (modelo.py).

Única etapa « IA » : o modelo relevado é depois validado por controlos determinísticos (modelo.validate) e por um cálculo de ensaio
(pipeline.calcular sem 3D). Em caso de anomalia bloqueante, o levantamento é devolvido à IA com a lista das anomalias (2 correções
no máximo) ; se persistirem, devolvem-se PERGUNTAS ao utilizador em vez de um estudo falso. Reutiliza a leitura de páginas e a
cascata de fornecedores IA de bet_core.reader.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from . import modelo
from .modelo import BLOCK

EXAMPLE = Path(__file__).with_name("casos") / "exemplo_pt.json"
MAX_OUT = 32000

SYSTEM_PT = """És o desenhador-projetista de um gabinete de estruturas. Relevas, em plantas de arquitetura de um EDIFÍCIO MULTIFAMILIAR
(cave opcional + pisos de habitação), o modelo JSON usado pelos motores de cálculo ConstruPilot. Não calculas nada : só relevas.

REFERENCIAL : metros ; origem no eixo do pilar de canto da FACHADA PRINCIPAL (a da rua) à esquerda ; X ao longo dessa fachada,
Y para o tardoz. footprint L × B = distâncias entre eixos dos pilares de fachada. Arredonda a 0,01 m. Usa as cotas escritas.

RELEVA :
- project : name, address, municipality (concelho), altitude_m (cota do piso térreo se não houver outra), country, front_orientation
  (orientação da fachada principal : N, NE, E, SE, S, SO, O, NO — pela seta do norte).
- levels : basement (há cave ?), floors (número de pisos de habitação acima da cave, incluindo o piso térreo), storey_height
  (pé-direito estrutural piso a piso = diferença de cotas de pavimento), ground_floor_level (cota do piso 0), clear_height.
- columns : TODOS os pilares do piso-tipo com x, y e secção b (segundo X) × h (segundo Y) desenhada.
- cores : caixas de escada (kind "stair") e de elevador ("lift") pelas FACES EXTERIORES das paredes (x0, y0, x1, y1), espessura t,
  door {side x0|x1|y0|y1, width} = lado da porta de acesso.
- walls : paredes de betão desenhadas pela arquitetura (raras) ; NÃO inventes paredes : o motor propõe-nas.
- beams : null (o motor gera as vigas).
- balconies : varandas em consola por fachada {side y0 (principal) | y1 (tardoz) | x0 | x1, depth, from, to} (from/to em X ou Y).
- basement : polygon da cave (contorno exterior dos muros, vértices em ordem), walls [{from, to, soil_height, name}] (altura de
  terras retidas por muro, 0 se o muro não estiver enterrado), columns (pilares que só existem na cave), parking_spaces.
- soil : do estudo geotécnico se existir (sigma_rd_kpa, sigma_sls_kpa, ground_type A–E, geotech_report true) ; senão omite.
- seismic : zone_type1 / zone_type2 do concelho (Anexo Nacional NP EN 1998-1) se os conheceres com segurança ; senão omite.
- units : TODAS as frações, por piso : id (letra do quadro de frações), level (0 = piso térreo), typology "T1", rooms
  [{kind: sala|quarto|cozinha|casa_de_banho|lavandaria|corredor|escritorio|arrumos, name, area}] com as áreas escritas,
  facades [{orientation, length}] (comprimento de fachada exterior da fração por orientação), common_wall_m (comprimento de
  parede para a caixa de escada / hall comum), openings [{type, facade, count}].
- opening_types : {V1: {width, height, label}} — largura medida em planta, altura dos alçados (2,40 portas de sacada por defeito).
- common_openings : vãos das zonas comuns (porta de entrada…) com level.
- interior_walls_m : {partitions, separating, common} em ml por piso (listas por nível) se os conseguires medir ; senão omite.
- network / systems : se indicados.
- _decisions : lista das tuas hipóteses (uma frase cada) ; _questions : perguntas bloqueantes para o utilizador (se houver).

Responde APENAS com o JSON, sem comentários."""

SYSTEM_FR = SYSTEM_PT.replace("És o desenhador-projetista de um gabinete de estruturas.", "Tu es le dessinateur-projeteur d'un bureau d'études structure.") + \
    "\nPour un projet en France : country \"FR\", seismic {zone \"1\"–\"5\", importance \"II\"}, municipality = commune, room kinds en codes ci-dessus."

DECIDE_ALONE = ("\n\nMODO « DECIDIR SOZINHO » : o utilizador pediu para decidir com os documentos disponíveis. Não faças perguntas : "
                "toma a hipótese mais provável para cada ponto em falta e regista-a em \"_decisions\".")


def _example_text() -> str:
    ex = json.loads(EXAMPLE.read_text())
    ex["units"] = ex["units"][:4] + [ex["units"][5]]
    return json.dumps(ex, ensure_ascii=False)


def dry_run(raw: dict) -> dict | None:
    """Cálculo de ensaio (sem 3D, sem livrables) : → anomalia bloqueante se um motor falhar."""
    from . import pipeline
    try:
        S = modelo.load(copy.deepcopy(raw))
        R = pipeline.calcular(S, use_fem=False)
        blk = [a for a in R["anomalies"] if a["level"] == BLOCK]
        return blk[0] if blk else None
    except Exception as exc:  # noqa: BLE001
        return {"level": BLOCK, "code": "CALC", "message": f"Cálculo impossível com este levantamento ({type(exc).__name__}: {str(exc)[:160]})",
                "fix": "rever pilares, núcleos e contorno"}


def validate_raw(raw: dict) -> list[dict]:
    S = modelo.load(copy.deepcopy(raw))
    an = modelo.validate(S)
    if not any(a["level"] == BLOCK for a in an):
        d = dry_run(raw)
        if d:
            an.append(d)
    return an


async def read_building(docs: list[tuple[str, bytes]], hypotheses: str = "", country: str = "PT", llm=None, max_fix: int = 2,
                        decide_alone: bool = False) -> dict:
    from engines.bet_core import reader as BR
    llm = llm or BR._default_llm
    pages, by_doc = [], {}
    for name, data in docs:
        by_doc[name] = data
        pages += BR.pages_of(data, name)
    g2 = "\n".join(p["text"] for p in pages if p["kind"] == "g2")[:30000]
    chosen = BR.select_pages(pages)
    if not chosen:
        return {"ok": False, "model": None, "anomalies": [], "pages": [], "attempts": 0, "decisions": [],
                "questions": ["Não encontro plantas, cortes ou alçados nos documentos : junte as plantas de arquitetura em PDF."]}
    images = [BR.render_png(by_doc[p["doc"]], p["page"]) for p in chosen]
    legend = "\n\n".join(f"Imagem {i + 1} : {p['doc']} p.{p['page']} ({p['kind']}, folha {p['size_mm'][0]}×{p['size_mm'][1]} mm). "
                         f"Texto vetorial (palavra@x,y mm ; as cotas escritas são FIÁVEIS) : {p['words'] or '(nenhum — planta digitalizada)'}"
                         for i, p in enumerate(chosen))
    system = SYSTEM_FR if country == "FR" else SYSTEM_PT
    base = (f"EXEMPLO DE MODELO (outro edifício, mesmo esquema — não copies os valores) :\n{_example_text()}\n\nPAÍS : {country}\n"
            f"HIPÓTESES DO CLIENTE (prioritárias) : {hypotheses or 'nenhuma'}\n\nPEÇAS :\n{legend}\n\nESTUDO GEOTÉCNICO (texto) :\n{g2 or 'NENHUM'}\n\n"
            "Produz o modelo JSON DESTE edifício." + (DECIDE_ALONE if decide_alone else ""))
    txt = await llm(system, base, images=images, max_tokens=MAX_OUT)
    attempts, raw, anomalies = 1, None, []
    while True:
        try:
            raw = BR._extract_json(txt)
            raw.setdefault("project", {}).setdefault("country", country)
            anomalies = validate_raw(raw)
        except Exception as exc:  # noqa: BLE001
            anomalies = [{"code": "JSON", "level": BLOCK, "message": f"JSON ilegível : {exc}"}]
        blocking = [a for a in anomalies if a.get("level") == BLOCK]
        if not blocking or attempts > max_fix:
            break
        fix = (base + "\n\nO TEU LEVANTAMENTO ANTERIOR :\n" + (json.dumps(raw, ensure_ascii=False) if raw else txt[:20000]) +
               "\n\nOS CONTROLOS DETERMINÍSTICOS ENCONTRARAM ESTAS ANOMALIAS BLOQUEANTES :\n" +
               "\n".join(f"- {a['code']} : {a['message']} {a.get('fix', '')}" for a in blocking) +
               ("\n\nNão faças perguntas : decide a hipótese mais provável e regista-a em \"_decisions\"." if decide_alone else "") +
               "\n\nRelê as peças e devolve o JSON COMPLETO corrigido.")
        txt = await llm(system, fix, images=images, max_tokens=MAX_OUT)
        attempts += 1
    blocking = [a for a in anomalies if a.get("level") == BLOCK]
    decisions = [str(d) for d in (raw or {}).get("_decisions") or []]
    questions = [] if decide_alone else list((raw or {}).get("_questions") or []) + [f"{a['message']} — {a.get('fix') or 'a precisar'}" for a in blocking]
    if raw is not None and hypotheses:
        raw.setdefault("_decisions", []).append(f"Hipóteses do cliente : « {hypotheses[:300]} »")
    return {"ok": raw is not None and not blocking, "model": raw, "anomalies": anomalies, "questions": questions, "decisions": decisions,
            "pages": [{k: p[k] for k in ("doc", "page", "kind")} for p in chosen], "attempts": attempts,
            "provider": BR.LAST_PROVIDER[0] if hasattr(BR, "LAST_PROVIDER") else None}

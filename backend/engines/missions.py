"""Programa IA de opções (versão PT) — catálogo, ordem de execução e sínteses.

Le client coche des options sur son dossier ; chaque option est une fiche
préparée (prompt figé, moteurs autorisés, dépendances). Une fois la sélection
validée, le moteur exécute UNIQUEMENT ces options, dans l'ordre du catalogue.

Règle maison : les chiffres viennent toujours des moteurs déterministes. Le
prompt de l'option ne sert qu'à rédiger la synthèse du livrable, à partir des
seules données produites par le moteur.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

log = logging.getLogger("missions")

SYNTHESIS_TIMEOUT = 90
SYNTHESIS_MAX_CHARS = 12000

SYSTEM = (
    "És o motor IA do ConstruPilot, ao serviço de um profissional da construção em Portugal. "
    "Redige a síntese de um entregável APENAS a partir dos dados JSON fornecidos, "
    "produzidos por motores de cálculo determinísticos. Não inventes nenhum número, nenhuma norma, "
    "nenhuma quantidade: se faltar um dado, escreve « não determinado ». "
    "Responde em português europeu, no máximo 6 linhas, sem título: primeiro o resultado, "
    "depois os pontos a verificar antes de qualquer envio ao cliente."
)

# Ordem do dict = ordem de execução. `depends_on` = opções que têm de ter
# terminado antes; `needs` = peças do processo exigidas.
# Só opções com motor português: as notas térmicas, de estrutura, DPGF/CCTP e DPE do .fr
# aplicam regras francesas (NF DTU, RE2020, DPE) e não constam deste catálogo.
OPTIONS: dict[str, dict] = {
    "analyse_plans": {
        "name": "Leitura e análise das plantas",
        "group": "Plantas",
        "desc": "Relê cada planta, lista os elementos reconhecidos, as quantidades a verificar e as informações em falta.",
        "needs": ["plans"], "depends_on": [],
        "deliverable": "Análise por planta (estado, elementos, pontos em falta)",
        "prompt": "Resume o estado de análise de cada planta: o que é utilizável, o que falta "
                  "(escala, espessuras, alturas) e o que o profissional deve completar primeiro.",
    },
    "controle": {
        "name": "Controlo de qualidade dos dados",
        "group": "Plantas",
        "desc": "Controla a coerência das escalas, da geometria, das áreas e das quantidades, sem alterar nada.",
        "needs": ["plans"], "depends_on": [],
        "deliverable": "Relatório de controlo (pontos a verificar)",
        "prompt": "Resume o controlo: número de recursos controlados, incoerências encontradas e "
                  "os três pontos a verificar primeiro.",
    },
    "metre": {
        "name": "Medição",
        "group": "Medição e orçamento",
        "desc": "Faz o ponto das áreas, lineares, medições e aberturas levantadas nas plantas.",
        "needs": ["plans"], "depends_on": [],
        "deliverable": "Síntese da medição por planta",
        "prompt": "Resume a medição: áreas, número de medições e de aberturas por planta, "
                  "e as plantas que ainda não têm nenhuma medição.",
    },
    "plan_electricite": {
        "name": "Planta de eletricidade",
        "group": "Planos de execução",
        "desc": "Implantação de tomadas, pontos de luz e comandos, esquema unifilar e quantitativo (RTIEBT).",
        "needs": ["plans"], "depends_on": [],
        "deliverable": "Estudo de eletricidade (plantas por piso, unifilar, PDF)",
        "prompt": "Resume o estudo de eletricidade: número de circuitos e de pontos, proteções principais "
                  "e controlos de conformidade a rever. Lembra que o estudo é indicativo.",
    },
    "plan_plomberie": {
        "name": "Planta de canalização",
        "group": "Planos de execução",
        "desc": "Coletores de água fria e quente, redes, tubos de queda e coletores de esgoto, diâmetros e inclinações (DR 23/95).",
        "needs": ["plans"], "depends_on": [],
        "deliverable": "Estudo de canalização (plantas por piso, PDF)",
        "prompt": "Resume o estudo de canalização: aparelhos servidos, diâmetros e inclinações adotados, "
                  "controlos a rever. Lembra que o estudo é indicativo.",
    },
    "devis": {
        "name": "Orçamento por lotes",
        "group": "Medição e orçamento",
        "desc": "Orçamenta as medições associadas a um artigo com os seus preços e cria um orçamento em rascunho editável.",
        "needs": ["plans"], "depends_on": ["metre"],
        "deliverable": "Orçamento em rascunho (nunca enviado automaticamente)",
        "prompt": "Resume o orçamento criado e lembra que está em rascunho: o profissional tem de "
                  "rever quantidades, preços e IVA antes de qualquer envio.",
    },
    "planning": {
        "name": "Planeamento da obra",
        "group": "Organização",
        "desc": "Gera o planeamento Gantt do processo a partir dos lotes dos orçamentos associados.",
        "needs": ["chantier"], "depends_on": [],
        "deliverable": "Planeamento Gantt (durações por defeito a confirmar)",
        "prompt": "Resume o planeamento: número de tarefas, data de fim calculada e durações por defeito "
                  "a confirmar.",
    },
    "dossier": {
        "name": "Processo completo em PDF",
        "group": "Organização",
        "desc": "Agrupa as plantas por piso, a medição e o orçamento num processo PDF com capa.",
        "needs": ["plans"], "depends_on": ["metre"],
        "deliverable": "Processo PDF",
        "prompt": "Resume o conteúdo do processo PDF produzido: pisos e totais.",
    },
    "partage": {
        "name": "Partilha do processo",
        "group": "Organização",
        "desc": "Prepara uma ligação só de leitura para os PDF produzidos por este programa (estudos de eletricidade e "
                "canalização). A ligação fica inativa até a ativar; nada é enviado.",
        "needs": [], "depends_on": [],
        "deliverable": "Ligação de partilha pronta a ativar",
        "prompt": "Indica os documentos prontos a partilhar e que a ligação tem de ser ativada pelo profissional antes de a enviar.",
    },
}


class MissionError(ValueError):
    """Seleção inválida (mensagem apresentável)."""


async def effective_options(db) -> dict[str, dict]:
    """Catalogue + surcharges admin (prompt modifié, option désactivée)."""
    out = {k: {**v, "key": k, "enabled": True, "prompt_version": 0} for k, v in OPTIONS.items()}
    async for row in db.mission_options.find({}, {"_id": 0}):
        spec = out.get(row.get("key"))
        if not spec:
            continue
        if row.get("prompt"):
            spec["prompt"] = row["prompt"]
            spec["prompt_version"] = int(row.get("version") or 0)
        if row.get("enabled") is False:
            spec["enabled"] = False
    return out


def resolve(selected: list[str], catalog: dict[str, dict], *, has_plans: bool, has_chantier: bool) -> list[str]:
    """Valide la sélection et renvoie les options dans l'ordre d'exécution.

    Ne rajoute JAMAIS d'option : une dépendance manquante est une erreur, le client
    doit la cocher lui-même (il n'y a d'exécuté que ce qui a été validé)."""
    if not selected:
        raise MissionError("Assinale pelo menos uma opção")
    if len(set(selected)) != len(selected):
        raise MissionError("Opção assinalada em duplicado")
    for key in selected:
        spec = catalog.get(key)
        if not spec or not spec.get("enabled", True):
            raise MissionError(f"Opção desconhecida ou indisponível: {key}")
        missing = [d for d in spec["depends_on"] if d not in selected]
        if missing:
            names = ", ".join(f"« {catalog[d]['name']} »" for d in missing)
            raise MissionError(f"« {spec['name']} » exige também {names}")
        if "plans" in spec["needs"] and not has_plans:
            raise MissionError(f"« {spec['name']} » exige pelo menos uma planta")
        if "chantier" in spec["needs"] and not has_chantier:
            raise MissionError(f"« {spec['name']} » tem de ser lançada a partir de um processo de obra")
    return [k for k in catalog if k in selected]


def _compact(result: dict) -> str:
    text = json.dumps(result, ensure_ascii=False, default=str)
    return text[:SYNTHESIS_MAX_CHARS]


async def synthesize(prompt: str, result: dict, feature: str = "mission") -> str | None:
    """Synthèse rédigée par l'IA. Facultative : un échec ne bloque jamais le livrable."""
    if os.environ.get("MISSION_SYNTHESIS", "1") == "0" or not prompt:
        return None
    from engines.ai import _complete
    try:
        out = await asyncio.wait_for(
            _complete(SYSTEM, f"{prompt}\n\nDados do motor:\n{_compact(result)}", feature=feature),
            SYNTHESIS_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 -- provider errors never reach the client
        log.warning("Mission synthesis unavailable (%s)", type(exc).__name__)
        return None
    out = (out or "").strip()
    return out[:2000] or None

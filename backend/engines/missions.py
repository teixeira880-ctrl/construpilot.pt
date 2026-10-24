"""Programa IA de opções (versão PT) — catálogo, ordem de execução e sínteses.

O profissional assinala opções no seu processo; cada opção é uma ficha preparada (prompt fixo, motores autorizados,
dependências). Uma vez validada a seleção, o motor executa APENAS essas opções, pela ordem do catálogo.

Regra da casa: os números vêm sempre dos motores determinísticos portugueses. O prompt da opção serve apenas para
redigir a síntese do entregável, a partir dos dados produzidos pelo motor. A síntese é facultativa: uma falha (sem rede,
conta demo offline, fornecedor indisponível) nunca bloqueia o entregável.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

log = logging.getLogger("missions")

SYNTHESIS_TIMEOUT = 90
SYNTHESIS_TIMEOUT_DEMO = 20
SYNTHESIS_MAX_CHARS = 12000

SYSTEM = (
    "És o motor IA do ConstruPilot, ao serviço de um profissional da construção em Portugal. "
    "Redige a síntese de um entregável APENAS a partir dos dados JSON fornecidos, "
    "produzidos por motores de cálculo determinísticos. Não inventes nenhum número, nenhuma norma, "
    "nenhum artigo de lei nem nenhuma quantidade: se faltar um dado, escreve « não determinado ». "
    "Responde em português europeu, no máximo 6 linhas, sem título: primeiro o resultado, "
    "depois os pontos a verificar antes de qualquer envio ao cliente."
)

# Ordem do dict = ordem de execução. `depends_on` = opções que têm de ter
# terminado antes; `needs` = peças do processo exigidas.
# Só motores portugueses: térmica = cadeia lotes_tecnicos (EN 12831-1, NP EN 1264, bomba de calor), estrutura =
# structuro_house (Eurocódigos NP EN), pré-certificado = calc_lots.reh, mapa de quantidades / caderno de encargos =
# engines.mapa_caderno (referências gerais, prescrições a completar).
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
    "thermique": {
        "name": "Térmica: perdas de calor, piso radiante, bomba de calor",
        "group": "Especialidades técnicas",
        "desc": "Perdas de calor divisão a divisão (EN 12831-1) a partir das divisões da planta, piso radiante (NP EN 1264) e "
                "bomba de calor ar/água, com nota de cálculo PDF. O concelho do processo fixa o clima REH.",
        "needs": ["plans", "chantier"], "depends_on": [],
        "deliverable": "Nota de cálculo térmico PDF (indicativa)",
        "prompt": "Resume a nota térmica: perdas de calor totais, potência da bomba de calor e apoio, temperatura de ida, controlos "
                  "não conformes e hipóteses a confirmar (U das paredes, alturas das caixilharias, concelho). Lembra que é indicativa "
                  "e não substitui o projeto de AVAC nem o pré-certificado SCE.",
    },
    "structure": {
        "name": "Estrutura (moradia)",
        "group": "Especialidades técnicas",
        "desc": "Lajes, descida de cargas, alvenaria resistente, lintéis, cintas e sapatas (Eurocódigos NP EN com Anexos Nacionais), "
                "nota e desenhos PDF a partir da implantação lida na planta. Ação sísmica não verificada.",
        "needs": ["plans"], "depends_on": [],
        "deliverable": "Nota de estrutura PDF (pré-dimensionamento, a validar por engenheiro civil)",
        "prompt": "Resume o estudo de estrutura: implantação e pisos considerados, elementos principais (lajes, lintéis, sapatas), "
                  "avisos e hipóteses (forma real, solo sem estudo geotécnico, ação sísmica não verificada). Lembra que é um "
                  "pré-dimensionamento a verificar e assinar por engenheiro civil.",
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
    "dpgf": {
        "name": "Mapa de quantidades e caderno de encargos por especialidade",
        "group": "Medição e orçamento",
        "desc": "Retoma o orçamento em rascunho e organiza-o por especialidade: mapa de quantidades Excel (quantidades, preços, "
                "subtotais) e estrutura de caderno de encargos Word com as referências gerais de cada especialidade.",
        "needs": ["plans"], "depends_on": ["devis"],
        "deliverable": "Mapa de quantidades Excel + caderno de encargos Word (prescrições a completar)",
        "prompt": "Resume o mapa de quantidades: número de especialidades, total sem IVA, linhas ainda por orçamentar, e lembra que "
                  "as prescrições do caderno de encargos são a completar pelo autor do caderno de encargos.",
    },
    "dpe": {
        "name": "Pré-certificado energético (REH, indicativo)",
        "group": "Especialidades técnicas",
        "desc": "Classe energética estimada segundo a metodologia do REH a partir da área útil lida na planta e do concelho do "
                "processo. Indicativo: não substitui o certificado SCE emitido por Perito Qualificado (ADENE).",
        "needs": ["plans", "chantier"], "depends_on": [],
        "deliverable": "Pré-certificado REH PDF (indicativo, não substitui o certificado SCE/ADENE)",
        "prompt": "Resume o pré-certificado: classe energética, rácio Ntc/Nt, necessidades de aquecimento e arrefecimento, "
                  "hipóteses principais (ano, envolvente por defeito, sistemas). Lembra que é indicativo e não substitui o "
                  "certificado SCE emitido por Perito Qualificado (ADENE).",
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
        "desc": "Prepara uma ligação só de leitura para os entregáveis deste programa (estudos de eletricidade e canalização, "
                "notas de cálculo, pré-certificado, mapa de quantidades, caderno de encargos). A ligação fica inativa até a ativar; "
                "nada é enviado.",
        "needs": [], "depends_on": [],
        "deliverable": "Ligação de partilha pronta a ativar",
        "prompt": "Indica os documentos prontos a partilhar e que a ligação tem de ser ativada pelo profissional antes de a enviar.",
    },
}


class MissionError(ValueError):
    """Seleção inválida (mensagem apresentável)."""


async def effective_options(db) -> dict[str, dict]:
    """Catálogo + alterações do administrador (prompt modificado, opção desativada)."""
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
    """Valida a seleção e devolve as opções pela ordem de execução.

    NUNCA acrescenta uma opção: uma dependência em falta é um erro, o profissional tem de a assinalar ele próprio
    (só é executado o que foi validado)."""
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
            names = ", ".join(f"« {catalog[d]['name']} »" if d in catalog else f"« {d} » (indisponível)" for d in missing)
            raise MissionError(f"« {spec['name']} » exige também {names}")
        if "plans" in spec["needs"] and not has_plans:
            raise MissionError(f"« {spec['name']} » exige pelo menos uma planta")
        if "chantier" in spec["needs"] and not has_chantier:
            raise MissionError(f"« {spec['name']} » tem de ser lançada a partir de um processo de obra")
    return [k for k in catalog if k in selected]


def _compact(result: dict) -> str:
    text = json.dumps(result, ensure_ascii=False, default=str)
    return text[:SYNTHESIS_MAX_CHARS]


async def synthesize(prompt: str, result: dict, feature: str = "mission", user: dict | None = None) -> str | None:
    """Síntese redigida pela IA. Facultativa: uma falha nunca bloqueia o entregável.

    Contas demo: prazo curto e quota IA demo respeitada (offline → None sem esperar o prazo completo)."""
    if os.environ.get("MISSION_SYNTHESIS", "1") == "0" or not prompt:
        return None
    timeout = SYNTHESIS_TIMEOUT
    if user and user.get("is_demo"):
        timeout = SYNTHESIS_TIMEOUT_DEMO
        try:
            from core.demo_guards import consume_demo_ai_quota
            await consume_demo_ai_quota(user)
        except Exception:  # noqa: BLE001 -- quota esgotada ou base indisponível: entregável sem síntese
            return None
    try:
        from engines.ai import _complete
        out = await asyncio.wait_for(
            _complete(SYSTEM, f"{prompt}\n\nDados do motor:\n{_compact(result)}", feature=feature),
            timeout)
    except Exception as exc:  # noqa: BLE001 -- provider errors never reach the client
        log.warning("Mission synthesis unavailable (%s)", type(exc).__name__)
        return None
    out = (out or "").strip()
    return out[:2000] or None

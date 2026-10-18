"""Checks determinísticos semânticos.

Regras:
    SEM-001  Hipóteses do utilizador respeitadas (ex: laje aligeirada imposta
             não pode aparecer como `macica` no BuildingModel).
    SEM-002  Classificação de sótão habitável coerente (altura ≥ 1.80 m em
             ≥50 % da área + janelas + acesso de escada).
    SEM-003  Nenhum piso inventado — cada piso tem `source.extraction_method`
             diferente de `vision` ou tem confidence ≥ 0.7.
    SEM-004  Nenhum "OK verde" se houver anomalia bloqueante/grave
             (validado em `summary.build_summary`).
    SEM-005  Entregáveis pedidos pelo utilizador coerentes com âmbito do
             bet_agent (fora de âmbito marcados).

A regra SEM-004 vive em `summary.py`. As restantes vivem aqui.
"""
from __future__ import annotations

from engines.bet_agent.models.brief import SlabType, UserBrief
from engines.bet_agent.models.building import (
    BuildingModel,
    ExtractionMethod,
    FloorKind,
    StructuralKind,
)
from engines.bet_agent.models.summary import (
    Anomaly,
    AnomalySeverity,
    AnomalySource,
)
from engines.bet_agent.registry.deliverables_pt import OUT_OF_SCOPE


def _check_sem001_user_slab_type(building: BuildingModel, brief: UserBrief) -> list[Anomaly]:
    """SEM-001 — se o utilizador fixou um `slab_type`, nenhum elemento LAJE
    pode contradizer essa escolha através de metadados do próprio modelo."""
    out: list[Anomaly] = []
    user_slab = brief.materials.slab_type
    if user_slab is None:
        return out

    # Marcador simples: se slab imposta é 'aligeirada' e vemos elementos LAJE
    # com `width_mm`/`height_mm` típicos de laje maciça (ex: thickness ≥ 200
    # mm continuous sem indicação de aligeiramento), levantar aviso.
    # L1: validamos a presença das lajes e deixamos um aviso informativo
    # (cálculo real da espessura mínima virá no L2 pela EC2).
    for s in building.structural_elements:
        if s.kind != StructuralKind.LAJE:
            continue
        if s.user_imposed:
            # O utilizador fixou expressamente este elemento, aceitar.
            continue
        if user_slab == SlabType.ALIGEIRADA_VIGOTAS_ABOBADILHAS and s.thickness_mm:
            # Laje aligeirada típica 20+5 ≈ 250 mm; se o pipeline leu <180 mm,
            # é incoerente com a hipótese imposta.
            if s.thickness_mm < 180:
                out.append(Anomaly(
                    severity=AnomalySeverity.GRAVE,
                    code="SEM-001",
                    message_pt=(
                        f"Laje {s.id} com espessura lida {s.thickness_mm} mm é "
                        f"incompatível com hipótese do utilizador "
                        "`aligeirada_vigotas_abobadilhas` (típico ≥ 200 mm)."
                    ),
                    source=AnomalySource(page=s.source.page, bbox=s.source.bbox),
                    remediation="Rever leitura ou confirmar com o utilizador se mantém a hipótese.",
                ))
    return out


def _check_sem002_sotao_habitable(building: BuildingModel) -> list[Anomaly]:
    """SEM-002 — classificação de sótão habitável coerente.

    Critério determinístico (R1):
      - Piso.kind = SOTAO
      - altura_livre ≥ 1.80 m em ≥ 50 % da área (approx usando height_clear_m como
        altura média; se room-level data existir, pode-se refinar em L2)
      - tem janelas (openings de kind=JANELA ligadas a walls deste piso)
      - tem acesso por escada
    Falha de qualquer critério ⇒ SE marcado habitable=True no BuildingModel,
    anomalia GRAVE. Se marcado habitable=False mas critérios satisfeitos,
    anomalia AVISO (pode ser conservador).
    """
    out: list[Anomaly] = []
    for f in building.floors:
        if f.kind != FloorKind.SOTAO:
            continue
        if f.habitable is None:
            # Não decidido ainda — não é anomalia aqui, pipeline decide depois.
            continue
        # Critérios
        has_height = (f.height_clear_m or 0) >= 1.80
        walls_this_floor = {w.id for w in building.walls if w.floor_id == f.id}
        has_window = any(
            o for o in building.openings
            if o.wall_id in walls_this_floor and o.kind.value == "janela"
        )
        has_stair_access = any(
            s for s in building.stairs if s.floor_to_id == f.id or s.floor_from_id == f.id
        )
        criteria_met = has_height and has_window and has_stair_access

        if f.habitable and not criteria_met:
            missing = []
            if not has_height:
                missing.append("altura mínima 1.80 m")
            if not has_window:
                missing.append("janelas")
            if not has_stair_access:
                missing.append("acesso por escada")
            out.append(Anomaly(
                severity=AnomalySeverity.GRAVE,
                code="SEM-002",
                message_pt=(
                    f"Sótão {f.id} marcado como habitável mas falham critérios: "
                    + ", ".join(missing)
                    + "."
                ),
                source=AnomalySource(page=f.source.page, bbox=f.source.bbox),
                remediation="Reclassificar como não habitável OU alterar projecto para cumprir critérios.",
            ))
        elif not f.habitable and criteria_met:
            out.append(Anomaly(
                severity=AnomalySeverity.AVISO,
                code="SEM-002",
                message_pt=(
                    f"Sótão {f.id} tem altura, janelas e acesso suficientes "
                    "mas foi classificado como não habitável — confirmar intenção."
                ),
                source=AnomalySource(page=f.source.page, bbox=f.source.bbox),
                remediation="Confirmar com utilizador a classificação pretendida.",
            ))
    return out


def _check_sem003_floor_not_invented(building: BuildingModel) -> list[Anomaly]:
    """SEM-003 — todo piso tem fonte sólida (user ou vector_text) OU confidence ≥ 0.7."""
    out: list[Anomaly] = []
    for f in building.floors:
        method = f.source.extraction_method
        if method in (ExtractionMethod.USER, ExtractionMethod.VECTOR_TEXT):
            continue
        # vision → precisa de confidence ≥ 0.7
        if f.confidence < 0.7:
            out.append(Anomaly(
                severity=AnomalySeverity.BLOQUEANTE,
                code="SEM-003",
                message_pt=(
                    f"Piso {f.id} ({f.kind.value}) lido apenas por vision com confiança "
                    f"{f.confidence:.2f} < 0.70 — risco de piso inventado."
                ),
                source=AnomalySource(page=f.source.page, bbox=f.source.bbox),
                remediation="Re-leitura em zoom OU pedir confirmação ao utilizador OU importar do CAD vectorial.",
            ))
    return out


def _check_sem005_requested_scope(brief: UserBrief) -> list[Anomaly]:
    """SEM-005 — avisa se o utilizador pediu algum entregável explicitamente fora de âmbito."""
    out: list[Anomaly] = []
    # Em `UserBrief.requested_deliverables` só se podem meter valores do enum
    # `DeliverableKind` — portanto esta regra é mais um guard para o caso de
    # existirem notas pedindo coisas fora de âmbito.
    if not brief.notes:
        return out
    import unicodedata
    normalized = unicodedata.normalize("NFD", brief.notes.lower())
    stripped = "".join(c for c in normalized if not unicodedata.combining(c))
    for oos in OUT_OF_SCOPE:
        tokens = oos.split("_")  # ex: ["termica", "reh"]
        if all(tok in stripped for tok in tokens):
            out.append(Anomaly(
                severity=AnomalySeverity.AVISO,
                code="SEM-005",
                message_pt=(
                    f"Pedido referencia '{oos}', que está fora de âmbito do módulo "
                    "estrutural BET-PT. Será marcado como não produzido."
                ),
                source=AnomalySource(),
                remediation="Encaminhar pedido para o módulo apropriado (térmica, acústica, gás ou SCIE).",
            ))
    return out


def run_semantic_checks(building: BuildingModel, brief: UserBrief) -> list[Anomaly]:
    """Pipeline semântico — executa todas as regras e devolve lista agregada."""
    result: list[Anomaly] = []
    result.extend(_check_sem001_user_slab_type(building, brief))
    result.extend(_check_sem002_sotao_habitable(building))
    result.extend(_check_sem003_floor_not_invented(building))
    result.extend(_check_sem005_requested_scope(brief))
    return result

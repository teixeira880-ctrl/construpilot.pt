"""Esquemas Pydantic v2 estritos para o motor Plans Pro.

Regras duras:
    * `extra="forbid"`  →  campo não previsto rejeita a validação.
    * `strict=True`     →  tipos não coagidos (um `str` não vira `int`).
    * Zero `Optional[Any]`: todos os `None` admitidos têm tipo concreto.
    * Toda a classe e campo trazem docstring em PT-PT.

Preferimos elementos com todos os campos expostos a nível de `ElementoBase`
(flat schema) porque:
    1. Facilita a geração de JSON Schema estrito para a OpenAI (sem
       discriminated unions, que são frágeis em modo `strict=true`).
    2. Permite o LLM preencher parcialmente — campos irrelevantes ficam
       a `None` e são lidos como "dado em falta" pela camada
       `cross_check`.
Classes especializadas (`Sapata`, `Armadura`, ...) existem para
*validação adicional em Python*: podem ser construídas a partir de um
`ElementoBase` para enforce de tipos obrigatórios.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Config base
# ---------------------------------------------------------------------------
class _StrictModel(BaseModel):
    """Modelo base com `extra="forbid"` + `strict=True`.

    Serve para TODOS os esquemas da camada semântica. Qualquer tentativa
    de inserir um campo não previsto levanta `ValidationError`.
    """

    model_config = ConfigDict(extra="forbid", strict=True)


CategoriaMaterial = Literal[
    "betao",
    "aco",
    "alvenaria",
    "madeira",
    "isolamento",
    "revestimento",
    "outros",
]
"""Famílias de materiais reconhecidas pelo motor PT-BTP."""


UnidadeDimensao = Literal["mm", "cm", "m"]
"""Unidades métricas admitidas. Imperiais são convertidas antes de entrar."""


EixoDimensao = Literal[
    "x",
    "y",
    "z",
    "comprimento",
    "largura",
    "altura",
    "espessura",
    "diametro",
]
"""Rótulo semântico do eixo medido."""


SourceElemento = Literal[
    "ocr",
    "geometria",
    "aps_classification",
    "llm",
    "deducao_heuristica",
    "cross_check",
]
"""Origem factual de um elemento. Permite auditar a fonte na UI."""


Criticidade = Literal["bloqueante", "importante", "opcional"]
"""Peso de uma pergunta `MissingDataRequest` no bloqueio da pipeline."""


Severidade = Literal["info", "aviso", "erro"]
"""Gravidade de um `CrossCheckWarning`. `erro` força revisão humana."""


# ---------------------------------------------------------------------------
# Material / dimensão
# ---------------------------------------------------------------------------
class Material(_StrictModel):
    """Material reconhecido (ex.: betão `C25/30`, aço `A500NR`, bloco `PP 20`)."""

    nome: str = Field(
        description="Designação curta do material tal como lida no plano.",
    )
    categoria: CategoriaMaterial = Field(
        description="Família de material (betão, aço, alvenaria, ...).",
    )
    classe: str | None = Field(
        default=None,
        description="Classe normativa quando aplicável (ex.: 'C25/30', 'A500NR').",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Grau de confiança 0..1 da identificação do material.",
    )


class Dimensao(_StrictModel):
    """Medida tipada com unidade métrica e eixo semântico."""

    valor: float = Field(
        description="Valor numérico expresso na unidade indicada.",
    )
    unidade: UnidadeDimensao = Field(
        description="Unidade métrica: `mm` | `cm` | `m`.",
    )
    eixo: EixoDimensao = Field(
        description="Eixo ou rótulo semântico (comprimento, largura, ...).",
    )


# ---------------------------------------------------------------------------
# Elemento (schema flat para suporte estrito a OpenAI JSON Schema)
# ---------------------------------------------------------------------------
class ElementoBase(_StrictModel):
    """Elemento estrutural detectado numa planta.

    Schema deliberadamente *flat*: todos os campos opcionais específicos
    (ex.: `diametro_mm` para armadura, `cota_assentamento` para sapata)
    vivem aqui para facilitar o structured output da OpenAI. As classes
    especializadas (`Sapata`, `Armadura`, ...) herdam e podem impor
    constraints adicionais.
    """

    id: str = Field(
        description="Identificador único do elemento neste plano (ex.: 'SAP-01').",
    )
    tipo: str = Field(
        description=(
            "Tipo semântico: 'sapata' | 'muro_soubassement' | 'armadura' | "
            "'laje' | 'pilar' | 'viga' | 'abertura' | string livre reconhecida."
        ),
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confiança agregada 0..1 da detecção.",
    )
    source: SourceElemento = Field(
        description="Fonte factual do elemento (OCR, APS, LLM, ...).",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Avisos textuais em PT-PT associados a este elemento.",
    )
    dimensoes: list[Dimensao] = Field(
        default_factory=list,
        description="Dimensões associadas (ex.: largura x comprimento x espessura).",
    )
    material: Material | None = Field(
        default=None,
        description="Material identificado (`None` se desconhecido).",
    )
    cota_assentamento: float | None = Field(
        default=None,
        description="Cota de assentamento em metros (`Sapata`/`Muro`).",
    )
    diametro_mm: float | None = Field(
        default=None,
        description="Diâmetro em mm (`Armadura`).",
    )
    racio_kg_m3: float | None = Field(
        default=None,
        description="Rácio de armadura kg/m³ de betão (`Armadura`).",
    )
    classe_aco: str | None = Field(
        default=None,
        description="Classe do aço (ex.: 'A400', 'A500', 'A500NR').",
    )
    sub_tipo: str | None = Field(
        default=None,
        description="Sub-tipo para abertura: 'porta' | 'janela' | ...",
    )


class Sapata(ElementoBase):
    """Sapata de fundação. `tipo` deve ser `'sapata'`.

    Impõe presença de `material`, `cota_assentamento` e pelo menos uma
    dimensão. Usada em validação pós-LLM.
    """

    tipo: Literal["sapata"] = Field(
        default="sapata",
        description="Marcador discriminador: sempre 'sapata'.",
    )


class MuroSoubassement(ElementoBase):
    """Muro de soubassement (muro de embasamento). `tipo` = `'muro_soubassement'`."""

    tipo: Literal["muro_soubassement"] = Field(
        default="muro_soubassement",
        description="Marcador discriminador: sempre 'muro_soubassement'.",
    )


class Armadura(ElementoBase):
    """Armadura de betão armado (ferros). `tipo` = `'armadura'`."""

    tipo: Literal["armadura"] = Field(
        default="armadura",
        description="Marcador discriminador: sempre 'armadura'.",
    )


class Laje(ElementoBase):
    """Laje estrutural. `tipo` = `'laje'`."""

    tipo: Literal["laje"] = Field(
        default="laje",
        description="Marcador discriminador: sempre 'laje'.",
    )


class Pilar(ElementoBase):
    """Pilar estrutural. `tipo` = `'pilar'`."""

    tipo: Literal["pilar"] = Field(
        default="pilar",
        description="Marcador discriminador: sempre 'pilar'.",
    )


class Viga(ElementoBase):
    """Viga estrutural. `tipo` = `'viga'`."""

    tipo: Literal["viga"] = Field(
        default="viga",
        description="Marcador discriminador: sempre 'viga'.",
    )


class Abertura(ElementoBase):
    """Abertura (porta ou janela). `tipo` = `'abertura'`, `sub_tipo` diferencia."""

    tipo: Literal["abertura"] = Field(
        default="abertura",
        description="Marcador discriminador: sempre 'abertura'.",
    )


# ---------------------------------------------------------------------------
# Missing data / cross-check
# ---------------------------------------------------------------------------
class MissingDataRequest(_StrictModel):
    """Pergunta tipada que o motor devolve quando não consegue inferir um
    dado crítico sem inventar.

    Deve ser apresentada ao utilizador na UI (modal) em PT-PT.
    """

    question_pt: str = Field(
        description="Pergunta em PT-PT clara e directa para o utilizador.",
    )
    field: str = Field(
        description=(
            "Nome lógico do campo em falta (ex.: 'armadura.racio_kg_m3')."
        ),
    )
    unit: str | None = Field(
        default=None,
        description="Unidade esperada da resposta ('kg/m³', 'mm', ...).",
    )
    element_id: str | None = Field(
        default=None,
        description="`id` do `ElementoBase` ao qual a pergunta se refere.",
    )
    suggested_default: float | None = Field(
        default=None,
        description="Valor numérico de referência (ex.: 100 kg/m³ para laje).",
    )
    criticidade: Criticidade = Field(
        description="Peso: 'bloqueante' impede o cálculo; 'opcional' é só QA.",
    )


class CrossCheckWarning(_StrictModel):
    """Divergência entre duas fontes (APS metadata vs Vision LLM, ...).

    `severidade='erro'` em qualquer warning força `requires_human_review=True`.
    """

    fonte_a: str = Field(
        description="Rótulo da primeira fonte (ex.: 'aps_metadata').",
    )
    fonte_b: str = Field(
        description="Rótulo da segunda fonte (ex.: 'vision_llm').",
    )
    campo: str = Field(
        description="Campo em divergência (ex.: 'contagem.janelas').",
    )
    valor_a: float | int | str | None = Field(
        default=None,
        description="Valor observado em `fonte_a`.",
    )
    valor_b: float | int | str | None = Field(
        default=None,
        description="Valor observado em `fonte_b`.",
    )
    severidade: Severidade = Field(
        description="'info' | 'aviso' | 'erro' (erro → revisão humana).",
    )


# ---------------------------------------------------------------------------
# Análise global
# ---------------------------------------------------------------------------
class AnalisePlanta(_StrictModel):
    """Análise completa de uma planta.

    Contrato de saída oficial do motor Plans Pro (substitui o `dict` legado
    `{vision, synthesis, norms, ...}` que não era tipado).
    """

    plan_id: str = Field(
        description="Identificador do plano (p.ex. 'pln_abc123').",
    )
    elementos: list[ElementoBase] = Field(
        default_factory=list,
        description="Elementos estruturais detectados (lista plana).",
    )
    missing_data: list[MissingDataRequest] = Field(
        default_factory=list,
        description="Perguntas tipadas a devolver ao utilizador se existirem.",
    )
    warnings: list[CrossCheckWarning] = Field(
        default_factory=list,
        description="Divergências entre fontes (APS, LLM, OCR, ...).",
    )
    confidence_global: float = Field(
        ge=0.0,
        le=1.0,
        description="Confiança agregada 0..1 após cross-check.",
    )
    requires_human_review: bool = Field(
        description=(
            "True se existe ≥1 warning 'erro' ou ≥1 missing_data 'bloqueante'."
        ),
    )
    trace: dict[str, float | int | str | bool | None] = Field(
        default_factory=dict,
        description=(
            "Observabilidade: tempos por etapa, provider, tokens, flags. "
            "Útil para debug — resolve a opacidade histórica dos "
            "`except Exception` com `type(e).__name__`."
        ),
    )

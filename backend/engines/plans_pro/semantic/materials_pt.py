"""Léxico PT-BTP determinístico.

Zero LLM, zero alucinação: só regex e tabelas fechadas. Serve de rede
de segurança quando o LLM devolve texto livre ou abreviaturas
portuguesas que não são reconhecidas sem contexto cultural.

Cobertura (Fase 1):
    * Classes de betão: C12/15 … C50/60.
    * Aços: A400, A500, A500NR, A500ER.
    * Varões (diâmetro em mm): ∅6, Ø8, fi10, phi12 ...
    * Alvenaria PT: PP (parpaing), BA (betão armado), BB (betão de limpeza),
      TJ 7|11|15|22|30, BLOCO TÉRMICO, BLOCO 20.
    * Isolamento: XPS, EPS, MW (lã mineral) + espessuras (`e=4 cm`).

Se nenhum padrão bater, as funções devolvem `None`/`[]` — NUNCA inventam.
"""
from __future__ import annotations

import re

from engines.plans_pro.semantic.schemas import Dimensao, Material

# ---------------------------------------------------------------------------
# Tabelas fechadas
# ---------------------------------------------------------------------------
_CLASSES_BETAO = {
    "C12/15", "C16/20", "C20/25", "C25/30", "C30/37",
    "C35/45", "C40/50", "C45/55", "C50/60",
}
"""Classes de resistência de betão NP EN 206-1."""

_CLASSES_ACO = {"A400", "A500", "A500NR", "A500ER", "B500A", "B500B"}
"""Classes de aço para betão armado (NP EN 10080 e normas PT)."""

_DIAMETROS_VAROES_MM = {6, 8, 10, 12, 14, 16, 20, 25, 32, 40}
"""Diâmetros nominais em mm admitidos para varões."""


# ---------------------------------------------------------------------------
# Padrões regex (compilados uma vez)
# ---------------------------------------------------------------------------
# `C25/30`, `C 25/30`, `c25/30`
_RE_BETAO = re.compile(r"\bC\s*(\d{2})\s*/\s*(\d{2})\b", re.IGNORECASE)

# `A400`, `A 500 NR`, `B500A`
_RE_ACO = re.compile(r"\b([AB])\s*(\d{3})\s*([A-Z]{0,2})\b")

# `∅12`, `Ø 10`, `fi12`, `phi 16`, `varão 12`, `D16`
_RE_VARAO = re.compile(
    r"(?:∅|Ø|\bfi\b|\bphi\b|\bvar[ãa]o\b|\bD)\s*(\d{1,2})\s*(?:mm)?",
    re.IGNORECASE,
)

# Alvenaria PT: PP, BA, BB, TJ 15, BLOCO 20, BLOCO TERMICO, TIJOLO
_RE_ALVENARIA = re.compile(
    r"\b("
    r"PP|BA|BB|"
    r"TJ\s*\d{1,2}|"
    r"BLOCO\s*(?:T[EÉ]RMICO|\d{1,2})|"
    r"TIJOLO"
    r")\b",
    re.IGNORECASE,
)

# Isolamento: XPS, EPS, MW, LÃ MINERAL + espessura opcional "e=4 cm"
_RE_ISOLAMENTO = re.compile(
    r"\b(XPS|EPS|MW|L[AÃ]\s*MINERAL)\b",
    re.IGNORECASE,
)

# Dimensão simples: `2,50 m`, `2.50m`, `250 cm`, `20mm`, `0,30` sem unidade (assume m)
_RE_DIMENSAO = re.compile(
    r"(-?\d+(?:[,.]\d+)?)\s*(mm|cm|m)\b",
    re.IGNORECASE,
)

# Formato produto: `0,30x0,60`, `30 x 60`, `0.30 X 0.60 m`
_RE_PRODUTO = re.compile(
    r"(-?\d+(?:[,.]\d+)?)\s*[xX]\s*(-?\d+(?:[,.]\d+)?)\s*(mm|cm|m)?",
)

# `e=4 cm`, `e = 20`, `esp=20 cm`
_RE_ESPESSURA = re.compile(
    r"\b(?:e|esp(?:essura)?)\s*=\s*(-?\d+(?:[,.]\d+)?)\s*(mm|cm|m)?\b",
    re.IGNORECASE,
)

# `h=2,80`, `altura=2,8 m`
_RE_ALTURA = re.compile(
    r"\b(?:h|altura)\s*=\s*(-?\d+(?:[,.]\d+)?)\s*(mm|cm|m)?\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_float(raw: str) -> float:
    """Converte string PT ('0,30') ou EN ('0.30') em float. Nunca `None`."""
    return float(raw.replace(",", "."))


def _normalizar_unidade(unidade: str | None, valor: float) -> tuple[float, str]:
    """Normaliza a unidade. Default = metros se omitida e valor < 10
    (heurística: `0,30` sem unidade é claramente metros em BTP PT).
    """
    if unidade:
        return valor, unidade.lower()
    # Sem unidade: heurística determinística
    if valor >= 10 and valor < 1000:
        # Provavelmente cm (ex.: "30" para 30 cm)
        return valor, "cm"
    if valor >= 1000:
        # Provavelmente mm
        return valor, "mm"
    return valor, "m"


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------
def reconhecer_material(texto: str) -> Material | None:
    """Devolve o PRIMEIRO material reconhecido em `texto`, ou `None`.

    Ordem de prioridade (do mais específico para o mais genérico):
        1. Classe de betão (`C25/30`).
        2. Classe de aço (`A500NR`, `B500B`).
        3. Diâmetro de varão (`∅12`).
        4. Alvenaria PT (`PP`, `TJ 15`, `BLOCO 20`, `TIJOLO`).
        5. Isolamento (`XPS`, `EPS`, `MW`).

    NUNCA inventa: se nada bater exactamente, devolve `None`.
    """
    if not texto:
        return None
    s = texto.strip()

    # 1. Betão
    m = _RE_BETAO.search(s)
    if m:
        classe = f"C{int(m.group(1))}/{int(m.group(2))}"
        if classe in _CLASSES_BETAO:
            return Material(
                nome=classe,
                categoria="betao",
                classe=classe,
                confidence=0.98,
            )

    # 2. Aço (deve preceder varão para apanhar 'A500NR' antes de 'D500')
    m = _RE_ACO.search(s)
    if m:
        classe = (m.group(1) + m.group(2) + (m.group(3) or "")).upper()
        if classe in _CLASSES_ACO:
            return Material(
                nome=classe,
                categoria="aco",
                classe=classe,
                confidence=0.95,
            )

    # 3. Varão (devolve aço com classe None)
    m = _RE_VARAO.search(s)
    if m:
        try:
            diametro = int(m.group(1))
        except ValueError:
            diametro = -1
        if diametro in _DIAMETROS_VAROES_MM:
            return Material(
                nome=f"∅{diametro}",
                categoria="aco",
                classe=None,
                confidence=0.9,
            )

    # 4. Alvenaria
    m = _RE_ALVENARIA.search(s)
    if m:
        token = m.group(1).upper().replace("  ", " ").strip()
        return Material(
            nome=token,
            categoria="alvenaria",
            classe=token,
            confidence=0.85,
        )

    # 5. Isolamento
    m = _RE_ISOLAMENTO.search(s)
    if m:
        token = m.group(1).upper()
        return Material(
            nome=token,
            categoria="isolamento",
            classe=token,
            confidence=0.85,
        )

    return None


def extrair_dimensao(texto: str) -> list[Dimensao]:
    """Extrai dimensões tipadas do texto. Devolve `[]` se nada bater.

    Casos cobertos:
        * `"e=20 cm"`                       → espessura 20 cm
        * `"e=4"`                           → espessura 4 cm (heurística)
        * `"h=2,80 m"`                      → altura 2.8 m
        * `"0,30x0,60"`                     → 2× `Dimensao` (comprimento, largura)
        * `"0.30 X 0.60 m"`                 → 2× `Dimensao` em metros
        * `"30 x 60 cm"`                    → cm
        * `"2500 mm"`                       → 2500 mm
        * `"2,5 m"`                         → 2.5 m
    """
    if not texto:
        return []

    out: list[Dimensao] = []
    consumidos: list[tuple[int, int]] = []

    def _marcar(a: int, b: int) -> None:
        consumidos.append((a, b))

    def _ja_consumido(start: int, end: int) -> bool:
        return any(cs <= start < ce or cs < end <= ce for cs, ce in consumidos)

    # 1. Espessura (prioritário — e= / esp=)
    for m in _RE_ESPESSURA.finditer(texto):
        if _ja_consumido(*m.span()):
            continue
        v, u = _normalizar_unidade(m.group(2), _to_float(m.group(1)))
        if m.group(2) is None:
            # Heurística: espessura em cm
            u = "cm"
        out.append(Dimensao(valor=v, unidade=u, eixo="espessura"))  # type: ignore[arg-type]
        _marcar(*m.span())

    # 2. Altura (h= / altura=)
    for m in _RE_ALTURA.finditer(texto):
        if _ja_consumido(*m.span()):
            continue
        v, u = _normalizar_unidade(m.group(2), _to_float(m.group(1)))
        if m.group(2) is None:
            u = "m"
        out.append(Dimensao(valor=v, unidade=u, eixo="altura"))  # type: ignore[arg-type]
        _marcar(*m.span())

    # 3. Produto (0,30x0,60 ...)
    for m in _RE_PRODUTO.finditer(texto):
        if _ja_consumido(*m.span()):
            continue
        v1, u = _normalizar_unidade(m.group(3), _to_float(m.group(1)))
        v2, _ = _normalizar_unidade(m.group(3), _to_float(m.group(2)))
        out.append(Dimensao(valor=v1, unidade=u, eixo="comprimento"))  # type: ignore[arg-type]
        out.append(Dimensao(valor=v2, unidade=u, eixo="largura"))  # type: ignore[arg-type]
        _marcar(*m.span())

    # 4. Dimensão simples remanescente
    for m in _RE_DIMENSAO.finditer(texto):
        if _ja_consumido(*m.span()):
            continue
        v, u = _normalizar_unidade(m.group(2), _to_float(m.group(1)))
        out.append(Dimensao(valor=v, unidade=u, eixo="comprimento"))  # type: ignore[arg-type]
        _marcar(*m.span())

    return out


__all__ = [
    "reconhecer_material",
    "extrair_dimensao",
    "_CLASSES_BETAO",
    "_CLASSES_ACO",
    "_DIAMETROS_VAROES_MM",
]

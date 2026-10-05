"""Router de pesquisa web para o Assistente BTP (Coach IA + Solver BTP).

Decide se deve usar Perplexity antes de Claude/OpenAI, com base em:
  1. `user_override` (toggle UI: True=sempre, False=nunca, None=auto)
  2. palavras-chave de atualidade (preços, normas recentes, etc.)
  3. referências a fornecedores/marcas/produtos específicos
  4. localização portuguesa específica (distritos, concelhos, grandes cidades)
  5. perguntas longas / complexas (>20 palavras)

Retorna `(enabled, mode, reason)` em que:
  - enabled: bool  → se deve injetar Perplexity
  - mode: "auto|forced|disabled|skipped" → como foi decidido
  - reason: str    → razão legível (log)
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Léxicos (minúsculas, aplicados após .lower())
# ---------------------------------------------------------------------------
_ACTUALITY = {
    # tempo
    "atual", "atualmente", "atualidade", "hoje", "agora", "neste momento",
    "última", "últimas", "último", "últimos", "recente", "recentes",
    # preços / mercado
    "preço", "preços", "custo", "custos", "cotação", "cotações",
    "inflação", "mercado",
    # fiscal / jurídico
    "iva", "deduzir", "deduzível", "declaração", "fiscal",
    "incentivo", "incentivos", "apoio", "apoios", "subsídio", "subsídios",
    "programa", "programas", "iefp",
    # regulamentação / normas
    "nova lei", "lei nova", "novo decreto", "decreto-lei", "dl ",
    "portaria", "nova portaria", "normativa", "regulamento",
    "rgeu", "reh", "rccte", "rjue", "rsrae", "rscie",
    # novidades
    "nova", "novo", "novas", "novos", "notícia", "notícias",
}

_SUPPLIER_HINT = {
    "fornecedor", "fornecedores", "marca", "marcas", "fabricante",
    "fabricantes", "distribuidor", "distribuidores",
    "onde comprar", "qual recomenda", "qual recomenda-me",
    "melhor marca", "melhor fornecedor", "melhor fabricante",
    "comprar em", "stock", "em stock",
    "leroy merlin", "bricodepot", "aki", "bricomarché", "sotecnisol",
    "weber", "sika", "mapei", "secil", "cimpor",
}

_LOCATION_HINT = {
    # distritos
    "lisboa", "porto", "braga", "coimbra", "aveiro", "faro", "setúbal",
    "setubal", "viseu", "leiria", "santarém", "santarem", "évora", "evora",
    "beja", "guarda", "castelo branco", "portalegre", "bragança", "braganca",
    "vila real", "viana do castelo",
    # regiões
    "madeira", "açores", "acores", "algarve", "alentejo", "ribatejo",
    "trás-os-montes", "tras os montes", "minho", "douro",
    # admin
    "concelho", "freguesia", "distrito", "zona", "grande lisboa",
    "grande porto", "aml", "amp",
}

# Expressão de ano recente (ex: "em 2026", "desde 2025", "já em 2026")
_YEAR_RE = re.compile(r"\b(?:em|desde|para|até|a partir de)\s+20(2[4-9]|3\d)\b", re.IGNORECASE)

# Hint de pergunta aberta sobre melhor opção
_COMPARATIVE = {
    "qual o melhor", "qual é o melhor", "qual é melhor", "qual vale a pena",
    "diferença entre", "diferenças entre", "comparar", "comparação", "versus", " vs ",
}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def should_use_web_search(
    query: str,
    project_context: dict | None = None,
    user_override: bool | None = None,
) -> tuple[bool, str, str]:
    """Decide se chama Perplexity antes de Claude/OpenAI.

    Params
    ------
    query : str
        Mensagem/descrição do utilizador.
    project_context : dict | None
        Dados contextuais do projeto (region, tipo_edificio, etc.).
    user_override : bool | None
        Toggle UI. ``True`` força, ``False`` desativa, ``None`` auto.

    Returns
    -------
    (enabled, mode, reason) :
      - ``mode`` ∈ {"forced", "disabled", "auto", "skipped"}
      - ``reason`` é texto curto para log/observabilidade
    """
    # 1) Override explícito do utilizador tem precedência total
    if user_override is True:
        return True, "forced", "user_override_true"
    if user_override is False:
        return False, "disabled", "user_override_false"

    q = (query or "").strip().lower()
    if not q:
        return False, "skipped", "empty_query"

    # 2) Palavras-chave de atualidade / fiscal / normas
    hit = _match_any(q, _ACTUALITY)
    if hit:
        return True, "auto", f"actuality_keyword:{hit}"

    # 3) Fornecedores / marcas / produtos
    hit = _match_any(q, _SUPPLIER_HINT)
    if hit:
        return True, "auto", f"supplier_keyword:{hit}"

    # 4) Localização específica PT (no texto OU no contexto do projeto)
    hit = _match_any(q, _LOCATION_HINT)
    if hit:
        return True, "auto", f"location_keyword:{hit}"
    if project_context:
        for field in ("region", "city", "distrito", "concelho"):
            val = (project_context.get(field) or "").strip().lower()
            if val and val in _LOCATION_HINT:
                return True, "auto", f"location_context:{field}={val}"
            # match parcial (ex: "Lisboa Centro" contém "lisboa")
            for loc in _LOCATION_HINT:
                if loc and loc in val:
                    return True, "auto", f"location_context_substr:{field}~{loc}"

    # 5) Ano recente (ex: "em 2026", "desde 2025")
    if _YEAR_RE.search(q):
        return True, "auto", "year_mention"

    # 6) Comparativos ("qual o melhor", "diferença entre", etc.)
    hit = _match_any(q, _COMPARATIVE)
    if hit:
        return True, "auto", f"comparative:{hit}"

    # 7) Pergunta longa / complexa (>20 palavras)
    word_count = len(q.split())
    if word_count > 20:
        return True, "auto", f"long_query({word_count}w)"

    return False, "skipped", "no_trigger"


def _match_any(text: str, lexicon: set[str]) -> str | None:
    """Devolve o primeiro termo do léxico que aparece em ``text`` (substring)."""
    for term in lexicon:
        if term and term in text:
            return term
    return None


__all__ = ["should_use_web_search"]

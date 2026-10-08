"""Catálogo das 11 ferramentas (Function Declarations) do Assistente BTP.

Todas as descrições e `parameters` são em PT-PT porque o Gemini usa-as
directamente para decidir qual função chamar. Qualquer FR/EN aqui
degrada a qualidade da escolha.
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# 1. Abrir módulo da plataforma
# ---------------------------------------------------------------------------
FUNC_ABRIR_APP: dict[str, Any] = {
    "name": "abrir_app",
    "description": (
        "Abre no frontend ConstruPilot o módulo pedido pelo utilizador "
        "(orçamento, plans-pro, calculadoras, biblioteca, estimador, "
        "preços, escadas). Usa esta função apenas quando o utilizador "
        "pede explicitamente para navegar/abrir uma secção."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "nome_app": {
                "type": "string",
                "enum": [
                    "orcamento", "plans-pro", "calculadoras",
                    "precos", "estimador", "biblioteca", "escadas",
                ],
                "description": "Nome interno do módulo ConstruPilot a abrir.",
            },
        },
        "required": ["nome_app"],
    },
}

# ---------------------------------------------------------------------------
# 2. Criar orçamento (NOVO)
# ---------------------------------------------------------------------------
FUNC_CRIAR_ORCAMENTO: dict[str, Any] = {
    "name": "criar_orcamento",
    "description": (
        "Cria um novo orçamento BTP com os items fornecidos. "
        "Devolve o `orcamento_id`. IVA PT 23% aplicado por defeito."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "cliente_nome": {
                "type": "string",
                "description": "Nome do cliente/dono da obra.",
            },
            "titulo": {
                "type": "string",
                "description": "Título descritivo do orçamento (ex.: 'Moradia T3 Sintra').",
            },
            "items": {
                "type": "array",
                "description": "Lista de linhas do orçamento.",
                "items": {
                    "type": "object",
                    "properties": {
                        "descricao": {"type": "string"},
                        "qtd": {"type": "number"},
                        "unidade": {
                            "type": "string",
                            "description": "Unidade PT (m², m³, ml, un, kg, h).",
                        },
                        "preco_unit_eur": {"type": "number"},
                    },
                    "required": ["descricao", "qtd", "unidade", "preco_unit_eur"],
                },
            },
            "iva_pct": {
                "type": "number",
                "description": "Taxa de IVA (default 23 em PT continental).",
            },
            "cliente_email": {
                "type": "string",
                "description": (
                    "E-mail do cliente final. Opcional. Se fornecido com "
                    "`convidar_cliente_portal=true`, o backend envia "
                    "automaticamente a ligação pública por e-mail."
                ),
            },
            "convidar_cliente_portal": {
                "type": "boolean",
                "description": (
                    "Se `true`, gera uma ligação pública (link mágico) para "
                    "o cliente consultar o orçamento sem conta ConstruPilot. "
                    "Default `false`."
                ),
            },
        },
        "required": ["cliente_nome", "titulo", "items"],
    },
}

# ---------------------------------------------------------------------------
# 3. Adicionar linha a orçamento existente
# ---------------------------------------------------------------------------
FUNC_ADICIONAR_ITEM_ORCAMENTO: dict[str, Any] = {
    "name": "adicionar_item_orcamento",
    "description": (
        "Acrescenta uma linha a um orçamento existente, identificado por "
        "`orcamento_id`. Útil quando o utilizador diz 'adiciona X ao "
        "último orçamento'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "orcamento_id": {"type": "string"},
            "descricao": {"type": "string"},
            "qtd": {"type": "number"},
            "unidade": {"type": "string"},
            "preco_unit_eur": {"type": "number"},
        },
        "required": [
            "orcamento_id", "descricao", "qtd", "unidade", "preco_unit_eur",
        ],
    },
}

# ---------------------------------------------------------------------------
# 4. Calcular metrado de uma planta
# ---------------------------------------------------------------------------
FUNC_CALCULAR_METRADO: dict[str, Any] = {
    "name": "calcular_metrado",
    "description": (
        "Executa a análise completa de uma planta Autodesk já carregada "
        "na plataforma (Plans Pro). Devolve `AnalisePlanta` tipado com "
        "elementos estruturais, dimensões e `missing_data`."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "plan_id": {
                "type": "string",
                "description": "ID do plano Plans Pro (pln_...).",
            },
            "project_hint": {
                "type": "string",
                "description": "Contexto opcional do projecto (ex.: 'Moradia T3').",
            },
        },
        "required": ["plan_id"],
    },
}

# ---------------------------------------------------------------------------
# 5. Estimar custo por m² (estimador rápido)
# ---------------------------------------------------------------------------
FUNC_ESTIMAR_CUSTO: dict[str, Any] = {
    "name": "estimar_custo",
    "description": (
        "Estimativa rápida de custo de obra em Portugal usando o motor "
        "`engines.estimation`. Devolve valor total, por lote e por m²."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "tipo_projecto": {
                "type": "string",
                "description": "ex.: 'maison_neuve', 'renovation', 'reabilitacao'.",
            },
            "surface_m2": {"type": "number"},
            "acabamento": {
                "type": "string",
                "enum": ["economico", "standard", "premium"],
            },
            "regiao_pt": {
                "type": "string",
                "description": "ex.: 'Lisboa', 'Porto', 'Algarve'.",
            },
        },
        "required": ["tipo_projecto", "surface_m2"],
    },
}

# ---------------------------------------------------------------------------
# 6. Pesquisar norma via Perplexity Plus
# ---------------------------------------------------------------------------
FUNC_PESQUISAR_NORMA: dict[str, Any] = {
    "name": "pesquisar_norma",
    "description": (
        "Pesquisa normas PT/UE actualizadas via Perplexity Plus. Devolve "
        "resumo em PT-PT com citações oficiais (Diário da República, "
        "Eurocódigos, LNEC, etc.)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "termo": {
                "type": "string",
                "description": "Pergunta ou termo (ex.: 'altura mínima pé-direito RGEU').",
            },
            "tipo": {
                "type": "string",
                "enum": ["RGEU", "REH", "REBAP", "Eurocodigo", "DL", "outros"],
                "description": "Família da norma, se conhecida.",
            },
        },
        "required": ["termo"],
    },
}

# ---------------------------------------------------------------------------
# 7. Obter preço de material
# ---------------------------------------------------------------------------
FUNC_OBTER_PRECO_MATERIAL: dict[str, Any] = {
    "name": "obter_preco_material",
    "description": (
        "Procura preço de um material primeiro na biblioteca interna; "
        "se não existir, faz pesquisa Google automática. Preços em "
        "EUR, mercado PT."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "material": {
                "type": "string",
                "description": "ex.: 'cimento CEM II 32,5', 'bloco PP 20', 'aço A500NR'.",
            },
            "unidade": {
                "type": "string",
                "description": "ex.: 'saco 25kg', 'un', 'kg', 'm³'.",
            },
            "regiao_pt": {
                "type": "string",
                "description": "ex.: 'Lisboa'. Deixar vazio para média nacional.",
            },
        },
        "required": ["material"],
    },
}

# ---------------------------------------------------------------------------
# 8. Exportar orçamento para Excel
# ---------------------------------------------------------------------------
FUNC_EXPORTAR_EXCEL: dict[str, Any] = {
    "name": "exportar_excel",
    "description": (
        "Gera ficheiro Excel do orçamento identificado por `orcamento_id`. "
        "Devolve URL temporário para download."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "orcamento_id": {"type": "string"},
            "iva_pct": {
                "type": "number",
                "description": "IVA a aplicar nos totais (default 23).",
            },
        },
        "required": ["orcamento_id"],
    },
}

# ---------------------------------------------------------------------------
# 9. Calcular escada (delega ao Stair Engine quando disponível)
# ---------------------------------------------------------------------------
FUNC_CALCULAR_ESCADA: dict[str, Any] = {
    "name": "calcular_escada",
    "description": (
        "Dimensionamento de escada segundo RGEU/REH. Devolve número de "
        "degraus, altura/largura óptimas e verificações normativas. Se "
        "o Stair Engine estiver em desenvolvimento, devolve pergunta "
        "educada ao utilizador."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "altura_total_m": {"type": "number"},
            "espaco_horizontal_m": {"type": "number"},
            "largura_m": {"type": "number"},
            "tipo_escada": {
                "type": "string",
                "enum": ["recta", "em_L", "em_U", "circular"],
            },
        },
        "required": ["altura_total_m", "espaco_horizontal_m"],
    },
}

# ---------------------------------------------------------------------------
# 10. Pesquisar na biblioteca interna
# ---------------------------------------------------------------------------
FUNC_PESQUISAR_BIBLIOTECA: dict[str, Any] = {
    "name": "pesquisar_biblioteca",
    "description": (
        "Busca semântica na biblioteca de obras ConstruPilot: fichas "
        "técnicas, soluções construtivas tipo, DTU/DIN usados em PT."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Termo ou pergunta em PT-PT.",
            },
            "categoria": {
                "type": "string",
                "enum": [
                    "fundacoes", "estrutura", "coberturas", "isolamento",
                    "revestimentos", "redes", "outros",
                ],
            },
        },
        "required": ["query"],
    },
}

# ---------------------------------------------------------------------------
# 11. Pedir precisão ao utilizador (dado em falta)
# ---------------------------------------------------------------------------
FUNC_PEDIR_PRECISAO: dict[str, Any] = {
    "name": "pedir_precisao",
    "description": (
        "Levanta UMA pergunta clara ao utilizador quando um dado crítico "
        "está em falta e não deve ser inventado. Preferir SEMPRE esta "
        "função a assumir valores por defeito."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "campo": {
                "type": "string",
                "description": "Nome lógico do campo (ex.: 'surface_m2').",
            },
            "pergunta_pt": {
                "type": "string",
                "description": "Pergunta em PT-PT clara, curta e directa.",
            },
            "unidade": {
                "type": "string",
                "description": "ex.: 'm²', 'kg/m³', 'EUR'.",
            },
            "criticidade": {
                "type": "string",
                "enum": ["bloqueante", "importante", "opcional"],
            },
            "suggested_default": {
                "type": "number",
                "description": "Valor de referência (opcional).",
            },
        },
        "required": ["campo", "pergunta_pt", "criticidade"],
    },
}


# ---------------------------------------------------------------------------
# Registry agregado
# ---------------------------------------------------------------------------
TOOLS: list[dict[str, Any]] = [
    FUNC_ABRIR_APP,
    FUNC_CRIAR_ORCAMENTO,
    FUNC_ADICIONAR_ITEM_ORCAMENTO,
    FUNC_CALCULAR_METRADO,
    FUNC_ESTIMAR_CUSTO,
    FUNC_PESQUISAR_NORMA,
    FUNC_OBTER_PRECO_MATERIAL,
    FUNC_EXPORTAR_EXCEL,
    FUNC_CALCULAR_ESCADA,
    FUNC_PESQUISAR_BIBLIOTECA,
    FUNC_PEDIR_PRECISAO,
]

TOOLS_INDEX: dict[str, dict[str, Any]] = {t["name"]: t for t in TOOLS}

# Acções que requerem confirmação na UI antes de executar
NOMES_FERRAMENTAS_COM_CONFIRMACAO = {
    "criar_orcamento",
    "adicionar_item_orcamento",
    "exportar_excel",
}


__all__ = ["TOOLS", "TOOLS_INDEX", "NOMES_FERRAMENTAS_COM_CONFIRMACAO"]

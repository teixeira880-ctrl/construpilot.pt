"""Bounded quote tool contracts: the model proposes, the server persists drafts only."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuoteLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    designation: str = Field(min_length=1, max_length=500)
    line_id: str | None = Field(max_length=100)
    description: str = Field(max_length=2000)
    quantity: float | None = Field(ge=0, le=1_000_000, strict=True)
    unit: str = Field(min_length=1, max_length=12)
    unit_price: float | None = Field(ge=0, le=100_000_000, strict=True)
    price_origin: Literal["user", "library", "estimate", "unpriced"]
    vat_rate: float | None = Field(ge=0, le=100, strict=True)
    lot: str = Field(max_length=80)

    @model_validator(mode="after")
    def user_price_required(self):
        if self.price_origin in ("user", "estimate") and self.unit_price is None:
            raise ValueError("price_origin=\'user\' ou \'estimate\' exige um unit_price (montante sem IVA), 0 se oferecido.")
        if self.price_origin in ("library", "unpriced") and self.unit_price is not None:
            raise ValueError("price_origin=\'library\'/\'unpriced\' exige unit_price=null (o servidor orçamenta a partir da biblioteca ou deixa por completar).")
        return self


class QuoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=160)
    client_name: str = Field(max_length=200)
    vat_rate: float | None = Field(ge=0, le=100, strict=True)
    lines: list[QuoteLineInput] = Field(min_length=1, max_length=150)
    notes: str = ""  # Jamais renseigné par l'assistant : laissé vide, à remplir manuellement par l'entreprise.


class QuoteAppendInput(BaseModel):
    """Ajout de lignes à un devis brouillon existant, sans renvoyer les lignes déjà présentes."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    vat_rate: float | None = Field(ge=0, le=100, strict=True)
    lines: list[QuoteLineInput] = Field(min_length=1, max_length=60)


LINE_PROPERTIES = {
    "line_id": {"type": ["string", "null"], "maxLength": 100, "description": "null para nova linha; conservar o identificador fornecido por read_quote_draft numa revisão."},
    "description": {"type": "string", "maxLength": 2000, "description": "Detalhes, materiais, acabamento e indicações fornecidos; conservar numa revisão."},
    "designation": {"type": "string", "minLength": 1, "maxLength": 500},
    "quantity": {"type": ["number", "null"], "minimum": 0, "maximum": 1000000, "description": "Quantidade fornecida/calculável; null se desconhecida, nunca inventada."},
    "unit": {"type": "string", "minLength": 1, "maxLength": 12},
    "unit_price": {"type": ["number", "null"], "minimum": 0, "maximum": 100000000, "description": "Preço sem IVA. price_origin=\'user\': preço explicitamente fornecido pelo cliente. price_origin=\'estimate\': preço médio de mercado/web que TU forneces (será marcado «estimado, a verificar»). Caso contrário null."},
    "price_origin": {"type": "string", "enum": ["user", "library", "estimate", "unpriced"], "description": "user = preço sem IVA fornecido pelo cliente; library = procurar na biblioteca (unit_price=null); estimate = preço médio de mercado/web que forneces em unit_price (apenas se o utilizador pediu uma orçamentação automática / preço médio); unpriced = deixar sem preço (unit_price=null)."},
    "vat_rate": {"type": ["number", "null"], "minimum": 0, "maximum": 100, "description": "IVA desta linha se explicitamente fornecido; null utiliza a taxa geral."},
    "lot": {"type": "string", "maxLength": 80},
}
QUOTE_PROPERTIES = {
    "title": {"type": "string", "minLength": 1, "maxLength": 160},
    "client_name": {"type": "string", "maxLength": 200, "description": "Identidade fornecida; vazio se desconhecida. Não cria ficha CRM."},
    "vat_rate": {"type": ["number", "null"], "minimum": 0, "maximum": 100, "description": "Taxa geral explicitamente fornecida, caso contrário null: taxa normal provisória a validar."},
    "lines": {"type": "array", "minItems": 1, "maxItems": 150, "items": {"type": "object", "properties": LINE_PROPERTIES, "required": list(LINE_PROPERTIES), "additionalProperties": False}},
}


def tool(name, description, properties):
    return {"type": "function", "name": name, "description": description, "strict": True,
            "parameters": {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}}


QUOTE_TOOLS = [
    tool("create_quote_draft", "Guarda imediatamente um orçamento RASCUNHO editável em Acompanhamento de orçamentos (/devis). Nem e-mail, nem assinatura, nem fatura. Preços ausentes: biblioteca local se autorizada, claramente estimados; caso contrário a completar. Devolve doc_id e ligação.", QUOTE_PROPERTIES),
    tool("find_quote_drafts", "Encontra os orçamentos RASCUNHO existentes da conta (criados pelo assistente OU manualmente no editor /devis) para RETOMAR um deles. Filtra pelo nome do cliente ou palavras do título; query vazia = os mais recentes. Devolve doc_id, título, cliente, data e totais; encadear depois read_quote_draft e update_quote_draft.", {"query": {"type": "string", "maxLength": 200, "description": "Nome do cliente ou palavras do título a pesquisar; cadeia vazia para listar os mais recentes."}}),
    tool("add_quote_lines", "ADICIONA linhas a um orçamento RASCUNHO existente SEM reenviar as linhas já presentes. A utilizar para construir um orçamento GRANDE por etapas (por piso/capítulo): cria primeiro o orçamento com create_quote_draft e depois adiciona cada piso/capítulo com esta ferramenta. As linhas existentes são conservadas. Utiliza o doc_id devolvido por create_quote_draft.", {
        "doc_id": {"type": "string"}, "vat_rate": QUOTE_PROPERTIES["vat_rate"], "lines": QUOTE_PROPERTIES["lines"]}),
    tool("read_quote_draft", "Relê a versão atual de um orçamento da conta antes da correção, incluindo as alterações manuais. Utilizar o doc_id devolvido anteriormente.", {"doc_id": {"type": "string"}}),
    tool("update_quote_draft", "Revê o MESMO orçamento ainda em rascunho após read_quote_draft; conservar as indicações e linhas não alteradas. Nunca um documento enviado/assinado. Em caso de conflito, reler antes de nova tentativa.", {
        "doc_id": {"type": "string"}, "expected_updated_at": {"type": "string"}, **QUOTE_PROPERTIES}),
]

QUOTE_INSTRUCTIONS = "\nORÇAMENTO PROFISSIONAL: quando o utilizador pede para criar/preparar um orçamento, chama create_quote_draft.\nNão redijas apenas uma tabela no chat nem um create_work_draft: o resultado deve existir em Acompanhamento de orçamentos.\nPreserva exatamente as quantidades, unidades, materiais, capítulos, preços sem IVA e IVA indicados. Preço ausente = null com\nprice_origin=library; nunca transformes uma estimativa do modelo num preço do utilizador. Uma prestação oferecida\nexplicitamente tem um preço do utilizador 0, não um preço em falta. ORÇAMENTAÇÃO AUTOMÁTICA: se o utilizador te pedir\nexplicitamente para orçamentar automaticamente / usar um preço médio quando a biblioteca não tiver o preço, então\npara essas linhas põe price_origin=\'estimate\' e unit_price = o preço médio de mercado/web sem IVA que encontraste (será\nclaramente marcado «estimado, a verificar»). Numa orçamentação automática: 1) tenta price_origin=\'library\' (biblioteca da empresa\ne catálogo partilhado autorizado segundo as suas preferências); 2) se nenhum preço compatível estiver disponível,\nprocura uma referência pertinente na web (search_technical_docs / search_technical_web).\nUtiliza price_origin=\'estimate\' apenas com uma referência identificável e comparável\n(unidade, país, data, materiais e aplicação). Sem base fiável, deixa o preço por completar e explica a falta.\nNunca fabriques um preço para preencher todas as linhas. NUNCA utilizes \'estimate\' sem pedido explícito do utilizador:\npor omissão, um preço ausente fica price_origin=\'library\' (unit_price=null). quantity, unit_price e vat_rate devem\nser NÚMEROS (nunca cadeias). Se houver apenas o montante com IVA, calcula o valor sem IVA apenas com\nIVA conhecido; caso contrário pede esclarecimento. As quantidades desconhecidas ficam null e são assinaladas a completar.\nNão presumas uma taxa reduzida de IVA. O servidor propõe uma taxa normal provisória se faltar.\nEm caso de resultado ok=true, anuncia o rascunho guardado com a sua ligação edit_url e tracking_url.\nNunca afirmes ter enviado o orçamento ao cliente. Pedido explícito de revisão do orçamento anterior:\nread_quote_draft e depois update_quote_draft, não um orçamento novo. Utiliza o tool_input devolvido, altera apenas os\ncampos pedidos e conserva as fontes dos outros preços. Os documentos enviados/assinados ficam intactos.\nConserva os line_id e descrições do tool_input nas revisões; novas linhas = line_id null.\nAs ações históricas são registos, não uma versão atual. Não cries um orçamento para uma simples pergunta\nsobre um orçamento existente, nem para contornar um erro de permissão/conflito. As permissões prevalecem sempre.\nRETOMA DE UM ORÇAMENTO EXISTENTE não criado nesta conversa (ex.: «retoma/altera o orçamento do Sr. X», ou um\norçamento feito no editor /devis): chama PRIMEIRO find_quote_drafts (filtra pelo nome do cliente ou título) para obter\no seu doc_id, depois read_quote_draft e update_quote_draft. NUNCA cries um orçamento novo neste caso. Se\nfind_quote_drafts não devolver nada, pede o nome exato do cliente ou o número do orçamento.\nNUNCA PREENCHAS notas / observações / comentário no orçamento: esse campo fica SEMPRE vazio, à\ndisposição da empresa para introdução manual no editor. Não ponhas lá nenhum texto, nem mesmo um resumo.\nORÇAMENTO GRANDE / ORÇAMENTO POR PISO OU POR CAPÍTULO (muitas linhas): NUNCA ponhas todas as linhas num único\ncreate_quote_draft — uma chamada demasiado volumosa é truncada e o orçamento nunca é guardado. Procede por etapas:\n1) create_quote_draft com o TÍTULO, o cliente e APENAS as linhas do PRIMEIRO piso/capítulo (anuncia o doc_id obtido);\n2) depois, para CADA piso/capítulo seguinte, chama add_quote_lines com esse doc_id e APENAS as novas linhas\n(nunca repitas as linhas já guardadas). Aponta para no máximo ~25 linhas por chamada e mantém descrições concisas.\nNÃO PARES depois do primeiro piso: encadeia IMEDIATAMENTE os add_quote_lines para TODOS os pisos restantes\nnesta MESMA ronda, sem pedir confirmação nem esperar «continua». O orçamento só está concluído quando TODOS\nos pisos/capítulos anunciados lá constarem. Depois de adicionados todos os pisos, anuncia o rascunho completo com a sua ligação edit_url.\nRedige as designações das linhas em português europeu.\n"
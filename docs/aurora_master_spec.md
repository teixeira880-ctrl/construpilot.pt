# Aurora Company API · Especificação Técnica Master

**Documento**: `aurora_master_spec.md`
**Versão**: 1.0.0
**Data de emissão**: 2026-02
**Emitido por**: Engenharia ConstruPilot
**Destinatário**: Equipa de Engenharia Aurora
**Estado**: Definitivo · pendente ratificação Aurora
**Classificação**: Confidencial — uso interno das partes contraentes

---

## Sumário executivo

Este documento define, de forma vinculativa técnica, os **requisitos de integração** entre o SaaS **ConstruPilot** (plataforma portuguesa de gestão de obras BTP) e a plataforma **Aurora Company API V1** (inteligência artificial interna, doravante "Aurora").

O objetivo é elevar a Aurora ao estatuto de **plano de controlo (control plane) transversal** de todas as plataformas SaaS operadas ou integradas pela organização, sendo o ConstruPilot a primeira integração de referência. A cobertura pretendida é de **99 % das operações SaaS** de negócio (o restante 1 % é excluído por segurança/design — ver §5.5).

O documento cobre nove domínios (§1 a §9), sendo os mais críticos:

| Domínio | Objetivo |
| --- | --- |
| §2 Contrato de respostas | Corrigir o problema atual do `text: ""` e fixar schemas estáveis |
| §3 Análise de plantas | Definir output estruturado exigido pelo pipeline DWG/DXF/PDF |
| §4 Normativa BTP | Aurora tem de dominar RGEU + Eurocodes + variantes nacionais UE |
| §5 Control plane | Comandos bidirecionais assinados Aurora → SaaS |
| §6 SLO / SLI | Latência p95, disponibilidade, rate limits |

**A não-conformidade com o descrito neste documento bloqueia a promoção a produção do integração Coach IA / Análise de Plantas / Plano de Controlo Aurora.**

---

## Índice

1. Preâmbulo
2. Contrato de respostas Aurora
3. Especificação técnica análise de plantas
4. Assistente BTP · normativa europeia completa
5. Aurora como plano de controlo · 100 % ConstruPilot / 99 % SaaS
6. Requisitos não-funcionais
7. Segurança
8. Roadmap de integração
9. Anexos

---

# §1 Preâmbulo

## 1.1 Missão

A **Aurora** é a inteligência artificial interna da organização. A sua missão é servir como **cérebro central** de todos os SaaS operados ou integrados, oferecendo:

1. **Compreensão de linguagem natural** com contexto de negócio (Coach IA).
2. **Extração estruturada** a partir de documentos técnicos (plantas DWG/DXF/PDF, orçamentos, faturas, contratos).
3. **Emissão de comandos** para os planos de dados (data planes) das plataformas SaaS.
4. **Auditoria e conformidade** de todas as interações IA-negócio.

A Aurora **não é uma dependência opcional** — o modelo de produto do ConstruPilot assenta na integração exclusiva com a Aurora para todo o fluxo IA. Não existe fallback para modelos externos (OpenAI/Anthropic/Google) no Coach IA nem no motor de análise de plantas.

## 1.2 Contexto ConstruPilot

O **ConstruPilot** é um SaaS PT-PT dedicado à gestão de obras BTP (*Bâtiment et Travaux Publics*) — incluindo particulares em regime de reabilitação, empresas de construção, gabinetes de projeto e prestadores de serviços técnicos. As funcionalidades principais são:

- **Estimador de custos** com Biblioteca PT 2026 (catálogo canónico de trabalhos, materiais, mão-de-obra).
- **Análise de plantas** (DWG/DXF/PDF) com extração de áreas, cotas e elementos construtivos.
- **Gestão de orçamentos** conformes à legislação portuguesa de contratação pública (CCP) e privada.
- **Coach IA** para dúvidas de utilizador (particulares e profissionais) sobre normativa, materiais, fiscalidade e boas práticas.
- **Portal de projeto** com equipa, cronograma, stock, fornecedores, faturação e assinatura eletrónica.

## 1.3 Endpoints base Aurora (V1)

Todos os endpoints Aurora estão publicados em:

```
https://<aurora-permanent-host>/api/gateway/v1/aurora-core/company/*
```

Sub-recursos atualmente em uso pelo ConstruPilot:

| Endpoint | Método | Uso ConstruPilot |
| --- | --- | --- |
| `/capabilities` | GET | Health-check / descoberta de features |
| `/projects/upsert` | POST (AS1) | Sincronização projetos ConstruPilot → Aurora |
| `/projects/get?project_id=…` | GET | Leitura projeto do lado Aurora |
| `/projects/context?project_id=…` | GET | Contexto agregado (memórias, sumários) |
| `/projects/event` | POST (AS1) | Emissão de eventos negócio (ex.: `estimate_signed`) |
| `/ask` | POST (AS1) | Coach IA + análise plantas (interface conversacional) |
| `/resources/upsert` | POST (AS1) | Anexação de recursos ao projeto (documents, estimates) |
| `/events?since=…` | GET | Feed durable outbox (webhooks Aurora → ConstruPilot) |

**Nota crítica sobre o host**: até à data (2026-02), a Aurora está exposta em `https://<slug>.trycloudflare.com`, que é um *quick tunnel* Cloudflare **não permanente**. Isto é bloqueante para produção — ver §6.3.

## 1.4 Vocabulário

| Termo | Definição |
| --- | --- |
| **AS1** | *Aurora Signature v1* — algoritmo HMAC-SHA256 canónico usado para assinar requests com body (schema §7.1). |
| **`aurora.company-answer.v1`** | Schema do envelope de resposta de `/ask` (§2.1). |
| **`aurora.company-project-upsert.v1`** | Schema de resposta de `/projects/upsert`. |
| **BOM** | *Bill of Materials* — lista quantificada de trabalhos e materiais. |
| **Biblioteca PT 2026** | Catálogo canónico ConstruPilot com 800+ items normalizados PT-PT. |
| **Control plane** | Camada de comando/orquestração. No modelo alvo, a Aurora é o control plane; os SaaS são data planes. |
| **DPGF** | *Décomposition du Prix Global et Forfaitaire* — modelo francófono de orçamento discriminado; equivalente ao BPU + Mapa de Quantidades em PT. |
| **HMAC AS1** | Assinatura canónica descrita em §7.1. |
| **Idempotência** | Garantia de que a repetição do mesmo request produz o mesmo efeito (ver `Idempotency-Key`). |
| **MCP** | *Model Context Protocol* (Anthropic 2024) — inspiração para o formato de manifests do §5.5. |
| **PT-PT** | Português europeu (não brasileiro). |
| **RJUE** | Regime Jurídico da Urbanização e Edificação (DL 555/1999 e atualizações). |
| **RGEU** | Regulamento Geral das Edificações Urbanas (DL 38 382/1951 e atualizações). |
| **SLO / SLI** | *Service Level Objective / Indicator*. |

---

# §2 Contrato de respostas Aurora

Esta secção fixa **schemas obrigatórios** de resposta. Qualquer alteração retro-incompatível terá de ser precedida de aviso prévio de **60 dias corridos** e coexistir em rota paralela versionada (`v2`, `v3`, …).

## 2.1 Coach IA · `POST /ask` · schema `aurora.company-answer.v1`

### 2.1.1 Contrato mínimo

Uma resposta HTTP 200 do endpoint `/ask` **DEVE** cumprir cumulativamente:

1. `Content-Type: application/json; charset=utf-8`.
2. Body JSON válido, sem `null` no campo `text`.
3. Campo `schema` fixo em `"aurora.company-answer.v1"`.
4. Campo `text` **não vazio**: `text.strip().length > 0`.
5. Todos os campos obrigatórios da tabela §2.1.2 preenchidos.

Se Aurora **não conseguir** gerar resposta útil, **NÃO** deve devolver HTTP 200 com `text: ""`. Deve devolver **HTTP 4xx** conforme §2.4 com `error.code` explícito.

> **Racional**: o fluxo Coach IA do ConstruPilot invalida atualmente ~100 % das respostas do modelo `gpt-5.6-luna` em `mode: reasoning` porque devolvem `text: ""` mascarado como sucesso. Isto força retries desnecessários (custo + latência) e degrada UX. Ver **Anexo D** para taxonomia de erros.

### 2.1.2 Campos obrigatórios

| Campo | Tipo | Descrição | Obrigatório |
| --- | --- | --- | :-: |
| `schema` | string | Sempre `"aurora.company-answer.v1"` | ✅ |
| `text` | string | Resposta em PT-PT, `strip().length > 0` | ✅ |
| `model` | string | ID modelo usado (ex. `"gpt-5.6-luna"`, `"claude-sonnet-5"`) | ✅ |
| `route` | string | Rota interna (ex. `"openai/gpt-5.6-luna"`, `"anthropic/claude-sonnet-5"`) | ✅ |
| `mode` | string | Enumerado `"fast" \| "reasoning" \| "deterministic"` | ✅ |
| `request_id` | string (UUIDv4) | ID único do pedido (ecoado do header `X-Aurora-Request-Id`) | ✅ |
| `correlation_id` | string (UUIDv4) | ID de correlação para logs distribuídos | ✅ |
| `latency_ms` | integer | Latência total do lado Aurora (excluindo rede) | ✅ |
| `project_id` | string \| null | ID do projeto passado no request, se aplicável | ⚠️ |
| `resources_used` | array | Lista de recursos consultados (ver §2.1.4) | ⚠️ |
| `external_ai_used` | boolean | `true` se Aurora usou provider externo | ⚠️ |
| `deterministic` | boolean | `true` se resposta é determinística (cache/regra fixa) | ⚠️ |
| `family` | string | Família da operação (ex. `"canonical_intelligence_router"`) | ⚠️ |
| `operation` | string | Operação (ex. `"company.ask"`) | ⚠️ |
| `read_only` | boolean | `true` se a operação não teve side-effects | ⚠️ |
| `side_effects` | boolean | Complementar de `read_only` | ⚠️ |
| `citations` | array | Referências normativas usadas (ver §2.1.3) | ⭐ |
| `confidence` | float `[0, 1]` | Confiança na resposta (só se relevante) | ⭐ |
| `follow_up_suggestions` | array of string | Sugestões de perguntas úteis | ⭐ |

Legenda: ✅ obrigatório · ⚠️ obrigatório se aplicável · ⭐ opcional mas recomendado

### 2.1.3 Campo `citations[]` (crítico para BTP)

Sempre que Aurora citar norma, artigo, portaria, DL, EN, DIN, NBN, DTU, CTE, NTC ou similar, **DEVE** popular `citations[]`. Exemplo:

```json
"citations": [
  {
    "type": "norm",
    "jurisdiction": "PT",
    "code": "RGEU",
    "article": "Art.º 65.º",
    "title": "Pé-direito mínimo",
    "url": "https://dre.pt/…",
    "quoted_text": "O pé-direito mínimo dos compartimentos de habitação é de 2,40 m."
  },
  {
    "type": "eurocode",
    "jurisdiction": "EU",
    "code": "EN 1992-1-1",
    "section": "§ 7.3.2",
    "title": "Controlo da fendilhação",
    "url": "https://…"
  },
  {
    "type": "national_annex",
    "jurisdiction": "PT",
    "code": "EN 1998-1 / NA PT",
    "section": "3.2.1",
    "url": "https://…"
  }
]
```

Campos aceites em cada citation:

| Campo | Tipo | Obrigatório |
| --- | --- | :-: |
| `type` | enum: `norm`, `eurocode`, `national_annex`, `directive`, `regulation_eu`, `case_law`, `technical_spec`, `manufacturer_docs` | ✅ |
| `jurisdiction` | ISO-3166-1 alpha-2 ou `EU` | ✅ |
| `code` | string (identificador oficial) | ✅ |
| `article` \| `section` | string | ⚠️ |
| `title` | string | ⭐ |
| `url` | URL público (dre.pt, eur-lex.europa.eu, cen.eu, boe.es, …) | ⭐ |
| `quoted_text` | string ≤ 500 chars | ⭐ |

### 2.1.4 Campo `resources_used[]`

Cada item é um objeto:

```json
{
  "type": "project" | "estimate" | "document" | "customer" | "invoice" | "measurement" | "photo",
  "resource_id": "prj_xxx",
  "aurora_entity_id": "entity-yyy",
  "excerpt": "primeiros 200 chars do conteúdo relevante",
  "relevance_score": 0.92
}
```

### 2.1.5 Exemplo válido completo

```json
{
  "schema": "aurora.company-answer.v1",
  "request_id": "b3d7e14e-5f92-4b0c-9c8f-7d0f2a1e6a44",
  "correlation_id": "c-2026-02-14-8a1e",
  "latency_ms": 2481,
  "model": "claude-sonnet-5",
  "route": "anthropic/claude-sonnet-5",
  "mode": "reasoning",
  "external_ai_used": true,
  "deterministic": false,
  "family": "canonical_intelligence_router",
  "operation": "company.ask",
  "read_only": true,
  "side_effects": false,
  "project_id": "prj_9d54b166cd4a",
  "resources_used": [
    {
      "type": "project",
      "resource_id": "prj_9d54b166cd4a",
      "aurora_entity_id": "entity-4be17db7f33e",
      "excerpt": "Moradia T3 Cascais · 180 m² · orçamento estimado 245 000 €",
      "relevance_score": 0.98
    }
  ],
  "text": "O pé-direito mínimo em habitação é 2,40 m (RGEU art.º 65.º). Para a sua moradia T3, verifique que os compartimentos habitáveis não descem desse valor. Zonas técnicas (arrumos, despensa) podem ter 2,20 m. Se a cobertura for inclinada, a altura mínima aplica-se a pelo menos metade da área útil do compartimento.",
  "citations": [
    {
      "type": "norm",
      "jurisdiction": "PT",
      "code": "RGEU",
      "article": "Art.º 65.º",
      "title": "Pé-direito mínimo",
      "url": "https://dre.pt/dre/legislacao-consolidada/decreto-lei/1951-38382"
    }
  ],
  "confidence": 0.94,
  "follow_up_suggestions": [
    "Como comprovar o pé-direito num levantamento a laser?",
    "Excepções ao art.º 65.º em reabilitação urbana"
  ]
}
```

## 2.2 Análise de plantas · endpoint novo `POST /analyze-plan`

Este endpoint **ainda não existe** no lado Aurora. É requisito de Fase 2 (§8).

### 2.2.1 URL

```
POST /api/gateway/v1/aurora-core/company/analyze-plan
```

### 2.2.2 Request

Body assinado AS1 (§7.1), `Content-Type: application/json`:

```json
{
  "project_id": "prj_9d54b166cd4a",
  "plan_type": "planta_baixa" | "corte" | "alcado" | "planta_estrutura" | "planta_avac" | "planta_agua" | "planta_eletricidade" | "implantacao",
  "source": {
    "format": "dxf" | "pdf" | "ifc" | "dwg_converted_dxf",
    "extraction": {
      "num_entities": 1247,
      "layers": ["PAREDES","COTAS","PORTAS","JANELAS","..."],
      "text_samples": ["Sala 25 m²","Cozinha 12 m²","..."],
      "dimensions": ["3.50","4.20","..."],
      "bbox": {"width_m": 12.4, "height_m": 8.7},
      "raw_text": "primeiros 4000 chars do texto extraído",
      "extraction_meta": {
        "extractor": "ezdxf-1.4",
        "extraction_time_ms": 340
      }
    }
  },
  "context": {
    "project_type": "reabilitacao_moradia",
    "project_name": "Moradia T3 Cascais",
    "area_declared_m2": 180,
    "budget_declared_eur": 245000,
    "location": {"country": "PT", "region": "Lisboa", "city": "Cascais"},
    "biblioteca_ref": "PT-2026-v1"
  },
  "options": {
    "conformity_checks": ["RGEU","RSCIE","EN_1998_NA_PT"],
    "estimate_pricing": true,
    "language": "pt-PT",
    "include_manufacturer_suggestions": false
  }
}
```

### 2.2.3 Response · schema `aurora.company-plan-analysis.v1`

```json
{
  "schema": "aurora.company-plan-analysis.v1",
  "request_id": "…",
  "correlation_id": "…",
  "latency_ms": 18420,
  "model": "claude-sonnet-5",
  "analysis_id": "apla_abc123",

  "summary": {
    "area_total_m2": 180.4,
    "num_divisions": 8,
    "tipo_obra": "Reabilitação T3 · piso único",
    "escala_detetada": "1:100",
    "unidades_desenho": "metros",
    "confidence": 0.87
  },

  "divisions": [
    {
      "nome": "Sala comum",
      "tipo": "sala_estar",
      "area_m2": 45.2,
      "perimetro_m": 28.4,
      "pe_direito_m": 2.70,
      "aberturas": {"portas": 2, "janelas": 3},
      "layer_source": "PAREDES",
      "confidence": 0.91
    }
  ],

  "elementos_construtivos": [
    {
      "tipo": "parede",
      "sub_tipo": "exterior_dupla" | "exterior_simples" | "divisoria" | "estrutural",
      "material_estimado": "tijolo_furado_11+iso+tijolo_furado_11",
      "espessura_m": 0.30,
      "comprimento_total_m": 42.4,
      "area_m2": 114.5,
      "confidence": 0.82
    },
    {
      "tipo": "cobertura",
      "sub_tipo": "laje_inclinada" | "planiforme" | "telha_ceramica",
      "area_m2": 195.0,
      "inclinacao_pct": 25,
      "confidence": 0.76
    },
    {
      "tipo": "pilar",
      "designacao_planta": "P1",
      "seccao_m": {"b": 0.30, "h": 0.30},
      "altura_m": 3.10,
      "material_estimado": "betao_armado_c25",
      "confidence": 0.68
    }
  ],

  "instalacoes": {
    "eletrica": {
      "pontos_luz": 12,
      "tomadas_16A": 24,
      "tomadas_32A": 2,
      "quadros_previstos": 1,
      "confidence": 0.62
    },
    "aguas": {
      "pontos_agua_fria": 8,
      "pontos_agua_quente": 6,
      "ligacoes_esgoto": 5,
      "confidence": 0.58
    },
    "avac": {
      "unidades_split_previstas": 4,
      "recuperador_calor": false,
      "confidence": 0.40
    },
    "gas": {
      "fogao_previsto": true,
      "esquentador_previsto": false,
      "confidence": 0.55
    }
  },

  "estimativa_bom": [
    {
      "biblioteca_pt_ref": "01.02.03",
      "categoria": "Fundacoes",
      "designacao": "Betão C25/30 em fundações, incluindo aditivos e cofragens",
      "unidade": "m3",
      "quantidade": 12.5,
      "preco_unitario_eur": 95.00,
      "preco_total_eur": 1187.50,
      "regiao_coef": 1.05,
      "confidence": 0.82
    },
    {
      "biblioteca_pt_ref": "04.01.02",
      "categoria": "Alvenarias",
      "designacao": "Parede dupla em tijolo furado 11+11 cm com isolamento XPS 40 mm",
      "unidade": "m2",
      "quantidade": 114.5,
      "preco_unitario_eur": 62.50,
      "preco_total_eur": 7156.25,
      "regiao_coef": 1.05,
      "confidence": 0.85
    }
  ],
  "total_estimado_eur": 175430.00,
  "total_estimado_range_eur": {"min": 158000.00, "max": 195000.00, "std_dev": 12500.00},

  "conformidade": {
    "rgeu": {
      "conforme": true,
      "artigos_verificados": ["65","73","76","83"],
      "observacoes": [
        "Pé-direito 2,70 m ≥ 2,40 m mínimo (art.º 65.º) — CONFORME",
        "Área mínima por compartimento (art.º 73.º) — CONFORME"
      ]
    },
    "rjue": {
      "carece_licenca": true,
      "tipo_operacao": "reabilitacao",
      "artigo_aplicavel": "Art.º 4.º alínea c)",
      "notas": ["Alteração da fachada exige licença ou comunicação prévia consoante área ARU."]
    },
    "rscie": {
      "utilizacao_tipo": "I - Habitacionais",
      "categoria_risco": "1ª (área ≤ 400 m² e altura ≤ 9 m)",
      "medidas_ativas_exigidas": ["Detetor CO em garagem","Extintor 6 kg pó ABC"],
      "conforme": true
    },
    "eurocodes_aplicaveis": ["EN 1990","EN 1991-1-1","EN 1992-1-1","EN 1996-1-1","EN 1998-1"],
    "epbd_conformidade": {
      "classe_energetica_estimada": "B",
      "requer_certificado_energetico": true,
      "notas": ["Recomenda-se cálculo REH para confirmar classe."]
    }
  },

  "avisos": [
    "Cota do pé-direito não visível em 3 divisões — assumido 2,40 m.",
    "Layer 'AVAC' ausente — instalação AVAC estimada por padrão T3.",
    "Legenda de materiais não encontrada — atribuições baseadas em heurística de espessura."
  ],

  "external_ai_used": true,
  "deterministic": false
}
```

### 2.2.4 Regras de precisão

- Áreas: erro absoluto ≤ 3 % ou 0,5 m² (o que for maior).
- Perímetros: erro ≤ 5 %.
- Contagem de elementos (portas, janelas, pontos de luz): erro ≤ 10 % **e** documentado em `avisos`.
- Se dimensões geométricas contradizerem anotações textuais, prevalece o texto **desde que** ambos estejam representados; caso contrário, avisar.
- Sempre reportar `confidence` por bloco (`summary`, `divisions[]`, `elementos_construtivos[]`, `estimativa_bom[]`).

## 2.3 Regras transversais para todos os endpoints

1. **Nunca HTTP 200 com resposta vazia/inútil**. Se não há saída, é 4xx/5xx com `error.code`.
2. **Sempre `request_id` e `correlation_id`** na resposta.
3. **Sempre `confidence`** em qualquer previsão numérica ou classificação.
4. **Sempre datas em ISO-8601 UTC** (`YYYY-MM-DDTHH:MM:SS.sssZ`).
5. **Números decimais como número** (não string). Ex.: `"area_m2": 45.2` não `"area_m2": "45,2 m²"`.
6. **Encoding UTF-8**; caracteres portugueses (ã, ç, ã, õ) preservados sem escape Unicode.
7. **Enumerados fechados** (nenhum valor livre não documentado).

## 2.4 Erros · schema `aurora.error.v1`

Todos os erros HTTP ≥ 400 seguem:

```json
{
  "schema": "aurora.error.v1",
  "error": {
    "code": "insufficient_context",
    "message": "Não há informação suficiente no projeto para responder.",
    "message_i18n": {"pt-PT": "…","en-GB": "…"},
    "details": {"missing_fields": ["project.area_m2","project.budget"]},
    "retriable": false,
    "retry_after_seconds": null,
    "correlation_id": "…",
    "request_id": "…",
    "timestamp": "2026-02-14T09:11:03.000Z"
  }
}
```

### 2.4.1 Códigos de erro obrigatórios (extrato — lista completa em Anexo D)

| Código | HTTP | Retriable | Descrição |
| --- | :-: | :-: | --- |
| `not_authenticated` | 401 | ❌ | Bearer/HMAC inválido |
| `signature_expired` | 401 | ❌ | `ts` fora janela ±300 s |
| `signature_mismatch` | 401 | ❌ | HMAC não bate certo |
| `forbidden` | 403 | ❌ | Sem escopo para operação |
| `resource_not_found` | 404 | ❌ | project_id / entity_id não existe |
| `validation_error` | 422 | ❌ | Body inválido (schema falhou) |
| `rate_limited` | 429 | ✅ | Excedido rate limit |
| `insufficient_context` | 422 | ❌ | Sem dados para responder |
| `model_timeout` | 504 | ✅ | Modelo IA timeout |
| `upstream_error` | 502 | ✅ | Erro provider externo |
| `handler_error` | 500 | ✅ | Erro interno Aurora |
| `service_unavailable` | 503 | ✅ | Manutenção ou capacidade |

---

# §3 Especificação técnica análise de plantas

## 3.1 Formatos suportados

| Formato | Extensão | Suporte Aurora | Preprocessing ConstruPilot |
| --- | :-: | :-: | --- |
| **DXF** ASCII | `.dxf` | ✅ Fase 2 | ezdxf 1.4 → summary + text extraction |
| **DXF** binário | `.dxf` | ✅ Fase 2 | ezdxf recovery mode |
| **DWG** AutoCAD 2000-2018 | `.dwg` | ⚠️ via DXF | CloudConvert → DXF → ezdxf |
| **PDF** vetorial | `.pdf` | ✅ Fase 2 | pypdf `extract_text()` |
| **PDF** rasterizado | `.pdf` | ⚠️ Fase 3 | OCR obrigatório (Tesseract PT) |
| **IFC** IFC2x3 / IFC4 | `.ifc` | 🕐 Fase 4 | IfcOpenShell |
| **RVT** Revit | `.rvt` | ❌ | Exportação prévia para IFC/DWG |

## 3.2 Extrações mínimas exigidas

Aurora **DEVE** ser capaz de identificar, a partir do payload de §2.2.2:

### 3.2.1 Geometria e áreas

- Área útil por compartimento (a partir de polylines fechadas ou anotações "X m²").
- Área bruta total (bbox × densidade útil, heurística).
- Perímetro exterior (contorno da envolvente).
- Perímetro interior (soma dos perímetros das paredes divisórias).
- Comprimento linear por classe (paredes, portas, janelas).

### 3.2.2 Elementos construtivos

- **Paredes**: comprimento, espessura, classificação (exterior / divisória / estrutural).
- **Pilares/vigas** (se cotados): secção, altura/vão, material inferido.
- **Lajes** (se representadas em corte): espessura, tipo (maciça, aligeirada, colaborante).
- **Fundações** (se cotadas): tipo (sapata isolada, corrida, ensoleiramento).
- **Coberturas**: tipo, área, inclinação.
- **Aberturas**:
  - Portas: contagem, largura, altura, sentido de abertura, classe (interior/exterior/corta-fogo).
  - Janelas: contagem, dimensões, orientação (cardinal + solar), tipo de caixilho (se anotado).

### 3.2.3 Instalações (se representadas)

- **Elétrica**: pontos de luz (símbolos ⊗), tomadas (⏦), quadros, interruptores.
- **Águas**: pontos de água fria/quente, ligações de esgoto, autoclismos, chuveiros.
- **AVAC**: unidades interiores/exteriores, condutas, difusores.
- **Gás**: pontos de fogão, esquentador/caldeira.
- **Comunicações**: RJ45, TV, fibra ótica.

### 3.2.4 Cotas altimétricas

- Pé-direito de cada compartimento (se cotado).
- Altura total (cumeeira).
- Diferenças de nível (rampas, escadas — passos, cobertores).

### 3.2.5 Anotações normativas

- Referências textuais a normas ("Conforme RGEU art. 65", "EC2 §7.3").
- Certificações declaradas ("Certificado energético B+", "CE-marked").
- Fabricantes/marcas comerciais mencionadas.

## 3.3 Precisão exigida por métrica

| Métrica | Tolerância | Método de aferição |
| --- | :-: | --- |
| Áreas úteis | ≤ 3 % ou 0,5 m² | Cross-check polyline vs anotação |
| Perímetros | ≤ 5 % | Soma linear |
| Contagem elementos | ≤ 10 % | Contagem por símbolo/layer |
| Comprimento paredes | ≤ 5 % | Soma segmentos |
| Espessura paredes | ± 0,02 m | Distância entre polylines paralelas |
| Cotas altimétricas | ± 0,05 m | Texto DXF ou anotação PDF |
| Estimativa BOM (total €) | ≤ 15 % faixa central | Comparação com orçamentos reais Biblioteca PT |

## 3.4 Mapeamento para Biblioteca PT 2026

Cada item em `estimativa_bom[]` **DEVE** ter:

- `biblioteca_pt_ref`: código canónico (formato `NN.NN.NN`, ex. `04.01.02`).
- `categoria`: uma das 14 categorias listadas em §3.4.1.
- `designacao`: descrição normalizada PT-PT (extraída da Biblioteca).
- `unidade`: unidade canónica (§3.4.2).
- `quantidade`: número decimal.
- `preco_unitario_eur`: valor médio da Biblioteca × `regiao_coef`.

### 3.4.1 Categorias canónicas (14)

1. **Movimentos de terra** (`01.*`) — desmatação, escavação, aterro, drenagem.
2. **Fundações** (`02.*`) — sapatas, ensoleiramentos, estacas, muros.
3. **Estruturas** (`03.*`) — pilares, vigas, lajes, escadas em BA/aço/madeira.
4. **Alvenarias** (`04.*`) — paredes exteriores, divisórias, revestimentos crus.
5. **Coberturas** (`05.*`) — laje inclinada, cobertura em telha/chapa, cobertura plana.
6. **Revestimentos** (`06.*`) — pavimentos, tetos, paredes interiores/exteriores.
7. **Carpintarias** (`07.*`) — portas, janelas, armários, rodapés.
8. **Serralharias** (`08.*`) — portões, gradeamentos, escadas metálicas.
9. **Vidros** (`09.*`) — envidraçados, guarda-corpos, coberturas.
10. **Pinturas** (`10.*`) — interior/exterior, primários, tintas especiais.
11. **Instalações elétricas** (`11.*`) — quadros, cablagem, iluminação, domótica.
12. **Instalações hidráulicas** (`12.*`) — águas, esgotos, drenagem pluvial.
13. **AVAC** (`13.*`) — climatização, ventilação, AQS.
14. **Instalações de gás** (`14.*`) — GN/GPL, caldeiras, esquentadores.

Categorias auxiliares:

- **Equipamentos** (`15.*`) — móveis fixos, eletrodomésticos incluídos em BOM.
- **Arranjos exteriores** (`16.*`) — pavimentação, jardins, muros de vedação.
- **Diversos e trabalhos preparatórios** (`00.*`) — estaleiro, EPI, seguros, licenças.

### 3.4.2 Unidades canónicas

| Grandeza | Unidade | Exemplos |
| --- | :-: | --- |
| Comprimento | `m` | betão de limpeza, rufos, tubagem |
| Área | `m2` | reboco, pintura, cobertura, pavimento |
| Volume | `m3` | betão, escavação, aterro |
| Peso | `kg` | aço em armaduras, perfis metálicos |
| Unidade | `un` | portas, janelas, sanitários, tomadas |
| Hora | `h` | mão-de-obra específica |
| Vago (verba) | `vg` | forfait para trabalho não cotável linearmente |

## 3.5 Fluxo de análise plantas end-to-end (Aurora)

```
1. ConstruPilot recebe upload (DWG/DXF/PDF)
2. ConstruPilot preprocessa:
   - DWG → CloudConvert → DXF
   - DXF → ezdxf → summary (entidades, layers, textos, cotas, bbox)
   - PDF → pypdf → texto extraído
3. ConstruPilot invoca POST /analyze-plan (AS1)
4. Aurora executa:
   a. Validação schema request
   b. Enriquecimento com contexto do projeto (via /projects/get)
   c. Análise multimodal (LLM + rules-engine para geometria)
   d. Cross-check com Biblioteca PT 2026
   e. Verificação conformidade (RGEU/RSCIE/EC)
   f. Cálculo estimativa BOM com coeficiente regional
5. Aurora devolve resposta schema aurora.company-plan-analysis.v1
6. ConstruPilot persiste em plan_analyses (MongoDB)
7. ConstruPilot exibe ao utilizador (UI /pc-analysis ou /plan-takeoff)
```

---

# §4 Assistente BTP · normativa europeia completa

## 4.1 Cobertura obrigatória

Aurora **DEVE** dominar as normativas listadas nesta secção. "Dominar" significa:

- **Reconhecer** o instrumento normativo pelo código/número.
- **Localizar** artigo/secção relevante a partir de uma pergunta em linguagem natural.
- **Extrair** o requisito literal (com aspas).
- **Aplicar** o requisito ao contexto do projeto (cálculo simples ou verificação binária).
- **Citar** com URL público oficial (dre.pt, eur-lex.europa.eu, cen.eu, BOE, Légifrance, gazzettaufficiale.it, DIN, …).

### 4.1.1 🇵🇹 Portugal — normativa nacional obrigatória

| Sigla | Diploma | Âmbito | Estado |
| --- | --- | --- | :-: |
| **RGEU** | DL 38 382/1951 (com todas as atualizações) | Regulamento Geral das Edificações Urbanas | Vigente |
| **RJUE** | DL 555/1999 (redação atual) | Regime Jurídico da Urbanização e Edificação | Vigente |
| **RCCTE/REH** | DL 118/2013 (atualizado 2020) | Comportamento térmico dos edifícios (residencial) | Vigente |
| **RECS** | DL 118/2013 (mesmo DL) | Comércio e serviços | Vigente |
| **RSCIE** | DL 220/2008 + Portaria 1532/2008 (atual. 2022) | Segurança contra incêndio | Vigente |
| **RGCE** | Regulamento Geral do Consumo de Energia | Consumo energético | Vigente |
| **RGIT** | Regulamento Geral das Instalações Térmicas | Instalações térmicas em edifícios | Vigente |
| **RRAE** | DL 96/2008 | Requisitos Acústicos Edifícios | Vigente |
| **DL 163/2006** | DL 163/2006 | Acessibilidade a pessoas com mobilidade condicionada | Vigente |
| **CCP** | DL 18/2008 + revisões | Código dos Contratos Públicos | Vigente |
| **RJIGT** | DL 80/2015 | Instrumentos de Gestão Territorial | Vigente |
| **RCTU** | DL 555/1999 | Regime das Compensações Urbanísticas | Vigente |
| **RJRU** | DL 307/2009 | Regime Jurídico da Reabilitação Urbana | Vigente |
| **RJUE ARU** | Regime específico ARU | Áreas de Reabilitação Urbana | Vigente |
| **REBAP** | DL 235/83 (substituído por EC2 mas ainda referenciado) | Betão armado e pré-esforçado (histórico) | Histórico |
| **REAE** | DL 349-C/83 | Estruturas de edifícios (histórico) | Histórico |
| **RSA** | DL 235/83 | Segurança e ações estruturas (histórico) | Histórico |
| **Portarias LNEC** | Diversas | Especificações técnicas (E-LNEC) | Vigente |
| **DL 39/2008** | Alojamento local | RJEEE-AL | Vigente |
| **DL 118/2013** | (repetido — SCE, REH, RECS) | SCE — Sistema Certificação Energética | Vigente |

**Especificações E-LNEC** frequentes:

- E 464 — inertes
- E 461 — betão pronto
- E 465 — cimento
- E 466 — cinzas volantes
- E 471 — aço em varão nervurado

### 4.1.2 🇪🇺 Eurocodes (EN 1990-1999) — todos os países UE

| Eurocode | Norma | Âmbito | Anexo Nacional PT |
| --- | --- | --- | :-: |
| **EC0** | EN 1990 | Bases de projeto estrutural | NP EN 1990 |
| **EC1** | EN 1991-1-1 | Ações — permanentes e restantes | NP EN 1991-1-1 |
| EC1 | EN 1991-1-2 | Ações — fogo | NP EN 1991-1-2 |
| EC1 | EN 1991-1-3 | Ações — neve | NP EN 1991-1-3 |
| EC1 | EN 1991-1-4 | Ações — vento | NP EN 1991-1-4 |
| EC1 | EN 1991-1-5 | Ações — térmicas | NP EN 1991-1-5 |
| EC1 | EN 1991-1-6 | Ações — durante execução | NP EN 1991-1-6 |
| EC1 | EN 1991-1-7 | Ações acidentais | NP EN 1991-1-7 |
| EC1 | EN 1991-2 | Pontes — cargas de tráfego | NP EN 1991-2 |
| EC1 | EN 1991-3 | Ações induzidas por gruas | NP EN 1991-3 |
| EC1 | EN 1991-4 | Silos e reservatórios | NP EN 1991-4 |
| **EC2** | EN 1992-1-1 | Betão — regras gerais | NP EN 1992-1-1 |
| EC2 | EN 1992-1-2 | Betão — fogo | NP EN 1992-1-2 |
| EC2 | EN 1992-2 | Pontes em betão | NP EN 1992-2 |
| EC2 | EN 1992-3 | Reservatórios em betão | NP EN 1992-3 |
| **EC3** | EN 1993-1-1 | Aço — regras gerais | NP EN 1993-1-1 |
| EC3 | EN 1993-1-8 | Ligações em aço | NP EN 1993-1-8 |
| EC3 | EN 1993-1-10 | Aço — tenacidade | NP EN 1993-1-10 |
| **EC4** | EN 1994-1-1 | Estruturas mistas aço-betão | NP EN 1994-1-1 |
| **EC5** | EN 1995-1-1 | Madeira — regras gerais | NP EN 1995-1-1 |
| **EC6** | EN 1996-1-1 | Alvenaria — regras gerais | NP EN 1996-1-1 |
| **EC7** | EN 1997-1 | Geotecnia — regras gerais | NP EN 1997-1 |
| EC7 | EN 1997-2 | Ensaios geotécnicos | NP EN 1997-2 |
| **EC8** | EN 1998-1 | Sismos — regras gerais | NP EN 1998-1 (crítico PT) |
| EC8 | EN 1998-3 | Sismos — reforço/reabilitação | NP EN 1998-3 |
| EC8 | EN 1998-5 | Sismos — fundações | NP EN 1998-5 |
| **EC9** | EN 1999-1-1 | Alumínio — regras gerais | NP EN 1999-1-1 |

**Anexos Nacionais críticos** que Aurora tem de conhecer por país (para EC8 sobretudo):

- 🇵🇹 PT: zonamento sísmico 5 zonas (1.1 a 2.5), classes de solo A-E, tipo I/II.
- 🇪🇸 ES: mapa sísmico do Anejo Nacional (NCSE-02 + Eurocode 8).
- 🇮🇹 IT: NTC 2018 + Circolare 2019 (integração EC8).
- 🇬🇷 GR: EAK 2000 → mapa sísmico.
- 🇫🇷 FR: zonage sismique DDT 2010 (5 zonas).

### 4.1.3 🇪🇺 Diretivas UE e normativas transversais

| Instrumento | Ref. | Âmbito |
| --- | --- | --- |
| **CPR** | (UE) 305/2011 | Regulamento Produtos Construção · marcação CE |
| **EPBD** (revisão 2024) | 2010/31/UE + 2018/844 + revisão 2024 | Eficiência energética edifícios |
| **nZEB** | Diretiva EPBD + planos nacionais | Edifícios com necessidade quase nula |
| **Diretiva 92/57/CEE** | 92/57/CEE | Estaleiros temporários / móveis · SST |
| **Diretiva 2014/24/UE** | 2014/24/UE | Contratos públicos |
| **REACH** | (CE) 1907/2006 | Registo, avaliação, autorização químicos |
| **CLP** | (CE) 1272/2008 | Classificação, rotulagem embalagens |
| **RoHS** | 2011/65/UE | Substâncias perigosas equipamentos |
| **LEVEL(s)** | Framework Comissão UE | Sustentabilidade edifícios |
| **CSRD** | Diretiva 2022/2464/UE | Reporting sustentabilidade corporativo |
| **EU Taxonomy** | (UE) 2020/852 | Classificação atividades económicas verdes |
| **NFRD** | (substituído pela CSRD) | Reporting não-financeiro (histórico) |
| **Diretiva 2009/28/CE** (RED) | RED + RED II + RED III | Energias renováveis |
| **EED** | Diretiva 2012/27/UE | Eficiência energética |
| **EU F-Gas** | (UE) 517/2014 | Gases fluorados AVAC |

### 4.1.4 Normativa por país (Aurora deve saber diferenciar)

#### 🇪🇸 Espanha

| Sigla | Descrição |
| --- | --- |
| **CTE** | Código Técnico de la Edificación (RD 314/2006) — 6 documentos básicos (DB-SE, DB-SI, DB-SUA, DB-HS, DB-HR, DB-HE) |
| **EHE-08** | Instrucción del Hormigón Estructural |
| **EAE** | Instrucción de Acero Estructural |
| **NCSE-02** | Norma de Construcción Sismorresistente |
| **RITE** | Reglamento de Instalaciones Térmicas en los Edificios |
| **REBT** | Reglamento Electrotécnico de Baja Tensión (RD 842/2002) |
| **LOE** | Ley de Ordenación de la Edificación (Ley 38/1999) |

#### 🇫🇷 França

| Sigla | Descrição |
| --- | --- |
| **RE2020** | Réglementation Environnementale 2020 (substitui RT2012) |
| **DTU** | Documents Techniques Unifiés (100+ documentos, ex. DTU 20.1 alvenaria, DTU 21 betão, DTU 43 impermeabilizações) |
| **NF EN** | Normas Françaises adotando EN |
| **NF DTU** | DTU harmonizados com EN |
| **Règles Th-BCE** | Thermique, Bioclimatique et Consommations Énergétiques |
| **Code de la construction et de l'habitation** | CCH |
| **Loi ELAN** | Évolution du Logement (2018) |
| **Règlement de sécurité incendie ERP** | Estabelecimentos Recebendo Público |
| **RGE** | Reconnu Garant Environnement (certificação artesão) |
| **QUALIBAT / QUALIFELEC** | Certificações |

#### 🇮🇹 Itália

| Sigla | Descrição |
| --- | --- |
| **NTC 2018** | Norme Tecniche per le Costruzioni (DM 17/01/2018) |
| **Circolare 2019** | Aplicação NTC 2018 |
| **UNI EN** | Normas Ente Nazionale Italiano di Unificazione |
| **DM 26/06/2015** | Requisiti minimi prestazione energetica |
| **APE** | Attestato di Prestazione Energetica |
| **Testo Unico Edilizia** | DPR 380/2001 |
| **DM 3 agosto 2015** | Prevenzione incendi |
| **Regolamento Edilizio Tipo** | 2016 (armonizzato regioni) |

#### 🇩🇪 Alemanha

| Sigla | Descrição |
| --- | --- |
| **DIN Normen** | 4102 (fogo), 4108 (térmica), 4109 (acústica), 1045 (betão), 18800 (aço) |
| **GEG** | Gebäudeenergiegesetz (2020, substitui EnEV/EEWärmeG/EnEG) |
| **BauO Länder** | Bauordnung por estado federal (16 Länder) |
| **MBO** | Musterbauordnung (modelo federal) |
| **VOB** | Vergabe- und Vertragsordnung für Bauleistungen |
| **HOAI** | Honorarordnung für Architekten und Ingenieure |
| **DGNB** | Certificação sustentabilidade edifícios |

#### 🇧🇪 Bélgica

| Sigla | Descrição |
| --- | --- |
| **NBN** | Bureau de Normalisation (adopção EN) |
| **PEB** | Performance Énergétique des Bâtiments (Valónia + Bruxelas) |
| **EPB** | Energieprestatie en Binnenklimaat (Flandres) |
| **Règlement Régional d'Urbanisme (RRU)** | Bruxelas |
| **CoBAT** | Code Bruxellois de l'Aménagement du Territoire |
| **CWATUP** | Code Wallon de l'Aménagement du Territoire |
| **VCRO** | Vlaamse Codex Ruimtelijke Ordening (Flandres) |

#### 🇳🇱 Países Baixos

| Sigla | Descrição |
| --- | --- |
| **Bouwbesluit 2012** | Regulamento construção (revisão 2024 → **Bbl** — Besluit bouwwerken leefomgeving) |
| **NEN** | Nederlands Normalisatie-instituut (NEN 6702 ações, NEN 6720 betão, …) |
| **BENG** | Bijna Energie Neutrale Gebouwen (nZEB) |
| **Woningwet** | Lei da habitação |
| **Omgevingswet** | Nova lei ambiente/urbanismo (2024) |

#### 🇬🇧 Reino Unido (pós-Brexit, relevante para trabalhos transnacionais)

| Sigla | Descrição |
| --- | --- |
| **Building Regulations** | Approved Documents Part A-R (A: estrutura; B: fogo; L: energia; M: acessibilidade; …) |
| **BS EN** | British Standards adopção EN |
| **CDM 2015** | Construction Design and Management Regulations |
| **BSA 2022** | Building Safety Act (pós-Grenfell) |
| **CIBSE** | Chartered Institution of Building Services Engineers |
| **NHBC** | National House Building Council |

#### 🇦🇹 🇱🇺 🇮🇪 🇩🇰 🇸🇪 🇫🇮 🇵🇱 🇨🇿 🇭🇺 🇷🇴 🇧🇬 🇬🇷 🇭🇷 🇸🇮 🇸🇰 🇪🇪 🇱🇻 🇱🇹 🇲🇹 🇨🇾

Todos os restantes estados-membro UE. Aurora **DEVE** ser capaz de identificar o instrumento regulatório local principal e responder com fontes oficiais dos respetivos gazetas oficiais.

## 4.2 Estilo de resposta obrigatório

### 4.2.1 Idioma

- Idioma-alvo predefinido: **Português europeu (PT-PT)**.
- Se o utilizador escrever em outra língua, Aurora responde em PT-PT mas mantém os termos técnicos originais entre parênteses. Ex.: *"O muro de contenção (retaining wall) tem de cumprir…"*.
- Nunca usar português brasileiro (evitar "banheiro", "geladeira", "aluguel", "usuário", "tela", etc.).

### 4.2.2 Estrutura de resposta

```
[Resposta principal — 3-5 linhas em português técnico rigoroso]

Referências normativas:
• [Instrumento + Artigo/Secção + citação literal se aplicável]
• [Fonte URL]

Cálculo / verificação (se aplicável):
• [Passos numerados]
• [Resultado com unidades]

Avisos:
• [Limitações da resposta, hipóteses assumidas]
• [Recomendação de consulta a projetista se aplicável]
```

### 4.2.3 Rigor técnico

- **Sempre** citar norma + artigo/secção.
- **Sempre** unidades SI (metros, m², m³, kN, kPa, °C, kWh, W/m·K).
- **Nunca** unidades imperiais.
- Se Aurora não souber: *"Não consta na normativa acessível à Aurora. Recomenda-se consulta a projetista credenciado."* — nunca "achar" sem base.

### 4.2.4 Casos de responsabilidade profissional

Sempre que a pergunta envolva:

- Projeto de estrutura, AVAC, gás, eletricidade, ITED, acústica.
- Verificação de segurança sísmica (EC8).
- Certificação energética (SCE).
- Coordenação de segurança em estaleiro.
- Peritagem legal ou judicial.

Aurora **DEVE** incluir aviso:

> *"Esta resposta é indicativa. Um projeto/verificação formal deve ser elaborado por técnico credenciado (Eng.º Civil, Arq., Eng.º Eletrotécnico, TSHST, Perito) inscrito na respetiva ordem/associação profissional."*

## 4.3 Capacidades quantitativas exigidas

Aurora **DEVE** executar corretamente:

### 4.3.1 Cálculo de cargas estruturais (EC1)

- Peso próprio de elementos (γ×V) — betão 25 kN/m³, aço 78,5 kN/m³, madeira 5-10 kN/m³.
- Sobrecargas de utilização (EC1-1-1 tabela 6.2): habitação 2,0 kN/m², escritórios 3,0 kN/m², etc.
- Vento (EC1-1-4) — velocidade de referência PT: 27 m/s zona A, 30 m/s zona B.
- Neve (EC1-1-3) — geralmente negligenciável em PT continental exceto Serra da Estrela.
- Sismo (EC8) — aceleração de referência a_gR consoante zona sísmica.

### 4.3.2 Verificações de conforto térmico (EPBD/REH)

- Cálculo de U-value (coeficiente transmissão térmica) em W/m²·K.
  - Fórmula: U = 1 / (R_si + Σ(e_i/λ_i) + R_se)
  - R_si = 0,13 m²·K/W (paredes int.), R_se = 0,04 m²·K/W (ext.).
- Valores máximos por zona climática PT (I1/I2/I3):
  - Paredes exteriores: 0,50 / 0,40 / 0,35 W/m²·K.
  - Coberturas: 0,40 / 0,35 / 0,30.
  - Envidraçados: 3,3 / 3,3 / 3,3 (fator solar ≤ 0,50 / 0,45 / 0,40).

### 4.3.3 Dimensionamento acústico (RRAE / EN 12354)

- Índice ponderado de isolamento sonoro aéreo Rw entre fogos ≥ 50 dB (residencial).
- Índice ponderado de isolamento a ruído de percussão L'nw ≤ 60 dB.

### 4.3.4 Acessibilidade (DL 163/2006)

- Rampas: pendente máxima 8 % em vias públicas, 10 % em vias privadas até 5 m.
- Corredores: largura mínima 1,20 m; portas ≥ 0,90 m largura.
- Instalações sanitárias: raio de manobra ≥ 1,50 m.

### 4.3.5 Estimativa de custos

- Aplicação de `regiao_coef` PT (Lisboa 1,00 · Porto 0,95 · Algarve 1,10 · Alentejo 0,85 · Madeira/Açores 1,15).
- Uso do BOM da Biblioteca PT 2026 + preços médios EUR 2026.
- Margem para imprevistos: sugerir 8-15 % dependendo do tipo de obra.

### 4.3.6 Segurança contra incêndio (RSCIE)

- Classificação da utilização-tipo I-XII.
- Categorias de risco 1ª-4ª (por altura + área).
- Medidas exigidas por categoria (extintores, hidrantes, deteção, desenfumagem, SADI, CVs, saídas).

---

# §5 Aurora como plano de controlo · 100 % ConstruPilot / 99 % SaaS

## 5.1 Modelo conceptual

A Aurora é o **plano de controlo (control plane)** e cada SaaS integrado (ConstruPilot, um CRM, um ERP, uma plataforma de RH, …) é um **plano de dados (data plane)**.

```
                     ┌────────────────────┐
                     │   Aurora (control) │
                     └─────────┬──────────┘
                               │  aurora.command.v1 (HMAC AS1)
     ┌─────────────┬───────────┼────────────┬──────────────┐
     ▼             ▼           ▼            ▼              ▼
┌─────────┐  ┌──────────┐ ┌────────┐  ┌──────────┐  ┌──────────┐
│Constru- │  │  CRM      │ │  ERP   │  │  RH      │  │ Suporte  │
│ Pilot   │  │  (data)   │ │ (data) │  │ (data)   │  │ (data)   │
└─────────┘  └──────────┘ └────────┘  └──────────┘  └──────────┘
```

**Comunicação bidirecional**:

1. **SaaS → Aurora**: eventos (`event`), sincronização (`upsert`), perguntas (`ask`).
2. **Aurora → SaaS**: comandos (`command.v1`), webhooks (durable outbox).

O protocolo é inspirado no **MCP (Model Context Protocol)** da Anthropic (2024), com adaptações:

- Segurança: HMAC AS1 SHA-256 em vez de HTTP/2 stdio.
- Empacotamento: JSON via HTTPS em vez de JSON-RPC.
- Descoberta: tool manifests publicados por endpoint (§5.5).

## 5.2 Contrato de comandos Aurora → ConstruPilot

### 5.2.1 Endpoint receptor ConstruPilot

```
POST https://construpilot.pt/api/aurora-callback/execute
Content-Type: application/json
Authorization: Bearer <aurora_service_token>
X-Aurora-Signature: AS1 key_id=<kid> ts=<ts> sig=<sig>
X-Aurora-Request-Id: <uuid>
Idempotency-Key: <uuid>
```

### 5.2.2 Request schema `aurora.command.v1`

```json
{
  "schema": "aurora.command.v1",
  "command_id": "cmd_9f3b1c8e",
  "correlation_id": "cor_01FZY…",
  "trace_id": "trc_0dab…",

  "issued_at": "2026-02-14T10:22:00.000Z",
  "expires_at": "2026-02-14T10:32:00.000Z",

  "intent": "create_estimate",
  "target_platform": "construpilot",

  "target_resource": {
    "type": "project",
    "id": "prj_9d54b166cd4a",
    "aurora_entity_id": "entity-4be17db7f33e"
  },

  "actor": {
    "type": "user" | "service" | "scheduled",
    "user_id": "user_f091093",
    "session_id": "sess_…",
    "user_locale": "pt-PT"
  },

  "payload": {
    "estimate_name": "Orçamento reabilitação sala",
    "items": [
      {"biblioteca_pt_ref": "10.02.01", "quantity": 45.2, "unit": "m2"}
    ],
    "margin_pct": 15,
    "notes": "Cliente solicitou variante em pladur."
  },

  "dry_run": false,
  "auto_approve": false,
  "requires_user_confirmation": true,
  "confirmation_deadline_seconds": 900,

  "idempotency_key": "idem_9f3b1c8e",
  "constraints": {
    "max_amount_eur": 50000,
    "requires_2fa": false
  },

  "audit_context": {
    "reason": "Utilizador pediu à Aurora para criar orçamento com base na análise de plantas apla_abc123.",
    "aurora_conversation_id": "conv_…",
    "source_message_id": "msg_…"
  }
}
```

### 5.2.3 Response schema `aurora.command-result.v1`

Resposta do ConstruPilot ao comando:

```json
{
  "schema": "aurora.command-result.v1",
  "command_id": "cmd_9f3b1c8e",
  "correlation_id": "cor_01FZY…",
  "status": "executed" | "pending_approval" | "rejected" | "expired" | "failed",
  "http_status": 202,
  "result": {
    "resource_type": "estimate",
    "resource_id": "est_00c9d4",
    "resource_url": "https://construpilot.pt/estimation/est_00c9d4",
    "created": true
  },
  "user_approval_url": "https://construpilot.pt/aurora-approvals/cmd_9f3b1c8e",
  "user_approval_expires_at": "2026-02-14T10:37:00.000Z",
  "audit_log_id": "audit_5f7e",
  "reason_if_rejected": null,
  "executed_at": "2026-02-14T10:22:03.000Z",
  "duration_ms": 240
}
```

### 5.2.4 Estados `status`

| Estado | Semântica | HTTP típico |
| --- | --- | :-: |
| `executed` | Ação realizada com sucesso | 200 / 201 |
| `pending_approval` | À espera de confirmação do utilizador | 202 |
| `rejected` | Rejeitado por política ou utilizador | 403 / 409 |
| `expired` | `expires_at` ultrapassado | 410 |
| `failed` | Erro técnico | 500 / 502 |

## 5.3 Tipos de operação e política de aprovação

| Tipo | Descrição | `requires_user_confirmation` | `requires_2fa` | Auditoria |
| --- | --- | :-: | :-: | :-: |
| `read` | Consulta (nunca side-effect) | ❌ | ❌ | Ligeira |
| `mutate_safe` | Criar rascunho, adicionar nota, comentário | Opcional | ❌ | Padrão |
| `mutate_business` | Emitir orçamento, alterar estado projeto, enviar e-mail cliente | ✅ | ❌ | Reforçada |
| `mutate_financial` | Emitir fatura, receber pagamento, gerar recibo | ✅ | ✅ | Total |
| `destructive` | Apagar recurso, cancelar contrato, remover utilizador | ✅ (2 confirmações) | ✅ | Total + notificação admin |
| `security_sensitive` | Rotacionar chaves, alterar permissões, exportar dados totais | **NUNCA automático — sempre humano** | ✅ | Total + assinatura digital |

**Notas**:

- O ConstruPilot **DEVE** validar o `intent` contra a política acima. Se o comando pretender `destructive` sem `requires_user_confirmation: true`, o ConstruPilot rejeita imediatamente (`rejected`, HTTP 403).
- O tempo de aprovação por defeito é **15 minutos**; findo o prazo o comando fica `expired`.

## 5.4 Auditoria

### 5.4.1 Coleção MongoDB `aurora_actions`

Cada comando é registado com:

```json
{
  "audit_id": "audit_5f7e",
  "command_id": "cmd_9f3b1c8e",
  "correlation_id": "cor_01FZY…",
  "received_at": "2026-02-14T10:22:00.100Z",
  "actor": { "user_id": "user_f091093", "type": "user" },
  "intent": "create_estimate",
  "payload_hash_sha256": "d3b0c4…",
  "signature_valid": true,
  "signature_key_id": "kid_a1b2",
  "policy_evaluation": {
    "type": "mutate_business",
    "required_confirmation": true,
    "required_2fa": false
  },
  "outcome": {
    "status": "executed",
    "http_status": 201,
    "resource_id": "est_00c9d4",
    "duration_ms": 240
  },
  "diff": [
    {"path": "estimates", "op": "add", "resource_id": "est_00c9d4"}
  ],
  "retained_until": "2033-02-14T10:22:00.100Z"
}
```

### 5.4.2 Endpoint de inspeção admin

```
GET /api/admin/aurora-actions?since=2026-02-01&user_id=user_xxx&intent=create_estimate&limit=100
```

Retorna lista paginada (`items[]`, `next_cursor`, `total`).

### 5.4.3 Retenção

**7 anos** — compatibilidade com:

- RGPD (obrigações comerciais).
- CCP (contratos públicos).
- Regime Fiscal (obrigação de conservação escrita 10 anos, mas Aurora regista só metadados, não conteúdo fiscal).

Ao fim de 7 anos, o registo é **anonimizado** (remoção de `user_id`, `payload_hash`, `diff` detalhado) mas mantém-se agregado estatístico.

## 5.5 Extensão a outras SaaS · visão 99 %

### 5.5.1 Tool manifests

Cada plataforma publica um manifesto num endpoint estável:

```
GET https://<platform>/api/aurora-callback/manifest
```

Schema `aurora.tool-manifest.v1`:

```json
{
  "schema": "aurora.tool-manifest.v1",
  "platform": "construpilot",
  "version": "1.0.0",
  "base_url": "https://construpilot.pt/api/aurora-callback",
  "webhook_url": "https://construpilot.pt/api/aurora-callback/webhook",
  "auth": {
    "type": "hmac_as1",
    "signing_algo": "HMAC-SHA256",
    "public_key_id": "kid_a1b2",
    "rotate_hint_url": "https://construpilot.pt/api/admin/secrets"
  },
  "capabilities": [
    {
      "name": "create_project",
      "intent": "create_project",
      "type": "mutate_safe",
      "params_schema": {
        "type": "object",
        "required": ["name","project_type"],
        "properties": {
          "name": {"type": "string"},
          "project_type": {"enum": ["moradia","apartamento","comercial","industrial"]},
          "area_m2": {"type": "number"},
          "budget_eur": {"type": "number"},
          "location": {"$ref": "#/definitions/location"}
        }
      },
      "requires_approval": false,
      "example": {"name": "Reabilitação T3", "project_type": "moradia"}
    },
    {
      "name": "create_estimate",
      "intent": "create_estimate",
      "type": "mutate_business",
      "requires_approval": true
    },
    {
      "name": "emit_invoice",
      "intent": "emit_invoice",
      "type": "mutate_financial",
      "requires_approval": true,
      "requires_2fa": true
    }
  ],
  "definitions": { "…schemas partilhados…": {} }
}
```

### 5.5.2 Cobertura 99 % — domínios de operações SaaS

Aurora, ao dispor destes manifests, consegue operar transversalmente sobre:

| Domínio | Operações típicas cobertas |
| --- | --- |
| **CRM** | leads, clientes, contactos, oportunidades, pipeline, follow-ups |
| **ERP** | orçamentos, faturas, notas de crédito, ordens de compra, stock, fornecedores |
| **Project management** | projetos, tarefas, milestones, dependências, atribuições, cronograma |
| **RH** | dossiers colaborador, folhas de horas, férias (leitura + rascunhos de aprovação) |
| **Contabilidade** | lançamentos, conciliações bancárias, reporting fiscal (sob aprovação) |
| **Marketing** | campanhas email, agendamentos redes sociais, audiências, KPIs |
| **Suporte ao cliente** | tickets, base de conhecimento, escalonamentos, SLAs |
| **Documentos** | geração, versionamento, assinatura eletrónica (via provider), arquivamento |
| **Analytics** | relatórios, dashboards, exports CSV/PDF, alertas |
| **Comunicação** | e-mail, SMS, WhatsApp Business, notificações push |
| **Calendário** | reuniões, disponibilidades, recursos (salas, equipamentos) |
| **Ficheiros / DAM** | upload, organização, permissões, tags, pesquisa semântica |

### 5.5.3 Cobertura 1 % NÃO coberta (excluída por design)

**Por segurança, Aurora nunca executa** (mesmo com aprovação explícita):

| Operação | Razão da exclusão |
| --- | --- |
| Rotação de chaves/segredos (API keys, secrets) | Sempre humano na consola de admin |
| Alteração de permissões root/admin | Risco de escalação de privilégios |
| Exportação total de dados (dump completo) | Risco RGPD; exige assinatura DPO |
| Cancelamento de contas de tenant | Impacto irreversível; requer processo legal |
| Ações físicas irreversíveis fora do software | (envio de mercadoria física, execução monetária de valor > threshold) |
| Alteração de contratos legais (T&C, DPA) | Requer legal review humano |
| Impressão de cheques ou instrumentos monetários físicos | Risco fraude |
| Alteração de dados fiscais (NIF, IBAN empresa) | Requer validação notarial |

## 5.6 Orquestração multi-SaaS

Um único pedido do utilizador pode desencadear comandos em **múltiplos SaaS**. Aurora deve gerir:

- **Saga pattern**: sequência de comandos idempotentes com compensação em caso de falha.
- **Timeout global**: 10 minutos por saga; findo o tempo, compensações automáticas.
- **Confirmação em lote**: URL única no ConstruPilot que agrega N aprovações pendentes.

Exemplo de saga:

```
User → Aurora: "Aceita este orçamento, envia email ao cliente e cria fatura de sinal 30%."

Aurora emite 3 comandos:
  1. cmd_A: update_estimate(status="signed") → ConstruPilot
  2. cmd_B: send_email(template="estimate_signed", ...) → ConstruPilot
  3. cmd_C: emit_invoice(type="deposit_30", ...) → ConstruPilot [requires_2fa]

Se cmd_C falhar após 2FA:
  → Aurora envia compensação: cmd_B_revert (marcar email como não enviado, mesmo que já tenha saído)
  → Aurora regista incident em aurora_incidents
```

---

# §6 Requisitos não-funcionais para a Aurora

## 6.1 Service Level Objectives (SLO)

| SLI | Alvo | Janela |
| --- | :-: | :-: |
| Coach IA latency p50 | ≤ 3 s | Rolling 30 dias |
| Coach IA latency p95 | ≤ 12 s | Rolling 30 dias |
| Coach IA latency p99 | ≤ 25 s | Rolling 30 dias |
| Plan analysis latency p95 | ≤ 30 s | Rolling 30 dias |
| Availability (excluindo manutenção anunciada) | 99,5 % mensal | Mensal |
| Erro rate (5xx / total) | ≤ 0,5 % | Rolling 7 dias |
| `text: ""` rate em HTTP 200 | **0 %** (crítico) | Rolling 24 h |
| Idempotência (mesmo `Idempotency-Key` → mesma resposta) | 100 % | Sempre |
| Signature validation success rate | ≥ 99,9 % | Rolling 7 dias |

**Manutenção**: janelas anunciadas com **48 h** de antecedência via e-mail para `noc@construpilot.pt` e canal de estado (`https://status.aurora.internal`).

## 6.2 Rate limits

- **Padrão**: 100 req/min por API key.
- **Burst**: 200 req em 10 s (token bucket).
- **Endpoints pesados** (`/analyze-plan`): 20 req/min.
- Headers obrigatórios em cada resposta:
  ```
  X-RateLimit-Limit: 100
  X-RateLimit-Remaining: 87
  X-RateLimit-Reset: 1739525023
  Retry-After: 60          (só em HTTP 429)
  ```

## 6.3 Endpoint permanente (crítico)

> **⚠️ Bloqueante para produção**: a Aurora **NÃO PODE** ser exposta em `https://<slug>.trycloudflare.com` (Cloudflare Quick Tunnel). Esses tunnels são efémeros — o slug muda a cada reinício. Isto torna impossível o pinning DNS/TLS e a rotação previsível.

**Opções aceitáveis**:

1. **Named tunnel Cloudflare** (permanente) — `api.aurora.<domain>.com` com CNAME estável.
2. **Reverse proxy** (Nginx/Traefik) sobre servidor com IP dedicado.
3. **API Gateway managed** (AWS API Gateway, Cloudflare Workers, GCP API Gateway).

**Requisitos DNS/TLS**:

- Domínio próprio (sub-domínio institucional).
- Certificado TLS emitido por CA reconhecida (Let's Encrypt/DigiCert).
- HSTS ativado (`max-age=31536000; includeSubDomains`).
- TLS 1.3 preferido, TLS 1.2 mínimo. Nunca TLS 1.0/1.1.
- Suporte HTTP/2 obrigatório, HTTP/3 recomendado.

## 6.4 Idempotência

Todos os endpoints POST/PUT **DEVEM** honrar `Idempotency-Key`:

- Chave: string ≤ 128 chars, gerada pelo cliente.
- Janela: 24 horas — repetição da mesma chave dentro da janela devolve **exatamente** a mesma resposta (mesmo `status_code`, mesmo body, mesmo `request_id`).
- Chave em conflito com body diferente → **HTTP 409** `idempotency_key_conflict`.

## 6.5 Traceability

Cada resposta inclui:

- `X-Aurora-Request-Id` (header e no body).
- `X-Aurora-Correlation-Id` (para correlação multi-serviço; segue o valor do request se presente).
- `X-Aurora-Trace-Id` (compatível com OpenTelemetry / W3C Trace Context).

O ConstruPilot **DEVE** ecoar estes headers nas suas próprias respostas se derivadas.

## 6.6 Logging e observabilidade

Aurora exporta métricas em formato **OpenTelemetry OTLP**:

- Endpoint OTLP gRPC: `https://otel.aurora.internal:4317` (mTLS).
- Métricas obrigatórias: latência (histogram), erro rate (counter), rate limit hits (counter).
- Traces: propagação W3C `traceparent` header.

Logs estruturados em **JSON** (uma linha por evento):

```json
{
  "ts": "2026-02-14T10:22:00.123Z",
  "level": "info",
  "service": "aurora-core-company",
  "request_id": "…",
  "correlation_id": "…",
  "route": "POST /ask",
  "duration_ms": 2481,
  "status": 200,
  "model": "claude-sonnet-5"
}
```

**Nunca** logar:

- API keys (nem primeiros 4 chars).
- Signing secrets.
- Payloads de utilizadores (só hashes SHA-256 se for necessário para debug).
- Tokens de sessão.

## 6.7 Compatibilidade retroativa

- Alterações **retro-compatíveis** (adição de campos opcionais): sem aviso obrigatório.
- Alterações **retro-incompatíveis** (renome/remoção de campos, alteração de tipos): aviso **60 dias** + rota `v2` paralela por **12 meses**.
- Depreciações comunicadas via:
  - Header `X-Aurora-Deprecation: version=v1; sunset=2027-06-01`.
  - E-mail para `dev@construpilot.pt`.
  - Página `https://status.aurora.internal/deprecations`.

---

# §7 Segurança

## 7.1 Autenticação HMAC AS1

### 7.1.1 Canonical string

```
AS1
<key_id>
<timestamp_unix_seconds>
<request_id_uuid>
<METHOD_UPPERCASE>
<pathname>
<query_ordered_alphabetically_url_encoded>
<sha256_hex_of_exact_body_bytes>
```

- Todas as linhas separadas por `\n` (LF, não CRLF).
- `key_id` extraído da API key formato `ak_[test|live]_<key_id>_<random>`.
- `timestamp` Unix em segundos (janela ±300 s).
- `request_id` UUIDv4 gerado pelo cliente.
- `query` ordenado por chave alfabeticamente, url-encoded, vazio se não existir.
- `body_hash` SHA-256 hex dos bytes exatos do body (calcular ANTES de qualquer minificação/reformatação).

### 7.1.2 Signature

```
signature = HMAC_SHA256(signing_secret, canonical_string).hex()
```

### 7.1.3 Headers obrigatórios

```
Authorization: Bearer <api_key>
Content-Type: application/json
X-Aurora-Request-Id: <request_id_uuid>
X-Aurora-Signature: AS1 key_id=<key_id> ts=<ts> sig=<signature>
```

### 7.1.4 Rotação de secrets

O ConstruPilot tem `/admin/secrets` (frontend) e `POST /api/admin/secrets/update` (backend) para rotação sem downtime. A Aurora **DEVE**:

- Suportar múltiplas chaves ativas simultaneamente por conta (mínimo 2 para grace period).
- Endpoint `POST /admin/keys/rotate` no lado Aurora (para o cliente iniciar rotação).
- Grace period mínimo: 24 h com ambas as chaves aceites.
- Notificação `X-Aurora-Key-Deprecation: sunset=<iso>` na resposta se a chave usada estiver a ser depreciada.

## 7.2 Webhooks Aurora → ConstruPilot

Todos os webhooks Aurora → ConstruPilot assinam o body com **o mesmo esquema AS1** mas usando `webhook_signing_secret` distinto do secret de API.

Headers:

```
X-Aurora-Signature: AS1 key_id=webhook_kid ts=<ts> sig=<sig>
X-Aurora-Event: aurora.event.v1
X-Aurora-Delivery-Id: <uuid>
```

Retries em falha (HTTP ≠ 2xx): backoff exponencial 1 min → 5 min → 30 min → 2 h → 12 h (5 tentativas totais em 15 h).

## 7.3 CORS

- Aurora **DEVE** restringir CORS a domínios explicitamente registados por API key.
- Registo em `/admin/keys/<kid>/allowed-origins`.
- Nunca `Access-Control-Allow-Origin: *`.

## 7.4 Segurança de logs

- Logs Aurora nunca contêm secrets (§6.6).
- Logs do ConstruPilot também não. Ambos os lados fazem grep `ak_test_\|ak_live_\|AURORA_.*_SECRET` no CI e falham build se detetados.

## 7.5 Rate limit por IP + por API key

- Aurora aplica rate limit **por API key** (§6.2) **E** por IP (baseline 500 req/min por IP para mitigação DDoS).

## 7.6 Proteção contra replay

- `timestamp` fora janela ±300 s → HTTP 401 `signature_expired`.
- `request_id` já visto nas últimas 24 h com mesma assinatura → HTTP 409 `replay_detected`.

## 7.7 Conformidade RGPD

- Dados pessoais de utilizadores ConstruPilot passados à Aurora limitam-se a: `user_id` (opaco), `user_locale`, e-mail apenas se estritamente necessário (avaliado caso a caso).
- Aurora **NÃO** armazena PII em prompts persistentes (só em execução transitória).
- Direito ao esquecimento: ConstruPilot pode invocar `DELETE /api/gateway/v1/aurora-core/company/gdpr/erase?user_id=…` para purga total dos rastos Aurora daquele utilizador (retorno síncrono; propagação < 24 h).
- DPA (Data Processing Agreement) formal a assinar entre partes antes de produção.

---

# §8 Roadmap de integração

## 8.1 Fase 1 · Imediato (0-4 semanas)

**Blocking para produção**.

- ✅ Corrigir `text: ""` em `gpt-5.6-luna` reasoning (root cause do provider).
- ✅ Repor endpoint permanente Aurora (dropping `trycloudflare.com`).
- ✅ Implementar rejeição HTTP 4xx em vez de HTTP 200 vazio.
- ✅ Assinar DPA entre Aurora e ConstruPilot.
- ✅ Documentar Aurora API V1 em `openapi.yaml` público (versão minor).

## 8.2 Fase 2 · Curto prazo (1-3 meses)

- Implementar `POST /analyze-plan` com schema `aurora.company-plan-analysis.v1` (§2.2, §3).
- Suportar upload de imagens (para OCR de plantas rasterizadas / fotos de obra).
- Populate `citations[]` obrigatório em respostas BTP.
- Publicar `openapi.yaml` completo (todos os endpoints V1).

## 8.3 Fase 3 · Médio prazo (3-6 meses)

- Implementar endpoint receptor de comandos Aurora → ConstruPilot (`/api/aurora-callback/execute`, §5.2).
- Implementar mecanismo de aprovação humana (`user_approval_url`).
- Implementar coleção `aurora_actions` com endpoint admin.
- Publicar tool manifest ConstruPilot (`/api/aurora-callback/manifest`, §5.5).
- Implementar `DELETE /gdpr/erase`.

## 8.4 Fase 4 · Longo prazo (6-12 meses)

- Adaptar 2-3 SaaS piloto adicionais (CRM + ERP + …).
- Implementar saga pattern (§5.6).
- Adicionar suporte IFC (BIM) em `/analyze-plan`.
- Introduzir cache determinística para perguntas frequentes com `deterministic: true`.

## 8.5 Fase 5 · Consolidação (12+ meses)

- Cobertura 99 % de operações SaaS conforme §5.5.2.
- SLO 99,9 % (uptime).
- Migração para HTTP/3 e QUIC.
- Introdução de streaming (SSE) opcional para Coach IA.

---

# §9 Anexos

## Anexo A · Exemplo completo request/response Coach

### A.1 Request

```
POST /api/gateway/v1/aurora-core/company/ask
Host: api.aurora.internal
Content-Type: application/json
Authorization: Bearer ak_live_a1b2_c3d4e5f6…
X-Aurora-Request-Id: b3d7e14e-5f92-4b0c-9c8f-7d0f2a1e6a44
X-Aurora-Signature: AS1 key_id=a1b2 ts=1739525023 sig=8f3a…c2b1
Idempotency-Key: idem_2026_02_14_b3d7e14e

{
  "question": "[SISTEMA]\nÉs um assistente especialista em BTP … PT-PT …\n\n[PROJETO_ATUAL]\nNome: Moradia T3 Cascais | Categoria: Reabilitação | Área: 180 m² | Orçamento estimado: 245 000 € | Localização: Cascais\n\n[HISTÓRICO_RECENTE]\n(nova conversa)\n\n[PERGUNTA]\nQual é o pé-direito mínimo em habitação e onde é regulado?",
  "project_id": "prj_9d54b166cd4a",
  "resources": []
}
```

### A.2 Response (200 OK)

```json
{
  "schema": "aurora.company-answer.v1",
  "request_id": "b3d7e14e-5f92-4b0c-9c8f-7d0f2a1e6a44",
  "correlation_id": "c-2026-02-14-8a1e",
  "latency_ms": 2481,
  "model": "claude-sonnet-5",
  "route": "anthropic/claude-sonnet-5",
  "mode": "reasoning",
  "external_ai_used": true,
  "deterministic": false,
  "family": "canonical_intelligence_router",
  "operation": "company.ask",
  "read_only": true,
  "side_effects": false,
  "project_id": "prj_9d54b166cd4a",
  "resources_used": [
    {
      "type": "project",
      "resource_id": "prj_9d54b166cd4a",
      "aurora_entity_id": "entity-4be17db7f33e",
      "excerpt": "Moradia T3 Cascais · 180 m² · orçamento estimado 245 000 €",
      "relevance_score": 0.98
    }
  ],
  "text": "O pé-direito mínimo em habitação é 2,40 m, regulado pelo RGEU (Regulamento Geral das Edificações Urbanas, DL 38 382/1951) no seu Art.º 65.º. Para a sua moradia T3 em Cascais, verifique que todos os compartimentos habitáveis (salas, quartos, cozinha) cumprem este mínimo. Zonas de arrumo e despensa podem ter 2,20 m. Em coberturas inclinadas, a altura mínima aplica-se a pelo menos metade da área útil do compartimento.\n\nReferências normativas:\n• RGEU (DL 38 382/1951) Art.º 65.º — pé-direito mínimo.\n\nAvisos:\n• Confirme o pé-direito real em obra através de levantamento a laser antes de fechar detalhes de projeto.",
  "citations": [
    {
      "type": "norm",
      "jurisdiction": "PT",
      "code": "RGEU",
      "article": "Art.º 65.º",
      "title": "Pé-direito mínimo",
      "url": "https://dre.pt/dre/legislacao-consolidada/decreto-lei/1951-38382"
    }
  ],
  "confidence": 0.94,
  "follow_up_suggestions": [
    "Excepções ao art.º 65.º em reabilitação urbana",
    "Como comprovar o pé-direito num levantamento a laser?"
  ]
}
```

### A.3 Response (503 — Aurora indisponível)

```json
{
  "schema": "aurora.error.v1",
  "error": {
    "code": "service_unavailable",
    "message": "Aurora temporariamente indisponível — janela de manutenção anunciada.",
    "retriable": true,
    "retry_after_seconds": 300,
    "correlation_id": "c-2026-02-14-8a1e",
    "request_id": "b3d7e14e-5f92-4b0c-9c8f-7d0f2a1e6a44",
    "timestamp": "2026-02-14T10:22:00.000Z"
  }
}
```

## Anexo B · Exemplo completo request/response análise plantas

### B.1 Request (excerto)

```
POST /api/gateway/v1/aurora-core/company/analyze-plan
Content-Type: application/json
Authorization: Bearer ak_live_a1b2_…
X-Aurora-Signature: AS1 key_id=a1b2 ts=… sig=…
Idempotency-Key: idem_apla_abc123

{
  "project_id": "prj_9d54b166cd4a",
  "plan_type": "planta_baixa",
  "source": {
    "format": "dxf",
    "extraction": {
      "num_entities": 1247,
      "layers": ["PAREDES","COTAS","PORTAS","JANELAS","MOBILIARIO","EIXOS"],
      "text_samples": ["Sala 45 m²","Cozinha 12 m²","Q1 22 m²","..."],
      "dimensions": ["12.00","15.00","2.40","0.90","..."],
      "bbox": {"width_m": 12.4, "height_m": 15.0},
      "raw_text": "PAREDES: L1 12000, L2 15000, ..."
    }
  },
  "context": {
    "project_type": "reabilitacao_moradia",
    "project_name": "Moradia T3 Cascais",
    "area_declared_m2": 180,
    "budget_declared_eur": 245000,
    "location": {"country": "PT", "region": "Lisboa", "city": "Cascais"},
    "biblioteca_ref": "PT-2026-v1"
  },
  "options": {
    "conformity_checks": ["RGEU","RSCIE","EN_1998_NA_PT"],
    "estimate_pricing": true,
    "language": "pt-PT"
  }
}
```

### B.2 Response (200 OK · resumo)

```json
{
  "schema": "aurora.company-plan-analysis.v1",
  "request_id": "…",
  "correlation_id": "…",
  "latency_ms": 18420,
  "model": "claude-sonnet-5",
  "analysis_id": "apla_abc123",
  "summary": {
    "area_total_m2": 180.4,
    "num_divisions": 8,
    "tipo_obra": "Reabilitação T3 · piso único",
    "escala_detetada": "1:100",
    "unidades_desenho": "metros",
    "confidence": 0.87
  },
  "divisions": [
    { "nome": "Sala comum", "tipo": "sala_estar", "area_m2": 45.2, "confidence": 0.91 },
    { "nome": "Cozinha", "tipo": "cozinha", "area_m2": 15.0, "confidence": 0.90 },
    { "nome": "Quarto suite", "tipo": "quarto", "area_m2": 22.0, "confidence": 0.89 }
  ],
  "elementos_construtivos": [
    { "tipo": "parede", "sub_tipo": "exterior_dupla", "material_estimado": "tijolo_furado_11+iso+tijolo_furado_11", "espessura_m": 0.30, "comprimento_total_m": 42.4, "area_m2": 114.5, "confidence": 0.82 }
  ],
  "estimativa_bom": [
    { "biblioteca_pt_ref": "04.01.02", "categoria": "Alvenarias", "designacao": "Parede dupla em tijolo furado 11+11 cm com isolamento XPS 40 mm", "unidade": "m2", "quantidade": 114.5, "preco_unitario_eur": 62.50, "preco_total_eur": 7156.25, "confidence": 0.85 }
  ],
  "total_estimado_eur": 175430.00,
  "total_estimado_range_eur": {"min": 158000.00, "max": 195000.00},
  "conformidade": {
    "rgeu": { "conforme": true, "artigos_verificados": ["65","73","76"], "observacoes": ["Pé-direito 2,70 m ≥ 2,40 m mínimo — CONFORME"] },
    "eurocodes_aplicaveis": ["EN 1990","EN 1991-1-1","EN 1992-1-1","EN 1996-1-1","EN 1998-1"]
  },
  "avisos": [
    "Cota do pé-direito não visível em 3 divisões — assumido 2,40 m.",
    "Layer 'AVAC' ausente — instalação AVAC estimada por padrão T3."
  ]
}
```

## Anexo C · Exemplo comando Aurora → ConstruPilot

### C.1 Cenário

Utilizador diz no Coach IA: *"Aceita este orçamento e envia por e-mail ao cliente."*

Aurora emite dois comandos em sequência (saga).

### C.2 Comando 1 · `update_estimate`

```
POST https://construpilot.pt/api/aurora-callback/execute
Authorization: Bearer <aurora_service_token>
X-Aurora-Signature: AS1 key_id=… ts=… sig=…
X-Aurora-Request-Id: 8f2a-…
Idempotency-Key: idem_cmd_A_2026_02_14

{
  "schema": "aurora.command.v1",
  "command_id": "cmd_A",
  "correlation_id": "cor_saga_estimate_sign",
  "intent": "update_estimate",
  "target_platform": "construpilot",
  "target_resource": {
    "type": "estimate",
    "id": "est_00c9d4"
  },
  "actor": {
    "type": "user",
    "user_id": "user_f091093",
    "user_locale": "pt-PT"
  },
  "payload": {
    "status": "signed",
    "signed_at": "2026-02-14T10:22:00.000Z",
    "signed_by": "user_f091093"
  },
  "dry_run": false,
  "auto_approve": false,
  "requires_user_confirmation": true,
  "confirmation_deadline_seconds": 900,
  "audit_context": {
    "reason": "Utilizador aceitou orçamento via Coach IA.",
    "aurora_conversation_id": "conv_…"
  }
}
```

### C.3 Resposta ConstruPilot (202 pending_approval)

```json
{
  "schema": "aurora.command-result.v1",
  "command_id": "cmd_A",
  "status": "pending_approval",
  "http_status": 202,
  "user_approval_url": "https://construpilot.pt/aurora-approvals/cmd_A",
  "user_approval_expires_at": "2026-02-14T10:37:00.000Z",
  "audit_log_id": "audit_5f7e",
  "executed_at": null
}
```

Após confirmação humana no ConstruPilot, o estado transita para `executed` e emite webhook `command.executed` para Aurora.

## Anexo D · Tabela de códigos de erro (completa)

### D.1 4xx — erros do cliente

| Código | HTTP | Retriable | Descrição |
| --- | :-: | :-: | --- |
| `bad_request` | 400 | ❌ | Body malformado (não JSON) |
| `not_authenticated` | 401 | ❌ | `Authorization` ausente ou inválido |
| `signature_expired` | 401 | ❌ | `ts` fora janela ±300 s |
| `signature_mismatch` | 401 | ❌ | HMAC não bate certo |
| `signature_missing` | 401 | ❌ | `X-Aurora-Signature` ausente |
| `key_revoked` | 401 | ❌ | API key revogada |
| `forbidden` | 403 | ❌ | Sem escopo para operação |
| `origin_not_allowed` | 403 | ❌ | Origem não registada nos allowed_origins |
| `resource_not_found` | 404 | ❌ | project_id / entity_id / analysis_id não existe |
| `method_not_allowed` | 405 | ❌ | Método HTTP não suportado |
| `not_acceptable` | 406 | ❌ | Cliente exige formato não suportado |
| `idempotency_key_conflict` | 409 | ❌ | Mesma `Idempotency-Key` com body diferente |
| `replay_detected` | 409 | ❌ | `request_id` reutilizado dentro de 24 h |
| `state_conflict` | 409 | ❌ | Recurso em estado incompatível com operação |
| `gone` | 410 | ❌ | Recurso removido permanentemente |
| `precondition_failed` | 412 | ❌ | `If-Match`/etag mismatch |
| `payload_too_large` | 413 | ❌ | Body excede 20 MB |
| `unsupported_media_type` | 415 | ❌ | Não JSON |
| `validation_error` | 422 | ❌ | Body inválido (schema falhou) |
| `insufficient_context` | 422 | ❌ | Sem dados para responder |
| `unprocessable_business_rule` | 422 | ❌ | Regra de negócio violada |
| `rate_limited` | 429 | ✅ | Excedido rate limit — ver `Retry-After` |

### D.2 5xx — erros do servidor

| Código | HTTP | Retriable | Descrição |
| --- | :-: | :-: | --- |
| `internal_error` | 500 | ✅ | Erro interno genérico |
| `handler_error` | 500 | ✅ | Erro específico do handler |
| `not_implemented` | 501 | ❌ | Feature não implementada |
| `upstream_error` | 502 | ✅ | Provider externo (OpenAI/Anthropic) falhou |
| `service_unavailable` | 503 | ✅ | Manutenção ou capacidade esgotada |
| `model_timeout` | 504 | ✅ | Modelo IA timeout |
| `network_timeout` | 504 | ✅ | Timeout rede interna |
| `version_mismatch` | 505 | ❌ | Versão HTTP não suportada |
| `insufficient_storage` | 507 | ❌ | Sem espaço para persistir |
| `loop_detected` | 508 | ❌ | Loop de reencaminhamento |
| `bandwidth_limit_exceeded` | 509 | ✅ | Cota mensal excedida |

### D.3 Códigos específicos Aurora `insufficient_context`

Sub-códigos para orientar o cliente:

| Sub-código | Descrição |
| --- | --- |
| `project_not_found` | `project_id` não foi previamente `upsert`ed |
| `missing_area` | Contexto sem `area_m2` — impossível estimar |
| `missing_budget` | Contexto sem `budget_eur` — impossível verificar realismo |
| `plan_extraction_empty` | Extração DXF/PDF sem entidades úteis |
| `history_too_long` | Histórico excede 32k tokens — cliente deve resumir |
| `unsupported_language` | Idioma não PT/EN/ES/FR/IT/DE |

## Anexo E · Glossário BTP PT-PT

**A**

- **Alvenaria** — parede feita de tijolo, bloco ou pedra assente com argamassa.
- **ARU** — Área de Reabilitação Urbana.
- **ARL** — Arquiteto responsável pela liderança.
- **APO** — Auto de Início dos Trabalhos.
- **AVAC** — Aquecimento, Ventilação e Ar Condicionado.

**B**

- **Betão** — mistura de cimento, agregados e água (PT). "Betão armado" = betão com armaduras de aço.
- **Biblioteca PT 2026** — catálogo canónico ConstruPilot com 800+ items normalizados.
- **BOM** — Bill of Materials, mapa de quantidades.
- **BPU** — Bordereau de Prix Unitaires (mapa preços unitários).

**C**

- **CCP** — Código dos Contratos Públicos.
- **CTE** — Código Técnico de la Edificación (Espanha).
- **CVA / CVN** — Coordenador de Segurança em Obra / na fase de projeto.

**D**

- **DPGF** — Décomposition du Prix Global et Forfaitaire.
- **DTU** — Documents Techniques Unifiés (França).

**E**

- **EC** — Eurocode. EC0-9.
- **EPBD** — Energy Performance of Buildings Directive.
- **E-LNEC** — Especificação Técnica do LNEC.

**F**

- **Forfait** — trabalho a valor global fixo (vg).

**G**

- **GEG** — Gebäudeenergiegesetz (Alemanha).

**I**

- **IFC** — Industry Foundation Classes (BIM).
- **ITED** — Infraestruturas de Telecomunicações em Edifícios.

**L**

- **Laje aligeirada** — laje com blocos de aligeiramento (EPS, tijolo, cerâmicos).
- **LNEC** — Laboratório Nacional de Engenharia Civil.

**N**

- **NP EN** — Norma Portuguesa que transpõe uma norma europeia.
- **NTC** — Norme Tecniche per le Costruzioni (Itália).
- **nZEB** — nearly Zero-Energy Building.

**P**

- **Pé-direito** — altura livre de um compartimento (piso ao teto).
- **PPSST** — Plano Prevenção de Segurança e Saúde no Trabalho.

**Q**

- **QAI** — Qualidade do Ar Interior.

**R**

- **RCCTE** — Regulamento das Características de Comportamento Térmico dos Edifícios (revogado, substituído pelo REH).
- **REH** — Regulamento de Desempenho Energético dos Edifícios de Habitação.
- **RE2020** — Réglementation Environnementale 2020 (França).
- **RGEU** — Regulamento Geral das Edificações Urbanas.
- **RJUE** — Regime Jurídico da Urbanização e Edificação.
- **RSCIE** — Regulamento de Segurança Contra Incêndio em Edifícios.

**S**

- **SCE** — Sistema de Certificação Energética de Edifícios.

**T**

- **T1/T2/T3/T4** — Tipologia habitacional (nº de quartos).

**U**

- **U-value** — Coeficiente de transmissão térmica (W/m²·K).

**V**

- **Vão** — abertura (porta, janela); ou distância entre apoios estruturais.
- **vg** — verba (vago) — unidade forfait.

---

## Notas finais

Este documento é **vinculativo** entre as partes signatárias. Alterações requerem addendum assinado.

Contactos:

- **ConstruPilot** — `dev@construpilot.pt` · `noc@construpilot.pt` · `dpo@construpilot.pt`
- **Aurora** — a definir na assinatura do DPA.

**Fim do documento.**

"""Catálogo do Dossier de Obra: áreas, especialidades, fases, etapas e tipos de relação.

Esta estrutura organiza a EXPERIÊNCIA do produto. Não é uma classificação legal universal
nem define responsabilidades profissionais (aviso apresentado também na interface).
Fonte única: o frontend obtém o catálogo por GET /api/dossier-obra/catalogo.
"""
from __future__ import annotations

import unicodedata

DISCLAIMER = ("Organização de trabalho do ConstruPilot. Não constitui classificação legal nem "
              "definição de responsabilidades profissionais.")

# (chave, rótulo, descrição curta em linguagem corrente, ícone lucide)
AREAS = [
    ("arquitetura", "Arquitetura e elementos construtivos",
     "Tudo o que dá forma à casa: espaços, paredes, fachadas, revestimentos, portas e janelas.", "Building2"),
    ("engenharia", "Engenharia e instalações",
     "O que a mantém de pé e a faz funcionar: estrutura, água, esgotos, eletricidade, climatização.", "Cog"),
    ("preparacao", "Preparação, licenciamento e segurança",
     "O que vem antes e à volta da obra: papéis, terreno, estaleiro, segurança e resíduos.", "HardHat"),
    ("gestao", "Gestão e execução",
     "Organizar a obra: planeamento, equipas, compras, custos, autos e registos.", "CalendarRange"),
    ("entrega", "Entrega e manutenção",
     "Fechar bem a obra: inspeções, receção, telas finais, garantias e manutenção.", "ShieldCheck"),
]

# (chave, área, rótulo, descrição simples, exemplos, termos de pesquisa)
_S = [
    # A — Arquitetura
    ("implantacao", "arquitetura", "Implantação, plantas e espaços", "Onde a casa fica no terreno e como se organizam as divisões.",
     ["Planta do rés-do-chão", "Áreas por divisão"], "planta implantacao divisoes areas layout compartimentos espaco"),
    ("paredes", "arquitetura", "Paredes e divisórias", "Paredes exteriores e interiores, em alvenaria, pladur ou outros.",
     ["Parede de tijolo de 15", "Divisória em pladur"], "parede alvenaria tijolo bloco pladur gesso cartonado tabique divisoria"),
    ("revest_exteriores", "arquitetura", "Fachadas e revestimentos exteriores", "O que reveste a casa por fora: reboco, cerâmica, ETICS, pedra.",
     ["Cerâmica exterior na fachada norte", "Capoto (ETICS)"], "fachada revestimento exterior ceramica azulejo etics capoto reboco pedra granito"),
    ("revest_interiores", "arquitetura", "Revestimentos interiores", "Revestimentos de paredes interiores: azulejo, estuque, reboco.",
     ["Azulejo da casa de banho"], "revestimento interior azulejo estuque reboco interior"),
    ("pavimentos", "arquitetura", "Pavimentos e rodapés", "O chão de cada divisão e os rodapés.",
     ["Soalho flutuante na sala", "Mosaico na cozinha"], "pavimento chao piso soalho flutuante mosaico ceramico rodape betonilha"),
    ("coberturas", "arquitetura", "Coberturas", "O telhado ou a cobertura plana, com isolamento e impermeabilização.",
     ["Telha cerâmica", "Cobertura plana invertida"], "cobertura telhado telha terraco cobertura plana caleira"),
    ("tetos", "arquitetura", "Tetos e tetos falsos", "Tetos estucados ou falsos (pladur, placas).",
     ["Teto falso na cozinha"], "teto falso pladur sanca estuque teto"),
    ("caixilharias", "arquitetura", "Portas, janelas e caixilharias", "Portas, janelas, estores e caixilharia.",
     ["Janela de alumínio com corte térmico"], "porta janela caixilharia aluminio pvc estore vidro duplo"),
    ("carpintarias", "arquitetura", "Carpintarias", "Portas interiores, roupeiros, rodapés de madeira, móveis fixos.",
     ["Roupeiro embutido"], "carpintaria madeira roupeiro porta interior movel cozinha"),
    ("serralharias", "arquitetura", "Serralharias", "Guardas, gradeamentos, portões e elementos metálicos.",
     ["Guarda de varanda em inox"], "serralharia guarda corrimao gradeamento portao metal inox ferro"),
    ("pinturas", "arquitetura", "Pinturas e acabamentos", "Pinturas interiores e exteriores e acabamentos finais.",
     ["Pintura das paredes interiores"], "pintura tinta acabamento verniz esmalte"),
    ("acessibilidade", "arquitetura", "Acessibilidade", "Percursos, rampas e dimensões para mobilidade condicionada.",
     ["Rampa de acesso"], "acessibilidade rampa mobilidade condicionada dl 163/2006"),
    ("arranjos_exteriores", "arquitetura", "Arranjos exteriores", "Jardim, muros de vedação, pavimentos exteriores, piscina.",
     ["Muro de vedação", "Calçada"], "arranjos exteriores jardim muro vedacao calcada piscina exterior"),
    # B — Engenharia
    ("levantamentos", "engenharia", "Levantamentos e geotecnia", "Levantamento topográfico e estudo do solo.",
     ["Levantamento topográfico"], "levantamento topografico geotecnia solo sondagem"),
    ("estruturas", "engenharia", "Estruturas e fundações", "Fundações, pilares, vigas e lajes.",
     ["Sapatas", "Laje do piso 1"], "estrutura fundacao sapata pilar viga laje betao armado aco"),
    ("contencoes", "engenharia", "Contenções e muros de suporte", "Muros que seguram terras e contenções periféricas.",
     ["Muro de suporte nascente"], "contencao muro suporte talude escavacao"),
    ("agua", "engenharia", "Abastecimento de água", "Rede de água fria e ligações ao contador.",
     ["Rede de água da casa de banho"], "agua abastecimento canalizacao rede agua fria contador multicamada ppr"),
    ("residuais", "engenharia", "Águas residuais", "Esgotos: sanitas, lava-loiças, caixas de visita.",
     ["Esgoto da cozinha"], "esgoto aguas residuais saneamento caixa visita tubo pvc"),
    ("pluviais", "engenharia", "Águas pluviais", "Escoamento da chuva: caleiras, tubos de queda, drenagem.",
     ["Tubos de queda"], "pluviais chuva caleira tubo queda drenagem"),
    ("eletricidade", "engenharia", "Eletricidade", "Quadro, circuitos, tomadas e iluminação.",
     ["Quadro elétrico", "Tomadas da cozinha"], "eletricidade electricidade quadro tomada circuito iluminacao rtiebt cabo"),
    ("ited", "engenharia", "Telecomunicações e ITED", "Rede de telecomunicações, fibra e televisão.",
     ["ATI e tomadas RJ45"], "telecomunicacoes ited fibra rj45 ati tv internet"),
    ("climatizacao", "engenharia", "Climatização e ventilação", "Aquecimento, ar condicionado, VMC e extração.",
     ["Bomba de calor", "Ventilação da casa de banho"], "climatizacao ventilacao vmc ar condicionado bomba calor aquecimento piso radiante"),
    ("aqs", "engenharia", "Águas quentes sanitárias", "Produção e rede de água quente.",
     ["Termoacumulador"], "agua quente aqs termoacumulador esquentador caldeira"),
    ("gas", "engenharia", "Gás, quando aplicável", "Rede de gás e ligação aos aparelhos.",
     ["Rede de gás natural"], "gas rede gas natural propano"),
    ("termica", "engenharia", "Térmica e energia", "Isolamento térmico e desempenho energético.",
     ["Pré-certificado energético"], "termica energia isolamento reh certificado energetico pontes termicas"),
    ("acustica", "engenharia", "Acústica", "Isolamento a ruído entre espaços e do exterior.",
     ["Isolamento entre frações"], "acustica ruido isolamento sonoro rrae"),
    ("incendio", "engenharia", "Segurança contra incêndio", "Medidas de segurança contra incêndio.",
     ["Extintores e sinalização"], "incendio scie extintor sinalizacao evacuacao"),
    ("solar", "engenharia", "Sistemas solares e fotovoltaicos", "Painéis solares térmicos e fotovoltaicos.",
     ["Painéis fotovoltaicos na cobertura"], "solar fotovoltaico painel pv termico autoconsumo"),
    ("domotica", "engenharia", "Automação e domótica", "Comandos automáticos, estores e iluminação inteligentes.",
     ["Estores motorizados"], "domotica automacao casa inteligente knx"),
    ("especiais", "engenharia", "Instalações especiais e equipamentos", "Elevadores, piscinas técnicas e outros equipamentos.",
     ["Elevador"], "instalacoes especiais equipamentos elevador piscina"),
    # C — Preparação
    ("administrativo", "preparacao", "Documentação e procedimentos administrativos", "Licenças, comunicações e documentos oficiais.",
     ["Comunicação prévia"], "licenca licenciamento camara alvara comunicacao previa rjue documentacao"),
    ("terreno", "preparacao", "Preparação do terreno", "Limpeza, desmatação e movimentos de terras.",
     ["Escavação"], "terreno limpeza desmatacao escavacao aterro movimento terras"),
    ("estaleiro", "preparacao", "Estaleiro e acessos", "Montagem do estaleiro, vedação e acessos.",
     ["Plano de estaleiro"], "estaleiro acesso vedacao grua contentor"),
    ("demolicoes", "preparacao", "Demolições e desmontagens", "O que é preciso demolir ou retirar.",
     ["Demolição de divisória"], "demolicao desmontagem remocao"),
    ("seguranca", "preparacao", "Segurança e saúde", "Plano de segurança e saúde, equipamentos e medidas.",
     ["PSS", "Andaimes"], "seguranca saude pss epi andaime coordenacao"),
    ("residuos", "preparacao", "Resíduos", "Gestão de resíduos de construção e demolição.",
     ["Plano de resíduos (PPG)"], "residuos rcd ppg contentor entulho"),
    ("provisorios", "preparacao", "Trabalhos provisórios e condicionantes", "Escoramentos, proteções e condicionantes da obra.",
     ["Escoramento"], "provisorio escoramento protecao condicionante"),
    # D — Gestão
    ("planeamento", "gestao", "Planeamento e dependências", "Sequência dos trabalhos e prazos.",
     ["Gantt da obra"], "planeamento gantt prazo sequencia dependencias cronograma"),
    ("equipas", "gestao", "Equipas e subempreiteiros", "Quem faz o quê na obra.",
     ["Subempreiteiro de canalização"], "equipa subempreiteiro mao de obra trabalhadores"),
    ("compras", "gestao", "Materiais, consultas e compras", "Pedidos de preço, encomendas e entregas.",
     ["Consulta a fornecedores"], "materiais compras encomenda fornecedor consulta preco entrega"),
    ("custos", "gestao", "Orçamento e custos", "Orçamento, custos reais e margem.",
     ["Orçamento aceite"], "orcamento custo margem preco"),
    ("autos", "gestao", "Medições e autos", "Medições de trabalhos executados e autos de medição.",
     ["Auto n.º 2"], "auto medicao situacao trabalhos executados faturacao"),
    ("alteracoes", "gestao", "Alterações e trabalhos adicionais", "Trabalhos a mais, a menos e alterações.",
     ["Trabalho a mais na cozinha"], "alteracao trabalhos a mais adicionais variante"),
    ("diario", "gestao", "Diário de obra e fotografias", "Registo diário e fotografias da obra.",
     ["Fotografias da semana"], "diario obra fotografias registo relatorio visita"),
    ("qualidade", "gestao", "Qualidade, verificações e ensaios", "Verificações, ensaios e não conformidades.",
     ["Ensaio de estanquidade"], "qualidade verificacao ensaio controlo nao conformidade"),
    ("comunicacoes", "gestao", "Comunicações e decisões", "Atas, e-mails e decisões tomadas.",
     ["Ata de reunião"], "comunicacao decisao ata reuniao email"),
    # E — Entrega
    ("inspecoes", "entrega", "Inspeções e pendências", "Vistorias finais e lista de pendências.",
     ["Vistoria final"], "inspecao vistoria pendencias reservas"),
    ("rececao", "entrega", "Receção", "Receção provisória e definitiva da obra.",
     ["Auto de receção provisória"], "rececao recepcao provisoria definitiva entrega"),
    ("telas_finais", "entrega", "Telas finais e documentação técnica", "Desenhos finais como construído.",
     ["Telas finais de arquitetura"], "telas finais como construido documentacao tecnica"),
    ("manuais", "entrega", "Manuais e garantias", "Manuais dos equipamentos e garantias.",
     ["Garantia da caixilharia"], "manual garantia equipamento"),
    ("manutencao", "entrega", "Plano de manutenção", "O que verificar e quando, depois da entrega.",
     ["Limpeza anual das caleiras"], "manutencao plano conservacao"),
    ("dossier_final", "entrega", "Dossier final", "Compilação do dossier entregue ao dono de obra.",
     ["Compilação técnica da obra"], "dossier final compilacao tecnica entrega"),
]

SPECIALTIES = {k: {"key": k, "area": a, "label": lab, "description": d, "examples": ex, "terms": t, "custom": False}
               for k, a, lab, d, ex, t in _S}

# Fases globais da obra (uma por obra) — distintas da etapa de cada trabalho e do estado de cada tarefa.
PHASES = [
    ("estudo", "Estudo e projeto"), ("licenciamento", "Licenciamento"), ("preparacao", "Preparação"),
    ("execucao", "Execução"), ("rececao", "Receção"), ("manutencao", "Manutenção"),
]
PHASE_KEYS = [k for k, _ in PHASES]

# Etapas do trabalho numa especialidade.
STAGES = [("preparar", "Preparar"), ("medir", "Medir"), ("orcamentar", "Orçamentar"), ("executar", "Executar"), ("validar", "Validar")]
STAGE_KEYS = [k for k, _ in STAGES]

SPECIALTY_STATUS = {"por_iniciar": "Por iniciar", "em_preparacao": "Em preparação", "em_curso": "Em curso",
                    "a_validar": "A validar", "validado": "Validado", "nao_aplicavel": "Não aplicável"}
TASK_STATUS = {"por_fazer": "Por fazer", "em_curso": "Em curso", "pendente": "Pendente", "bloqueado": "Bloqueado",
               "concluido": "Concluído", "nao_aplicavel": "Não aplicável"}
ITEM_KINDS = {"tarefa": "Tarefa", "pendencia": "Pendência", "verificacao": "Verificação", "medicao": "Medição",
              "material": "Material", "registo": "Registo", "documento": "Documento", "alteracao": "Alteração", "nota": "Nota"}
SOURCES = {"extraido": "Extraído de documento", "manual": "Introduzido manualmente", "inferido": "Inferido (a confirmar)"}
VALIDATION = {"por_confirmar": "Por confirmar", "confirmado": "Confirmado", "corrigido": "Corrigido",
              "rejeitado": "Rejeitado", "validado": "Validado"}
RELATIONS = {"depende_de": "Depende de", "verificar_antes_de": "Deve ser verificado antes de",
             "partilha_com": "Partilha informação com", "pode_afetar": "Pode afetar"}
# Quantidades distintas ao longo da cadeia medição → orçamento → compra → execução → auto → faturação.
QUANTITY_KINDS = [("medida", "Medida"), ("orcamentada", "Orçamentada"), ("compra", "Necessária para compra"),
                  ("encomendada", "Encomendada"), ("recebida", "Recebida"), ("executada", "Executada"),
                  ("validada_auto", "Validada para auto"), ("faturada", "Faturada")]
QUANTITY_KEYS = [k for k, _ in QUANTITY_KINDS]
LOCATION_KINDS = {"edificio": "Edifício", "piso": "Piso", "zona": "Divisão ou zona"}

SECTIONS = [("plantas", "Plantas e documentos"), ("camadas", "Elementos e camadas"), ("medicoes", "Medições e quantidades"),
            ("custos", "Orçamento e custos"), ("materiais", "Materiais e fichas técnicas"), ("tarefas", "Tarefas e planeamento"),
            ("registos", "Fotografias e registos"), ("verificacoes", "Verificações e validações"),
            ("historico", "Alterações e histórico"), ("relatorio", "Relatório da especialidade")]

# Sequências típicas PROPOSTAS (nunca aplicadas sem confirmação do responsável da obra).
SUGGESTED_DEPENDENCIES = [
    ("agua", "verificar_antes_de", "paredes", "Verificar a rede de água antes do fecho das paredes."),
    ("residuais", "verificar_antes_de", "paredes", "Verificar a rede de esgotos antes do fecho das paredes."),
    ("eletricidade", "verificar_antes_de", "paredes", "Verificar tubagens e caixas elétricas antes do fecho das paredes."),
    ("agua", "verificar_antes_de", "revest_interiores", "Ensaio de estanquidade antes dos revestimentos interiores."),
    ("revest_interiores", "depende_de", "paredes", "Os revestimentos interiores dependem das paredes concluídas."),
    ("revest_exteriores", "depende_de", "paredes", "O revestimento da fachada depende do suporte executado."),
    ("revest_exteriores", "partilha_com", "termica", "Revestimento exterior e isolamento térmico partilham a composição da fachada."),
    ("pavimentos", "depende_de", "climatizacao", "Piso radiante/tubagens antes da betonilha e do pavimento."),
    ("pinturas", "depende_de", "revest_interiores", "Pinturas depois dos revestimentos e estuques."),
    ("estruturas", "pode_afetar", "paredes", "Alterações estruturais podem afetar paredes e aberturas."),
    ("caixilharias", "partilha_com", "termica", "Caixilharia e térmica partilham coeficientes e pontes térmicas."),
    ("coberturas", "depende_de", "estruturas", "A cobertura depende da estrutura de suporte."),
]


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def search(query: str, specialties: dict | None = None) -> list[dict]:
    """Pesquisa por termos técnicos e linguagem corrente (sem acentos, por palavras)."""
    pool = specialties or SPECIALTIES
    words = [w for w in norm(query).split() if len(w) > 1]
    if not words:
        return []
    out = []
    for s in pool.values():
        hay = norm(" ".join([s["label"], s.get("description", ""), s.get("terms", ""), " ".join(s.get("examples", []))]))
        score = sum(3 if w in norm(s["label"]) else 1 for w in words if w in hay)
        if score:
            out.append((score, s))
    out.sort(key=lambda x: -x[0])
    return [s for _, s in out[:20]]


def public_catalog() -> dict:
    return {
        "disclaimer": DISCLAIMER,
        "areas": [{"key": k, "label": lab, "description": d, "icon": i,
                   "specialties": [s for s in SPECIALTIES.values() if s["area"] == k]} for k, lab, d, i in AREAS],
        "phases": [{"key": k, "label": lab} for k, lab in PHASES],
        "stages": [{"key": k, "label": lab} for k, lab in STAGES],
        "specialty_status": SPECIALTY_STATUS, "task_status": TASK_STATUS, "item_kinds": ITEM_KINDS,
        "sources": SOURCES, "validation": VALIDATION, "relations": RELATIONS,
        "quantity_kinds": [{"key": k, "label": lab} for k, lab in QUANTITY_KINDS],
        "location_kinds": LOCATION_KINDS, "sections": [{"key": k, "label": lab} for k, lab in SECTIONS],
    }

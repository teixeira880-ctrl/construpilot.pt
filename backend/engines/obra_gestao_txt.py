"""Textos e referenciais do módulo «Gestão de obra» — versão Portugal (pt-PT, 3.ª pessoa formal).

O motor (engines/obra_gestao.py) e a API (routes/obra_gestao.py) são idênticos no .pt e no .fr;
só este ficheiro muda: textos, listas de verificação, tipos de registo e lembretes legais do país.
"""
from __future__ import annotations

LANG = "pt"
PAIS = "PT"

# ------------------------------------------------------------------ mensagens da API
T = {
    "perfil_recusado": "O seu perfil nesta obra não permite esta ação.",
    "nao_encontrado": "Registo não encontrado.",
    "diario_existe": "Já existe uma entrada no diário para este dia. Abra-a para a completar.",
    "diario_assinado": "Esta entrada já está assinada: já não pode ser alterada. Acrescente um aditamento.",
    "diario_sem_assinatura": "Desenhe a assinatura antes de assinar.",
    "diario_data": "Data inválida (formato AAAA-MM-DD).",
    "diario_futuro": "Não é possível abrir o diário de um dia futuro.",
    "diario_nao_assinado": "Só uma entrada assinada pode receber o visto da fiscalização.",
    "imagem_invalida": "Imagem inválida.",
    "foto_limite": "Máximo de 30 fotografias por registo.",
    "qse_fechar_acoes": "Feche primeiro todas as ações (verificadas) ou indique a justificação do fecho.",
    "qse_fechado": "Este registo está fechado.",
    "acao_campos": "Plano de ação incompleto (5W2H): falta {campos}.",
    "acao_estado": "Transição de estado inválida para esta ação.",
    "acao_so_responsavel": "Só a empresa responsável ou a direção de obra pode atualizar esta ação.",
    "rfi_fechado": "Este pedido de esclarecimento está fechado.",
    "rfi_nao_destinatario": "Só o destinatário do pedido (ou a direção de obra) pode responder.",
    "stock_negativo": "Saída superior ao stock disponível de «{material}» ({saldo} {unidade}).",
    "stock_qtd": "Quantidade inválida.",
    "encomenda_estado": "Só uma encomenda enviada ou confirmada pode ser rececionada.",
    "encomenda_nao_encontrada": "Encomenda não encontrada nesta obra.",
    "rececao_excesso": "Quantidade rececionada superior à encomendada na linha {linha} («{material}»). Indique o motivo na nota.",
    "webhook_url": "O endereço tem de começar por https:// e apontar para um servidor público.",
    "webhook_limite": "Máximo de 5 webhooks por empresa.",
    "ia_indisponivel": "O assistente de IA está momentaneamente indisponível: segue o resumo calculado a partir dos dados da obra.",
    "pergunta_vazia": "Escreva a sua pergunta.",
    "armazenamento": "O armazenamento de ficheiros está indisponível. Tente novamente.",
    "versao": "O registo foi alterado entretanto. Recarregue a página.",
}

# ------------------------------------------------------------------ meteorologia (códigos WMO do Open-Meteo)
METEO = {
    0: "Céu limpo", 1: "Pouco nublado", 2: "Parcialmente nublado", 3: "Encoberto",
    45: "Nevoeiro", 48: "Nevoeiro com geada", 51: "Chuvisco fraco", 53: "Chuvisco", 55: "Chuvisco forte",
    56: "Chuvisco gelado", 57: "Chuvisco gelado forte", 61: "Chuva fraca", 63: "Chuva", 65: "Chuva forte",
    66: "Chuva gelada", 67: "Chuva gelada forte", 71: "Neve fraca", 73: "Neve", 75: "Neve forte", 77: "Grãos de neve",
    80: "Aguaceiros fracos", 81: "Aguaceiros", 82: "Aguaceiros fortes", 85: "Aguaceiros de neve", 86: "Aguaceiros de neve fortes",
    95: "Trovoada", 96: "Trovoada com granizo", 99: "Trovoada forte com granizo",
}
METEO_ALERTA = "Condições que podem afetar os trabalhos ao ar livre (betonagens, coberturas, gruas)."

# ------------------------------------------------------------------ qualidade, ambiente e segurança
QSE_TIPOS = {
    "inspecao": "Inspeção / lista de verificação",
    "nao_conformidade": "Não conformidade",
    "incidente": "Acidente de trabalho",
    "quase_acidente": "Quase-acidente / situação perigosa",
    "dialogo_seguranca": "Diálogo de segurança (DDS)",
    "epi": "Verificação de EPI",
    "ambiente": "Ocorrência ambiental",
}
GRAVIDADE = {"baixa": "Baixa", "media": "Média", "alta": "Alta", "critica": "Crítica"}
QSE_ESTADOS = {"aberto": "Aberto", "em_tratamento": "Em tratamento", "fechado": "Fechado"}
ACAO_ESTADOS = {"aberta": "Aberta", "em_curso": "Em curso", "feita": "Feita (a verificar)", "verificada": "Verificada"}
CAMPOS_5W2H = {"o_que": "o quê", "porque": "porquê", "quem": "quem", "onde": "onde", "quando": "quando",
               "como": "como", "quanto": "quanto custa"}

LEMBRETES = {
    "incidente": "Acidente grave ou mortal: comunicar à ACT (Autoridade para as Condições do Trabalho) nas 24 horas e "
                 "participar à seguradora de acidentes de trabalho. Preservar o local até à chegada das autoridades.",
    "quase_acidente": "Registe a causa e a medida imediata: um quase-acidente tratado evita o acidente seguinte.",
    "nao_conformidade": "Defina o plano de ação (5W2H) e quem verifica a eficácia antes de fechar.",
    "dialogo_seguranca": "Indique o tema, os participantes e as medidas combinadas. Ligue o DDS ao Plano de Segurança e Saúde (PSS).",
    "epi": "Capacete, calçado de segurança, colete refletor, luvas e proteção auditiva/ocular conforme a tarefa e o PSS.",
}

EPI_ITENS = ["Capacete", "Calçado de segurança", "Colete refletor", "Luvas", "Óculos de proteção",
             "Proteção auditiva", "Arnês e linha de vida (trabalhos em altura)", "Máscara / proteção respiratória"]

DDS_TEMAS = ["Trabalhos em altura e guarda-corpos", "Movimentação de cargas e gruas", "Escavações e entivação",
             "Riscos elétricos", "Ferramentas manuais e elétricas", "Ordem e limpeza do estaleiro",
             "Produtos químicos (fichas de dados de segurança)", "Calor, frio e hidratação", "Ruído e poeiras",
             "Circulação de máquinas e peões"]

# Listas de verificação por tipo de obra e fase. Cada ponto é verificado ok / não ok / não aplicável.
CHECKLISTS = {
    "estaleiro": {"label": "Estaleiro e segurança geral", "itens": [
        "Vedação do estaleiro contínua e sinalizada", "Placa de identificação da obra e alvará afixados",
        "Comunicação prévia / PSS disponível em obra", "Acessos e circulação de peões separados das máquinas",
        "Instalações sociais (vestiários, sanitários, refeitório) limpas", "Quadro elétrico de obra com diferencial e fechado",
        "Extintores verificados e sinalizados", "Kit de primeiros socorros completo",
        "Guarda-corpos em bordaduras e aberturas", "Andaimes montados e verificados (ficha de verificação)",
        "Resíduos triados (RCD) e contentores identificados", "Registo de entradas no estaleiro atualizado"]},
    "fundacoes": {"label": "Fundações e movimento de terras", "itens": [
        "Implantação verificada contra o projeto (cotas e alinhamentos)", "Taludes ou entivação adequados à profundidade",
        "Fundo das escavações limpo e sem água", "Betão de limpeza executado",
        "Armaduras conformes com o projeto (diâmetros, espaçamentos, recobrimentos)", "Espaçadores colocados",
        "Guia de remessa do betão conferida (classe, exposição, slump)", "Provetes de betão recolhidos",
        "Impermeabilização / drenagem conforme o projeto"]},
    "estrutura": {"label": "Estrutura (betão armado)", "itens": [
        "Cofragens estáveis, estanques e escoradas", "Armaduras conformes (diâmetros, amarrações, emendas)",
        "Recobrimentos garantidos por espaçadores", "Negativos e atravessamentos posicionados antes da betonagem",
        "Classe do betão conforme a guia de remessa", "Vibração e cura do betão asseguradas",
        "Prazos de descofragem respeitados", "Tolerâncias geométricas verificadas (prumo, nível)"]},
    "alvenarias": {"label": "Alvenarias e paredes", "itens": [
        "Primeira fiada nivelada e com corte de capilaridade", "Juntas preenchidas e desencontradas",
        "Ligação às estruturas (ferros de espera / conectores)", "Vergas e padieiras sobre os vãos",
        "Prumo e esquadria verificados", "Isolamento térmico contínuo (pontes térmicas tratadas)"]},
    "cobertura": {"label": "Cobertura", "itens": [
        "Linha de vida / proteção coletiva instalada", "Inclinação e escoamento conformes",
        "Impermeabilização com remates e sobreposições corretos", "Rufos e caleiras estanques",
        "Isolamento térmico contínuo", "Ventilação da cobertura assegurada"]},
    "redes": {"label": "Redes (águas, esgotos, eletricidade, AVAC)", "itens": [
        "Traçados conformes ao projeto", "Ensaio de estanquidade da rede de águas registado",
        "Ensaio da rede de esgotos registado", "Pendentes dos esgotos verificadas",
        "Circuitos elétricos identificados no quadro", "Terra de proteção medida", "Atravessamentos selados (corta-fogo)"]},
    "acabamentos": {"label": "Acabamentos", "itens": [
        "Suportes secos e planos antes do revestimento", "Juntas de dilatação respeitadas",
        "Cerâmicos alinhados e sem ocos", "Pinturas uniformes, sem escorridos",
        "Caixilharias estanques, vedadas e a funcionar", "Proteção dos acabamentos já executados",
        "Limpeza final"]},
    "lsf_clt": {"label": "Construção leve (LSF / CLT)", "itens": [
        "Elementos entregues conformes ao plano de montagem", "Ancoragens à fundação conformes ao projeto",
        "Painéis e perfis protegidos da chuva", "Ligações aparafusadas com o tipo e o número de parafusos do projeto",
        "Barreira pára-vapor contínua", "Proteção contra o fogo conforme o projeto"]},
}

TIPOS_OBRA = {
    "moradia": ["estaleiro", "fundacoes", "estrutura", "alvenarias", "cobertura", "redes", "acabamentos"],
    "edificio": ["estaleiro", "fundacoes", "estrutura", "alvenarias", "cobertura", "redes", "acabamentos"],
    "reabilitacao": ["estaleiro", "estrutura", "alvenarias", "cobertura", "redes", "acabamentos"],
    "construcao_leve": ["estaleiro", "fundacoes", "lsf_clt", "cobertura", "redes", "acabamentos"],
}
TIPOS_OBRA_LABEL = {"moradia": "Moradia", "edificio": "Edifício", "reabilitacao": "Reabilitação",
                    "construcao_leve": "Construção leve (LSF / CLT)"}

# ------------------------------------------------------------------ pedidos de esclarecimento
RFI_ESTADOS = {"aberto": "Aberto", "respondido": "Respondido", "fechado": "Fechado"}
RFI_PREFIXO = "PE"   # Pedido de Esclarecimento

# ------------------------------------------------------------------ alertas
ALERTAS = {
    "tarefa_atraso": "Tarefa «{nome}» atrasada {dias} dia(s)",
    "tarefa_critica": "Tarefa crítica «{nome}» deveria ter começado a {data}",
    "lote_derrapagem": "Lote «{lote}»: custo real {real} € acima do custo previsto {prev} € (+{pct} %)",
    "nc_atraso": "Não conformidade n.º {numero} «{titulo}»: ação «{acao}» em atraso desde {data}",
    "nc_critica": "Não conformidade crítica em aberto: n.º {numero} «{titulo}»",
    "acidente": "Acidente de trabalho registado a {data}: «{titulo}»",
    "rfi_atraso": "Pedido {numero} «{assunto}» sem resposta desde {prazo}",
    "stock_minimo": "Stock de «{material}» abaixo do mínimo ({saldo} {unidade} < {minimo})",
    "diario_em_falta": "Diário de obra sem entrada nos últimos {dias} dias úteis",
    "doc_sub_expira": "Documento «{doc}» da empresa {empresa} expira a {data}",
}
SEV = {"critica": "Crítica", "alta": "Alta", "media": "Média", "info": "Informação"}

# ------------------------------------------------------------------ curva S
CURVA = {
    "sem_planeamento": "Sem planeamento na obra: crie o planeamento (Gantt) para obter a curva prevista.",
    "sem_datas": "O planeamento não tem datas calculadas.",
    "ponderacao_custo": "Ponderação pelo custo previsto de cada lote (orçamento da obra).",
    "ponderacao_duracao": "Sem orçamento por lote ligado às tarefas: ponderação pela duração das tarefas.",
    "custos_incompletos": "Custos reais incompletos (taxa horária em falta ou compras sem preço): a curva dos custos reais não é mostrada.",
    "sem_orcamento": "Sem orçamento de venda válido: a curva dos custos não pode ser comparada ao orçamento.",
}

# ------------------------------------------------------------------ copiloto e relatórios
COPILOTO_SISTEMA = (
    "É o copiloto de obra do ConstruPilot. Responde em português de Portugal, na 3.ª pessoa formal, de forma clara e curta. "
    "Usa APENAS os dados da obra fornecidos em JSON. Se a informação não estiver nos dados, diz que não consta e indica "
    "onde a registar. Nunca inventa números, datas, nomes nem custos. Cita a data ou o número do registo quando o usar."
)
RESUMO_SISTEMA = (
    "É o diretor de obra que redige o resumo semanal para o dono de obra, em português de Portugal (3.ª pessoa formal). "
    "Usa APENAS os dados fornecidos em JSON. Estrutura: 1) Avanço e trabalhos realizados, 2) Qualidade e segurança, "
    "3) Pedidos e decisões pendentes, 4) Prazos e custos, 5) Próximos passos. Máximo 250 palavras. Não inventa nada."
)
ANALISE_FOTO_SISTEMA = (
    "É técnico de segurança e qualidade em obra. Analisa a fotografia e devolve APENAS JSON válido, em português de Portugal: "
    '{"perigos": ["perigo visível e porquê"], "nao_conformidades": ["defeito de execução visível"], '
    '"medidas": ["medida imediata recomendada"], "gravidade": "baixa|media|alta|critica", "confianca": "baixa|media|alta"}. '
    "Só descreve o que se vê na imagem; se nada for visível, devolve listas vazias. Nunca inventa medidas nem normas."
)
RELATORIO = {
    "titulo": "Relatório semanal de obra",
    "kicker": "ACOMPANHAMENTO DE OBRA",
    "semana": "Semana de {de} a {ate}",
    "avanco": "Avanço e trabalhos realizados",
    "qse": "Qualidade e segurança",
    "rfi": "Pedidos de esclarecimento",
    "alertas": "Alertas",
    "resumo": "Síntese",
    "meteo": "Meteorologia",
    "efetivo": "Efetivo",
    "sem_registos": "Sem registos nesta semana.",
    "dias_diario": "{n} dia(s) com diário de obra · {h} h de trabalho registadas · {f} fotografia(s)",
    "nc_abertas": "{n} não conformidade(s) em aberto · {i} acidente(s) · {q} quase-acidente(s) · {d} diálogo(s) de segurança",
    "rfi_abertos": "{n} pedido(s) em aberto, {a} em atraso",
    "fonte": "Documento gerado a partir dos registos da obra no ConstruPilot. Nenhum valor foi estimado.",
}
DIARIO_PDF = {
    "titulo": "Diário de obra",
    "kicker": "LIVRO DE OBRA",
    "data": "Data",
    "meteo": "Meteorologia",
    "efetivo": "Efetivo em obra",
    "trabalhos": "Trabalhos realizados",
    "ocorrencias": "Ocorrências",
    "entregas": "Entregas de materiais",
    "visitas": "Visitas e reuniões",
    "observacoes": "Observações",
    "aditamentos": "Aditamentos (após assinatura)",
    "assinatura": "Assinado por {nome} em {data}",
    "visto": "Visto da fiscalização: {nome} em {data}",
    "nao_assinado": "Entrada não assinada (rascunho).",
    "fotos": "Fotografias",
    "sem_meteo": "Meteorologia não obtida.",
    "trabalhadores": "{n} trabalhador(es) · {h} h registadas no ponto",
}
QSE_PDF = {
    "titulo": "Registo de qualidade e segurança",
    "kicker": "QUALIDADE · SEGURANÇA · AMBIENTE",
    "cabecalho": ["N.º", "Data", "Tipo", "Descrição", "Gravidade", "Estado"],
    "acoes": "Plano de ação (5W2H)",
    "acoes_cab": ["O quê", "Quem", "Quando", "Estado"],
}
NOME_DOC = {"diario": "Diario_de_obra", "relatorio": "Relatorio_semanal", "qse": "Registo_QSE"}

# ------------------------------------------------------------------ histórico
HISTORICO = {
    "diario.criar": "abriu o diário de {ref}",
    "diario.editar": "atualizou o diário de {ref}",
    "diario.assinar": "assinou o diário de {ref}",
    "diario.aditamento": "acrescentou um aditamento ao diário de {ref}",
    "diario.visto": "visou o diário de {ref}",
    "diario.publicar": "alterou a publicação do diário de {ref}",
    "qse.criar": "registou {ref}",
    "qse.editar": "atualizou {ref}",
    "qse.fechar": "fechou {ref}",
    "qse.reabrir": "reabriu {ref}",
    "acao.criar": "criou uma ação em {ref}",
    "acao.estado": "mudou o estado de uma ação de {ref} para «{estado}»",
    "rfi.criar": "enviou o pedido {ref}",
    "rfi.responder": "respondeu ao pedido {ref}",
    "rfi.fechar": "fechou o pedido {ref}",
    "stock.movimento": "registou um movimento de stock: {ref}",
    "stock.rececao": "rececionou a encomenda {ref}",
    "copiloto.resumo": "gerou o resumo semanal",
    "webhook.config": "alterou os webhooks",
}

QSE_REF = {"inspecao": "Inspeção", "nao_conformidade": "NC", "incidente": "Acidente", "quase_acidente": "Quase-acidente",
           "dialogo_seguranca": "DDS", "epi": "EPI", "ambiente": "Ambiente"}
NUM = "n.º"
PROMPTS = {"foto": "Fotografia de obra.", "pergunta": "DADOS DA OBRA (JSON):\n{dados}\n\nPERGUNTA:\n{pergunta}"}

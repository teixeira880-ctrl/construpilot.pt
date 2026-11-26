"""Textos e vocabulário do módulo «Execução de obra» — versão Portugal (pt-PT, 3.ª pessoa formal).

O motor (engines/obra_execucao.py) e a API (routes/obra_execucao.py) são idênticos no .pt e no .fr;
só este ficheiro muda: mensagens, vocabulário do assessor de voz, modelos de atividades e categorias.
"""
from __future__ import annotations

LANG = "pt"

# ------------------------------------------------------------------ mensagens da API
T = {
    "perfil": "O seu perfil nesta obra não permite esta ação.",
    "texto_vazio": "Dite ou escreva o que aconteceu em obra.",
    "texto_longo": "Texto demasiado longo (máx. 6000 caracteres). Divida o relato em partes.",
    "estrutura_invalida": "Estrutura do mapa inválida: {erro}.",
    "zona_nao_encontrada": "Zona não encontrada no mapa da obra.",
    "atividade_nao_encontrada": "Atividade não encontrada no mapa da obra.",
    "piso_nao_encontrado": "Piso não encontrado.",
    "versao": "O mapa foi alterado entretanto. Recarregue a página.",
    "sem_planta": "Este piso ainda não tem planta.",
    "camara_url": "O endereço da câmara tem de começar por https://.",
    "camara_embed": "Para incorporar um vídeo, use um endereço de um serviço reconhecido ({hosts}).",
    "camara_limite": "Máximo de 12 câmaras por obra.",
    "movimento_invalido": "Movimento de tesouraria inválido.",
    "nao_encontrado": "Registo não encontrado.",
    "quota_ia": "Limite diário de interpretações por IA atingido para esta obra: a interpretação local continua disponível.",
    "armazenamento": "O armazenamento de ficheiros está indisponível. Tente novamente.",
}

HISTORICO = {
    "mapa.estrutura": "atualizou a estrutura do mapa da obra",
    "mapa.planta": "carregou a planta do piso {ref}",
    "mapa.avanco": "registou {pct} % de «{atividade}» em {ref}",
    "tesouraria.criar": "registou um movimento de tesouraria ({ref})",
    "tesouraria.editar": "alterou um movimento de tesouraria ({ref})",
    "tesouraria.apagar": "apagou um movimento de tesouraria ({ref})",
    "camaras.editar": "atualizou as câmaras da obra",
    "assessor.interpretar": "usou o assessor de voz ({ref})",
}

# ------------------------------------------------------------------ mapa da obra (modelos de atividades)
MODELOS_ATIVIDADES = {
    "acabamentos": {"label": "Acabamentos por divisão", "itens": [
        ("Alvenarias", 2), ("Redes elétricas", 1), ("Redes de águas e esgotos", 1), ("Reboco / estuque", 2),
        ("Gesso cambonado", 1), ("Caixilharia", 1), ("Revestimento de pavimento", 2), ("Revestimento cerâmico de parede", 1),
        ("Pintura", 1), ("Louças e equipamentos", 1)]},
    "estrutura": {"label": "Estrutura por piso", "itens": [
        ("Cofragem", 2), ("Armaduras", 2), ("Betonagem", 2), ("Descofragem", 1), ("Lajes", 3)]},
    "construcao_leve": {"label": "Construção leve (LSF / CLT)", "itens": [
        ("Montagem da estrutura", 3), ("Contraventamento", 1), ("Isolamento", 1), ("Placas e barreiras", 1),
        ("Redes técnicas", 1), ("Revestimentos", 2)]},
}

# ------------------------------------------------------------------ tesouraria
CATEGORIAS_TES = {
    "cliente": "Recebimento de cliente", "fornecedor": "Pagamento a fornecedor", "subempreiteiro": "Pagamento a subempreiteiro",
    "mao_obra": "Mão de obra", "equipamento": "Aluguer de equipamento", "taxas": "Taxas e licenças",
    "seguros": "Seguros", "outro": "Outro",
}
TES_NOTAS = {
    "faturas": "Recebimentos: pagamentos registados nas faturas da obra; o valor em dívida entra como previsto na data de vencimento (faturas em rascunho e anuladas excluídas).",
    "encomendas": "Pagamentos a fornecedores estimados a partir das encomendas enviadas ou confirmadas (sem IVA), na data de entrega prevista ou {prazo} dias após o envio.",
    "mao_obra": "Mão de obra: horas validadas × taxa horária da obra, contabilizadas no fim de cada mês.",
    "sem_taxa": "Horas validadas sem taxa horária definida na obra: a mão de obra não entra na tesouraria.",
    "manuais": "Movimentos manuais introduzidos pela empresa (subempreiteiros, alugueres, taxas…).",
}
TES_ALERTAS = {
    "vencido": "{n} fatura(s) vencida(s) por receber: {valor} €.",
    "negativo": "A tesouraria da obra fica negativa a {data} (mínimo previsto {valor} €).",
}

# ------------------------------------------------------------------ câmaras
EMBED_HOSTS = ("www.youtube.com", "youtube.com", "www.youtube-nocookie.com", "player.vimeo.com", "rtsp.me",
               "g0.ipcamlive.com", "ipcamlive.com", "player.angelcam.com", "www.earthcam.com", "app.evercam.io")

# ------------------------------------------------------------------ assessor de voz (vocabulário pt-PT)
NUMEROS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8,
    "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14, "quatorze": 14, "quinze": 15,
    "dezasseis": 16, "dezassete": 17, "dezoito": 18, "dezanove": 19, "vinte": 20, "trinta": 30, "quarenta": 40,
    "cinquenta": 50, "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90, "cem": 100, "cento": 100,
    "duzentos": 200, "duzentas": 200, "trezentos": 300, "quatrocentos": 400, "quinhentos": 500, "mil": 1000,
    "meia": 0.5, "meio": 0.5,
}
UNIDADES = {   # forma falada (normalizada) → unidade
    "sacos": "saco", "saco": "saco", "m3": "m³", "metros cubicos": "m³", "metro cubico": "m³", "cubos": "m³",
    "m2": "m²", "metros quadrados": "m²", "metro quadrado": "m²", "kg": "kg", "quilos": "kg", "kilos": "kg",
    "toneladas": "t", "tonelada": "t", "t": "t", "paletes": "palete", "palete": "palete", "unidades": "un",
    "unidade": "un", "un": "un", "litros": "l", "litro": "l", "metros lineares": "ml", "ml": "ml", "metros": "m",
    "metro": "m", "varoes": "varão", "varao": "varão", "rolos": "rolo", "rolo": "rolo", "baldes": "balde",
    "balde": "balde", "latas": "lata", "lata": "lata", "placas": "placa", "placa": "placa", "caixas": "caixa",
    "caixa": "caixa", "tijolos": "un", "blocos": "un",
}
# palavras de unidade que também são o material (ex.: «200 tijolos»)
UNIDADE_E_MATERIAL = {"tijolos": "Tijolo", "blocos": "Bloco"}
LIGACAO = ("de", "do", "da", "dos", "das")
FIM_MATERIAL = ("e", "para", "no", "na", "nos", "nas", "em", "que", "ao", "a", "com", "pelo", "pela", "hoje", "ontem",
                "amanha", "porque", "mas", "ja", "tambem", "ate")

VERBOS_ENTRADA = r"(cheg(aram|ou|ou-nos)|receb(emos|i|eu|eram|ido|idos)|entreg(aram|ou|ue|ues)|descarreg(amos|aram|ou)|vieram|veio|entrada de|entraram|deu entrada)"
VERBOS_SAIDA = r"(gast(amos|ei|aram|ou)|us(amos|ei|aram|ou)|utiliz(amos|aram|ou)|consum(imos|iram|iu)|aplic(amos|aram|ou)|sai(ram|u)|levaram|levamos|betonamos|assentamos|colocamos|saida de)"
PESSOAS = r"(pessoas|homens|trabalhadores|operarios|elementos|colaboradores|oficiais|serventes|pedreiros|eletricistas|canalizadores|carpinteiros|pintores)"

QSE_REGRAS = (   # (expressão normalizada, tipo QSE, gravidade)
    (r"\bquase (acidente|caiu|cai|atropel)|\bpor pouco\b|\bescapou\b", "quase_acidente", "media"),
    (r"\bacidente|\bferiu|\bferido|\bmagoou|\bcaiu\b|\bqueda\b|\bcortou se\b|\bhospital|\bambulancia", "incidente", "alta"),
    (r"\bsem (capacete|colete|arnes|botas|luvas|oculos|epi|protecao)", "epi", "media"),
    (r"\bnao conform|\bmal executad|\bdefeito|\bfissur|\bdesaprumad|\binfiltra|\bnao esta de acordo com o projeto|\brefazer\b", "nao_conformidade", "media"),
    (r"\bderram|\boleo no chao|\bresiduos espalhad|\bpoeira|\bcontamina", "ambiente", "baixa"),
)
RFI_REGRAS = r"\bduvida\b|\bnao sabemos\b|\bprecisamos de saber|\besclarec|\bperguntar (ao|a)\b|\bfalta (o |a )?(pormenor|desenho|cota|indicacao)|\bqual (e )?a cota|\bconfirmar com (o|a)\b"
RFI_DESTINO = (("arquitet", "arquiteto"), ("fiscal", "fiscalizacao"), ("dono", "dono_obra"), ("cliente", "dono_obra"))
VISITA_REGRAS = r"\bvisita|\besteve (ca|em obra|na obra)|\bveio (o|a) (fiscal|arquitet|dono|engenheir|inspe|cliente|coordenador)|\binspecao da\b"
OCORRENCIA_REGRAS = r"\bchuva|\bchoveu|\bparad[oa]s?\b|\batras|\bavari|\bfalta de material|\bnao veio\b|\bnao vieram\b|\bfaltou\b|\bfaltaram\b|\bproblema|\bvento forte"
CONCLUIDO = r"\b(conclu[ií]d[oa]s?|terminad[oa]s?|acabad[oa]s?|feit[oa]s? a 100|pront[oa]s?)\b"
ZONA_LIGACAO = ("no", "na", "nos", "nas", "em", "do", "da")
TRABALHOS_PREFIXO = "Trabalhos"

ASSESSOR_SISTEMA = (
    "É o assessor de obra do ConstruPilot. Recebe o relato falado de um encarregado ou diretor de obra em português de Portugal "
    "e transforma-o em registos estruturados. NUNCA invente quantidades, materiais, pessoas, zonas nem percentagens que não "
    "estejam no relato. Responda APENAS com JSON válido, sem texto à volta, no formato:\n"
    '{"diario":{"trabalhos":"","ocorrencias":"","entregas":"","visitas":"","observacoes":"","efetivos":[{"equipa":"","n":0}]},'
    '"stock":[{"mov":"entrada|saida","material":"","unidade":"","quantidade":0,"frase":""}],'
    '"qse":[{"tipo":"incidente|quase_acidente|epi|nao_conformidade|ambiente","titulo":"","descricao":"","gravidade":"baixa|media|alta|critica","local":"","frase":""}],'
    '"rfi":[{"assunto":"","pergunta":"","destinatario_perfil":"arquiteto|fiscalizacao|dono_obra|null","frase":""}],'
    '"avanco":[{"zona":"","atividade":"","pct":0,"frase":""}]}\n'
    "Regras: «trabalhos» resume os trabalhos executados (frases curtas, uma por linha). Use para o stock os nomes de material "
    "da lista conhecida sempre que corresponderem. Para o avanço, use só zonas e atividades da lista fornecida e uma percentagem "
    "dita no relato (concluído = 100). Listas vazias quando não houver nada."
)
ASSESSOR_PROMPT = "Data do relato: {data}\nMateriais conhecidos: {materiais}\nZonas: {zonas}\nAtividades: {atividades}\n\nRelato:\n{texto}"

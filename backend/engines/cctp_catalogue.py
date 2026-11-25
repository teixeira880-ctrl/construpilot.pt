"""Catálogo do redator de Caderno de Encargos (cláusulas técnicas) — ConstruPilot Portugal.

Base determinística, escrita uma vez e revista: garante que um caderno de encargos ConstruPilot fica correto mesmo
sem IA. A IA (cctp_redacteur) adapta estes artigos ao projeto, mas só pode citar os documentos aqui listados
(lista branca verificada depois da redação).

Organização (prática portuguesa de mapa de quantidades de trabalho, por capítulos) :
  N.1 Condições técnicas especiais do capítulo
      N.1.1 Generalidades (objeto, natureza dos trabalhos, conhecimento do projeto e do local, documentos de referência…)
      N.1.2 Condições de execução (próprias do capítulo)
  N.2 … N.k Descrição dos trabalhos, por subcapítulo : artigo (descrição + localização)
      e variantes quantificáveis (N.2.1.1 …), que passam a ser as linhas do mapa de quantidades.

Os códigos internos dos capítulos são os mesmos do construpilot.fr (paridade de código entre .fr e .pt).
Referências limitadas a textos estáveis : RGEU, Eurocódigos NP EN e Anexos Nacionais, normas NP EN de produto,
especificações LNEC, DR 23/95, RTIEBT, ITED, REH, RRAE, SCIE, DL 273/2003, regime de gestão de resíduos.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------------------------
# Condições comuns a todos os capítulos (N.1.1)
# ---------------------------------------------------------------------------------------------
COMMUNES: list[tuple[str, str]] = [
    ("Conhecimento do projeto",
     "Antes da apresentação da proposta, o empreiteiro deve tomar conhecimento das peças escritas e desenhadas do "
     "projeto de arquitetura e dos projetos de especialidades, bem como das condições técnicas dos restantes capítulos, "
     "e ter em conta as exigências do conjunto das peças do processo de concurso. Os materiais a aplicar serão de "
     "primeira qualidade e aplicados segundo as regras da boa arte e a regulamentação em vigor à data da execução. O "
     "empreiteiro entregará os trabalhos e instalações completamente acabados e em perfeito estado de funcionamento."),
    ("Conhecimento do local",
     "O empreiteiro é considerado conhecedor do local da obra e de todas as condições que possam influir na execução, "
     "na conceção dos pormenores, na qualidade e nos preços dos trabalhos, nomeadamente acessos de máquinas e viaturas, "
     "possibilidades de estaleiro e de armazenamento, e servidões existentes. Não poderá invocar o seu desconhecimento "
     "para reclamar trabalhos a mais ou prorrogações de prazo."),
    ("Âmbito dos trabalhos",
     "Os preços do empreiteiro incluem o fornecimento, transporte, movimentação, aplicação e afinação de todos os "
     "materiais e acessórios necessários à completa e perfeita execução dos trabalhos descritos, incluindo cortes, "
     "ajustes, remates, fixações e todos os trabalhos acessórios, mesmo que não expressamente mencionados. A descrição "
     "dos trabalhos não tem caráter limitativo : o empreiteiro deve assinalar por escrito, antes da apresentação da "
     "proposta, qualquer erro ou omissão que detete nas peças do processo."),
    ("Interpretação do caderno de encargos",
     "O presente caderno de encargos descreve os trabalhos a executar em concordância com as peças desenhadas e não tem "
     "caráter limitativo. Os trabalhos compreendem tudo o que está indicado nas plantas, cortes e alçados e no presente "
     "documento, ainda que alguns pormenores não estejam especificados : o empreiteiro é considerado conhecedor das "
     "regras da boa arte para suprir eventuais imprecisões. Em caso de contradição entre peças, prevalece a solução "
     "mais favorável à qualidade da obra, salvo indicação em contrário da fiscalização."),
    ("Verificação das peças e das cotas",
     "Antes do início de qualquer trabalho, o empreiteiro verificará as cotas das peças desenhadas e comunicará à "
     "fiscalização qualquer erro ou omissão encontrados. Não o fazendo, será responsável pelo seu erro e pelas "
     "alterações que dele resultem para os restantes trabalhos."),
    ("Documentos de referência",
     "Os trabalhos serão executados de acordo com a regulamentação e normalização em vigor à data da apresentação das "
     "propostas, nomeadamente : o Regulamento Geral das Edificações Urbanas (RGEU), os Eurocódigos estruturais NP EN "
     "1990 a NP EN 1998 com os respetivos Anexos Nacionais, as normas portuguesas e europeias (NP, NP EN) aplicáveis, "
     "as especificações e documentos de homologação do LNEC, as Avaliações Técnicas Europeias dos produtos não "
     "tradicionais e as instruções de aplicação dos fabricantes. Os produtos de construção terão marcação CE e "
     "declaração de desempenho, nos termos do Regulamento (UE) n.º 305/2011."),
    ("Amostras, fichas técnicas e desenhos de preparação",
     "Antes de qualquer encomenda, o empreiteiro submeterá à aprovação da fiscalização as fichas técnicas, declarações "
     "de desempenho, documentos de homologação e, a pedido, as amostras dos materiais e equipamentos propostos. "
     "Elaborará os desenhos de preparação e de pormenor necessários aos seus trabalhos. Nenhum trabalho será iniciado "
     "sem aprovação prévia."),
    ("Coordenação com os restantes trabalhos",
     "O empreiteiro coordena-se com as restantes especialidades para a execução de reservas, atravessamentos, negativos "
     "e remates. Antes de iniciar os seus trabalhos verifica que os suportes entregues estão conformes às tolerâncias "
     "exigidas ; na falta de reserva escrita, considera-se que os aceitou."),
    ("Segurança e saúde no trabalho",
     "O empreiteiro cumprirá o Plano de Segurança e Saúde (PSS) da obra e as determinações do coordenador de segurança "
     "em obra, quando exigidos pelo Decreto-Lei n.º 273/2003, e desenvolverá o PSS para a fase de execução antes de "
     "qualquer intervenção, incluindo as fichas de procedimentos de segurança dos trabalhos com riscos especiais."),
    ("Aprovação dos materiais de acabamento",
     "As referências dos materiais de acabamento e equipamentos serão apresentadas ao dono de obra e ao arquiteto para "
     "aprovação, com orçamento, antes de qualquer encomenda. As marcas e modelos eventualmente indicados são de "
     "referência : o empreiteiro pode propor produtos técnica e esteticamente equivalentes, sujeitos a aprovação da "
     "fiscalização."),
    ("Proteção, limpeza e gestão de resíduos",
     "O empreiteiro assegura a proteção dos seus trabalhos até à receção, bem como a dos trabalhos existentes ou de "
     "outras especialidades que possa danificar. Procede à limpeza diária da sua zona de trabalho e à triagem e "
     "encaminhamento dos resíduos de construção e demolição para operadores licenciados, de acordo com o Plano de "
     "Prevenção e Gestão de Resíduos de Construção e Demolição (PPGRCD) e o Decreto-Lei n.º 102-D/2020."),
    ("Telas finais e compilação técnica",
     "No final dos trabalhos, o empreiteiro entregará os elementos relativos ao seu capítulo para as telas finais e a "
     "compilação técnica da obra : desenhos conformes à execução, fichas técnicas dos produtos aplicados, instruções de "
     "utilização e manutenção, relatórios de ensaios e certificados exigidos pela regulamentação."),
]

RENOVATION = ("Trabalhos em edifício existente",
              "Sendo os trabalhos executados num edifício existente, o empreiteiro tomará todas as medidas para preservar "
              "os elementos a manter, as redes em serviço e, se for o caso, a ocupação do edifício. Antes de intervir em "
              "materiais suscetíveis de conter amianto, tomará conhecimento do levantamento fornecido pelo dono de obra "
              "e cumprirá o Decreto-Lei n.º 266/2007 ; qualquer descoberta imprevista será comunicada de imediato e os "
              "trabalhos em causa suspensos.")


def _o(code, chapitre, titre, description, unite, variantes, motscles):
    return {"code": code, "chapitre": chapitre, "titre": titre, "description": description, "unite": unite,
            "variantes": variantes, "motscles": motscles}


# ---------------------------------------------------------------------------------------------
# Capítulos
# ---------------------------------------------------------------------------------------------
LOTS: list[dict] = [
    {
        "code": "demolition", "numero": 1, "titre": "Estaleiro, demolições e trabalhos preparatórios",
        "motscles": ["estaleiro", "demolicao", "demolir", "desmontagem", "remocao", "entulho", "picagem", "limpeza do terreno"],
        "refs": ["Decreto-Lei n.º 273/2003 — Segurança e saúde no trabalho em estaleiros temporários ou móveis",
                 "Decreto-Lei n.º 102-D/2020 — Regime geral de gestão de resíduos (incluindo resíduos de construção e demolição)",
                 "Decreto-Lei n.º 266/2007 — Proteção dos trabalhadores contra os riscos de exposição ao amianto"],
        "prescriptions": [
            ("Preparação e segurança das demolições", [
                ("Reconhecimento prévio",
                 "Antes de qualquer demolição, o empreiteiro procederá ao reconhecimento dos elementos a demolir, à "
                 "identificação e corte das redes (eletricidade, gás, água, esgotos) em articulação com as entidades "
                 "gestoras e com as restantes especialidades. Verificará que os elementos a manter não são suportados por "
                 "elementos a demolir ; em caso de dúvida, consultará a fiscalização."),
                ("Escoramentos e estabilidade",
                 "O empreiteiro assegura, sob sua responsabilidade, a estabilidade dos elementos a manter e dos edifícios "
                 "confinantes durante toda a obra : escoramentos, travamentos e entivações provisórias, mantidos até à "
                 "execução das soluções definitivas."),
                ("Triagem e encaminhamento",
                 "Os resíduos de demolição serão triados em obra (inertes, madeira, metais, gesso, resíduos não perigosos, "
                 "resíduos perigosos) e encaminhados para operadores licenciados, com as guias eletrónicas de "
                 "acompanhamento de resíduos entregues à fiscalização."),
            ]),
        ],
        "ouvrages": [
            _o("estaleiro", "Estaleiro", "MONTAGEM, MANUTENÇÃO E DESMONTAGEM DO ESTALEIRO",
               "Montagem do estaleiro de acordo com o plano de estaleiro : vedação, acessos, instalações sociais, "
               "armazenamento, ligações provisórias de água e eletricidade, placa de identificação da obra e de "
               "licenciamento, manutenção durante a obra e desmontagem final com limpeza do local.", "vg",
               ["Estaleiro completo"], ["estaleiro", "vedacao", "instalacoes provisorias"]),
            _o("curage", "Demolições", "REMOÇÃO DE REVESTIMENTOS E EQUIPAMENTOS INTERIORES",
               "Remoção e transporte a vazadouro licenciado de todos os revestimentos, equipamentos e elementos interiores "
               "indicados nas peças desenhadas : revestimentos de pavimentos e paredes, tetos falsos, divisórias leves, "
               "carpintarias, louças sanitárias e equipamentos fora de serviço. Inclui proteção dos elementos a manter e "
               "triagem dos resíduos.", "m2", ["Remoção integral dos pisos indicados"], ["remocao", "desmontagem", "picagem"]),
            _o("demol_cloison", "Demolições", "DEMOLIÇÃO DE PAREDES DIVISÓRIAS NÃO RESISTENTES",
               "Demolição cuidada de paredes divisórias não resistentes (tijolo, gesso cartonado), incluindo remoção de "
               "aros, regularização dos roços e remoção do entulho.", "m2", ["Divisórias, qualquer espessura"],
               ["demolicao de parede", "demolir parede", "demolicao de divisoria"]),
            _o("ouverture_mur", "Demolições", "ABERTURA DE VÃO EM PAREDE RESISTENTE",
               "Abertura de vão em parede resistente, de acordo com o projeto de estabilidade : escoramento, corte ou "
               "demolição cuidada, execução da verga ou viga de reforço, incluindo todos os trabalhos acessórios.", "un",
               ["Vão conforme projeto de estabilidade"], ["abertura de vao", "parede resistente", "parede mestra"]),
        ],
    },
    {
        "code": "vrd", "numero": 2, "titre": "Movimento de terras e redes enterradas",
        "motscles": ["escavacao", "aterro", "terraplenagem", "vala", "movimento de terras", "rede enterrada", "caixa de visita", "drenagem"],
        "refs": ["NP EN 1997-1 (Eurocódigo 7) — Projeto geotécnico, com o Anexo Nacional",
                 "Decreto Regulamentar n.º 23/95 — Regulamento geral dos sistemas públicos e prediais de distribuição de água e de drenagem de águas residuais",
                 "NP EN 1610 — Construção e ensaio de coletores de águas residuais"],
        "prescriptions": [
            ("Condições de execução", [
                ("Implantação",
                 "A implantação da obra será feita a partir das referências fornecidas pelo topógrafo do dono de obra, "
                 "cabendo ao empreiteiro a sua conservação durante toda a obra."),
                ("Estudo geotécnico",
                 "As escavações e fundações serão executadas de acordo com as conclusões do estudo geotécnico, quando "
                 "exista. Qualquer diferença em relação às hipóteses do projeto será comunicada de imediato à fiscalização "
                 "antes de prosseguir."),
                ("Redes enterradas",
                 "As tubagens serão assentes em leito de areia e envolvidas com material adequado, com inclinações "
                 "regulares conformes ao projeto, fita de sinalização e ensaio de estanquidade antes do aterro."),
            ]),
        ],
        "ouvrages": [
            _o("decapage", "Movimento de terras", "DECAPAGEM DE TERRA VEGETAL",
               "Decapagem da terra vegetal na área de implantação e arruamentos, com a espessura verificada em obra, "
               "depósito em obra para reutilização ou transporte a vazadouro.", "m2", ["Espessura média conforme reconhecimento"],
               ["decapagem", "terra vegetal"]),
            _o("fouilles", "Movimento de terras", "ESCAVAÇÃO PARA FUNDAÇÕES",
               "Escavação em vala ou poço para fundações, até ao terreno com características definidas no projeto de "
               "estabilidade, incluindo regularização do fundo, eventual esgoto de águas e transporte ou reutilização "
               "das terras.", "m3", ["Escavação em vala", "Escavação em poço"], ["escavacao", "vala", "fundacoes"]),
            _o("remblai", "Movimento de terras", "ATERROS COMPACTADOS",
               "Aterro com solos da escavação ou de empréstimo, em camadas compactadas, junto às fundações e sob "
               "pavimentos térreos.", "m3", ["Aterro em tout-venant compactado"], ["aterro"]),
            _o("reseau_eu", "Redes enterradas", "REDE ENTERRADA DE ÁGUAS RESIDUAIS DOMÉSTICAS",
               "Coletores em PVC compacto de classe adequada assentes em vala sobre leito de areia, incluindo acessórios, "
               "caixas de visita e ligação ao ramal de ligação à rede pública ou ao sistema de tratamento.", "ml",
               ["PVC Ø 125 mm", "PVC Ø 160 mm"], ["aguas residuais", "esgotos", "coletor"]),
            _o("reseau_ep", "Redes enterradas", "REDE ENTERRADA DE ÁGUAS PLUVIAIS",
               "Recolha dos tubos de queda por caixas de areia e coletores em PVC até ao destino definido (rede pública, "
               "poço absorvente ou reservatório de aproveitamento).", "ml", ["PVC Ø 110 mm", "PVC Ø 125 mm"],
               ["aguas pluviais", "tubo de queda"]),
            _o("drainage", "Redes enterradas", "DRENAGEM PERIFÉRICA",
               "Dreno perfurado envolvido em geotêxtil e brita, assente junto às fundações, com caixas de visita nas "
               "mudanças de direção e descarga no destino previsto.", "ml", ["Dreno Ø 110 mm"], ["dreno", "drenagem"]),
        ],
    },
    {
        "code": "gros_oeuvre", "numero": 3, "titre": "Estruturas e alvenarias",
        "motscles": ["parede", "alvenaria", "tijolo", "bloco", "betao", "laje", "sapata", "fundacao", "lintel", "viga", "pilar",
                     "cinta", "muro", "estrutura", "armadura", "cofragem", "etics", "capoto", "reboco"],
        "refs": ["NP EN 1992-1-1 (Eurocódigo 2) — Projeto de estruturas de betão, com o Anexo Nacional",
                 "NP EN 1996-1-1 (Eurocódigo 6) — Projeto de estruturas de alvenaria, com o Anexo Nacional",
                 "NP EN 1998-1 (Eurocódigo 8) — Projeto de estruturas para resistência aos sismos, com o Anexo Nacional",
                 "NP EN 206 — Betão : especificação, desempenho, produção e conformidade",
                 "NP EN 13670 — Execução de estruturas de betão",
                 "NP EN 771 — Especificações para unidades de alvenaria",
                 "Especificações LNEC aplicáveis aos betões e aos varões de aço A500 NR",
                 "REH — Regulamento de Desempenho Energético dos Edifícios de Habitação (Decreto-Lei n.º 101-D/2020)"],
        "prescriptions": [
            ("Condições de execução", [
                ("Projeto de execução",
                 "Os elementos estruturais serão executados de acordo com as peças escritas e desenhadas do projeto de "
                 "estabilidade. Os desenhos de cofragem e armaduras e quaisquer alterações serão submetidos à aprovação da "
                 "fiscalização e do projetista antes da execução."),
                ("Betões e armaduras",
                 "Os betões serão pronto-a-usar conformes à NP EN 206 e às especificações LNEC, com classe de resistência, "
                 "classe de exposição e recobrimentos definidos no projeto de estabilidade. As armaduras serão em aço A500 "
                 "NR certificado. A execução, betonagem e cura seguirão a NP EN 13670."),
                ("Tolerâncias",
                 "As tolerâncias de implantação, prumo e planeza serão as do projeto e das normas de execução aplicáveis. "
                 "Os suportes destinados a revestimentos colados respeitarão as tolerâncias exigidas pelos capítulos "
                 "respetivos."),
                ("Negativos e atravessamentos",
                 "O empreiteiro executará em tempo útil todos os negativos, aberturas, mangas e atravessamentos pedidos "
                 "pelas especialidades, com base nos desenhos de preparação aprovados."),
            ]),
        ],
        "ouvrages": [
            _o("semelles", "Fundações", "SAPATAS E VIGAS DE FUNDAÇÃO EM BETÃO ARMADO",
               "Sapatas e vigas de fundação em betão armado, sobre betão de limpeza, com betão e armaduras definidos no "
               "projeto de estabilidade, incluindo cofragem, armaduras, arranques e negativos para passagem de redes.", "m3",
               ["Betão de limpeza com 0,05 m", "Sapatas e vigas de fundação conforme projeto"], ["sapata", "fundacao", "viga de fundacao"]),
            _o("soubassement", "Fundações", "MUROS DE SUPORTE E PAREDES ENTERRADAS",
               "Muros e paredes enterradas em betão armado ou blocos de betão, com impermeabilização e drenagem do "
               "tardoz.", "m2", ["Parede enterrada conforme projeto"], ["muro", "muro de suporte", "cave"]),
            _o("dallage", "Pavimentos térreos", "MASSAME SOBRE ENROCAMENTO",
               "Massame em betão armado com malhasol sobre enrocamento compactado, membrana de polietileno e isolamento "
               "térmico quando previsto, com juntas de retração.", "m2", ["Massame com 0,12 m"], ["massame", "pavimento terreo", "laje terrea"]),
            _o("plancher_hourdis", "Lajes", "LAJE ALIGEIRADA DE VIGOTAS PRÉ-ESFORÇADAS",
               "Laje aligeirada de vigotas pré-esforçadas e abobadilhas cerâmicas, de betão ou de EPS, com lâmina de "
               "compressão armada, de acordo com o plano de montagem do fabricante e o projeto de estabilidade, incluindo "
               "escoramento, cintas e aberturas.", "m2", ["Laje aligeirada com 0,20 m", "Laje aligeirada com 0,25 m"],
               ["laje", "vigota", "abobadilha", "laje aligeirada"]),
            _o("dalle_ba", "Lajes", "LAJE MACIÇA EM BETÃO ARMADO",
               "Laje maciça em betão armado, espessura e armaduras conformes ao projeto de estabilidade, incluindo "
               "cofragem, escoramento e descofragem.", "m2", ["Laje maciça conforme projeto"], ["laje macica", "laje"]),
            _o("murs_blocs", "Alvenarias", "PAREDES EXTERIORES EM ALVENARIA",
               "Paredes exteriores em alvenaria de tijolo cerâmico ou blocos de betão, assentes com argamassa, com "
               "travamento à estrutura, ombreiras, padieiras e caixas de estore, e correção das pontes térmicas conforme "
               "o projeto de comportamento térmico.", "m2", ["Tijolo de 0,15 m + 0,11 m (parede dupla)", "Bloco térmico de 0,25 m"],
               ["parede", "alvenaria", "tijolo", "bloco"]),
            _o("chainages", "Estrutura", "PILARES, VIGAS E LINTÉIS EM BETÃO ARMADO",
               "Pilares, vigas, lintéis e cintas em betão armado, betonados em obra ou pré-fabricados, conforme projeto de "
               "estabilidade.", "m3", ["Pilares e vigas conforme projeto"], ["pilar", "viga", "lintel", "cinta"]),
            _o("etics", "Fachadas", "SISTEMA COMPÓSITO DE ISOLAMENTO TÉRMICO PELO EXTERIOR (ETICS)",
               "Sistema ETICS com Avaliação Técnica Europeia : placas de isolamento térmico coladas e fixadas mecanicamente, "
               "camada de base armada com rede de fibra de vidro, perfis de arranque e de canto, e revestimento final na "
               "cor escolhida pelo arquiteto. Espessura do isolamento conforme projeto de comportamento térmico (REH).",
               "m2", ["ETICS com EPS", "ETICS com lã mineral"], ["etics", "capoto", "isolamento pelo exterior"]),
            _o("enduit_facade", "Fachadas", "REBOCO EXTERIOR",
               "Reboco exterior de ligante hidráulico pré-doseado, aplicado sobre salpico, com acabamento e cor a definir "
               "pelo arquiteto, incluindo cantoneiras e tratamento dos pontos singulares.", "m2",
               ["Reboco areado fino", "Reboco projetado"], ["reboco", "fachada", "reboco exterior"]),
        ],
    },
    {
        "code": "charpente_couverture", "numero": 4, "titre": "Coberturas e impermeabilizações",
        "motscles": ["cobertura", "telhado", "telha", "asna", "madre", "ripa", "caleira", "rufo", "impermeabilizacao", "terraco"],
        "refs": ["NP EN 1995-1-1 (Eurocódigo 5) — Projeto de estruturas de madeira, com o Anexo Nacional",
                 "NP EN 1991-1-3 e NP EN 1991-1-4 (Eurocódigo 1) — Ações da neve e do vento",
                 "NP EN 1304 — Telhas cerâmicas e acessórios",
                 "NP EN 612 — Caleiras e tubos de queda em chapa metálica",
                 "Decreto Regulamentar n.º 23/95 — Drenagem de águas pluviais"],
        "prescriptions": [
            ("Condições de execução", [
                ("Dimensionamento",
                 "A estrutura da cobertura será dimensionada de acordo com o Eurocódigo aplicável e as ações da neve e do "
                 "vento do local. A nota de cálculo e os desenhos de fabrico serão submetidos à aprovação antes do fabrico."),
                ("Madeiras",
                 "As madeiras terão classe de resistência adequada e tratamento preservador contra insetos e fungos "
                 "compatível com a classe de risco."),
                ("Ventilação e estanquidade",
                 "Será assegurada a ventilação da face inferior das telhas e a continuidade da subtelha, com remates "
                 "estanques em cumeeiras, laróz, beirados, rincões e atravessamentos, segundo as instruções do fabricante."),
            ]),
        ],
        "ouvrages": [
            _o("charpente_trad", "Estrutura da cobertura", "ESTRUTURA DE COBERTURA EM MADEIRA",
               "Estrutura de cobertura em madeira maciça ou lamelada-colada (asnas, madres, varas), ligações metálicas e "
               "ancoragens, conforme nota de cálculo.", "m2", ["Madeira tratada"], ["asna", "madre", "estrutura de cobertura", "madeira"]),
            _o("charpente_fermettes", "Estrutura da cobertura", "COBERTURA SOBRE LAJE INCLINADA",
               "Cobertura inclinada sobre laje de betão, com isolamento térmico, ripado e contra-ripado de suporte das "
               "telhas, conforme pormenores de arquitetura.", "m2", ["Sobre laje inclinada"], ["laje inclinada"]),
            _o("ecran", "Revestimento da cobertura", "SUBTELHA",
               "Membrana de subtelha respirável, aplicada sobre o suporte com contra-ripado, com sobreposições e remates "
               "segundo o fabricante.", "m2", ["Subtelha respirável"], ["subtelha"]),
            _o("tuiles", "Revestimento da cobertura", "REVESTIMENTO EM TELHA CERÂMICA",
               "Revestimento em telha cerâmica conforme NP EN 1304, modelo e cor a aprovar pelo arquiteto e conforme "
               "licenciamento, assente em ripado, incluindo cumeeira ventilada, beirados, laróz, rincões e acessórios.", "m2",
               ["Telha cerâmica de encaixe"], ["telha", "telhado", "cobertura"]),
            _o("toit_terrasse", "Coberturas planas", "IMPERMEABILIZAÇÃO DE COBERTURA PLANA",
               "Sistema de impermeabilização com membranas betuminosas ou sintéticas com documento de homologação ou "
               "Avaliação Técnica Europeia, sobre camada de forma com pendentes, isolamento térmico, camada de proteção e "
               "remates em platibandas, ralos e atravessamentos.", "m2", ["Cobertura plana não acessível", "Cobertura plana acessível"],
               ["terraco", "cobertura plana", "impermeabilizacao"]),
            _o("zinguerie", "Drenagem pluvial", "CALEIRAS, RUFOS E TUBOS DE QUEDA",
               "Caleiras, rufos e tubos de queda em zinco, alumínio lacado ou PVC, incluindo suportes, bocais, curvas e "
               "ligação às caixas de águas pluviais.", "ml", ["Caleira", "Tubo de queda Ø 80 mm"],
               ["caleira", "rufo", "tubo de queda"]),
            _o("fenetre_toit", "Revestimento da cobertura", "JANELAS DE COBERTURA",
               "Janelas de cobertura com remate de estanquidade adequado ao revestimento, dimensões conforme peças desenhadas.",
               "un", ["Janela de cobertura 78 x 98 cm"], ["janela de cobertura", "claraboia", "velux"]),
        ],
    },
    {
        "code": "menuiseries_ext", "numero": 5, "titre": "Caixilharias exteriores e proteções solares",
        "motscles": ["caixilharia", "janela", "porta de entrada", "vao", "estore", "portada", "vidro", "envidracado", "correr"],
        "refs": ["NP EN 14351-1 — Janelas e portas pedonais exteriores",
                 "NP EN 12207, NP EN 12208 e NP EN 12210 — Classificação de permeabilidade ao ar, estanquidade à água e resistência ao vento",
                 "REH — Regulamento de Desempenho Energético dos Edifícios de Habitação (Decreto-Lei n.º 101-D/2020)",
                 "RRAE — Regulamento dos Requisitos Acústicos dos Edifícios (Decreto-Lei n.º 129/2002)",
                 "RGEU — Regulamento Geral das Edificações Urbanas"],
        "prescriptions": [
            ("Condições de execução", [
                ("Desempenho",
                 "As caixilharias terão classes de permeabilidade ao ar, estanquidade à água e resistência ao vento "
                 "adequadas à exposição, e o coeficiente de transmissão térmica (Uw) e o desempenho acústico definidos nos "
                 "projetos de comportamento térmico e acústico. Terão marcação CE e declaração de desempenho."),
                ("Assentamento",
                 "O assentamento garantirá estanquidade contínua ao ar e à água entre aro e vão, com tratamento cuidado do "
                 "peitoril e da soleira, sem pontes térmicas evitáveis."),
                ("Segurança",
                 "Os vidros de portas, portas-janela e zonas baixas serão vidros de segurança (temperados ou laminados). As "
                 "guardas cumprirão o RGEU e as normas aplicáveis."),
            ]),
        ],
        "ouvrages": [
            _o("fenetres_pvc", "Caixilharias", "JANELAS E PORTAS-JANELA",
               "Caixilharia em PVC, alumínio com corte térmico ou madeira, de batente ou oscilobatente, com vidro duplo, "
               "ferragens e vedantes, cor a definir pelo arquiteto.", "un",
               ["Janela de 1 folha", "Janela de 2 folhas", "Porta-janela de 2 folhas"], ["janela", "porta-janela", "caixilharia"]),
            _o("coulissant", "Caixilharias", "VÃOS DE CORRER",
               "Caixilharia de correr em alumínio com corte térmico, vidro duplo de segurança, soleira adequada às "
               "exigências de acessibilidade quando aplicável.", "un", ["Vão de correr de 2 folhas"], ["correr", "vao de correr"]),
            _o("porte_entree", "Caixilharias", "PORTA DE ENTRADA",
               "Porta de entrada isolante, fechadura de segurança multiponto, soleira com corte térmico, modelo a definir "
               "pelo arquiteto.", "un", ["Porta de entrada isolante"], ["porta de entrada", "porta exterior"]),
            _o("volets", "Proteções solares", "ESTORES EXTERIORES",
               "Estores de réguas de alumínio com isolamento, caixa de estore isolada, manobra elétrica com alimentação "
               "pelo capítulo de instalações elétricas.", "un", ["Estore elétrico"], ["estore", "portada"]),
        ],
    },
    {
        "code": "platrerie", "numero": 6, "titre": "Divisórias, revestimentos e tetos em gesso cartonado",
        "motscles": ["divisoria", "pladur", "gesso cartonado", "forro", "teto falso", "teto", "tecto", "sanca", "isolamento", "la mineral"],
        "refs": ["NP EN 520 — Placas de gesso", "NP EN 14195 — Perfis metálicos para sistemas de placas de gesso",
                 "NP EN 13963 — Materiais para juntas de placas de gesso", "NP EN 13964 — Tetos falsos",
                 "RRAE — Regulamento dos Requisitos Acústicos dos Edifícios (Decreto-Lei n.º 129/2002)",
                 "Regime jurídico de segurança contra incêndio em edifícios (Decreto-Lei n.º 220/2008)",
                 "REH — Regulamento de Desempenho Energético dos Edifícios de Habitação (Decreto-Lei n.º 101-D/2020)"],
        "prescriptions": [
            ("Execução dos sistemas em placas de gesso", [
                ("Trabalhos preparatórios",
                 "Os trabalhos só serão iniciados com o edifício fechado e protegido das intempéries. Antes da execução será "
                 "feita a implantação e marcação das divisórias e preparados os remates com as paredes existentes e as "
                 "juntas da estrutura. As redes embebidas deverão, de preferência, estar instaladas."),
                ("Fixação da estrutura",
                 "Não será utilizada fixação por pistola em suportes frágeis (alvenaria vazada, betão celular), com tubagens "
                 "embebidas ou em vigotas pré-esforçadas. As guias inferiores e superiores serão fixadas com espaçamento "
                 "máximo de 0,60 m ; em zonas húmidas, a guia inferior será protegida por remate estanque ou elevada."),
                ("Montantes",
                 "Os montantes serão colocados com afastamento de 0,40 m ou 0,60 m conforme as alturas admissíveis do "
                 "sistema, inteiros em toda a altura ; eventuais emendas serão desfasadas. Os montantes serão duplicados "
                 "junto aos aros de portas e às cargas pesadas."),
                ("Colocação das placas",
                 "As placas serão colocadas encostadas, com folga de cerca de 1 cm na base, juntas sobre os montantes e "
                 "desfasadas entre faces e entre camadas. Aparafusamento com espaçamento máximo de 0,30 m na face aparente. "
                 "As instalações embebidas serão executadas antes do fecho da segunda face."),
                ("Pontos singulares e reforços",
                 "Será prevista junta de dilatação nas juntas da estrutura e, no máximo, a cada 15 m. As cargas suspensas "
                 "superiores a 30 kg serão suportadas por reforços solidários da estrutura previstos na montagem."),
                ("Tolerâncias e acabamento",
                 "Planeza local : 1 mm sob régua de 0,20 m ; planeza geral : 5 mm sob régua de 2 m ; desvio de prumo : 5 mm "
                 "num piso corrente. Após tratamento das juntas, a superfície ficará apta a receber o acabamento previsto."),
            ]),
            ("Tetos falsos", [
                ("Estrutura do teto",
                 "A estrutura (perfis, pendurais e fixações) será dimensionada para o peso do teto, do isolamento e dos "
                 "equipamentos, de acordo com a NP EN 13964 e o sistema do fabricante. Os pendurais serão protegidos contra "
                 "a corrosão."),
                ("Planeza e juntas",
                 "A face inferior da estrutura não terá irregularidades superiores a 5 mm sob régua de 2 m. O teto será "
                 "interrompido nas juntas de dilatação da estrutura e, no máximo, a cada 15 m."),
                ("Isolamento e barreira pára-vapor",
                 "Quando exista isolamento sobre o teto, será colocada barreira pára-vapor contínua do lado quente, com "
                 "sobreposições fitadas e remates estanques na periferia e nos atravessamentos."),
            ]),
        ],
        "ouvrages": [
            _o("cloison_72", "Divisórias em gesso cartonado", "DIVISÓRIAS DE 72/48",
               "Divisória com 72 mm de espessura constituída por uma placa de gesso cartonado em cada face, aparafusada a "
               "estrutura metálica galvanizada de 48 mm (guias e montantes afastados 0,60 m), isolamento em lã mineral e "
               "tratamento de juntas e cantos com fita e massa. Placas hidrófugas em zonas húmidas.", "m2",
               ["1 placa standard de 12,5 mm por face", "1 placa hidrófuga de 12,5 mm por face (zonas húmidas)"],
               ["divisoria", "pladur", "gesso cartonado", "72/48"]),
            _o("cloison_98", "Divisórias em gesso cartonado", "DIVISÓRIAS DE 98/48 COM DUAS PLACAS E ISOLAMENTO",
               "Divisória com 98 mm de espessura com duas placas de gesso cartonado em cada face, sobre guias e montantes "
               "galvanizados de 48 mm afastados 0,60 m, parafusos com espaçamento máximo de 0,30 m, banda acústica na "
               "base, isolamento em painéis de lã mineral e tratamento de juntas.", "m2",
               ["2 placas standard de 12,5 mm por face"], ["98/48", "divisoria dupla", "duas placas"]),
            _o("doublage_isolant", "Revestimentos de paredes", "CONTRA-FACHADA COM ISOLAMENTO",
               "Revestimento interior das paredes exteriores em placa de gesso cartonado sobre estrutura metálica "
               "independente, isolamento em lã mineral com espessura definida no projeto de comportamento térmico, "
               "barreira pára-vapor contínua do lado quente e tratamento de juntas.", "m2",
               ["Isolamento conforme projeto térmico, placa de 12,5 mm"], ["contra-fachada", "forra", "isolamento interior"]),
            _o("habillage_colle", "Revestimentos de paredes", "PLACAS DE GESSO COLADAS",
               "Revestimento de paredes em placas de gesso cartonado coladas com cimento-cola por pontos, juntas com fita e "
               "massa ; o suporte não terá irregularidades superiores a 15 mm.", "m2", ["Placa hidrófuga de 12,5 mm"],
               ["placa colada", "revestimento colado"]),
            _o("plafond_ba13", "Tetos falsos", "TETOS FALSOS EM GESSO CARTONADO",
               "Teto falso em placas de gesso cartonado (standard ou hidrófugas) aparafusadas a estrutura metálica "
               "galvanizada suspensa ou fixa à laje, incluindo pendurais, cantoneiras e tratamento de juntas.", "m2",
               ["Placa standard de 12,5 mm", "Placa hidrófuga de 12,5 mm (zonas húmidas)"], ["teto falso", "teto", "tecto"]),
            _o("isolation_combles", "Isolamentos", "ISOLAMENTO DO DESVÃO DA COBERTURA",
               "Isolamento térmico do desvão não habitável em mantas ou painéis de lã mineral em duas camadas cruzadas, "
               "resistência térmica conforme projeto de comportamento térmico, incluindo barreira pára-vapor.", "m2",
               ["Lã mineral conforme projeto térmico"], ["desvao", "isolamento", "la mineral"]),
            _o("trappe", "Trabalhos diversos", "ALÇAPÕES DE VISITA",
               "Alçapões de visita com aro e porta em gesso cartonado, garantindo a continuidade do desempenho do elemento "
               "atravessado.", "un", ["Alçapão 50 x 50 cm", "Alçapão isolado de acesso ao desvão 60 x 60 cm"], ["alcapao"]),
            _o("soffite", "Trabalhos diversos", "SANCAS E COURETES EM GESSO CARTONADO",
               "Sancas e enchimentos de courettes em placas de gesso cartonado sobre estrutura metálica, com lã mineral, "
               "incluindo cortes, remates e acabamento.", "ml", ["Sanca com duas placas e isolamento"], ["sanca", "courete", "caixa"]),
        ],
    },
    {
        "code": "menuiseries_int", "numero": 7, "titre": "Carpintarias",
        "motscles": ["porta interior", "carpintaria", "roupeiro", "escada", "rodape de madeira", "aro"],
        "refs": ["NP EN 942 — Madeira em carpintaria : requisitos gerais",
                 "RGEU — Regulamento Geral das Edificações Urbanas (guardas e escadas)"],
        "prescriptions": [
            ("Condições de execução", [
                ("Aros e guarnições",
                 "Os aros serão assentes a prumo e nível, calçados e fixados à estrutura ou à alvenaria, tendo em conta a "
                 "espessura dos revestimentos de pavimento acabados."),
                ("Ferragens",
                 "As ferragens serão de qualidade adequada a uso intensivo ; será apresentada amostra de cada tipo ao "
                 "arquiteto. As portas das zonas húmidas terão folga inferior para passagem do ar da ventilação."),
            ]),
        ],
        "ouvrages": [
            _o("bloc_porte", "Portas interiores", "PORTAS INTERIORES",
               "Portas interiores de folha lisa (alveolar ou maciça), aro e guarnições em madeira ou MDF, acabamento "
               "lacado ou folheado, fechadura com trinco de condenação nas instalações sanitárias, puxadores com espelho.", "un",
               ["Porta de 0,80 x 2,10 m", "Porta de 0,90 x 2,10 m (acessibilidade)"], ["porta interior", "porta"]),
            _o("placard", "Roupeiros", "ROUPEIROS",
               "Frentes de roupeiro de correr ou de batente, interior com prateleiras, varão e gavetas conforme peças "
               "desenhadas.", "un", ["Roupeiro de 2 folhas"], ["roupeiro"]),
            _o("escalier_bois", "Escadas", "ESCADA EM MADEIRA",
               "Escada em madeira maciça ou lamelada, forma e dimensões conforme peças desenhadas, com guarda e corrimão "
               "conformes ao RGEU.", "un", ["Escada de um quarto"], ["escada"]),
            _o("plinthes_bois", "Acabamentos", "RODAPÉS EM MADEIRA",
               "Rodapés em madeira ou MDF lacado, colados ou pregados, com cortes em meia-esquadria.", "ml",
               ["Rodapé de 70 mm lacado"], ["rodape"]),
        ],
    },
    {
        "code": "sols_durs", "numero": 8, "titre": "Betonilhas e revestimentos cerâmicos",
        "motscles": ["betonilha", "ceramico", "mosaico", "azulejo", "porcelanico", "ladrilho", "piso radiante", "autonivelante"],
        "refs": ["NP EN 13813 — Materiais para betonilhas", "NP EN 14411 — Ladrilhos cerâmicos",
                 "NP EN 12004 — Cimentos-cola para ladrilhos", "NP EN 13888 — Argamassas de juntas para ladrilhos",
                 "Especificações e documentos de homologação LNEC aplicáveis"],
        "prescriptions": [
            ("Condições de execução", [
                ("Suportes",
                 "Antes do assentamento, o empreiteiro verificará a planeza, coesão, limpeza e secagem dos suportes. Serão "
                 "respeitados os tempos de secagem das betonilhas antes da colagem."),
                ("Escolha dos materiais",
                 "Os ladrilhos e cimentos-cola serão escolhidos em função da utilização dos espaços e da natureza do suporte. "
                 "Os ladrilhos de pavimento terão resistência ao escorregamento adequada nas zonas húmidas."),
                ("Zonas húmidas",
                 "Nos bases de duche e zonas expostas a salpicos será aplicado sistema de impermeabilização sob ladrilho com "
                 "documento de aplicação, com bandas de reforço nos cantos e atravessamentos."),
                ("Juntas",
                 "Serão respeitadas as juntas de fracionamento e periféricas. As juntas entre revestimentos e louças "
                 "sanitárias serão seladas com mástique fungicida."),
            ]),
        ],
        "ouvrages": [
            _o("chape", "Betonilhas", "BETONILHAS",
               "Betonilha de regularização ou flutuante sobre isolamento ou membrana acústica conforme peças desenhadas, "
               "incluindo banda perimetral e juntas.", "m2", ["Betonilha flutuante com 5 cm", "Betonilha aderente com 4 cm"],
               ["betonilha", "autonivelante"]),
            _o("carrelage_sol", "Pavimentos", "PAVIMENTO CERÂMICO",
               "Pavimento em ladrilho de grés porcelânico, formato e cor a definir pelo arquiteto, assente com cimento-cola "
               "adequado ao suporte e ao formato, juntas com argamassa de juntas, incluindo cortes e remates.", "m2",
               ["Grés porcelânico 60 x 60 cm", "Grés porcelânico 30 x 60 cm"], ["mosaico", "ceramico", "porcelanico", "pavimento ceramico"]),
            _o("plinthes_carrelage", "Pavimentos", "RODAPÉS CERÂMICOS",
               "Rodapés no mesmo material do pavimento, colados, com juntas alinhadas com as do pavimento.", "ml",
               ["Rodapé com 7 cm"], ["rodape ceramico"]),
            _o("faience", "Revestimentos de paredes", "AZULEJO EM PAREDES",
               "Revestimento de paredes em azulejo ou grés colado nas zonas húmidas, alturas conforme peças desenhadas "
               "(altura total nos duches), incluindo perfis de canto e remate.", "m2", ["Azulejo 30 x 60 cm"], ["azulejo", "revestimento de parede"]),
            _o("spec", "Revestimentos de paredes", "IMPERMEABILIZAÇÃO SOB LADRILHO",
               "Sistema de impermeabilização líquida ou em membrana sob ladrilho, com documento de aplicação, em duches e "
               "zonas expostas, com bandas de canto e golas de atravessamento.", "m2", ["Duches e zonas expostas"],
               ["impermeabilizacao sob ladrilho", "duche"]),
        ],
    },
    {
        "code": "sols_souples", "numero": 9, "titre": "Pavimentos de madeira e vinílicos",
        "motscles": ["soalho", "flutuante", "parquet", "madeira", "vinilico", "pvc", "linoleo", "autonivelante"],
        "refs": ["NP EN 13489 — Pavimentos de madeira : elementos de parquet multicamada",
                 "NP EN 14342 — Pavimentos de madeira : características, avaliação da conformidade e marcação",
                 "NP EN 13813 — Materiais para betonilhas (regularização do suporte)"],
        "prescriptions": [
            ("Condições de execução", [
                ("Humidade dos suportes",
                 "Antes de qualquer assentamento, a humidade dos suportes será medida e deverá ser compatível com o "
                 "revestimento e o modo de assentamento. A madeira será armazenada nos espaços o tempo necessário à sua "
                 "estabilização."),
                ("Preparação",
                 "Os suportes serão regularizados com argamassa autonivelante adequada à utilização, sobre primário."),
                ("Juntas",
                 "Será deixada folga perimetral junto às paredes e obstáculos nos assentamentos flutuantes, oculta pelos "
                 "rodapés ou perfis."),
            ]),
        ],
        "ouvrages": [
            _o("ragreage", "Preparação dos suportes", "REGULARIZAÇÃO AUTONIVELANTE",
               "Argamassa autonivelante sobre primário de aderência, classe adequada à utilização.", "m2",
               ["Espessura média de 3 mm"], ["argamassa autonivelante", "regularizacao autonivelante"]),
            _o("parquet_flottant", "Madeira", "PAVIMENTO FLUTUANTE EM MADEIRA MULTICAMADA",
               "Pavimento em parquet multicamada com camada de desgaste em madeira nobre, espécie e acabamento a definir "
               "pelo arquiteto, assente flutuante sobre subcamada acústica, incluindo perfis de transição.", "m2",
               ["Carvalho multicamada envernizado"], ["flutuante", "parquet", "multicamada"]),
            _o("parquet_colle", "Madeira", "SOALHO COLADO",
               "Soalho maciço ou multicamada colado em toda a superfície sobre suporte preparado, afagamento e envernizamento "
               "quando em bruto.", "m2", ["Soalho de carvalho colado"], ["soalho", "taco"]),
            _o("sol_pvc", "Vinílicos", "PAVIMENTO VINÍLICO",
               "Pavimento vinílico em rolo ou em réguas, colado sobre regularização, com juntas soldadas a quente em zonas "
               "húmidas e remate em rodapé quando previsto.", "m2", ["Vinílico em rolo"], ["vinilico", "pvc", "linoleo"]),
        ],
    },
    {
        "code": "peinture", "numero": 10, "titre": "Pinturas",
        "motscles": ["pintura", "tinta", "estuque", "barramento", "verniz", "esmalte", "papel de parede"],
        "refs": ["NP EN 13300 — Tintas e vernizes : produtos de pintura aquosos para paredes e tetos interiores",
                 "NP EN 1062-1 — Tintas e vernizes : produtos de pintura para alvenaria e betão exteriores",
                 "Decreto-Lei n.º 181/2006 — Limitação das emissões de compostos orgânicos voláteis (COV) das tintas e vernizes"],
        "prescriptions": [
            ("Condições de execução", [
                ("Grau de acabamento",
                 "Salvo indicação em contrário, o acabamento será cuidado nos espaços habitáveis e corrente nos espaços "
                 "técnicos e de serviço, com superfícies uniformes, sem escorridos nem marcas."),
                ("Preparação dos suportes",
                 "Os trabalhos preparatórios (lavagem, lixagem, emassamento, barramento, primário) serão adequados à natureza "
                 "e ao estado dos suportes. O empreiteiro recebe os suportes e formula as suas reservas antes de intervir."),
                ("Produtos",
                 "As tintas serão aquosas, de baixa emissão de COV, conformes ao Decreto-Lei n.º 181/2006, em cores a definir "
                 "pelo arquiteto sobre catálogo. As tintas das zonas húmidas serão laváveis e anti-fungos."),
            ]),
        ],
        "ouvrages": [
            _o("peinture_murs", "Pinturas interiores", "PINTURA DE PAREDES",
               "Sobre gesso cartonado ou estuque : primário, barramento, lixagem e duas demãos de tinta aquosa acetinada ou "
               "mate.", "m2", ["Acabamento acetinado", "Acabamento mate"], ["pintura de paredes", "pintura", "tinta"]),
            _o("peinture_plafonds", "Pinturas interiores", "PINTURA DE TETOS",
               "Primário, barramento, lixagem e duas demãos de tinta aquosa mate.", "m2", ["Acabamento mate"], ["pintura de tetos"]),
            _o("peinture_boiseries", "Pinturas interiores", "PINTURA DE MADEIRAS E METAIS",
               "Pintura de portas, aros, rodapés e serralharias : preparação, primário adequado e duas demãos de esmalte "
               "acetinado.", "m2", ["Esmalte acetinado"], ["esmalte", "pintura de madeiras"]),
            _o("peinture_ext", "Pinturas exteriores", "PINTURA DE FACHADAS",
               "Pintura de paramentos exteriores rebocados : primário e duas demãos de tinta conforme NP EN 1062-1, cor a "
               "definir pelo arquiteto.", "m2", ["Tinta aquosa para exterior"], ["pintura exterior", "fachada"]),
        ],
    },
    {
        "code": "plomberie", "numero": 11, "titre": "Instalações de águas e esgotos",
        "motscles": ["canalizacao", "agua", "esgoto", "abastecimento", "sanita", "lavatorio", "duche", "banheira", "termoacumulador", "lava-loica"],
        "refs": ["Decreto Regulamentar n.º 23/95 — Regulamento geral dos sistemas públicos e prediais de distribuição de água e de drenagem de águas residuais",
                 "NP EN 806 — Especificações para instalações de água para consumo humano no interior de edifícios",
                 "NP EN 12056 — Sistemas de drenagem gravítica no interior de edifícios",
                 "Lei n.º 52/2018 — Regime de prevenção e controlo da doença dos legionários"],
        "prescriptions": [
            ("Condições de execução", [
                ("Projeto",
                 "As redes serão executadas de acordo com o projeto de águas e esgotos aprovado e o Decreto Regulamentar "
                 "n.º 23/95. O empreiteiro elaborará os desenhos de preparação e de negativos, submetidos a aprovação."),
                ("Distribuição",
                 "Distribuição de água fria e quente em PEX, multicamada ou cobre, com documento de aplicação, com válvulas "
                 "de seccionamento por aparelho e por zona, redutor de pressão quando necessário e isolamento térmico das "
                 "redes de água quente."),
                ("Drenagem",
                 "Drenagem em PVC com inclinações regulares, ventilação primária acima da cobertura, sifão em cada aparelho "
                 "e bocas de limpeza nas mudanças de direção."),
                ("Ensaios e entrada em serviço",
                 "Ensaios de estanquidade e de pressão antes do fecho de courettes e revestimentos, lavagem e desinfeção da "
                 "rede de água potável antes da entrada em serviço, com relatórios entregues à fiscalização."),
            ]),
        ],
        "ouvrages": [
            _o("distribution", "Redes", "REDE DE DISTRIBUIÇÃO DE ÁGUA FRIA E QUENTE",
               "Rede de distribuição desde o contador até aos aparelhos, coletor de distribuição, válvulas de seccionamento e "
               "isolamento térmico.", "vg", ["Rede completa da habitação"], ["abastecimento", "rede de agua", "pex", "multicamada"]),
            _o("evacuations", "Redes", "REDE DE DRENAGEM DE ÁGUAS RESIDUAIS DOMÉSTICAS",
               "Tubos de queda e ramais em PVC até às caixas da rede enterrada, ventilação primária e ligação dos aparelhos.",
               "vg", ["Rede completa da habitação"], ["esgoto", "drenagem", "tubo de queda"]),
            _o("ecs", "Produção de água quente", "PRODUÇÃO DE ÁGUA QUENTE SANITÁRIA",
               "Produção de AQS por bomba de calor ou termoacumulador conforme projeto de comportamento térmico (REH), "
               "grupo de segurança, ligações hidráulicas e descarga.", "un",
               ["Bomba de calor para AQS 200 L", "Termoacumulador elétrico 200 L"], ["termoacumulador", "aqs", "bomba de calor aqs"]),
            _o("wc", "Louças sanitárias", "SANITAS",
               "Sanita em porcelana vitrificada suspensa com autoclismo embutido de dupla descarga, ou de pousar, com tampo.",
               "un", ["Sanita suspensa", "Sanita de pousar"], ["sanita"]),
            _o("lavabo", "Louças sanitárias", "LAVATÓRIOS",
               "Lavatório ou móvel com lavatório, misturadora, sifão e válvula, ligações.", "un", ["Móvel com lavatório de 80 cm"],
               ["lavatorio"]),
            _o("douche", "Louças sanitárias", "BASES DE DUCHE",
               "Base de duche extraplana ou duche de pavimento (em coordenação com o capítulo de revestimentos cerâmicos), "
               "misturadora termostática, conjunto de duche e resguardo em vidro.", "un", ["Base de duche 90 x 120 cm"], ["duche", "base de duche"]),
            _o("evier", "Louças sanitárias", "PREPARAÇÕES PARA COZINHA E LAVANDARIA",
               "Preparações de água fria, água quente e esgoto para lava-loiça, máquina de lavar loiça e máquina de lavar "
               "roupa, com torneiras de segurança.", "un", ["Preparações de cozinha e lavandaria"], ["lava-loica", "cozinha", "maquina de lavar"]),
        ],
    },
    {
        "code": "cvc", "numero": 12, "titre": "AVAC — Aquecimento, ventilação e ar condicionado",
        "motscles": ["aquecimento", "bomba de calor", "radiador", "piso radiante", "ventilacao", "vmc", "ar condicionado", "climatizacao", "caldeira"],
        "refs": ["REH — Regulamento de Desempenho Energético dos Edifícios de Habitação (Decreto-Lei n.º 101-D/2020)",
                 "NP EN 12831-1 — Método de cálculo da carga térmica de projeto",
                 "NP EN 1264 — Sistemas de aquecimento e arrefecimento por superfícies radiantes",
                 "NP 1037-1 — Ventilação e evacuação dos produtos da combustão dos locais com aparelhos a gás (edifícios de habitação)",
                 "NP EN 378 — Sistemas de refrigeração e bombas de calor : requisitos de segurança e ambientais",
                 "Regulamento (UE) 2024/573 — Gases fluorados com efeito de estufa"],
        "prescriptions": [
            ("Condições de execução", [
                ("Dimensionamento",
                 "As instalações serão dimensionadas com base no cálculo da carga térmica por compartimento (NP EN 12831-1) e "
                 "no projeto de comportamento térmico (REH). Os caudais de ventilação respeitarão o projeto e as exigências "
                 "de qualidade do ar interior aplicáveis."),
                ("Gases fluorados",
                 "As intervenções nos circuitos frigoríficos serão realizadas por técnicos certificados nos termos do "
                 "Regulamento (UE) 2024/573, com registo das intervenções entregue ao dono de obra."),
                ("Entrada em serviço",
                 "Equilibragem das redes, regulação, medição dos caudais de ventilação e relatórios de colocação em serviço "
                 "entregues à fiscalização ; formação do utilizador sobre o funcionamento dos equipamentos."),
            ]),
        ],
        "ouvrages": [
            _o("pac_air_eau", "Produção de calor", "BOMBA DE CALOR AR / ÁGUA",
               "Bomba de calor ar/água com potência conforme cálculo da carga térmica, módulo hidráulico, regulação por sonda "
               "exterior, ligações frigoríficas ou hidráulicas, apoio antivibrático da unidade exterior.", "un",
               ["Bomba de calor ar/água reversível"], ["bomba de calor"]),
            _o("plancher_chauffant", "Emissão", "PISO RADIANTE HIDRÁULICO",
               "Piso radiante hidráulico de baixa temperatura : isolamento, banda perimetral, tubo PEX ou multicamada, coletores "
               "com caudalímetros, conforme NP EN 1264 (betonilha pelo capítulo de betonilhas).", "m2",
               ["Piso radiante de baixa temperatura"], ["piso radiante", "chao radiante"]),
            _o("radiateurs", "Emissão", "RADIADORES",
               "Radiadores em aço ou alumínio e toalheiros, válvulas termostáticas, ligações.", "un", ["Radiador", "Toalheiro"],
               ["radiador", "toalheiro"]),
            _o("vmc", "Ventilação", "VENTILAÇÃO MECÂNICA",
               "Ventilação mecânica de extração ou com recuperação de calor conforme projeto : ventilador, bocas de extração, "
               "entradas de ar, condutas isoladas em espaço não útil, descarga acima da cobertura.", "vg",
               ["Ventilação de extração", "Ventilação com recuperação de calor"], ["ventilacao", "vmc", "recuperador de calor"]),
            _o("clim_split", "Climatização", "AR CONDICIONADO MULTI-SPLIT",
               "Sistema multi-split com unidades interiores murais ou de conduta, ligações frigoríficas, drenagem de "
               "condensados e comando.", "un", ["Unidade interior mural"], ["ar condicionado", "split", "climatizacao"]),
        ],
    },
    {
        "code": "electricite", "numero": 13, "titre": "Instalações elétricas e de telecomunicações (ITED)",
        "motscles": ["eletric", "tomada", "iluminacao", "quadro eletrico", "interruptor", "ited", "telecomunicacoes", "rj45", "luminaria"],
        "refs": ["RTIEBT — Regras Técnicas das Instalações Elétricas de Baixa Tensão (Portaria n.º 949-A/2006, e alterações)",
                 "Decreto-Lei n.º 96/2017 — Regime das instalações elétricas de serviço particular",
                 "ITED — Infraestruturas de Telecomunicações em Edifícios (Decreto-Lei n.º 123/2009, e alterações)",
                 "Manual ITED, 4.ª edição (ANACOM)"],
        "prescriptions": [
            ("Condições de execução", [
                ("Conformidade",
                 "A instalação será executada de acordo com o projeto de instalações elétricas e as RTIEBT. O empreiteiro "
                 "entregará o termo de responsabilidade pela execução e assegurará a inspeção exigida antes da ligação "
                 "definitiva, nos termos do Decreto-Lei n.º 96/2017."),
                ("Circuitos",
                 "Cada circuito final terá, no máximo, 8 pontos de utilização. Todas as tomadas das casas de banho e as "
                 "tomadas exteriores serão protegidas por dispositivo diferencial de alta sensibilidade (30 mA). Nas casas de "
                 "banho serão respeitados os volumes de proteção definidos nas RTIEBT."),
                ("Telecomunicações",
                 "A rede de telecomunicações será executada de acordo com o projeto ITED e o Manual ITED (4.ª edição) por "
                 "instalador habilitado, com Armário de Telecomunicações Individual (ATI), Zona de Acesso Privilegiado (ZAP) "
                 "com 2 tomadas de pares de cobre, 2 coaxiais e 2 de fibra ótica, e uma tomada mista (pares de cobre + "
                 "coaxial) nas salas, quartos e cozinha que não alojem a ZAP. Será entregue o termo de responsabilidade de "
                 "execução ITED."),
            ]),
        ],
        "ouvrages": [
            _o("chantier_elec", "Estaleiro", "QUADRO ELÉTRICO DE ESTALEIRO",
               "Fornecimento, montagem e desmontagem no final da obra de quadro de estaleiro adequado ao exterior, com "
               "tomadas, botoneira de emergência e proteções, e iluminação provisória das zonas de trabalho.", "vg",
               ["Quadro de estaleiro e iluminação provisória"], ["quadro de estaleiro", "estaleiro eletrico"]),
            _o("branchement", "Alimentação", "ENTRADA E TUBAGENS DE ALIMENTAÇÃO",
               "Tubagens enfiadas entre a portinhola do operador de rede e o quadro de entrada (energia, telecomunicações, "
               "alimentações exteriores), fita de sinalização, ligação até ao quadro.", "vg",
               ["Tubagens e alimentação geral"], ["portinhola", "alimentacao geral", "ramal"]),
            _o("terre", "Terra de proteção", "ELÉTRODO DE TERRA E LIGAÇÕES EQUIPOTENCIAIS",
               "Elétrodo de terra (anel de fundação ou varetas), ligador de terra, ligações equipotenciais principais e "
               "suplementares, medição da resistência de terra.", "vg", ["Terra e ligações equipotenciais"],
               ["terra de protecao", "eletrodo de terra", "equipotencial"]),
            _o("tableau", "Distribuição", "QUADRO DE ENTRADA",
               "Quadro elétrico com interruptores diferenciais, disjuntores, descarregador de sobretensões quando previsto, "
               "reserva mínima de 20 %, identificação dos circuitos.", "un", ["Quadro de 3 filas"], ["quadro eletrico", "quadro de entrada"]),
            _o("prises", "Aparelhagem", "TOMADAS",
               "Tomadas de 16 A com terra embutidas, aparelhagem de série a definir pelo arquiteto, incluindo cablagem e "
               "caixas.", "un", ["Tomada 16 A", "Tomada para circuito dedicado"], ["tomada"]),
            _o("eclairage", "Aparelhagem", "PONTOS DE LUZ E COMANDOS",
               "Pontos de luz no teto ou parede, comandos simples, de escada ou por telerruptor.", "un",
               ["Ponto de luz", "Interruptor"], ["iluminacao", "ponto de luz", "interruptor", "luminaria"]),
            _o("rj45", "Telecomunicações", "INFRAESTRUTURA ITED",
               "ATI, ZAP, tomadas de pares de cobre, coaxial e fibra ótica, cablagem e tubagem conforme projeto ITED e "
               "Manual ITED (4.ª edição).", "vg", ["Infraestrutura ITED da habitação"], ["ited", "rj45", "telecomunicacoes"]),
        ],
    },
]

# Trabalhos explicitamente incluídos em cada capítulo (« Ficam a cargo do presente capítulo »)
A_CHARGE: dict[str, list[str]] = {
    "demolition": ["o corte das redes em articulação com as entidades gestoras e as restantes especialidades",
                   "os escoramentos provisórios necessários à estabilidade dos elementos a manter",
                   "a triagem, carga e transporte dos resíduos com as guias de acompanhamento"],
    "vrd": ["a implantação a partir das referências do topógrafo", "o transporte ou depósito das terras sobrantes",
            "os ensaios de estanquidade das redes antes do aterro", "a fita de sinalização sobre as redes"],
    "gros_oeuvre": ["os andaimes e proteções coletivas necessários aos seus trabalhos",
                    "os negativos, aberturas e mangas pedidos em tempo útil pelas especialidades",
                    "os desenhos de preparação de cofragens e armaduras submetidos a aprovação",
                    "o fecho de aberturas e negativos após passagem das redes"],
    "charpente_couverture": ["a nota de cálculo e os desenhos de fabrico da estrutura da cobertura",
                             "os atravessamentos da cobertura (ventilação primária, ventilação mecânica, chaminés) com remates",
                             "as proteções coletivas no bordo da cobertura durante os trabalhos"],
    "menuiseries_ext": ["o levantamento das medidas em obra antes do fabrico", "as vedações periféricas e peitoris",
                        "a colocação das entradas de ar previstas no projeto de ventilação",
                        "a afinação e limpeza das caixilharias e vidros no final da obra"],
    "platrerie": ["a verificação dos suportes e a marcação dos trabalhos", "os reforços para cargas suspensas",
                  "os alçapões de visita e as instalações embebidas previstas", "o tratamento de juntas pronto a pintar"],
    "menuiseries_int": ["o assentamento dos aros em coordenação com as divisórias", "as ferragens e batentes",
                        "a folga inferior das portas para passagem do ar", "as afinações e a proteção até à receção"],
    "sols_durs": ["a verificação da marcação de nível que define as cotas dos pavimentos acabados",
                  "os desenhos de esquartelamento dos revestimentos", "a apresentação de amostras à fiscalização",
                  "cortes, remates, soleiras e perfis de acabamento", "a proteção e limpeza dos revestimentos"],
    "sols_souples": ["a medição da humidade dos suportes e a regularização", "a apresentação de amostras à fiscalização",
                     "perfis de transição, rodapés e remates", "a proteção e limpeza dos revestimentos"],
    "peinture": ["a receção dos suportes e os trabalhos preparatórios adequados", "as proteções (plásticos, fitas)",
                 "as amostras de cor sobre catálogo", "a limpeza final com remoção das proteções"],
    "plomberie": ["os desenhos de preparação e de negativos", "os ensaios de estanquidade antes do fecho das courettes",
                  "a lavagem e desinfeção da rede antes da entrada em serviço", "a caixa do contador ou subcontador quando previsto"],
    "cvc": ["a nota de dimensionamento (carga térmica por compartimento)", "os negativos a comunicar às especialidades",
            "a colocação em serviço, a equilibragem e a medição dos caudais", "a formação do utilizador e as instruções de manutenção"],
    "electricite": ["o quadro de estaleiro e a iluminação provisória", "o elétrodo de terra e a medição da resistência de terra",
                    "o termo de responsabilidade pela execução e a inspeção da instalação",
                    "o termo de responsabilidade ITED", "as telas finais e esquemas dos quadros"],
}

LOTS_PAR_CODE = {lot["code"]: lot for lot in LOTS}


def references_autorisees(lot: dict) -> list[str]:
    """Lista branca dos documentos citáveis num capítulo."""
    return list(lot.get("refs") or [])

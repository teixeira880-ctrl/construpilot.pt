"""Moteur « études » OpenAI (Responses API) — prompt système fourni par l'utilisateur, schémas stricts."""

SYSTEM_PROMPT = "És o motor de assistência técnica do ConstruPilot para a análise de\ndocumentos de construção.\n\nAplicas em simultâneo a lógica profissional de um diretor de obra, de um\nmedidor-orçamentista, de um desenhador-projetista e de um arquiteto, sem\npretender substituir estes profissionais nem validar um estudo estrutural.\n\nO teu objetivo é examinar metodicamente o documento fornecido, reconstruir\nas cadeias de cotas, efetuar controlos cruzados e assinalar apenas\nas incoerências realmente demonstráveis.\n\nREGRA ABSOLUTA DE ÂMBITO\n\nAnalisa exclusivamente os documentos e as páginas realmente fornecidos no\npedido em curso.\n\nNunca presumas a existência ou o conteúdo:\n- de uma planta do R/C;\n- de um piso;\n- de uma cobertura;\n- de um corte;\n- de um alçado;\n- de uma planta de fundações;\n- de uma memória de cálculo;\n- de uma versão anterior;\n- ou de qualquer outro documento ausente.\n\nSe apenas for fornecida uma planta do desvão sanitário, limita a análise a essa planta.\n\nNunca analises sapatas, vigas de fundação, pilares, vigas, paredes, aberturas ou\noutros elementos situados fora do âmbito expressamente pedido.\n\nUma informação não visível deve ser classificada como «informação não fornecida»\nou «ilegível». Nunca deve ser inventada.\n\nLEITURA INICIAL\n\nAntes de qualquer conclusão:\n\n1. Identificar a legenda, o título, o nível, a escala, a data, o índice,\n   a orientação e as unidades, quando legíveis.\n2. Identificar a natureza real do documento.\n3. Definir o âmbito pedido pelo utilizador.\n4. Inventariar apenas os elementos efetivamente visíveis.\n5. Distinguir os traços do edifício das linhas de cota, eixos, tramas,\n   anotações, referências, símbolos e traços de corte.\n6. Assinalar qualquer informação ilegível antes de tentar um cálculo.\n\nANÁLISE DAS PAREDES E DA GEOMETRIA\n\nPara as paredes incluídas no âmbito:\n\n- identificar as paredes exteriores e interiores;\n- determinar a sua espessura apenas se estiver cotada ou for geometricamente\n  mensurável com uma escala fiável;\n- controlar as ligações, cantos, recuos e continuidades;\n- controlar os alinhamentos de fachadas e de paredes interiores resistentes;\n- procurar os desvios não cotados;\n- verificar a coerência entre largura interior, espessuras de paredes e largura\n  exterior;\n- verificar a coerência entre comprimento interior, espessuras de paredes e\n  comprimento exterior;\n- ter em conta cada parede atravessada nas cadeias de cotas;\n- nunca aplicar automaticamente uma espessura de 20 cm se a planta indicar\n  outra espessura ou se esta não puder ser confirmada.\n\nCONTROLO DAS COTAS\n\nPara cada cadeia de cotas:\n\n1. Registar as cotas parciais pela sua ordem geométrica.\n2. Identificar os seus pontos de partida e de chegada.\n3. Não somar cotas pertencentes a eixos ou cadeias diferentes.\n4. Acrescentar as espessuras de paredes realmente atravessadas quando a cota as\n   exclui.\n5. Comparar a soma calculada com a cota total correspondente.\n6. Indicar explicitamente:\n   - a fórmula;\n   - os valores utilizados;\n   - o resultado;\n   - a cota indicada;\n   - o desvio constatado;\n   - a unidade.\n7. Controlar a repetição de uma mesma dimensão em várias zonas.\n8. Controlar as cotas interiores em relação às dimensões exteriores.\n9. Verificar se um desvio pode ser explicado por uma espessura de parede, um\n   forro, uma junta, um desvio de eixo ou um limite de cotagem.\n10. Só declarar uma incoerência confirmada depois de eliminar as explicações\n    visíveis plausíveis.\n\nABERTURAS E ELEMENTOS CONSTRUTIVOS\n\nApenas quando fizerem parte do âmbito pedido:\n\n- identificar portas, janelas, vãos e reservas;\n- registar largura, altura, sentido de abertura, peitoril e padieira quando\n  indicados;\n- verificar a sua posição em relação às paredes, eixos e cadeias de cotas;\n- identificar vigas, pilares, sapatas, vigas de fundação, lajes, aberturas em laje, escadas,\n  redes, cobertura, impermeabilização e arranjos exteriores apenas se forem visíveis e pedidos;\n- nunca deduzir um dimensionamento estrutural ausente.\n\nMÉTODO DE VERIFICAÇÃO\n\nPara cada anomalia potencial:\n\n1. Formular a hipótese.\n2. Procurar uma cota ou anotação que a possa explicar.\n3. Refazer o cálculo por um segundo método.\n4. Verificar a unidade e a escala.\n5. Controlar se a cota se refere à face interior, à face exterior ou a um eixo.\n6. Verificar se uma cota é acumulada ou parcial.\n7. Comparar com outra ocorrência na mesma página.\n8. Atribuir um nível de confiança.\n9. Conservar as provas necessárias para que o utilizador possa controlar\n   o resultado.\n\nPROIBIÇÕES\n\n- Nunca inventar uma cota.\n- Nunca completar mentalmente uma parte oculta ou ilegível.\n- Nunca afirmar que um elemento existe noutra página não fornecida.\n- Nunca pôr em causa, criticar ou invalidar o gabinete de projeto de estruturas.\n- Nunca concluir que existe um erro estrutural.\n- Nunca apresentar uma hipótese como um facto.\n- Nunca afirmar que uma obra está conforme uma norma sem verificação\n  regulamentar explícita.\n- Nunca gerar uma conclusão global a partir de uma zona parcialmente\n  legível.\n- Nunca modificar os valores de origem para fazer corresponder os cálculos.\n\nCLASSIFICAÇÃO DOS RESULTADOS\n\nCada ponto deve ser classificado numa única categoria:\n\n- Conforme: o controlo está demonstrado e é coerente.\n- Incoerência confirmada: o desvio está quantificado e verificado duas vezes.\n- Incoerência provável: os indícios são sérios, mas falta uma informação.\n- A confirmar: várias interpretações continuam possíveis.\n- Informação insuficiente: a leitura ou o documento não permitem concluir.\n\nREDAÇÃO DO RELATÓRIO\n\nUtilizar um português europeu profissional, neutro, preciso e compreensível.\n\nCada observação deve indicar:\n- a página;\n- a zona em causa;\n- o elemento controlado;\n- as cotas registadas;\n- o cálculo efetuado;\n- o eventual desvio;\n- o nível de confiança;\n- a ação de verificação recomendada.\n\nO relatório nunca deve mencionar «limites da análise da planta».\n\nNão utilizar uma formulação que dê a entender que o ConstruPilot analisou\nplantas que não foram transmitidas.\n\nORÇAMENTOS E ATAS\n\nPara os orçamentos:\n- preservar todas as linhas, quantidades, unidades, preços unitários, taxas de IVA e\n  totais;\n- nunca suprimir um serviço sem instrução;\n- recalcular matematicamente os subtotais, IVA, descontos, adiantamentos e total c/ IVA;\n- assinalar qualquer diferença entre os valores de origem e os valores recalculados;\n- produzir um JSON estruturado antes de gerar o novo PDF.\n\nPara as atas:\n- separar factos observados, decisões, reservas, responsabilidades, prazos e\n  ações;\n- não atribuir uma decisão a uma pessoa se esta não for explicitamente\n  mencionada;\n- conservar as datas, locais, intervenientes e referências da obra;\n- utilizar uma redação factual e juridicamente prudente.\n\nDADOS DO MOTOR CONSTRUPILOT\n\nAs adições, subtrações, conversões de escala e controlos geométricos são efetuados pelo código\nConstruPilot (cotas vetoriais exatas, cadeias, fachadas opostas, elementos desenhados, cotas não alinhadas, medições\nautomáticas) e são-te fornecidos em JSON: interpreta-os, cruza-os com a tua leitura do documento, não os\nrecalcules a teu gosto e não inventes nenhuma medida ausente. Cada número da tua resposta provém ou do documento,\nou destes dados."

VERIFY_PROMPT = "És o CONTROLADOR INDEPENDENTE do ConstruPilot. Recebes o documento original, o JSON da primeira análise e\nos cálculos do motor ConstruPilot. Não refazes a análise: controla-la. Procura sistematicamente:\nas cotas esquecidas; as associações erradas de cadeias; os erros de unidade; as paredes mal contabilizadas;\nas conclusões não demonstradas; os elementos inventados (ausentes do documento e dos dados do motor); as\ncontradições internas; qualquer afirmação sobre um documento ou uma página não fornecidos; qualquer acusação ao gabinete de projeto de estruturas.\nCada constatação é classificada «bloqueante» (invalida uma conclusão) ou «menor». O relatório só pode ser marcado\n«verificado» se não houver anomalia bloqueante. Responde estritamente segundo o esquema JSON pedido, em português europeu profissional."

ANALYSIS_SCHEMA = {
 "type": "object",
 "properties": {
  "document_type": {
   "type": "string"
  },
  "analysis_scope": {
   "type": "array",
   "items": {
    "type": "string"
   }
  },
  "pages_analyzed": {
   "type": "array",
   "items": {
    "type": "integer"
   }
  },
  "plan_metadata": {
   "type": "object",
   "properties": {
    "title": {
     "type": [
      "string",
      "null"
     ]
    },
    "level": {
     "type": [
      "string",
      "null"
     ]
    },
    "scale": {
     "type": [
      "string",
      "null"
     ]
    },
    "revision": {
     "type": [
      "string",
      "null"
     ]
    },
    "date": {
     "type": [
      "string",
      "null"
     ]
    }
   },
   "required": [
    "title",
    "level",
    "scale",
    "revision",
    "date"
   ],
   "additionalProperties": False
  },
  "observed_elements": {
   "type": "array",
   "items": {
    "type": "object",
    "properties": {
     "page": {
      "type": "integer"
     },
     "element": {
      "type": "string"
     },
     "description": {
      "type": "string"
     }
    },
    "required": [
     "page",
     "element",
     "description"
    ],
    "additionalProperties": False
   }
  },
  "dimension_chains": {
   "type": "array",
   "items": {
    "type": "object",
    "properties": {
     "page": {
      "type": "integer"
     },
     "zone": {
      "type": "string"
     },
     "partials": {
      "type": "array",
      "items": {
       "type": "number"
      }
     },
     "total_indicated": {
      "type": [
       "number",
       "null"
      ]
     },
     "sum": {
      "type": [
       "number",
       "null"
      ]
     },
     "difference": {
      "type": [
       "number",
       "null"
      ]
     },
     "unit": {
      "type": "string"
     },
     "note": {
      "type": "string"
     }
    },
    "required": [
     "page",
     "zone",
     "partials",
     "total_indicated",
     "sum",
     "difference",
     "unit",
     "note"
    ],
    "additionalProperties": False
   }
  },
  "calculations": {
   "type": "array",
   "items": {
    "type": "object",
    "properties": {
     "id": {
      "type": "string"
     },
     "page": {
      "type": "integer"
     },
     "formula": {
      "type": "string"
     },
     "values": {
      "type": "array",
      "items": {
       "type": "number"
      }
     },
     "result": {
      "type": [
       "number",
       "null"
      ]
     },
     "indicated": {
      "type": [
       "number",
       "null"
      ]
     },
     "difference": {
      "type": [
       "number",
       "null"
      ]
     },
     "unit": {
      "type": "string"
     }
    },
    "required": [
     "id",
     "page",
     "formula",
     "values",
     "result",
     "indicated",
     "difference",
     "unit"
    ],
    "additionalProperties": False
   }
  },
  "alignment_checks": {
   "type": "array",
   "items": {
    "type": "object",
    "properties": {
     "page": {
      "type": "integer"
     },
     "zone": {
      "type": "string"
     },
     "result": {
      "type": "string",
      "enum": [
       "conforme",
       "ecart",
       "a_confirmer",
       "information_insuffisante"
      ]
     },
     "note": {
      "type": "string"
     }
    },
    "required": [
     "page",
     "zone",
     "result",
     "note"
    ],
    "additionalProperties": False
   }
  },
  "openings": {
   "type": "array",
   "items": {
    "type": "object",
    "properties": {
     "page": {
      "type": "integer"
     },
     "type": {
      "type": "string"
     },
     "width": {
      "type": [
       "number",
       "null"
      ]
     },
     "height": {
      "type": [
       "number",
       "null"
      ]
     },
     "note": {
      "type": "string"
     }
    },
    "required": [
     "page",
     "type",
     "width",
     "height",
     "note"
    ],
    "additionalProperties": False
   }
  },
  "inconsistencies": {
   "type": "array",
   "items": {
    "type": "object",
    "properties": {
     "id": {
      "type": "string"
     },
     "category": {
      "type": "string"
     },
     "page": {
      "type": [
       "integer",
       "null"
      ]
     },
     "zone": {
      "type": "string"
     },
     "observed_value": {
      "type": [
       "number",
       "null"
      ]
     },
     "calculated_value": {
      "type": [
       "number",
       "null"
      ]
     },
     "difference": {
      "type": [
       "number",
       "null"
      ]
     },
     "unit": {
      "type": "string"
     },
     "evidence": {
      "type": "array",
      "items": {
       "type": "string"
      }
     },
     "explanation": {
      "type": "string"
     },
     "possible_interpretations": {
      "type": "array",
      "items": {
       "type": "string"
      }
     },
     "status": {
      "type": "string",
      "enum": [
       "confirmed",
       "probable",
       "to_confirm",
       "insufficient_information"
      ]
     },
     "confidence": {
      "type": "number"
     },
     "recommended_action": {
      "type": "string"
     }
    },
    "required": [
     "id",
     "category",
     "page",
     "zone",
     "observed_value",
     "calculated_value",
     "difference",
     "unit",
     "evidence",
     "explanation",
     "possible_interpretations",
     "status",
     "confidence",
     "recommended_action"
    ],
    "additionalProperties": False
   }
  },
  "conforming_points": {
   "type": "array",
   "items": {
    "type": "string"
   }
  },
  "missing_information": {
   "type": "array",
   "items": {
    "type": "string"
   }
  },
  "points_to_confirm": {
   "type": "array",
   "items": {
    "type": "string"
   }
  },
  "report_summary": {
   "type": "string"
  },
  "conclusion": {
   "type": "string"
  },
  "global_confidence": {
   "type": "number"
  }
 },
 "required": [
  "document_type",
  "analysis_scope",
  "pages_analyzed",
  "plan_metadata",
  "observed_elements",
  "dimension_chains",
  "calculations",
  "alignment_checks",
  "openings",
  "inconsistencies",
  "conforming_points",
  "missing_information",
  "points_to_confirm",
  "report_summary",
  "conclusion",
  "global_confidence"
 ],
 "additionalProperties": False
}

VERIFY_SCHEMA = {
 "type": "object",
 "properties": {
  "verified": {
   "type": "boolean"
  },
  "findings": {
   "type": "array",
   "items": {
    "type": "object",
    "properties": {
     "severity": {
      "type": "string",
      "enum": [
       "bloquant",
       "mineur"
      ]
     },
     "category": {
      "type": "string"
     },
     "target_id": {
      "type": [
       "string",
       "null"
      ]
     },
     "description": {
      "type": "string"
     },
     "correction": {
      "type": "string"
     }
    },
    "required": [
     "severity",
     "category",
     "target_id",
     "description",
     "correction"
    ],
    "additionalProperties": False
   }
  },
  "corrected_inconsistency_ids_to_drop": {
   "type": "array",
   "items": {
    "type": "string"
   }
  },
  "summary": {
   "type": "string"
  },
  "confidence": {
   "type": "number"
  }
 },
 "required": [
  "verified",
  "findings",
  "corrected_inconsistency_ids_to_drop",
  "summary",
  "confidence"
 ],
 "additionalProperties": False
}

MENTION = {
 "fr": "Este documento constitui um controlo de coerência da planta {plan}, realizado pela ConstruPilot.fr por conta de {company}. Assinala unicamente as eventuais incoerências de geometria, alinhamento e cotagem visíveis no documento fornecido. Não altera, não valida nem põe em causa, em nenhum caso, os cálculos de estrutura ou os estudos realizados pelo gabinete de projeto competente.",
 "pt": "Este documento constitui um controlo de coerência da planta {plan}, realizado pela ConstruPilot.pt por conta de {company}. "
       "Assinala unicamente as eventuais incoerências de geometria, alinhamento e cotagem visíveis no documento fornecido. "
       "Não altera, não valida nem põe em causa, em nenhum caso, os cálculos de estrutura ou os estudos realizados pelo gabinete de projeto competente.",
}

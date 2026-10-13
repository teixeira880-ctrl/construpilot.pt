"""Prompt et schéma « dimensions intérieures mur à mur » (passes géométrie / cotations / rapprochement)."""

INTERIOR_PROMPT = "Deves controlar todas as dimensões interiores realmente visíveis no âmbito pedido.\n\nUma dimensão interior parede a parede é a distância perpendicular entre as duas faces interiores de duas paredes opostas.\nNão corresponde nem a uma distância entre eixos nem a uma simples dimensão exterior diminuída de duas paredes.\n\nComeça por inventariar todas as paredes e todos os vãos. Para cada fila horizontal e vertical, reconstrói a\nsucessão completa: parede exterior + espaço interior + parede interior + espaço interior + parede interior + espaço interior + parede exterior.\nConta todas as espessuras de paredes atravessadas.\n\nPara cada espaço, indica: a parede de partida; a face utilizada; a parede de chegada; a face utilizada; a cota escrita;\na medição geométrica; a diferença; o nível de confiança.\n\nSó podes declarar a análise concluída se cada espaço fechado visível tiver uma medição horizontal e uma medição\nvertical, ou uma justificação precisa que indique por que razão não pode ser determinada.\n\nNunca substituas as dimensões interiores individuais por uma única dimensão interior geral.\nNunca deduzas todas as dimensões apenas a partir das cotas exteriores.\nSe uma cota for ilegível, indica a sua localização e classifica-a como ilegível. Não a inventes.\n\nAntes de concluir, soma as dimensões interiores e todas as espessuras das paredes atravessadas. Compara o total obtido\ncom a dimensão exterior correspondente. Se o fecho não funcionar, procura primeiro: uma parede esquecida; uma face errada;\numa confusão eixo/face; uma cota associada ao segmento errado; uma cota parcial confundida com uma cota acumulada;\num erro de unidade; um texto de secção (50x30, 60x30) confundido com uma dimensão.\n\nREGRAS DE ASSOCIAÇÃO: uma cota vertical nunca é associada a um segmento horizontal; uma cota de espessura (0,13 / 0,20 m)\nnunca é um comprimento de vão; uma secção «50x30» nunca é uma cota parede a parede; duas dimensões de referências\ndiferentes (face/face, eixo/eixo, eixo/face, face ext./face ext.) nunca são comparadas diretamente; uma dimensão só se chama\n«fachada» se as suas extremidades forem as faces exteriores da fachada.\n\nO motor ConstruPilot fornece-te as paredes detetadas (duas faces, eixo, espessura), as medições interiores face a face, as\ncotas classificadas por tipo de referência e as equações de fecho, calculadas sobre os vetores exatos do PDF. CONTROLAS\nestas associações e raciocinas; não és um instrumento de medição píxel a píxel: nunca substituas um valor do\nmotor por uma estimativa visual, assinala antes o desacordo em `review_findings`. Escreve os textos em português europeu."

PASS_GEOMETRY = ("PASSAGEM 1 — GEOMETRIA. A partir do documento, das ampliações e das paredes detetadas pelo motor: verifica o inventário das paredes (duas faces, eixo, espessura, extremidades, interseções, continuidade, vãos). Assinala qualquer parede esquecida, qualquer par de traços que não seja uma parede (linha de cota, sapata, tracejado, traço de corte), qualquer face mal identificada. Classifica cada elemento com o REFERENCIAL DE SÍMBOLOS fornecido (parede resistente, divisória, parede de betão, pilar, viga, viga de fundação, sapata contínua/isolada, linha de cota, eixo da malha…): classe candidata, fonte (legenda > legenda da folha > marca > geometria > convenção), alternativas, confiança. Lê primeiro a legenda e o quadro da folha: prevalecem sobre a convenção geral. NÃO analises ainda as cotas escritas.")
PASS_DIMENSIONS = ("PASSAGEM 2 — COTAGEM. Para cada texto numérico: texto bruto, posição, orientação, linha de cota, linhas de chamada, pontos realmente cotados, unidade, distância geométrica, compatibilidade valor/segmento. Rejeita as associações incompatíveis (orientação, chamadas, extremidades, posição na cadeia, vizinhas). Classifica cada cota: face int./face int., face ext./face ext., eixo/eixo, eixo/face, vão, espessura, acumulada, parcial, estimada.")
PASS_RECONCILE = ("PASSAGEM 3 — COMPARAÇÃO. Compara geometria e cotagem: para cada espaço, cota escrita vs medição; reconstitui cada cadeia completa; fecha cada fila; localiza cada medição; decide sobre a completude.")

_S = {"type": "string"}
_NN = {"type": ["number", "null"]}
_SN = {"type": ["string", "null"]}

INTERIOR_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "walls": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "wall_id": _S, "orientation": {"type": "string", "enum": ["horizontal", "vertical", "inclined"]},
            "thickness_m": _NN, "role": {"type": "string", "enum": ["exterior", "interior", "unknown"]},
            "ouvrage_class": _S, "class_source": {"type": "string", "enum": ["legende", "cartouche", "repere", "geometrie", "convention"]},
            "class_alternatives": {"type": "array", "items": _S}, "associated_text": _S,
            "engine_agreement": {"type": "string", "enum": ["confirmed", "corrected", "rejected", "added"]},
            "comment": _S, "confidence": {"type": "number"}},
            "required": ["wall_id", "orientation", "thickness_m", "role", "ouvrage_class", "class_source", "class_alternatives", "associated_text",
                         "engine_agreement", "comment", "confidence"]}},
        "interior_measurements": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "measurement_id": _S, "direction": {"type": "string", "enum": ["horizontal", "vertical"]},
            "from_wall": _S, "from_face": _S, "to_wall": _S, "to_face": _S,
            "reference_type": {"type": "string", "enum": ["inside_face_to_inside_face", "outside_face_to_outside_face", "axis_to_axis",
                                                          "axis_to_face", "opening", "wall_thickness", "cumulative", "partial", "estimated"]},
            "written_dimension_m": _NN, "geometric_dimension_m": _NN, "difference_m": _NN, "page": {"type": "integer"},
            "status": {"type": "string", "enum": ["confirmed", "probable", "to_confirm", "unreadable"]},
            "justification": _S, "confidence": {"type": "number"}},
            "required": ["measurement_id", "direction", "from_wall", "from_face", "to_wall", "to_face", "reference_type",
                         "written_dimension_m", "geometric_dimension_m", "difference_m", "page", "status", "justification", "confidence"]}},
        "closure_equations": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "row_id": _S, "direction": {"type": "string", "enum": ["horizontal", "vertical"]}, "formula": _S,
            "sum_m": _NN, "exterior_dimension_m": _NN, "difference_m": _NN,
            "status": {"type": "string", "enum": ["closed", "open", "not_compared"]}, "explanation": _S},
            "required": ["row_id", "direction", "formula", "sum_m", "exterior_dimension_m", "difference_m", "status", "explanation"]}},
        "dimension_associations_rejected": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "raw_text": _S, "reason": _S, "location": _S}, "required": ["raw_text", "reason", "location"]}},
        "unreadable_dimensions": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "location": _S, "comment": _S}, "required": ["location", "comment"]}},
        "review_findings": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "target": _S, "finding": _S, "severity": {"type": "string", "enum": ["bloquant", "mineur"]}},
            "required": ["target", "finding", "severity"]}},
        "analysis_complete": {"type": "boolean"},
        "incompleteness_reasons": {"type": "array", "items": _S},
        "summary": _S,
    },
    "required": ["walls", "interior_measurements", "closure_equations", "dimension_associations_rejected", "unreadable_dimensions",
                 "review_findings", "analysis_complete", "incompleteness_reasons", "summary"],
}

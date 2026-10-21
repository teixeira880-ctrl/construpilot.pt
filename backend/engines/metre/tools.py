"""Function-calling contracts for the deterministic metré engine (validated server-side before execution)."""
from . import calibration, chains, dedupe, quantities

NUM_OR_NULL = {"type": ["number", "null"]}
STR_OR_NULL = {"type": ["string", "null"]}

READING = {"type": "object", "properties": {
    "label": {"type": "string"}, "value_m": NUM_OR_NULL,
    "candidates_m": {"type": "array", "items": {"type": "number"}, "description": "Leituras OCR concorrentes se o valor não estiver resolvido"},
    "origin": {"type": "string", "enum": ["plan_reading", "native_text", "user_statement", "assumption"]},
    "plan_id": STR_OR_NULL, "page": {"type": ["integer", "null"]},
    "box": {"type": ["array", "null"], "items": {"type": "number"}, "description": "Zona de origem da cota na página, normalizada [x0,y0,x1,y1] (0-1)"}},
    "required": ["label", "value_m", "candidates_m", "origin", "plan_id", "page", "box"], "additionalProperties": False}


def _fn(name, description, properties):
    return {"type": "function", "name": name, "description": description, "strict": True,
            "parameters": {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}}


METRE_TOOLS = [
    _fn("check_dimension_chain",
        "Soma determinística de uma cadeia de cotas: vãos interiores + espessuras das paredes realmente atravessadas, comparada com o total declarado. Nunca volta a acrescentar as espessuras se a cadeia já as incluir. reference=\'axes\': meias-espessuras nas paredes de extremidade. Qualquer leitura não resolvida torna o resultado indeterminado.",
        {"spans": {"type": "array", "items": READING}, "thicknesses": {"type": "array", "items": READING},
         "chain_includes_thickness": {"type": "boolean"}, "reference": {"type": "string", "enum": ["faces", "axes"]},
         "declared_total": {"anyOf": [READING, {"type": "null"}]}}),
    _fn("compare_dimension_values",
        "Diferença aritmética entre dois valores do mesmo intervalo. Se o intervalo ou a referência diferirem, a diferença é documentada sem ser classificada como incoerência.",
        {"a": READING, "b": READING, "same_interval": {"type": "boolean"}, "same_reference": {"type": "boolean"}}),
    _fn("resolve_ambiguous_reading",
        "Decide uma leitura OCR ambígua (ex.: 13,27 / 13,72) APENAS com uma prova independente: texto nativo PDF, ampliação, declaração do utilizador. A concordância aritmética nunca é uma prova.",
        {"label": {"type": "string"}, "candidates_m": {"type": "array", "items": {"type": "number"}},
         "confirmations": {"type": "array", "items": {"type": "object", "properties": {
             "kind": {"type": "string", "enum": ["native_text", "zoom_crop", "user_statement", "arithmetic_fit"]}, "value_m": {"type": "number"}, "ref": STR_OR_NULL},
             "required": ["kind", "value_m", "ref"], "additionalProperties": False}},
         "arithmetic_fit_m": NUM_OR_NULL}),
    _fn("classify_strokes",
        "Classifica traços (camada, padrão, setas) em tracejado / mobiliário / eixo / linha de cota / oculto / parede… Os traços não construtivos ou não classificados nunca entram numa medição.",
        {"strokes": {"type": "array", "items": {"type": "object", "properties": {
            "stroke_id": {"type": "string"}, "kind": STR_OR_NULL, "layer": STR_OR_NULL, "pattern": STR_OR_NULL,
            "has_arrowheads": {"type": "boolean"}, "has_ticks": {"type": "boolean"}},
            "required": ["stroke_id", "kind", "layer", "pattern", "has_arrowheads", "has_ticks"], "additionalProperties": False}}}),
    _fn("dedupe_elements",
        "Unifica as observações de um mesmo elemento visto em planta, alçado, lista ou pormenor (marca F1/P02, ou posição). Conta cada elemento uma vez e conserva todas as provas.",
        {"observations": {"type": "array", "items": {"type": "object", "properties": {
            "obs_id": {"type": "string"}, "element_type": {"type": "string"}, "tag": STR_OR_NULL,
            "view": {"type": "string", "enum": ["plan", "section", "elevation", "schedule", "detail", "other"]},
            "dimensions": {"type": "object", "properties": {"width_m": NUM_OR_NULL, "height_m": NUM_OR_NULL, "length_m": NUM_OR_NULL},
                           "required": ["width_m", "height_m", "length_m"], "additionalProperties": False},
            "location": {"type": "object", "properties": {"level": STR_OR_NULL, "x_m": NUM_OR_NULL, "y_m": NUM_OR_NULL},
                         "required": ["level", "x_m", "y_m"], "additionalProperties": False}},
            "required": ["obs_id", "element_type", "tag", "view", "dimensions", "location"], "additionalProperties": False}}}),
    _fn("calculate_quantities",
        "Quantidades por categoria com fórmula, deduções, líquido e estado. wall_area: C × A − vãos segundo deduction_rule EXPLÍCITA (full/none/threshold); altura ausente → só o comprimento. concrete_volume: implantação × altura, sem altura → só a implantação. roof_area: sem inclinação → área projetada. packaged_units: quantidade aplicada vs a encomendar. Nenhuma perda sem extra_pct/waste_pct explícito.",
        {"items": {"type": "array", "items": {"type": "object", "properties": {
            "category": {"type": "string", "enum": ["wall_area", "concrete_volume", "roof_area", "packaged_units"]},
            "element": {"type": "string"}, "location": STR_OR_NULL, "sources": {"type": "array", "items": {"type": "string"}},
            "length_m": NUM_OR_NULL, "height_m": NUM_OR_NULL, "width_m": NUM_OR_NULL, "area_m2": NUM_OR_NULL,
            "openings": {"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}, "width_m": NUM_OR_NULL, "height_m": NUM_OR_NULL},
                                                    "required": ["label", "width_m", "height_m"], "additionalProperties": False}},
            "deduction_rule": {"type": ["string", "null"], "enum": ["full", "none", "threshold", None]}, "deduction_threshold_m2": NUM_OR_NULL,
            "extra_pct": NUM_OR_NULL, "plan_area_m2": NUM_OR_NULL, "slope_deg": NUM_OR_NULL,
            "net_quantity": NUM_OR_NULL, "units_per_measure": NUM_OR_NULL, "pack_size": NUM_OR_NULL, "waste_pct": NUM_OR_NULL,
            "product": STR_OR_NULL, "unit": STR_OR_NULL},
            "required": ["category", "element", "location", "sources", "length_m", "height_m", "width_m", "area_m2", "openings", "deduction_rule",
                         "deduction_threshold_m2", "extra_pct", "plan_area_m2", "slope_deg", "net_quantity", "units_per_measure", "pack_size",
                         "waste_pct", "product", "unit"], "additionalProperties": False}}}),
]
METRE_TOOLS += [
    _fn("calibrate_view",
        "Calibra a escala de UMA vista ou de UM pormenor a partir das suas cotas explícitas legíveis (comprimento em píxeis ↔ valor). Deteta escalas múltiplas, deformação h/v de uma digitalização e diferença face à escala da legenda (PDF redimensionado). Uma calibração só vale para a sua vista.",
        {"view_id": {"type": "string"}, "references": {"type": "array", "items": {"type": "object", "properties": {
            "label": {"type": "string"}, "value_m": {"type": "number"}, "px_length": {"type": "number"}, "axis": {"type": ["string", "null"], "enum": ["h", "v", None]}},
            "required": ["label", "value_m", "px_length", "axis"], "additionalProperties": False}},
         "declared_scale": STR_OR_NULL, "dpi": NUM_OR_NULL}),
    _fn("measure_pixels",
        "Converte um comprimento medido em píxeis com a calibração de uma vista (resultado de calibrate_view). Recusado se a calibração não for fiável: nenhuma medição em píxeis é então apresentada como confirmada.",
        {"calibration": {"type": "object", "properties": {"view_id": {"type": "string"}, "status": {"type": "string", "enum": ["reliable", "per_axis", "unreliable"]},
                                                          "px_per_m": NUM_OR_NULL, "px_per_m_by_axis": {"type": ["object", "null"], "properties": {"h": NUM_OR_NULL, "v": NUM_OR_NULL},
                                                                                                        "required": ["h", "v"], "additionalProperties": False},
                                                          "measurements_allowed": {"type": "boolean"}, "spread_pct": NUM_OR_NULL, "reasons": {"type": "array", "items": {"type": "string"}}},
                         "required": ["view_id", "status", "px_per_m", "px_per_m_by_axis", "measurements_allowed", "spread_pct", "reasons"], "additionalProperties": False},
         "label": {"type": "string"}, "px_length": {"type": "number"}, "axis": {"type": ["string", "null"], "enum": ["h", "v", None]}}),
]
METRE_TOOL_NAMES = {t["name"] for t in METRE_TOOLS}

METRE_INSTRUCTIONS = "Para cada leitura proveniente de uma planta anexada, indica plan_id, página e box (zona normalizada da cota) para que o utilizador\npossa abrir o recorte e corrigir a leitura. Medição e controlo de cotas: qualquer cálculo (soma de cadeia, diferença entre cotas, área, volume, dedução, contagem) passa pelas ferramentas\ncheck_dimension_chain, compare_dimension_values, resolve_ambiguous_reading, classify_strokes, dedupe_elements e calculate_quantities; nunca calcules\nestes valores de cabeça. Apresenta as suas entradas, fórmulas, resultados e estados (confirmado / provável / indeterminado / não verificável) tal como devolvidos.\nQualquer medição em píxeis passa por calibrate_view (por vista / pormenor) e depois measure_pixels; sem calibração fiável, só são utilizadas as cotas explícitas.\nUma diferença entre cotas é um ponto de leitura ou de coerência a esclarecer, nunca uma acusação de erro de cálculo do gabinete de projeto. Nenhuma tolerância\nde execução, nenhuma percentagem de perda e nenhuma regra de dedução são aplicadas sem serem explicitamente pedidas ou referenciadas.\nPlantas de estrutura (armaduras, vigas, lajes): um estudo de obra tem-nas em conta tal como a arquitetura. As listas de aços e\nde malhas leem-se com read_rebar_schedule (nunca de cabeça); as massas, totais e diferenças face aos resumos são os devolvidos pela ferramenta. Uma\nlista marcada «parcial» não permite nenhuma extrapolação para o piso completo.\nVolumes de betão de um piso (paredes, pilares, laje, alturas de vigas): apenas com compute_concrete_volumes, passando-lhe o DXF/DWG do piso, a planta de\ncofragem PDF e o caderno de cortes se estiverem anexados. Regra dos níveis: a cota superior das paredes é a cota inferior do pavimento superior (AS pavimento −\nespessura), salvo indicação em contrário impressa; a altura é tomada por zona de corte. Apresenta os volumes por elemento com a fórmula, a fonte de cada\nnível e o estado devolvidos; se faltar um dado (nível de base, espessura, altura de viga), pede-o ao utilizador em vez de o supor. A leitura\nvisual do caderno de cortes é faturada: só passes allow_vision=true com o acordo do utilizador (ou se os cortes já tiverem sido lidos)."


def run_metre_tool(name: str, args: dict) -> dict:
    if name == "check_dimension_chain":
        clean = {k: v for k, v in args.items() if k != "declared_total"}
        return {"ok": True, **chains.check_dimension_chain(**clean, declared_total=args.get("declared_total"))}
    if name == "compare_dimension_values":
        return {"ok": True, **chains.compare_values(args["a"], args["b"], same_interval=args["same_interval"], same_reference=args["same_reference"])}
    if name == "resolve_ambiguous_reading":
        return {"ok": True, **chains.resolve_reading(label=args["label"], candidates_m=args["candidates_m"],
                                                     confirmations=args.get("confirmations"), arithmetic_fit_m=args.get("arithmetic_fit_m"))}
    if name == "classify_strokes":
        return {"ok": True, **dedupe.classify_strokes(args["strokes"])}
    if name == "dedupe_elements":
        return {"ok": True, **dedupe.dedupe_elements(args["observations"])}
    if name == "calculate_quantities":
        return {"ok": True, **quantities.calculate_quantities(args["items"])}
    if name == "calibrate_view":
        return {"ok": True, **calibration.calibrate_view(view_id=args["view_id"], references=args["references"],
                                                          declared_scale=args.get("declared_scale"), dpi=args.get("dpi"))}
    if name == "measure_pixels":
        return {"ok": True, **calibration.measure_pixels(calibration=args["calibration"], label=args["label"], px_length=args["px_length"], axis=args.get("axis"))}
    return {"ok": False, "error": "Ferramenta de medição desconhecida"}

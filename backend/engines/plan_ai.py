"""AI Plan Interpreter — utilise GPT-Vision pour comprendre un plan 2D.

⚠️ Ce module **ne calcule PAS** les mesures. Il extrait des indices sémantiques :
- pièces détectées avec noms et surfaces textuelles inscrites sur le plan
- ouvertures probables (portes, fenêtres)
- échelle éventuelle
- warnings (plan de mauvaise qualité, échelle absente, etc.)

Les calculs géométriques restent la responsabilité du `geometry.py`.
"""
from __future__ import annotations

import json
import logging
import os
import re

from engines.plan_principles import CORE_PRINCIPLES
from engines.llm_keys import studies_key

logger = logging.getLogger(__name__)


PROMPT = "És um **especialista em estrutura, alvenarias e medições da construção** com 25 anos de experiência\n(alvenaria, estrutura de cobertura, vãos, escadas). Analisas uma planta de arquitetura 2D e\nproduzes um **levantamento de medições exaustivo pronto a orçamentar**, distinguindo claramente:\n- as **linhas de cota** (linhas finas com setas + valor numérico) — NÃO as contes como paredes\n- os **desenhos de paredes** (traços espessos, tracejados cheios, preenchimento betão/bloco)\n- os **vãos / negativos** (portas, janelas, envidraçados, aberturas de escadas, courettes técnicas)\n- os **materiais e especificações** inscritos em texto (revestimentos de pavimento, isolantes, acabamentos, certificado energético)\n\nDevolve ESTRITAMENTE JSON (sem markdown, sem texto fora do JSON) com ESTA estrutura (mantém as chaves e os valores enumerados tal como indicados):\n\n{\n  \"plan_type\": \"residential\" | \"commercial\" | \"facade\" | \"coupe\" | \"unknown\",\n  \"detected_scale\": \"1:50\" | \"1:100\" | \"1:200\" | null,\n  \"quality\": \"excellent\" | \"good\" | \"poor\" | \"unreadable\",\n  \"warnings\": [\"texte libre : plan flou / échelle absente / etc.\"],\n\n  \"rooms\": [\n    {\n      \"name\": \"Salon\",\n      \"surface_written_m2\": 32.40,      // si inscrit sur le plan, sinon null\n      \"estimated_surface_m2\": 32.5,     // ton estimation à partir des cotes visibles\n      \"perimeter_estimated_m\": 22.8,    // périmètre estimé (mètres linéaires)\n      \"ceiling_height_m\": 2.50,         // hauteur sous plafond si indiquée\n      \"level\": \"RDC\" | \"R+1\" | \"R-1\" | \"combles\" | null,\n      \"notes\": \"traversant sud-nord, exposition principale sud\",\n      \"floor_material\": \"carrelage\" | \"parquet\" | \"béton\" | \"moquette\" | \"vinyle\" | null,\n      \"floor_note_text\": \"citation textuelle du plan si présente (ex: \'Carrelage 60x60 gris\')\"\n    }\n  ],\n\n  \"dimension_lines\": [\n    // Traits de cote lus sur le plan (lignes fines + flèches + valeur)\n    // Ne PAS confondre avec les murs !\n    // bbox_norm = coordonnées NORMALISÉES 0-1 de la ligne de cote sur l\'image\n    //   [x1, y1, x2, y2] où (x1,y1) et (x2,y2) sont les extrémités du trait de cote.\n    //   x=0 = bord gauche, x=1 = bord droit ; y=0 = haut, y=1 = bas.\n    {\"value_m\": 3.42, \"location\": \"façade sud\",\n     \"orientation\": \"horizontale\" | \"verticale\" | \"oblique\",\n     \"bbox_norm\": [0.12, 0.34, 0.48, 0.34],\n     \"confidence\": 0.0-1.0}\n  ],\n\n  \"wall_types\": {\n    // Distinction visuelle : trait épais = mur, hachures = béton/parpaing, double-trait = doublage\n    \"load_bearing_visible\": true,       // murs porteurs identifiés (traits pleins épais)\n    \"partition_visible\": true,          // cloisons (traits fins pleins)\n    \"insulation_layer_visible\": false,  // doublage / isolation représenté (double trait)\n    \"hatching_present\": \"béton\" | \"parpaing\" | \"brique\" | \"pierre\" | \"aucun\",\n    \"notes\": \"légende à interpréter si présente\"\n  },\n\n  \"facade_walls\": [\n    // Murs extérieurs (façades) : chaque orientation ou pan\n    {\n      \"orientation\": \"sud\" | \"nord\" | \"est\" | \"ouest\" | \"sud-est\" | \"nord-ouest\" | \"unknown\",\n      \"length_m\": 12.4,\n      \"height_m\": 2.50,\n      \"area_gross_m2\": 31.0,             // longueur × hauteur (avant déduction ouvertures)\n      \"openings_area_m2\": 6.2,           // total portes+fenêtres+baies sur cette façade\n      \"area_net_m2\": 24.8,               // net (à peindre / ravaler / isoler)\n      \"wall_type\": \"porteur\" | \"cloison\" | \"doublage\",\n      \"material_guess\": \"parpaing\" | \"béton\" | \"brique\" | \"bois\" | \"pierre\" | \"unknown\"\n    }\n  ],\n\n  \"interior_walls\": {\n    \"total_length_m\": 45.0,              // linéaire total cloisons intérieures\n    \"load_bearing_length_m\": 12.0,       // sous-total murs porteurs internes\n    \"partition_length_m\": 33.0,          // sous-total cloisons\n    \"total_area_gross_m2\": 112.5         // linéaire × hauteur moyenne\n  },\n\n  \"openings\": {\n    // Ouvertures RÉSERVÉES dans les murs (portes, fenêtres, baies, trémies, gaines VMC/plomberie)\n    \"doors_visible\": 5,\n    \"windows_visible\": 8,\n    \"bays_visible\": 2,\n    \"reservations_visible\": 0,            // trémies gaines techniques ≠ portes/fenêtres\n    \"details\": [\n      {\"kind\": \"porte\" | \"fenetre\" | \"baie\" | \"porte-fenetre\" | \"velux\" | \"reservation\",\n       \"location\": \"salon-sud\" | \"cuisine-est\" | \"escalier\" | ...,\n       \"width_m\": 0.90, \"height_m\": 2.10, \"count\": 1,\n       \"area_m2\": 1.89,\n       \"symbol_note\": \"arc de porte 90° / vitrage double / linteau BA / ...\"}\n    ],\n    \"total_openings_area_m2\": 24.5\n  },\n\n  \"stairwells\": [\n    // Trémies + emprise escaliers\n    {\"location\": \"central\" | \"façade-est\" | ...,\n     \"type\": \"droit\" | \"quart-tournant\" | \"hélicoïdal\" | \"unknown\",\n     \"trémie_area_m2\": 3.2,              // trou de plancher\n     \"footprint_m2\": 4.5,                // emprise au sol\n     \"steps\": 14, \"riser_height_m\": 0.17, \"tread_depth_m\": 0.28,\n     \"connects_levels\": [\"RDC\", \"R+1\"]}\n  ],\n\n  \"floors\": {\n    \"ground_floor_area_m2\": 92.0,        // dalle RDC (sur terre-plein ou vide sanitaire)\n    \"upper_floors_area_m2\": 78.0,        // planchers intermédiaires (bois / béton)\n    \"total_floor_slab_m2\": 170.0,\n    \"slab_thickness_m\": 0.20,            // épaisseur estimée dalle béton\n    \"floor_type\": \"béton-plein\" | \"hourdis\" | \"poutres-bois\" | \"unknown\"\n  },\n\n  \"materials_notes\": [\n    // Textes/légendes lus sur le plan qui décrivent des matériaux ou spécifications\n    {\"text_verbatim\": \"Carrelage grès cérame 60x60 antidérapant\",\n     \"category\": \"revêtement_sol\" | \"isolation\" | \"menuiserie\" | \"peinture\" | \"cloison\" |\n                 \"toiture\" | \"façade\" | \"réglementaire\" | \"autre\",\n     \"location_on_plan\": \"salle de bain\" | \"légende bas-droit\" | ...,\n     \"quantity_hint\": \"42 m²\" | null}\n  ],\n\n  \"client_info\": {\n    // Infos client / maître d\'ouvrage détectées dans le cartouche du plan ou l\'imprimé\n    // Permis de Construire (souvent en bas de page ou en légende). Mets \"detected\": false\n    // si rien n\'est lisible. Ne devine jamais : n\'extrais que ce qui est écrit.\n    \"detected\": true | false,\n    \"first_name\": \"Jean\" | null,\n    \"last_name\": \"Dupont\" | null,\n    \"company\": \"SCI ...\" | null,\n    \"email\": null,\n    \"phone\": \"06 12 34 56 78\" | null,\n    \"address\": \"12 rue des Lilas\" | null,\n    \"postal_code\": \"75011\" | null,\n    \"city\": \"Paris\" | null\n  },\n\n  \"electrical\": {\n    // Symboles électriques repérés (norme NF C 15-100) — analyse les pictogrammes\n    \"outlets\": 0,            // prises de courant (cercle + 2 traits / \"PC\")\n    \"switches\": 0,           // interrupteurs (simple, va-et-vient, va-et-vient double)\n    \"light_points\": 0,       // points lumineux / plafonniers (croix ou \"x\" dans un cercle)\n    \"spots\": 0,              // spots encastrés\n    \"panels\": 0,             // tableaux électriques / GTL / coffrets\n    \"network_tv\": 0,         // prises RJ45 / TV / téléphone / fibre\n    \"details\": [\n      {\"kind\": \"prise\" | \"interrupteur\" | \"point_lumineux\" | \"spot\" | \"tableau\" | \"rj45\" | \"tv\" | \"autre\",\n       \"room\": \"Salon\" | ..., \"count\": 1, \"symbol_note\": \"prise 16A / va-et-vient / applique / ...\"}\n    ]\n  },\n\n  \"plumbing\": {\n    // Symboles plomberie / sanitaires repérés (pictogrammes des appareils)\n    \"wc\": 0, \"washbasins\": 0, \"showers\": 0, \"bathtubs\": 0,\n    \"kitchen_sinks\": 0, \"water_heaters\": 0, \"washing_machines\": 0,\n    \"supply_points\": 0,      // arrivées d\'eau (EF/EC)\n    \"drains\": 0,             // évacuations / siphons de sol\n    \"details\": [\n      {\"kind\": \"wc\" | \"lavabo\" | \"douche\" | \"baignoire\" | \"evier\" | \"chauffe_eau\" |\n               \"lave_linge\" | \"arrivee_eau\" | \"evacuation\" | \"autre\",\n       \"room\": \"Salle de bain\" | ..., \"count\": 1, \"symbol_note\": \"douche 90x90 / vasque double / ...\"}\n    ]\n  },\n\n  \"totals_gros_oeuvre\": {\n    \"linear_walls_m\": 92.5,              // TOTAL linéaire murs (façades + intérieurs)\n    \"facade_walls_area_net_m2\": 145.0,   // TOTAL m² murs extérieurs à ravaler/isoler\n    \"interior_walls_area_m2\": 112.5,     // TOTAL m² cloisons/refends intérieurs\n    \"openings_area_m2\": 24.5,            // TOTAL surface ouvertures\n    \"floor_slab_area_m2\": 170.0,         // TOTAL surface planchers/dalles\n    \"concrete_volume_m3_estimated\": 34.0,// volume béton estimé (dalles + linteaux)\n    \"confidence\": 0.0-1.0\n  },\n\n  \"total_surface_written_m2\": 170.0,\n  \"confidence\": 0.0-1.0\n}\n\nREGRAS CRÍTICAS:\n- **NUNCA confundir linhas de cota e paredes.** As linhas de cota são finas, têm setas\n  ou traços nas extremidades e têm um valor numérico («3.42», «342» cm). As paredes\n  são desenhadas com traço espesso cheio, muitas vezes com tracejado ou preenchimento.\n- **Distingue os vãos/negativos**: arco de porta = porta; retângulo envidraçado numa\n  parede = janela/envidraçado; grande abertura no pavimento = abertura de escada; pequeno quadrado com a etiqueta\n  «ventilação / courette» = negativo técnico.\n- **Copia os textos literalmente** em `materials_notes` para tudo o que descreva um material\n  ou uma especificação («isolamento lã de rocha 200 mm», «tinta mate branca», etc.).\n- **Interpreta os símbolos técnicos**: conta e localiza os símbolos **elétricos**\n  (tomadas, interruptores, pontos de luz, focos, quadro, RJ45/TV) em `electrical`,\n  e os símbolos de **canalização/sanitários** (sanita, lavatório, duche, banheira, lava-loiça, termoacumulador,\n  máquina de lavar, alimentações/esgotos) em `plumbing`. Associa cada símbolo à sua divisão.\n  Se nenhum símbolo técnico for visível, deixa os contadores a 0 e `details` vazio.\n- És ESPECIALISTA — utiliza ordens de grandeza realistas (pé-direito 2.50m\n  por omissão, espessura da laje 0.20m, porta 0.90×2.10, janela 1.20×1.20…).\n- Se a escala estiver escrita («1:100») utiliza-a para afinar os comprimentos.\n- Se não conseguires determinar um valor com certeza suficiente, põe `null`\n  (nunca 0 por omissão, nunca adivinhar às cegas).\n- Distingue **fachadas (exterior)** das **divisórias/paredes interiores**.\n- Deteta as aberturas de escada (retângulo vazio no pavimento) e dá a implantação.\n- Preenche sempre `totals_gros_oeuvre` — é a parte mais crítica para a\n  orçamentação. Soma de forma coerente os subtotais.\n- Os valores textuais livres (nomes de divisões, notas, localizações) são escritos em português europeu.\n- Responde APENAS com o JSON, sem markdown, sem comentário.\n"


def plan_model() -> tuple[str, str]:
    """Modèle IA pour la lecture de plans : PLAN_AI_MODEL='provider:model' (défaut GPT-5.5, le plus fort en raisonnement+vision)."""
    raw = os.environ.get("PLAN_AI_MODEL") or "openai:gpt-5.5"
    provider, _, model = raw.partition(":")
    return (provider or "openai"), (model or "gpt-5.5")


async def _call_gpt_vision(image_b64_png: str, api_key: str, prompt: str | None = None, lang: str = "pt") -> str:
    """Send the plan image to the configured vision model and return raw text."""
    from emergentintegrations.llm.chat import ImageContent, UserMessage

    from engines.expenses.metering import MeteredChat as LlmChat
    from engines.plan_geometry_prompt import LANG_INSTRUCTION
    provider, model = plan_model()
    chat = LlmChat(
        api_key=api_key,
        session_id="plan-analyze", expense_feature="plan_analysis",
        system_message=CORE_PRINCIPLES + "\n\nRespondes sempre em JSON estrito, sem markdown. As chaves JSON ficam tal como pedidas; os VALORES textuais (nomes de divisões, localizações, notas): "
        + LANG_INSTRUCTION.get(lang, LANG_INSTRUCTION["fr"]),
    ).with_model(provider, model)
    msg = UserMessage(
        text=prompt or PROMPT,
        file_contents=[ImageContent(image_base64=image_b64_png)],
    )
    return await chat.send_message(msg)


COTES_PROMPT = "És um medidor especialista. Regista TODAS as cotas (linhas de cota) inscritas nesta planta,\nsem exceção: cotas exteriores totais, cotas parciais (cadeias), cotas interiores de divisões,\ncotas de vãos, cotas verticais e horizontais. Não confundas uma parede com uma linha de cota.\n\nResponde APENAS em JSON estrito:\n{\n  \"scale_text\": \"1:50\" | null,\n  \"units_hint\": \"cm\" | \"m\" | \"mm\" | null,\n  \"dimension_lines\": [\n    {\"value_m\": 3.42,                 // valeur convertie en MÈTRES (342 cm → 3.42 ; 3420 mm → 3.42)\n     \"raw_text\": \"342\",               // texte exactement tel qu\'inscrit sur le plan\n     \"orientation\": \"horizontale\" | \"verticale\" | \"oblique\",\n     \"location\": \"façade sud, cote totale\" | \"salon, largeur\" | \"fenêtre cuisine\" | ...,\n     \"bbox_norm\": [x1, y1, x2, y2],   // extrémités EXACTES du trait de cote (entre les 2 traits d\'attache),\n                                      // normalisées 0-1 : x=0 bord gauche, x=1 bord droit, y=0 haut, y=1 bas\n     \"confidence\": 0.0-1.0}\n  ]\n}\nRegras: uma entrada por cota lida; para uma cota horizontal y1 == y2, para uma vertical x1 == x2;\nsê o mais preciso possível nas extremidades (servem para medir o traço); não inventes nenhum valor."


async def read_dimension_lines(image_b64_png: str, lang: str = "pt") -> dict:
    """Lecture dédiée de toutes les cotes du plan (valeur + position du trait)."""
    api_key = studies_key(plan_model()[0])
    if not api_key:
        return {"error": "EMERGENT_LLM_KEY absent", "dimension_lines": []}
    try:
        raw = await _call_gpt_vision(image_b64_png, api_key, prompt=COTES_PROMPT, lang=lang)
        data = _parse_json_response(raw)
    except Exception as e:
        from engines.llm_keys import note_openai_error
        if await note_openai_error(e):
            return await read_dimension_lines(image_b64_png, lang)
        logger.warning(f"AI cotes reading failed: {e}")
        return {"error": f'Leitura IA das cotas impossível: {type(e).__name__}', "dimension_lines": []}
    return {"scale_text": data.get("scale_text"), "units_hint": data.get("units_hint"),
            "dimension_lines": _clean_dimension_lines(data.get("dimension_lines") or [])}


def _parse_json_response(raw: str) -> dict:
    """Extract & parse JSON from a GPT text response (strips markdown fences)."""
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(txt)
    except Exception:
        # Fallback : find first {...} block in the response
        m = re.search(r"\{[\s\S]*\}", txt)
        if not m:
            return {"error": "AI response not JSON", "raw": txt[:200], "confidence": 0.0}
        try:
            return json.loads(m.group(0))
        except Exception as e:
            return {"error": f"JSON parse: {e}", "raw": txt[:200], "confidence": 0.0}


def _clean_dimension_lines(items: list) -> list:
    """Valide et normalise les traits de cote : garde `bbox_norm` si présent et bien formé."""
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        bbox = it.get("bbox_norm")
        # Un bbox_norm valide = liste/tuple de 4 floats dans [0, 1]
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            try:
                bbox = [max(0.0, min(1.0, float(v))) for v in bbox]
                it["bbox_norm"] = bbox
            except (TypeError, ValueError):
                it.pop("bbox_norm", None)
        else:
            it.pop("bbox_norm", None)
        out.append(it)
    return out


def _normalize_analysis(data: dict) -> dict:
    """Ensure all gros-œuvre fields exist so the front never crashes on undefined."""
    data.setdefault("rooms", [])
    data.setdefault("openings", {})
    data.setdefault("warnings", [])
    data.setdefault("facade_walls", [])
    data.setdefault("interior_walls", {})
    data.setdefault("stairwells", [])
    data.setdefault("floors", {})
    data.setdefault("totals_gros_oeuvre", {})
    data["dimension_lines"] = _clean_dimension_lines(data.get("dimension_lines") or [])
    data.setdefault("wall_types", {})
    data.setdefault("materials_notes", [])
    data.setdefault("electrical", {})
    data.setdefault("plumbing", {})
    data.setdefault("client_info", {})
    if isinstance(data.get("electrical"), dict):
        data["electrical"].setdefault("details", [])
    if isinstance(data.get("plumbing"), dict):
        data["plumbing"].setdefault("details", [])
    if isinstance(data.get("openings"), dict):
        data["openings"].setdefault("details", [])
        data["openings"].setdefault("reservations_visible", 0)
    return data


async def analyze_plan_image(image_b64_png: str, lang: str = "pt") -> dict:
    """Send a PNG plan image to GPT-Vision and return the parsed gros-œuvre JSON.

    Always returns a dict — errors are surfaced via the `error` key.
    """
    api_key = studies_key(plan_model()[0])
    if not api_key:
        return {"error": "EMERGENT_LLM_KEY absent", "confidence": 0.0}
    try:
        raw = await _call_gpt_vision(image_b64_png, api_key, lang=lang)
    except ImportError:
        logger.error("emergentintegrations not installed")
        return {"error": "AI unavailable", "confidence": 0.0}
    except Exception as e:
        from engines.llm_keys import note_openai_error
        if await note_openai_error(e):
            return await analyze_plan_image(image_b64_png, lang)
        logger.warning(f"AI plan analysis failed: {e}")
        return {"error": f"AI call failed: {type(e).__name__}", "confidence": 0.0}
    return _normalize_analysis(_parse_json_response(raw))

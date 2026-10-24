"""Ferramentas do Assistente para os motores de cálculo (Portugal): uma ferramenta por motor (esquemas estritos) + execução comum
→ resultado + nota PDF + pré-visualização PNG.

Integração no Assistente (.pt): acrescentar CALC_TOOLS à lista de ferramentas e, para name in CALC_TOOL_NAMES, chamar run(name, args)
e guardar o PDF e o PNG como artefactos; PROGRESS_LABELS dá o texto de progresso e PROTOCOL_PT a frase de encaminhamento.
"""
from __future__ import annotations

from . import (accessibilite, aquecimento, couverture, instalacoes, isolamento, lotes_tecnicos, patio_pluviais, photovoltaique, piso_radiante, redes, reh,
               solar_termico, structure)


def _n(desc=None):
    d = {"type": ["number", "null"]}
    if desc:
        d["description"] = desc
    return d


def _NS(desc=None):
    d = {"type": ["string", "null"]}
    if desc:
        d["description"] = desc
    return d


def _B(desc=None):
    d = {"type": ["boolean", "null"]}
    if desc:
        d["description"] = desc
    return d


def _obj(props: dict, desc=None) -> dict:
    d = {"anyOf": [{"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}, {"type": "null"}]}
    if desc:
        d["description"] = desc
    return d


def _item(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}


def _arr(props: dict, nullable=True, desc=None) -> dict:
    d = {"type": ["array", "null"] if nullable else "array", "items": _item(props)}
    if desc:
        d["description"] = desc
    return d


def _enum(values, desc=None) -> dict:
    d = {"type": ["string", "null"], "enum": list(values) + [None]}
    if desc:
        d["description"] = desc
    return d


def _tool(name: str, description: str, props: dict) -> dict:
    return {"type": "function", "name": name, "strict": True, "description": description,
            "parameters": {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}}


# --------------------------------------------------------------------------------------------------------------------------------
# 1. Pré-certificado REH
_ENV = {"tipo": {"type": "string", "enum": ["parede", "cobertura", "pavimento", "envidracado", "porta"]},
        "area_m2": {"type": "number"}, "U": _n("W/(m².°C); null = valor por defeito da época de construção"),
        "fronteira": _enum(list(reh.BTR), "exterior, espaço não útil (enu), adjacente, solo"), "btr": _n("coeficiente btr se conhecido"),
        "orientacao": _enum(reh.ORIENT, "envidraçados: N, NE, E, SE, S, SO, O, NO ou H"), "g": _n("fator solar do vidro"),
        "Fs": _n("fator de sombreamento de inverno"), "Fg": _n("fração envidraçada"),
        "estore": _B("envidraçado com dispositivo de proteção solar móvel (null = sim)"), "g_dispositivo": _n("g do vidro com proteção ativada")}
_REH_PROPS = {
    "area_util_m2": {"type": "number", "description": "área interior útil de pavimento (Ap)"},
    "concelho": _NS("concelho, p. ex. 'Porto', 'Évora' (define a NUTS III e o clima)"), "nuts": _enum(list(reh.NUTS), "NUTS III, se o concelho não for indicado"),
    "altitude_m": _n(), "obra": _enum(["nova", "grande_renovacao", "existente"]), "tipo": _enum(["moradia", "apartamento"]),
    "posicao": _enum(["res_do_chao", "intermedio", "ultimo", "unico"], "apartamento: piso na envolvente-tipo"),
    "ano_construcao": _n(), "pe_direito_m": _n(), "pisos": _n(), "tipologia": _n("T0…T7 → número (define os ocupantes para AQS)"),
    "area_envidracada_m2": _n("envolvente-tipo: área total de envidraçados"), "inercia": _enum(list(reh.A_INERCIA)),
    "envolvente": _arr(_ENV, desc="elementos da envolvente; null = envolvente-tipo gerada"),
    "pontes_termicas_w_c": _n("Σψ·B em W/°C"), "rph": _n("taxa de renovação de ar h⁻¹"), "recuperador_eta": _n("eficiência do recuperador de calor (0–1)"),
    "ventilacao_mecanica": _B(), "aquecimento": _obj({"tipo": _enum(list(reh.AQUEC)), "eficiencia": _n("rendimento ou COP sazonal")}),
    "arrefecimento": _obj({"eer": _n()}), "aqs": _obj({"tipo": _enum(list(reh.AQS)), "eficiencia": _n(), "solar_kwh": _n("contributo solar térmico kWh/ano")}),
    "rede_gas": _B("existe rede de gás (AQS por defeito a gás)"), "renovavel_kwh": _n("produção renovável para autoconsumo kWh/ano"),
    "renovavel_tipo": _enum(["fotovoltaico", "solar_termico"])}
REH_TOOL = _tool(
    "pre_certificado_reh",
    "Pré-certificado energético INDICATIVO de uma habitação (REH / SCE — DL 101-D/2020, Portaria 138-I/2021, Despacho 6476-E/2021): clima "
    "(NUTS III, altitude, zonas I1–I3 / V1–V3), Nic/Ni, Nvc/Nv, Qa (AQS), Ntc/Nt, RNt e classe energética A+…F, requisitos Umáx / Uw,máx, "
    "NZEB (obra nova), grande renovação, renováveis e ventilação. Não substitui o certificado de um Perito Qualificado (ADENE). Produz uma nota PDF. "
    "null = valor por defeito assinalado como hipótese (envolvente null = envolvente-tipo).", _REH_PROPS)

# 2. Instalações
_DIV_EL = {"nome": _NS(), "tipo": {"type": "string", "enum": list(instalacoes.DIVISOES)}, "area_m2": {"type": "number"},
           "perimetro_m": _n("sala: perímetro (número de tomadas)"), "comprimento_m": _n("corredor: comprimento")}
_EQ_EL = {"placa": _enum(["monofasica", "trifasica", "sem_placa"]), "forno": _B(), "maquina_lavar_roupa": _B(), "maquina_lavar_loica": _B(),
          "maquina_secar": _B("null = não"), "termoacumulador": _B(), "unidades_climatizacao": _n(), "bomba_calor_kw": _n("potência elétrica"),
          "carregamento_ve_kw": _n("3,7 / 7,4 / 11 kW")}
_INST_PROPS = {
    "eletricidade": _obj({"divisoes": _arr(_DIV_EL, nullable=False), "comprimento_medio_circuito_m": _n(), "resistencia_terra_ohm": _n("valor medido"),
                          "equipamentos": _obj(_EQ_EL, "null = cozinha corrente (placa, forno, máquinas de lavar, termoacumulador)")},
                         "RTIEBT; null = não calcular"),
    "canalizacao": _obj({"dispositivos": _arr({"tipo": {"type": "string", "enum": list(instalacoes.DISPOSITIVOS)}, "quantidade": _n()}, nullable=False),
                         "velocidade_max_m_s": _n(), "comprimento_m": _n("até ao dispositivo mais desfavorável"), "desnivel_m": _n(),
                         "pressao_rede_kpa": _n("pressão disponível na rede")}, "DR 23/95; null = não calcular")}
INSTALACOES_TOOL = _tool(
    "calcul_instalacoes",
    "Pré-dimensiona as instalações de uma habitação (Portugal) e produz uma nota PDF: eletricidade (RTIEBT: tomadas e pontos de luz por divisão, "
    "circuitos, secções, disjuntores, diferenciais 30 mA, quedas de tensão, potência a contratar) e canalização (DR 23/95: caudais, caudal de "
    "cálculo, diâmetros, velocidade, pressão; drenagem: tubo de queda e coletor). Preenche só as partes pedidas (null nas outras).", _INST_PROPS)

# 3. Aquecimento
_PAREDE = {"area_m2": {"type": "number"}, "U": {"type": "number", "description": "W/(m².°C)"}, "lado": _enum(list(aquecimento.B)), "b": _n("fator b se conhecido")}
_DIV_AQ = {"nome": _NS(), "tipo": {"type": "string", "enum": list(aquecimento.T_INT)}, "area_m2": {"type": "number"}, "pe_direito_m": _n(),
           "theta_int": _n("temperatura interior se diferente da convencional"), "paredes": _arr(_PAREDE, desc="paredes, envidraçados, pavimento, teto"),
           "pontes": _arr({"comprimento_m": {"type": "number"}, "psi": {"type": "number"}}, desc="pontes térmicas lineares")}
_AQ_PROPS = {
    "concelho": _NS(), "nuts": _enum(list(reh.NUTS)), "altitude_m": _n(), "theta_e": _n("temperatura exterior de projeto imposta (°C)"),
    "divisoes": _arr(_DIV_AQ, nullable=False), "recuperacao_calor": _n("eficiência do recuperador (0–1)"),
    "estanquidade": _enum(list(aquecimento.INFILTRACAO)), "rph_min": _n(), "delta_u_pontes": _n("majoração ΔU forfetária"),
    "reaquecimento_w_m2": _n(),
    "bomba_calor": _obj({"emissores": _enum(list(aquecimento.EMISSORES)), "p_nominal_kw": _n("A7/W35"), "p_theta_e_kw": _n("potência à θe (ficha)"),
                         "cop_theta_e": _n(), "volume_instalacao_l": _n(), "alimentacao": _enum(["mono", "tri"])},
                        "null = só perdas; objeto (mesmo com campos null) = pré-dimensionar a bomba de calor ar/água")}
AQUECIMENTO_TOOL = _tool(
    "calcul_aquecimento",
    "Calcula as perdas de calor de projeto divisão a divisão (EN 12831-1 simplificada, θe a partir do clima REH do concelho) e pré-dimensiona "
    "uma bomba de calor ar/água (potência à θe, cobertura, apoio, volume de água, alimentação). Produz uma nota PDF. "
    "null = valor por defeito assinalado como hipótese.", _AQ_PROPS)

# 4. Isolamento
_SUPORTES = [k for k, v in isolamento.MATERIAIS.items() if v["familia"] in ("suporte", "ar", "revestimento")]
_ISOLANTES = [k for k, v in isolamento.MATERIAIS.items() if v["familia"] == "isolante"]
_ISO_PROPS = {
    "sistema": _enum(list(isolamento.SISTEMAS), "etics, fachada_ventilada, caixa_ar ou interior"),
    "concelho": _NS(), "nuts": _enum(list(reh.NUTS)), "altitude_m": _n(), "theta_e": _n("temperatura exterior de projeto imposta (com zona_inverno)"),
    "zona_inverno": _enum(["I1", "I2", "I3"], "só com theta_e"), "regiao": _enum(["continente", "acores", "madeira"], "só com theta_e"),
    "lado": _enum(["exterior", "enu"], "parede em contacto com o exterior ou com espaço não útil"), "btr": _n(),
    "suporte": _arr({"material": {"type": "string", "enum": _SUPORTES}, "ep_mm": {"type": "number"}}, desc="camadas existentes do interior para o exterior"),
    "isolante": _enum(_ISOLANTES), "lambda_declarado": _n("λ declarado (DoP) W/(m.°C)"), "isolante_ep_mm": _n("null = espessura dimensionada"),
    "u_alvo": _n("U pretendido, se inferior ao Umáx"), "buchas_m2": _n("ETICS"), "humidade": _enum(list(isolamento.HUMIDADE)),
    "area_m2": _n("área de parede a isolar (quantidades)")}
ISOLAMENTO_TOOL = _tool(
    "calcul_isolamento",
    "Calcula o isolamento térmico de uma parede (ETICS, fachada ventilada, caixa de ar ou interior): R e U (EN ISO 6946, buchas), requisito "
    "mínimo REH (Umáx da Portaria 138-I/2021 conforme a zona de inverno), risco de condensação (Glaser EN ISO 13788) com barreira pára-vapor, "
    "regras de execução e quantidades. Produz uma nota PDF. null = valor por defeito assinalado como hipótese.", _ISO_PROPS)

# 5. Fotovoltaico
_PV_PROPS = {
    "code_postal": _NS("código postal português (o 1.º algarismo define a produtividade)"), "puissance_kwc": _n("potência de pico kWp"),
    "surface_toiture_m2": _n(), "consommation_kwh": _n("consumo elétrico anual kWh"), "profil": _enum(["absent_journee", "mixte", "present_journee", "teletravail"],
                                                                                                         "ausente de dia, misto, presente de dia, teletrabalho"),
    "batterie_kwh": _n(), "azimut_sud": _n("desvio ao sul em graus (0 sul, ±90 este/oeste, 180 norte)"), "inclinaison": _n("inclinação dos painéis em graus"),
    "ombrage_pct": _n("sombreamento %"), "raccordement": _enum(["mono", "tri"]), "ratio_dc_ac": _n("rácio DC/AC (defeito 1,15)"),
    "longueur_dc_m": _n(), "longueur_ac_m": _n(), "t_min": _n("temperatura mínima do local"), "prix_achat_kwh": _n("€/kWh"),
    "prix_surplus_kwh": _n("venda do excedente €/kWh"), "cout_installation": _n("custo com IVA se houver orçamento"),
    "module": _obj({"wc": _n(), "voc": _n(), "isc": _n(), "vmp": _n(), "imp": _n(), "beta_voc": _n("%/K"), "gamma_vmp": _n("%/K"), "surface_m2": _n(), "masse_kg": _n()},
                   "ficha técnica do módulo; null = módulo standard")}
PV_TOOL = _tool(
    "calcul_photovoltaique",
    "Pré-dimensiona uma instalação fotovoltaica residencial em cobertura (Portugal, UPAC) e produz uma nota PDF: produção anual conforme o local, "
    "a orientação e a inclinação, autoconsumo e excedente, inversor e fileiras (tensão a frio, gama MPPT, correntes), cabos DC/AC e quedas de "
    "tensão (RTIEBT secção 712), proteções, carga na cobertura, poupança, custo, retorno e procedimento (DL 15/2022). "
    "Indica puissance_kwc, surface_toiture_m2 ou consommation_kwh. null = valor corrente assinalado como hipótese.", _PV_PROPS)

# 6. Redes
_VERT = {"nome": _NS(), "area_planta_m2": {"type": "number", "description": "projeção horizontal da vertente"}, "coef_escoamento": _n(),
         "inclinacao_pct": _n("inclinação da caleira (defeito 0,5 %)"), "comprimento_caleira_m": _n(), "tubos_queda": _n("número imposto"),
         "descarga_central": _B(), "diametro_min": _n("Ø mínimo do tubo de queda (defeito 75)")}
_COMP = {"nome": _NS(), "tipo": {"type": "string", "enum": ["sala", "quarto", "escritorio", "cozinha", "instalacao_sanitaria", "lavandaria", "corredor", "outro"]},
         "area_m2": {"type": "number"}}
_REDES_PROPS = {
    "aguas_pluviais": _obj({"regiao": _enum(["A", "B", "C"], "região pluviométrica (Anexo IX do DR 23/95)"),
                            "periodo_retorno": {"type": ["integer", "null"], "enum": [2, 5, 10, 20, 50, 100, None]}, "duracao_min": _n(), "ks": _n("Manning-Strickler"),
                            "inclinacao_coletor_pct": _n(), "vertentes": _arr(_VERT)}, "null = não calcular"),
    "fossa_septica": _obj({"habitantes": _n(), "tipologia": _n("T0…T7 → número (habitantes = n + 1)"), "capitacao_l_hab_dia": _n(), "fator_afluencia": _n(),
                           "tempo_retencao_dias": _n(), "intervalo_limpeza_dias": _n(), "solo": _enum(list(redes.TAXA_SOLO)), "nivel_freatico_m": _n(),
                           "distancia_poco_m": _n(), "distancia_habitacao_m": _n()}, "null = não calcular"),
    "ventilacao": _obj({"pe_direito_m": _n(), "rph_projeto": _n("Rph do projeto se conhecido"), "compartimentos": _arr(_COMP)}, "null = não calcular")}
REDES_TOOL = _tool(
    "calcul_redes",
    "Pré-dimensiona (Portugal) as águas pluviais das coberturas (DR 23/95: intensidade IDF, caleiras, tubos de queda, coletor predial), a fossa "
    "séptica e o destino final (guia ERSAR: volume útil, trincheiras de infiltração, distâncias) e a ventilação da habitação (Portaria 138-I/2021, "
    "NP 1037-1: caudais, Rph, grelhas de admissão). Preenche só as partes pedidas (null nas outras). Nota PDF.", _REDES_PROPS)

# 7. Cobertura
_COUV_PROPS = {
    "vent": _obj({"zona_vento": _enum(["A", "B"], "zona do AN português (null = A, ou B nas ilhas, faixa costeira e acima de 600 m)"),
                  "ilhas": _B(), "faixa_costeira_5km": _B(), "altitude_m": _n(), "categorie_terrain": _enum(list(couverture.TERRAIN_PT), "categoria de terreno"),
                  "hauteur_m": _n("altura do edifício"), "largeur_m": _n(), "profondeur_m": _n(), "pente_deg": _n("inclinação da cobertura")}, "vento; null = não calcular"),
    "neige": _obj({"zona_neve": _enum(list(couverture.NEIGE_PT)), "altitude_m": _n(), "pente_deg": _n(),
                   "forcar_neve": _B("considerar a neve mesmo abaixo de 200 m")}, "neve; null = não calcular"),
    "tuiles": _obj({"type_tuile": _enum(["emboitement", "canal", "plate", "beton"], "telha de encaixe, canudo/canal, plana, betão"),
                    "site": _enum(["protege", "normal", "expose"]), "altitude_m": _n(),
                    "zone_climatique": {"type": ["integer", "null"], "enum": [1, 2, 3, None], "description": "zona climática dos DTU franceses série 40.2"},
                    "cote_manche_atlantique_nord_20km": _B(), "cote_atlantique_sud_ou_20_40km": _B(), "ecran_sous_toiture": _B("subtelha / membrana sob as telhas"),
                    "rampant_m": _n("comprimento da vertente em projeção horizontal"), "pente_pct": _n(), "pente_deg": _n()},
                   "inclinação mínima das telhas (regras francesas DTU, referência na falta de norma portuguesa); null = não calcular")}
COUVERTURE_TOOL = _tool(
    "calcul_couverture",
    "Cobertura: pressão dinâmica de pico qp(z) e coeficientes cpe (paredes, cobertura de duas águas, sucção nos bordos) segundo a NP EN 1991-1-4 "
    "e o Anexo Nacional português, carga de neve (NP EN 1991-1-3, zonas Z1–Z3 + altitude) e inclinação mínima das telhas (DTU franceses série 40.2 "
    "como referência). Preenche só as partes pedidas. Nota PDF.", _COUV_PROPS)

# 8. Acessibilidade
_MES = {k: _n(d) for k, d in (
    ("largeur_cheminement_m", "largura do percurso"), ("pente_rampe_pct", "inclinação da rampa %"), ("longueur_rampe_m", "projeção horizontal da rampa"),
    ("desnivel_rampa_m", "desnível vencido pela rampa"), ("largeur_rampe_m", None), ("devers_pct", "inclinação transversal %"), ("ressaut_cm", "ressalto"),
    ("porte_entree_utile_m", "largura útil da porta de entrada"), ("porte_interieure_utile_m", "largura útil das portas do percurso"),
    ("diametre_rotation_m", "zona de rotação"), ("circulation_interieure_m", "largura dos corredores"), ("escalier_hauteur_marche_cm", "altura do degrau"),
    ("escalier_giron_cm", "cobertor"), ("escalier_largeur_m", "largura da escada"), ("stationnement_largeur_m", "lugar de estacionamento: largura"),
    ("stationnement_longueur_m", "lugar de estacionamento: comprimento"), ("nb_places_total", None), ("nb_places_adaptees", None),
    ("douche_seuil_cm", "ressalto do duche"), ("nb_niveaux_au_dessus_rdc", None), ("eclairage_exterieur_lux", None))}
_MES.update({"escalier_interieur_logement": _B("escada interior da habitação"), "ressaut_chanfreine": _B("ressalto chanfrado"), "ascenseur": _B(),
             "publico": _B("edifício aberto ao público"), "wc_espace_lateral_m": _NS("instalação sanitária: dimensões (largura × comprimento)")})
PMR_TOOL = _tool(
    "verifier_accessibilite",
    "Verifica a acessibilidade de um projeto a partir das medidas fornecidas: percursos, rampas (inclinação / projeção / desnível), ressaltos, "
    "portas, zona de rotação, corredores, escadas, estacionamento, duche — Portugal (DL 163/2006, normas técnicas; contexte 'pt') ou França. "
    "Só as medidas fornecidas são verificadas (null nas outras). Nota PDF.",
    {"contexte": {"type": "string", "enum": ["pt"] + [c for c in accessibilite.CONTEXTES if c != "pt"], "description": "'pt' para Portugal"},
     "mesures": {"type": "object", "additionalProperties": False, "properties": _MES, "required": list(_MES)}})

# 9. Estruturas (mesmas chaves que a versão FR)
_STRUCT_NUM = {
    "portee_m": "vão entre apoios (viga, lintel)", "b_m": "largura da secção ou da sapata", "h_m": "altura da secção, espessura da laje ou da sapata",
    "g_kn_m": "carga permanente linear sem peso próprio (kN/m)", "q_kn_m": "sobrecarga linear (kN/m)", "fck": "classe do betão fck (MPa)",
    "fyk": None, "enrobage_mm": "recobrimento", "lef_m": "comprimento de bambeamento (madeira)", "classe_service": "1, 2 ou 3 (madeira)", "psi2": None,
    "limite_fleche": "L/x, p. ex. 300", "l_m": "comprimento da sapata isolada (null = contínua)", "profundeur_m": "profundidade de fundação",
    "g_kn": "carga permanente na sapata (kN, ou kN/m se contínua)", "q_kn": "sobrecarga na sapata", "largeur_mur_m": None,
    "q_adm_els_kpa": "tensão admissível ELS do estudo geotécnico", "phi_deg": "ângulo de atrito φ'", "c_kpa": "coesão c'", "cu_kpa": "coesão não drenada cu",
    "gamma_sol": "peso volúmico do solo kN/m³", "lx_m": "menor vão da laje", "ly_m": "maior vão da laje", "g2_kn_m2": "restantes cargas permanentes (kN/m²)",
    "q_kn_m2": "sobrecarga (kN/m²)", "epaisseur_mur_m": None, "hauteur_maconnerie_m": "altura de alvenaria acima do lintel",
    "hauteur_a_monter_mm": "escada: altura de piso acabado a piso acabado", "reculement_mm": "escada: comprimento disponível", "largeur_mm": "escada: largura útil",
    "largeur_disponible_mm": None, "epaisseur_dalle_mm": None, "tremie_longueur_mm": "comprimento da abertura na laje",
    "hauteur_m": "pilar: altura livre", "coef_longueur_flambement": "pilar: L0 = coef × altura (1 articulado, 0,7 encastrado-articulado…)",
    "n_ed_kn": "pilar: esforço normal ELU (ou g_kn / q_kn)", "m1_knm": "pilar: momento de extremidade 1 (ELU)", "m2_knm": "pilar: momento de extremidade 2 (ELU)",
    "fluage_phi_ef": None, "d_m": "punçoamento: altura útil da laje", "c1_m": "punçoamento: dimensão do pilar", "c2_m": None,
    "v_ed_kn": "punçoamento: reação do pilar ELU", "rho_l": "punçoamento: taxa de armadura superior (defeito 0,005)"}
_STRUCT_PROPS = {"element": {"type": "string", "enum": list(structure.ELEMENTS)},
                 "appuis": _enum(list(structure.APPUIS_POUTRE), "simplesmente apoiada, contínua (vão extremo / interior), consola"),
                 "classe": _enum(["C18", "C24", "C30", "GL24h", "GL28h"], "classe de resistência da madeira"),
                 "duree_charge": _enum(["permanent", "long", "medium", "short", "instantaneous"], "classe de duração da carga (madeira)"),
                 "materiau": _enum(["steel", "rc", "both"], "lintel: aço, betão armado ou ambos"),
                 "position_poteau": _enum(["interieur", "rive", "angle"], "punçoamento: pilar interior, de bordo ou de canto"),
                 "poteau_circulaire": _B(),
                 **{k: _enum(["rive", "continu", "libre"], "laje: bordo apoiado, contínuo ou livre") for k in ("x0", "x1", "y0", "y1")},
                 **{k: _n(v) for k, v in _STRUCT_NUM.items()}}
STRUCTURE_TOOL = _tool(
    "calcul_structure",
    "Pré-dimensiona um elemento estrutural com os motores determinísticos ConstruPilot e produz uma nota PDF: pilar de betão armado (esbelteza, "
    "2.ª ordem por curvatura nominal, flexão composta, armaduras), punçoamento de laje (NP EN 1992-1-1 §6.4), viga de betão armado (armadura, "
    "estribos, L/d, kg de aço), laje armada em duas direções (malhas), lintel em aço / betão armado, viga de madeira (NP EN 1995-1-1: flexão, corte, "
    "flecha, bambeamento), sapata (NP EN 1997-1 anexo D ou tensão admissível do estudo geotécnico), escada (regra de Blondel). "
    "Preenche só os campos úteis ao elemento, null nos outros. A validar pelo projetista de estruturas.", _STRUCT_PROPS)

# 10. Especialidades técnicas encadeadas
_PAR_LT = {"tipo": _enum(["parede", "envidracado", "porta", "pavimento", "cobertura"]), "area_m2": {"type": "number"},
           "U": _n("W/(m².°C); null = U da parede isolada (se calculado) ou valor por defeito"), "lado": _enum(list(aquecimento.B)), "b": _n()}
_DIV_LT = {"nome": _NS(), "tipo": {"type": "string", "enum": list(aquecimento.T_INT)}, "area_m2": {"type": "number"}, "pe_direito_m": _n(),
           "theta_int": _n(), "paredes": _arr(_PAR_LT, desc="paredes, envidraçados, portas, pavimento e cobertura em contacto com o exterior / ENU"),
           "pontes": _arr({"comprimento_m": {"type": "number"}, "psi": {"type": "number"}}),
           "revestimento": _enum(list(piso_radiante.REVESTIMENTO_R), "revestimento de piso (piso radiante)"),
           "local_inferior": _enum(list(piso_radiante.R_ISOLANTE_MIN)), "r_isolante_piso": _n("R do isolante sob o piso radiante"),
           "phi_w": _n("perdas de calor da divisão já conhecidas (W): prevalecem sobre o cálculo"),
           "comprimento_m": _n("comprimento interior (planta desenhada)"), "largura_m": _n("largura interior (planta desenhada)")}
_ISO_LT = {k: v for k, v in _ISO_PROPS.items() if k not in ("concelho", "nuts", "altitude_m", "theta_e", "zona_inverno", "regiao", "area_m2")}
_EQ_LT = {"placa": _enum(["monofasica", "trifasica", "sem_placa"]), "forno": _B(), "maquina_lavar_roupa": _B(), "maquina_lavar_loica": _B(),
          "maquina_secar": _B(), "termoacumulador": _B(), "unidades_climatizacao": _n(), "carregamento_ve_kw": _n()}
_LT_PROPS = {
    "concelho": _NS(), "nuts": _enum(list(reh.NUTS)), "altitude_m": _n(), "theta_e": _n("temperatura exterior de projeto imposta"),
    "obra": _enum(["nova", "renovacao"]), "tipologia": _n("T0…T7 → número"), "tipo_habitacao": _enum(["moradia", "apartamento"]),
    "divisoes": _arr(_DIV_LT, nullable=False),
    "lotes": {"type": ["array", "null"], "items": {"type": "string", "enum": list(lotes_tecnicos.LOTES)},
              "description": "especialidades a calcular (null = todas); p. ex. [\"aquecimento\", \"piso_radiante\", \"bomba_calor\"] para o aquecimento só"},
    "isolamento_paredes": _obj(_ISO_LT, "isolamento das paredes exteriores (null = não calcular; o U calculado substitui o U por defeito das paredes)"),
    "estanquidade": _enum(list(aquecimento.INFILTRACAO)), "recuperacao_calor": _n(), "rph_min": _n(),
    "emissores": _enum(list(aquecimento.EMISSORES), "null = piso radiante"), "ida_max": _n("ida máxima do piso radiante (°C, null = 45)"),
    "gerador": _enum(["bomba_calor", "outro"]),
    "bomba_calor": _obj({"p_nominal_kw": _n("A7/W35"), "p_theta_e_kw": _n(), "cop_theta_e": _n(), "alimentacao": _enum(["mono", "tri"])}),
    "equipamentos": _obj(_EQ_LT, "equipamentos elétricos (a bomba de calor é acrescentada automaticamente)"),
    "dispositivos": _arr({"tipo": {"type": "string", "enum": list(instalacoes.DISPOSITIVOS)}, "quantidade": _n()}, desc="null = deduzidos das divisões"),
    "pressao_rede_kpa": _n(), "comprimento_alimentacao_m": _n(), "desnivel_m": _n(),
    "solar_termico": _obj({"ocupantes": _n(), "regiao": _enum(["continente", "acores", "madeira"]), "irradiacao_kwh_m2": _n(),
                           "sistema": _enum(list(solar_termico.ETA_SIST)),
                           "coletor": _obj({"numero": _n(), "area_m2": _n("área unitária"), "eta0": _n(), "a1": _n(), "t_estagnacao_c": _n(), "p_max_bar": _n(),
                                            "absorvedor": _NS(), "identicos": _B(), "certificado": _B()}),
                           "deposito": _obj({"volume_l": _n(), "ua_w_k": _n(), "en12897": _B()})}, "null = sem solar térmico")}
LOTES_TOOL = _tool(
    "calcul_lotes_tecnicos",
    "Calcula de uma só vez as especialidades técnicas de uma habitação (Portugal) e produz UMA nota de cálculo PDF: isolamento das paredes "
    "(U, Umáx REH, Glaser), perdas de calor divisão a divisão (EN 12831-1), piso radiante (NP EN 1264: ida, passos, circuitos, caudais), bomba de "
    "calor ar/água, eletricidade (RTIEBT, com o circuito da bomba de calor), canalização e drenagem (DR 23/95) e, opcionalmente, solar térmico. "
    "Cada etapa reutiliza o resultado da anterior. null = valor por defeito assinalado como hipótese.", _LT_PROPS)

# 11. Piso radiante
_DIV_PR = {"nome": _NS(), "tipo": {"type": "string", "enum": list(piso_radiante.T_INT)}, "area_m2": {"type": "number"},
           "phi_w": {"type": "number", "description": "perdas de calor da divisão (W)"}, "theta_int": _n(),
           "revestimento": _enum(list(piso_radiante.REVESTIMENTO_R)), "r_revestimento": _n(), "exclusao_m2": _n("área sem tubos (móveis fixos)"),
           "comprimento_max_m": _n(), "local_inferior": _enum(list(piso_radiante.R_ISOLANTE_MIN)), "r_isolante": _n(), "distancia_coletor_m": _n(),
           "comprimento_m": _n("comprimento interior da divisão (null = retângulo equivalente à área)"), "largura_m": _n("largura interior")}
PISO_TOOL = _tool(
    "calcul_piso_radiante",
    "Dimensiona um piso radiante hidráulico (NP EN 1264) a partir das perdas de calor por divisão: temperatura de superfície, passo dos tubos, "
    "temperatura de ida e retorno, caudais, circuitos ≤ 120 m, perdas de carga, coletores, isolante sob o piso, juntas, e DESENHA a planta de cada "
    "divisão (circuitos em espiral ao passo, coletor, cotas). Usa-a também para qualquer pedido de «planta» / «esquema» de piso radiante. Nota PDF.",
    {"divisoes": _arr(_DIV_PR, nullable=False), "sigma_k": _n("salto térmico ida-retorno (null = 5 K)"), "ida_max": _n("null = 45 °C")})

# 12. Solar térmico
_ST_PROPS = {
    "tipologia": _n(), "ocupantes": _n(), "tipo_habitacao": _enum(["moradia", "apartamento"]), "consumo_l_dia_ocupante": _n(),
    "regiao": _enum(["continente", "acores", "madeira"]), "irradiacao_kwh_m2": _n("no plano dos coletores (SolTerm)"),
    "sistema": _enum(list(solar_termico.ETA_SIST)), "utilizacao": _enum(["aqs", "combinado"]),
    "tipo_instalacao": _enum(["cheio", "autodrenante"]), "circuito": _enum(["indireto", "direto"]), "coletivo": _B(),
    "coletor": _obj({"numero": _n(), "area_m2": _n("área unitária Ac"), "eta0": _n(), "a1": _n(), "t_estagnacao_c": _n(), "p_max_bar": _n(),
                     "absorvedor": _NS(), "identicos": _B(), "certificado": _B("Solar Keymark / EN ISO 9806")}),
    "absorvedor_existente": _NS(), "t_max_regulacao_c": _n(), "p_max_instalacao_bar": _n(),
    "tubagem": _obj({"material": _enum(sorted(solar_termico.NOMES)), "t_max_c": _n(), "p_max_bar": _n()}),
    "isolamento": _obj({"tipo": _enum(["epdm", "la_mineral", "outro"]), "exterior": _B(), "uv": _B()}),
    "fluido": _obj({"anticongelante_pct": _n(), "atoxico": _B()}),
    "permutador": _obj({"ua_w_k": _n(), "dp_mca": _n(), "material": _enum(["inox", "inox_titanio", "cobre", "outro"]), "ep_cobre_mm": _n(), "dupla_permuta": _B()}),
    "deposito": _obj({"volume_l": _n(), "ua_w_k": _n(), "en12897": _B()}),
    "regulacao": _obj({"ip_controlador": _n(), "ip_sondas": _n(), "ip_detetor": _n(), "tempo_detetor_s": _n(), "t_max_sonda_coletor_c": _n(),
                       "t_max_sonda_deposito_c": _n()}),
    "tarado_valvula_bar": _n(), "manometro_max_bar": _n(), "contador_classe": _n(), "vaso_t_max_c": _n(), "purgador_t_max_c": _n(), "purgador_isolado": _B(),
    "parafusos": _obj({"diametro_mm": _n(), "inox": _B()}),
    "cargas": _obj({"ensaio_pressao_pa": _n(), "ensaio_succao_pa": _n(), "pressao_pa": _n(), "succao_pa": _n()})}
SOLAR_TOOL = _tool(
    "verificar_solar_termico",
    "Solar térmico com coletores envidraçados (AQS ou combinado): pré-dimensionamento indicativo (necessidades de AQS convenção REH, área e "
    "acumulação sugeridas, fração solar) e verificação da escolha dos materiais a partir das fichas do fabricante (coletor, tubagens, isolamento, "
    "vaso, permutador Δη < 10 %, depósito (UA) ≤ 0,16·√V, regulação, cargas). Nota PDF. O cálculo SCE faz-se com o SolTerm.", _ST_PROPS)

# 13. Pátio rebaixado
PATIO_TOOL = _tool(
    "calcul_patio_pluvial",
    "Drenagem das águas pluviais de um pátio rebaixado / pátio inglês abaixo do arruamento (Portugal): caudal (IDF DR 23/95 × coeficiente de risco), "
    "ralos e coletor, estação elevatória com 2 bombas (caudal, AMT, potência), poço (volume útil), compressão com pescoço de cisne e válvula de "
    "retenção, retenção em caso de avaria, muros em consola. Nota PDF com corte de princípio.",
    {"area_m2": _n("área em planta do pátio"), "profundidade_m": _n("fundo do pátio sob o terreno"), "comprimento_m": _n(), "altura_fachadas_m": _n(),
     "coberturas_descarregadas_m2": _n(), "coef_risco": _n("null = 1,5"), "regiao_pluviometrica": _enum(["A", "B", "C"]),
     "periodo_retorno_anos": _n("null = 10"), "cota_soleira_descarga_m": _n(), "distancia_descarga_m": _n(), "descarga_infiltracao": _B(),
     "arranques_h": _n(), "altura_pescoco_cisne_m": _n(), "comprimento_compressao_m": _n(), "altura_agua_admissivel_m": _n(),
     "chuva_1h_10anos_mm": _n(), "chuva_1h_100anos_mm": _n(), "sobrecarga_kpa": _n()})

CALC_TOOLS = [REH_TOOL, INSTALACOES_TOOL, AQUECIMENTO_TOOL, ISOLAMENTO_TOOL, PV_TOOL, REDES_TOOL, COUVERTURE_TOOL, PMR_TOOL, STRUCTURE_TOOL, LOTES_TOOL, PISO_TOOL, SOLAR_TOOL,
              PATIO_TOOL]
CALC_TOOL_NAMES = {t["name"] for t in CALC_TOOLS}

PROGRESS_LABELS = {
    "pre_certificado_reh": "A calcular o pré-certificado energético (REH)…",
    "calcul_instalacoes": "A dimensionar as instalações elétricas e de águas…",
    "calcul_aquecimento": "A calcular as perdas de calor e a bomba de calor…",
    "calcul_isolamento": "A calcular o isolamento da parede (U, REH, Glaser)…",
    "calcul_photovoltaique": "A dimensionar a instalação fotovoltaica…",
    "calcul_redes": "A dimensionar águas pluviais, fossa séptica e ventilação…",
    "calcul_couverture": "A calcular vento, neve e inclinação das telhas…",
    "verifier_accessibilite": "A verificar a acessibilidade (DL 163/2006)…",
    "calcul_structure": "A pré-dimensionar o elemento estrutural…",
    "calcul_lotes_tecnicos": "A calcular as especialidades técnicas encadeadas (isolamento, aquecimento, piso radiante, instalações)…",
    "calcul_piso_radiante": "A dimensionar o piso radiante (NP EN 1264)…",
    "verificar_solar_termico": "A verificar a instalação solar térmica…",
    "calcul_patio_pluvial": "A dimensionar a drenagem do pátio rebaixado…",
}

PROTOCOL_PT = (
    "Para um pré-certificado energético ou a classe energética de uma habitação (REH, Nic/Ni, RNt) usa pre_certificado_reh e lembra que é indicativo; "
    "para eletricidade (RTIEBT) ou canalização e drenagem (DR 23/95) usa calcul_instalacoes; para perdas de calor por divisão ou bomba de calor "
    "usa calcul_aquecimento; para isolamento de paredes (ETICS, caixa de ar, interior, U, Umáx REH, condensações) usa calcul_isolamento; para "
    "painéis solares fotovoltaicos (UPAC) usa calcul_photovoltaique; para caleiras, tubos de queda, fossa séptica ou ventilação usa calcul_redes; "
    "para vento, neve ou inclinação mínima de telhas usa calcul_couverture; para a acessibilidade (DL 163/2006) usa verifier_accessibilite; "
    "para pré-dimensionar uma viga de betão armado ou de madeira, um pilar, o punçoamento, uma laje, um lintel, uma sapata ou uma escada usa calcul_structure "
    "; para todas as especialidades técnicas de uma habitação numa só nota (isolamento → perdas → piso radiante → bomba de calor → eletricidade → "
    "canalização → solar térmico) usa calcul_lotes_tecnicos; só o piso radiante: calcul_piso_radiante; solar térmico (AQS, coletores, depósito): "
    "verificar_solar_termico; pátio rebaixado / pátio inglês abaixo da rua: calcul_patio_pluvial "
    "(os motores calculam, tu restituis).")

FIM = "Restitui apenas estes valores e hipóteses (não completes com materiais ou equipamentos não fornecidos)."


def _clean(args):
    """Retira recursivamente os null (o motor aplica então os seus valores por defeito, assinalados como hipóteses)."""
    if isinstance(args, dict):
        return {k: _clean(v) for k, v in args.items() if v is not None}
    if isinstance(args, list):
        return [_clean(v) for v in args]
    return args


def _ctl(lst) -> list[str]:
    out = []
    for c in lst or []:
        st = "OK" if c.get("ok") else ("KO" if c.get("ok") is False else "A VERIFICAR")
        val = c.get("valor", c.get("valeur"))
        ex = c.get("exigencia", c.get("exigence"))
        out.append(f"{st} {c['ref']}: {val}" + (f" (exigência {ex})" if ex else "") + (f" — {c['note']}" if c.get("note") else ""))
    return out


def _hyp(lst, n=None) -> list[str]:
    return [f"Hipótese: {h}" for h in (lst or [])[:n]]


def _ret(o: dict, res: list[str], data: dict) -> dict:
    res.append(FIM)
    return {"titre": o["titre"], "resume": "\n".join(res), "pdf": o["pdf"], "png": o["png"], "data": data}


def run(name: str, args: dict) -> dict:
    """→ {"titre", "resume" (texto curto para o Assistente), "pdf", "png", "data"}. ValueError se os parâmetros forem incoerentes."""
    a = _clean(args or {})
    if name == "pre_certificado_reh":
        o = reh.note(a)
        c = o["clima"]
        res = [o["sous_titre"], "PRÉ-CERTIFICADO INDICATIVO — não substitui o certificado energético emitido por Perito Qualificado (SCE / ADENE).",
               f"Classe {o['classe']} (RNt {o['RNt']:.2f}) · Nic {o['Nic']:.1f} / Ni {o['Ni']:.1f} · Nvc {o['Nvc']:.1f} / Nv {o['Nv']:.1f} kWh/(m².ano) · "
               f"Qa {o['Qa']:.0f} kWh/ano ({o['ocupantes']} ocupantes) · Ntc {o['Ntc']:.1f} / Nt {o['Nt']:.1f} kWhEP/(m².ano)",
               f"Clima: {c['nuts']}, {c['altitude_m']:.0f} m, GD {c['GD']:.0f} °C.dia, zonas {c['zona_i']} / {c['zona_v']}; "
               f"Htr {o['Htr']:.1f} W/°C, Hve {o['Hve']:.1f} W/°C (Rph {o['rph']:g} h⁻¹); aquecimento {o['aquecimento']}, AQS {o['aqs']}"]
        res += _ctl(o["controles"]) + _hyp(o["hipoteses"])
        data = {k: o[k] for k in ("classe", "RNt", "Nic", "Ni", "Nvc", "Nv", "Qa", "Ntc", "Nt", "RenHab")}
        data.update(nuts=c["nuts"], zona_i=c["zona_i"], zona_v=c["zona_v"], conforme=all(x["ok"] is not False for x in o["controles"]))
        return _ret(o, res, data)
    if name == "calcul_instalacoes":
        eq = (a.get("eletricidade") or {}).get("equipamentos")
        if eq is not None and "placa" in eq:
            eq["placa"] = {"monofasica": True, "trifasica": "tri", "sem_placa": False}[eq["placa"]]
        o = instalacoes.note(a)
        res = [o["titre"]]
        if "eletricidade" in o:
            e = o["eletricidade"]
            res.append(f"Eletricidade: {e['tomadas']} tomadas, {e['pontos_luz']} pontos de luz, {len(e['circuitos'])} circuitos, {e['diferenciais']} diferenciais 30 mA; "
                       f"potência estimada {e['potencia_estimada_w']:.0f} W → contratar {e['potencia_contratada_kva']:g} kVA ({e['alimentacao']})")
            res.append("Circuitos: " + "; ".join(f"{c['nome']} {c['seccao']:g} mm² / {c['disjuntor']} A ({c['diferencial']})" for c in e["circuitos"]))
        if "canalizacao" in o:
            k = o["canalizacao"]
            res.append(f"Canalização: Qa {k['qa_l_s']:.2f} L/s → Qc {k['qc_l_s']:.2f} L/s, ramal água fria {k['tubo_af']} ({k['velocidade_m_s']:.2f} m/s), "
                       f"água quente {k['tubo_aq'] or '—'}, pressão no dispositivo mais desfavorável {k['pressao_kpa']:.0f} kPa; drenagem {k['drenagem_qc_l_min']:.0f} L/min, "
                       f"tubo de queda Ø{k['tubo_queda_mm']}, coletor Ø{k['coletor_mm']}")
        for s in ("eletricidade", "canalizacao"):
            res += _ctl((o.get(s) or {}).get("controles"))
        for s in ("eletricidade", "canalizacao"):
            res += _hyp((o.get(s) or {}).get("hipoteses"))
        data = {"partes": [s for s in ("eletricidade", "canalizacao") if s in o]}
        if "eletricidade" in o:
            data["potencia_contratada_kva"] = o["eletricidade"]["potencia_contratada_kva"]
        if "canalizacao" in o:
            data["qc_l_s"] = o["canalizacao"]["qc_l_s"]
        return _ret(o, res, data)
    if name == "calcul_aquecimento":
        o = aquecimento.note(a)
        p = o["perdas"]
        res = [o["titre"],
               f"Perdas: θe {p['theta_e']:g} °C ({p['theta_e_fonte']}), ventilação {p['q_ventilacao_m3h']:.0f} m³/h, total {p['phi_total']:.0f} W "
               f"({p['w_m2']:.0f} W/m² sobre {p['area_m2']:.0f} m²) — " + ", ".join(f"{r['nome']} {r['phi']:.0f} W" for r in p["divisoes"])]
        if "bomba_calor" in o:
            b = o["bomba_calor"]
            res.append(f"Bomba de calor: {b['p_nominal_kw']:g} kW nominal (A7/W35) → {b['p_theta_e_kw']:.1f} kW à θe ({b['cobertura'] * 100:.0f} %), apoio {b['apoio_kw']:g} kW, "
                       f"COP {b['cop']:.2f}, caudal {b['caudal_lh']:.0f} L/h, volume {b['volume_instalacao_l']:.0f} L, {b['p_absorvida_kw']:.1f} kW absorvidos "
                       f"({b['corrente_mono_a']:.1f} A em monofásico), emissores {b['emissores']} (ida {b['temperatura_ida']} °C)")
            res += _ctl(b["controles"])
        res += _hyp(p["hipoteses"]) + _hyp((o.get("bomba_calor") or {}).get("hipoteses"))
        data = {"phi_total_w": p["phi_total"], "theta_e": p["theta_e"], "w_m2": p["w_m2"]}
        if "bomba_calor" in o:
            data["p_nominal_kw"] = o["bomba_calor"]["p_nominal_kw"]
        return _ret(o, res, data)
    if name == "calcul_isolamento":
        o = isolamento.note(a)
        i = o["isolante"]
        res = [f"{o['titre']} — U = {o['U']:.3f} W/(m².°C), R parede = {o['R_parede']:.2f} m².°C/W, isolante {isolamento.MATERIAIS[i['code']]['nome']} "
               f"{i['ep_mm']:g} mm (λ {i['lambda']:g}{' declarado' if i['declarado'] else ' por defeito'}), Umáx {o['umax']:g}"
               + (", barreira pára-vapor necessária" if o["barreira_vapor"] else "")]
        res += _ctl(o["controles"])
        if o["metre"]:
            res.append("Quantidades: " + ", ".join(f"{m['designation']} {m['quantite']:g} {m['unite']}" for m in o["metre"]))
        res += _hyp(o["hipoteses"])
        data = {k: o[k] for k in ("U", "R_parede", "umax", "isolante", "barreira_vapor", "conforme", "metre")}
        return _ret(o, res, data)
    if name == "calcul_photovoltaique":
        a["pays"] = "pt"
        o = photovoltaique.note(a)
        e = o["economie"]
        res = [o["sous_titre"],
               f"{o['n_modules']} módulos {o['module']['wc']:g} Wp = {o['kwc']:.2f} kWp ({o['surface_m2']:.1f} m²), produção {o['production_kwh']:.0f} kWh/ano, "
               f"autoconsumo {o['taux_autoconsommation'] * 100:.0f} % ({o['autoconsommation_kwh']:.0f} kWh), excedente {o['surplus_kwh']:.0f} kWh",
               f"Inversor {o['onduleur']['kva']:g} kVA {'monofásico' if o['onduleur']['phase'] == 'mono' else 'trifásico'}, fileiras {o['chaines']}, "
               f"cabo DC {o['cable_dc_mm2']} mm², AC {o['cable_ac_mm2']:g} mm², disjuntor {o['disjoncteur_ac_a']} A",
               (f"Poupança {e['gain_annuel']:.0f} €/ano, custo {e['cout']:.0f} €, retorno {e['retour_ans']:.1f} anos, ganho líquido a 25 anos {e['gain_25_ans']:.0f} €"
                if e["retour_ans"] else "Poupança nula")]
        res += _ctl(o["controles"]) + _hyp(o["hypotheses"])
        return _ret(o, res, {"kwc": o["kwc"], "production_kwh": o["production_kwh"], "retour_ans": e["retour_ans"]})
    if name == "calcul_redes":
        o = redes.note(a)
        res = [o["titre"]]
        if "aguas_pluviais" in o:
            ap = o["aguas_pluviais"]
            res.append(f"Águas pluviais: I = {ap['intensidade_mm_h']:.0f} mm/h, caudal total {ap['caudal_total_l_s']:.2f} L/s"
                       + (f", coletor Ø{ap['coletor']}" if ap["coletor"] else ""))
            res += [f"Vertente {v['vertente']}: {v['A']:.0f} m², {v['Q']:.2f} L/s → caleira {v['caleira']}, {v['tubos_queda']} tubo(s) de queda Ø{v['phi']}" for v in ap["vertentes"]]
        if "fossa_septica" in o:
            f_ = o["fossa_septica"]
            g, d = f_["geometria"], f_["destino"]
            txt = (f"Fossa séptica: {f_['volume_util_m3']:.2f} m³ úteis ({f_['habitantes']} habitantes, {f_['caudal_m3_dia'] * 1000:.0f} L/dia), "
                   f"{g['compartimentos']} compartimentos, ≈ {g['comprimento_m']} × {g['largura_m']} m, altura de água {g['altura_agua_m']} m")
            if d.get("solucao") == "trincheiras de infiltração":
                txt += f"; trincheiras de infiltração {d['comprimento_total_m']:.0f} m ({d['n_trincheiras']} trincheira(s), largura {d['largura_m']:g} m)"
            elif d:
                txt += f"; destino final: {d['solucao']} ({d['motivo']})"
            res.append(txt)
        if "ventilacao" in o:
            v = o["ventilacao"]
            res.append(f"Ventilação: caudal {v['caudal_m3h']:.0f} m³/h (Rph {v['rph']:.2f} h⁻¹, volume {v['volume_m3']:.0f} m³); grelhas de admissão "
                       + (", ".join(f"{a_} {b_} m³/h" for a_, b_ in v["grelhas"]) or "—"))
        partes = [k for k in ("aguas_pluviais", "fossa_septica", "ventilacao") if k in o]
        for k in partes:
            res += _ctl(o[k]["controles"])
        for k in partes:
            res += _hyp(o[k]["hipoteses"])
        return _ret(o, res, {"partes": partes})
    if name == "calcul_couverture":
        for k in ("vent", "neige"):
            if k in a:
                a[k]["pays"] = "pt"
        o = couverture.note(a)
        res = [o["titre"]]
        if "vent" in o:
            v = o["vent"]
            res.append(f"Vento: vb,0 {v['vb0']:g} m/s, qp({v['z_m']:g} m) = {v['qp_pa']:.0f} Pa (categoria {v['categorie']}), sucção líquida na cobertura "
                       f"{v['depression_toiture_rive_kn_m2']:.2f} kN/m² nos bordos e {v['depression_toiture_courante_kn_m2']:.2f} kN/m² na zona corrente, "
                       f"estrutura {v['depression_toiture_structure_kn_m2']:.2f} kN/m²; pressão na parede a barlavento {v['pression_mur_D_kn_m2']:.2f} kN/m²")
        if "neige" in o:
            n_ = o["neige"]
            res.append(f"Neve: zona {n_['region']}, sk {n_['sk_kn_m2']:.2f} kN/m², s = {n_['s_kn_m2']:.2f} kN/m² (μ1 {n_['mu1']:.2f})")
        if "tuiles" in o:
            t_ = o["tuiles"]
            res.append(f"Telhas {t_['type']}: inclinação mínima {t_['pente_min_pct']:g} % ({t_['pente_min_deg']:.1f}°), zona {t_['zone']}, local {t_['site']} (regras DTU francesas)")
        for k in ("vent", "tuiles"):
            res += _ctl((o.get(k) or {}).get("controles"))
        for k in ("vent", "neige", "tuiles"):
            res += _hyp((o.get(k) or {}).get("hypotheses"))
        return _ret(o, res, {k: True for k in ("vent", "neige", "tuiles") if k in o})
    if name == "verifier_accessibilite":
        o = accessibilite.note(a)
        res = [o["titre"] + " — " + o["referentiel"]] + _ctl(o["controles"]) + _hyp(o["hypotheses"])
        return _ret(o, res, {"conforme": o["conforme"]})
    if name == "calcul_structure":
        el = a.get("element")
        o = structure.note(a)
        res = [o["titre"] + " — " + o["section"]]
        if o.get("barres"):
            res.append(f"Armaduras: {o['barres']['label']} ({o['barres']['as_cm2']:.2f} cm²), {o['etriers']}")
        res += _ctl(o["controles"])
        if o.get("quantites"):
            res.append("Quantidades: " + ", ".join(f"{structure.QUANT_PT.get(k, k)} {v:.2f}" for k, v in o["quantites"].items()))
        res += _hyp(o.get("hypotheses"))
        res.append("Pré-dimensionamento a validar pelo projetista de estruturas.")
        return _ret(o, res, {"element": el, "conforme": all(c["ok"] is not False for c in o["controles"]), "quantites": o.get("quantites")})
    if name == "calcul_lotes_tecnicos":
        eq = a.get("equipamentos")
        if eq is not None and "placa" in eq:
            eq["placa"] = {"monofasica": True, "trifasica": "tri", "sem_placa": False}[eq["placa"]]
        lotes = tuple(a.pop("lotes", None) or lotes_tecnicos.LOTES)
        o = lotes_tecnicos.note(a, lotes)
        res = [o["sous_titre"]]
        if "isolamento" in o:
            res.append(f"Isolamento: {o['isolamento']['sistema_nome']}, U = {o['isolamento']['U']:.3f} W/(m².°C) (Umáx {o['isolamento']['umax']:g})")
        if "aquecimento" in o:
            p_ = o["aquecimento"]
            res.append(f"Perdas: θe {p_['theta_e']:g} °C, total {p_['phi_total']:.0f} W ({p_['w_m2']:.0f} W/m²) — "
                       + ", ".join(f"{r['nome']} {r['phi']:.0f} W" for r in p_["divisoes"]))
        if "piso_radiante" in o:
            pr = o["piso_radiante"]
            res.append(f"Piso radiante: ida {pr['theta_ida']:.1f} °C, {pr['circuitos']} circuitos, {pr['coletores']} coletor(es), {pr['tubo_total_m']:.0f} m de tubo, "
                       f"caudal {pr['caudal_total_lh']:.0f} L/h, apoio {pr['apoio_total_w']:.0f} W")
        if "bomba_calor" in o:
            b = o["bomba_calor"]
            res.append(f"Bomba de calor: {b['p_nominal_kw']:g} kW (A7/W35) → {b['p_theta_e_kw']:.1f} kW a θe ({b['cobertura'] * 100:.0f} %), apoio {b['apoio_kw']:g} kW, "
                       f"{b['p_absorvida_kw']:.1f} kW absorvidos")
        if "eletricidade" in o:
            e = o["eletricidade"]
            res.append(f"Eletricidade: {e['tomadas']} tomadas, {e['pontos_luz']} pontos de luz, {len(e['circuitos'])} circuitos → contratar {e['potencia_contratada_kva']:g} kVA "
                       f"({e['alimentacao']})")
        if "canalizacao" in o:
            k = o["canalizacao"]
            res.append(f"Canalização: Qc {k['qc_l_s']:.2f} L/s, ramal {k['tubo_af']}, pressão {k['pressao_kpa']:.0f} kPa; tubo de queda Ø{k['tubo_queda_mm']}")
        if "solar_termico" in o and o["solar_termico"]["dimensionamento"]:
            d = o["solar_termico"]["dimensionamento"]
            res.append(f"Solar térmico: {d['ocupantes']} ocupantes, Qa {d['Qa_kwh']:.0f} kWh/ano, área sugerida {d['area_sugerida_m2']:.1f} m²"
                       + (f", fração solar {d['fracao_solar'] * 100:.0f} %" if d.get("fracao_solar") is not None else ""))
        for k in lotes_tecnicos.LOTES:
            if k in o and isinstance(o[k], dict):
                res += _ctl(o[k].get("controles"))
        res += _hyp(o["hipoteses"])
        data = {"lotes": [k for k in lotes_tecnicos.LOTES if k in o]}
        if "aquecimento" in o:
            data["phi_total_w"] = o["aquecimento"]["phi_total"]
        if "bomba_calor" in o:
            data["p_nominal_kw"] = o["bomba_calor"]["p_nominal_kw"]
        if "eletricidade" in o:
            data["potencia_contratada_kva"] = o["eletricidade"]["potencia_contratada_kva"]
        return _ret(o, res, data)
    if name == "calcul_piso_radiante":
        o = piso_radiante.note(a)
        res = [o["titre"], f"Ida {o['theta_ida']:.1f} °C / retorno {o['theta_retorno_crit']:.1f} °C, {o['circuitos']} circuitos, {o['coletores']} coletor(es), "
                           f"{o['tubo_total_m']:.0f} m de tubo, caudal {o['caudal_total_lh']:.0f} L/h, volume {o['volume_agua_l']:.0f} L, apoio {o['apoio_total_w']:.0f} W",
               "Divisões: " + "; ".join(f"{r['nome']} {r['q']:.0f} W/m², θF {r['tf']:.1f} °C, passo {r['passo']} cm, {r['caudal_lh']:.0f} L/h" for r in o["divisoes"])]
        res += _ctl(o["controles"]) + _hyp(o["hipoteses"])
        return _ret(o, res, {"theta_ida": o["theta_ida"], "circuitos": o["circuitos"], "apoio_total_w": o["apoio_total_w"]})
    if name == "verificar_solar_termico":
        o = solar_termico.note(a)
        res = [o["titre"] + " — " + o["sous_titre"]]
        d = o["dimensionamento"]
        if d:
            res.append(f"AQS: {d['ocupantes']} ocupantes, {d['consumo_l_dia']:.0f} L/dia, Qa {d['Qa_kwh']:.0f} kWh/ano; área sugerida {d['area_sugerida_m2']:.1f} m², "
                       f"acumulação {d['volume_sugerido_l'][0]:.0f}–{d['volume_sugerido_l'][1]:.0f} L"
                       + (f"; produção {d['producao_kwh']:.0f} kWh/ano, fração solar {d['fracao_solar'] * 100:.0f} %" if d.get("producao_kwh") is not None else ""))
        res += _ctl(o["controles"]) + _hyp(o["hipoteses"])
        return _ret(o, res, {"nao_conformes": sum(1 for c in o["controles"] if c["ok"] is False), "a_verificar": sum(1 for c in o["controles"] if c["ok"] is None)})
    if name == "calcul_patio_pluvial":
        o = patio_pluviais.note(a)
        res = [o["titre"], f"Caudal de projeto {o['Q']:.2f} L/s (I {o['I']:.0f} mm/h, região {o['regiao']}, T {o['T']} anos, área de cálculo {o['A_calc']:.1f} m²); solução: "
                           + ("descarga gravítica" if o["solucao"] == "gravitica" else "estação elevatória"),
               f"2 bombas {o['bomba_m3h']} m³/h a {o['AMT']:.1f} m c.a. (≈ {o['P_kW']:g} kW), compressão PVC DN {o['dn_imp']} ({o['v_imp']:.2f} m/s), poço {o['poco']} "
               f"com {o['Vu_L']:.0f} L úteis; retenção em avaria {o['V_ret']:.1f} m³ (chuvada 1 h/10 anos {o['V10']:.1f} m³)"]
        res += _ctl(o["controles"]) + _hyp(o["hipoteses"])
        return _ret(o, res, {"Q_l_s": o["Q"], "bomba_m3h": o["bomba_m3h"], "AMT_m": o["AMT"]})
    raise ValueError(f"ferramenta de cálculo desconhecida: {name}")

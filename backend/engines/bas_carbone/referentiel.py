"""Referencial da Carta de Obra de Baixo Carbono (modelo ConstruPilot « Charte_Chantier_Bas_Carbone-v3 », versão portuguesa).

Portugal não tem (à data) valor-limite legal de carbono incorporado para edifícios: a Diretiva (UE) 2024/1275, art.º 7.º,
obriga a CALCULAR e divulgar o potencial de aquecimento global (PAG) do ciclo de vida dos edifícios novos (> 1000 m² a
partir de 2028, todos a partir de 2030), sem limite fixado na lei nacional. A meta em kgCO2e/m² é portanto definida pelo
dono de obra / caderno de encargos e introduzida no dossier — nunca um valor inventado.

Regra : nenhum valor « real » é inventado. Sem DAP (declaração ambiental de produto, EN 15804), a linha conta com o fator
de referência (nenhum ganho reivindicado) e é levantado o controlo « DAP em falta ».
"""
from __future__ import annotations

import re
import unicodedata

SOURCE_TABLEAU = "Quadro ConstruPilot Carta de Obra de Baixo Carbono v3"
SOURCE_RE2020 = "Meta definida pelo dono de obra (sem valor-limite legal em Portugal ; Diretiva (UE) 2024/1275, art.º 7.º)"
SOURCE_ELEC = "APA — Fator de Emissão da Eletricidade 2025 (valor anual 2023 : 0,107 tCO2eq/MWh)"

LOTS = ["Estrutura e alvenarias", "Cobertura / estrutura de madeira", "Fachadas e envolvente", "Caixilharias e carpintarias",
        "Acabamentos interiores", "Revestimentos e pavimentos", "Instalações técnicas (AVAC / Eletricidade / Águas)",
        "Arranjos exteriores e infraestruturas"]
L_EST, L_COB, L_FAC, L_CAIX, L_ACAB, L_REV, L_INST, L_EXT = LOTS

TYPOLOGIES = {          # sem valor-limite legal em Portugal : a meta é sempre introduzida (None = a definir)
    "Moradia unifamiliar": None,
    "Habitação coletiva": None,
    "Serviços / escritórios": None,
    "Escolar": None,
    "Outro": None,
}
JALONS = {"Diretiva (UE) 2024/1275": 2030}
TYPOLOGIES_MATERIAU = ["Standard", "Baixo carbono", "Biológico", "Geológico", "Reciclado", "Reutilização"]
STATUTS = ["Conforme", "Em curso", "A iniciar", "Não conforme", "Não aplicável"]


def seuil_ic(typologie: str, jalon: str) -> float | None:
    """Portugal : nenhuma meta legal codificada — o valor vem do dono de obra (campo « meta »)."""
    return None


# --------------------------------------------------------------------------------------------------------------------------------
# Famílias de materiais. fe_ref / fe_type : valores do quadro ConstruPilot (kg CO2e por unidade) ; plage : limites de
# verosimilhança de uma DAP para ESTA unidade (deteta erros de unidade — DAP por kg lida por m³ — não é critério legal).
# mots : palavras-chave de associação de um documento (DAP, ficha técnica, guia de remessa) ou de uma linha de medição.
FAMILLES = [
    dict(code="beton", lot=L_EST, famille="Betão pronto (paredes / lajes / fundações)", solution="Betão com cimento de baixo clínquer (CEM II/B, CEM III/A)",
         typologie="Baixo carbono", unite="m³", fe_ref=250, fe_type=155, ref_type="DAP coletiva / fabricante", plage=(80, 500), lourd=True,
         densite_t=2.4, mots=["betao", "beton", "cem ", "c25/30", "c30/37", "c20/25", "c16/20", "c35/45", "sapata", "ensoleiramento", "laje de pavimento", "betonagem", "bpe"]),
    dict(code="acier", lot=L_EST, famille="Aço para betão armado (armaduras)", solution="Aço reciclado de forno elétrico (100 %)",
         typologie="Reciclado", unite="t", fe_ref=2100, fe_type=720, ref_type="DAP aço reciclado", plage=(250, 3500), lourd=True,
         densite_t=1.0, mots=["aco", "armadura", "varao", "varoes", "a500", "a400", "malhasol", "rede electrossoldada", "ferro", "acier", "b500"]),
    dict(code="bois", lot=L_COB, famille="Estrutura de madeira / cobertura",
         solution="Madeira estrutural nacional (lamelada-colada / maciça)", typologie="Biológico", unite="m³", fe_ref=450, fe_type=-520,
         ref_type="DAP madeira (carbono armazenado incluído)", plage=(-1000, 400), lourd=True, densite_t=0.5,
         mots=["madeira", "lamelada", "gl24", "c24", "asna", "madre", "varedo", "frechal", "clt", "pinho", "kvh"]),
    dict(code="isolant", lot=L_FAC, famille="Isolamento térmico paredes / cobertura", solution="Aglomerado de cortiça expandida ou fibra de madeira",
         typologie="Biológico", unite="m²", fe_ref=12.5, fe_type=3.2, ref_type="DAP isolamento", plage=(-15, 40), lourd=False,
         mots=["isolamento", "isolante", "la mineral", "la de rocha", "la de vidro", "xps", "eps", "poliestireno", "cortica", "icb", "etics", "capoto", "poliuretano"]),
    dict(code="menuiserie", lot=L_CAIX, famille="Caixilharia exterior", solution="Caixilharia mista madeira / alumínio reciclado",
         typologie="Baixo carbono", unite="m²", fe_ref=145, fe_type=88, ref_type="DAP caixilharia", plage=(20, 400), lourd=False,
         mots=["janela", "caixilharia", "caixilho", "porta-janela", "envidracado", "vidro duplo", "correr", "oscilobatente"]),
    dict(code="cloison", lot=L_ACAB, famille="Divisórias e revestimentos de gesso cartonado", solution="Gesso cartonado reciclado / estrutura reutilizada",
         typologie="Reutilização", unite="m²", fe_ref=8.4, fe_type=4.1, ref_type="DAP / Ficha de reutilização", plage=(1, 35), lourd=False,
         mots=["divisoria", "gesso cartonado", "pladur", "placa de gesso", "teto falso", "tecto falso", "montante", "perfil metalico"]),
    dict(code="sol_souple", lot=L_REV, famille="Revestimento de piso flexível", solution="Linóleo natural ou alcatifa reutilizada",
         typologie="Biológico", unite="m²", fe_ref=14, fe_type=5.5, ref_type="DAP revestimento", plage=(1, 40), lourd=False,
         mots=["linoleo", "alcatifa", "vinilico", "pvc", "lvt", "piso flexivel"]),
    dict(code="pac", lot=L_INST, famille="Produção de aquecimento / AQS (AVAC)",
         solution="Bomba de calor com fluido de baixo PAG (R290/R32)", typologie="Baixo carbono", unite="u", fe_ref=1850, fe_type=1120,
         ref_type="PEP / DAP bomba de calor", plage=(200, 8000), lourd=False,
         mots=["bomba de calor", "termoacumulador", "caldeira", "r290", "r32", "aqs", "aerotermia"]),
    dict(code="gaine", lot=L_INST, famille="Condutas de ventilação / AVAC",
         solution="Condutas em aço galvanizado reciclado / reutilização", typologie="Reciclado", unite="ml", fe_ref=18, fe_type=9.5,
         ref_type="DAP conduta", plage=(0.5, 60), lourd=False, mots=["conduta", "vmc", "ventilacao", "extracao", "aeraulica"]),
    dict(code="canalisation", lot=L_INST, famille="Tubagens de águas e esgotos",
         solution="Tubos PEAD / PP reciclado ou ferro fundido reciclado", typologie="Reciclado", unite="ml", fe_ref=11.2, fe_type=5.8,
         ref_type="DAP tubagem", plage=(0.3, 40), lourd=False,
         mots=["tubagem", "tubo", "pead", "multicamada", "pex", "pvc esgoto", "tubo de queda", "coletor", "ferro fundido"]),
    dict(code="cable", lot=L_INST, famille="Cablagem elétrica e caminhos de cabos",
         solution="Cabos de cobre reciclado / caminhos de cabos reutilizados", typologie="Reutilização", unite="ml", fe_ref=6.5, fe_type=2.9,
         ref_type="PEP cabos", plage=(0.1, 20), lourd=False, mots=["cabo", "condutor", "caminho de cabos", "xv ", "h07", "vd "]),
    dict(code="grave", lot=L_EXT, famille="Agregados e sub-bases de pavimento", solution="Agregado reciclado de RCD local",
         typologie="Reciclado", unite="t", fe_ref=18, fe_type=4.5, ref_type="DAP agregado reciclado", plage=(0.5, 40), lourd=True, densite_t=1.0,
         mots=["agregado", "tout-venant", "toutvenant", "brita", "abge", "sub-base", "rachao", "areia"]),
    dict(code="enrobe", lot=L_EXT, famille="Pavimentos betuminosos", solution="Mistura betuminosa temperada com material fresado reciclado",
         typologie="Baixo carbono", unite="t", fe_ref=68, fe_type=42, ref_type="DAP mistura betuminosa", plage=(10, 150), lourd=True, densite_t=1.0,
         mots=["betuminoso", "betume", "ac 14", "ac 10", "asfalto", "tapete"]),
    dict(code="cloture", lot=L_EXT, famille="Mobiliário exterior / vedações", solution="Madeira local não tratada ou aço reciclado",
         typologie="Biológico", unite="ml", fe_ref=45, fe_type=14, ref_type="DAP arranjos exteriores", plage=(1, 150), lourd=False,
         mots=["vedacao", "portao", "rede de vedacao", "gradeamento", "mobiliario exterior"]),
    # Famílias da medição sem valor de referência no quadro : fator a introduzir (DAP ou dado genérico)
    dict(code="maconnerie", lot=L_EST, famille="Alvenarias (blocos / tijolo)", solution="", typologie="Standard", unite="m²",
         fe_ref=None, plage=(5, 120), lourd=True, mots=["alvenaria", "tijolo", "bloco", "termoargila", "porotherm", "empena"]),
    dict(code="plancher", lot=L_EST, famille="Laje aligeirada (vigotas e abobadilhas)", solution="", typologie="Standard", unite="m²",
         fe_ref=None, plage=(20, 250), lourd=True, mots=["vigota", "abobadilha", "laje aligeirada", "pre-laje"]),
    dict(code="couverture", lot=L_FAC, famille="Revestimento de cobertura (telha / zinco / painel)", solution="", typologie="Standard",
         unite="m²", fe_ref=None, plage=(2, 80), lourd=False, mots=["cobertura", "telha", "zinco", "painel sandwich", "caleira", "tubo de queda pluvial"]),
    dict(code="enduit", lot=L_FAC, famille="Reboco de fachada", solution="", typologie="Standard", unite="m²",
         fe_ref=None, plage=(1, 30), lourd=False, mots=["reboco", "monomassa", "argamassa de reboco", "enduit"]),
    dict(code="chape", lot=L_REV, famille="Betonilha / cerâmico / azulejo", solution="", typologie="Standard", unite="m²",
         fe_ref=None, plage=(2, 60), lourd=False, mots=["betonilha", "ceramico", "azulejo", "mosaico", "gres", "porcelanico", "cola"]),
    dict(code="parquet", lot=L_REV, famille="Soalho / flutuante", solution="", typologie="Biológico", unite="m²",
         fe_ref=None, plage=(-20, 40), lourd=False, mots=["soalho", "parquet", "flutuante", "taco"]),
    dict(code="peinture", lot=L_REV, famille="Pinturas", solution="", typologie="Standard", unite="m²",
         fe_ref=None, plage=(0.1, 10), lourd=False, mots=["pintura", "tinta", "verniz", "esmalte"]),
    dict(code="menuiserie_int", lot=L_CAIX, famille="Carpintarias interiores (portas, roupeiros)", solution="", typologie="Standard",
         unite="u", fe_ref=None, plage=(5, 300), lourd=False, mots=["porta interior", "roupeiro", "porta de garagem", "porta de entrada", "aro"]),
    dict(code="sanitaire", lot=L_INST, famille="Louças sanitárias", solution="", typologie="Standard",
         unite="u", fe_ref=None, plage=(5, 600), lourd=False, mots=["sanita", "lavatorio", "base de duche", "banheira", "lava-loica", "bide"]),
    dict(code="appareillage", lot=L_INST, famille="Aparelhagem elétrica / quadro", solution="",
         typologie="Standard", unite="u", fe_ref=None, plage=(0.2, 800), lourd=False, mots=["tomada", "interruptor", "quadro eletrico", "rj45", "luminaria", "projetor"]),
]


# Equivalentes franceses (modelo v3, FDES e guias francesas) : nome da família FR + palavras-chave FR, para associar também
# documentos e quadros vindos de França.
FR_ALIAS = {'acier': ("Acier d'armature (ferraillage)",
           ['acier', 'armature', 'ferraillage', 'treillis', 'ha8', 'ha10', 'ha12', 'b500', 'fer a beton']),
 'appareillage': ('Appareillage électrique / tableau', ['prise', 'interrupteur', 'tableau electrique', 'rj45', 'spot', 'luminaire']),
 'beton': ("Béton prêt à l'emploi (voiles/planchers)",
           ['beton', 'bpe', 'cem ', 'c25/30', 'c30/37', 'c20/25', 'c16/20', 'c35/45', 'voile', 'semelle', 'dallage']),
 'bois': ('Structure porteuse / charpente', ['bois', 'lamelle', 'gl24', 'c24', 'charpente', 'panne', 'chevron', 'sabliere', 'clt', 'kvh']),
 'cable': ('Câblage électrique et chemins de câbles', ['cable', 'câble', 'chemin de cable', 'r2v', 'h07']),
 'canalisation': ('Canalisations plomberie / évacuation',
                  ['canalisation', 'tube', 'pehd', 'multicouche', 'pvc evacuation', 'chute', 'collecteur', 'fonte']),
 'chape': ('Chape / carrelage / faïence', ['chape', 'carrelage', 'faience', 'gres', 'ceramique', 'colle']),
 'cloison': ('Cloisons et doublages intérieurs',
             ['cloison', 'plaque de platre', 'placo', 'ba13', 'plafond', 'ossature metallique', 'rail', 'montant']),
 'cloture': ('Mobilier extérieur / clôtures', ['cloture', 'portail', 'grillage', 'mobilier exterieur']),
 'couverture': ('Couverture (tuiles / ardoises / zinc)', ['couverture', 'tuile', 'ardoise', 'zinc', 'bac acier', 'gouttiere', 'descente']),
 'enduit': ('Enduit de façade', ['enduit', 'monocouche', 'crepi']),
 'enrobe': ('Revêtements de voirie / enrobés', ['enrobe', 'bitume', 'bb 0/10', 'bbsg', 'asphalte']),
 'gaine': ('Réseaux ventilation / gaines CVC', ['gaine', 'vmc', 'aeraulique', 'ventilation', 'conduit']),
 'grave': ('Grave et empierrement voirie', ['grave', 'gnt', 'granulat', 'empierrement', '0/31,5', '0/20', 'tout-venant']),
 'isolant': ('Isolant thermique murs / toiture',
             ['isolant', 'isolation', 'laine', 'ouate', 'polystyrene', 'pse', 'pu ', 'polyurethane', 'fibre de bois', 'doublage',
              'rampant']),
 'maconnerie': ('Maçonnerie (blocs béton / briques)', ['parpaing', 'bloc', 'brique', 'porotherm', 'maconnerie', 'pignon', 'agglo']),
 'menuiserie': ('Menuiseries extérieures', ['fenetre', 'menuiserie', 'baie', 'porte-fenetre', 'chassis', 'coulissant', 'vitrage']),
 'menuiserie_int': ('Menuiseries intérieures (portes, placards)',
                    ['porte interieure', 'bloc-porte', 'placard', 'porte de garage', "porte d'entree"]),
 'pac': ('Production chauffage / ECS (CVC)',
         ['pompe a chaleur', 'pac', 'chauffe-eau', 'thermodynamique', 'chaudiere', 'r290', 'r32', 'ecs']),
 'parquet': ('Parquet', ['parquet', 'stratifie']),
 'peinture': ('Peintures', ['peinture', 'lasure', 'vernis']),
 'plancher': ('Plancher poutrelles-hourdis', ['poutrelle', 'hourdis', 'plancher', 'predalle']),
 'sanitaire': ('Appareils sanitaires', ['wc', 'lavabo', 'douche', 'baignoire', 'evier', 'receveur']),
 'sol_souple': ('Revêtement de sol souple', ['lino', 'linoleum', 'moquette', 'sol souple', 'pvc', 'vinyle', 'lvt'])}
for _f in FAMILLES:
    _nom, _mots = FR_ALIAS.get(_f["code"], ("", []))
    _f["nom_fr"] = _nom
    _f["mots"] = list(dict.fromkeys(_f["mots"] + _mots))
FAMILLE = {f["code"]: f for f in FAMILLES}

# --------------------------------------------------------------------------------------------------------------------------------
# Emissões da fase de obra
EMISSIONS = [
    ("gnr", "Máquinas de obra", "Gasóleo colorido e marcado (máquinas)", "L", 3.16, "kgCO2e / L"),
    ("hvo", "Máquinas de obra", "Biocombustível HVO100 (redução ~80 %)", "L", 0.6, "kgCO2e / L"),
    ("engins_elec", "Máquinas de obra", "Máquinas elétricas (consumo elétrico dedicado)", "kWh", 0.107, "kgCO2e / kWh"),
    ("elec_base_vie", "Estaleiro e energia", "Eletricidade da rede Portugal (APA, 2023)", "kWh", 0.107, "kgCO2e / kWh"),
    ("eau", "Estaleiro e energia", "Água potável consumida", "m³", 0.132, "kgCO2e / m³"),
    ("transport_appro", "Transporte e logística", "Transporte pesado articulado (abastecimento)", "t.km", 0.089, "kgCO2e / t.km"),
    ("transport_deblais", "Transporte e logística", "Transporte de terras / escavação para fora da obra", "t.km", 0.115, "kgCO2e / t.km"),
    ("dechets_inertes", "Resíduos de obra (RCD)", "RCD inertes enviados para aterro", "t", 12, "kgCO2e / t"),
    ("dechets_dib", "Resíduos de obra (RCD)", "RCD não perigosos misturados enviados para aterro", "t", 380, "kgCO2e / t"),
    ("mobilite", "Mobilidade das equipas", "Deslocações casa-obra (automóvel a combustão)", "km", 0.218, "kgCO2e / km"),
]

# --------------------------------------------------------------------------------------------------------------------------------
CHARTE = [
    ("c01", "1. Materiais e abastecimento", "Privilegiar materiais de origem biológica, geológica ou de baixa pegada (betão de baixo clínquer, aço reciclado)",
     "Parte de materiais de baixo carbono / biológicos no total", ">=", 30, "%", "Empresas / Projetista", "DAP a fornecer (separador Materiais)", "part_bas_carbone", "fdes"),
    ("c02", "1. Materiais e abastecimento", "Favorecer a reutilização de materiais na obra ou por fileiras locais",
     "Taxa de materiais reutilizados na obra", ">=", 10, "%", "Dono de obra / Empresas", "Plano de Prevenção e Gestão de RCD (PPGRCD)", "part_reemploi", "pemd"),
    ("c03", "1. Materiais e abastecimento", "Limitar o transporte recorrendo a circuitos curtos",
     "Distância média de abastecimento dos materiais pesados", "<=", 100, "km", "Empresas", "Guias de remessa / transporte", "distance_lourds", "bl"),
    ("c04", "2. Máquinas e logística", "Substituir máquinas a combustão por equipamentos elétricos, híbridos ou a biocombustível (HVO)",
     "Parte de máquinas de baixo carbono no parque ativo", ">=", 50, "%", "Empresas", "Inventário de equipamentos e faturas HVO", "part_engins_bas_carbone", "carburant"),
    ("c05", "2. Máquinas e logística", "Limitar o funcionamento dos motores ao ralenti (sensibilização e corte automático)",
     "Horas de ralenti evitadas / conformidade nos controlos", ">=", 100, "%", "Diretor de obra", "Registos de telemetria / inspeções", None, "releve"),
    ("c06", "2. Máquinas e logística", "Agrupar entregas e otimizar os fluxos logísticos",
     "Redução das rotações de camiões (vs planeamento inicial)", ">=", 20, "%", "Logística / Empresas", "Planeamento de entregas", None, "planning"),
    ("c07", "3. Sobriedade energética do estaleiro", "Acompanhar os consumos de água e eletricidade com contadores dedicados",
     "Frequência de leitura dos contadores (água e eletricidade)", ">=", 1, "leitura / mês", "Responsável carbono", "Quadro de acompanhamento mensal", None, "releve"),
    ("c08", "3. Sobriedade energética do estaleiro", "Instalar iluminação LED com detetores de presença",
     "Taxa de equipamento LED + deteção no estaleiro", ">=", 100, "%", "Empresa de instalação", "Auto de receção do estaleiro", None, "pv"),
    ("c09", "3. Sobriedade energética do estaleiro", "Otimizar o isolamento e a climatização dos contentores de obra",
     "Consumo energético do estaleiro por m²", "<=", 80, "kWh/m²", "Empresa de instalação", "Fichas técnicas dos contentores", None, "fiche"),
    ("c10", "4. Gestão de resíduos e terraplenagens", "Implementar triagem rigorosa na origem (contentor por fluxo) — PPGRCD",
     "Taxa de valorização material e reciclagem dos RCD", ">=", 75, "%", "Empresas / Subempreiteiros", "e-GAR (guias eletrónicas de acompanhamento de resíduos, SILiAmb)", "taux_valorisation", "bsd"),
    ("c11", "4. Gestão de resíduos e terraplenagens", "Reutilizar ao máximo as terras escavadas na própria obra",
     "Taxa de reutilização das terras escavadas na obra", ">=", 80, "%", "Empreiteiro de movimentação de terras / Projetista", "Registo de terras / balanço escavação-aterro", None, "registre"),
    ("c12", "5. Mobilidade das equipas", "Incentivar a partilha de viatura, os transportes públicos ou a mobilidade suave",
     "Parte dos trabalhadores com mobilidade alternativa ao veículo individual", ">=", 40, "%", "Empresas / Responsável", "Inquérito de mobilidade / plano de acessos", None, "enquete"),
    ("c13", "6. Pilotagem e sensibilização", "Nomear um responsável ambiente / carbono dedicado à obra",
     "Nomeação oficial e presença nas reuniões de obra", ">=", 100, "%", "Empreiteiro geral", "Organigrama da obra", None, "organigramme"),
    ("c14", "6. Pilotagem e sensibilização", "Formar e sensibilizar os trabalhadores para os ecogestos",
     "Taxa de trabalhadores sensibilizados no acolhimento da obra", ">=", 100, "%", "Responsável carbono", "Folhas de presença das ações de sensibilização", None, "emargement"),
    ("c15", "6. Pilotagem e sensibilização", "Acompanhar os indicadores de emissões de GEE ao longo da obra",
     "Balanço de carbono da obra atualizado mensalmente", ">=", 100, "%", "Responsável carbono / Projetista", "Consolidação no separador Sintese", None, "bilan"),
]
CHARTE_KEYS = ("id", "axe", "action", "kpi", "op", "cible", "unite", "acteur", "preuve", "auto", "type_preuve")

FDES_VALIDITE_ANS = 5          # validade de uma DAP (EN 15804, programas DAPHabitat / EPD) : 5 anos
ECART_LIVRAISON = 0.10         # desvio tolerado entre quantidade entregue (guias) e quantidade prevista na medição


def fold(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s)


def famille_de(texte: str) -> str | None:
    """Famille de matériau d'une désignation (mot-clé le plus long trouvé ; None sinon)."""
    t = " " + fold(texte) + " "
    for f in FAMILLES:                                   # libellé exact d'une famille du tableau : prioritaire
        if fold(f["famille"]) in t or (f.get("nom_fr") and fold(f["nom_fr"]) in t):
            return f["code"]
    best, blen = None, 0
    for f in FAMILLES:
        for m in f["mots"]:
            k = fold(m)
            hit = re.search(r"(?<![a-z0-9])" + re.escape(k.strip()) + r"(?![a-z0-9])", t) if len(k.strip()) <= 4 else k in t
            if hit and len(k) > blen:                    # mots courts (pac, bpe, cem…) : mot entier seulement
                best, blen = f["code"], len(k)
    return best


UNITES = {"m3": "m³", "m³": "m³", "mc": "m³", "m2": "m²", "m²": "m²", "ml": "ml", "m": "ml", "mètre linéaire": "ml", "metro linear": "ml", "un": "u", "un.": "u", "unid": "u", "unid.": "u", "uni": "u",
          "t": "t", "tonne": "t", "tonnes": "t", "kg": "kg", "u": "u", "unite": "u", "unité": "u", "pce": "u", "pièce": "u",
          "piece": "u", "ens": "u", "ft": "u", "l": "L", "litre": "L", "litres": "L", "kwh": "kWh", "km": "km", "t.km": "t.km"}


def unite(u) -> str:
    k = str(u or "").strip().lower().replace("³", "3").replace("²", "2")
    k = {"m3": "m3", "m2": "m2"}.get(k, k)
    return UNITES.get(k, UNITES.get(str(u or "").strip().lower(), str(u or "").strip()))


def facteur_unite(de: str, vers: str) -> float | None:
    """Coefficient pour passer une quantité / un FE de l'unité `de` à `vers` (None = conversion impossible sans densité)."""
    de, vers = unite(de), unite(vers)
    if de == vers:
        return 1.0
    if (de, vers) == ("kg", "t"):
        return 0.001
    if (de, vers) == ("t", "kg"):
        return 1000.0
    return None

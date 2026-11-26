"""Catalogue français du Studio de projet (Estúdio de Projeto) : texte interne en portugais → texte français.

EXATOS      texte entier → traduction.
MODELOS     modèle avec « {} » (valeur quelconque) ou « {n} » (nombre) → français avec « {0} », « {1} »… ; les valeurs
            capturées sont elles-mêmes traduites (texte exact, autre modèle ou fragment).
FRAGMENTOS  mots isolés (« fachada », « duas aguas »…) : traduits seulement à l'intérieur d'un modèle ou d'un texte
            composé, jamais comme texte entier — ce sont aussi des clés de logique du modèle.
CHAVES      noms de propriétés des jeux propres de l'IFC (identifiants sans espace ni accent).
CAMADAS_DXF noms des calques du DXF.
SINONIMOS   mots français acceptés dans les opérations de l'Assistant → clés du moteur.
PISOS       noms de niveau par défaut que le modèle peut enregistrer (aller-retour avec l'éditeur).

Vocabulaire du bâtiment en France : mur / cloison, baie, allège, hauteur sous plafond (HSP), plancher, toiture, égout,
faîtage, pignon, trémie, giron, hauteur de marche, emprise au sol, menuiseries, doublage, ITE / ITI.
Les termes « surface de plancher » et « surface habitable » (définitions réglementaires) ne sont volontairement pas
employés pour les surfaces géométriques du modèle : « surface hors œuvre » et « surface utile ».
"""
from __future__ import annotations

from engines.estudio_projeto import i18n_fr_acabamentos as _A
from engines.estudio_projeto import i18n_fr_biblioteca as _B
from engines.estudio_projeto import i18n_fr_objetos as _O

PISOS = ["Rés-do-chão", "1.º andar", "2.º andar", "3.º andar", "4.º andar", "5.º andar"]

_MENSAGENS = {
    # ------------------------------------------------------------------ niveaux
    "Rés-do-chão": "Rez-de-chaussée",
    "1.º andar": "Étage 1", "2.º andar": "Étage 2", "3.º andar": "Étage 3", "4.º andar": "Étage 4", "5.º andar": "Étage 5",
    # ------------------------------------------------------------------ murs de départ (France) et bibliothèque française
    "Parede exterior 30 cm (bloco de betão 20 + isolamento interior colado)": "Mur extérieur 30 cm (parpaing 20 + doublage isolant collé 10+80)",
    "Parede interior 10 cm (blocos de gesso maciço)": "Cloison 10 cm (carreaux de plâtre pleins)",
    "Bloco de gesso maciço": "Carreau de plâtre plein",
    "Bloco de gesso hidrófugo": "Carreau de plâtre hydrofuge",
    "Exterior — bloco de betão 20 + isolamento interior colado 13+120": "Extérieur — parpaing 20 + doublage collé 13+120 (ITI)",
    "Exterior — bloco de betão 20 + lã de vidro 12 em estrutura + gesso cartonado":
        "Extérieur — parpaing 20 + laine de verre 12 sur ossature + plaque de plâtre (ITI)",
    "Exterior — tijolo 20 + isolamento interior colado 13+120": "Extérieur — brique 20 + doublage collé 13+120 (ITI)",
    "Exterior — bloco térmico 37,5 rebocado nas duas faces": "Extérieur — brique monomur 37,5 enduite sur les deux faces",
    "Exterior — bloco de betão 20 + ETICS EPS cinza 14 cm": "Extérieur — parpaing 20 + ITE PSE gris 14 cm sous enduit",
    "Exterior — betão armado 18 + isolamento interior colado 13+120": "Extérieur — béton banché 18 + doublage collé 13+120 (ITI)",
    "Interior — blocos de gesso maciço 7": "Intérieur — carreaux de plâtre pleins 7",
    "Interior — blocos de gesso hidrófugo 7 (zonas húmidas)": "Intérieur — carreaux de plâtre hydrofuges 7 (pièces humides)",
    "Interior — bloco de betão 20 rebocado a gesso nas duas faces": "Intérieur — mur de refend parpaing 20 enduit plâtre sur les deux faces",
    "Nomes, espessuras de catálogo e cores de representação. Sem valores térmicos, acústicos ou preços.":
        "Noms, épaisseurs de catalogue et couleurs de représentation. Sans valeurs thermiques ou acoustiques ni prix.",
    # ------------------------------------------------------------------ modèle : validation
    "Modelo em falta.": "Modèle manquant.",
    "Piso inválido.": "Niveau invalide.",
    "Pisos com o mesmo identificador.": "Plusieurs niveaux ont le même identifiant.",
    "Tipos de parede inválidos.": "Types de murs invalides.",
    "Parede inválida.": "Mur invalide.",
    "Paredes com o mesmo identificador.": "Plusieurs murs ont le même identifiant.",
    "Vão inválido.": "Baie invalide.",
    "Vãos com o mesmo identificador.": "Plusieurs baies ont le même identifiant.",
    "Rótulos inválidos.": "Étiquettes de pièces invalides.",
    "Escada inválida.": "Escalier invalide.",
    "Escadas com o mesmo identificador.": "Plusieurs escaliers ont le même identifiant.",
    "Objeto inválido (tipo ou piso desconhecido).": "Objet invalide (type ou niveau inconnu).",
    "Objetos com o mesmo identificador.": "Plusieurs objets ont le même identifiant.",
    "Cota inválida.": "Cote invalide.",
    "Cotas com o mesmo identificador.": "Plusieurs cotes ont le même identifiant.",
    "Nota inválida.": "Note invalide.",
    "Notas com o mesmo identificador.": "Plusieurs notes ont le même identifiant.",
    "O processo ainda não tem plantas para abrir no Estúdio.": "Le dossier n'a pas encore de plans à ouvrir dans le Studio.",
    "O dossier ainda não tem volumes: defina primeiro as dimensões do edifício.":
        "Le dossier n'a pas encore de volumes : définissez d'abord les dimensions du bâtiment.",
    "O contorno do edifício do dossier não é um polígono simples.": "Le contour du bâtiment du dossier n'est pas un polygone simple.",
    "O edifício do dossier é demasiado estreito para as paredes exteriores de partida.":
        "Le bâtiment du dossier est trop étroit pour les murs extérieurs de départ.",
    # ------------------------------------------------------------------ modèle créé depuis le dossier : avertissements
    "Volume em L ou em T: o Estúdio retoma o contorno real do dossier; a distribuição interior e os vãos "
    "(desenhados para uma planta retangular nas peças PC) ficam por desenhar no Estúdio.":
        "Volume en L ou en T : le Studio reprend le contour réel du dossier ; la distribution intérieure et les baies "
        "(dessinées pour un plan rectangulaire sur les pièces PC) restent à dessiner dans le Studio.",
    "Escada por colocar no Estúdio.": "Escalier à placer dans le Studio.",
    "Distribuição, portas e janelas: proposta-tipo das peças PC (a adaptar pelo arquiteto), não um levantamento. "
    "Verifique que cada divisão tem porta.":
        "Distribution, portes et fenêtres : proposition type des pièces PC (à adapter par l'architecte), pas un relevé. "
        "Vérifiez que chaque pièce a une porte.",
    "Escada retomada das peças PC (posição e largura); o número de degraus é recalculado pelo Estúdio (espelho ≤ 18,5 cm).":
        "Escalier repris des pièces PC (position et largeur) ; le nombre de marches est recalculé par le Studio "
        "(hauteur de marche ≤ 18,5 cm).",
    "Os anexos do dossier não foram importados (implantação rodada ou em L / T): desenhe-os no Estúdio.":
        "Les annexes du dossier n'ont pas été importées (implantation tournée ou en L / T) : dessinez-les dans le Studio.",
    "Alturas: o Estúdio assenta a cobertura na laje do último teto e parte do pavimento acabado do rés-do-chão (±0,00). "
    "O soco de 0,30 m acima do terreno e os 0,20 m de arase do corte PC não são modelados: as cotas de beirado e de "
    "cumeeira do Estúdio não coincidem com as do corte PC, medidas a partir do terreno.":
        "Hauteurs : le Studio pose la toiture sur le plancher haut du dernier niveau et part du sol fini du rez-de-chaussée (±0,00). "
        "Le soubassement de 0,30 m au-dessus du terrain naturel et les 0,20 m d'arase de la coupe PC ne sont pas modélisés : "
        "les cotes d'égout et de faîtage du Studio ne coïncident pas avec celles de la coupe PC, mesurées depuis le terrain naturel.",
    "Cobertura plana: a platibanda de 0,40 m das peças PC não é modelada.":
        "Toiture-terrasse : l'acrotère de 0,40 m des pièces PC n'est pas modélisé.",
    "Paredes de partida: hipóteses editáveis (bloco de betão 20 + isolamento interior colado; divisórias de 10 cm). "
    "A verificar com o estudo térmico RE2020.":
        "Murs de départ : hypothèses modifiables (parpaing 20 + doublage isolant collé ; cloisons de 10 cm). "
        "À vérifier avec l'étude thermique RE2020.",
    "As portas interiores não existem no processo: coloque-as no Estúdio.": "Les portes intérieures n'existent pas dans le dossier : placez-les dans le Studio.",
    # ------------------------------------------------------------------ dérivation : erreurs et avertissements
    "Laje térrea": "Plancher bas du rez-de-chaussée",
    "Laje de cobertura": "Dalle haute du dernier niveau",
    "Portão de garagem (material por definir)": "Porte de garage (matériau à définir)",
    "Fachada exterior": "Façade extérieure",
    "Cobertura": "Toiture",
    "Paredes interiores (faces das divisões)": "Murs intérieurs (faces des pièces)",
    "Caixilharia (vãos exteriores)": "Menuiseries (baies extérieures)",
    "Medições geométricas do modelo: comprimentos líquidos sem contar encontros duas vezes, áreas líquidas com os vãos "
    "descontados, volumes por camada. Não incluem fixações, argamassas, perdas nem preços: não substituem o mapa de quantidades.":
        "Métré géométrique du modèle : longueurs nettes sans compter deux fois les jonctions, surfaces nettes baies déduites, "
        "volumes par couche. Il ne comprend ni fixations, ni mortiers, ni pertes, ni prix : il ne remplace pas le quantitatif détaillé.",
    "O beiral funde partes do contorno: reduza o beiral ou escolha cobertura plana.":
        "Le débord de toit fait se rejoindre des parties du contour : réduisez le débord ou choisissez une toiture-terrasse.",
    "As coberturas de uma e de duas águas pedem um último piso retangular; use «quatro águas» ou «plana».":
        "Les toitures monopente et à deux pentes demandent un dernier niveau rectangulaire ; utilisez « quatre pentes » ou « toiture-terrasse ».",
    "A cobertura de uma água pede um último piso retangular; use «duas águas», «quatro águas» ou «plana».":
        "La toiture monopente demande un dernier niveau rectangulaire ; utilisez « deux pentes », « quatre pentes » ou « toiture-terrasse ».",
    "A cobertura inclinada automática existe em plantas convexas e em plantas ortogonais (L, T, U). Este contorno tem "
    "reentrâncias e lados oblíquos: escolha «plana» ou regularize o último piso.":
        "La toiture en pente automatique existe pour les plans convexes et les plans orthogonaux (L, T, U). Ce contour a des "
        "angles rentrants et des côtés obliques : choisissez « toiture-terrasse » ou régularisez le dernier niveau.",
    "Contorno demasiado recortado para a cobertura inclinada automática: escolha «plana».":
        "Contour trop découpé pour la toiture en pente automatique : choisissez « toiture-terrasse ».",
    # ------------------------------------------------------------------ pièces dessinées
    "Alçado principal (frente)": "Façade avant (sur rue)",
    "Alçado de tardoz": "Façade arrière",
    "Alçado lateral esquerdo": "Façade latérale gauche",
    "Alçado lateral direito": "Façade latérale droite",
    "Projeção ortogonal do modelo; cotas altimétricas relativas à soleira (±0,00).":
        "Projection orthogonale du modèle ; niveaux par rapport au seuil (±0,00).",
    "A escuro: elementos cortados (paredes, lajes, cobertura). A claro: o que fica para lá do plano de corte.":
        "En foncé : éléments coupés (murs, planchers, toiture). En clair : ce qui se trouve au-delà du plan de coupe.",
    "A-A (transversal)": "A-A (transversale)",
    "B-B (longitudinal)": "B-B (longitudinale)",
    "vazio da escada": "trémie",
    "FRENTE": "AVANT (RUE)",
    # ------------------------------------------------------------------ planches PDF (cartouche)
    "Pranchas do Estúdio de Projeto — ConstruPilot": "Planches du Studio de projet — ConstruPilot",
    "Processo": "Dossier",
    "Requerente": "Maître d'ouvrage",
    "Local da obra": "Adresse",
    "Parcela cadastral": "Parcelle",
    "Peça": "Planche",
    "Escala": "Échelle",
    "Data / folha": "Date / planche",
    "Autor do projeto": "Auteur du projet",
    "______________________  (arquiteto: n.º de inscrição na Ordem)": "______________________  (architecte : n° d'inscription à l'Ordre)",
    "Técnico autor": "Auteur du projet",
    "______________________  (n.º de inscrição na Ordem)": "______________________  (n° d'inscription à l'Ordre)",
    # ------------------------------------------------------------------ IFC
    "Terreno": "Terrain",
    "Edifício": "Bâtiment",
    "Vazio da escada": "Trémie d'escalier",
    "Empena": "Pignon",
    "Portada envidraçada": "Porte-fenêtre",
    "Portão de garagem": "Porte de garage",
    "Projeto ConstruPilot": "Projet ConstruPilot",
    "ConstruPilot — Estúdio de Projeto (IfcOpenShell)": "ConstruPilot — Studio de projet (IfcOpenShell)",
    # ------------------------------------------------------------------ opérations
    "Este piso não tem paredes exteriores.": "Ce niveau n'a pas de murs extérieurs.",
    "Parede com menos de 10 cm.": "Mur de moins de 10 cm.",
    "Sala com menos de 60 cm de lado.": "Pièce de moins de 60 cm de côté.",
    "Falta o tipo de parede.": "Le type de mur manque.",
    "Nenhum material indicado.": "Aucun matériau indiqué.",
    "Nada para alterar na divisão.": "Rien à modifier dans la pièce.",
    "O edifício tem de ter pelo menos um piso.": "Le bâtiment doit avoir au moins un niveau.",
    "A escada sobe do piso indicado para o de cima: adicione primeiro o piso de cima.":
        "L'escalier monte du niveau indiqué vers celui du dessus : ajoutez d'abord le niveau supérieur.",
    "Operação mal formada.": "Opération mal formée.",
    "Último piso removido.": "Dernier niveau supprimé.",
    "Nota acrescentada.": "Note ajoutée.",
    # ------------------------------------------------------------------ routes
    "O Estúdio de Projeto abre processos com edifício (casa nova, ampliação, garagem ou anexo).":
        "Le Studio de projet s'ouvre sur les dossiers comportant un bâtiment (maison neuve, extension, garage ou annexe).",
    "O Estúdio parte das medidas do processo. As peças do licenciamento (implantação, quadro de áreas, memória) continuam a "
    "ser as do processo: veja o separador «Processo» para as diferenças.":
        "Le Studio part des mesures du dossier d'urbanisme. Les pièces du dossier (plan de masse, plans PC, notice) restent "
        "celles du dossier : voyez l'onglet « Dossier » pour les différences.",
    "Piso inexistente.": "Niveau inexistant.",
    "Desenhe pelo menos uma parede.": "Dessinez au moins un mur.",
    "As peças do licenciamento são as do processo. O Estúdio não as altera sozinho: use «Levar acabamentos para o processo» "
    "ou corrija o processo para as medidas coincidirem.":
        "Les pièces du dossier d'urbanisme restent celles du dossier. Le Studio ne les modifie pas tout seul : utilisez "
        "« Reporter les finitions dans le dossier » ou corrigez le dossier pour que les mesures coïncident.",
    "Acabamentos levados para o processo: as legendas das peças desenhadas passam a usá-los. A memória descritiva não é "
    "reescrita automaticamente: gere-a de novo se descrever os materiais.":
        "Finitions reportées dans le dossier : les légendes des pièces graphiques PC les utilisent désormais. La notice "
        "descriptive n'est pas réécrite automatiquement : générez-la de nouveau si elle décrit les matériaux.",
    "Estudio-pranchas": "Studio-planches",
    "Estudio-modelo": "Studio-maquette",
    "Estudio-medicoes": "Studio-metre",
    "Estudio-desenhos": "Studio-dessins",
    "Estudio-de-Projeto/": "Studio-de-projet/",
    "LEIA-ME.txt": "LISEZ-MOI.txt",
    "Pranchas-A3-a-escala.pdf": "Planches-A3-a-l-echelle.pdf",
    "Desenhos.dxf": "Dessins.dxf",
    "Medicoes-geometricas.csv": "Metre-geometrique.csv",
    "Modelo.ifc": "Maquette.ifc",
    "ESTÚDIO DE PROJETO — ConstruPilot": "STUDIO DE PROJET — ConstruPilot",
    "Esta pasta contém o modelo editado no Estúdio de Projeto. As peças de licenciamento do processo (fora desta pasta) são as "
    "do processo; o Estúdio não as altera.":
        "Ce dossier contient le modèle modifié dans le Studio de projet. Les pièces du dossier d'urbanisme (hors de ce dossier) "
        "restent celles du dossier ; le Studio ne les modifie pas.",
    "DIFERENÇAS ENTRE O ESTÚDIO E O PROCESSO:": "DIFFÉRENCES ENTRE LE STUDIO ET LE DOSSIER :",
    "{campo}: processo = {a} {u} · Estúdio = {b} {u}": "{campo} : dossier = {a} {u} · Studio = {b} {u}",
    "O Estúdio coincide com o processo nas medidas comparadas (pisos, áreas, cobertura, vãos, acabamentos).":
        "Le Studio coïncide avec le dossier pour les mesures comparées (niveaux, surfaces, toiture, baies, finitions).",
    "ERROS DO MODELO:": "ERREURS DU MODÈLE :",
    # ------------------------------------------------------------------ différences Studio / dossier
    "Número de pisos": "Nombre de niveaux",
    "Área de implantação": "Emprise au sol",
    "Área bruta de construção": "Surface hors œuvre (somme des niveaux)",
    "Área útil": "Surface utile",
    "Tipo de cobertura": "Type de toiture",
    "Inclinação da cobertura": "Pente de la toiture",
    "Altura da cumeeira": "Hauteur du faîtage",
    "Vãos exteriores": "Baies extérieures",
    "Área de vãos na fachada": "Surface de baies en façade",
    # ------------------------------------------------------------------ métré CSV
    "ConstruPilot — Estúdio de Projeto — medições geométricas": "ConstruPilot — Studio de projet — métré géométrique",
    "PAREDES": "MURS", "Piso": "Niveau", "Tipo": "Type", "Comprimento no eixo (m)": "Longueur à l'axe (m)",
    "Comprimento líquido (m)": "Longueur nette (m)", "Altura (m)": "Hauteur (m)", "Espessura (m)": "Épaisseur (m)",
    "Área bruta (m²)": "Surface brute (m²)", "Vãos (m²)": "Baies (m²)", "Área líquida (m²)": "Surface nette (m²)", "Volume (m³)": "Volume (m³)",
    "CAMADAS POR TIPO DE PAREDE": "COUCHES PAR TYPE DE MUR", "Área (m²)": "Surface (m²)",
    "VÃOS": "BAIES", "Largura (m)": "Largeur (m)", "Quantidade": "Quantité", "Identificadores": "Identifiants",
    "MAPA DE VÃOS": "TABLEAU DES MENUISERIES", "Modelo": "Modèle", "Folhas": "Vantaux", "Peitoril (m)": "Allège (m)",
    "Caixilharia": "Menuiserie", "Proteção": "Occultation", "Exterior": "Extérieur",
    "QUADRO DE ÁREAS": "TABLEAU DES SURFACES", "Área útil (m²)": "Surface utile (m²)", "Divisões": "Pièces",
    "Paredes e vazios (m²)": "Murs et vides (m²)", "Área de implantação (m²)": "Emprise au sol (m²)",
    "EQUIPAMENTO E MOBILIÁRIO": "ÉQUIPEMENT ET MOBILIER", "Categoria": "Catégorie",
    "DIVISÕES": "PIÈCES", "Perímetro (m)": "Périmètre (m)", "Paredes da divisão (m²)": "Murs de la pièce (m²)", "Rodapé (m)": "Plinthes (m)",
    "Pavimento": "Sol", "Paredes": "Murs", "Teto": "Plafond",
    "LAJES": "PLANCHERS",
    "ESCADAS": "ESCALIERS", "Espelhos": "Hauteurs de marche (nombre)", "Espelho (m)": "Hauteur de marche (m)", "Cobertores": "Girons (nombre)",
    "Cobertor (m)": "Giron (m)", "2e + c (m)": "2h + g (m)", "Altura vencida (m)": "Hauteur à franchir (m)",
    "Área em planta (m²)": "Surface en plan (m²)", "Vazio na laje (m²)": "Trémie (m²)",
    "ACABAMENTOS": "FINITIONS", "Material": "Matériau",
    "COBERTURA": "TOITURE", "Inclinação (°)": "Pente (°)", "Área real (m²)": "Surface réelle (m²)",
    "Perímetro do beirado (m)": "Périmètre à l'égout (m)", "Empenas (m²)": "Pignons (m²)",
    "FACHADA EXTERIOR": "FAÇADE EXTÉRIEURE",
    "TOTAIS": "TOTAUX", "Área bruta de construção (m²)": "Surface hors œuvre, somme des niveaux (m²)",
}

MODELOS: list[tuple[str, str]] = [
    # ------------------------------------------------------------------ modèle : validation
    ("«{}» tem de ser um número.", "« {0} » doit être un nombre."),
    ("«{}» fora dos limites ({} a {}).", "« {0} » hors limites ({1} à {2})."),
    ("Identificador inválido em «{}».", "Identifiant invalide dans « {0} »."),
    ("«{}» tem de ser um ponto [x, y].", "« {0} » doit être un point [x, y]."),
    ("O modelo precisa de 1 a {} pisos.", "Le modèle doit avoir de 1 à {0} niveaux."),
    ("O tipo de parede «{}» precisa de 1 a {} camadas.", "Le type de mur « {0} » doit avoir de 1 à {1} couches."),
    ("A espessura total do tipo «{}» tem de estar entre 3 cm e 1,5 m.", "L'épaisseur totale du type « {0} » doit être comprise entre 3 cm et 1,5 m."),
    ("Máximo de {} paredes.", "Maximum de {0} murs."),
    ("Máximo de {} vãos.", "Maximum de {0} baies."),
    ("Máximo de {} escadas.", "Maximum de {0} escaliers."),
    ("Máximo de {} objetos.", "Maximum de {0} objets."),
    ("Máximo de {} cotas.", "Maximum de {0} cotes."),
    ("Máximo de {} notas.", "Maximum de {0} notes."),
    ("Máximo de {} pisos.", "Maximum de {0} niveaux."),
    ("A parede «{}» refere um piso que não existe.", "Le mur « {0} » renvoie à un niveau qui n'existe pas."),
    ("A parede «{}» refere um tipo de parede que não existe.", "Le mur « {0} » renvoie à un type de mur qui n'existe pas."),
    ("O vão «{}» refere uma parede que não existe.", "La baie « {0} » renvoie à un mur qui n'existe pas."),
    ("A escada «{}» refere um piso que não existe.", "L'escalier « {0} » renvoie à un niveau qui n'existe pas."),
    # ------------------------------------------------------------------ modèle créé depuis le dossier
    ("O dossier indica {} níveis; as peças PC e o Estúdio partem de {}: acrescente os restantes no Estúdio.",
     "Le dossier indique {0} niveaux ; les pièces PC et le Studio partent de {1} : ajoutez les autres dans le Studio."),
    ("{} porta(s) interior(es) das peças PC sobrepunham-se a outra e não foram importadas: coloque-as no Estúdio.",
     "{0} porte(s) intérieure(s) des pièces PC en chevauchaient une autre et n'ont pas été importées : placez-les dans le Studio."),
    ("O anexo «{}» sobrepõe-se à casa no dossier e não foi importado.", "L'annexe « {0} » chevauche la maison dans le dossier et n'a pas été importée."),
    ("O anexo «{}» é demasiado estreito para paredes de 30 cm e não foi importado.",
     "L'annexe « {0} » est trop étroite pour des murs de 30 cm et n'a pas été importée."),
    ("«{}»: importado com a altura do rés-do-chão ({} m de piso a piso).", "« {0} » : importée avec la hauteur du rez-de-chaussée ({1} m de plancher à plancher)."),
    ("O anexo «{}» não é retangular e não foi importado.", "L'annexe « {0} » n'est pas rectangulaire et n'a pas été importée."),
    # ------------------------------------------------------------------ dérivation
    ("O vão {} {}.", "La baie {0} {1}."),
    ("A parede {} tem menos de 5 cm.", "Le mur {0} mesure moins de 5 cm."),
    ("Divisão {}", "Pièce {0}"),
    ("{}: {} parede(s) sem ligação a outras.", "{0} : {1} mur(s) sans liaison avec les autres."),
    ("{}: as paredes não fecham nenhuma divisão.", "{0} : les murs ne ferment aucune pièce."),
    ("Laje do {}", "Plancher bas — {0}"),
    ("Vazio aberto na laje onde o pé-direito livre sobre a escada seria inferior a {} m.",
     "Trémie ouverte dans le plancher là où l'échappée au-dessus de l'escalier serait inférieure à {0} m."),
    ("Terraço sobre {}", "Terrasse au-dessus de : {0}"),
    # ------------------------------------------------------------------ escaliers
    ("A escada {} está no último piso: não há piso acima para onde subir.", "L'escalier {0} est au dernier niveau : il n'y a pas de niveau au-dessus."),
    ("Escada {}: 2 × espelho + cobertor = {} m, fora do intervalo de conforto 0,60–0,65 m (regra de Blondel).",
     "Escalier {0} : 2 × hauteur de marche + giron = {1} m, hors de la plage de confort 0,60–0,65 m (loi de Blondel)."),
    ("Escada {}: parte da escada fica fora do contorno do piso.", "Escalier {0} : une partie de l'escalier sort du contour du niveau."),
    ("Escada {}: a escada atravessa uma parede.", "Escalier {0} : l'escalier traverse un mur."),
    # ------------------------------------------------------------------ pièces dessinées
    ("Planta do {} — cotada", "Plan coté — {0}"),
    ("Área bruta do piso {} m² · cotas em metros · áreas úteis entre faces de parede.",
     "Surface hors œuvre du niveau {0} m² · cotes en mètres · surfaces utiles entre nus des murs."),
    ("Corte {} — plano {} = {} m", "Coupe {0} — plan {1} = {2} m"),
    ("Topo das paredes  +{}", "Arase des murs  +{0}"),
    ("Cumeeira  +{}", "Faîtage  +{0}"),
    ("{}  +{n}", "{0}  +{1}"),
    ("{}  -{n}", "{0}  -{1}"),
    ("pé-direito {n}", "HSP {0}"),
    ("sobe · {} × {} cm", "monte · {0} × {1} cm"),
    ("1:{}  (folha A3)", "1/{0}  (format A3)"),
    # ------------------------------------------------------------------ IFC
    ("Parede {}", "Mur {0}"),
    ("Vão {}", "Baie {0}"),
    ("Porta {}", "Porte {0}"),
    ("Portão de garagem {}", "Porte de garage {0}"),
    ("Janela {}", "Fenêtre {0}"),
    ("Portada envidraçada {}", "Porte-fenêtre {0}"),
    ("Água {}", "Versant {0}"),
    ("Empena {}", "Pignon {0}"),
    ("Escada {}", "Escalier {0}"),
    # ------------------------------------------------------------------ opérations
    ("Piso «{}» não existe.", "Le niveau « {0} » n'existe pas."),
    ("Não conheço o tipo de parede «{}».", "Type de mur « {0} » inconnu."),
    ("Não há espaço livre para o vão na parede {}.", "Pas de place libre pour la baie dans le mur {0}."),
    ("Parede {} criada ({} m).", "Mur {0} créé ({1} m)."),
    ("Sala de {} × {} m (eixos) criada.", "Pièce de {0} × {1} m (aux axes) créée."),
    ("Parede {} removida (e os seus vãos).", "Mur {0} supprimé (avec ses baies)."),
    ("{} parede(s) passam a «{}».", "{0} mur(s) passent en « {1} »."),
    ("{} {} de {} × {} m colocada na parede {}.", "{0} {1} de {2} × {3} m posée dans le mur {4}."),
    ("Vão {} alterado.", "Baie {0} modifiée."),
    ("Vão {} removido.", "Baie {0} supprimée."),
    ("Cobertura: {}, {}°.", "Toiture : {0}, {1}°."),
    ("{}.º andar criado com as paredes e janelas do piso de baixo.", "Étage {0} créé avec les murs et les fenêtres du niveau inférieur."),
    ("Pé-direito do piso {}: {} m.", "Hauteur sous plafond du niveau {0} : {1} m."),
    ("Escada {} colocada.", "Escalier {0} placé."),
    ("Escada {} removida.", "Escalier {0} supprimé."),
    ("{} ({}) colocado.", "{0} ({1}) placé."),
    ("Objeto {} removido.", "Objet {0} supprimé."),
    ("Operação desconhecida «{}». Disponíveis: {}.", "Opération inconnue « {0} ». Disponibles : {1}."),
    ("Não conheço o acabamento «{}» para {}.", "Finition « {0} » inconnue ({1})."),
    ("Não encontrei uma parede exterior no lado «{}».", "Aucun mur extérieur trouvé du côté « {0} »."),
    ("Um vão de {} m não cabe na parede {} ({} m).", "Une baie de {0} m ne tient pas dans le mur {1} ({2} m)."),
    ("Não encontrei a divisão «{}».", "Pièce « {0} » introuvable."),
    ("Parede «{}» não existe.", "Le mur « {0} » n'existe pas."),
    ("Não encontrei paredes «{}».", "Aucun mur « {0} » trouvé."),
    ("Vão «{}» não existe.", "La baie « {0} » n'existe pas."),
    ("Tipo de cobertura desconhecido «{}» (plana, uma_agua, duas_aguas, quatro_aguas).",
     "Type de toiture inconnu « {0} » (plana = toiture-terrasse, uma_agua = monopente, duas_aguas = deux pentes, quatro_aguas = quatre pentes)."),
    ("Escada «{}» não existe.", "L'escalier « {0} » n'existe pas."),
    ("Não conheço o objeto «{}».", "Objet « {0} » inconnu."),
    ("Objeto «{}» não existe.", "L'objet « {0} » n'existe pas."),
    ("dados em falta ({})", "données manquantes ({0})"),
    ("Operação {} ({}): {}", "Opération {0} ({1}) : {2}"),
    ("Acabamentos da casa — {}.", "Finitions de la maison — {0}."),
    ("Divisão «{}» — {}.", "Pièce « {0} » — {1}."),
    ("nome «{}»", "nom « {0} »"),
    ("fachada: {}", "façade : {0}"),
    ("cobertura: {}", "toiture : {0}"),
    ("caixilharia: {}", "menuiseries : {0}"),
    ("pavimento: {}", "sol : {0}"),
    ("parede interior: {}", "murs intérieurs : {0}"),
    ("teto: {}", "plafond : {0}"),
    # ------------------------------------------------------------------ différences Studio / dossier
    ("Pé-direito — {}", "Hauteur sous plafond — {0}"),
    ("Acabamento — {}", "Finition — {0}"),
]

FRAGMENTOS = {
    # types de baie (clé du modèle, ou clé avec majuscule dans les messages des opérations)
    "janela": "fenêtre", "porta": "porte", "portada": "porte-fenêtre", "portao": "porte de garage",
    "Janela": "Fenêtre", "Porta": "Porte", "Portada": "Porte-fenêtre", "Portao": "Porte de garage",
    # toitures
    "plana": "toiture-terrasse", "uma agua": "monopente", "duas aguas": "deux pentes", "quatro aguas": "quatre pentes",
    "uma_agua": "monopente", "duas_aguas": "deux pentes", "quatro_aguas": "quatre pentes",
    # escaliers
    "escada reta": "droit", "escada l": "quart tournant", "escada u": "demi-tournant",
    # éléments recevant une finition
    "fachada": "façade", "cobertura": "toiture", "caixilharia": "menuiseries", "pavimento": "sol",
    "parede interior": "murs intérieurs", "teto": "plafond",
    "sim": "oui", "não": "non",
    "rés-do-chão": "rez-de-chaussée",
    # motifs d'une baie invalide
    "não cabe no comprimento da parede": "ne tient pas dans la longueur du mur",
    "é mais alto do que a parede": "est plus haute que le mur",
    "sobrepõe-se a outro vão": "chevauche une autre baie",
    # noms de champs cités dans les erreurs de validation
    "pé-direito": "hauteur sous plafond", "espessura da laje": "épaisseur du plancher", "tipo de parede": "type de mur",
    "espessura da camada": "épaisseur de la couche", "parede": "mur", "parede.a": "mur.a", "parede.b": "mur.b", "vão": "baie",
    "posição do vão": "position de la baie", "largura do vão": "largeur de la baie", "altura do vão": "hauteur de la baie",
    "peitoril": "allège", "inclinação da cobertura": "pente de la toiture", "beiral": "débord de toit",
    "laje de cobertura": "dalle haute du dernier niveau", "rótulo": "étiquette de pièce", "escada": "escalier",
    "rotação da escada": "rotation de l'escalier", "largura da escada": "largeur de l'escalier", "cobertor": "giron",
    "objeto": "objet", "rotação do objeto": "rotation de l'objet", "largura do objeto": "largeur de l'objet",
    "profundidade do objeto": "profondeur de l'objet", "cota": "cote", "cota.a": "cote.a", "cota.b": "cote.b",
    "afastamento da cota": "décalage de la cote", "nota": "note", "laje térrea": "plancher bas du rez-de-chaussée", "piso": "niveau",
}

CHAVES = {
    "CP_Estudio": "CP_Studio", "CP_Acabamentos": "CP_Finitions",
    "IdModelo": "IdModele", "TipoParede": "TypeMur", "Fachada": "Facade", "ComprimentoNoEixo": "LongueurAxe",
    "InclinacaoGraus": "PenteDegres", "AreaEmPlanta": "SurfaceEnPlan", "Acabamento": "Finition",
    "Largura": "Largeur", "AlturaVencida": "HauteurAFranchir", "Blondel": "Blondel",
    "Categoria": "Categorie", "Profundidade": "Profondeur", "Altura": "Hauteur",
    "Pavimento": "Sol", "Paredes": "Murs", "Teto": "Plafond",
}

CAMADAS_DXF = {
    "PAREDES": "MURS", "VAOS": "BAIES", "TEXTO_VAOS": "TEXTE_BAIES", "PAVIMENTOS": "SOLS", "MOBILIARIO": "MOBILIER",
    "ESCADAS": "ESCALIERS", "TEXTO": "TEXTE", "COTAS": "COTES", "DESENHO": "DESSIN",
}

# mots français acceptés dans les opérations de l'Assistant → clés du moteur (comparaison sans accents ni majuscules)
SINONIMOS = {
    "vao.tipo": {"fenetre": "janela", "fenêtre": "janela", "porte": "porta", "porte d'entree": "porta", "porte-fenetre": "portada",
                 "porte fenetre": "portada", "baie": "portada", "baie vitree": "portada", "baie coulissante": "portada",
                 "porte de garage": "portao", "portail": "portao"},
    "mudar_vao.tipo": {"fenetre": "janela", "porte": "porta", "porte-fenetre": "portada", "porte fenetre": "portada", "baie": "portada",
                       "baie vitree": "portada", "porte de garage": "portao"},
    "cobertura.tipo": {"toiture-terrasse": "plana", "toiture terrasse": "plana", "toit plat": "plana", "toit_plat": "plana", "plate": "plana",
                       "plat": "plana", "terrasse": "plana", "monopente": "uma_agua", "une pente": "uma_agua", "un pan": "uma_agua",
                       "deux pentes": "duas_aguas", "deux_pentes": "duas_aguas", "deux pans": "duas_aguas", "2 pentes": "duas_aguas",
                       "2 pans": "duas_aguas", "quatre pentes": "quatro_aguas", "quatre pans": "quatro_aguas", "4 pentes": "quatro_aguas",
                       "4 pans": "quatro_aguas", "croupes": "quatro_aguas"},
    "escada.tipo": {"droit": "reta", "droite": "reta", "quart tournant": "l", "1/4 tournant": "l", "en l": "l",
                    "demi-tournant": "u", "demi tournant": "u", "1/2 tournant": "u", "en u": "u"},
    "lado": {"avant": "frente", "rue": "frente", "facade avant": "frente", "sud": "frente", "arriere": "tardoz", "jardin": "tardoz",
             "fond": "tardoz", "facade arriere": "tardoz", "gauche": "esquerda", "droite": "direita"},
    "lado_baixo": {"avant": "frente", "rue": "frente", "arriere": "tardoz", "jardin": "tardoz", "gauche": "esquerda", "droite": "direita"},
    "sentido": {"gauche": "esq", "droite": "dir"},
    "de": {"exterieurs": "exteriores", "exterieur": "exteriores", "murs exterieurs": "exteriores", "facades": "exteriores",
           "interieurs": "interiores", "interieur": "interiores", "cloisons": "interiores", "murs interieurs": "interiores"},
}


def _fundir(*dicts: dict) -> dict:
    """Junta os catálogos; a mesma chave em dois catálogos tem de ter a mesma tradução (senão é um erro do catálogo)."""
    out: dict = {}
    for d in dicts:
        for k, v in d.items():
            if k in out and out[k] != v:
                raise ValueError(f"Tradução em conflito para «{k}»: «{out[k]}» ≠ «{v}»")
            out[k] = v
    return out


EXATOS = _fundir(_B.CATEGORIAS, _B.BIBLIOTECA, _A.GRUPOS, _A.ACABAMENTOS, _O.PAREDES_TIPO, _O.CATEGORIAS_OBJ, _O.OBJETOS,
                 _O.MODELOS_VAO, _O.PROTECOES, _MENSAGENS)

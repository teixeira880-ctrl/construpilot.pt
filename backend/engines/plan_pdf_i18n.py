"""Traduction FR → PT-PT des libellés des PDF de contrôle des cotes (Paragraph traduisant selon la langue courante).

Les générateurs PDF restent écrits en français ; quand `LANG` vaut « pt », chaque fragment connu est remplacé
(fragments les plus longs d'abord). Les données métier (valeurs, textes IA déjà rédigés en PT) ne sont pas touchées.
"""
from __future__ import annotations

import contextvars

from reportlab.platypus import Paragraph as _RLParagraph

LANG: contextvars.ContextVar[str] = contextvars.ContextVar("plan_pdf_lang", default="pt")

FR_PT: dict[str, str] = {
    "nu int. droit": "face int. direita", "nu int. gauche": "face int. esquerda",
    "nu int. haut": "face int. superior", "nu int. bas": "face int. inferior",
    # phrases longues
    "Analyse automatique de cohérence du plan — contrôle géométrique et dimensionnel": "Análise automática de coerência da planta — controlo geométrico e dimensional",
    "Chaque cote inscrite sur le plan est mesurée à l'échelle et comparée à sa valeur indiquée.": "Cada cota inscrita na planta é medida à escala e comparada com o valor indicado.",
    "Plan original + cotes mesurées (vert OK / orange à vérifier / rouge incohérence).": "Planta original + cotas medidas (verde OK / laranja a verificar / vermelho incoerência).",
    "Rapport global : synthèse par page puis, pour chaque page, détail + plan annoté.": "Relatório global: síntese por página e, para cada página, detalhe + planta anotada.",
    "Les écarts positifs signifient que la mesure est plus grande que la cote inscrite. ": "Os desvios positivos significam que a medição é maior do que a cota inscrita. ",
    "Lecture IA : positions des traits de cote approximatives (±1-2 %) — les incohérences ": "Leitura IA: posições das linhas de cota aproximadas (±1-2 %) — as incoerências ",
    "signalées doivent être confirmées sur le plan d'origine.": "assinaladas devem ser confirmadas na planta original.",
    "= écart proche de la tolérance, à vérifier · ": "= desvio próximo da tolerância, a verificar · ",
    "= incohérence entre la cote indiquée et la mesure. ": "= incoerência entre a cota indicada e a medição. ",
    "Seuils de détection ConstruPilot (0–2 mm négligeable · 2–10 mm faible · 10–30 mm à vérifier · 30–100 mm anomalie ": "Limiares de deteção ConstruPilot (0–2 mm desprezável · 2–10 mm fraco · 10–30 mm a verificar · 30–100 mm anomalia ",
    "Seuils de détection ConstruPilot : 0–2 mm négligeable · 2–10 mm faible · 10–30 mm à vérifier · 30–100 mm anomalie ": "Limiares de deteção ConstruPilot: 0–2 mm desprezável · 2–10 mm fraco · 10–30 mm a verificar · 30–100 mm anomalia ",
    "importante · > 100 mm anomalie majeure) — ce ne sont pas des tolérances réglementaires d'exécution. ": "importante · > 100 mm anomalia grave) — não são tolerâncias regulamentares de execução. ",
    "importante · > 100 mm anomalie majeure — ce ne sont pas des tolérances réglementaires d'exécution.": "importante · > 100 mm anomalia grave — não são tolerâncias regulamentares de execução.",
    "Les hypothèses de correction ne modifient jamais le plan.": "As hipóteses de correção nunca alteram a planta.",
    "Traçabilité : chaque résultat est reproductible à partir des valeurs sources, de la formule et de l'écart indiqués. ": "Rastreabilidade: cada resultado é reprodutível a partir dos valores de origem, da fórmula e do desvio indicados. ",
    "Périmètre : cette analyse est limitée au document fourni (page indiquée), à ses cotes lisibles et à l'échelle ": "Âmbito: esta análise limita-se ao documento fornecido (página indicada), às suas cotas legíveis e à escala ",
    "déclarée ou calibrée. Elle ne constitue ni une étude d'exécution ni une validation structurelle : les valeurs ": "declarada ou calibrada. Não constitui um projeto de execução nem uma validação estrutural: os valores ",
    "recalculées et les hypothèses de fermeture sont des aides à la vérification, jamais des cotes de remplacement. ": "recalculados e as hipóteses de fecho são auxiliares de verificação, nunca cotas de substituição. ",
    "Les points signalés doivent être confirmés avec l'auteur du plan.": "Os pontos assinalados devem ser confirmados com o autor da planta.",
    "Des façades opposées parallèles et cotées selon les mêmes références devraient présenter des dimensions compatibles. ": "Fachadas opostas paralelas e cotadas segundo as mesmas referências deveriam apresentar dimensões compatíveis. ",
    "Un écart peut provenir d'un décrochement volontaire, d'une géométrie non rectangulaire, de références de cotation ": "Um desvio pode resultar de um recuo intencional, de uma geometria não retangular, de referências de cotagem ",
    "différentes (axes d'un côté, faces de l'autre), d'une erreur de dessin ou de cotation. Le plan seul ne permet pas de ": "diferentes (eixos de um lado, faces do outro), de um erro de desenho ou de cotagem. A planta por si só não permite ",
    "déterminer automatiquement laquelle de ces hypothèses est correcte.": "determinar automaticamente qual destas hipóteses está correta.",
    "Façades opposées : NON INDIQUÉ — les cotes lisibles ne permettent pas la comparaison.": "Fachadas opostas: NÃO INDICADO — as cotas legíveis não permitem a comparação.",
    "Alignement apparent à vérifier — précision insuffisante pour une mesure fiable.": "Alinhamento aparente a verificar — precisão insuficiente para uma medição fiável.",
    "Aucune chaîne générale n'a pu être reconstruite à partir des cotes lisibles (NON INDIQUÉ).": "Não foi possível reconstruir nenhuma cadeia geral a partir das cotas legíveis (NÃO INDICADO).",
    "Aucune chaîne partielle contiguë détectée sur cette page.": "Nenhuma cadeia parcial contígua detetada nesta página.",
    "Toutes les cotes contrôlées (cote inscrite vs mesure à l'échelle)": "Todas as cotas controladas (cota inscrita vs medição à escala)",
    "Marqueurs CP-xx : vert conforme · jaune à vérifier · orange incohérence · rouge incohérence majeure": "Marcadores CP-xx: verde conforme · amarelo a verificar · laranja incoerência · vermelho incoerência grave",
    "Légende des sources : LUE SUR PLAN · FOURNIE PAR L'UTILISATEUR (cote corrigée) · VALEUR CALCULÉE · HYPOTHÈSE.": "Legenda das fontes: LIDA NA PLANTA · FORNECIDA PELO UTILIZADOR (cota corrigida) · VALOR CALCULADO · HIPÓTESE.",
    "Hypothèses mathématiques permettant la fermeture de la chaîne — le plan n'est pas modifié.": "Hipóteses matemáticas que permitem o fecho da cadeia — a planta não é alterada.",
    "Ce rapport est produit par le contrôle ConstruPilot : chaque cote est relue, mesurée à l'échelle et confrontée aux autres ": "Este relatório é produzido pelo controlo ConstruPilot: cada cota é relida, medida à escala e confrontada com os outros ",
    "données du plan par recalcul indépendant. Les valeurs recalculées et les hypothèses sont toujours distinguées des valeurs ": "dados da planta por recálculo independente. Os valores recalculados e as hipóteses são sempre distinguidos dos valores ",
    "inscrites. Ce document n'est pas une étude d'exécution : les points signalés sont des points nécessitant vérification.": "inscritos. Este documento não é um projeto de execução: os pontos assinalados são pontos que requerem verificação.",
    "Contrôle automatique de cohérence géométrique et dimensionnelle du plan": "Controlo automático de coerência geométrica e dimensional da planta",
    ": lecture des cotes inscrites, recalcul indépendant des chaînes et des grandes cotes, ": ": leitura das cotas inscritas, recálculo independente das cadeias e das cotas gerais, ",
    "comparaison des façades opposées, contrôle des alignements et identification des points à clarifier avant ": "comparação das fachadas opostas, controlo dos alinhamentos e identificação dos pontos a clarificar antes da ",
    "utilisation des dimensions pour l'implantation ou l'exécution.": "utilização das dimensões para a implantação ou a execução.",
    "nécessitent une clarification des références de cotation et de la géométrie définitive avant utilisation des ": "requerem uma clarificação das referências de cotagem e da geometria definitiva antes da utilização das ",
    "dimensions concernées pour l'implantation.": "dimensões em causa para a implantação.",
    "Le contrôle géométrique a porté sur": "O controlo geométrico incidiu sobre",
    "incohérence(s) détectée(s) et": "incoerência(s) detetada(s) e",
    "point(s) à clarifier": "ponto(s) a clarificar",
    "épaisseur(s) de murs prise(s) en compte : ": "espessura(s) de parede considerada(s): ",
    "non déterminable avec certitude — HYPOTHÈSE : cotes entre faces": "não determinável com certeza — HIPÓTESE: cotas entre faces",
    "référence de cotation : ": "referência de cotagem: ",
    "tolérance de détection : ": "tolerância de deteção: ",
    "seuils mm ConstruPilot pour les niveaux": "limiares mm ConstruPilot para os níveis",
    "échelle effective du PDF": "escala efetiva do PDF",
    "alors que le cartouche indique": "enquanto a legenda indica",
    "(PDF réduit à l'impression)": "(PDF reduzido na impressão)",
    "source des cotes : extraction vectorielle du PDF (": "fonte das cotas: extração vetorial do PDF (",
    "cotes mesurées au millimètre entre ": "cotas medidas ao milímetro entre ",
    "lignes d'attache) croisée avec la lecture IA (": "linhas de chamada) cruzada com a leitura IA (",
    "lues par l'IA seule et non vérifiées": "lidas apenas pela IA e não verificadas",
    "divergence(s) de lecture tranchée(s) par le texte vectoriel": "divergência(s) de leitura resolvida(s) pelo texto vetorial",
    "cote(s) classée(s) NON DÉTERMINÉ.": "cota(s) classificada(s) NÃO DETERMINADO.",
    "cotes vectorielles du PDF (mesure exacte au mm) croisées avec la lecture IA": "cotas vetoriais do PDF (medição exata ao mm) cruzadas com a leitura IA",
    "Croisement vectoriel ↔ IA :": "Cruzamento vetorial ↔ IA:",
    "cote(s) mesurée(s) dans les vecteurs du PDF, ": "cota(s) medida(s) nos vetores do PDF, ",
    "confirmée(s) par la lecture IA, ": "confirmada(s) pela leitura IA, ",
    "lue(s) par l'IA seule ": "lida(s) apenas pela IA ",
    "(non vérifiées, jamais comptées en incohérence)": "(não verificadas, nunca contadas como incoerência)",
    " · divergences de lecture (le texte vectoriel fait foi) : ": " · divergências de leitura (o texto vetorial prevalece): ",
    "lecture IA du plan (image)": "leitura IA da planta (imagem)",
    "cotes exactes du fichier DXF": "cotas exatas do ficheiro DXF",
    "Abstention ConstruPilot :": "Abstenção ConstruPilot:",
    "cote(s) non déterminée(s)": "cota(s) não determinada(s)",
    "Mesure à l'échelle non fiable sur cette page (dispersion des ratios mesure/cote) : les écarts ": "Medição à escala não fiável nesta página (dispersão dos rácios medição/cota): os desvios ",
    "mesurés ne sont pas signalés comme incohérences. Seuls les contrôles arithmétiques (chaînes, ": "medidos não são assinalados como incoerências. Apenas os controlos aritméticos (cadeias, ",
    "fermetures) font foi. Calibrez l'échelle manuellement pour réactiver la mesure.": "fechos) prevalecem. Calibre a escala manualmente para reativar a medição.",
    "calibrée automatiquement": "calibrada automaticamente",
    "Recalcul indépendant (passage 2)": "Recálculo independente (passagem 2)",
    "Contrôle adversarial (passage 3)": "Controlo adversarial (passagem 3)",
    "Contrôle adversarial": "Controlo adversarial",
    "Cotes concernées": "Cotas em causa",
    "Action recommandée": "Ação recomendada",
    "Hypothèses possibles": "Hipóteses possíveis",
    "Causes possibles": "Causas possíveis",
    "Calcul ConstruPilot": "Cálculo ConstruPilot",
    "Valeur recalculée": "Valor recalculado",
    "Cote indiquée sur le plan": "Cota indicada na planta",
    "Donnée du plan": "Dado da planta",
    "devrait être": "deveria ser",
    "au lieu de": "em vez de",
    "Section « Analyse géométrique ConstruPilot » (double lecture IA).": "Secção « Análise geométrica ConstruPilot » (dupla leitura IA).",
    "Analyse géométrique ConstruPilot — double lecture": "Análise geométrica ConstruPilot — dupla leitura",
    "Compatibilité géométrique": "Compatibilidade geométrica",
    "À vérifier avant utilisation": "A verificar antes da utilização",
    "Fermeture des chaînes sur les cotes générales": "Fecho das cadeias nas cotas gerais",
    "Cotes partielles ↔ cotes totales (mesure ConstruPilot)": "Cotas parciais ↔ cotas totais (medição ConstruPilot)",
    "Chaînes de cotes (partielles = totale ?)": "Cadeias de cotas (parciais = total?)",
    "Surfaces écrites sur le plan ↔ surfaces mesurées": "Áreas escritas na planta ↔ áreas medidas",
    "Chaîne (valeurs inscrites)": "Cadeia (valores inscritos)",
    "Fermeture des chaînes": "Fecho das cadeias",
    "Fermeture chaîne": "Fecho da cadeia",
    "Chaîne de cotes → cote": "Cadeia de cotas → cota",
    "Matrice de cohérence": "Matriz de coerência",
    "Contrôles croisés": "Controlos cruzados",
    "Façades opposées": "Fachadas opostas",
    "Alignements": "Alinhamentos",
    "Façades": "Fachadas",
    "Détail des cotes contrôlées": "Detalhe das cotas controladas",
    "Plan original — cotes mesurées": "Planta original — cotas medidas",
    "PLAN ANNOTÉ CONSTRUPILOT": "PLANTA ANOTADA CONSTRUPILOT",
    "RAPPORT DE CONTRÔLE DU PLAN": "RELATÓRIO DE CONTROLO DA PLANTA",
    "Rapport de contrôle du plan": "Relatório de controlo da planta",
    "CONTRÔLE DES GRANDES COTES": "CONTROLO DAS COTAS GERAIS",
    "CONTRÔLE DÉTAILLÉ DES CHAÎNES": "CONTROLO DETALHADO DAS CADEIAS",
    "CONTRÔLE DES FAÇADES ET ALIGNEMENTS": "CONTROLO DAS FACHADAS E ALINHAMENTOS",
    "TABLEAU GÉNÉRAL DES CONTRÔLES": "QUADRO GERAL DOS CONTROLOS",
    "POINTS À CLARIFIER AVANT EXÉCUTION": "PONTOS A CLARIFICAR ANTES DA EXECUÇÃO",
    "FICHES DÉTAILLÉES": "FICHAS DETALHADAS",
    "Points nécessitant vérification": "Pontos que requerem verificação",
    "RÉSUMÉ EXÉCUTIF": "RESUMO EXECUTIVO",
    "Résumé du contrôle": "Resumo do controlo",
    "Résultat global": "Resultado global",
    "Principale incohérence": "Principal incoerência",
    "Données extraites du plan": "Dados extraídos da planta",
    "Hypothèses retenues": "Hipóteses consideradas",
    "Objet du rapport": "Objeto do relatório",
    "CONTRÔLE DES COTES": "CONTROLO DAS COTAS",
    "Contrôle des cotes": "Controlo das cotas",
    "Contrôles réalisés": "Controlos realizados",
    "Éléments cohérents": "Elementos coerentes",
    "Points à vérifier": "Pontos a verificar",
    "Incohérences majeures": "Incoerências graves",
    "Incohérence majeure": "Incoerência grave",
    "Incohérences": "Incoerências",
    "Incohérence": "Incoerência",
    "INCOHÉRENCE": "INCOERÊNCIA",
    "Confirmer la cote": "Confirmar a cota",
    "Confirmer les références de cotation face/axe": "Confirmar as referências de cotagem face/eixo",
    "Comparer avec le plan architectural / structure": "Comparar com a planta de arquitetura / estrutura",
    "Vérifier la correspondance murs / fondations": "Verificar a correspondência paredes / fundações",
    "Document analysé": "Documento analisado",
    "Type de plan": "Tipo de planta",
    "Date du plan": "Data da planta",
    "Date de l'analyse": "Data da análise",
    "Identifiant du rapport": "Identificador do relatório",
    "Localisation": "Localização",
    "Révision": "Revisão",
    "Échelle": "Escala",
    "Projet": "Projeto",
    "cotes contrôlées": "cotas controladas",
    "chaîne(s) de cotes": "cadeia(s) de cotas",
    "incohérente(s)": "incoerente(s)",
    "incohérence(s)": "incoerência(s)",
    "ignorée(s)": "ignorada(s)",
    "à vérifier": "a verificar",
    "À vérifier": "A verificar",
    "écart max": "desvio máx.",
    "Écart max": "Desvio máx.",
    "Chaînes KO": "Cadeias KO",
    "page(s) contrôlée(s)": "página(s) controlada(s)",
    "confirmée(s)": "confirmada(s)",
    "infirmée(s)": "refutada(s)",
    "contestée(s)": "contestada(s)",
    "rejetée(s)": "rejeitada(s)",
    "maintenue(s)": "mantida(s)",
    "Cartouche : ": "Legenda: ",
    "Source des cotes": "Fonte das cotas", "Source": "Fonte",
    "Source du calcul": "Fonte do cálculo",
    "Tolérance": "Tolerância",
    "Cote inscrite": "Cota inscrita",
    "Cote indiquée": "Cota indicada",
    "Cotes partielles": "Cotas parciais",
    "Cote totale": "Cota total",
    "Cote plan": "Cota planta",
    "Valeur plan": "Valor planta",
    "Calculée": "Calculada",
    "Calculé": "Calculado",
    "Mesurée": "Medida",
    "Mesuré": "Medido",
    "Mesure": "Medição",
    "Écrite": "Escrita",
    "Écart": "Desvio",
    "Orient.": "Orient.",
    "Résultat": "Resultado",
    "Confiance": "Confiança",
    "Contrôle": "Controlo",
    "Statut": "Estado",
    "Niveau": "Nível",
    "Calcul": "Cálculo",
    "Formule": "Fórmula",
    "Explication": "Explicação",
    "Conclusion": "Conclusão",
    "Cohérent": "Coerente",
    "Information": "Informação",
    "Ignorée": "Ignorada",
    "Verdict": "Veredicto",
    "aucune incohérence": "nenhuma incoerência",
    "écarts à vérifier": "desvios a verificar",
    "NON DÉTERMINÉ": "NÃO DETERMINADO",
    "NON INDIQUÉ": "NÃO INDICADO",
    "VALEUR CALCULÉE": "VALOR CALCULADO",
    "LUE SUR PLAN": "LIDA NA PLANTA",
    "horizontale": "horizontal",
    "verticale": "vertical",
    "oblique": "oblíqua",
    "Cote #": "Cota #",
    "Plan": "Planta",
    "Page ": "Página ",
    "PAGE ": "PÁGINA ",
    " · page ": " · página ",
    "— page ": "— página ",
    "(page ": "(página ",
    "cotes et": "cotas e",
    "contrôles.": "controlos.",
    "cotes": "cotas",
    "cote": "cota",
    "orange": "laranja",
    "rouge": "vermelho",
    "vert": "verde",
    "Les dimensions générales opposées présentent des écarts de": "As dimensões gerais opostas apresentam desvios de",
    ": l'emprise n'est pas confirmée rectangulaire sans cote unique, diagonale ou plan d'axes.": ": a implantação não se confirma retangular sem cota única, diagonal ou planta de eixos.",
    "Chaîne(s) de cotes ne se refermant pas :": "Cadeia(s) de cotas que não fecham:",
    "en cotes partielles": "em cotas parciais", "contre": "contra",
    "cote(s) incohérente(s) et": "cota(s) incoerente(s) e", "à vérifier entre valeur inscrite et mesure.": "a verificar entre valor inscrito e medição.",
    "Toutes les cotes inscrites correspondent à la mesure, les chaînes se referment et les dimensions ": "Todas as cotas inscritas correspondem à medição, as cadeias fecham e as dimensões ",
    "générales opposées sont égales : aucune incohérence relevée sur cette page.": "gerais opostas são iguais: nenhuma incoerência detetada nesta página.",
    "Ces points doivent être clarifiés sur un plan corrigé avant l'implantation.": "Estes pontos devem ser clarificados numa planta corrigida antes da implantação.",
    "Conclusion rapide": "Conclusão rápida",
    "Cotes probablement erronées (non alignées sur le dessin)": "Cotas provavelmente erradas (não alinhadas com o desenho)",
    "Mesures automatiques — distances dessinées sans cote": "Medições automáticas — distâncias desenhadas sem cota",
    "cote(s) probablement erronée(s) : leurs extrémités ne sont alignées sur aucune face ni axe de mur dessiné (écart > 10 mm en projection perpendiculaire) — ": "cota(s) provavelmente errada(s): as suas extremidades não estão alinhadas com nenhuma face nem eixo de parede desenhado (desvio > 10 mm em projeção perpendicular) — ",

    "Éléments dessinés — largeur dessinée vs étiquette (semelles, poutres, murs)": "Elementos desenhados — largura desenhada vs etiqueta (sapatas, vigas, paredes)",
    "élément(s) étiqueté(s) « largeur x hauteur » mesuré(s) entre les deux traits parallèles qui les dessinent : ": "elemento(s) etiquetado(s) « largura x altura » medido(s) entre os dois traços paralelos que os desenham: ",
    "conforme(s),": "conforme(s),", "Cotes non rattachées au dessin": "Cotas não ligadas ao desenho",
    "Chaque extrémité de cote doit tomber sur un trait du dessin (face ou axe de mur). Les cotes suivantes ont une ": "Cada extremidade de cota deve coincidir com um traço do desenho (face ou eixo de parede). As cotas seguintes têm uma ",
    "extrémité à plus de 10 mm (échelle du plan) de tout trait long : la cote ne mesure pas ce qui est dessiné.": "extremidade a mais de 10 mm (escala da planta) de qualquer traço longo: a cota não mede o que está desenhado.",
    "Étiquette": "Etiqueta", "Annoncé": "Anunciado", "Dessiné": "Desenhado", "Extrémité": "Extremidade",
    "Équerrage": "Esquadria", "si l'écart de": "se o desvio de", "cm est un défaut d'équerrage sur une ": "cm for um defeito de esquadria numa ",
    "emprise L": "implantação L", "les diagonales valent ≈": "as diagonais valem ≈", "soit une différence de diagonales ≈": "ou seja, uma diferença de diagonais ≈",
    "et un angle dévié ≈": "e um ângulo desviado ≈", "à contrôler au décamètre sur les deux diagonales lors de l'implantation.": "a controlar com fita métrica nas duas diagonais na implantação.",
    "Si l'écart de": "Se o desvio de", "cm est un défaut d'équerrage, les diagonales diffèrent d'environ ": "cm for um defeito de esquadria, as diagonais diferem cerca de ",
    "soit un angle dévié de": "ou seja, um ângulo desviado de",
    "Éléments dessinés dont la largeur ne correspond pas à l'étiquette :": "Elementos desenhados cuja largura não corresponde à etiqueta:",
    "dessiné": "desenhado", "et": "e", "autre(s)": "outro(s)",
    "cote(s) non rattachée(s) à un trait du dessin (extrémité à plus de 10 mm de toute face ou axe) : ": "cota(s) não ligada(s) a um traço do desenho (extremidade a mais de 10 mm de qualquer face ou eixo): ",
    "les cotes sont rattachées au dessin et les éléments étiquetés ont la largeur ": "as cotas estão ligadas ao desenho e os elementos etiquetados têm a largura ",
    "annoncée : aucune incohérence relevée sur cette page.": "anunciada: nenhuma incoerência detetada nesta página.",
    "élément(s) dessiné(s)": "elemento(s) desenhado(s)", "incohérent(s)": "incoerente(s)", "cote(s) non rattachée(s)": "cota(s) não ligada(s)", "Façades opposées (dimensions générales)": "Fachadas opostas (dimensões gerais)",
    "façade(s) opposée(s)": "fachada(s) oposta(s)",
    "Deux cotes générales opposées d'une emprise rectangulaire doivent être égales. Un écart de quelques cm impose ": "Duas cotas gerais opostas de uma implantação retangular devem ser iguais. Um desvio de alguns cm exige ",
    "une cote unique, une diagonale ou un plan d'axes avant implantation.": "uma cota única, uma diagonal ou uma planta de eixos antes da implantação.",
    "haut": "topo", "bas": "base", "gauche": "esquerda", "droite": "direita", "Cote A": "Cota A", "Cote B": "Cota B",
    # libellés courts / clés de cartouche / verdicts (format JSON imposé à l'IA)
    "cohérent(s)": "coerente(s)", "Valeur indiquée": "Valor indicado", "Élément": "Elemento", "Valeur": "Valor",
    "Type": "Tipo", "type plan": "tipo de planta", "projet": "projeto", "niveau": "nível", "date": "data",
    "revision": "revisão", "numero": "número", "discipline": "disciplina", "unite": "unidade", "echelle": "escala",
    "REJETÉE": "REJEITADA", "CONTESTÉE": "CONTESTADA", "MAINTENUE": "MANTIDA", "CONFIRMÉE": "CONFIRMADA",
    "INFIRMÉE": "REFUTADA", "INCERTAINE": "INCERTA", "NON REVUE": "NÃO REVISTA", "PASSAGE 2 UNIQUEMENT": "APENAS PASSAGEM 2",
    "attaque": "ataque", "valeurs": "valores", "écart": "desvio", "À VÉRIFIER": "A VERIFICAR", "COHÉRENT": "COERENTE",
    "INCOHÉRENCE MAJEURE": "INCOERÊNCIA GRAVE", "Légende du plan annoté": "Legenda da planta anotada",
    "Rapport généré le": "Relatório gerado em", "Agent de contrôle adversarial": "Agente de controlo adversarial",
    "Fermeture mathématique": "Fecho matemático", "passage 2": "passagem 2", "passage 3": "passagem 3", "Passage": "Passagem",
    "TRÈS ÉLEVÉ": "MUITO ELEVADO", "ÉLEVÉ": "ELEVADO", "MOYEN": "MÉDIO", "FAIBLE": "FRACO", "HYPOTHÈSE": "HIPÓTESE",
    "CALCULÉE": "CALCULADA", "LUE": "LIDA", "Anomalies": "Anomalias", "Anomalie": "Anomalia", "anomalie(s)": "anomalia(s)",
    "Plan annoté": "Planta anotada", "annoté": "anotada", "VERT": "VERDE", "BLEU": "AZUL", "JAUNE": "AMARELO",
    "ORANGE": "LARANJA", "ROUGE": "VERMELHO", "Synthèse": "Síntese", "Réponses": "Respostas", "Conclusion de l'agent": "Conclusão do agente",
}
import re as _re

_WORD = r"[\wÀ-ÿ]"


def _pattern(fr: str) -> _re.Pattern:
    pat = _re.escape(fr)
    if _re.match(_WORD, fr[0]):
        pat = f"(?<!{_WORD})" + pat
    if _re.match(_WORD, fr[-1]):
        pat = pat + f"(?!{_WORD})"
    return _re.compile(pat)


_RULES = [(_pattern(fr), FR_PT[fr]) for fr in sorted(FR_PT, key=len, reverse=True)]


def tr(text, lang: str | None = None) -> str:
    """Traduit un libellé FR (fragments connus, mots entiers) vers la langue courante ; identité en FR."""
    lang = lang or LANG.get()
    if lang != "pt" or not isinstance(text, str):
        return text
    for pat, pt in _RULES:
        text = pat.sub(pt, text)
    return text


class Paragraph(_RLParagraph):
    def __init__(self, text, style, *args, **kwargs):
        super().__init__(tr(text), style, *args, **kwargs)


def plan_scope_label(plan: dict, page_index: int, report: dict, lang: str = "pt") -> str:
    """« fondations », « RDC », « R+1 »… : cartouche IA (type_plan / niveau) sinon niveau détecté à l'import."""
    doc = ((report.get("geometry") or {}).get("document") or {})
    parts = [str(doc.get(k)).strip() for k in ("type_plan", "niveau") if doc.get(k) and str(doc.get(k)).upper() not in ("NON INDIQUÉ", "NON LISIBLE", "NÃO INDICADO")]
    if not parts:
        pages = plan.get("pages") or []
        lbl = pages[page_index].get("level_label") if page_index < len(pages) and isinstance(pages[page_index], dict) else None
        if lbl:
            parts = [str(lbl)]
    parts = list(dict.fromkeys(parts))
    if len(parts) == 2 and parts[1].lower() in parts[0].lower():
        parts = parts[:1]
    return " — ".join(parts) or ("planta" if lang == "pt" else "plan")


def disclaimer(plan: dict, page_index: int, report: dict, branding: dict | None, lang: str = "pt") -> str:
    company = (branding or {}).get("company_name")
    fname = plan.get("filename") or ("planta" if lang == "pt" else "plan")
    scope = plan_scope_label(plan, page_index, report, lang)
    if lang == "pt":
        who = f" realizado por <b>{company}</b>" if company else ""
        return (f"<b>Âmbito deste documento.</b> Este documento constitui um controlo de coerência da planta « {fname} » "
                f"({scope}, página {page_index + 1}){who} com <b>ConstruPilot.fr</b>. Não põe em causa, em nenhum caso, o "
                "dimensionamento nem os cálculos de estrutura elaborados pelo gabinete de projeto de estruturas (BET): assinala "
                "unicamente as incoerências de esquadria e de cotagem verificadas na planta fornecida, para que sejam confirmadas "
                "com o autor da planta antes da execução.")
    who = f' realizado por <b>{company}</b>' if company else ""
    return (f'<b>Alcance deste documento.</b> Este documento constitui um controlo de coerência da planta «{fname} » ({scope}, page {page_index + 1}){who} com o <b>ConstruPilot.pt</b>. Não põe de forma alguma em causa o dimensionamento nem os cálculos de estrutura estabelecidos pelo gabinete de projeto: regista apenas as incoerências de esquadria e de cotagem constatadas na planta fornecida, para que sejam confirmadas com o autor da planta antes da execução.')


COVER = {
    "fr": {"kicker": "CONTROLO DE COERÊNCIA DAS COTAS", "title1": "RELATÓRIO DE CONTROLO", "title2": "DAS COTAS E DA ESQUADRIA",
           "asker": "Empresa requerente", "with": "Análise realizada com o apoio de ConstruPilot.fr", "project": "Projeto",
           "doc": "Documento examinado", "scale": "échelle", "page": "page", "date": "Data da análise"},
    "pt": {"kicker": "CONTROLO DE COERÊNCIA DAS COTAS", "title1": "RELATÓRIO DE CONTROLO", "title2": "DAS COTAS E DA ESQUADRIA",
           "asker": "Empresa requerente", "with": "Análise realizada com o apoio de ConstruPilot.fr", "project": "Projeto",
           "doc": "Documento examinado", "scale": "escala", "page": "página", "date": "Data da análise"},
}


def _clean(v) -> str | None:
    s = str(v or "").strip()
    return None if not s or s.upper() in ("NON INDIQUÉ", "NON LISIBLE", "NÃO INDICADO", "NÃO LEGÍVEL", "NONE") else s


def cover_story(plan: dict, page_index: int, report: dict, branding: dict | None, lang: str, S: dict,
                width: float, subtitle: str | None = None) -> list:
    """Page de garde : nom entreprise + kicker, grand logo centré, titre, entreprise demandeuse, projet, document examiné."""
    import base64
    import io
    from datetime import datetime, timezone

    from PIL import Image
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm as _mm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Spacer, Table, TableStyle

    t = COVER.get(lang, COVER["fr"])
    b = branding or {}
    company = b.get("company_name") or "—"
    doc = ((report.get("geometry") or {}).get("document") or {})
    c = lambda name, **kw: ParagraphStyle(name, parent=S["body"], **kw)
    compact = width > 220 * _mm  # paysage : hauteur réduite → couverture + portée sur la même page
    gap = (4 if compact else 10) * _mm
    story: list = []
    head = Table([[_RLParagraph(f"<b>{company}</b>", c("cv_co", textColor="#0F5132", fontSize=10)),
                   _RLParagraph(t["kicker"], c("cv_k", textColor="#475569", fontSize=9.5))]],
                 colWidths=[width * 0.35, width * 0.65])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, "#FF5A00"),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (0, 0), 0)]))
    story += [head, Spacer(1, gap)]
    logo = b.get("logo_b64")
    if logo:
        try:
            raw = base64.b64decode(logo.split(",")[-1])
            im = Image.open(io.BytesIO(raw))
            max_w, max_h = width * 0.7, (34 if compact else 70) * _mm
            r = min(max_w / im.width, max_h / im.height)
            story += [RLImage(io.BytesIO(raw), width=im.width * r, height=im.height * r, hAlign="CENTER"), Spacer(1, gap)]
        except Exception:  # noqa: BLE001
            pass
    else:
        story += [_RLParagraph("<font color='#FF5A00'><b>Constru</b></font><b>Pilot</b>",
                               c("cv_cp", fontSize=26, leading=30, alignment=1)), Spacer(1, gap)]
    title_style = c("cv_t", fontName="Helvetica-Bold", fontSize=16 if compact else 20, leading=20 if compact else 25,
                    alignment=1, textColor="#0A0D14")
    scope = plan_scope_label(plan, page_index, report, lang)
    story += [_RLParagraph(t["title1"], title_style),
              _RLParagraph(subtitle or (t["title2"] + (f" — {scope.upper()}" if scope and scope not in ("plan", "planta") else "")), title_style),
              Spacer(1, 3 * _mm if compact else 6 * _mm),
              _RLParagraph(f"<b>{t['asker']} : {company}</b>", c("cv_a", fontSize=12, leading=15, alignment=1, textColor="#0F5132")),
              _RLParagraph(t["with"], c("cv_w", fontSize=10.5, leading=14, alignment=1, textColor="#475569")),
              Spacer(1, 3 * _mm if compact else 8 * _mm)]
    projet = _clean(doc.get("projet"))
    if projet:
        story.append(_RLParagraph(f"<b>{t['project']} : {projet}</b>", c("cv_p", fontName="Helvetica-Bold", fontSize=13, leading=17, alignment=1)))
    cal = report.get("calibration") or {}
    ech = _clean(doc.get("echelle")) or (f"1/{cal['scale_denominator']}" if cal.get("scale_denominator") else None)
    parts = [_clean(doc.get("discipline")), _clean(doc.get("type_plan")), _clean(doc.get("numero")), _clean(doc.get("date")),
             f"{t['scale']} {ech}" if ech else None]
    parts = [x for x in dict.fromkeys(parts) if x]
    fname = plan.get("filename") or "plan"
    story.append(_RLParagraph(
        f"<b>{t['doc']} :</b> {fname} ({t['page']} {page_index + 1})" + (" — " + " - ".join(parts) if parts else ""),
        c("cv_d", fontSize=10.5, leading=14, alignment=1)))
    story.append(_RLParagraph(f"{t['date']} : {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC",
                              c("cv_dt", fontSize=9, leading=12, alignment=1, textColor="#64748B")))
    story.append(Spacer(1, 4 * _mm if compact else 8 * _mm))
    return story

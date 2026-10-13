"""Moteur « études » OpenAI (Responses API) — prompt système fourni par l'utilisateur, schémas stricts."""

SYSTEM_PROMPT = "Tu es le moteur d'assistance technique de ConstruPilot pour l'analyse de\ndocuments du bâtiment.\n\nTu appliques simultanément la logique professionnelle d'un conducteur de\ntravaux, d'un métreur, d'un dessinateur-projeteur et d'un architecte, sans\nprétendre remplacer ces professionnels ni valider une étude structurelle.\n\nTon objectif est d'examiner méthodiquement le document fourni, de reconstruire\nles chaînes de cotes, d'effectuer des contrôles croisés et de signaler seulement\nles incohérences réellement démontrables.\n\nRÈGLE ABSOLUE DE PÉRIMÈTRE\n\nAnalyse exclusivement les documents et les pages réellement fournis dans la\ndemande en cours.\n\nNe suppose jamais l'existence ou le contenu :\n- d'un plan du RDC ;\n- d'un étage ;\n- d'une toiture ;\n- d'une coupe ;\n- d'une façade ;\n- d'un plan de fondations ;\n- d'une note de calcul ;\n- d'une version antérieure ;\n- ou de tout autre document absent.\n\nSi un seul plan du vide sanitaire est fourni, limite l'analyse à ce plan.\n\nN'analyse jamais les semelles, longrines, poteaux, poutres, murs, ouvertures ou\nautres éléments situés hors du périmètre expressément demandé.\n\nUne information non visible doit être classée comme « information non fournie »\nou « illisible ». Elle ne doit jamais être inventée.\n\nLECTURE INITIALE\n\nAvant toute conclusion :\n\n1. Identifier le cartouche, le titre, le niveau, l'échelle, la date, l'indice,\n   l'orientation et les unités, lorsqu'ils sont lisibles.\n2. Identifier la nature réelle du document.\n3. Définir le périmètre demandé par l'utilisateur.\n4. Inventorier uniquement les éléments effectivement visibles.\n5. Distinguer les traits du bâtiment des lignes de cote, axes, hachures,\n   annotations, repères, symboles et traits de coupe.\n6. Signaler toute information illisible avant de tenter un calcul.\n\nANALYSE DES MURS ET DE LA GÉOMÉTRIE\n\nPour les murs compris dans le périmètre :\n\n- identifier les murs extérieurs et intérieurs ;\n- déterminer leur épaisseur uniquement si elle est cotée ou géométriquement\n  mesurable avec une échelle fiable ;\n- contrôler les jonctions, angles, décrochements et continuités ;\n- contrôler les alignements de façades et de refends ;\n- rechercher les décalages non cotés ;\n- vérifier la cohérence entre largeur intérieure, épaisseurs de murs et largeur\n  extérieure ;\n- vérifier la cohérence entre longueur intérieure, épaisseurs de murs et\n  longueur extérieure ;\n- prendre en compte chaque mur traversé dans les chaînes de cotes ;\n- ne jamais appliquer automatiquement une épaisseur de 20 cm si le plan indique\n  une autre épaisseur ou si elle ne peut pas être confirmée.\n\nCONTRÔLE DES COTES\n\nPour chaque chaîne de cotes :\n\n1. Relever les cotes partielles dans leur ordre géométrique.\n2. Identifier leurs points de départ et d'arrivée.\n3. Ne pas additionner des cotes appartenant à des axes ou chaînes différents.\n4. Ajouter les épaisseurs de murs réellement traversées lorsque la cote les\n   exclut.\n5. Comparer la somme calculée à la cote totale correspondante.\n6. Indiquer explicitement :\n   - la formule ;\n   - les valeurs utilisées ;\n   - le résultat ;\n   - la cote indiquée ;\n   - l'écart constaté ;\n   - l'unité.\n7. Contrôler la répétition d'une même dimension sur plusieurs zones.\n8. Contrôler les cotes intérieures par rapport aux dimensions extérieures.\n9. Vérifier si un écart peut être expliqué par une épaisseur de mur, un doublage,\n   un joint, un décalage d'axe ou une limite de cotation.\n10. Ne déclarer une incohérence confirmée qu'après élimination des explications\n    visibles plausibles.\n\nOUVERTURES ET ÉLÉMENTS CONSTRUCTIFS\n\nSeulement lorsqu'ils font partie du périmètre demandé :\n\n- identifier portes, fenêtres, baies et réservations ;\n- relever largeur, hauteur, sens d'ouverture, allège et linteau lorsqu'ils sont\n  indiqués ;\n- vérifier leur position par rapport aux murs, axes et chaînes de cotes ;\n- identifier poutres, poteaux, semelles, longrines, dalles, trémies, escaliers,\n  réseaux, toiture, étanchéité et VRD uniquement s'ils sont visibles et demandés ;\n- ne jamais déduire un dimensionnement structurel absent.\n\nMÉTHODE DE VÉRIFICATION\n\nPour chaque anomalie potentielle :\n\n1. Formuler l'hypothèse.\n2. Rechercher une cote ou annotation pouvant l'expliquer.\n3. Refaire le calcul par une seconde méthode.\n4. Vérifier l'unité et l'échelle.\n5. Contrôler si la cote concerne le nu intérieur, le nu extérieur ou un axe.\n6. Vérifier si une cote est cumulée ou partielle.\n7. Comparer avec une autre occurrence sur la même page.\n8. Attribuer un niveau de confiance.\n9. Conserver les preuves nécessaires pour que l'utilisateur puisse contrôler\n   le résultat.\n\nINTERDICTIONS\n\n- Ne jamais inventer une cote.\n- Ne jamais compléter mentalement une partie masquée ou illisible.\n- Ne jamais affirmer qu'un élément existe sur une autre page non fournie.\n- Ne jamais mettre en doute, critiquer ou invalider le BET.\n- Ne jamais conclure à une erreur structurelle.\n- Ne jamais présenter une hypothèse comme un fait.\n- Ne jamais affirmer qu'un ouvrage est conforme à une norme sans vérification\n  réglementaire explicite.\n- Ne jamais générer une conclusion globale à partir d'une zone partiellement\n  lisible.\n- Ne jamais modifier les valeurs sources pour faire correspondre les calculs.\n\nCLASSIFICATION DES RÉSULTATS\n\nChaque point doit être classé dans une seule catégorie :\n\n- Conforme : le contrôle est démontré et cohérent.\n- Incohérence confirmée : l'écart est chiffré et vérifié deux fois.\n- Incohérence probable : les indices sont sérieux, mais une information manque.\n- À confirmer : plusieurs interprétations restent possibles.\n- Information insuffisante : la lecture ou le document ne permet pas de conclure.\n\nRÉDACTION DU RAPPORT\n\nEmployer un français professionnel, neutre, précis et compréhensible.\n\nChaque observation doit indiquer :\n- la page ;\n- la zone concernée ;\n- l'élément contrôlé ;\n- les cotes relevées ;\n- le calcul effectué ;\n- l'écart éventuel ;\n- le niveau de confiance ;\n- l'action de vérification recommandée.\n\nLe rapport ne doit jamais mentionner « limites de l'analyse du plan ».\n\nNe pas utiliser une formulation laissant croire que ConstruPilot a analysé des\nplans qui n'ont pas été transmis.\n\nDEVIS ET COMPTES RENDUS\n\nPour les devis :\n- préserver toutes les lignes, quantités, unités, prix unitaires, taux de TVA et\n  totaux ;\n- ne jamais supprimer une prestation sans instruction ;\n- recalculer mathématiquement les sous-totaux, TVA, remises, acomptes et total TTC ;\n- signaler toute différence entre les valeurs sources et les valeurs recalculées ;\n- produire un JSON structuré avant de générer le nouveau PDF.\n\nPour les comptes rendus :\n- séparer faits observés, décisions, réserves, responsabilités, échéances et\n  actions ;\n- ne pas attribuer une décision à une personne si elle n'est pas explicitement\n  mentionnée ;\n- conserver les dates, lieux, intervenants et références du chantier ;\n- employer une rédaction factuelle et juridiquement prudente.\n\nDONNÉES DU MOTEUR CONSTRUPILOT\n\nLes additions, soustractions, conversions d'échelle et contrôles géométriques sont effectués par le code\nConstruPilot (cotes vectorielles exactes, chaînes, façades opposées, éléments dessinés, cotes non alignées, mesures\nautomatiques) et te sont fournis en JSON : tu les interprètes, tu les croises avec ta lecture du document, tu ne les\nrecalcules pas à ta guise et tu n'inventes aucune mesure absente. Chaque nombre de ta réponse provient soit du document,\nsoit de ces données."

VERIFY_PROMPT = "Tu es le CONTRÔLEUR INDÉPENDANT de ConstruPilot. Tu reçois le document original, le JSON de la première analyse et\nles calculs du moteur ConstruPilot. Tu ne refais pas l'analyse : tu la contrôles. Recherche systématiquement :\nles cotes oubliées ; les mauvaises associations de chaînes ; les erreurs d'unité ; les murs mal comptabilisés ;\nles conclusions non démontrées ; les éléments inventés (absents du document et des données moteur) ; les\ncontradictions internes ; toute affirmation portant sur un document ou une page non fournis ; toute mise en cause du BET.\nChaque constat est classé « bloquant » (invalide une conclusion) ou « mineur ». Le rapport ne peut être marqué\n« vérifié » que sans anomalie bloquante. Réponds strictement selon le schéma JSON demandé, en français professionnel."

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
 "fr": "Ce document constitue un contrôle de cohérence du plan {plan}, réalisé par ConstruPilot.fr pour le compte de {company}. "
       "Il relève uniquement les éventuelles incohérences de géométrie, d'alignement et de cotation visibles sur le document fourni. "
       "Il ne modifie, ne valide et ne remet en aucun cas en cause les calculs de structure ou les études réalisées par le bureau d'études compétent.",
 "pt": "Este documento constitui um controlo de coerência da planta {plan}, realizado pela ConstruPilot.fr por conta de {company}. "
       "Assinala unicamente as eventuais incoerências de geometria, alinhamento e cotagem visíveis no documento fornecido. "
       "Não altera, não valida nem põe em causa, em nenhum caso, os cálculos de estrutura ou os estudos realizados pelo gabinete de projeto competente.",
}

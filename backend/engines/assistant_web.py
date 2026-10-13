"""Search receives only server-defined BTP concepts, never company or document text."""
import os

TOPICS = {
    "jonction_batiments": "joint de dilatation jonction bâtiment existant extension mouvements différentiels étanchéité raccord façade recommandations AQC CSTB fabricant",
    "urbanisme": "permis construire déclaration préalable travaux service public",
    "beton": "béton dosage résistance enrobage recommandations construction",
    "fondations": "fondations semelles profondeur étude géotechnique construction",
    "maconnerie": "maçonnerie murs porteurs chaînages ouvertures règles professionnelles",
    "structure": "structures bâtiments poutres poteaux dimensionnement Eurocodes",
    "charpente": "charpente bois assemblages règles professionnelles bâtiment",
    "couverture": "couverture toiture pente étanchéité DTU règles professionnelles",
    "etancheite": "étanchéité toiture terrasse parois enterrées règles professionnelles",
    "isolation": "isolation thermique acoustique bâtiments recommandations ADEME",
    "renovation_energetique": "rénovation énergétique bâtiments aides France Rénov ADEME",
    "ventilation": "ventilation VMC logement qualité air recommandations ADEME",
    "chauffage": "chauffage pompe à chaleur dimensionnement logement recommandations",
    "plomberie": "plomberie bâtiment alimentation évacuations règles professionnelles",
    "electricite": "installation électrique logement sécurité NF C 15 100 recommandations",
    "menuiserie": "menuiserie fenêtres pose étanchéité règles professionnelles",
    "carrelage": "carrelage pose joints supports DTU règles professionnelles",
    "accessibilite": "accessibilité bâtiments réglementation service public",
    "securite_chantier": "prévention sécurité chantier bâtiment INRS OPPBTP",
    "amiante": "amiante diagnostic avant travaux obligations service public INRS",
    "dechets": "déchets chantier bâtiment tri réemploi réglementation ADEME",
    "devis_facturation": "devis facture bâtiment mentions obligatoires service public professionnel",
    "assurances": "assurance décennale dommages ouvrage construction service public",
    "reception_travaux": "réception travaux réserves garanties construction service public",
    "contrats": "contrat travaux bâtiment obligations consommateur professionnel service public",
    "plans_cao": "lecture plans bâtiment cotations échelle unités DXF DWG documentation",
    "gestion_chantier": "organisation suivi chantier bâtiment planning compte rendu bonnes pratiques",
}


async def technical_search(topic):
    from engines.openai_studies import _client
    if topic not in TOPICS:
        raise ValueError("Sujet technique non autorisé")
    query = TOPICS[topic]
    client = _client()
    try:
        response = await client.responses.create(model=os.environ["ASSISTANT_MODEL_FAST"],
            reasoning={"effort": "medium"}, store=False, max_output_tokens=2400,
            instructions="Recherche technique générique. Consulte des sources officielles. Réponds en français avec citations. Ne présente pas une synthèse comme le texte complet d'une norme.",
            input=query, tools=[{"type": "web_search"}], tool_choice="required", include=["web_search_call.action.sources"])
        if response.status != "completed":
            raise RuntimeError("Recherche interrompue")
        sources = {}
        for item in response.output:
            if item.type == "web_search_call":
                for source in getattr(getattr(item, "action", None), "sources", None) or []:
                    url = getattr(source, "url", "")
                    if url.startswith(("https://", "http://")):
                        sources[url] = {"url": url, "title": getattr(source, "title", None) or url}
            if item.type == "message":
                for part in item.content:
                    for citation in getattr(part, "annotations", None) or []:
                        if getattr(citation, "type", None) == "url_citation" and citation.url.startswith(("https://", "http://")):
                            sources[citation.url] = {"url": citation.url, "title": citation.title}
        return {"ok": bool(sources), "query": query, "text": response.output_text,
            "sources": list(sources.values()), "scope": "Recherche générique sans données du compte ni documents"}
    finally:
        await client.close()
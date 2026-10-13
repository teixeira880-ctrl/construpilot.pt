"""Search receives only server-defined BTP concepts, never company or document text."""
import os

TOPICS = {
    "jonction_batiments": "junta de dilatação ligação edifício existente ampliação movimentos diferenciais estanquidade remate fachada recomendações LNEC fabricante",
    "urbanisme": "licenciamento obras comunicação prévia RJUE câmara municipal",
    "beton": "betão dosagem resistência recobrimento NP EN 206 especificações LNEC",
    "fondations": "fundações sapatas profundidade estudo geotécnico Eurocódigo 7",
    "maconnerie": "alvenaria paredes resistentes lintéis aberturas regras de boa prática LNEC",
    "structure": "estruturas edifícios vigas pilares dimensionamento Eurocódigos Anexos Nacionais",
    "charpente": "estrutura de madeira ligações Eurocódigo 5 boas práticas",
    "couverture": "cobertura inclinada telhado estanquidade regras de boa prática LNEC",
    "etancheite": "impermeabilização cobertura em terraço paredes enterradas boas práticas LNEC",
    "isolation": "isolamento térmico acústico edifícios REH RRAE recomendações ADENE",
    "renovation_energetique": "reabilitação energética edifícios apoios Fundo Ambiental ADENE",
    "ventilation": "ventilação habitação qualidade do ar REH recomendações",
    "chauffage": "aquecimento bomba de calor dimensionamento habitação recomendações",
    "plomberie": "canalização edifícios abastecimento drenagem regulamento geral",
    "electricite": "instalação elétrica habitação segurança RTIEBT recomendações",
    "menuiserie": "caixilharia janelas aplicação estanquidade boas práticas",
    "carrelage": "revestimento cerâmico assentamento juntas suportes boas práticas",
    "accessibilite": "acessibilidade edifícios DL 163/2006 regulamentação",
    "securite_chantier": "prevenção segurança obra construção ACT plano de segurança e saúde",
    "amiante": "amianto diagnóstico antes de obras obrigações APA ACT",
    "dechets": "resíduos de construção e demolição triagem reutilização regulamentação APA",
    "devis_facturation": "orçamento fatura construção menções obrigatórias Autoridade Tributária",
    "assurances": "seguro responsabilidade civil construção garantia obra Código Civil",
    "reception_travaux": "receção de obra defeitos garantias construção Portugal",
    "contrats": "contrato de empreitada obrigações consumidor profissional Portugal",
    "plans_cao": "leitura plantas construção cotagem escala unidades DXF DWG documentação",
    "gestion_chantier": "organização acompanhamento obra construção planeamento ata boas práticas",
}


async def technical_search(topic):
    from engines.openai_studies import _client
    if topic not in TOPICS:
        raise ValueError("Tema técnico não autorizado")
    query = TOPICS[topic]
    client = _client()
    try:
        response = await client.responses.create(model=os.environ["ASSISTANT_MODEL_FAST"],
            reasoning={"effort": "medium"}, store=False, max_output_tokens=2400,
            instructions="Pesquisa técnica genérica. Consulta fontes oficiais portuguesas (Diário da República, LNEC, IPQ, ADENE, câmaras municipais). Responde em português europeu com citações. Não apresentes uma síntese como o texto completo de uma norma.",
            input=query, tools=[{"type": "web_search"}], tool_choice="required", include=["web_search_call.action.sources"])
        if response.status != "completed":
            raise RuntimeError("Pesquisa interrompida")
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
            "sources": list(sources.values()), "scope": "Pesquisa genérica sem dados da conta nem documentos"}
    finally:
        await client.close()
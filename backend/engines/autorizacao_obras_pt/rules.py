"""Motor de regras do RJUE (Regime Jurídico da Urbanização e Edificação, DL 555/99 consolidado).

Cada regra traz código único, referência legal exata, URL para a fonte oficial, estado
(confirmado / a_confirmar) e condições. A função `diagnosticar` percorre o catálogo pela
ordem de prioridade (mais específico → mais geral) e devolve o procedimento aplicável
com fundamento legal, técnicos obrigatórios indicativos, peças e avisos — tudo em PT-PT.

Fonte principal consultada: Procuradoria-Geral Distrital de Lisboa (PGDL) — texto
consolidado do DL 555/99, 26.ª versão (Retificação n.º 29-A/2026, de 27/07).
"""

from __future__ import annotations

from typing import Any, Dict, List

LEI_RJUE: Dict[str, Any] = {
    "codigo": "DL 555/99",
    "data": "1999-12-16",
    "titulo": "Regime Jurídico da Urbanização e da Edificação",
    "versao_consolidada_url": (
        "https://www.pgdlisboa.pt/leis/lei_mostra_articulado.php?nid=625&tabela=leis&so_miolo="
    ),
    "status": "confirmado",
    "alteracoes_relevantes": [
        {"codigo": "DL 10/2024", "data": "2024-01-08",
         "titulo": "Simplex urbanístico",
         "fonte_url": "https://www.pgdlisboa.pt/leis/lei_mostra_articulado.php?nid=3737&tabela=leis",
         "status": "confirmado"},
        {"codigo": "DL 43/2024", "data": "2024-07-02",
         "fonte_url": "https://www.pgdlisboa.pt/leis/lei_mostra_articulado.php?nid=3809&tabela=leis",
         "status": "confirmado"},
        {"codigo": "DL 108/2026", "data": "2026-05-29",
         "fonte_url": "https://www.pgdlisboa.pt/leis/lei_mostra_articulado.php?nid=4024&tabela=leis",
         "status": "confirmado"},
        {"codigo": "Retificação 29-A/2026", "data": "2026-07-27",
         "fonte_url": "https://www.pgdlisboa.pt/leis/lei_mostra_articulado.php?nid=4049&tabela=leis",
         "status": "confirmado"},
    ],
}

# Cenários cobertos nesta fase F1
SCENARIOS = [
    "anexo_escassa_relevancia",
    "obras_interiores",
    "piscina",
    "ampliacao_comunicacao_previa",
    "moradia_nova_licenciamento",
    "zona_protegida",
]

AVISO_PDM = (
    "Mesmo quando a obra é isenta de controlo prévio, tem de respeitar o PDM, o regulamento "
    "municipal e demais normas legais aplicáveis (art.º 6.º-A n.º 3 e art.º 6.º n.º 8 do RJUE)."
)
AVISO_INICIO_TRABALHOS = (
    "A informação sobre o início dos trabalhos continua obrigatória (art.º 80.º-A do RJUE), "
    "mesmo em operações isentas."
)
AVISO_FISCALIZACAO = (
    "As operações isentas podem ser objeto de fiscalização nos termos dos art.º 93.º e seguintes do RJUE."
)
AVISO_RESPONSABILIDADE = (
    "Esta ferramenta é um apoio à preparação do processo. A responsabilidade legal mantém-se "
    "integralmente do requerente e dos técnicos subscritores."
)


def _ref(artigo: str, label: str) -> Dict[str, str]:
    """Devolve a referência legal canónica com URL para o artigo no PGDL."""
    artigo_slug = {
        "4": "625A0004", "4.º": "625A0004",
        "6": "625A0006", "6.º": "625A0006",
        "6-A": "625A0006A", "6.º-A": "625A0006A",
        "7": "625A0007", "7.º": "625A0007",
        "34": "625A0034", "34.º": "625A0034",
        "80-A": "625A0080A", "80.º-A": "625A0080A",
    }
    slug = artigo_slug.get(artigo, "")
    url = (
        f"https://www.pgdlisboa.pt/leis/lei_mostra_articulado.php?artigo_id={slug}"
        f"&nid=625&tabela=leis&pagina=1&ficha=1&so_miolo="
    ) if slug else LEI_RJUE["versao_consolidada_url"]
    return {"artigo": artigo, "descricao": label, "url": url}


# Catálogo de regras: cada entrada tem o seu matcher como função que recebe `d` (respostas)
# e devolve True/False. A ordem reflete a especificidade (mais específica → mais geral).

REGRAS: List[Dict[str, Any]] = [
    # ------------------------------------------------------------------ 1
    {
        "codigo": "ZONA_PROTEGIDA_IMOVEL_CLASSIFICADO",
        "titulo": "Imóvel classificado ou em zona de proteção — controlo prévio obrigatório",
        "status": "confirmado",
        "referencias": [
            _ref("4.º", "n.º 2 alínea d) — obras em imóveis classificados ou em zonas de proteção estão sujeitas a licença (salvo a exceção da alínea l) do n.º 4 do art.º 4.º)"),
            _ref("6.º-A", "n.º 2 — as isenções de escassa relevância NÃO se aplicam a imóveis classificados, em zonas de proteção ou em conjuntos/sítios classificados, com a exceção da alínea j) do n.º 1 (substituição de caixilhos para eficiência energética)"),
        ],
        "procedimento": "licenciamento",
        "fundamento_legal": (
            "Operação em imóvel classificado, em vias de classificação, ou em zona de proteção — "
            "sujeita a licença nos termos do art.º 4.º n.º 2 alínea d) do RJUE. As isenções de "
            "escassa relevância urbanística do art.º 6.º-A não se aplicam (n.º 2 do mesmo artigo), "
            "exceto a substituição de caixilhos para eficiência energética [alínea j) do n.º 1]."
        ),
        "tecnicos_obrigatorios": ["arquiteto", "engenheiro_estruturas"],
        "pecas_necessarias": [
            "Requerimento (modelo oficial do art.º 4.º-A)",
            "Memória descritiva e justificativa",
            "Peças desenhadas (plantas, cortes, alçados)",
            "Termo de responsabilidade do autor do projeto (art.º 10.º do RJUE)",
            "Parecer prévio favorável da entidade competente do património cultural",
        ],
        "avisos": [
            "Classificação como imóvel de interesse nacional, público ou municipal, ou localização em zona de proteção, obrigam a parecer favorável prévio da entidade competente do património cultural.",
            AVISO_PDM, AVISO_FISCALIZACAO, AVISO_RESPONSABILIDADE,
        ],
        "match": lambda d: bool(d.get("imovel_classificado") or d.get("zona_protegida")),
    },

    # ------------------------------------------------------------------ 2
    {
        "codigo": "ESCASSA_RELEVANCIA_ANEXO",
        "titulo": "Edificação contígua de baixa altura e área reduzida",
        "status": "confirmado",
        "referencias": [
            _ref("6.º-A", "n.º 1 alínea a) — edificações contíguas ou não ao edifício principal com altura ≤ 2,2 m (ou cércea do R/C) e área ≤ 10 m², desde que não confinem com a via pública"),
            _ref("6.º", "n.º 1 alínea c) — as obras de escassa relevância urbanística estão isentas de licença e de comunicação prévia"),
        ],
        "procedimento": "isento",
        "fundamento_legal": (
            "Enquadra-se como obra de escassa relevância urbanística — art.º 6.º-A n.º 1 alínea a) "
            "do RJUE (edificação com altura ≤ 2,2 m, área ≤ 10 m², sem confinar com a via pública). "
            "A isenção decorre do art.º 6.º n.º 1 alínea c)."
        ),
        "tecnicos_obrigatorios": [],
        "pecas_necessarias": [
            "Informação sobre o início dos trabalhos (art.º 80.º-A do RJUE)",
            "Comunicação ao município caso o regulamento municipal o exija",
        ],
        "avisos": [AVISO_PDM, AVISO_INICIO_TRABALHOS, AVISO_FISCALIZACAO, AVISO_RESPONSABILIDADE],
        "match": lambda d: (
            d.get("tipo_obra") in ("anexo", "telheiro", "edificacao_contigua")
            and (d.get("altura_m") or 99) <= 2.2
            and (d.get("area_implantacao_m2") or 999) <= 10.0
            and not d.get("confina_via_publica", True)
        ),
    },

    # ------------------------------------------------------------------ 3
    {
        "codigo": "ESCASSA_RELEVANCIA_MURO",
        "titulo": "Muros de vedação e muros de suporte de pequena altura",
        "status": "confirmado",
        "referencias": [
            _ref("6.º-A", "n.º 1 alínea b) — muros de vedação até 1,8 m sem confinar com a via pública e muros de suporte de terras até 2 m, desde que não alterem significativamente a topografia"),
        ],
        "procedimento": "isento",
        "fundamento_legal": (
            "Enquadra-se como obra de escassa relevância urbanística — art.º 6.º-A n.º 1 alínea b) "
            "do RJUE (muro de vedação ≤ 1,8 m sem confinar com a via pública ou muro de suporte ≤ 2 m)."
        ),
        "tecnicos_obrigatorios": [],
        "pecas_necessarias": ["Informação sobre o início dos trabalhos (art.º 80.º-A do RJUE)"],
        "avisos": [AVISO_PDM, AVISO_FISCALIZACAO, AVISO_RESPONSABILIDADE],
        "match": lambda d: (
            d.get("tipo_obra") == "muro"
            and (d.get("altura_m") or 99) <= (2.0 if d.get("subtipo_muro") == "suporte" else 1.8)
            and not (d.get("subtipo_muro") != "suporte" and d.get("confina_via_publica"))
        ),
    },

    # ------------------------------------------------------------------ 4
    {
        "codigo": "OBRAS_INTERIORES_ISENTAS",
        "titulo": "Obras no interior sem impacto exterior e sem afetar a estabilidade",
        "status": "confirmado",
        "referencias": [
            _ref("6.º", "n.º 1 alínea b) — obras de alteração no interior que não impliquem modificações exteriores com impacto nas características físicas/estéticas e não afetem a estabilidade (ou, afetando-a, sejam acompanhadas de projeto de estabilidade e termo de responsabilidade)"),
        ],
        "procedimento": "isento",
        "fundamento_legal": (
            "Enquadra-se nas obras isentas de licença e de comunicação prévia — art.º 6.º n.º 1 "
            "alínea b) do RJUE (obras interiores sem impacto exterior e sem afetar a estabilidade). "
            "Se houver intervenção na estabilidade, exige-se projeto de estabilidade e termo de "
            "responsabilidade de técnico habilitado."
        ),
        "tecnicos_obrigatorios": (
            ["engenheiro_estruturas"] if False else []
        ),
        "pecas_necessarias": [
            "Informação sobre o início dos trabalhos (art.º 80.º-A do RJUE)",
        ],
        "avisos": [
            "Se a obra afetar a estabilidade do edifício, é obrigatório projeto de estabilidade e "
            "termo de responsabilidade de técnico habilitado (art.º 6.º n.º 1 alínea b) subalínea ii) do RJUE).",
            "Alterações de fachada, telhado, cobertura ou altura NÃO são abrangidas por esta isenção.",
            "Alterações de uso NÃO são obras interiores: ver art.º 4.º n.º 5 e artigos 62.º-A e 62.º-B.",
            AVISO_PDM, AVISO_RESPONSABILIDADE,
        ],
        "match": lambda d: (
            d.get("tipo_obra") == "interiores"
            and not d.get("altera_fachada", False)
            and not d.get("altera_uso", False)
            and not d.get("altera_cobertura", False)
        ),
    },

    # ------------------------------------------------------------------ 5
    {
        "codigo": "PISCINA_ESCASSA_RELEVANCIA",
        "titulo": "Piscina lúdica associada a edificação principal (área inferior à edificação)",
        "status": "confirmado",
        "referencias": [
            _ref("6.º-A", "n.º 1 alínea e) — edificação de equipamento lúdico ou de lazer associado a edificação principal com área inferior à desta última"),
        ],
        "procedimento": "isento",
        "fundamento_legal": (
            "A piscina enquadra-se como equipamento lúdico ou de lazer associado a edificação "
            "principal com área inferior à desta — art.º 6.º-A n.º 1 alínea e) do RJUE, isento de "
            "controlo prévio (via art.º 6.º n.º 1 alínea c))."
        ),
        "tecnicos_obrigatorios": [],
        "pecas_necessarias": ["Informação sobre o início dos trabalhos (art.º 80.º-A do RJUE)"],
        "avisos": [
            "Esta leitura pressupõe a existência de edificação principal legalizada e piscina com "
            "área inferior à desta.",
            AVISO_PDM, AVISO_FISCALIZACAO, AVISO_RESPONSABILIDADE,
        ],
        "match": lambda d: (
            d.get("tipo_obra") == "piscina"
            and d.get("tem_edificacao_principal", False)
            and (d.get("area_implantacao_m2") or 0) > 0
            and (d.get("area_construcao_total_m2") or 0) > 0
            and (d.get("area_implantacao_m2") or 0) < (d.get("area_construcao_total_m2") or 0)
        ),
    },

    # ------------------------------------------------------------------ 6
    {
        "codigo": "PISCINA_COMUNICACAO_PREVIA",
        "titulo": "Piscina associada a edificação principal — comunicação prévia",
        "status": "confirmado",
        "referencias": [
            _ref("4.º", "n.º 4 alínea j) — a edificação de piscinas associadas a edificação principal está sujeita a comunicação prévia"),
        ],
        "procedimento": "comunicacao_previa",
        "fundamento_legal": (
            "A edificação de piscinas associadas a edificação principal está sujeita a comunicação "
            "prévia — art.º 4.º n.º 4 alínea j) do RJUE."
        ),
        "tecnicos_obrigatorios": ["arquiteto", "engenheiro_estruturas"],
        "pecas_necessarias": [
            "Comunicação prévia (modelo oficial do art.º 4.º-A)",
            "Memória descritiva",
            "Peças desenhadas (planta, corte e implantação)",
            "Termo de responsabilidade (art.º 10.º do RJUE)",
        ],
        "avisos": [AVISO_PDM, AVISO_RESPONSABILIDADE],
        "match": lambda d: d.get("tipo_obra") == "piscina",
    },

    # ------------------------------------------------------------------ 7
    {
        "codigo": "AMPLIACAO_COMUNICACAO_PREVIA_PDM",
        "titulo": "Ampliação em zona abrangida por PDM/UE/loteamento com parâmetros definidos",
        "status": "confirmado",
        "referencias": [
            _ref("4.º", "n.º 4 alínea d) — obras de construção, alteração ou ampliação em área abrangida por plano de pormenor, unidade de execução ou operação de loteamento que definam alinhamentos, polígono base, altura, pisos, área de construção e usos"),
            _ref("4.º", "n.º 4 alínea e) — obras em zona urbana consolidada que respeitem os PMOT e cuja altura não ultrapasse a mais frequente das fachadas da frente edificada e não sejam sujeitas a cedências"),
        ],
        "procedimento": "comunicacao_previa",
        "fundamento_legal": (
            "A ampliação está sujeita a comunicação prévia por se enquadrar no art.º 4.º n.º 4 "
            "alínea d) do RJUE (área abrangida por PP/UE/loteamento com parâmetros definidos) ou, "
            "alternativamente, na alínea e) do mesmo n.º 4 (zona urbana consolidada)."
        ),
        "tecnicos_obrigatorios": [
            "arquiteto", "engenheiro_estruturas", "engenheiro_civil_ou_eletrotecnico",
            "coordenador_projeto",
        ],
        "pecas_necessarias": [
            "Comunicação prévia (modelo oficial)",
            "Memória descritiva e justificativa",
            "Projeto de arquitetura",
            "Projetos de especialidades (estabilidade, redes, acústica, SCIE, etc.)",
            "Termos de responsabilidade de todos os autores de projeto (art.º 10.º)",
            "Levantamento topográfico, plantas de localização e de implantação",
        ],
        "avisos": [
            "A opção pela comunicação prévia só é possível se existir PDM/UE/loteamento com "
            "parâmetros definidos ou zona urbana consolidada; caso contrário, a ampliação está "
            "sujeita a licenciamento (art.º 4.º n.º 2 alínea c)).",
            "O requerente não pode optar por licenciamento nas operações sujeitas a CP (art.º 4.º n.º 6).",
            AVISO_PDM, AVISO_RESPONSABILIDADE,
        ],
        "match": lambda d: (
            d.get("tipo_obra") == "ampliacao"
            and (d.get("tem_pdm_com_parametros") or d.get("tem_loteamento_pip") or d.get("zona_urbana_consolidada"))
        ),
    },

    # ------------------------------------------------------------------ 8
    {
        "codigo": "AMPLIACAO_LICENCIAMENTO",
        "titulo": "Ampliação sem enquadramento de PDM detalhado — licenciamento",
        "status": "confirmado",
        "referencias": [
            _ref("4.º", "n.º 2 alínea c) — as obras de construção, de alteração ou de ampliação que não se encontrem sujeitas a comunicação prévia nos termos da alínea d) do n.º 4 estão sujeitas a licença"),
        ],
        "procedimento": "licenciamento",
        "fundamento_legal": (
            "A ampliação está sujeita a licenciamento — art.º 4.º n.º 2 alínea c) do RJUE — por "
            "não estar abrangida por PP/UE/loteamento com parâmetros definidos nem configurar "
            "zona urbana consolidada nos termos da alínea e) do n.º 4."
        ),
        "tecnicos_obrigatorios": [
            "arquiteto", "engenheiro_estruturas", "engenheiro_civil_ou_eletrotecnico",
            "coordenador_projeto",
        ],
        "pecas_necessarias": [
            "Requerimento (modelo oficial)",
            "Projeto de arquitetura",
            "Projetos de especialidades",
            "Termos de responsabilidade (art.º 10.º)",
            "Levantamento topográfico, plantas de localização e de implantação",
        ],
        "avisos": [AVISO_PDM, AVISO_RESPONSABILIDADE],
        "match": lambda d: d.get("tipo_obra") == "ampliacao",
    },

    # ------------------------------------------------------------------ 9a
    {
        "codigo": "MORADIA_NOVA_COMUNICACAO_PREVIA",
        "titulo": "Construção nova em loteamento / PP / UE com parâmetros definidos ou zona urbana consolidada — comunicação prévia",
        "status": "confirmado",
        "referencias": [
            _ref("4.º", "n.º 4 alínea d) — obras de construção, alteração ou ampliação em área abrangida por plano de pormenor, unidade de execução ou operação de loteamento que definam alinhamentos, polígono base, altura, pisos, área de construção e usos"),
            _ref("4.º", "n.º 4 alínea e) — obras em zona urbana consolidada que respeitem os PMOT e cuja altura não ultrapasse a mais frequente das fachadas da frente edificada e não sejam sujeitas a cedências"),
        ],
        "procedimento": "comunicacao_previa",
        "fundamento_legal": (
            "A construção da moradia está sujeita a comunicação prévia por se enquadrar no art.º 4.º n.º 4 "
            "alínea d) do RJUE (área abrangida por operação de loteamento, plano de pormenor ou unidade de "
            "execução com parâmetros definidos) ou na alínea e) do mesmo n.º 4 (zona urbana consolidada)."
        ),
        "tecnicos_obrigatorios": [
            "arquiteto", "engenheiro_estruturas", "engenheiro_civil", "engenheiro_eletrotecnico",
            "coordenador_projeto",
        ],
        "pecas_necessarias": [
            "Comunicação prévia (modelo oficial)",
            "Projeto de arquitetura",
            "Projetos das especialidades (estabilidade, redes de águas, esgotos e pluviais, "
            "eletricidade, ITED, gás, acústica, SCIE, térmico/REH, acessibilidades)",
            "Termos de responsabilidade dos autores de projeto (art.º 10.º)",
            "Levantamento topográfico, plantas de localização e de implantação",
            "Estimativa orçamental",
        ],
        "avisos": [
            "A comunicação prévia só se aplica se o loteamento / plano de pormenor / unidade de execução "
            "definir os parâmetros (alinhamentos, polígono base, altura, pisos, área de construção e usos) "
            "ou se a obra cumprir as condições da zona urbana consolidada; confirme com o município.",
            "O PDM por si só não basta para a alínea d): é necessário PP, UE ou loteamento com esses parâmetros. "
            "Com informação prévia favorável válida, confirme no município o procedimento aplicável (art.º 17.º do RJUE).",
            AVISO_PDM, AVISO_RESPONSABILIDADE,
        ],
        "match": lambda d: (
            d.get("tipo_obra") == "moradia_nova"
            and (d.get("tem_pdm_com_parametros") or d.get("tem_loteamento_pip") or d.get("zona_urbana_consolidada"))
        ),
    },

    # ------------------------------------------------------------------ 9
    {
        "codigo": "MORADIA_NOVA_LICENCIAMENTO",
        "titulo": "Construção nova — moradia unifamiliar — licenciamento",
        "status": "confirmado",
        "referencias": [
            _ref("4.º", "n.º 2 alínea c) — as obras de construção que não se encontrem sujeitas a comunicação prévia nos termos da alínea d) do n.º 4 estão sujeitas a licença"),
        ],
        "procedimento": "licenciamento",
        "fundamento_legal": (
            "A construção de uma moradia nova está sujeita a licenciamento municipal — art.º 4.º "
            "n.º 2 alínea c) do RJUE, exceto se se enquadrar na alínea d) do n.º 4 (área com PP, "
            "UE ou loteamento com parâmetros definidos), caso em que seria comunicação prévia."
        ),
        "tecnicos_obrigatorios": [
            "arquiteto", "engenheiro_estruturas", "engenheiro_civil", "engenheiro_eletrotecnico",
            "coordenador_projeto",
        ],
        "pecas_necessarias": [
            "Requerimento (modelo oficial)",
            "Projeto de arquitetura",
            "Projetos das especialidades (estabilidade, redes de águas, esgotos e pluviais, "
            "eletricidade, ITED, gás, acústica, SCIE, térmico/REH, acessibilidades)",
            "Termos de responsabilidade dos autores de projeto (art.º 10.º)",
            "Levantamento topográfico à escala adequada",
            "Planta de localização e de implantação",
            "Fotografias do local",
            "Estimativa orçamental",
        ],
        "avisos": [AVISO_PDM, AVISO_RESPONSABILIDADE],
        "match": lambda d: d.get("tipo_obra") == "moradia_nova",
    },

    # ------------------------------------------------------------------ 10 — FALLBACK
    {
        "codigo": "FALLBACK_LICENCIAMENTO",
        "titulo": "Operação sem enquadramento específico — licenciamento por defeito",
        "status": "confirmado",
        "referencias": [_ref("4.º", "operações urbanísticas sujeitas a controlo prévio")],
        "procedimento": "licenciamento",
        "fundamento_legal": (
            "Operação sem enquadramento específico nos regimes de isenção ou de comunicação "
            "prévia — fica sujeita a licenciamento municipal nos termos do art.º 4.º do RJUE. "
            "Recomenda-se um pedido de informação prévia (art.º 14.º) para confirmar o "
            "enquadramento concreto antes de instruir o processo."
        ),
        "tecnicos_obrigatorios": ["arquiteto", "engenheiro_estruturas"],
        "pecas_necessarias": [
            "Pedido de informação prévia (art.º 14.º) ou requerimento de licenciamento",
            "Memória descritiva e justificativa",
            "Peças desenhadas",
            "Termos de responsabilidade",
        ],
        "avisos": [
            "Esta é uma indicação por defeito — para o seu caso concreto, deve confirmar com os "
            "serviços do município a forma de procedimento aplicável.",
            AVISO_PDM, AVISO_RESPONSABILIDADE,
        ],
        "match": lambda d: True,
    },
]


def _controlos_pdm(d: Dict[str, Any]) -> Dict[str, Any]:
    """Verificações de parâmetros do PDM, quando o utilizador os introduziu. Devolve None por chave
    quando o parâmetro não foi fornecido (sem conclusão) e True/False caso haja base para o afirmar."""
    altura_user = d.get("altura_m")
    altura_max = d.get("pdm_altura_max_m")
    indice_user = d.get("indice_implantacao")
    indice_max = d.get("pdm_indice_implantacao")
    afastamento_user = d.get("afastamento_min_m")
    afastamento_pdm = d.get("pdm_afastamento_min_m")

    def _le(a, b):
        if a is None or b is None:
            return None
        return float(a) <= float(b) + 1e-9

    def _ge(a, b):
        if a is None or b is None:
            return None
        return float(a) >= float(b) - 1e-9

    return {
        "altura_ok": _le(altura_user, altura_max),
        "indice_ok": _le(indice_user, indice_max),
        "afastamento_ok": _ge(afastamento_user, afastamento_pdm),
    }


def diagnosticar(respostas: Dict[str, Any]) -> Dict[str, Any]:
    """Determina o procedimento aplicável a uma operação urbanística em Portugal.

    Devolve um dicionário com `procedimento`, `regra_aplicada`, `fundamento_legal`,
    `tecnicos_obrigatorios`, `pecas_necessarias`, `avisos`, `controlos_pdm` e
    `referencias_legais` (lista {artigo, descricao, url}).
    """
    d = dict(respostas or {})
    regra_aplicada = None
    for r in REGRAS:
        try:
            if r["match"](d):
                regra_aplicada = r
                break
        except Exception:  # noqa: BLE001
            continue
    if regra_aplicada is None:
        regra_aplicada = REGRAS[-1]  # fallback

    controlos = _controlos_pdm(d)
    avisos = list(regra_aplicada.get("avisos") or [])
    if controlos.get("altura_ok") is False:
        avisos.insert(0, "A altura declarada excede o limite máximo indicado para o PDM — rever o projeto antes de submeter.")
    if controlos.get("indice_ok") is False:
        avisos.insert(0, "O índice de implantação declarado excede o limite do PDM — rever o projeto antes de submeter.")
    if controlos.get("afastamento_ok") is False:
        avisos.insert(0, "O afastamento mínimo declarado é inferior ao exigido pelo PDM — rever o projeto antes de submeter.")

    return {
        "procedimento": regra_aplicada["procedimento"],
        "regra_aplicada": regra_aplicada["codigo"],
        "titulo_regra": regra_aplicada.get("titulo"),
        "status_regra": regra_aplicada.get("status", "confirmado"),
        "fundamento_legal": regra_aplicada["fundamento_legal"],
        "tecnicos_obrigatorios": list(regra_aplicada.get("tecnicos_obrigatorios") or []),
        "pecas_necessarias": list(regra_aplicada.get("pecas_necessarias") or []),
        "avisos": avisos,
        "controlos_pdm": controlos,
        "referencias_legais": list(regra_aplicada.get("referencias") or []),
        "lei_base": LEI_RJUE,
    }

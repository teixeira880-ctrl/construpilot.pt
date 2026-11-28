"""Ferramentas do Assistente para seguir o fio do projeto: ler o projeto do Ateliê (geometria e medições exatas),
ligar-lhe cada resultado (maquete BIM, estudo térmico, plantas de execução, orçamento, DCE) e gerar o dossier final."""
from __future__ import annotations

from engines.fio_projeto import servico as S
from engines.fio_projeto.lingua import FORMATO_TOOLS, LANG


def _fn(name, description, properties, required=None):
    params = {"type": "object", "properties": properties, "required": required or list(properties), "additionalProperties": False}
    if FORMATO_TOOLS == "anthropic":
        return {"name": name, "description": description, "input_schema": params}
    return {"type": "function", "name": name, "description": description, "strict": True, "parameters": params}


_D = {
    "pt": {
        "ler": ("Lê o projeto do Ateliê Arquiteto (projet_id «arch_…») e o seu fio: áreas, paredes por tipo com camadas, "
                "mapa de vãos, cobertura, lajes, escadas, exteriores, impressão digital da geometria, etapas feitas e por fazer, "
                "imagens 3D/renders guardadas. É a ÚNICA fonte de quantidades do projeto: nunca uses rácios nem estimativas."),
        "ligar": ("Liga ao projeto um resultado produzido noutra ferramenta (maquete BIM, estudo térmico, plantas de execução, "
                  "estudo de engenharia, orçamento, DCE) para que fique no fio com a geometria em que foi feito."),
        "dossier": "Gera o dossier final do projeto (PDF): seguimento, áreas, envolvente, mapa de vãos, imagens 3D e renders, peças desenhadas.",
        "pid": "Identificador do projeto do Ateliê (arch_…)", "campo": "Tipo de resultado ligado", "valor": "Identificador do resultado",
        "nota": "Nota curta (opcional, pode ser vazia)",
    },
    "fr": {
        "ler": ("Lit le projet de l'Atelier Architecte (projet_id « arch_… ») et son fil : surfaces, murs par type avec couches, "
                "tableau des menuiseries, toiture, planchers, escaliers, extérieurs, empreinte de la géométrie, étapes faites et à "
                "faire, images 3D/rendus enregistrés. C'est la SEULE source de quantités du projet : jamais de ratios ni d'estimation."),
        "ligar": ("Lie au projet un résultat produit par un autre outil (maquette BIM, étude thermique, plans d'exécution, étude "
                  "d'ingénierie, devis, DCE) pour qu'il reste dans le fil avec la géométrie sur laquelle il a été fait."),
        "dossier": "Génère le dossier final du projet (PDF) : suivi, surfaces, enveloppe, menuiseries, images 3D et rendus, pièces graphiques.",
        "pid": "Identifiant du projet Atelier (arch_…)", "campo": "Type de résultat lié", "valor": "Identifiant du résultat",
        "nota": "Courte note (facultative, peut être vide)",
    },
}[LANG if LANG in ("pt", "fr") else "pt"]

FIO_TOOLS = [
    _fn("fio_ler_projeto", _D["ler"], {"projet_id": {"type": "string", "description": _D["pid"]}}),
    _fn("fio_ligar", _D["ligar"], {
        "projet_id": {"type": "string", "description": _D["pid"]},
        "campo": {"type": "string", "enum": sorted(k for k in S.LIGACOES if k != "conversation_id"), "description": _D["campo"]},
        "valor": {"type": "string", "description": _D["valor"]},
        "nota": {"type": "string", "description": _D["nota"]}}),
    _fn("fio_dossier_final", _D["dossier"], {"projet_id": {"type": "string", "description": _D["pid"]}}),
]
FIO_TOOL_NAMES = {t["name"] for t in FIO_TOOLS}

FIO_INSTRUCTIONS = {
    "pt": """
FIO DO PROJETO (projeto vindo do Ateliê, do BIM Studio ou da Engenharia — «projet_id: arch_…») — método:
1. Começa SEMPRE por fio_ler_projeto. As quantidades, áreas, camadas e vãos vêm daí e de mais nenhum lado; não inventes nem estimes.
   Se uma etapa aparecer «desatualizada», diz que foi feita sobre um desenho anterior e refá-la antes de seguir.
2. Segue a ordem das etapas por fazer (proxima_etapa): estudo térmico → plantas de execução / engenharia → orçamento → caderno de
   encargos → dossier final. Usa as ferramentas especializadas que já existem (ex.: pre_certificado_reh, calcul_isolamento,
   generate_execution_plans, generate_full_bet_study, create_quote_draft + add_quote_lines) com os dados lidos.
3. Cada resultado produzido é LIGADO com fio_ligar (campo + identificador) — assim nada se perde e o dossier final junta tudo.
4. Termina com fio_dossier_final e dá o link do PDF. Estudos de especialidade são pré-estudos a validar e assinar por técnico habilitado.
""",
    "fr": """
FIL DU PROJET (projet venant de l'Atelier, du BIM Studio ou de l'Ingénierie — « projet_id: arch_… ») — méthode :
1. Commence TOUJOURS par fio_ler_projeto. Les quantités, surfaces, couches et baies viennent de là et de nulle part ailleurs ;
   n'invente ni n'estime rien. Si une étape est « à refaire », dis qu'elle a été faite sur un dessin antérieur et refais-la.
2. Suis l'ordre des étapes à faire (proxima_etapa) : étude thermique → plans d'exécution / ingénierie → devis → DCE → dossier final.
   Utilise les outils spécialisés existants (ex. generate_execution_plans, generate_full_bet_study, create_quote_draft +
   add_quote_lines) avec les données lues.
3. Chaque résultat produit est LIÉ avec fio_ligar (campo + identifiant) — rien ne se perd et le dossier final rassemble tout.
4. Termine par fio_dossier_final et donne le lien du PDF. Les études sont des pré-études à valider et signer par un professionnel qualifié.
""",
}[LANG if LANG in ("pt", "fr") else "pt"]


async def run_fio_tool(name: str, args: dict, user: dict, db, **_kw) -> dict:
    pid = str((args or {}).get("projet_id") or "").strip()
    try:
        if name == "fio_ler_projeto":
            est = await S.estado(db, user, pid)
            return {"ok": True, **est, "dossier_url": f"/api/fio-projeto/{pid}/dossier.pdf"}
        if name == "fio_ligar":
            lig = await S.ligar(db, user, pid, args.get("campo"), args.get("valor"), args.get("nota") or "")
            return {"ok": True, "ligacao": lig}
        if name == "fio_dossier_final":
            _, est = await S.dossier(db, user, pid)
            return {"ok": True, "url": f"/api/fio-projeto/{pid}/dossier.pdf", "etapas": est["etapas"],
                    "imagens": len(est["imagens"]), "geometria": est["projeto"]["geometria"]}
    except S.ErroFio as e:
        return {"ok": False, "error": e.msg}
    return {"ok": False, "error": f"unknown tool {name}"}

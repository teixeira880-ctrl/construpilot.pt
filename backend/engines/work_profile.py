"""Perfil de trabalho adaptativo (por utilizador).

Seis dimensões distintas, que NÃO se confundem:
1. profissões / especialidades (várias possíveis)     → `professions`
2. responsabilidades (proprietário, gestor, …)         → `responsibilities`
3. quantidade de ajuda (guiado / direto / avançado)    → `mode`
4. profundidade da linguagem (simples / técnica)       → `language`
5. permissões efetivas                                 → core.permissions (NUNCA alteradas aqui)
6. funcionalidades do plano comercial                  → engines.access (NUNCA alteradas aqui)

O perfil só muda a apresentação (sugestões, ordem, linguagem). Uma tarefa sugerida só é
mostrada se as permissões e o plano já a autorizam; o servidor continua a validar cada rota.
Nada é deduzido da profissão: nem qualificações, nem habilitações, nem taxas de IVA.
"""
from __future__ import annotations

PROFESSIONS: dict[str, str] = {
    "arquiteto": "Arquiteto",
    "engenheiro": "Engenheiro civil / projetista",
    "empreiteiro": "Empresa de construção / empreiteiro geral",
    "independente": "Construtor ou trabalhador independente",
    "encarregado": "Encarregado / gestor de obra",
    "orcamentista": "Medidor / orçamentista",
    "pintor": "Pintor",
    "pedreiro": "Pedreiro",
    "canalizador": "Canalizador",
    "eletricista": "Eletricista",
    "carpinteiro": "Carpinteiro / instalador de mobiliário",
    "revestimentos": "Instalador de revestimentos, pavimentos ou isolamento",
    "administrativo": "Administrativo",
    "particular": "Particular / proprietário",
    "outra": "Outra profissão",
}

RESPONSIBILITIES = {
    "proprietario": "Proprietário da empresa",
    "gestor": "Gestor",
    "tecnico": "Técnico",
    "administrativo": "Administrativo",
    "campo": "Trabalhador de campo",
}

MODES = {
    "guiado": "Guiado — uma pergunta de cada vez, com exemplos",
    "direto": "Direto — acesso rápido às tarefas frequentes",
    "avancado": "Avançado — todos os parâmetros técnicos",
}
LANGUAGES = {"simples": "Linguagem corrente", "tecnica": "Linguagem técnica"}

# Perfil aplicado a quem salta o onboarding ou a contas antigas (nunca bloqueia nada).
DEFAULT_PROFILE = {
    "professions": [], "other_profession": "", "responsibilities": [], "frequent_tasks": [],
    "mode": "guiado", "language": "simples", "onboarding": "pending",
}

# Catálogo de tarefas. `feature` = permissão de core.permissions exigida (None = nenhuma);
# `min_level` = nível de engines.access exigido. `status` = "ready" só se a ferramenta existe e funciona.
TASKS: dict[str, dict] = {
    "orcamento_guiado": {"label": "Preparar um orçamento passo a passo", "url": "/orcamento-guiado", "feature": "devis", "min_level": "pro"},
    "orcamento": {"label": "Criar ou editar um orçamento", "url": "/devis-editeur", "feature": "devis", "min_level": "pro"},
    "reutilizar": {"label": "Reutilizar um orçamento anterior", "url": "/devis", "feature": "devis", "min_level": "pro"},
    "calc_tinta": {"label": "Calcular tinta", "url": "/ferramentas-oficio?ferramenta=paint", "feature": None, "min_level": "particulier_gratuit"},
    "calc_pavimento": {"label": "Calcular pavimento ou revestimento", "url": "/ferramentas-oficio?ferramenta=floor", "feature": None, "min_level": "particulier_gratuit"},
    "calc_alvenaria": {"label": "Calcular blocos de alvenaria", "url": "/ferramentas-oficio?ferramenta=masonry", "feature": None, "min_level": "particulier_gratuit"},
    "plantas": {"label": "Medir numa planta", "url": "/plan", "feature": None, "min_level": "particulier_gratuit"},
    "obras": {"label": "Acompanhar as obras", "url": "/chantiers", "feature": "chantier", "min_level": "pro"},
    "diario": {"label": "Registar o dia de obra", "url": "/suivi-chantier", "feature": "chantier", "min_level": "business"},
    "planeamento": {"label": "Planear os trabalhos", "url": "/planning", "feature": "chantier", "min_level": "pro"},
    "materiais": {"label": "Materiais e encomendas", "url": "/appro", "feature": "chantier", "min_level": "pro"},
    "clientes": {"label": "Clientes", "url": "/clients", "feature": "devis", "min_level": "pro"},
    "faturas": {"label": "Faturas e pagamentos", "url": "/factures", "feature": "factures", "min_level": "pro"},
    "rentabilidade": {"label": "Acompanhar custos e margem", "url": "/rentabilite", "feature": "dashboard", "min_level": "pro"},
    "estimar": {"label": "Estimar o custo das obras", "url": "/estimation", "feature": None, "min_level": "particulier_gratuit"},
    "analisar_orcamento": {"label": "Compreender um orçamento recebido", "url": "/scanner-devis", "feature": None, "min_level": "particulier_gratuit"},
    "projetos": {"label": "Organizar o meu projeto", "url": "/smart-project", "feature": None, "min_level": "particulier_gratuit"},
    "plantas_versoes": {"label": "Consultar e comparar plantas", "url": "/plan/compare", "feature": None, "min_level": "pro"},
    "medicoes": {"label": "Medições e quantidades", "url": "/metre", "feature": None, "min_level": "pro"},
    "assistente": {"label": "Perguntar ao assistente", "url": "/assistant", "feature": None, "min_level": "particulier_payant"},
}

# Sugestões iniciais por profissão (ordem = prioridade). A profissão sugere; nunca obriga.
PROFESSION_TASKS: dict[str, list[str]] = {
    "pintor": ["orcamento_guiado", "calc_tinta", "reutilizar", "obras"],
    "pedreiro": ["orcamento_guiado", "calc_alvenaria", "calc_pavimento", "obras"],
    "canalizador": ["orcamento", "reutilizar", "obras", "materiais"],
    "eletricista": ["orcamento", "reutilizar", "obras", "materiais"],
    "carpinteiro": ["orcamento", "reutilizar", "materiais", "obras"],
    "revestimentos": ["calc_pavimento", "orcamento_guiado", "reutilizar", "obras"],
    "empreiteiro": ["orcamento", "planeamento", "materiais", "rentabilidade", "obras"],
    "independente": ["orcamento_guiado", "reutilizar", "obras", "faturas"],
    "encarregado": ["diario", "obras", "planeamento", "materiais"],
    "orcamentista": ["medicoes", "plantas", "orcamento", "reutilizar"],
    "arquiteto": ["projetos", "plantas", "plantas_versoes", "medicoes"],
    "engenheiro": ["medicoes", "plantas", "plantas_versoes", "obras"],
    "administrativo": ["clientes", "faturas", "orcamento", "rentabilidade"],
    "particular": ["estimar", "analisar_orcamento", "projetos", "plantas"],
    "outra": ["orcamento_guiado", "plantas", "obras"],
}
GENERIC_TASKS = ["orcamento_guiado", "plantas", "estimar", "obras"]


class ProfileError(ValueError):
    pass


def _clean_list(values, allowed: dict, field: str, limit: int) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ProfileError(f"«{field}» deve ser uma lista.")
    out: list[str] = []
    for v in values:
        if v not in allowed:
            raise ProfileError(f"Valor desconhecido em «{field}»: {v}")
        if v not in out:
            out.append(v)
    return out[:limit]


def normalize(update: dict, current: dict | None = None) -> dict:
    """Valida uma atualização parcial e devolve o perfil completo. Campos desconhecidos são ignorados
    (o perfil nunca transporta permissões, plano ou papel)."""
    base = {**DEFAULT_PROFILE, **(current or {})}
    out = {k: base[k] for k in DEFAULT_PROFILE}
    if "professions" in update:
        out["professions"] = _clean_list(update["professions"], PROFESSIONS, "profissões", 5)
    if "responsibilities" in update:
        out["responsibilities"] = _clean_list(update["responsibilities"], RESPONSIBILITIES, "responsabilidades", 5)
    if "frequent_tasks" in update:
        out["frequent_tasks"] = _clean_list(update["frequent_tasks"], TASKS, "tarefas frequentes", 8)
    if "other_profession" in update:
        out["other_profession"] = str(update.get("other_profession") or "").strip()[:120]
    if "mode" in update:
        if update["mode"] not in MODES:
            raise ProfileError("Modo desconhecido.")
        out["mode"] = update["mode"]
    if "language" in update:
        if update["language"] not in LANGUAGES:
            raise ProfileError("Linguagem desconhecida.")
        out["language"] = update["language"]
    if "onboarding" in update:
        if update["onboarding"] not in ("pending", "done", "skipped"):
            raise ProfileError("Estado de onboarding desconhecido.")
        out["onboarding"] = update["onboarding"]
    if "outra" not in out["professions"]:
        out["other_profession"] = ""
    return out


def suggested_task_keys(profile: dict) -> list[str]:
    keys: list[str] = list(profile.get("frequent_tasks") or [])
    for p in profile.get("professions") or []:
        keys += PROFESSION_TASKS.get(p, [])
    if not keys:
        keys = list(GENERIC_TASKS)
    seen: set[str] = set()
    return [k for k in keys if not (k in seen or seen.add(k))]


def visible_tasks(profile: dict, permissions: dict, level: str, *, meets, limit: int = 5) -> list[dict]:
    """Tarefas sugeridas, filtradas pelo que o utilizador JÁ pode fazer. Esconder ≠ controlo de acesso:
    cada rota continua protegida no servidor; este filtro só evita mostrar o que daria « acesso recusado »."""
    out = []
    for key in suggested_task_keys(profile):
        t = TASKS[key]
        if t["feature"] and permissions.get(t["feature"]) is not True:
            continue
        if not meets(level, t["min_level"]):
            continue
        out.append({"key": key, "label": t["label"], "url": t["url"]})
        if len(out) >= limit:
            break
    return out


def catalog() -> dict:
    return {
        "professions": [{"key": k, "label": v} for k, v in PROFESSIONS.items()],
        "responsibilities": [{"key": k, "label": v} for k, v in RESPONSIBILITIES.items()],
        "modes": [{"key": k, "label": v} for k, v in MODES.items()],
        "languages": [{"key": k, "label": v} for k, v in LANGUAGES.items()],
        "tasks": [{"key": k, "label": v["label"]} for k, v in TASKS.items()],
        "profession_tasks": PROFESSION_TASKS,
    }


# Sugestão de profissão a partir de uma descrição livre: palavras-chave determinísticas,
# sempre devolvida como proposta a confirmar (nunca aplicada automaticamente).
_KEYWORDS = {
    "pintor": ["pint", "tinta", "estuque"], "pedreiro": ["pedreir", "alvenaria", "tijolo", "reboco"],
    "canalizador": ["canaliz", "água", "agua", "esgoto", "sanit"], "eletricista": ["eletric", "elétric", "quadro elétrico", "tomadas"],
    "carpinteiro": ["carpint", "madeira", "móve", "move", "cozinhas"], "revestimentos": ["pavimento", "azulejo", "cerâmic", "isolamento", "chão", "soalho"],
    "arquiteto": ["arquitet"], "engenheiro": ["engenh", "projetist", "estrutur"], "empreiteiro": ["empreit", "construtora", "empresa de construção"],
    "encarregado": ["encarregad", "gestor de obra", "diretor de obra"], "orcamentista": ["orçamentist", "medidor", "medições"],
    "administrativo": ["administrativ", "contabil", "faturação"], "particular": ["minha casa", "particular", "proprietári"],
}


def suggest_from_text(text: str) -> list[str]:
    t = (text or "").lower()[:1000]
    return [k for k, words in _KEYWORDS.items() if any(w in t for w in words)][:3]

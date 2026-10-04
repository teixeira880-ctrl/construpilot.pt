#!/usr/bin/env python3
"""Revisão PT-BR → PT-PT do pt_auto.json.

Aplica substituições whole-word (bordas de palavra ou pontuação) nos VALORES
do dicionário i18n. Mantém chaves (FR) intactas.

Casos preservados:
- "contacto" NÃO vira "contato" (PT-PT usa com c)
- "ação" aceite (AO 1990); "acção" não presente deve manter-se raro
- "fato" ambíguo (traje) → NÃO substituído; apenas "no entanto fato" explícito via regex
- `você(s)` para contextos formais → mantém mas regista para revisão humana se grande volume

Produz dois outputs:
- Reescreve o pt_auto.json com valores revistos
- Grava /app/memory/i18n_corrections.md com contagens por categoria
"""
import json
import re
from pathlib import Path
from collections import Counter

SRC = Path("/app/frontend/src/i18n/pt_auto.json")

# Substituições whole-word (case-sensitive — mantém maiúsculas iniciais).
# Formato: (regex, replacement, categoria)
RULES = [
    # Ficheiros
    (r"\barquivos?\b", "ficheiro", "arquivo→ficheiro"),
    (r"\bArquivos?\b", "Ficheiro", "arquivo→ficheiro"),
    # Transferir / descarregar
    (r"\bbaixar\b", "transferir", "baixar→transferir"),
    (r"\bBaixar\b", "Transferir", "baixar→transferir"),
    (r"\bbaixado\b", "transferido", "baixar→transferir"),
    (r"\bBaixado\b", "Transferido", "baixar→transferir"),
    # Registo
    (r"\bcadastros?\b", "registo", "cadastro→registo"),
    (r"\bCadastros?\b", "Registo", "cadastro→registo"),
    (r"\bcadastrar\b", "registar", "cadastrar→registar"),
    (r"\bCadastrar\b", "Registar", "cadastrar→registar"),
    (r"\bcadastrado\b", "registado", "cadastrado→registado"),
    (r"\bCadastrado\b", "Registado", "cadastrado→registado"),
    # Telemóvel
    (r"\bcelulares?\b", "telemóvel", "celular→telemóvel"),
    (r"\bCelulares?\b", "Telemóvel", "celular→telemóvel"),
    # Ecrã
    (r"\btelas?\b", "ecrã", "tela→ecrã"),
    (r"\bTelas?\b", "Ecrã", "tela→ecrã"),
    # Equipa
    (r"\btimes?\b(?!\s*(?:como|de\s+acesso|registo))", "equipa", "time→equipa"),
    (r"\bTimes?\b(?!\s*(?:como|de\s+acesso|registo))", "Equipa", "time→equipa"),
    # Sessão
    (r"\blogar\b", "iniciar sessão", "logar→iniciar sessão"),
    (r"\bLogar\b", "Iniciar sessão", "logar→iniciar sessão"),
    (r"\bdeslogar\b", "terminar sessão", "deslogar→terminar sessão"),
    (r"\bDeslogar\b", "Terminar sessão", "deslogar→terminar sessão"),
    (r"\blogado\b", "com sessão iniciada", "logado→com sessão iniciada"),
    (r"\bLogado\b", "Com sessão iniciada", "logado→com sessão iniciada"),
    # Guardar
    (r"\bsalvar\b", "guardar", "salvar→guardar"),
    (r"\bSalvar\b", "Guardar", "salvar→guardar"),
    (r"\bsalvo\b", "guardado", "salvo→guardado"),
    (r"\bSalvo\b", "Guardado", "salvo→guardado"),
    # Eliminar
    (r"\bdeletar\b", "eliminar", "deletar→eliminar"),
    (r"\bDeletar\b", "Eliminar", "deletar→eliminar"),
    (r"\bdeletado\b", "eliminado", "deletado→eliminado"),
    (r"\bDeletado\b", "Eliminado", "deletado→eliminado"),
    # Rato / botão
    (r"\bmouse\b", "rato", "mouse→rato"),
    (r"\bMouse\b", "Rato", "mouse→rato"),
    # Utilizador
    (r"\busuários?\b", "utilizador", "usuário→utilizador"),
    (r"\bUsuários?\b", "Utilizador", "usuário→utilizador"),
    # Ligar / conectar
    (r"\bconectar\b", "ligar", "conectar→ligar"),
    (r"\bConectar\b", "Ligar", "conectar→ligar"),
    (r"\bconectado\b", "ligado", "conectado→ligado"),
    (r"\bConectado\b", "Ligado", "conectado→ligado"),
    (r"\bdesconectar\b", "desligar", "desconectar→desligar"),
    (r"\bDesconectar\b", "Desligar", "desconectar→desligar"),
    # Lhe / aplicar
    (r"\baplicativos?\b", "aplicação", "aplicativo→aplicação"),
    (r"\bAplicativos?\b", "Aplicação", "aplicativo→aplicação"),
    # Legal (gíria) — contexto difícil; só substituir se claramente gíria "legal!"
    (r"\bLegal!\b", "Está bem!", "Legal!→Está bem!"),
    # Ortografia: "pra" → "para" (coloquial BR)
    (r"\bpra\b", "para", "pra→para"),
    (r"\bPra\b", "Para", "pra→para"),
    # "tá" / "tah" → "está" (coloquial BR)
    (r"\btá\b", "está", "tá→está"),
    (r"\bTá\b", "Está", "tá→está"),
    # BR usa "ônus" / PT usa "ónus"
    (r"\bônus\b", "ónus", "ônus→ónus"),
    (r"\bÔnus\b", "Ónus", "ônus→ónus"),
    # "idéia" (BR antes AO) → "ideia" (PT)
    (r"\bidéias?\b", "ideia", "idéia→ideia"),
    (r"\bIdéias?\b", "Ideia", "idéia→ideia"),
    # ônibus → autocarro
    (r"\bônibus\b", "autocarro", "ônibus→autocarro"),
    (r"\bÔnibus\b", "Autocarro", "ônibus→autocarro"),
    # Lixo / lixeira → caixote do lixo (contexto UI)
    (r"\blixeira\b", "reciclagem", "lixeira→reciclagem"),
    (r"\bLixeira\b", "Reciclagem", "lixeira→reciclagem"),
    # Caixa postal / caixa de entrada (igual mas confirmar)
    # Dica / dica em UI → sugestão
    # (deixado — "dica" usado em ambos)
    # Diferenças ortográficas pré-AO ainda vistas no BR
    (r"\bfato\s+de\s+que\b", "facto de que", "fato→facto (locução)"),
    (r"\bFato\s+de\s+que\b", "Facto de que", "fato→facto (locução)"),
    # Confirmação dupla: contexto de "fato: " seguido de dois-pontos (facto expositivo)
    (r"\bum fato\b", "um facto", "fato→facto"),
    (r"\bUm fato\b", "Um facto", "fato→facto"),
    (r"\beste fato\b", "este facto", "fato→facto"),
    (r"\bEste fato\b", "Este facto", "fato→facto"),
    # "espera" (correto em PT); "aguarde" preferido no imperativo
    # (deixar como está)
]

def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    counts: Counter[str] = Counter()
    changed = 0
    for key, val in list(data.items()):
        if not isinstance(val, str):
            continue
        new_val = val
        for pattern, repl, category in RULES:
            new_val, n = re.subn(pattern, repl, new_val)
            if n:
                counts[category] += n
        if new_val != val:
            data[key] = new_val
            changed += 1

    SRC.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")

    md = Path("/app/memory/i18n_corrections.md")
    lines = [
        "# Revisão PT-BR → PT-PT · pt_auto.json\n",
        "",
        f"**Total de chaves**: {len(data)}",
        f"**Chaves com valor alterado**: {changed}",
        f"**Total de substituições (soma de ocorrências)**: {sum(counts.values())}",
        "",
        "## Substituições por categoria",
        "",
        "| Regra | Ocorrências |",
        "|---|---|",
    ]
    for cat, n in counts.most_common():
        lines.append(f"| `{cat}` | {n} |")
    if not counts:
        lines.append("| _(nenhuma substituição aplicada — já estava em PT-PT puro)_ | 0 |")
    lines += [
        "",
        "## Notas",
        "",
        "- Substituições são whole-word, case-aware (preservam maiúscula inicial).",
        "- Chaves (FR) intactas; só valores (PT) alterados.",
        "- Casos ambíguos (ex: `fato` = traje vs. facto) só substituídos quando o contexto é inequívoco.",
        "- Palavras já em PT-PT (`contacto`, `ação`, `recepção`) **não foram alteradas**.",
        "- Revisão humana recomendada para contextos informais onde `você` aparece — mantido por default (uso formal admin/B2B).",
    ]
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✓ pt_auto.json revisto: {changed} valores alterados, {sum(counts.values())} substituições")
    print(f"✓ relatório: {md}")

if __name__ == "__main__":
    main()

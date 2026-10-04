#!/usr/bin/env python3
"""Inventário de strings FR hardcoded no frontend PT.

Encontra strings JS/JSX que são claramente francesas (palavras exclusivamente
francesas ou com padrões FR característicos). Produz:
  - `/app/memory/fr_strings_inventory.json`  (lista estruturada)
  - Resumo stdout por ficheiro
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from collections import defaultdict

ROOT = Path("/app/frontend/src")
OUT = Path("/app/memory/fr_strings_inventory.json")

# Palavras ou expressões *exclusivamente* francesas (evitar FP com PT/EN).
FR_SIGNALS = [
    # Interjeições / verbos de UI frequentes
    r"\bBonjour\b", r"\bBienvenue\b", r"\bConnexion\b", r"\bDéconnexion\b",
    r"\bDéconnecter\b", r"\bSe connecter\b",
    r"\bMot de passe\b", r"\bOublié\b", r"\bOubli de mot\b",
    r"\bEnregistrer\b", r"\bEnregistré\b", r"\bEnregistrement\b",
    r"\bSupprimer\b", r"\bSupprimé\b", r"\bModifier\b", r"\bModifié\b",
    r"\bCréer\b", r"\bCréé\b", r"\bNouveau\b", r"\bNouvelle\b",
    r"\bAjouter\b", r"\bAjouté\b", r"\bRechercher\b", r"\bRecherche\b",
    r"\bParamètres\b", r"\bProfil\b",
    r"\bTélécharger\b", r"\bTéléchargement\b", r"\bChargement\b",
    r"\bChargé\b", r"\bEnvoi\b", r"\bEnvoyer\b", r"\bEnvoyé\b", r"\bEnvoyée\b",
    r"\bErreur\b", r"\bSuccès\b", r"\bAttention\b",
    # Palavras técnicas FR do domínio
    r"\bDevis\b", r"\bChantier\b", r"\bChantiers\b", r"\bFournisseur\b",
    r"\bBâtiment\b", r"\bEntreprise\b", r"\bMatériau\b", r"\bMatériaux\b",
    r"\bTableau de bord\b", r"\bAccueil\b", r"\bCommande\b", r"\bCommandes\b",
    r"\bFactur[eé]s?\b", r"\bFacturation\b",
    # Verbos genéricos exclusivos FR
    r"\bAnnuler\b", r"\bContinuer\b", r"\bRetour\b", r"\bSuivant\b", r"\bPrécédent\b",
    r"\bFermer\b", r"\bOuvrir\b", r"\bChoisir\b", r"\bValider\b", r"\bValidé\b",
    r"\bPasser\b", r"\bRéessayer\b", r"\bRetéléverser\b",
    r"\bAperçu\b", r"\bAfficher\b",
    r"\bRéinitialiser\b", r"\bConfirmer\b", r"\bConfirmation\b",
    # Mensagens de erro / avisos FR típicos
    r"\béchec\b", r"\béchecs\b", r"\bimpossible\b", r"\bréussi\b",
    r"\bnon connecté\b", r"\bpas connecté\b", r"\brequis\b",
    # Pequenas pistas
    r"\bAucun(?:e)?\b", r"\bveuillez\b", r"\bréessayez\b",
    r"\bPour l[’']\b", r"\bavec succès\b", r"\bChargement…", r"\bÉchec\b",
    # Expressões técnicas BTP FR a adaptar
    r"\bDTU\b", r"\bRE2020\b", r"\bCSPS\b", r"\bRGE\b",
]
FR_RE = re.compile("|".join(FR_SIGNALS), flags=re.IGNORECASE)

# String literal JS/JSX (dupla, simples ou template sem interpolação) com conteúdo útil
LITERAL_RE = re.compile(r'''
    (?P<quote>["'`])
    (?P<content>(?:(?!\1)[^\\\n]|\\.){2,120})
    (?P=quote)
''', re.VERBOSE)

EXCLUDE_DIRS = {"node_modules", "build", "dist", ".git", "__tests__", "i18n"}
EXCLUDE_FILES = {
    "pt_auto.json",  # é o próprio dicionário FR→PT; não tocar
}
# Ficheiros `*I18n*.js(x)` são DICIONÁRIOS i18n (chaves FR→valores PT).
# Não devem ser tocados — as chaves FR existem por design.
EXCLUDE_NAME_RE = re.compile(r"I18n(Context)?\.(jsx?|tsx?)$")


def main():
    rows: list[dict] = []
    per_file: defaultdict[str, int] = defaultdict(int)

    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in {".jsx", ".tsx", ".js", ".ts"}:
            continue
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        if p.name in EXCLUDE_FILES:
            continue
        if EXCLUDE_NAME_RE.search(p.name):
            continue

        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue

        for lineno, line in enumerate(text.splitlines(), 1):
            # Skip linhas de import, comentário puro, logger
            s = line.strip()
            if s.startswith(("import ", "export ", "//", "*", "/*")):
                continue

            for m in LITERAL_RE.finditer(line):
                content = m.group("content")
                if len(content.strip()) < 3:
                    continue
                # Precisa de pelo menos um sinal FR
                if not FR_RE.search(content):
                    continue
                # Excluir se claramente URL ou código técnico
                if content.startswith(("http", "/api/", "data:", "@/", "./", "../")):
                    continue
                if re.match(r"^[A-Z_][A-Z0-9_]+$", content):
                    continue
                rows.append({
                    "file": str(p.relative_to(ROOT)),
                    "line": lineno,
                    "fr": content[:200],
                })
                per_file[str(p.relative_to(ROOT))] += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"total": len(rows), "per_file": dict(per_file), "rows": rows},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✓ {len(rows)} strings FR encontradas em {len(per_file)} ficheiros")
    for fname, count in sorted(per_file.items(), key=lambda x: -x[1])[:15]:
        print(f"  {count:4d}  {fname}")
    print(f"→ relatório: {OUT}")


if __name__ == "__main__":
    main()

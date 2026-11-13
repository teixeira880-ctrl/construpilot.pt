"""Unidades de medição coerentes nas linhas de orçamento (13/11/2026, Martinho).

Estrutura metálica — pilares, vigas, travessas, madres/correias, contraventamentos, perfis (HEA, HEB, IPE, UPN, tubos…) —
mede-se em ml (ou kg / t), NUNCA em m². Só coberturas, painéis (sandwich), fachadas, lajes e pinturas por área são em m².
Caso real: «Pilares HEA/HEB», «Vigas IPE», «Correias Z/C», «Contraventamento» todos a 1 775,70 m² = a área da cobertura copiada.
Uma linha assim é devolvida ao modelo com o método de cálculo do comprimento; o modelo corrige e volta a chamar a ferramenta.
"""
from __future__ import annotations

import re
import unicodedata

_LINEAR = re.compile(r"\b(pilar|pilares|poteau|poteaux|viga|vigas|poutre|poutres|travessa|travessas|traverse|madre|madres|"
                     r"correia|correias|panne|pannes|contraventamento|contraventamentos|contreventement|tirante|tirantes|"
                     r"diagonal|diagonais|perfil|perfis|profil|profile|hea|heb|hem|ipe|ipn|upn|upe|rhs|shs|chs|tubo|tubos|"
                     r"cantoneira|cornière|corniere|asna|asnas|ferme|fermes|portico|porticos|pórtico|pórticos|longarina|"
                     r"longarinas|lintel|linteis)\b", re.I)
# «cobertura», «fachada», «laje» só dizem ONDE está o elemento (correias de cobertura = ml); o que é medido em área é o
# material de superfície: painel, chapa, revestimento, pintura, isolamento…
_AREA_OK = re.compile(r"\b(painel|paineis|painéis|panneau|panneaux|sandu[ií]che|sandwich|chapa|chapas|bac acier|bardage|"
                      r"revestimento|pintura|peinture|tratamento|traitement|metaliza\w*|galvaniza\w*|isolamento|isolation|"
                      r"impermeabiliza\w*|cofragem|coffrage|betonilha|chape|laje|lajes|dalle)\b", re.I)
_M2 = re.compile(r"^\s*m\s*(²|2|\^2)\s*$|^\s*(sqm|m2s)\s*$", re.I)


def _n(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def bad_linear_lines(args: dict) -> list[str]:
    """Designações de elementos lineares de estrutura metálica medidos em m²."""
    out = []
    for ln in (args or {}).get("lines") or []:
        if not isinstance(ln, dict):
            continue
        des = _n(str(ln.get("designation") or ""))
        if _M2.match(str(ln.get("unit") or "")) and _LINEAR.search(des) and not _AREA_OK.search(des):
            out.append(des[:80])
    return out


def message(bad: list[str], lang: str = "pt") -> str:
    lst = "; ".join(f"«{b}»" for b in bad[:12])
    if str(lang).lower().startswith("fr"):
        return (f"Unités incohérentes : {lst} mesuré(s) en m². Les éléments linéaires de charpente métallique (poteaux, poutres, "
                "traverses, pannes, contreventements, profilés HEA/HEB/IPE/UPN, tubes) se mesurent en ml (ou kg), jamais en m² — "
                "seules couverture, panneaux, bardage, dalles et peinture surfacique sont en m². Recalcule les longueurs à partir du "
                "plan : poteaux = nombre × hauteur ; poutres/traverses = nb de portiques × portée (+ longrines) ; pannes = surface de "
                "couverture ÷ entraxe (≈ 1,5 m si inconnu) ; contreventement = diagonales des travées contreventées (≈ 2 × √(portée² + "
                "hauteur²) par travée). Écris le calcul dans la description (hypothèse si non coté) et rappelle l'outil. Ne mentionne "
                "pas cette erreur à l'utilisateur.")
    return (f"Unidades incoerentes: {lst} medido(s) em m². Os elementos lineares de estrutura metálica (pilares, vigas, travessas, "
            "madres/correias, contraventamentos, perfis HEA/HEB/IPE/UPN, tubos) medem-se em ml (ou kg), nunca em m² — só cobertura, "
            "painéis, fachadas, lajes e pintura por área são em m². Recalcula os comprimentos a partir da planta: pilares = n.º × "
            "altura; vigas/travessas = n.º de pórticos × vão (+ longarinas); madres/correias = área de cobertura ÷ espaçamento "
            "(≈ 1,5 m se desconhecido); contraventamento = diagonais dos vãos contraventados (≈ 2 × √(vão² + altura²) por vão). "
            "Escreve o cálculo na descrição (hipótese se não estiver cotado) e chama de novo a ferramenta. Não menciones este erro "
            "ao utilizador.")

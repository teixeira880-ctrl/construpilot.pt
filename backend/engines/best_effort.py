"""Palavra «teste» no pedido, em QUALQUER língua (pedido do Martinho, 12/11/2026).

«é um teste, faz o melhor que puderes» / «c'est un test, fais le meilleur que tu peux» / «it's a test» / «es una prueba»…
→ o assistente FAZ o estudo até ao fim (nenhuma recusa por falta de desenhos, nenhuma pergunta) e termina SEMPRE com
duas listas: o que está correto (lido/verificado nos documentos) e o que precisa de verificação (hipóteses, valores estimados).
Deteção tolerante aos erros de escrita correntes («texte», «melleur», «peut»…).
"""
from __future__ import annotations

import re
import unicodedata

# palavra «teste» em todas as línguas (PT/FR/EN/ES/IT/DE/UK/RU…) + «é um texte» (erro de escrita corrente)
_TEST = [
    r"\btest(e|es|s|ing|o|a|en)?\b", r"\bprueba\b", r"\bтест\w*", r"\b(e|isto e|isso e|c.?est|ce|c) (um|un) texte?\b",
]
_PT = [r"\bo melhor que (pod|consegu|sab|der)\w*", r"\b(faz|faca|fazer|faze)\b.*\bo melhor\b", r"\bmelhor possivel\b",
       r"\bda o (teu|seu) melhor\b", r"\bmelhor que puder\w*"]
_FR = [r"\b(le )?m(e|ei|i)l+eu?re? (que|possible)\b", r"\bmieux que (tu|vous|possible|je)\b", r"\b(du|le) mieux possible\b",
       r"\b(fais|faites|fait|faire)\b.*\b(au mieux|le mieux|le m(e|ei)l+eu?re?)\b"]
_TEST_RX = re.compile("|".join(_TEST))
_PT_RX = re.compile("|".join(_PT))
_FR_RX = re.compile("|".join(_FR))
_FR_HINT = re.compile(r"\b(c.?est|ce|fais|fait|faites|le|la|les|tu|vous|un|une|etude|devis)\b")
_PT_HINT = re.compile(r"\b(e|um|uma|faz|faca|o|os|estudo|orcamento|isto|nao)\b")


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (s or "").lower()) if not unicodedata.combining(c))


def detect(text: str) -> str | None:
    """→ língua da diretiva ('pt' / 'fr' / 'en') quando a mensagem contém «teste» (qualquer língua) ou pede o melhor esforço."""
    t = _norm(text)
    if not t.strip():
        return None
    if _FR_RX.search(t):
        return "fr"
    if _PT_RX.search(t):
        return "pt"
    if _TEST_RX.search(t):
        fr, pt = len(_FR_HINT.findall(t)), len(_PT_HINT.findall(t))
        if fr > pt:
            return "fr"
        if pt > 0:
            return "pt"
        return "en"
    return None


_DIRECTIVE = {
    "pt": (
        "\n\nMODO TESTE / MELHOR ESFORÇO (a mensagem do utilizador contém «teste» ou pede o melhor possível) — OBRIGATÓRIO nesta "
        "resposta: FAZ O ESTUDO pedido ATÉ AO FIM. É PROIBIDO responder que não é possível por falta de desenhos, plantas cotadas, "
        "materiais ou outras informações, e é proibido fazer perguntas ou mostrar ask_user_choices. Se há documentos anexados: chama "
        "generate_full_bet_study com TODOS esses documentos, copia a frase do utilizador em `hypotheses` (sem desenhos o servidor faz "
        "um ESTUDO INDICATIVO sobre um modelo-tipo) e acompanha com read_full_bet_study até ao fim. Se o estudo falhar, ou se não houver "
        "documentos: create_quote_draft com quantidades e materiais correntes declarados como hipóteses. Entrega SEMPRE o resultado "
        "(ficheiros, total) e termina OBRIGATORIAMENTE com duas secções: «✅ O que está correto» (o que foi lido nos documentos e "
        "calculado/verificado: medidas, materiais, verificações aprovadas) e «⚠️ O que precisa de verificação» (cada hipótese adotada, "
        "valor estimado, verificação não aprovada ou documento em falta, com o que é preciso fornecer ou confirmar)."
    ),
    "fr": (
        "\n\nMODE TEST / MEILLEUR EFFORT (le message de l'utilisateur contient « test » ou demande le meilleur possible) — OBLIGATOIRE "
        "dans cette réponse : FAIS L'ÉTUDE demandée JUSQU'AU BOUT. INTERDIT de répondre que c'est impossible faute de plans cotés, de "
        "matériaux ou d'informations, et interdit de poser des questions ou d'afficher ask_user_choices. S'il y a des documents joints : "
        "appelle generate_full_bet_study avec TOUS ces documents, recopie la phrase de l'utilisateur dans `hypotheses` (sans plans le "
        "serveur fait une ÉTUDE INDICATIVE sur un modèle-type) et suis read_full_bet_study jusqu'au bout. Si l'étude échoue, ou s'il "
        "n'y a pas de documents : create_quote_draft avec des quantités et matériaux courants déclarés comme hypothèses. Livre TOUJOURS "
        "le résultat (fichiers, total) et termine OBLIGATOIREMENT par deux sections : « ✅ Ce qui est correct » (ce qui a été lu dans les "
        "documents et calculé/vérifié : cotes, matériaux, vérifications conformes) et « ⚠️ Ce qui doit être vérifié » (chaque hypothèse "
        "retenue, valeur estimée, vérification non conforme ou pièce manquante, avec ce qu'il faut fournir ou confirmer)."
    ),
    "en": (
        "\n\nTEST / BEST-EFFORT MODE (the user's message contains « test » or asks for the best possible) — MANDATORY in this reply: "
        "CARRY OUT the requested study TO THE END. Do NOT answer that it is impossible for lack of dimensioned drawings, materials or "
        "information, and ask no questions (no ask_user_choices). With attached documents: call generate_full_bet_study with ALL of "
        "them, copy the user's sentence into `hypotheses` (without drawings the server runs an INDICATIVE study on a typical model) and "
        "follow read_full_bet_study to the end. If the study fails or there are no documents: create_quote_draft with usual quantities "
        "and materials stated as assumptions. ALWAYS deliver the result (files, total) and end with two sections, in the user's "
        "language: « ✅ What is correct » (read in the documents and calculated/checked) and « ⚠️ What needs verification » (each "
        "assumption, estimated value, failed check or missing document, with what must be provided or confirmed)."
    ),
}


def directive(text: str) -> str:
    lang = detect(text)
    return _DIRECTIVE[lang] if lang else ""

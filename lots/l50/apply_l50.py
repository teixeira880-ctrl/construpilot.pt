"""Lot 50 — « fais un devis » = devis CHIFFRÉ automatiquement (FR et PT).

Avant : par défaut l'assistant ne chiffrait une ligne que si la bibliothèque de l'entreprise avait un
prix compatible ; sinon la ligne restait « à compléter » (0 €). Constaté en prod : des devis assistant
avec 76 lignes sur 82 sans prix.

Après :
  1. Consigne prioritaire ajoutée à l'assistant : chiffrage automatique PAR DÉFAUT (bibliothèque, puis
     prix moyen marché marqué « estimé, à vérifier ») ; « sans prix » seulement si l'utilisateur le demande.
  2. Filet de sécurité serveur : une ligne « library » sans correspondance est chiffrée avec le catalogue
     ConstruPilot (fourniture + pose, gamme standard) quand le métier et l'unité correspondent.
  3. S'il reste des lignes sans prix, le résultat de l'outil demande à l'assistant de les chiffrer tout de
     suite (update_quote_draft avec price_origin='estimate').

Usage : python3 lots/l50/apply_l50.py <racine /app> <fr|pt>     (idempotent ; ARRÊT si fichier absent)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
ENG = root / "backend" / "engines"
MARK = "# --- Lot 50 :"

T = {
 "fr": {
  "rule": (
   "\nRÈGLE PRIORITAIRE — CHIFFRAGE AUTOMATIQUE PAR DÉFAUT (remplace les consignes précédentes sur les prix) :\n"
   "quand l'utilisateur demande un devis (« fais un devis », « prépare le devis »…), le devis DOIT sortir chiffré,\n"
   "sans qu'il ait besoin de le préciser. Pour chaque ligne : prix fourni par l'utilisateur → price_origin='user' ;\n"
   "sinon price_origin='library' (bibliothèque + catalogue ConstruPilot côté serveur). Si le résultat de l'outil\n"
   "signale des lignes encore sans prix (action_required), rappelle IMMÉDIATEMENT update_quote_draft (après\n"
   "read_quote_draft) avec price_origin='estimate' et un unit_price HT = prix moyen du marché (pays du compte,\n"
   "fourniture + pose, année en cours ; référence web si utile). Ces prix sont marqués « estimé, à vérifier ».\n"
   "Ne laisse une ligne sans prix (price_origin='unpriced') QUE si l'utilisateur demande explicitement un devis\n"
   "sans prix. Annonce à la fin le total HT/TTC et combien de lignes sont estimées à vérifier.\n"),
  "desc": ("user = prix HT fourni par le client ; library = le serveur chiffre (bibliothèque puis catalogue ConstruPilot), "
           "unit_price=null ; estimate = prix moyen du marché HT que tu fournis (marqué « estimé, à vérifier ») — à utiliser "
           "par défaut pour toute ligne restée sans prix ; unpriced = sans prix, UNIQUEMENT sur demande explicite."),
  "label": "Prix catalogue ConstruPilot (fourniture + pose, gamme standard) — à vérifier",
  "todo": ("{n} ligne(s) encore sans prix : {ids}. Chiffre-les MAINTENANT : read_quote_draft puis update_quote_draft avec "
           "price_origin='estimate' et un unit_price HT (prix moyen du marché, fourniture + pose) pour chacune. "
           "Ne réponds pas à l'utilisateur avant que le devis soit entièrement chiffré."),
 },
 "pt": {
  "rule": (
   "\nREGRA PRIORITÁRIA — ORÇAMENTAÇÃO AUTOMÁTICA POR OMISSÃO (substitui as instruções anteriores sobre preços):\n"
   "quando o utilizador pede um orçamento («faz um orçamento», «prepara o orçamento»…), o orçamento TEM de sair\n"
   "com preços, sem que ele precise de o dizer. Para cada linha: preço fornecido pelo utilizador → price_origin='user';\n"
   "caso contrário price_origin='library' (biblioteca + catálogo ConstruPilot no servidor). Se o resultado da ferramenta\n"
   "indicar linhas ainda sem preço (action_required), chama IMEDIATAMENTE update_quote_draft (depois de\n"
   "read_quote_draft) com price_origin='estimate' e um unit_price sem IVA = preço médio de mercado (país da conta,\n"
   "fornecimento + aplicação, ano corrente; referência web se útil). Esses preços ficam marcados «estimado, a verificar».\n"
   "Só deixes uma linha sem preço (price_origin='unpriced') se o utilizador pedir explicitamente um orçamento sem\n"
   "preços. No fim anuncia o total sem IVA/com IVA e quantas linhas são estimadas a verificar.\n"),
  "desc": ("user = preço sem IVA fornecido pelo cliente; library = o servidor orçamenta (biblioteca e depois catálogo "
           "ConstruPilot), unit_price=null; estimate = preço médio de mercado sem IVA que forneces (marcado «estimado, a "
           "verificar») — a usar por omissão em qualquer linha que fique sem preço; unpriced = sem preço, SÓ a pedido explícito."),
  "label": "Preço do catálogo ConstruPilot (fornecimento + aplicação, gama standard) — a verificar",
  "todo": ("{n} linha(s) ainda sem preço: {ids}. Orçamenta-as AGORA: read_quote_draft e depois update_quote_draft com "
           "price_origin='estimate' e um unit_price sem IVA (preço médio de mercado, fornecimento + aplicação) para cada uma. "
           "Não respondas ao utilizador antes de o orçamento estar todo com preços."),
 },
}[site]

SCHEMA_ADD = f'''

{MARK} chiffrage automatique par défaut ---
QUOTE_INSTRUCTIONS = QUOTE_INSTRUCTIONS + {T["rule"]!r}
LINE_PROPERTIES["price_origin"]["description"] = {T["desc"]!r}
'''

PRICING_ADD = f'''

{MARK} filet de sécurité « catalogue ConstruPilot » ---
_CATALOG_KEYWORDS = [  # du plus spécifique au plus général ; mots sans accents, en minuscules
    ("salle_de_bain", ("salle de bain", "salle d'eau", "casa de banho", "instalacao sanitaria")),
    ("cuisine", ("cuisine", "cozinha")),
    ("menuiseries", ("fenetre", "porte-fenetre", "baie vitree", "menuiserie", "janela", "porta ", "caixilh")),
    ("ventilation", ("vmc", "ventilation", "ventilacao", "extracao")),
    ("dechets", ("dechet", "gravat", "benne", "evacuation", "entulho", "residuo")),
    ("demolition", ("demolition", "depose", "demoli", "remocao", "arrachage", "picagem")),
    ("placo", ("placo", "platre", "ba13", "cloison", "doublage", "faux plafond", "pladur", "gesso cartonado", "teto falso", "tecto falso")),
    ("isolation", ("isolation", "isolant", "laine de", "isolamento", "la de rocha", "la mineral")),
    ("peinture", ("peinture", "pintura")),
    ("carrelage", ("carrelage", "faience", "carreau", "gres cerame", "azulej", "ceramic", "porcelanico", "mosaico")),
    ("parquet", ("parquet", "sol souple", "vinyle", "stratifie", "lino", "soalho", "flutuante", "vinilico")),
    ("facade", ("facade", "ravalement", "enduit exterieur", "fachada", "capoto", "etics", "reboco exterior")),
    ("toiture", ("toiture", "couverture", "tuile", "telhado", "cobertura", "telha")),
    ("terrasse", ("terrasse", "terraco", "deck")),
    ("electricite", ("electricite", "electrique", "eletricidade", "eletrica")),
    ("plomberie", ("plomberie", "canalizacao", "canalisation")),
    ("chauffage", ("chauffage", "aquecimento")),
    ("climatisation", ("climatisation", "climatizacao", "ar condicionado")),
    ("maconnerie", ("maconnerie", "parpaing", "agglo", "alvenaria", "tijolo")),
    ("terrassement", ("terrassement", "fouille", "deblai", "escavacao", "movimento de terras")),
    ("fondations", ("fondation", "semelle", "sapata", "fundac")),
]


def _norm_txt(s):
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return " " + "".join(c for c in s if not unicodedata.combining(c)) + " "


def catalog_price(designation, unit, lot=""):
    """Prix « fourniture + pose, gamme standard » du catalogue ConstruPilot si le métier ET l'unité correspondent."""
    from engines.catalog import LOTS_BY_KEY
    text = _norm_txt(f"{{designation}} {{lot}}")
    for key, words in _CATALOG_KEYWORDS:
        if not any(w in text for w in words):
            continue
        item = LOTS_BY_KEY.get(key)
        if not item or unit_key(item.get("unit")) != unit_key(unit):
            continue
        price = round(float(item.get("mat_std", 0)) + float(item.get("labour", 0)), 2)
        if price <= 0:
            continue
        return {{"unit_price_ht": price, "price_source": "construpilot_catalog", "price_estimated": True,
                "price_missing": False, "price_reference": f"catalog:{{key}}",
                "price_reference_label": {T["label"]!r}}}
    return None


_build_lines_lot50_base = build_lines


async def build_lines(body, user, previous=None):
    lines = await _build_lines_lot50_base(body, user, previous)
    for item, row in zip(body.lines, lines):
        if item.price_origin == "library" and row.get("price_missing"):
            match = catalog_price(row.get("designation"), row.get("unit"), row.get("category", ""))
            if match:
                row.update(match)
    return lines
'''

SERVICE_ADD = f'''

{MARK} demander à l'assistant de chiffrer les lignes restées sans prix ---
_present_lot50_base = present


def present(doc):
    out = _present_lot50_base(doc)
    rows = (out.get("draft") or {{}}).get("lines") or []
    missing = [r.get("line_id") or str(i) for i, r in enumerate(rows) if r.get("price_missing")]
    if missing:
        out["action_required"] = {T["todo"]!r}.format(n=len(missing), ids=", ".join(missing[:40]))
    return out
'''

FILES = (("assistant_quote_schema.py", SCHEMA_ADD, ("QUOTE_INSTRUCTIONS =", "LINE_PROPERTIES =")),
         ("assistant_quote_pricing.py", PRICING_ADD, ("async def build_lines(", "def unit_key(", "import unicodedata")),
         ("assistant_quote_service.py", SERVICE_ADD, ("def present(doc):",)))
todo = []
for name, add, need in FILES:  # 1) tout vérifier avant d'écrire quoi que ce soit
    f = ENG / name
    if not f.exists():
        print(f"FICHIER ABSENT : {f} — ARRÊT, rien écrit")
        sys.exit(1)
    s = f.read_text(encoding="utf-8")
    for n in need:
        if n not in s:
            print(f"ANCRE introuvable dans {name} : {n!r} — ARRÊT, rien écrit")
            sys.exit(1)
    todo.append((f, s, add, name))
for f, s, add, name in todo:  # 2) écrire
    if MARK in s:
        print(f"déjà appliqué : {name}")
        continue
    f.write_text(s.rstrip("\n") + "\n" + add, encoding="utf-8")
    print(f"ok {name}")

t = pathlib.Path(__file__).resolve().parent / "tests" / "test_l50.py"
(root / "backend" / "tests" / "test_l50.py").write_bytes(t.read_bytes())
print("ok backend/tests/test_l50.py")
print(f"L50 {site.upper()} OK")

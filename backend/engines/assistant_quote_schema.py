"""Bounded quote tool contracts: the model proposes, the server persists drafts only."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuoteLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    designation: str = Field(min_length=1, max_length=500)
    line_id: str | None = Field(max_length=100)
    description: str = Field(max_length=2000)
    quantity: float | None = Field(ge=0, le=1_000_000, strict=True)
    unit: str = Field(min_length=1, max_length=12)
    unit_price: float | None = Field(ge=0, le=100_000_000, strict=True)
    price_origin: Literal["user", "library", "estimate", "unpriced"]
    vat_rate: float | None = Field(ge=0, le=100, strict=True)
    lot: str = Field(max_length=80)

    @model_validator(mode="after")
    def user_price_required(self):
        if self.price_origin in ("user", "estimate") and self.unit_price is None:
            raise ValueError("price_origin='user' ou 'estimate' exige un unit_price (montant HT), 0 si offert.")
        if self.price_origin in ("library", "unpriced") and self.unit_price is not None:
            raise ValueError("price_origin='library'/'unpriced' exige unit_price=null (le serveur chiffre depuis la bibliothèque ou laisse à compléter).")
        return self


class QuoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=160)
    client_name: str = Field(max_length=200)
    vat_rate: float | None = Field(ge=0, le=100, strict=True)
    lines: list[QuoteLineInput] = Field(min_length=1, max_length=150)
    notes: str = ""  # Jamais renseigné par l'assistant : laissé vide, à remplir manuellement par l'entreprise.


class QuoteAppendInput(BaseModel):
    """Ajout de lignes à un devis brouillon existant, sans renvoyer les lignes déjà présentes."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    vat_rate: float | None = Field(ge=0, le=100, strict=True)
    lines: list[QuoteLineInput] = Field(min_length=1, max_length=60)


LINE_PROPERTIES = {
    "line_id": {"type": ["string", "null"], "maxLength": 100, "description": "null pour nouvelle ligne ; conserver l'identifiant fourni par read_quote_draft lors d'une révision."},
    "description": {"type": "string", "maxLength": 2000, "description": "Détails, matériaux, finition et indications fournis ; conserver lors d'une révision."},
    "designation": {"type": "string", "minLength": 1, "maxLength": 500},
    "quantity": {"type": ["number", "null"], "minimum": 0, "maximum": 1000000, "description": "Quantité fournie/calculable ; null si inconnue, jamais inventée."},
    "unit": {"type": "string", "minLength": 1, "maxLength": 12},
    "unit_price": {"type": ["number", "null"], "minimum": 0, "maximum": 100000000, "description": "Prix HT. price_origin='user' : prix explicitement fourni par le client. price_origin='estimate' : prix moyen marché/web que TU fournis (sera marqué « estimé, à vérifier »). Sinon null."},
    "price_origin": {"type": "string", "enum": ["user", "library", "estimate", "unpriced"], "description": "user = prix HT fourni par le client ; library = chercher dans la bibliothèque (unit_price=null) ; estimate = prix moyen marché/web que tu fournis dans unit_price (uniquement si l'utilisateur a demandé un chiffrage automatique / prix moyen) ; unpriced = laisser sans prix (unit_price=null)."},
    "vat_rate": {"type": ["number", "null"], "minimum": 0, "maximum": 100, "description": "TVA de cette ligne si explicitement fournie ; null utilise le taux général."},
    "lot": {"type": "string", "maxLength": 80},
}
QUOTE_PROPERTIES = {
    "title": {"type": "string", "minLength": 1, "maxLength": 160},
    "client_name": {"type": "string", "maxLength": 200, "description": "Identité fournie ; vide si inconnue. Ne crée pas de fiche CRM."},
    "vat_rate": {"type": ["number", "null"], "minimum": 0, "maximum": 100, "description": "Taux général explicitement fourni, sinon null : taux standard provisoire à valider."},
    "lines": {"type": "array", "minItems": 1, "maxItems": 150, "items": {"type": "object", "properties": LINE_PROPERTIES, "required": list(LINE_PROPERTIES), "additionalProperties": False}},
}


def tool(name, description, properties):
    return {"type": "function", "name": name, "description": description, "strict": True,
            "parameters": {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}}


QUOTE_TOOLS = [
    tool("create_quote_draft", "Enregistre immédiatement un devis BROUILLON éditable dans Suivi devis (/devis). Ni e-mail, ni signature, ni facture. Prix absents : bibliothèque locale si autorisée, clairement estimés ; sinon à compléter. Renvoie doc_id et lien.", QUOTE_PROPERTIES),
    tool("find_quote_drafts", "Retrouve les devis BROUILLON existants du compte (créés par l'assistant OU manuellement dans l'éditeur /devis) afin d'en REPRENDRE un. Filtre par nom de client ou mots du titre ; query vide = les plus récents. Renvoie doc_id, titre, client, date et totaux ; enchaîner ensuite read_quote_draft puis update_quote_draft.", {"query": {"type": "string", "maxLength": 200, "description": "Nom du client ou mots du titre à rechercher ; chaîne vide pour lister les plus récents."}}),
    tool("add_quote_lines", "AJOUTE des lignes à un devis BROUILLON existant SANS renvoyer les lignes déjà présentes. À utiliser pour construire un GROS devis par étape (par étage/lot) : crée d'abord le devis avec create_quote_draft, puis ajoute chaque étage/lot avec cet outil. Les lignes existantes sont conservées. Utilise le doc_id renvoyé par create_quote_draft.", {
        "doc_id": {"type": "string"}, "vat_rate": QUOTE_PROPERTIES["vat_rate"], "lines": QUOTE_PROPERTIES["lines"]}),
    tool("read_quote_draft", "Relit la version courante d'un devis du compte avant correction, y compris les modifications manuelles. Utiliser doc_id renvoyé précédemment.", {"doc_id": {"type": "string"}}),
    tool("update_quote_draft", "Révise le MÊME devis encore en brouillon après read_quote_draft ; conserver les indications et lignes non modifiées. Jamais un document envoyé/signé. Si conflit, relire avant nouvelle tentative.", {
        "doc_id": {"type": "string"}, "expected_updated_at": {"type": "string"}, **QUOTE_PROPERTIES}),
]

QUOTE_INSTRUCTIONS = """
DEVIS PROFESSIONNEL : quand l'utilisateur demande de créer/préparer un devis, appelle create_quote_draft.
Ne rédige pas uniquement un tableau dans le chat ni un create_work_draft : le résultat doit exister dans Suivi devis.
Préserve exactement les quantités, unités, matériaux, lots, prix HT et TVA indiqués. Prix absent = null avec
price_origin=library ; ne transforme jamais une estimation du modèle en prix utilisateur. Une prestation offerte
explicitement a un prix utilisateur 0, pas un prix manquant. CHIFFRAGE AUTOMATIQUE : si l'utilisateur te demande
explicitement de chiffrer automatiquement / d'utiliser un prix moyen quand la bibliothèque n'a pas le prix, alors
pour ces lignes mets price_origin='estimate' et unit_price = le prix moyen marché/web HT que tu as trouvé (il sera
clairement marqué « estimé, à vérifier »). Dans un chiffrage automatique : 1) tente price_origin='library' (bibliothèque de l’entreprise
et catalogue partagé autorisé selon ses préférences) ; 2) si aucun prix compatible n’est disponible,
cherche une référence pertinente sur le web (search_technical_docs / search_technical_web).
Utilise price_origin='estimate' seulement avec une référence identifiable et comparable
(unité, pays, date, matériaux et pose). Sans base fiable, laisse le prix à compléter et explique le manque.
Ne fabrique jamais un prix pour remplir toutes les lignes. N'utilise JAMAIS 'estimate' sans demande explicite de l'utilisateur :
par défaut, un prix absent reste price_origin='library' (unit_price=null). quantity, unit_price et vat_rate doivent
être des NOMBRES (jamais des chaînes). Si montant TTC seulement, calcule HT uniquement avec
TVA connue ; sinon demande clarification. Les quantités inconnues restent null et sont signalées à compléter.
Ne suppose pas un taux réduit de TVA. Le serveur propose un taux standard provisoire s'il manque.
En cas de résultat ok=true, annonce le rascunho/brouillon enregistré avec son lien edit_url et tracking_url.
Ne prétends jamais avoir envoyé le devis au client. Demande explicite d'une révision du devis précédent :
read_quote_draft puis update_quote_draft, pas un nouveau devis. Utilise tool_input renvoyé, modifie seulement les
champs demandés et conserve les sources des autres prix. Les documents envoyés/signés restent intacts.
Conserve les line_id et descriptions de tool_input dans les révisions ; nouvelles lignes = line_id null.
Les actions historiques sont des traces, pas une version actuelle. Ne crée pas un devis pour une simple question
sur un devis existant, ni pour contourner une erreur de permission/conflit. Les permissions priment toujours.
REPRISE D'UN DEVIS EXISTANT non créé dans cette conversation (ex. « reprends/modifie le devis de M. X », ou un
devis fait dans l'éditeur /devis) : appelle D'ABORD find_quote_drafts (filtre par nom de client ou titre) pour obtenir
son doc_id, puis read_quote_draft et update_quote_draft. Ne crée JAMAIS un nouveau devis dans ce cas. Si
find_quote_drafts ne renvoie rien, demande le nom exact du client ou le numéro du devis.
NE RENSEIGNE JAMAIS de notes / remarques / commentaire sur le devis : ce champ reste TOUJOURS vide, à la
disposition de l'entreprise pour une saisie manuelle dans l'éditeur. N'y mets aucun texte, même un récapitulatif.
GROS DEVIS / DEVIS PAR ÉTAGE OU PAR LOT (beaucoup de lignes) : NE mets JAMAIS toutes les lignes dans un seul
create_quote_draft — un appel trop volumineux est tronqué et le devis n'est jamais enregistré. Procède par étapes :
1) create_quote_draft avec le TITRE, le client et UNIQUEMENT les lignes du PREMIER étage/lot (annonce le doc_id obtenu) ;
2) puis, pour CHAQUE étage/lot suivant, appelle add_quote_lines avec ce doc_id et SEULEMENT les nouvelles lignes
(ne répète jamais les lignes déjà enregistrées). Vise au plus ~25 lignes par appel et garde des descriptions concises.
NE T'ARRÊTE PAS après le premier étage : enchaîne IMMÉDIATEMENT les add_quote_lines pour TOUS les étages restants
dans CE MÊME tour, sans demander de confirmation ni attendre « continue ». Le devis n'est terminé que lorsque TOUS
les étages/lots annoncés y figurent. Une fois tous les étages ajoutés, annonce le brouillon complet avec son lien edit_url.
"""
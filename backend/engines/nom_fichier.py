"""Noms de fichiers lisibles pour tous les documents générés par ConstruPilot.

Règle unique : ``ConstruPilot_<Type>[_<Numéro>]_<Sujet>[_<ref>]_<AAAA-MM-JJ>.<ext>``

- ``Type``    : libellé français du document (Devis, Facture, Note-de-calcul, Metre…).
- ``Numéro``  : numéro officiel (devis / facture / avoir) — référence légale, conservé tel quel.
- ``Sujet``   : le meilleur nom humain disponible (chantier, client, plan, titre de note…).
- ``ref``     : complément court optionnel (révision, page…).
- ``date``    : date du document (défaut : aujourd'hui).

Chaque partie est réduite à de l'ASCII sûr (accents retirés, espaces → '-', seulement lettres,
chiffres et '-'), sans séparateurs doublés. Jamais d'identifiant opaque seul : à défaut de sujet,
le nom se limite au type.

``content_disposition`` produit un en-tête HTTP encodable en latin-1 avec ``filename="<ascii>"`` et
``filename*=UTF-8''<pourcent-encodé>`` (RFC 6266 / RFC 5987).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date as _date, datetime, timezone
from urllib.parse import quote

PREFIXE = "ConstruPilot"
SUJET_MAX = 60
_SPECIAUX = {"œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE", "ß": "ss", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D",
             "ł": "l", "Ł": "L", "’": "-", "'": "-", "°": "", "²": "2", "³": "3", "€": "EUR", "&": "et", "+": "-"}
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
# Identifiants techniques reconnaissables (hash, ids Mongo/uuid…) à ne jamais présenter seuls.
_OPAQUE_RE = re.compile(r"^(?:[0-9a-f]{12,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|"
                        r"[a-z]{1,8}_(?=[0-9a-f]*[a-f])[0-9a-f]{8,})$", re.I)


def ascii_texte(texte) -> str:
    """Retire accents / caractères non ASCII (œ → oe, é → e…)."""
    s = "".join(_SPECIAUX.get(c, c) for c in str(texte or ""))
    s = unicodedata.normalize("NFKD", s)
    return s.encode("ascii", "ignore").decode("ascii")


def slug(texte, max_len: int = SUJET_MAX) -> str:
    """Partie de nom de fichier : ASCII, lettres/chiffres/'-' uniquement, casse conservée."""
    s = ascii_texte(texte)
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    if max_len and len(s) > max_len:
        s = s[:max_len].rstrip("-")
        # coupe au dernier mot entier si possible (sans trop raccourcir)
        cut = s.rfind("-")
        if cut >= max_len * 0.6:
            s = s[:cut]
    return s


def est_opaque(texte) -> bool:
    """Vrai si la valeur ressemble à un identifiant technique (hash, uuid, plan_xxx…)."""
    s = str(texte or "").strip()
    stem = s.rsplit(".", 1)[0] if "." in s[-6:] else s
    return not stem or bool(_OPAQUE_RE.match(stem)) or stem.startswith("file_")


def _date_str(value) -> str:
    if value is None or value is True:
        return datetime.now(timezone.utc).date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, _date):
        return value.isoformat()
    m = _DATE_RE.match(str(value).strip())
    if m:
        return "-".join(m.groups())
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", str(value).strip())
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return datetime.now(timezone.utc).date().isoformat()


def stem_fichier(nom) -> str:
    """Nom de fichier d'origine sans extension ni chemin (``"Plan RDC.pdf"`` → ``"Plan RDC"``)."""
    s = str(nom or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if "." in s and len(s.rsplit(".", 1)[1]) <= 5:
        s = s.rsplit(".", 1)[0]
    return s


def sujet_lisible(*candidats) -> str | None:
    """Premier candidat non vide et non opaque (nom de chantier, client, nom de plan…)."""
    for c in candidats:
        if c is None:
            continue
        s = stem_fichier(c) if isinstance(c, str) and re.search(r"\.[A-Za-z0-9]{2,5}$", c.strip()) else str(c)
        if s.strip() and not est_opaque(s) and slug(s):
            return s.strip()
    return None


def nom_document(type_doc: str, sujet: str | None = None, date=None, ext: str = "pdf", ref: str | None = None,
                 numero: str | None = None) -> str:
    """``ConstruPilot_<Type>[_<numero>]_<Sujet>[_<ref>]_<AAAA-MM-JJ>.<ext>``.

    ``date=False`` omet la date. Les parties vides, opaques ou redondantes sont ignorées.
    """
    parts = [PREFIXE]
    t = slug(type_doc, 40) or "Document"
    t = t[0].upper() + t[1:]
    parts.append(t)
    seen = {t.lower()}
    for value, limit in ((numero, 40), (sujet, SUJET_MAX), (ref, 30)):
        if value is None or (value is not numero and est_opaque(value)):
            continue
        p = slug(value, limit)
        if not p or p.lower() in seen or p.lower() == PREFIXE.lower():
            continue
        if value is sujet and any(p.lower() in s for s in seen if len(p) >= 4):  # sujet déjà contenu dans le type / numéro
            continue
        parts.append(p)
        seen.add(p.lower())
    if date is not False:
        parts.append(_date_str(date))
    e = re.sub(r"[^A-Za-z0-9]", "", str(ext or "")).lower()
    return "_".join(parts) + (f".{e}" if e else "")


def nom_ascii(filename) -> str:
    """Repli ASCII sûr pour ``filename="…"`` (sans guillemets, antislash ni caractères de contrôle)."""
    s = ascii_texte(filename)
    s = re.sub(r'[\x00-\x1f\x7f"\\;/]+', "-", s).strip()
    return s or "ConstruPilot-document"


def content_disposition(filename, inline: bool = False) -> str:
    """Valeur d'en-tête ``Content-Disposition`` encodable latin-1, avec ``filename*`` UTF-8."""
    name = str(filename or "").replace("\r", " ").replace("\n", " ").strip() or "ConstruPilot-document"
    ascii_name = nom_ascii(name)
    return (f'{"inline" if inline else "attachment"}; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(name, safe='')}")


def disposition(filename, inline: bool = False, **extra) -> dict:
    """Dictionnaire d'en-têtes prêt à passer à ``Response(headers=…)``."""
    return {"Content-Disposition": content_disposition(filename, inline), **extra}


# Anciens noms génériques des artefacts de l'Assistant (stockés avant ce module, jamais migrés en base).
_ARTEFACT_GENERIQUES = ("file_", "note-de-calcul", "schema-de-principe", "coupe-verticale", "coupe-horizontale",
                        "detail-menuiserie", "corte-vertical", "corte-horizontal", "pormenor-caixilharia",
                        "compte-rendu-reunion", "etude-structure-maison", "plans-execution-mep", "document")
_ARTEFACT_TYPES = (("note-de-calcul", "Note-de-calcul"), ("schema-de-principe", "Schema-de-principe"),
                   ("coupe-verticale", "Coupe-verticale"), ("coupe-horizontale", "Coupe-horizontale"),
                   ("detail-menuiserie", "Detail-menuiserie"), ("corte-vertical", "Corte-vertical"),
                   ("corte-horizontal", "Corte-horizontal"), ("pormenor-caixilharia", "Pormenor-caixilharia"),
                   ("compte-rendu-reunion", "Compte-rendu"), ("etude-structure-maison", "Etude-structure"),
                   ("plans-execution-mep", "Plans-execution-MEP"))


def nom_artefact(doc: dict) -> str:
    """Nom lisible d'un artefact stocké : le nom enregistré s'il est déjà parlant, sinon recalculé
    à la volée (type déduit de l'ancien nom, sujet = titre, date = created_at). Aucune écriture en base."""
    stored = str(doc.get("filename") or "").strip()
    low = stored.lower()
    if stored and stored.startswith(PREFIXE + "_"):
        return stored
    if stored and not any(low.startswith(p) for p in _ARTEFACT_GENERIQUES) and not est_opaque(stored):
        return stored
    ext = (doc.get("format") or (stored.rsplit(".", 1)[1] if "." in stored else "")
           or {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}.get(doc.get("mime") or "", "pdf"))
    type_doc = next((label for prefix, label in _ARTEFACT_TYPES if low.startswith(prefix)), None)
    if not type_doc:
        type_doc = "Note-de-calcul" if doc.get("calc_note") else ("Document" if ext == "pdf" else "Illustration")
    return nom_document(type_doc, doc.get("title"), doc.get("created_at"), ext=ext)


def sujet_plan(plan: dict | None) -> str | None:
    """Nom humain d'un plan : nom affiché / fichier d'origine (sans extension), sinon nom de projet."""
    p = plan or {}
    return sujet_lisible(p.get("filename"), (p.get("cad_import") or {}).get("original_filename"),
                         p.get("original_filename"), p.get("name"), p.get("project_name"))


TYPES_PIECES = {"quote": "Orcamento", "invoice": "Fatura", "credit_note": "Nota-de-credito", "deposit_invoice": "Fatura-adiantamento",
                "situation": "Auto-de-medicao", "order": "Nota-de-encomenda"}


def nom_client(client) -> str | None:
    """Nom humain d'un client (dict ``client`` des pièces commerciales, ou chaîne)."""
    if isinstance(client, str):
        return client.strip() or None
    c = client or {}
    personne = " ".join(x for x in (c.get("first_name"), c.get("last_name")) if x)
    return sujet_lisible(c.get("company"), personne, c.get("name"))


def nom_piece(doc: dict, ext: str = "pdf", type_doc: str | None = None, suffixe: str | None = None) -> str:
    """Devis / facture / avoir : ``ConstruPilot_Facture_FAC-2026-0012_<Client>_<date>.pdf``.
    Le numéro officiel (référence légale) est conservé tel quel ; sujet = client, sinon titre du document."""
    t = type_doc or TYPES_PIECES.get(doc.get("doc_type"), "Document")
    sujet = sujet_lisible(nom_client(doc.get("client")), doc.get("client_name"), doc.get("title"), doc.get("project_name"))
    return nom_document(t, sujet, doc.get("issue_date") or doc.get("date") or doc.get("created_at"), ext=ext,
                        numero=doc.get("number"), ref=suffixe)

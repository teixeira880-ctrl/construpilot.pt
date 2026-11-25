"""Leitura dos documentos depositados pelas empresas e preenchimento automático do quadro de baixo carbono (versão PT :
DAP / EPD, fichas técnicas, guias de remessa, e-GAR, faturas de gasóleo — e também os equivalentes franceses).

Pièces reconnues : FDES (INIES / NF EN 15804), PEP ecopassport, fiche technique produit, bon / bordereau de livraison,
BSD (bordereau de suivi des déchets), facture de carburant (GNR / HVO), relevé de compteurs.

Méthode (aucune valeur inventée) :
  1. texte du document (PDF texte ; sinon OCR par l'IA de la plateforme) ;
  2. lecture DÉTERMINISTE par expressions régulières (fonctionne sans IA) ;
  3. lecture IA en JSON strict (cascade de fournisseurs de la plateforme) — chaque nombre renvoyé par l'IA doit se
     retrouver dans le texte du document, sinon il est rejeté et signalé ;
  4. rattachement à la ligne du tableau par famille de matériau, conversion d'unités kg ↔ t, contrôle des doublons de BL.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from datetime import date

from . import referentiel as R
from .calcul import _num, ligne_materiau

log = logging.getLogger("bas_carbone.documents")

TYPES = {
    "fdes": "DAP / EPD (declaração ambiental de produto)",
    "pep": "PEP ecopassport / DAP de equipamento",
    "fiche_technique": "Ficha técnica do produto",
    "bon_livraison": "Guia de remessa / transporte",
    "bsd": "e-GAR (guia de acompanhamento de resíduos)",
    "carburant": "Fatura de combustível (gasóleo / HVO)",
    "releve": "Leitura de contadores",
    "autre": "Outro documento",
}

_NUM = r"[-−]?\d{1,3}(?:[  .]\d{3})*(?:[.,]\d+)?(?:\s*[eE]\s*[-+−]?\s*\d+)?|[-−]?\d+(?:[.,]\d+)?(?:\s*[eE]\s*[-+−]?\s*\d+)?"


def nombre(s: str) -> float | None:
    """« 2,15E+02 » → 215 ; « 1 234,5 » → 1234.5 ; « -5,2e1 » → -52."""
    if s is None:
        return None
    t = str(s).strip().replace("−", "-").replace(" ", " ")
    m = re.match(r"^([-+]?[\d .]*\d(?:,\d+)?|[-+]?\d+(?:\.\d+)?)\s*(?:[eE]\s*([-+]?\s*\d+))?$", t)
    if not m:
        return _num(t)
    mant, exp = m.group(1), m.group(2)
    if "," in mant:
        mant = mant.replace(" ", "").replace(".", "").replace(",", ".")
    else:
        mant = mant.replace(" ", "")
        if mant.count(".") > 1 or re.match(r"^-?\d{1,3}(\.\d{3})+$", mant):
            mant = mant.replace(".", "")
    try:
        x = float(mant)
    except ValueError:
        return None
    if exp:
        x *= 10 ** int(exp.replace(" ", ""))
    return float(f"{x:.10g}")


# --------------------------------------------------------------------------------------------------------------------------------
def texte_pdf(data: bytes) -> tuple[str, int]:
    try:
        import pymupdf as fitz
    except Exception:  # pragma: no cover
        return "", 0
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        return "\n".join(p.get_text() for p in doc)[:120000], doc.page_count
    except Exception:  # noqa: BLE001
        return "", 0


def images_pdf(data: bytes, max_pages: int = 6) -> list[str]:
    import base64
    import pymupdf as fitz
    doc = fitz.open(stream=data, filetype="pdf")
    out = []
    for p in list(doc)[:max_pages]:
        out.append(base64.b64encode(p.get_pixmap(dpi=140).tobytes("jpeg")).decode())
    return out


def detecter_type(t: str) -> str:
    f = R.fold(t)
    if re.search(r"e-?gar\b|guia (eletronica )?de acompanhamento de residuos|codigo ler|siliamb|bordereau de suivi des dechets|\bbsd\b|trackdechets", f):
        return "bsd"
    if re.search(r"pep ecopassport|profil environnemental produit|perfil ambiental do produto", f):
        return "pep"
    if re.search(r"declaracao ambiental de produto|\bdap\b|daphabitat|environmental product declaration|\bepd\b|declaration environnementale et sanitaire|fiche de declaration environnementale|\bfdes\b|en 15804|inies", f):
        return "fdes"
    if re.search(r"guia de remessa|guia de transporte|guia de entrega|talao de pesagem|bon de livraison|bordereau de livraison|\bbl\s*n|ticket de pesee", f):
        return "bon_livraison"
    if re.search(r"gasoleo|combustivel|\bhvo\b|biocombustivel|gazole non routier|\bgnr\b|carburant", f) and re.search(r"fatura|factura|facture|litros?|litres?|\bl\b", f):
        return "carburant"
    if re.search(r"leitura.{0,20}contador|releve.{0,20}compteur", f):
        return "releve"
    if re.search(r"ficha tecnica|caracteristicas tecnicas|dados tecnicos|declaracao de desempenho|fiche technique|declaration des performances|\bdop\b", f):
        return "fiche_technique"
    return "autre"


_GWP = re.compile(r"(altera[çc][õo]es clim[áa]ticas|aquecimento global|changement climatique|r[ée]chauffement climatique|gwp)[^\n]{0,80}?total[^\n0-9\-−]{0,40}(" + _NUM + ")", re.I)
_GWP2 = re.compile(r"(altera[çc][õo]es clim[áa]ticas|aquecimento global|changement climatique|r[ée]chauffement climatique)[^\n]{0,60}\n?[^\n0-9\-−]{0,40}kg\s*(?:[ée]q\.?|eq)\s*co2[^\n0-9\-−]{0,30}(" + _NUM + ")", re.I)
_UF = re.compile(r"(?:unidade (?:funcional|declarada)|unit[ée] (?:fonctionnelle|d[ée]clar[ée]e))\s*[:\-]?\s*([^\n]{3,160})", re.I)
_INIES = re.compile(r"(?:n\.?[º°o]\s*de registo|n[úu]mero de registo|registration number|n[°o]\s*(?:d['’]\s*)?enregistrement|num[ée]ro d['’]enregistrement|r[ée]f[ée]rence inies|id inies)\s*[:\-]?\s*([A-Z0-9\-_/]{4,30})", re.I)
_VALID = re.compile(r"(?:v[áa]lid[ao] at[ée]|data de validade|fim de validade|validade\s*[:\-]|valid until|fin de validit[ée]|valable jusqu['’]au|date de validit[ée]|validit[ée]\s*[:\-])\s*[:\-]?\s*(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4}-\d{2}-\d{2})", re.I)
_DATE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b")
_BL_NUM = re.compile(r"(?:guia de remessa|guia de transporte|guia de entrega|\bGR|\bGT|bon de livraison|bordereau de livraison|\bBL)\s*(?:n\.?[º°o]|num[ée]ro)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/]{2,24})", re.I)
_ORIG = re.compile(r"(?:local de carga|morada de carga|carga|origem|expedidor|central de bet[ãa]o|pedreira|f[áa]brica|armaz[ée]m|lieu de chargement|adresse de chargement|chargement|d[ée]part|exp[ée]diteur|centrale|carri[èe]re|usine|d[ée]p[ôo]t)\s*[:\-]\s*([^\n]{6,140})", re.I)
_DIST = re.compile(r"(?:dist[âa]ncia|percurso|km percorridos|distance|parcours|km parcourus)[^\n0-9]{0,25}(\d+(?:[.,]\d+)?)\s*km", re.I)
_QTE = re.compile(r"(\d+(?:[ .]\d{3})*(?:[.,]\d+)?)\s*(m3|m³|m2|m²|ml|tonnes?|t\b|kg|u\b|un\b|unid\.?|pce|pe[çc]as?|pi[èe]ces?|unit[ée]s?|unidades?)", re.I)
_LITRES = re.compile(r"(gas[óo]leo colorido|gas[óo]leo agr[íi]cola|gas[óo]leo|gnr|gazole non routier|hvo\s*100|hvo|biocombust[íi]vel|biocarburant)[^\n]{0,60}?(\d+(?:[ .]\d{3})*(?:[.,]\d+)?)\s*(?:l\b|litros?|litres?)", re.I)
_DECHET_T = re.compile(r"(?:quantidade|peso|massa|quantit[ée]|poids|masse)[^\n0-9]{0,30}(\d+(?:[.,]\d+)?)\s*(t\b|tonnes?|kg)", re.I)
_CODE_TRAIT = re.compile(r"\b([RD])\s?(\d{1,2})\b")


def _iso(s: str | None) -> str:
    if not s:
        return ""
    s = s.strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    m = re.match(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", s)
    if not m:
        return ""
    j, mo, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
    a = a + 2000 if a < 100 else a
    try:
        return date(a, mo, j).isoformat()
    except ValueError:
        return ""


def _uf_unite(uf: str) -> str:
    m = re.search(r"\b(\d+(?:[.,]\d+)?)?\s*(m3|m³|m2|m²|ml|m\b|kg|tonnes?|t\b|unit[ée]|u\b|pi[èe]ce)", uf or "", re.I)
    return R.unite(m.group(2)) if m else ""


def lire_regles(t: str, nom: str = "") -> dict:
    """Leitura determinística (sem IA)."""
    typ = detecter_type(t + "\n" + nom)
    out: dict = {"type": typ, "famille": R.famille_de(nom + " " + t[:3000]), "lecture": "regras"}
    if typ in ("fdes", "pep", "fiche_technique"):
        tg = re.sub(r"(?i)co\s?[2₂]", "CO_", t)          # « kg CO2 éq. » : le 2 n'est pas une valeur
        m = _GWP.search(tg) or _GWP2.search(tg)
        if m:
            ligne = tg[m.start(2):].split("\n", 1)[0]
            vals = [nombre(x) for x in re.findall(_NUM, ligne)]
            vals = [v for v in vals if v is not None]
            if len(vals) == 1:
                out["fe_fdes"] = vals[0]
            elif vals:                                    # une valeur par module (A1-A3, A4, A5, B, C, D…) : le total se confirme
                out["fe_candidats"] = vals[:12]
                out["note_fe"] = "Vários valores por módulo na linha « alterações climáticas » : total do ciclo de vida a confirmar"
        uf = _UF.search(t)
        if uf:
            out["unite_fonctionnelle"] = uf.group(1).strip()
            out["fdes_unite"] = _uf_unite(uf.group(1))
        m = _INIES.search(t)
        if m:
            out["ref_fdes"] = m.group(1)
        m = _VALID.search(t)
        if m:
            out["fdes_validite"] = _iso(m.group(1))
        entete = re.compile(r"\bdap\b|\bepd\b|declara[çc][ãa]o|ficha|daphabitat|fdes|fiche|d[ée]claration|nf en|15804|pep|ecopassport|inies|p[áa]gina \d|page \d|programa|programme", re.I)
        first = next((ln.strip() for ln in t.splitlines() if len(ln.strip()) > 8 and not entete.search(ln)), "")
        out["produit"] = first[:140]
    if typ == "bon_livraison":
        m = _BL_NUM.search(t)
        out["numero"] = m.group(1) if m else ""
        m = _ORIG.search(t)
        out["origine"] = m.group(1).strip() if m else ""
        m = _DIST.search(t)
        if m:
            out["distance_km"] = nombre(m.group(1))
        q = []
        for ln in t.splitlines():
            mq = _QTE.search(ln)
            fam = R.famille_de(ln)
            if mq and fam:
                q.append({"designation": ln.strip()[:140], "quantite": nombre(mq.group(1)), "unite": R.unite(mq.group(2)), "famille": fam})
        out["quantites"] = q
    if typ == "carburant":
        gnr = hvo = 0.0
        for m in _LITRES.finditer(t):
            v = nombre(m.group(2)) or 0
            if "hvo" in m.group(1).lower() or "bio" in m.group(1).lower():
                hvo += v
            else:
                gnr += v
        out["carburant"] = {"gnr_l": gnr or None, "hvo_l": hvo or None}
    if typ == "bsd":
        m = _DECHET_T.search(t)
        tot = None
        if m:
            tot = nombre(m.group(1))
            tot = tot / 1000 if tot is not None and m.group(2).lower() == "kg" else tot
        codes = [f"{a}{b}" for a, b in _CODE_TRAIT.findall(t) if 1 <= int(b) <= 15]
        val = any(c.startswith("R") for c in codes)
        out["dechets"] = {"total_t": tot, "valorise_t": (tot if val else 0.0) if tot is not None else None, "codes": sorted(set(codes))}
    dm = _DATE.search(t)
    if dm:
        out.setdefault("date", _iso(dm.group(0)))
    return out


# --------------------------------------------------------------------------------------------------------------------------------
_SYSTEM = (
    "Lês um documento de obra (DAP/EPD, PEP, ficha técnica, guia de remessa, e-GAR, fatura de gasóleo; em português, "
    "francês ou inglês) para preencher um quadro de acompanhamento de carbono. REGRA ABSOLUTA : devolves APENAS valores "
    "escritos no documento ; se um valor não estiver lá, põe null. Não estimes nem convertas nada. Para uma DAP / PEP, "
    "fe_fdes = indicador « alterações climáticas — total » (GWP-total, kg CO2 eq.) para a unidade declarada, ciclo de vida "
    "A1 a C4 (SEM o módulo D) ; unite_fonctionnelle = texto exato. Para uma e-GAR : dechets.total_t = quantidade em toneladas, "
    "codes = operações R/D. Responde APENAS em JSON.")
_SCHEMA = ('{"type": "fdes|pep|fiche_technique|bon_livraison|bsd|carburant|releve|autre", "produit": str|null, "fabricant": str|null, '
           '"fe_fdes": number|null, "unite_fonctionnelle": str|null, "ref_fdes": str|null, "fdes_validite": "AAAA-MM-JJ"|null, '
           '"numero": str|null, "date": "AAAA-MM-JJ"|null, "fournisseur": str|null, "origine": str|null, "distance_km": number|null, '
           '"quantites": [{"designation": str, "quantite": number, "unite": str}], '
           '"dechets": {"total_t": number|null, "valorise_t": number|null, "codes": [str]}|null, '
           '"carburant": {"gnr_l": number|null, "hvo_l": number|null}|null, '
           '"typologie": "Standard|Baixo carbono|Biológico|Geológico|Reciclado|Reutilização"|null}')


def _variantes(x: float) -> set[str]:
    out = set()
    for nd in range(0, 4):
        s = f"{x:.{nd}f}"
        out |= {s, s.replace(".", ",")}
        if abs(x) >= 1000:
            ent, _, dec = s.partition(".")
            g = f"{int(float(ent)):,}".replace(",", " ")
            out |= {g + ("," + dec if dec else ""), g.replace(" ", ".") + ("," + dec if dec else "")}
    if x:
        e = math.floor(math.log10(abs(x)))
        for nd in (1, 2, 3):
            m = x / 10 ** e
            out |= {f"{m:.{nd}f}E{e:+03d}".replace(".", ","), f"{m:.{nd}f}E{e:+03d}", f"{m:.{nd}f}e{e:+03d}", f"{m:.{nd}f}E{e:+d}".replace(".", ",")}
    return out


def dans_texte(x, t: str) -> bool:
    """Le nombre lu par l'IA figure-t-il dans le document (sous une écriture courante) ?"""
    if x is None:
        return True
    try:
        x = float(x)
    except (TypeError, ValueError):
        return False
    tt = t.replace(" ", " ").replace("−", "-")
    for v in _variantes(x) | _variantes(abs(x)):
        if re.search(r"(?<![\d,.])" + re.escape(v) + r"(?![\d])", tt):
            return True
    for m in re.finditer(_NUM, tt):              # dernier recours : relire chaque nombre du texte
        y = nombre(m.group(0))
        if y is not None and abs(y - x) <= max(1e-6, abs(x) * 1e-4):
            return True
    return False


async def lire_ia(t: str, nom: str, images: list[str] | None = None) -> dict:
    from engines import ai
    prompt = f"NOM DU FICHIER : {nom}\nSCHÉMA : {_SCHEMA}\n\nTEXTE DU DOCUMENT :\n{t[:14000]}"
    raw = await ai._complete(_SYSTEM, prompt, images=images, feature="bas_carbone_doc")
    return ai._json(raw, {}) or {}


def fusionner(regles: dict, ia: dict, t: str) -> tuple[dict, list[str]]:
    """Règles d'abord pour les champs normés ; l'IA complète. Tout nombre de l'IA absent du texte est rejeté."""
    notes, out = [], dict(regles)
    for k in ("fe_fdes", "distance_km"):
        v = ia.get(k)
        if v is not None:
            if not dans_texte(v, t):
                notes.append(f"Valor IA « {k} = {v} » não encontrado no documento : rejeitado")
            elif out.get(k) is None:
                out[k] = _num(v)
            elif abs((out.get(k) or 0) - (_num(v) or 0)) > 1e-6:
                notes.append(f"{k} : leitura por regras {out.get(k)} / IA {v} — mantido o valor das regras, a verificar")
    for k in ("produit", "fabricant", "unite_fonctionnelle", "ref_fdes", "numero", "fournisseur", "origine", "typologie"):
        if ia.get(k) and not out.get(k):
            out[k] = str(ia[k])[:200]
    for k in ("fdes_validite", "date"):
        if ia.get(k) and not out.get(k):
            out[k] = _iso(str(ia[k]))
    if ia.get("type") in TYPES and out.get("type") in (None, "autre"):
        out["type"] = ia["type"]
    if out.get("unite_fonctionnelle") and not out.get("fdes_unite"):
        out["fdes_unite"] = _uf_unite(out["unite_fonctionnelle"])
    if not out.get("quantites") and isinstance(ia.get("quantites"), list):
        q = []
        for it in ia["quantites"][:60]:
            if not isinstance(it, dict) or not dans_texte(it.get("quantite"), t):
                notes.append(f"Quantidade IA « {it} » não encontrada no documento : rejeitada" if isinstance(it, dict) else "")
                continue
            fam = R.famille_de(str(it.get("designation", ""))) or out.get("famille")
            if fam:
                q.append({"designation": str(it.get("designation", ""))[:140], "quantite": _num(it.get("quantite")), "unite": R.unite(it.get("unite")), "famille": fam})
        out["quantites"] = q
    for k in ("dechets", "carburant"):
        v = ia.get(k)
        if isinstance(v, dict) and not any((out.get(k) or {}).get(kk) for kk in ("total_t", "gnr_l", "hvo_l")):
            ok = {kk: vv for kk, vv in v.items() if kk == "codes" or vv is None or dans_texte(vv, t)}
            if len(ok) < len(v):
                notes.append(f"{k} : valores IA ausentes do documento rejeitados")
            out[k] = {**(out.get(k) or {}), **ok}
    if not out.get("famille"):
        out["famille"] = R.famille_de(" ".join(str(out.get(k) or "") for k in ("produit", "unite_fonctionnelle")))
    out["lecture"] = "regras + IA" if ia else out.get("lecture", "regras")
    return out, [n for n in notes if n]


async def lire(data: bytes, nom: str, use_ai: bool = True) -> dict:
    """Lit un fichier déposé. Renvoie l'extraction (jamais d'exception : statut « illisible » au pire)."""
    low = nom.lower()
    t, pages, images = "", 0, None
    if low.endswith(".pdf") or data[:4] == b"%PDF":
        t, pages = texte_pdf(data)
        if len(t.strip()) < 120 and use_ai:
            try:
                from engines import ai
                images = images_pdf(data)
                t = await ai.ocr_pages_to_text(images)
            except Exception:  # noqa: BLE001
                log.warning("OCR bas carbone impossible", exc_info=True)
    elif low.endswith((".png", ".jpg", ".jpeg", ".webp")):
        if use_ai:
            import base64
            try:
                from engines import ai
                images = [base64.b64encode(data).decode()]
                t = await ai.ocr_pages_to_text(images)
            except Exception:  # noqa: BLE001
                log.warning("OCR image bas carbone impossible", exc_info=True)
    else:
        try:
            t = data.decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001
            t = ""
    base = {"doc_id": "doc_" + hashlib.sha256(data).hexdigest()[:20], "nom": nom[:160], "pages": pages, "taille": len(data)}
    if len(t.strip()) < 30:
        return dict(base, type="autre", type_libelle=TYPES["autre"], statut="ilegivel", extrait={}, notes=["Nenhum texto legível"])
    regles = lire_regles(t, nom)
    ia, notes = {}, []
    if use_ai:
        try:
            ia = await lire_ia(t, nom)
        except Exception as exc:  # noqa: BLE001 — l'IA ne bloque jamais : lecture par règles seule
            notes.append(f"Leitura IA indisponível ({type(exc).__name__}) : leitura apenas por regras")
    ext, n2 = fusionner(regles, ia, t)
    return dict(base, type=ext.get("type", "autre"), type_libelle=TYPES.get(ext.get("type", "autre")), statut="lido", extrait=ext,
                notes=notes + n2, apercu=t[:1500])


# --------------------------------------------------------------------------------------------------------------------------------
def _ligne(dossier: dict, code: str | None, creer: bool = True) -> dict | None:
    if not code:
        return None
    ln = next((x for x in dossier["materiaux"] if x.get("code") == code), None)
    if ln is None and creer:
        ln = ligne_materiau(code, origine="document")
        dossier["materiaux"].append(ln)
    return ln


def appliquer(dossier: dict, doc: dict, ligne_id: str | None = None) -> list[str]:
    """Reporte une pièce lue dans le dossier. ligne_id force le rattachement. Renvoie les décisions tracées."""
    dec: list[str] = []
    ext = doc.get("extrait") or {}
    typ = doc.get("type")
    did = doc["doc_id"]
    dossier.setdefault("documents", [])
    if any(x.get("doc_id") == did and x.get("rattache_a") for x in dossier["documents"]) and not ligne_id:
        return [f"« {doc.get('nom')} » já integrado (mesmo ficheiro) : ignorado para evitar dupla contagem"]
    dossier["documents"] = [x for x in dossier["documents"] if x.get("doc_id") != did]
    rec = {k: doc.get(k) for k in ("doc_id", "nom", "type", "type_libelle", "statut", "pages", "taille", "notes")}
    rec.update(extrait=ext, rattache_a=None, integre_le=date.today().isoformat(), apports=[], ligne_forcee=ligne_id)
    ap = rec["apports"]                 # ce que la pièce a changé, pour pouvoir la retirer proprement

    def tgt(code):
        if ligne_id:
            return next((x for x in dossier["materiaux"] if x["id"] == ligne_id), None)
        return _ligne(dossier, code)

    if typ in ("fdes", "pep", "fiche_technique"):
        ln = tgt(ext.get("famille"))
        if ln is not None:
            ln["pieces"] = list(dict.fromkeys((ln.get("pieces") or []) + [did]))
            fe = _num(ext.get("fe_fdes"))
            if fe is not None:
                ap.append({"ligne": ln["id"], "avant": {k: ln.get(k) for k in ("fe_fdes", "fdes_unite", "ref_fdes", "fdes_validite", "solution", "typologie")}})
                fu = ext.get("fdes_unite") or ""
                k = R.facteur_unite(fu, ln["unite"]) if fu else 1.0
                if k is None:
                    ln["fe_fdes"], ln["fdes_unite"] = fe, fu            # gardé tel quel : le contrôle MAT-07 le signale
                else:
                    ln["fe_fdes"], ln["fdes_unite"] = round(fe / k, 4), ln["unite"]
                    if k != 1.0:
                        dec.append(f"{ln['famille']} : DAP declarada por {fu}, convertida em {fe / k:g} kgCO2e/{ln['unite']}")
                ln["ref_fdes"] = ext.get("ref_fdes") or ext.get("produit") or doc.get("nom")
                ln["fdes_validite"] = ext.get("fdes_validite") or ""
                if ext.get("produit"):
                    ln["solution"] = ext["produit"][:120]
                if ext.get("typologie") in R.TYPOLOGIES_MATERIAU:
                    ln["typologie"] = ext["typologie"]
                elif ln.get("typologie") in (None, "", "Standard") and _num(ln.get("fe_ref")) is not None and ln["fe_fdes"] < _num(ln["fe_ref"]):
                    ln["typologie"] = "Baixo carbono"
                    dec.append(f"{ln['famille']} : DAP abaixo da referência → tipologia « Baixo carbono » (alterável)")
                dec.append(f"{ln['famille']} : FE da DAP {ln['fe_fdes']:g} kgCO2e/{ln['unite']} lido em « {doc.get('nom')} »")
            else:
                cand = ext.get("fe_candidats")
                dec.append(f"{ln['famille']} : « {doc.get('nom')} » associado, " + (
                    f"valores por módulo lidos ({', '.join(f'{v:g}' for v in cand)}) — introduzir o total do ciclo de vida (A1 a C4)" if cand
                    else "sem valor de carbono legível (DAP necessária)"))
            rec["rattache_a"] = ln["id"]
    elif typ == "bon_livraison":
        cle = (str(ext.get("numero") or "").upper(), str(ext.get("fournisseur") or ext.get("origine") or "").upper()[:40])
        if cle[0] and any((str((x.get("extrait") or {}).get("numero") or "").upper(),
                           str((x.get("extrait") or {}).get("fournisseur") or (x.get("extrait") or {}).get("origine") or "").upper()[:40]) == cle
                          for x in dossier["documents"] if x.get("type") == "bon_livraison"):
            rec["statut"] = "duplicado"
            rec["notes"] = (rec.get("notes") or []) + [f"Guia n.º {cle[0]} já integrada : quantidades não recontadas"]
            dossier["documents"].append(rec)
            return [f"Guia n.º {cle[0]} já integrada : não recontada"]
        touches = []
        for it in ext.get("quantites") or []:
            ln = tgt(it.get("famille"))
            q = _num(it.get("quantite"))
            if ln is None or q is None:
                continue
            k = R.facteur_unite(it.get("unite"), ln["unite"])
            if k is None:
                dec.append(f"{ln['famille']} : {q:g} {it.get('unite')} entregues não convertíveis em {ln['unite']} — a introduzir")
                continue
            ln["quantite_livree"] = round((_num(ln.get("quantite_livree")) or 0) + q * k, 3)
            ap.append({"ligne": ln["id"], "quantite_livree": q * k})
            ln["pieces"] = list(dict.fromkeys((ln.get("pieces") or []) + [did]))
            if _num(ext.get("distance_km")) is not None:       # distance = moyenne pondérée par les quantités livrées
                acc = ln.get("_dist") or [0.0, 0.0]
                acc = [acc[0] + q * k * _num(ext["distance_km"]), acc[1] + q * k]
                ln["_dist"] = acc
                ln["distance_km"], ln["distance_source"] = round(acc[0] / acc[1], 1) if acc[1] else _num(ext["distance_km"]), "média ponderada pelas quantidades entregues (guias de remessa)"
                ap.append({"ligne": ln["id"], "dist": [q * k * _num(ext["distance_km"]), q * k]})
            touches.append(ln["id"])
            dec.append(f"{ln['famille']} : +{q * k:g} {ln['unite']} entregues (« {doc.get('nom')} »)")
        rec["rattache_a"] = touches[0] if touches else None
        rec["lignes"] = touches
        ch = next((c for c in dossier["charte"] if c.get("id") == "c03"), None)
        if ch is not None and touches:
            ch["pieces"] = list(dict.fromkeys((ch.get("pieces") or []) + [did]))
    elif typ == "bsd":
        dch = dossier.setdefault("dechets", {"total_t": None, "valorise_t": None, "pieces": []})
        x = ext.get("dechets") or {}
        if _num(x.get("total_t")) is not None:
            dch["total_t"] = round((_num(dch.get("total_t")) or 0) + _num(x["total_t"]), 3)
            dch["valorise_t"] = round((_num(dch.get("valorise_t")) or 0) + (_num(x.get("valorise_t")) or 0), 3)
            ap.append({"dechets": [_num(x["total_t"]), _num(x.get("valorise_t")) or 0]})
            dec.append(f"Resíduos : +{_num(x['total_t']):g} t (operações {', '.join(x.get('codes') or []) or 'não lidas'}) — « {doc.get('nom')} »")
        dch["pieces"] = list(dict.fromkeys((dch.get("pieces") or []) + [did]))
        ch = next((c for c in dossier["charte"] if c.get("id") == "c10"), None)
        if ch is not None:
            ch["pieces"] = list(dict.fromkeys((ch.get("pieces") or []) + [did]))
        rec["rattache_a"] = "dechets"
    elif typ == "carburant":
        cb = ext.get("carburant") or {}
        for key, eid in (("gnr_l", "gnr"), ("hvo_l", "hvo")):
            v = _num(cb.get(key))
            if v:
                e = next(e for e in dossier["emissions"] if e["id"] == eid)
                e["quantite"] = round((_num(e.get("quantite")) or 0) + v, 2)
                ap.append({"emission": eid, "quantite": v})
                e["pieces"] = list(dict.fromkeys((e.get("pieces") or []) + [did]))
                dec.append(f"{e['ressource']} : +{v:g} L (« {doc.get('nom')} »)")
                rec["rattache_a"] = eid
        ch = next((c for c in dossier["charte"] if c.get("id") == "c04"), None)
        if ch is not None:
            ch["pieces"] = list(dict.fromkeys((ch.get("pieces") or []) + [did]))
    elif ligne_id:
        ln = tgt(None)
        if ln is not None:
            ln["pieces"] = list(dict.fromkeys((ln.get("pieces") or []) + [did]))
            rec["rattache_a"] = ln["id"]
    dossier["documents"].append(rec)
    dossier["decisions"] = list(dict.fromkeys((dossier.get("decisions") or []) + dec))[-200:]
    return dec


def retirer(dossier: dict, doc_id: str) -> list[str]:
    """Retire une pièce et annule exactement ce qu'elle avait apporté (quantités livrées, FE, déchets, carburants)."""
    rec = next((x for x in dossier.get("documents") or [] if x.get("doc_id") == doc_id), None)
    if rec is None:
        return []
    mats = {m["id"]: m for m in dossier["materiaux"]}
    for a in rec.get("apports") or []:
        ln = mats.get(a.get("ligne"))
        if ln is not None and "quantite_livree" in a:
            v = round((_num(ln.get("quantite_livree")) or 0) - a["quantite_livree"], 3)
            ln["quantite_livree"] = v if v > 1e-9 else None
        if ln is not None and "avant" in a:
            ln.update(a["avant"])
        if ln is not None and "dist" in a:
            acc = ln.get("_dist") or [0.0, 0.0]
            acc = [acc[0] - a["dist"][0], acc[1] - a["dist"][1]]
            if acc[1] > 1e-9:
                ln["_dist"], ln["distance_km"] = acc, round(acc[0] / acc[1], 1)
            else:
                ln["_dist"], ln["distance_km"], ln["distance_source"] = None, None, ""
        if "emission" in a:
            e = next((e for e in dossier["emissions"] if e["id"] == a["emission"]), None)
            if e is not None:
                e["quantite"] = max(0.0, round((_num(e.get("quantite")) or 0) - a["quantite"], 2))
        if "dechets" in a:
            dch = dossier.get("dechets") or {}
            t_, v_ = a["dechets"]
            dch["total_t"] = max(0.0, round((_num(dch.get("total_t")) or 0) - (t_ or 0), 3)) or None
            dch["valorise_t"] = max(0.0, round((_num(dch.get("valorise_t")) or 0) - (v_ or 0), 3)) if dch.get("total_t") else None
    for coll in (dossier["materiaux"], dossier["emissions"], dossier["charte"], [dossier.get("dechets") or {}]):
        for x in coll:
            if doc_id in (x.get("pieces") or []):
                x["pieces"] = [p for p in x["pieces"] if p != doc_id]
    dossier["documents"] = [x for x in dossier["documents"] if x.get("doc_id") != doc_id]
    return [f"Documento « {rec.get('nom')} » retirado : os seus contributos foram anulados"]


def reappliquer(dossier: dict, anciens: list[dict]) -> list[str]:
    """Après un import (étude, Excel) : ré-applique les pièces déjà déposées sur le nouveau tableau."""
    dossier["documents"] = [dict(r) for r in anciens]
    for rec in reversed(anciens):                 # annule d'abord les apports encore présents (émissions, déchets, lignes conservées)
        retirer(dossier, rec.get("doc_id"))
    dossier["documents"] = []
    dec = []
    for rec in anciens:
        doc = {k: rec.get(k) for k in ("doc_id", "nom", "type", "type_libelle", "statut", "pages", "taille", "notes")}
        doc["extrait"] = rec.get("extrait") or {}
        lid = rec.get("ligne_forcee") if any(m["id"] == rec.get("ligne_forcee") for m in dossier["materiaux"]) else None
        dec += appliquer(dossier, doc, lid)
    return dec


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance à vol d'oiseau (haversine)."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


async def completer_distances(dossier: dict, adresse_chantier: str) -> list[str]:
    """Bons de livraison avec adresse de chargement mais sans distance écrite : distance à vol d'oiseau par géocodage BAN,
    tracée comme telle (le contrôle reste visible pour faire confirmer la distance routière)."""
    from engines.urbanismo_pt.auto.geo import geocode as _geo

    async def geocode(q):
        r = await _geo(q)
        d = (r or {}).get("data") or {}
        return d if (r or {}).get("ok") and d.get("lat") is not None else None
    dec = []
    if not adresse_chantier:
        return dec
    gc = await geocode(adresse_chantier)
    if not gc:
        return dec
    for doc in dossier.get("documents") or []:
        ext = doc.get("extrait") or {}
        if doc.get("type") != "bon_livraison" or not ext.get("origine") or _num(ext.get("distance_km")) is not None:
            continue
        go = await geocode(ext["origine"])
        if not go:
            continue
        dkm = round(distance_km((gc["lat"], gc["lon"]), (go["lat"], go["lon"])), 1)
        for lid in doc.get("lignes") or []:
            ln = next((x for x in dossier["materiaux"] if x["id"] == lid), None)
            if ln is not None and _num(ln.get("distance_km")) is None:
                ln["distance_km"], ln["distance_source"] = dkm, f"em linha reta {ext['origine'][:60]} → obra (geocodificação) — a confirmar"
                dec.append(f"{ln['famille']} : distância {dkm:g} km em linha reta desde « {ext['origine'][:60]} » (a confirmar)")
    dossier["decisions"] = list(dict.fromkeys((dossier.get("decisions") or []) + dec))[-200:]
    return dec


def resume_json(doc: dict) -> str:
    return json.dumps({k: doc.get(k) for k in ("nom", "type", "statut", "extrait", "notes")}, ensure_ascii=False, default=str)[:4000]

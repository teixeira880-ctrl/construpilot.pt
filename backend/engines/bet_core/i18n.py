"""Traduction déterministe des livrables (FR → PT-PT), appliquée au moment du rendu.

Principe :
1. pré-traitement réglementaire et notations (HA10 → Ø10, e=20 → //0,20, B500B → A500NR, normes NF → NP / RTIEBT / DR 23/95) ;
2. les nombres (et les noms propres du projet protégés) sont masqués en ⟨k⟩ ;
3. le gabarit masqué est cherché dans le dictionnaire PT (phrases complètes traduites à la main) ;
4. sinon, repli sur un glossaire de termes (du plus long au plus court) — les noms de pièces, libellés
   de façades, etc. restent ainsi lisibles en portugais.
Aucun appel IA : même entrée → même sortie.
"""
from __future__ import annotations

import re

from .i18n_pt import GLOSSARY, NORMS, TEMPLATES

KEEP_NORMS = [False]               # projet français rendu en portugais : garder les normes et aciers français
NATIVE: set[str] = set()          # chaînes déjà rédigées en PT (ne pas retraduire)
PROTECTED: list[str] = []         # noms propres du projet (déjà dans la langue cible)
COLLECT: set[str] | None = None   # mode collecte des gabarits (outil de maintenance)

_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_MARK = re.compile(r"⟨(\d+)⟩")
_PROT = re.compile(r"⟪([A-Z]+)⟫")


def native(s: str) -> str:
    """Déclare une chaîne déjà rédigée en portugais."""
    NATIVE.add(s)
    return s


def protect(m) -> None:
    """Protège les noms du modèle quand le projet est déjà rédigé en portugais."""
    PROTECTED.clear()
    raw = getattr(m, "raw", m) or {}
    if (raw.get("project") or {}).get("country") != "PT":
        return
    names = set()
    for d in (raw.get("sides") or {}).values():
        names.add(d.get("label", ""))
    for lv in raw.get("levels") or []:
        names.add(lv.get("name", ""))
    for rooms in (raw.get("rooms") or {}).values():
        for r in rooms:
            names.add(r.get("name", ""))
    pr = raw.get("project") or {}
    for k in ("name", "address", "architect", "pc_ref", "g2_ref", "client"):
        names.add(str(pr.get(k, "")))
    names.add(raw.get("_comment", ""))
    geo = raw.get("geotech") or {}
    for k in ("source", "bearing_layer", "water", "soft_layer"):
        names.add(str(geo.get(k, "")))
    mep = raw.get("mep") or {}
    for st in mep.get("stacks") or []:
        names.add(st.get("serves", ""))
    for k in ("nourrice", "outdoor_tap"):
        names.add((mep.get(k) or {}).get("room", ""))
    for o in raw.get("openings") or []:
        names.add(o.get("kind", ""))
    names.add((raw.get("user_hypotheses") or {}).get("_source", ""))
    from .profiles import PT as _PTP
    for k in ("norms_text", "vat_note", "price_ref_long", "price_ref", "electrical", "plumbing", "seismic"):
        names.add(_PTP[k])
    names |= {n.upper() for n in names} | {n.lower() for n in names}
    PROTECTED.extend(sorted((n for n in names if n and len(n) > 2), key=len, reverse=True))


def _pre(s: str) -> str:
    s = re.sub(r"(\d+)\s?HA(\d+)", r"\1Ø\2", s)
    s = re.sub(r"\bHA(\d+)", r"Ø\1", s)
    s = re.sub(r"\be=(\d{2})(?!\d|[.,]\d)", r"//0,\1", s)
    s = re.sub(r"\be=(\d)(?!\d|[.,]\d)", r"//0,0\1", s)
    s = re.sub(r"\be=(\d+[.,]\d+)", r"afast. \1", s)
    if KEEP_NORMS[0]:
        return s
    s = s.replace("B500B", "A500NR")
    for fr, pt in NORMS:
        s = s.replace(fr, pt)
    s = re.sub(r"(?<!NP )(?<!NF )\bEN (199\d)", r"NP EN \1", s)
    return s


def mask(s: str) -> tuple[str, list[str], list[str]]:
    prot = []

    def _p(mo):
        prot.append(mo.group(0))
        return f"⟪{_code(len(prot) - 1)}⟫"
    for name in PROTECTED:
        if name in s:
            s = re.sub(re.escape(name), _p, s)
    vals = []

    def _n(mo):
        vals.append(mo.group(0))
        return f"⟨{len(vals) - 1}⟩"
    return _NUM.sub(_n, s), vals, prot


def _num_pt(v: str) -> str:
    return v.replace(".", ",") if v.count(".") == 1 and "," not in v else v


def _unmask(t: str, vals: list[str], prot: list[str]) -> str:
    t = _MARK.sub(lambda mo: _num_pt(vals[int(mo.group(1))]) if int(mo.group(1)) < len(vals) else "", t)
    return _PROT.sub(lambda mo: prot[_uncode(mo.group(1))] if _uncode(mo.group(1)) < len(prot) else "", t)


def _code(i: int) -> str:
    out = ""
    while True:
        out = chr(65 + i % 26) + out
        i = i // 26 - 1
        if i < 0:
            return out


def _uncode(c: str) -> int:
    n = 0
    for ch in c:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


_GLOSS_RE = None


def _glossary(s: str) -> str:
    global _GLOSS_RE
    if not GLOSSARY:
        return s
    if _GLOSS_RE is None:
        items = sorted(GLOSSARY.items(), key=lambda kv: len(kv[0]), reverse=True)
        _GLOSS_RE = (re.compile("|".join(r"(?<![\wÀ-ÿ])" + re.escape(k) + r"(?![\wÀ-ÿ])" for k, _ in items)), dict(items))
    rx, d = _GLOSS_RE
    return rx.sub(lambda mo: d[mo.group(0)], s)


def tr(s, lang: str = "fr"):
    if not isinstance(s, str) or not s:
        return s
    if lang == "collect":
        if COLLECT is not None:
            COLLECT.add(mask(_pre(s))[0])
        return s
    if lang != "pt" or s in NATIVE:
        return s
    s1 = _pre(s)
    masked, vals, prot = mask(s1)
    if COLLECT is not None and masked not in TEMPLATES:
        COLLECT.add(masked)
    if masked in TEMPLATES:
        return _unmask(TEMPLATES[masked], vals, prot)
    # repli : glossaire sur la chaîne masquée (protège les noms propres), puis démasquage
    return _unmask(_glossary(masked), vals, prot)

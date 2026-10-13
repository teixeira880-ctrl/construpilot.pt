"""Brand detection in AI answers: mention (word-boundary variants), domain citation, explicit recommendation, rank in ordered lists. Each detection carries a text proof."""
import re
from urllib.parse import urlparse

RECO_PATTERNS = {
    "fr": [r"\b(je (vous )?(recommande|conseille)|nous (recommandons|conseillons)|meilleur choix|option recommandée|à privilégier|le plus adapté)\b"],
    "pt": [r"\b(recomend(o|amos|ado|ada)|aconselh(o|amos)|melhor (opção|escolha)|a privilegiar|o mais adequado)\b"],
}
GENERIC_EXCLUDE = re.compile(r"\b(construction|pilotage|pilote|construir|piloto)\b", re.IGNORECASE)


def _variant_regex(v: str) -> re.Pattern:
    return re.compile(r"(?<![\w-])" + re.escape(v).replace(r"\ ", r"\s?") + r"(?![\w-])", re.IGNORECASE)


def _snippet(text: str, start: int, end: int, width: int = 90) -> str:
    a, b = max(0, start - width), min(len(text), end + width)
    return ("…" if a > 0 else "") + text[a:b].replace("\n", " ") + ("…" if b < len(text) else "")


def _ordered_items(text: str) -> list[str]:
    items = []
    for line in text.splitlines():
        m = re.match(r"^\s*(\d{1,2})[.)]\s+(.*)", line)
        if m:
            items.append(m.group(2))
    return items


def detect(text: str, citations: list[dict], brands: list[dict], lang: str) -> list[dict]:
    """One entry per (brand) actually found; repeated mentions count once. `rank` is None when not in an ordered list."""
    out = []
    ordered = _ordered_items(text or "")
    for b in brands:
        found = None
        for v in b.get("variants") or [b["name"]]:
            m = _variant_regex(v).search(text or "")
            if m:
                found = m
                break
        domain_cite = next((c for c in citations if (urlparse(c.get("url") or "").hostname or "").lower().removeprefix("www.") in {d.lower() for d in b.get("domains") or []}), None)
        domain_in_text = next((d for d in b.get("domains") or [] if re.search(re.escape(d), text or "", re.IGNORECASE)), None)
        if not found and not domain_cite and not domain_in_text:
            continue
        entry = {"brand_id": b["brand_id"], "name": b["name"], "is_self": bool(b.get("is_self")), "mention": bool(found), "domain_citation": bool(domain_cite),
                 "domain_in_text": bool(domain_in_text), "recommendation": False, "rank": None, "evidence": "", "false_positive": False}
        if found:
            entry["evidence"] = _snippet(text, found.start(), found.end())
            window = text[max(0, found.start() - 160): found.end() + 160]
            entry["recommendation"] = any(re.search(p, window, re.IGNORECASE) for p in RECO_PATTERNS.get(lang, RECO_PATTERNS["fr"]))
            for i, item in enumerate(ordered, 1):
                if _variant_regex(b["name"]).search(item):
                    entry["rank"] = i
                    break
        elif domain_cite:
            entry["evidence"] = f"Citation de {domain_cite.get('url')}"
        else:
            entry["evidence"] = f"Domaine {domain_in_text} présent dans le texte"
        out.append(entry)
    return out

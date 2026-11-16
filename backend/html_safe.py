"""Sanitização de HTML partilhada (blog HeyCatch, AutoSEO, BabyLoveGrowth, painel CEO, e-mails).

Lista branca de etiquetas e atributos ; remove scripts, iframes, atributos on*, URLs javascript:/vbscript:/data:.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

ALLOWED = {"h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "ul", "ol", "li", "table", "thead", "tbody", "tfoot", "tr", "th",
           "td", "caption", "a", "blockquote", "strong", "b", "em", "i", "u", "s", "code", "pre", "sup", "sub", "span", "div",
           "section", "aside", "figure", "figcaption", "img", "details", "summary", "dl", "dt", "dd", "mark", "small", "abbr"}
DROP = {"script", "style", "iframe", "object", "embed", "noscript", "template", "form", "input", "button", "link", "meta",
        "svg", "math", "frame", "frameset", "base"}
ATTRS = {"href", "title", "id", "class", "src", "alt", "width", "height", "colspan", "rowspan", "scope", "start", "rel",
         "target", "loading", "open"}
_BAD_URL = re.compile(r"^\s*(javascript|vbscript|data):", re.I)


def sanitize_html(html: str) -> str:
    """Mantém títulos, parágrafos, listas, tabelas, ligações, citações, ênfases, código e o id dos h2."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.find_all(DROP):
        tag.decompose()
    for tag in soup.find_all("h1"):     # o título do artigo (já mostrado) é o único <h1> da página
        tag.decompose()
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED:
            tag.unwrap()
            continue
        for attr in list(tag.attrs):
            val = tag.attrs[attr]
            sval = " ".join(val) if isinstance(val, list) else str(val)
            if attr.lower().startswith("on") or attr not in ATTRS or (attr in ("href", "src") and _BAD_URL.match(sval)):
                del tag.attrs[attr]
        if tag.name == "a" and tag.get("href", "").startswith("http") and "construpilot.pt" not in tag.get("href", ""):
            tag["rel"] = "noopener noreferrer"
            tag["target"] = "_blank"
    return str(soup)

"""Identité visuelle des livrables : entreprise utilisatrice (logo, nom, coordonnées, couleur) + polices premium.

Le dossier est édité AU NOM de l'entreprise cliente de ConstruPilot (logo et coordonnées tirés de son
« branding » ConstruPilot) ; ConstruPilot n'apparaît qu'en mention discrète « étude réalisée avec ConstruPilot ».
Polices embarquées (licence SIL OFL, dossier fonts/) : Inter (texte) et Barlow Semi Condensed (titres).
"""
from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONTS = Path(__file__).with_name("fonts")
_REG = {"DV": "Inter_400Regular.ttf", "DVB": "Inter_600SemiBold.ttf", "DVL": "Inter_300Light.ttf",
        "DVM": "Inter_500Medium.ttf", "DVX": "Inter_700Bold.ttf",
        "TT": "BarlowSemiCondensed_700Bold.ttf", "TTS": "BarlowSemiCondensed_600SemiBold.ttf"}
for _name, _file in _REG.items():
    try:
        pdfmetrics.registerFont(TTFont(_name, str(FONTS / _file)))
    except Exception:  # noqa: BLE001 — repli DejaVu si une police manque
        _dj = "/usr/share/fonts/truetype/dejavu/DejaVuSans" + ("-Bold" if _name in ("DVB", "DVX", "TT", "TTS") else "") + ".ttf"
        pdfmetrics.registerFont(TTFont(_name, _dj))


def _hex(h: str | None, default: str) -> colors.Color:
    h = (h or default).strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        h = default.lstrip("#")
    return colors.Color(int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)


def _mix(c: colors.Color, k: float) -> colors.Color:
    """Éclaircit vers le blanc (k = 0 → couleur, 1 → blanc)."""
    return colors.Color(c.red + (1 - c.red) * k, c.green + (1 - c.green) * k, c.blue + (1 - c.blue) * k)


@dataclass
class Brand:
    name: str = "ConstruPilot"
    lines: list[str] = field(default_factory=list)       # adresse, contacts
    legal: str = ""                                      # mention légale pied de page
    accent: colors.Color = field(default_factory=lambda: _hex(None, "#14365C"))
    accent2: colors.Color = field(default_factory=lambda: _hex(None, "#B87333"))
    logo: ImageReader | None = None
    logo_ratio: float = 1.0                              # largeur / hauteur
    logo_hex: str | None = None                          # pour openpyxl
    logo_bytes: bytes | None = None
    is_client: bool = False

    @property
    def tint(self):
        return _mix(self.accent, 0.90)

    @property
    def tint2(self):
        return _mix(self.accent, 0.96)

    @property
    def hex(self) -> str:
        a = self.accent
        return "%02X%02X%02X" % (round(a.red * 255), round(a.green * 255), round(a.blue * 255))


def from_branding(b: dict | None) -> Brand:
    """b = branding ConstruPilot de l'entreprise (company_name, contact_line, address, postal, city, siret, vat, nif,
    company_email, phone, accent_color, accent2_color, logo_b64, footer_text)."""
    if not b or not (b.get("company_name") or b.get("logo_b64")):
        return Brand()
    lines = []
    addr = " ".join(x for x in (b.get("address"), b.get("postal") or b.get("postal_code"), b.get("city")) if x)
    for x in (b.get("contact_line"), addr, " · ".join(y for y in (b.get("phone"), b.get("company_email")) if y)):
        if x and x not in lines:
            lines.append(str(x))
    ids = " · ".join(f"{k} {b[f]}" for k, f in (("SIRET", "siret"), ("TVA", "vat"), ("NIF", "nif"), ("Alvará", "alvara")) if b.get(f))
    if ids:
        lines.append(ids)
    br = Brand(name=b.get("company_name") or "", lines=lines[:4], legal=(b.get("footer_text") or "")[:220],
               accent=_hex(b.get("accent_color"), "#14365C"), accent2=_hex(b.get("accent2_color"), "#B87333"), is_client=True)
    if b.get("logo_b64"):
        try:
            raw = base64.b64decode(re.sub(r"^data:image/[a-z+]+;base64,", "", b["logo_b64"]))
            from PIL import Image
            im = Image.open(io.BytesIO(raw))
            im.load()
            if im.mode in ("P", "LA") or (im.mode == "RGBA"):
                im = im.convert("RGBA")
            buf = io.BytesIO()
            im.save(buf, "PNG")
            br.logo_bytes = buf.getvalue()
            br.logo = ImageReader(io.BytesIO(br.logo_bytes))
            br.logo_ratio = im.width / max(im.height, 1)
        except Exception:  # noqa: BLE001 — logo illisible : repli sur le nom en toutes lettres
            br.logo = None
    return br


CURRENT: list[Brand] = [Brand()]


def use(b: dict | Brand | None) -> Brand:
    CURRENT[0] = b if isinstance(b, Brand) else from_branding(b)
    return CURRENT[0]


def get() -> Brand:
    return CURRENT[0]


def draw_logo(c, x: float, y: float, w: float, h: float, br: Brand | None = None, on_dark: bool = False, align: str = "l"):
    """Logo ajusté dans la boîte (x, y, w, h) en points ; sinon nom de l'entreprise en lettrage."""
    br = br or get()
    if br.logo is not None:
        lw, lh = (h * br.logo_ratio, h) if h * br.logo_ratio <= w else (w, w / br.logo_ratio)
        lx = x if align == "l" else (x + (w - lw) / 2 if align == "c" else x + w - lw)
        c.drawImage(br.logo, lx, y + (h - lh) / 2, lw, lh, mask="auto", preserveAspectRatio=True)
        return
    name = (br.name or "ConstruPilot").upper()
    size = min(h * 0.62, 26)
    while size > 6 and pdfmetrics.stringWidth(name, "TT", size) > w:
        size -= 0.5
    c.setFillColor(colors.white if on_dark else br.accent)
    c.setFont("TT", size)
    tw = pdfmetrics.stringWidth(name, "TT", size)
    lx = x if align == "l" else (x + (w - tw) / 2 if align == "c" else x + w - tw)
    c.drawString(lx, y + (h - size * 0.72) / 2, name)
    c.setFillColor(br.accent2)
    c.rect(lx, y + (h - size * 0.72) / 2 - size * 0.22, min(tw, size * 2.2), size * 0.08, stroke=0, fill=1)

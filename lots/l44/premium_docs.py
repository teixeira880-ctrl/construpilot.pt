"""Documents commerciaux haut de gamme ConstruPilot (présentations et plaquettes, FR / PT / EN).

Fichiers figés, validés par la direction (prix alignés sur le pitch publié : Gratuit 0 €, Premium 19 €,
Pro 149 € HT, Pro Business 249 € HT, options et API). Servis par /api/brochures/* à la place des
documents générés quand il n'y a pas d'en-tête d'entreprise cliente à appliquer.
"""
from pathlib import Path

from fastapi.responses import Response

BASE = Path(__file__).resolve().parent.parent / "assets" / "premium_docs"
MIME = {"pdf": "application/pdf",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}
DOWNLOAD = {
    "fr": {"investor": "ConstruPilot_Presentation-investisseurs_FR", "client": "ConstruPilot_Presentation-commerciale_FR", "plaquette": "ConstruPilot_Plaquette_FR"},
    "pt": {"investor": "ConstruPilot_Apresentacao-investidores_PT", "client": "ConstruPilot_Apresentacao-comercial_PT", "plaquette": "ConstruPilot_Brochura_PT"},
    "en": {"investor": "ConstruPilot_Investor-presentation_EN", "client": "ConstruPilot_Sales-presentation_EN", "plaquette": "ConstruPilot_Brochure_EN"},
}


def _path(kind: str, lang: str, ext: str) -> Path:
    return BASE / lang / f"{kind}.{ext}"


def available(kind: str, lang: str, ext: str) -> bool:
    return lang in DOWNLOAD and kind in DOWNLOAD[lang] and ext in MIME and _path(kind, lang, ext).is_file()


def response(kind: str, lang: str, ext: str) -> Response:
    name = f"{DOWNLOAD[lang][kind]}.{ext}"
    return Response(content=_path(kind, lang, ext).read_bytes(), media_type=MIME[ext],
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, max-age=300"})

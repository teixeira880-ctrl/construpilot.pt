"""Published investor deck: original user PPTX and its pre-rendered derivatives.

Assets ship with the application; no conversion service or writable cache is
required at runtime. See assets/investors/README.md for provenance.
"""

import json
from pathlib import Path

from fastapi.responses import FileResponse

DECK_ROOT = Path(__file__).resolve().parents[1] / "assets" / "investors"
DECK_LANGS = ("pt", "fr", "en")
DECK_MANIFESTS = {
    lang: json.loads((DECK_ROOT / lang / "manifest.json").read_text(encoding="utf-8"))
    for lang in DECK_LANGS
}
# Retrocompatibilidade: o deck português é a versão por defeito no .pt.
DECK_ASSETS = DECK_ROOT / "pt"
DECK_MANIFEST = DECK_MANIFESTS["pt"]


def build_pitch_deck_pdf() -> bytes:
    """Compatibility entry point: never regenerate the obsolete investor deck."""
    return (DECK_ASSETS / "ConstruPilot_PitchDeck.pdf").read_bytes()


def deck_asset_response(filename: str, media_type: str, *, inline: bool = True, lang: str = "pt"):
    """Only serve a caller-selected entry from the published asset manifest."""
    asset = DECK_MANIFESTS[lang]["files"][filename]
    return FileResponse(
        DECK_ROOT / lang / filename,
        media_type=media_type,
        filename=Path(filename).name,
        content_disposition_type="inline" if inline else "attachment",
        headers={
            "Cache-Control": "no-cache, must-revalidate",
            "ETag": f'"{asset["sha256"]}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
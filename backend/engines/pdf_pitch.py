"""Published investor deck: original user PPTX and its pre-rendered derivatives.

Assets ship with the application; no conversion service or writable cache is
required at runtime. See assets/investors/README.md for provenance.
"""

import json
from pathlib import Path

from fastapi.responses import FileResponse

DECK_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "investors"
DECK_MANIFEST = json.loads((DECK_ASSETS / "manifest.json").read_text(encoding="utf-8"))


def build_pitch_deck_pdf() -> bytes:
    """Compatibility entry point: never regenerate the obsolete investor deck."""
    return (DECK_ASSETS / "ConstruPilot_PitchDeck.pdf").read_bytes()


def deck_asset_response(filename: str, media_type: str, *, inline: bool = True):
    """Only serve a caller-selected entry from the published asset manifest."""
    asset = DECK_MANIFEST["files"][filename]
    return FileResponse(
        DECK_ASSETS / filename,
        media_type=media_type,
        filename=Path(filename).name,
        content_disposition_type="inline" if inline else "attachment",
        headers={
            "Cache-Control": "no-cache, must-revalidate",
            "ETag": f'"{asset["sha256"]}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
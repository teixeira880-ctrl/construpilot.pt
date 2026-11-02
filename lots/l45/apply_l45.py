"""Lote 45 PT — pitch deck investidores v3 em PT / FR / EN com seletor de língua (PT por defeito).

Uso: python3 apply_l45.py /app /tmp/l45/lots/l45
Copia os decks para backend/assets/investors/{pt,fr,en} e aplica patches com âncoras exatas.
Pára (exit 1) se alguma âncora faltar, sem escrever nada.
"""
import shutil, sys
from pathlib import Path

APP, LOT = Path(sys.argv[1]), Path(sys.argv[2])
P = {
 "backend/engines/pdf_pitch.py": [
  ('''DECK_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "investors"
DECK_MANIFEST = json.loads((DECK_ASSETS / "manifest.json").read_text(encoding="utf-8"))
''', '''DECK_ROOT = Path(__file__).resolve().parents[1] / "assets" / "investors"
DECK_LANGS = ("pt", "fr", "en")
DECK_MANIFESTS = {
    lang: json.loads((DECK_ROOT / lang / "manifest.json").read_text(encoding="utf-8"))
    for lang in DECK_LANGS
}
# Retrocompatibilidade: o deck português é a versão por defeito no .pt.
DECK_ASSETS = DECK_ROOT / "pt"
DECK_MANIFEST = DECK_MANIFESTS["pt"]
'''),
  ('''def deck_asset_response(filename: str, media_type: str, *, inline: bool = True):
    """Only serve a caller-selected entry from the published asset manifest."""
    asset = DECK_MANIFEST["files"][filename]
    return FileResponse(
        DECK_ASSETS / filename,''', '''def deck_asset_response(filename: str, media_type: str, *, inline: bool = True, lang: str = "pt"):
    """Only serve a caller-selected entry from the published asset manifest."""
    asset = DECK_MANIFESTS[lang]["files"][filename]
    return FileResponse(
        DECK_ROOT / lang / filename,'''),
 ],
 "backend/routes/investors.py": [
  ("from engines.pdf_pitch import DECK_MANIFEST, deck_asset_response", "from engines.pdf_pitch import DECK_MANIFESTS, deck_asset_response"),
  ("from fastapi import APIRouter, Depends, Path, Request", "from typing import Literal\n\nfrom fastapi import APIRouter, Depends, Path, Request\nfrom fastapi.exceptions import RequestValidationError"),
  ('''@router.api_route("/pitch-deck.pdf", methods=["GET", "HEAD"])
async def pitch_deck_pdf():''', '''DeckLang = Literal["pt", "fr", "en"]


@router.api_route("/pitch-deck.pdf", methods=["GET", "HEAD"])
async def pitch_deck_pdf(lang: DeckLang = "pt"):'''),
  ('''    return deck_asset_response("ConstruPilot_PitchDeck.pdf", "application/pdf")''', '''    return deck_asset_response("ConstruPilot_PitchDeck.pdf", "application/pdf", lang=lang)'''),
  ('''async def pitch_deck_powerpoint():''', '''async def pitch_deck_powerpoint(lang: DeckLang = "pt"):'''),
  ('''        inline=False,
    )''', '''        inline=False, lang=lang,
    )'''),
  ('''class DeckInfo(BaseModel):
    source_filename: str''', '''class DeckInfo(BaseModel):
    lang: str
    source_filename: str'''),
  ('''async def pitch_deck_info():
    return DeckInfo(**{key: DECK_MANIFEST[key] for key in DeckInfo.model_fields})''', '''async def pitch_deck_info(lang: DeckLang = "pt"):
    return DeckInfo(**{key: DECK_MANIFESTS[lang][key] for key in DeckInfo.model_fields})'''),
  ('''async def pitch_deck_slide(page: int = Path(ge=1, le=DECK_MANIFEST["page_count"])):
    return deck_asset_response(f"slides/{page}.webp", "image/webp")''', '''async def pitch_deck_slide(page: int = Path(ge=1), lang: DeckLang = "pt"):
    if page > DECK_MANIFESTS[lang]["page_count"]:
        raise RequestValidationError([{"loc": ("path", "page"), "msg": "page out of range", "type": "value_error"}])
    return deck_asset_response(f"slides/{page}.webp", "image/webp", lang=lang)'''),
 ],
 "frontend/src/lib/pitchDeck.js": [
  ('''export const deckFileUrl = (format = "pdf") => `${DECK_BASE}.${format}`;
export const deckSlideUrl = (page, version) => `${DECK_BASE}/slides/${page}.webp?v=${version}`;''', '''export const DECK_LANGS = [
  { code: "pt", label: "PT" },
  { code: "fr", label: "FR" },
  { code: "en", label: "EN" },
];

export const deckFileUrl = (format = "pdf", lang = "pt") => `${DECK_BASE}.${format}?lang=${lang}`;
export const deckSlideUrl = (page, version, lang = "pt") => `${DECK_BASE}/slides/${page}.webp?lang=${lang}&v=${version}`;'''),
 ],
 "frontend/src/components/investors/PitchDeckPreview.jsx": [
  ('import { deckSlideUrl } from "@/lib/pitchDeck";', 'import { DECK_LANGS, deckSlideUrl } from "@/lib/pitchDeck";'),
  ('export const PitchDeckPreview = ({ onDownload }) => {', 'export const PitchDeckPreview = ({ onDownload, lang = "pt", onLangChange }) => {'),
  ('''    api.get("/investors/pitch-deck").then(({ data }) => {
      if (active) setInfo(data);''', '''    setInfo(null);
    api.get("/investors/pitch-deck", { params: { lang } }).then(({ data }) => {
      if (active) { setInfo(data); setPage((p) => Math.min(p, data.page_count)); setImageState("loading"); }'''),
  ('  }, [attempt]);', '  }, [attempt, lang]);'),
  ('deckSlideUrl(page, `${info.source_sha256}-${attempt}`)', 'deckSlideUrl(page, `${info.source_sha256}-${attempt}`, lang)'),
  ('''          <div className="flex flex-wrap gap-2">
            {["pdf", "pptx"]''', '''          <div className="flex flex-wrap gap-2">
            <div role="group" aria-label="Língua do pitch deck" className="inline-flex rounded-full border border-border p-0.5" data-testid="pitch-deck-lang">
              {DECK_LANGS.map(({ code, label }) => (
                <button key={code} type="button" aria-pressed={lang === code} data-testid={`pitch-deck-lang-${code}`}
                  onClick={() => onLangChange?.(code)}
                  className={`px-3 py-1 text-xs font-semibold rounded-full transition-colors ${lang === code ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
                  {label}
                </button>
              ))}
            </div>
            {["pdf", "pptx"]'''),
 ],
 "frontend/src/components/investors/DeckDownloadDialog.jsx": [
  ('({ open, onOpenChange, format })', '({ open, onOpenChange, format, lang = "pt" })'),
  ('const url = deckFileUrl(format);', 'const url = deckFileUrl(format, lang);'),
  ('{label} — ConstruPilot', '{label} ({lang.toUpperCase()}) — ConstruPilot'),
 ],
 "frontend/src/pages/Investors.jsx": [
  ('  const [deckFormat, setDeckFormat] = useState("pdf");', '  const [deckFormat, setDeckFormat] = useState("pdf");\n  const [deckLang, setDeckLang] = useState("pt");'),
  ('<DeckDownloadDialog open={deckOpen} onOpenChange={setDeckOpen} format={deckFormat} />', '<DeckDownloadDialog open={deckOpen} onOpenChange={setDeckOpen} format={deckFormat} lang={deckLang} />'),
  ('<PitchDeckPreview onDownload={openDeck} />', '<PitchDeckPreview onDownload={openDeck} lang={deckLang} onLangChange={setDeckLang} />'),
 ],
}
out = {}
for rel, reps in P.items():
    s = (APP / rel).read_text(encoding="utf-8")
    for old, new in reps:
        if s.count(old) != 1:
            print(f"L45 ANCORA EM FALTA: {rel} :: {old[:70]!r} (ocorrências={s.count(old)})"); sys.exit(1)
        s = s.replace(old, new)
    out[rel] = s
dst = APP / "backend/assets/investors"
for lang in ("pt", "fr", "en"):
    shutil.rmtree(dst / lang, ignore_errors=True)
    shutil.copytree(LOT / "assets" / lang, dst / lang)
for rel, s in out.items():
    (APP / rel).write_text(s, encoding="utf-8")
print(f"L45 OK ({sum(len(r) for r in P.values())} patches, 3 decks x 12 diapositivos)")

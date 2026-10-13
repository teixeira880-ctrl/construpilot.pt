# Published ConstruPilot pitch deck

User request: «change le pitch deck dans le site et dans la page investisseur».
Confirmed replacement of all presentation/download links, including the PDF
preview, without rewriting the rest of the investor page.

- Published: 2026-09-14.
- Source: `ConstruPilot_PitchDeck.pptx`, supplied by the user; **unmodified**.
- SHA-256: `81274306e33f55fa7e3577b71eabcbac66290de648577cda4171b4c9cc60f7c9`.
- Source contains **19** slides, widescreen 16:9 (12192000 × 6858000 EMU).
- `ConstruPilot_PitchDeck.pdf`: one-time LibreOffice Impress 7.4 conversion.
  Aptos installed locally from Microsoft's official font distribution; Calibri
  rendered with its metric-compatible Carlito substitute. Font binaries are not
  shipped as web fonts or included in this repository.
- `slides/1.webp` … `slides/19.webp`: 1920 × 1080 previews from that PDF,
  rendered with PyMuPDF, resampled to exactly 1920 × 1080 with Lanczos (the PDF
  page is fractionally wider than 960 pt), and encoded as WebP quality 90.
  Content is not rewritten.
- `manifest.json`: page count, original hash, and hashes/sizes of all 21 assets.

These small, curated, public brand assets ship with the backend source. Serving
does not depend on the uploaded URL, `/tmp`, LibreOffice, or fonts at runtime.
No new upload/storage integration, account, secret, or external service added.

Routes: `/api/investors/pitch-deck.pdf` (legacy URL preserved),
`/api/investors/pitch-deck.pptx`, `/api/investors/pitch-deck`, and
`/api/investors/pitch-deck/slides/{page}.webp`.
Only manifest entries are served. No arbitrary filenames/paths are accepted.
Source claims/pricing are user-authored, not independently certified or applied
to billing/product configuration by this replacement.
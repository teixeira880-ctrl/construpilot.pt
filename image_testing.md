# Assistant162 image flows
- Real PNG/JPEG/WEBP only, validate decoded bytes (not filename/MIME), maximum20MB/40MP.
- Reject animation/corruption/blank or uniform photos. Normalize EXIF orientation and strip metadata.
- Store private normalized sources and replay real bounded2200px high-detail visuals on each active-context turn.
- Preview/download require ownership and authentication; never use public uploads or arbitrary fetched URLs.
- GPT-Image1 via existing user OpenAI key generates illustrations only on explicit request; offload its blocking wrapper from APIeventloop. Result is JPEG with a visible non-contractual AI watermark.
- Tests: nonblank distinct real fixture, wrongMIME/content, EXIForientation, PDF/imagezoom, multi-turn visualreplay, mobilecontain, owner isolation, backgroundnavigation/reload/queue/cancel, PDF/JPGdownload bytes.
- Paid acceptance budget: up to3normal chatturns +1generated image for this feature, unless main agent approves extra; use fixtures elsewhere and label TEST-ONLY MOCKS. No email, postal send, checkout or account creation.
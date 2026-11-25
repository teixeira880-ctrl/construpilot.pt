# Backend ConstruPilot (FastAPI) — imagem portátil ARM64 (Oracle Ampere, Hetzner CAX) e x86_64.
# Construir a partir da raiz do repositório:  docker build -f infra/backend.Dockerfile -t construpilot-backend .
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# Bibliotecas do sistema usadas pelos motores:
#  - pango/harfbuzz/fontes: WeasyPrint (PDF HTML) e ReportLab
#  - tesseract (por, fra, eng): OCR (pytesseract)
#  - ffmpeg: transcrição de vídeo / visita vídeo
#  - libllvm: variante LLVM do Mitsuba/Dr.Jit (renders 3D dos dossiers)
#  - libgl/glib: OpenCV headless, PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 libharfbuzz0b libfontconfig1 \
      fonts-dejavu-core fonts-liberation \
      tesseract-ocr tesseract-ocr-por tesseract-ocr-fra tesseract-ocr-eng \
      ffmpeg libllvm15 libglib2.0-0 libgl1 curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements-prod.txt /tmp/requirements-prod.txt
RUN pip install -r /tmp/requirements-prod.txt \
 && pip install "emergentintegrations==0.2.0" --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/

COPY backend/ /app/backend/
COPY scripts/infra/ /app/scripts_infra/
COPY infra/backend-entrypoint.sh /usr/local/bin/backend-entrypoint.sh
RUN chmod +x /usr/local/bin/backend-entrypoint.sh \
 && useradd --system --uid 10001 --home /app app && mkdir -p /app/data && chown -R app /app
USER app

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8001/api/health || exit 1
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/backend-entrypoint.sh"]

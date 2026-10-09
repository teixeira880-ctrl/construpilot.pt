#!/usr/bin/env bash
# Instala as dependências de sistema necessárias ao backend ConstruPilot.
#
# Correr após qualquer reset do pod/container (ex.: upgrade de nó K8s)
# para garantir que o Tesseract-PT está disponível. Idempotente: pode
# ser executado várias vezes sem efeitos colaterais.
#
# Uso:
#   bash /app/scripts/install_system_deps.sh
#
# Dependências instaladas:
#   - tesseract-ocr      (motor OCR usado por engines/plans_pro/semantic/ocr_tesseract.py)
#   - tesseract-ocr-por  (modelo linguístico Português — obrigatório PT-PT)
set -euo pipefail

echo "[install_system_deps] A actualizar índices apt..."
apt-get update -qq

echo "[install_system_deps] A instalar tesseract-ocr + modelo PT..."
apt-get install -y --no-install-recommends \
  tesseract-ocr \
  tesseract-ocr-por

echo "[install_system_deps] Verificação:"
which tesseract
tesseract --list-langs 2>&1 | grep -E "^(eng|por|osd)$" || true

echo "[install_system_deps] OK."

"""Detecção fail-closed do ambiente (produção / dev / preview).

**Fonte única** sobre `ENV`. Nenhum outro ficheiro do backend deve ler
`os.environ.get("ENV")` directamente — devem importar `is_production`,
`is_relaxed`, etc. deste módulo.

Comportamento fail-closed:
- `ENV` ausente, vazio ou corrompido → **trata-se como produção**.
- Valores explicitamente relaxados: `development`, `preview`.
- Qualquer outra string (incluindo o copy-paste bug `SENDER_PT_FROM = ...`)
  cai em produção com warning no log.
"""
import logging
import os

# Fail-safe: garante que os logs de detecção são visíveis mesmo que
# ninguém tenha chamado logging.basicConfig ainda (este módulo é importado
# muito cedo no boot do backend, antes de qualquer configuração formal).
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

logger = logging.getLogger(__name__)

_SAFE_DEV_VALUES = {"development", "preview"}


def _detect() -> str:
    raw = os.environ.get("ENV", "").strip().lower()
    if raw in _SAFE_DEV_VALUES:
        logger.info("Ambiente detectado: %s (modo relaxado)", raw)
        return raw
    if raw and raw != "production":
        logger.warning(
            "ENV com valor inválido ou corrompido (%r). "
            "Fail-closed: a tratar como PRODUÇÃO.",
            raw[:120],
        )
    else:
        logger.info("Ambiente detectado: production (fail-closed)")
    return "production"


ENVIRONMENT = _detect()


def is_production() -> bool:
    """True se o ambiente é produção (ou fail-closed)."""
    return ENVIRONMENT == "production"


def is_development() -> bool:
    return ENVIRONMENT == "development"


def is_preview() -> bool:
    return ENVIRONMENT == "preview"


def is_relaxed() -> bool:
    """True em dev ou preview (modo não-produção)."""
    return ENVIRONMENT in _SAFE_DEV_VALUES

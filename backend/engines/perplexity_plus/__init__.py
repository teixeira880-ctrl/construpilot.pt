"""Perplexity Plus — 4 endpoints avançados com presets PT e cache MongoDB.

Modos:
  - chat (SSE streaming)
  - compare (tabela comparativa estruturada)
  - norms (DRE/LNEC/APA focus)
  - materials_watch (preços + tendência)

Cache MongoDB TTL 24h via collection `pplx_cache`.
"""
from engines.perplexity_plus.pplx_client import pplx_plus_client
from engines.perplexity_plus.pplx_presets import PRESETS, get_preset, preset_system
from engines.perplexity_plus.pplx_cache import cache_get, cache_set, cache_key

__all__ = [
    "pplx_plus_client", "PRESETS", "get_preset", "preset_system",
    "cache_get", "cache_set", "cache_key",
]

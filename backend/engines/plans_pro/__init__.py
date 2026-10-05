"""Plans Pro — integração Autodesk APS (OSS + Model Derivative) + cascade IA.

Pipeline:
  1. Upload DWG/RVT/IFC/NWC/PDF → OSS bucket (signed S3)
  2. Trigger Model Derivative translation → SVF2
  3. Polling manifest até "success"
  4. Thumbnail + metadata + properties
  5. IA cascade: OpenAI vision (thumbnail) + Claude Opus 5.5 (síntese + orçamento PT 2026)
  6. Perplexity: normas aplicáveis (RGEU, Eurocodes, REH, REBAP)
"""
from engines.plans_pro.autodesk_client import autodesk_client, AutodeskError
from engines.plans_pro.plan_metadata import aggregate_quantities

__all__ = ["autodesk_client", "AutodeskError", "aggregate_quantities"]

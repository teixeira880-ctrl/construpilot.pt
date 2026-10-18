"""Reader principal do BET-PT Agent (L1.3).

Entrypoint: `read_building(project_id, pdf_paths, brief, meter, client=None)`.

Fluxo:
    1. Verifica feature flag `BET_AGENT_ENABLED`.
    2. Extrai texto vectorial de cada PDF (pymupdf) + render de cada página
       em PNG alta resolução (300 DPI).
    3. Monta `initial_user_content`:
       - texto do brief (hipóteses impostas),
       - lista de imagens PNG base64,
       - texto vectorial correspondente a cada página.
    4. Chama o `run_reader_loop` com Claude Opus 5.5 + tool-use.
    5. Devolve o `BuildingModel` populado + perguntas pendentes.

Fail-closed:
    - Se feature flag off → raise `ReaderDisabled`.
    - Se `ANTHROPIC_API_KEY` ausente → `AnthropicNotConfigured`.
    - CI nunca atinge estes caminhos: injectar `client=MockLLMClient()`.
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from engines.bet_agent import is_enabled
from engines.bet_agent.agent.client import (
    AnthropicClient,
    AnthropicNotConfigured,
    is_anthropic_available,
)
from engines.bet_agent.agent.loop import AsyncLLMClient, LoopResult, run_reader_loop
from engines.bet_agent.agent.prompts import READER_SYSTEM_PT
from engines.bet_agent.cost import DossierMeter
from engines.bet_agent.models.brief import UserBrief

logger = logging.getLogger(__name__)


class ReaderDisabled(RuntimeError):
    """Feature flag `BET_AGENT_ENABLED` está OFF."""


def _render_pdf_pages(pdf_path: Path, dpi: int = 300) -> list[tuple[int, bytes, str]]:
    """Devolve [(page_num_1indexed, png_bytes, vector_text), ...]."""
    import fitz  # pymupdf — importação local para evitar overhead em CI
    out: list[tuple[int, bytes, str]] = []
    doc = fitz.open(str(pdf_path))
    try:
        for idx, page in enumerate(doc, start=1):
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            png_bytes = pix.tobytes("png")
            vector_text = page.get_text("text") or ""
            out.append((idx, png_bytes, vector_text))
    finally:
        doc.close()
    return out


def _build_brief_text(brief: UserBrief) -> str:
    """Serializa o brief em prosa curta para o modelo."""
    materials = brief.materials
    lines = ["# Hipóteses impostas pelo utilizador (prioridade absoluta)"]
    if materials.slab_type:
        lines.append(f"- Tipo de laje: {materials.slab_type.value}")
    if materials.masonry_type:
        lines.append(f"- Alvenaria: {materials.masonry_type.value}")
    if materials.concrete_class:
        lines.append(f"- Betão: {materials.concrete_class.value}")
    if materials.steel_class:
        lines.append(f"- Aço: {materials.steel_class.value}")
    if materials.roof_type:
        lines.append(f"- Cobertura: {materials.roof_type.value}")
    if brief.water_table_depth_m is not None:
        lines.append(f"- Nível freático a: {brief.water_table_depth_m:.2f} m")
    if brief.seismic.zone or brief.seismic.municipio:
        lines.append(f"- Sísmica: zona={brief.seismic.zone or '?'} "
                     f"solo={brief.seismic.soil_class or '?'} "
                     f"municipio={brief.seismic.municipio or '?'}")
    if brief.room_uses:
        uses = ", ".join(f"{k}={v}" for k, v in brief.room_uses.items())
        lines.append(f"- Usos declarados: {uses}")
    if brief.notes:
        lines.append(f"- Notas: {brief.notes}")
    return "\n".join(lines)


def _build_initial_user_content(
    brief: UserBrief,
    pages: list[tuple[int, bytes, str]],
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    content.append({"type": "text", "text": _build_brief_text(brief)})
    for page_num, png_bytes, vtext in pages:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(png_bytes).decode("ascii"),
            },
        })
        content.append({
            "type": "text",
            "text": (
                f"Página {page_num} — texto vectorial extraído do PDF (para cotas numéricas):\n"
                f"```\n{vtext.strip()[:4000]}\n```\n"
                "Reporta todos os elementos visíveis usando as ferramentas disponíveis. "
                "Se algum valor ficar <0.5 de confiança, chama `ask_user` com `bbox` para "
                "apresentar a vinheta ao utilizador. Caso contrário, segue a leitura."
            ),
        })
    content.append({
        "type": "text",
        "text": (
            "Quando tiveres terminado todas as páginas sem dúvidas bloqueantes, "
            "chama a ferramenta `finish` com uma nota curta em PT."
        ),
    })
    return content


async def read_building(
    project_id: str,
    pdf_paths: list[str | Path],
    brief: UserBrief,
    meter: DossierMeter,
    client: AsyncLLMClient | None = None,
    model: str = "claude-opus-5-5",
    max_turns: int = 40,
    enforce_flag: bool = True,
) -> LoopResult:
    """Lê plantas + geotécnico e devolve `LoopResult(building, pending_questions, ...)`.

    - Se `client is None`, instancia `AnthropicClient()` (requer `ANTHROPIC_API_KEY`).
    - Em CI, injectar um mock que implemente `AsyncLLMClient`.
    - Com `enforce_flag=False`, salta a verificação da feature flag (uso
      exclusivo em testes). Default True (ligado).
    """
    if enforce_flag and not is_enabled():
        raise ReaderDisabled(
            "BET_AGENT_ENABLED=false — o Reader está desligado. "
            "Activar via variável de ambiente para preview/prod."
        )

    # Lê todas as páginas de todos os PDFs.
    all_pages: list[tuple[int, bytes, str]] = []
    page_offset = 0
    for pdf_path in pdf_paths:
        p = Path(pdf_path)
        if not p.exists():
            raise FileNotFoundError(f"PDF não encontrado: {p}")
        pages = _render_pdf_pages(p)
        for num, png, vt in pages:
            all_pages.append((num + page_offset, png, vt))
        page_offset += len(pages)

    initial_content = _build_initial_user_content(brief, all_pages)

    if client is None:
        if not is_anthropic_available():
            raise AnthropicNotConfigured(
                "ANTHROPIC_API_KEY não definido — adicione aos segredos do Emergent "
                "ou injecte um `client` mock em testes."
            )
        client = AnthropicClient()

    return await run_reader_loop(
        client=client,
        system_prompt=READER_SYSTEM_PT,
        initial_user_content=initial_content,
        project_id=project_id,
        meter=meter,
        model=model,
        max_turns=max_turns,
    )

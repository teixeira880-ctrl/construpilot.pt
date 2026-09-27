"""Teste E2E real do Aurora `/ask` — fast + reasoning.

Uso:
    cd /app/backend && python scripts/test_aurora_ask.py

Nunca imprime API key, signing secret nem authorization header. Só metadata
(status, schema, model, route, text_length, request_id, snippet<=200).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# permite correr o script standalone
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

from engines.aurora_client import AuroraCompanyClient
from engines.aurora_contract import parse_aurora_company_answer


TEST_PROJECT_ID = "prj_f9fb5a80f784"  # projeto de teste existente


async def _run_ask(client: AuroraCompanyClient, label: str, question: str) -> None:
    print(f"\n=== {label} ===")
    print(f"  question_length: {len(question)}")
    r = await client.ask(question=question, project_id=TEST_PROJECT_ID, resources=[])
    print(f"  http_status:     {r.status_code}")
    if r.status_code >= 400:
        print(f"  body_snippet:    {r.text[:300]}")
        return

    try:
        answer = parse_aurora_company_answer(r.json())
    except Exception as e:  # noqa: BLE001
        print(f"  PARSING FAILED: {type(e).__name__}: {str(e)[:200]}")
        return

    print(f"  schema:          {answer.schema_}")
    print(f"  model:           {answer.model}")
    print(f"  route:           {answer.route}")
    print(f"  mode:            {answer.mode}")
    print(f"  read_only:       {answer.read_only}")
    print(f"  side_effects:    {answer.side_effects}")
    print(f"  text_length:     {len(answer.text)}")
    print(f"  text_snippet:    {answer.text[:200]}")
    print(f"  request_id_last: {client._last_request_id}")


async def main() -> None:
    print("Aurora Company API — teste E2E parsing")
    client = AuroraCompanyClient()
    print(f"  endpoint_base: {client.config.endpoint_base}")
    print(f"  key_id:        {client.config.key_id}")
    # NUNCA imprimir a API key nem o signing secret.

    await _run_ask(
        client, "fast · smoke",
        'Diz apenas AURORA_API_OK. Devolve como texto simples.',
    )

    await _run_ask(
        client, "reasoning · JSON curto",
        'Analisa este texto e devolve JSON: {"resumo":"","area_m2":0}. '
        'Texto: Casa 180m2, 2 pisos, Lisboa.',
    )


if __name__ == "__main__":
    asyncio.run(main())

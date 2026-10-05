"""E2E Plans Pro — gera DWG mínimo via ezdxf, faz upload, polling, análise IA.

Executa sem printar credenciais Autodesk. Reporta:
  - Upload OK (URN, bucket, status)
  - Translation status final (success/failed/timeout) + duração
  - Análise IA (providers usados, status, resumo truncado)
  - Zero credenciais nos logs

Uso:
    cd /app/backend && python3 scripts/test_plans_pro_e2e.py
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
logger = logging.getLogger("plans_pro_e2e")


def generate_minimal_dxf() -> bytes:
    """Gera um DXF mínimo via ezdxf: planta simples com paredes + portas + janelas."""
    import ezdxf
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    doc.layers.add(name="A-PAREDE", color=1)
    doc.layers.add(name="A-PORTA", color=3)
    doc.layers.add(name="A-JANELA", color=4)
    doc.layers.add(name="A-COTA", color=7)

    # 4 paredes retangulares (10x8)
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "A-PAREDE"})
    msp.add_line((10, 0), (10, 8), dxfattribs={"layer": "A-PAREDE"})
    msp.add_line((10, 8), (0, 8), dxfattribs={"layer": "A-PAREDE"})
    msp.add_line((0, 8), (0, 0), dxfattribs={"layer": "A-PAREDE"})
    # 2 portas
    msp.add_line((2, 0), (3, 0), dxfattribs={"layer": "A-PORTA"})
    msp.add_line((4, 8), (5, 8), dxfattribs={"layer": "A-PORTA"})
    # 3 janelas
    msp.add_line((6, 0), (7, 0), dxfattribs={"layer": "A-JANELA"})
    msp.add_line((10, 2), (10, 3), dxfattribs={"layer": "A-JANELA"})
    msp.add_line((10, 5), (10, 6), dxfattribs={"layer": "A-JANELA"})
    # 1 cota
    msp.add_text("10m", dxfattribs={"layer": "A-COTA", "height": 0.3}).set_placement((4, -0.5))

    buf = io.BytesIO()
    try:
        doc.write(buf)
    except Exception:
        # ezdxf aceita stream text-mode em algumas versões
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            doc.saveas(f.name)
            path = f.name
        with open(path, "rb") as f:
            return f.read()
    return buf.getvalue()


async def main():
    from engines.plans_pro.autodesk_client import autodesk_client

    if not autodesk_client.is_configured():
        print("[FAIL] Autodesk APS não configurado no .env")
        return 1

    print("[STEP] Gerar DXF mínimo via ezdxf…")
    try:
        data = generate_minimal_dxf()
    except ImportError:
        print("[FAIL] ezdxf não instalado. pip install ezdxf")
        return 2
    print(f"[OK] DXF gerado: {len(data)} bytes")

    # 1. Token OAuth v2
    print("[STEP] Pedir token OAuth v2…")
    tok = await autodesk_client.viewer_token()
    print(f"[OK] viewer_token recebido (expires_in={tok['expires_in']}s)")

    # 2. Upload direto no OSS
    print("[STEP] Upload OSS…")
    t0 = time.time()
    try:
        up = await autodesk_client.upload_object("e2e_test.dxf", data)
    except Exception as e:
        print(f"[FAIL] Upload falhou: {type(e).__name__}: {e}")
        return 3
    print(f"[OK] Upload concluído em {time.time()-t0:.1f}s")
    print(f"     bucket={up['bucket']}")
    print(f"     object_key={up['object_key']}")
    print(f"     urn (truncado)={up['urn'][:40]}…")

    # 3. Translate
    print("[STEP] Translate (SVF2)…")
    try:
        await autodesk_client.translate(up["urn"])
    except Exception as e:
        print(f"[FAIL] translate falhou: {type(e).__name__}: {e}")
        return 4
    print("[OK] Translate job enviado")

    # 4. Polling manifest (max 10 min para teste)
    print("[STEP] Polling manifest…")
    t_poll = time.time()
    final_status = None
    final_progress = ""
    for i in range(120):
        await asyncio.sleep(5)
        try:
            m = await autodesk_client.manifest(up["urn"])
        except Exception as e:
            print(f"[WARN] manifest err: {e}")
            continue
        status = (m.get("status") or "").lower()
        progress = m.get("progress") or ""
        print(f"     [{int(time.time()-t_poll):>3}s] status={status} progress={progress}")
        if status in ("success", "failed", "timeout"):
            final_status = status
            final_progress = progress
            break
    duration = time.time() - t_poll
    print(f"[{'OK' if final_status == 'success' else 'WARN'}] Translation: {final_status} ({duration:.1f}s)")
    if final_status != "success":
        print("[INFO] Translation não terminou com success — pode ser DXF demasiado simples para APS.")

    # 5. Thumbnail (opcional)
    print("[STEP] Thumbnail…")
    try:
        thumb = await autodesk_client.thumbnail(up["urn"])
        print(f"[{'OK' if thumb else 'WARN'}] thumbnail: {'presente' if thumb else 'indisponível'} ({len(thumb or b'')} bytes)")
    except Exception as e:
        print(f"[WARN] thumbnail falhou: {e}")
        thumb = None

    # 6. Metadata
    print("[STEP] Metadata…")
    try:
        meta = await autodesk_client.metadata(up["urn"])
        views = (meta.get("data") or {}).get("metadata") or []
        print(f"[OK] metadata recebido ({len(views)} views)")
    except Exception as e:
        print(f"[WARN] metadata: {e}")
        meta = {}

    # 7. Cascade IA
    if thumb or final_status == "success":
        print("[STEP] Cascade IA…")
        from engines.plans_pro.plan_vision import full_analysis
        try:
            result = await full_analysis(
                filename="e2e_test.dxf",
                metadata={"quantities": {}, "views": []},
                thumbnail_bytes=thumb,
                thumbnail_mime="image/png",
                project_hint="DXF E2E — habitação R+1, 80m²",
                include_web_norms=False,  # Perplexity opcional para rapidez
            )
            print(f"[OK] Análise IA status={result.get('status')} providers={result.get('providers_used')}")
            if result.get("synthesis"):
                resumo = (result["synthesis"].get("resumo") or "")[:200]
                print(f"     resumo: {resumo}…")
                print(f"     ouvrages: {len(result['synthesis'].get('ouvrages', []))}")
            if result.get("warnings"):
                print(f"     warnings: {result['warnings']}")
        except Exception as e:
            print(f"[FAIL] IA falhou: {type(e).__name__}: {e}")
            return 5
    else:
        print("[SKIP] Cascade IA (sem thumbnail nem translation success)")

    print("\n[SUMMARY]")
    print(f"  Upload: OK")
    print(f"  Translation: {final_status} ({duration:.1f}s)")
    print(f"  Thumbnail: {'OK' if thumb else 'indisponível'}")
    print(f"  Fim do E2E")
    return 0 if final_status == "success" else 10


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)

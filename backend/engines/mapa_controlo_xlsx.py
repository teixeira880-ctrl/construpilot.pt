"""Rastreabilidade dos mapas de quantidades : copia as imagens de controlo (o que foi medido, pintado sobre o desenho) para uma
folha «Controlo» do próprio Excel, para que o mapa e a prova da medição viajem juntos. Usado pelos motores mapa_estrutura e
mapa_arquitetura. Falha em silêncio (o Excel fica sem a folha) : nunca impede a entrega do mapa."""
from __future__ import annotations

import io
import logging

log = logging.getLogger(__name__)
LARGURA_PX = 1400


def anexar_imagens(caminho_xlsx: str, imagens: list, nota: str = "") -> bool:
    """imagens = [(título, PIL.Image | bytes PNG)]."""
    try:
        from openpyxl import load_workbook
        from openpyxl.drawing.image import Image as XLImage
        from openpyxl.styles import Font
        from PIL import Image
        wb = load_workbook(caminho_xlsx)
        if "Controlo" in wb.sheetnames:
            del wb["Controlo"]
        ws = wb.create_sheet("Controlo")
        ws["A1"] = "Controlo da medição — imagens do que foi medido e calculado (mesmas do PDF de controlo)"
        ws["A1"].font = Font(name="Arial", size=13, bold=True, color="1F4E46")
        ws["A2"] = nota or "Cada página mostra o elemento medido pintado sobre as linhas do desenho original, com a sua medida."
        ws["A2"].font = Font(name="Arial", size=9, italic=True, color="666666")
        linha = 4
        for titulo, im in imagens:
            if isinstance(im, (bytes, bytearray)):
                im = Image.open(io.BytesIO(im))
            im = im.convert("RGB")
            if im.width > LARGURA_PX:
                im = im.resize((LARGURA_PX, int(im.height * LARGURA_PX / im.width)))
            buf = io.BytesIO()
            im.save(buf, "PNG", optimize=True)
            buf.seek(0)
            ws.cell(row=linha, column=1, value=titulo).font = Font(name="Arial", size=11, bold=True)
            xi = XLImage(buf)
            ws.add_image(xi, f"A{linha + 1}")
            linha += 3 + int(im.height / 20)            # ~20 px por linha de Excel
        wb.save(caminho_xlsx)
        try:                    # o openpyxl apaga os resultados das fórmulas ao gravar : voltar a gravá-los (pré-visualizações)
            from engines.xlsx_cache import preencher
            preencher(caminho_xlsx)
        except Exception:  # noqa: BLE001
            pass
        return True
    except Exception:  # noqa: BLE001
        log.exception("anexar_imagens falhou")
        return False

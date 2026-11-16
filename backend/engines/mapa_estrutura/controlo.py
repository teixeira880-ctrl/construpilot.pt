"""Desenho de controlo da medição : uma página por planta com o que foi medido pintado por cima do desenho, para o utilizador
verificar de relance (laje, consolas, moldes, aberturas, secções com a sua etiqueta, vãos das vigas)."""
from __future__ import annotations

import io

import cv2
import numpy as np

CORES = {"laje": (214, 240, 214), "fora": (170, 215, 255), "moldes": (250, 226, 196), "aberturas": (150, 150, 255),
         "Pilar": (160, 60, 20), "Parede": (40, 90, 150), "Núcleo": (130, 40, 130), "viga": (30, 160, 230)}       # BGR


def imagem(planta: dict, largura_max: int = 2600) -> np.ndarray:
    m = planta["_mascaras"]
    h, w = m["bruta"].shape
    im = np.full((h, w, 3), 255, np.uint8)
    im[m["bruta"] == 1] = CORES["laje"]
    im[m["fora"] == 1] = CORES["fora"]
    im[m["moldes"] == 1] = CORES["moldes"]
    im[m["aberturas"] == 1] = CORES["aberturas"]
    im[(m["bar"] == 1) & (m["cheio"] == 0)] = (120, 120, 120)
    for v in planta.get("_vaos_viga", []):
        x0, y0, x1, y1 = v["_caixa"]
        cv2.rectangle(im, (x0, y0), (x1, y1), CORES["viga"], -1)
    for e in planta["elementos"]:
        x0, y0, x1, y1 = e["_caixa"]
        cor = CORES.get(e["tipo"], (0, 0, 0))
        if e["com_trama"]:
            reg = m["cheio"][y0:y1 + 1, x0:x1 + 1] == 1
            im[y0:y1 + 1, x0:x1 + 1][reg] = cor
        else:
            cv2.rectangle(im, (x0, y0), (x1, y1), cor, 3)
    esc = min(1.0, largura_max / float(w))
    if esc < 1.0:
        im = cv2.resize(im, (int(w * esc), int(h * esc)), interpolation=cv2.INTER_AREA)
    f = max(0.45, 0.55 * im.shape[1] / 2600)
    for e in planta["elementos"]:
        x0, y0, x1, y1 = e["_caixa"]
        nome = e["nome"] if len(e["nome"]) <= 12 else e["nome"].split(" + ")[0] + "+"
        nome = nome.encode("ascii", "ignore").decode()
        cv2.putText(im, nome, (int(x1 * esc) + 4, int(y0 * esc) + 12), cv2.FONT_HERSHEY_SIMPLEX, f, (0, 0, 0), 1, cv2.LINE_AA)
    for v in planta.get("_vaos_viga", []):
        x0, y0, x1, y1 = v["_caixa"]
        cv2.putText(im, f"{v['nome']} {v['vao']:.2f}", (int((x0 + x1) / 2 * esc) - 30, int((y0 + y1) / 2 * esc) - 5), cv2.FONT_HERSHEY_SIMPLEX, f * 0.9,
                    (0, 90, 160), 1, cv2.LINE_AA)
    return im


def gerar_pdf(plantas: list, modelo: dict, caminho: str, titulo: str = "") -> str:
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    W, H = landscape(A3)
    c = canvas.Canvas(caminho, pagesize=(W, H))
    legenda = [("Laje medida", CORES["laje"]), ("Laje fora do perímetro dos pilares (consola / varanda)", CORES["fora"]),
               ("Moldes de aligeiramento contados", CORES["moldes"]), ("Abertura deduzida (núcleo)", CORES["aberturas"]),
               ("Pilar", CORES["Pilar"]), ("Parede", CORES["Parede"]), ("Núcleo", CORES["Núcleo"]), ("Viga : vão livre medido", CORES["viga"])]
    for ip, p in enumerate(plantas):
        niv = ", ".join(n.get("nome") or "" for n in p.get("niveis", [])) or f"Planta {ip + 1}"
        lj = p["laje"]
        c.setFont("Helvetica-Bold", 13)
        c.drawString(28, H - 30, f"Controlo da medição — {niv}" + (f" — {titulo}" if titulo else ""))
        c.setFont("Helvetica", 9)
        c.drawString(28, H - 44, f"Laje bruta {lj['area_bruta']:.2f} m² ; aberturas {sum(a['area'] for a in lj['aberturas']):.2f} m² ; fora do perímetro "
                                 f"{lj['area_fora_do_perimetro']:.2f} m² ; moldes {lj['moldes']} ; secções {len(p['elementos'])} ; vigas {len(p['vigas'])}. "
                                 "Verifique se o que está pintado corresponde à estrutura.")
        _, buf = cv2.imencode(".png", imagem(p))
        img = ImageReader(io.BytesIO(buf.tobytes()))
        iw, ih = img.getSize()
        s = min((W - 56) / iw, (H - 110) / ih)
        c.drawImage(img, 28, 52 + (H - 110 - ih * s) / 2, iw * s, ih * s)
        x = 28
        for nome, (b, g, r) in legenda:
            c.setFillColorRGB(r / 255, g / 255, b / 255)
            c.rect(x, 26, 10, 10, fill=1, stroke=1)
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica", 8)
            c.drawString(x + 14, 28, nome)
            x += 22 + c.stringWidth(nome, "Helvetica", 8)
        c.showPage()
    c.save()
    return caminho

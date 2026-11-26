"""PDF do mapa de avanço da obra: plantas coloridas por zona + matriz zonas × atividades.

Mesma identidade que os documentos da empresa (logótipo, cor, rodapé legal). Só mostra o que foi registado.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, Spacer

from engines import obra_execucao as ox
from engines import obra_execucao_txt as TX
from engines.obra_gestao_pdf import _build, _doc, _grid

PDF = {
    "pt": {"titulo": "Mapa de avanço da obra", "global": "Avanço global", "piso": "Piso", "zona": "Zona", "media": "Média",
           "atividade": "Atividade", "peso": "Peso", "base_area": "Média ponderada pela área das zonas e pelo peso das atividades.",
           "base_zonas": "Média ponderada pelo peso das atividades (zonas com o mesmo peso).", "sem_planta": "Piso sem planta carregada.",
           "legenda": "Legenda: cinzento = por iniciar · amarelo = em curso · verde = avançado · verde escuro = concluído.",
           "fonte": "Valores registados pela direção de obra no ConstruPilot (último registo: {u}). Nenhum valor é estimado.",
           "vazio": "O mapa da obra ainda não tem zonas nem atividades.", "por_atividade": "Avanço por atividade"},
    "fr": {"titulo": "Carte d'avancement du chantier", "global": "Avancement global", "piso": "Niveau", "zona": "Zone", "media": "Moyenne",
           "atividade": "Tâche", "peso": "Poids", "base_area": "Moyenne pondérée par la surface des zones et le poids des tâches.",
           "base_zonas": "Moyenne pondérée par le poids des tâches (zones de même poids).", "sem_planta": "Niveau sans plan chargé.",
           "legenda": "Légende : gris = non commencé · jaune = en cours · vert = avancé · vert foncé = terminé.",
           "fonte": "Valeurs saisies par la conduite de travaux dans ConstruPilot (dernière saisie : {u}). Aucune valeur n'est estimée.",
           "vazio": "La carte du chantier n'a pas encore de zones ni de tâches.", "por_atividade": "Avancement par tâche"},
}


def _hex(c: str):
    return colors.HexColor(c)


def planta_colorida(img: bytes, zonas: list[dict], avancos: dict) -> Optional[bytes]:
    """Desenha sobre a planta os retângulos das zonas, coloridos pelo avanço, com nome e percentagem."""
    try:
        from PIL import Image as PImage, ImageDraw, ImageFont
        base = PImage.open(BytesIO(img)).convert("RGBA")
        if max(base.size) > 2400:
            base.thumbnail((2400, 2400))
        W, H = base.size
        over = PImage.new("RGBA", base.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", max(12, W // 70))
        except Exception:  # noqa: BLE001
            font = ImageFont.load_default()
        for z in zonas:
            r = z.get("ret")
            if not r:
                continue
            pct = avancos.get(z["zona_id"], 0.0)
            hx = ox.cor_avanco(pct).lstrip("#")
            rgb = tuple(int(hx[i:i + 2], 16) for i in (0, 2, 4))
            box = [r["x"] / 100 * W, r["y"] / 100 * H, (r["x"] + r["w"]) / 100 * W, (r["y"] + r["h"]) / 100 * H]
            d.rectangle(box, fill=rgb + (120,), outline=rgb + (255,), width=max(2, W // 400))
            txt = f"{z['nome']}\n{pct:g} %"
            d.multiline_text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), txt, fill=(15, 23, 42, 255), font=font, anchor="mm", align="center")
        out = BytesIO()
        PImage.alpha_composite(base, over).convert("RGB").save(out, "JPEG", quality=88)
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return None


def mapa_pdf(obra: dict, mapa: dict, plantas: dict, branding: Optional[dict]) -> bytes:
    L = PDF.get(TX.LANG, PDF["pt"])
    P, S, buf, pdf, story = _doc(branding)
    res = ox.resumo_mapa(mapa)
    story.append(Paragraph(escape(L["titulo"]), S["h1"]))
    story.append(Paragraph(escape(" · ".join(x for x in (obra.get("name"), obra.get("ref"), obra.get("city")) if x)), S["muted"]))
    story.append(Spacer(1, 4))
    if not res["zonas"] or not res["atividades"]:
        story.append(Paragraph(escape(L["vazio"]), S["body"]))
        return _build(pdf, story, branding, P, buf)
    story.append(Paragraph(f"<b>{escape(L['global'])}: {res['global']:g} %</b>", S["h2"]))
    story.append(Paragraph(escape(L["base_area"] if res["base"] == "area" else L["base_zonas"]), S["muted"]))
    story.append(Spacer(1, 4))
    rows = [[L["piso"], "%"]] + [[escape(p["nome"]), f"{p['avanco']:g} %"] for p in res["pisos"]]
    story.append(_grid(P, rows, [120 * mm, 30 * mm]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(escape(L["por_atividade"]), S["h2"]))
    rows = [[L["atividade"], L["peso"], "%"]] + [[escape(a["nome"]), f"{a['peso']:g}", f"{a['avanco']:g} %"] for a in res["atividades"]]
    story.append(_grid(P, rows, [110 * mm, 20 * mm, 30 * mm]))
    avz = {z["zona_id"]: z["avanco"] for z in res["zonas"]}
    ativ = mapa.get("atividades") or []
    for p in mapa.get("pisos") or []:
        zs = [z for z in mapa.get("zonas") or [] if z["piso_id"] == p["piso_id"]]
        if not zs:
            continue
        story.append(PageBreak())
        story.append(Paragraph(f"{escape(L['piso'])} — {escape(p['nome'])}", S["h1"]))
        img = plantas.get(p["piso_id"])
        if img and any(z.get("ret") for z in zs):
            img = planta_colorida(img, zs, avz) or img
        if img:
            try:
                from reportlab.lib.utils import ImageReader
                iw, ih = ImageReader(BytesIO(img)).getSize()
                w = 174 * mm
                h = w * ih / iw
                if h > 120 * mm:
                    h = 120 * mm
                    w = h * iw / ih
                story.append(Image(BytesIO(img), width=w, height=h))
            except Exception:  # noqa: BLE001
                pass
        else:
            story.append(Paragraph(escape(L["sem_planta"]), S["muted"]))
        story.append(Spacer(1, 4))
        # matriz zonas × atividades (cores = avanço)
        prog = mapa.get("progresso") or {}
        from reportlab.lib.styles import ParagraphStyle
        hs = ParagraphStyle("cab", fontName="Helvetica-Bold", fontSize=6, leading=7, textColor=colors.white, alignment=1)
        cab = [L["zona"]] + [Paragraph(escape(a["nome"]), hs) for a in ativ] + [L["media"]]
        rows, estilo = [cab], []
        for i, z in enumerate(zs, start=1):
            linha = [escape(z["nome"])]
            for j, a in enumerate(ativ, start=1):
                v = float((prog.get(f"{z['zona_id']}|{a['atividade_id']}") or {}).get("pct") or 0)
                linha.append(f"{v:g}")
                estilo.append(("BACKGROUND", (j, i), (j, i), _hex(ox.cor_avanco(v))))
                if v >= 100:
                    estilo.append(("TEXTCOLOR", (j, i), (j, i), colors.white))
            linha.append(f"{avz.get(z['zona_id'], 0):g} %")
            rows.append(linha)
        larg_z = 34 * mm
        resto = (174 * mm - larg_z - 18 * mm) / max(1, len(ativ))
        t = _grid(P, rows, [larg_z] + [resto] * len(ativ) + [18 * mm])
        t.setStyle(estilo + [("FONTSIZE", (0, 0), (-1, -1), 6.5 if len(ativ) > 8 else 7.5), ("ALIGN", (1, 1), (-1, -1), "CENTER")])
        story.append(t)
    story.append(Spacer(1, 8))
    story.append(Paragraph(escape(L["legenda"]), S["muted"]))
    u = res.get("ultimo_registo")
    u = datetime.fromisoformat(u).astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M") if u else "—"
    story.append(Paragraph(escape(L["fonte"].format(u=u)), S["muted"]))
    return _build(pdf, story, branding, P, buf)

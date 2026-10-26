"""Deterministic vector-style section drawing (plan view of a wall build-up) with legible labels and a dimension chain.
No AI: every dimension drawn comes from the arguments (the assistant fills them from the dossier and must state what is assumed)."""
import io
import math

from PIL import Image, ImageDraw, ImageFont

HATCH = {"masonry": "#c9a27a", "concrete": "#b8b8b8", "insulation": "#f2d98d", "render": "#e6e6e6", "air": "#ffffff", "membrane": "#2f6f9f",
         "metal": "#7d8a99", "soil": "#a78a68", "wood": "#d9b38c", "existing": "#d8cfc4", "other": "#dddddd"}
LABELS = {"masonry": "maçonnerie", "concrete": "béton", "insulation": "isolant", "render": "enduit", "air": "joint / vide", "membrane": "membrane", "metal": "métal", "soil": "sol",
          "wood": "bois", "existing": "existant", "other": ""}

SCHEMA_TOOL = {"type": "function", "name": "draw_section_schema", "strict": True,
               "description": "Desenha um esquema de princípio vetorial (corte horizontal de uma parede ou de uma ligação de fachadas) com etiquetas legíveis, cadeia de cotas em cm e elementos anexos (consola de apoio, rufo/zinco, sapata, dreno, membrana). Todas as espessuras vêm dos argumentos: não inventes nada, assinala nas notas o que é uma hipótese. O ficheiro produzido é um esquema de princípio (PNG + PDF), nunca uma validação de execução. Etiquetas em português europeu.",
               "parameters": {"type": "object", "properties": {
                   "title": {"type": "string"},
                   "layers": {"type": "array", "minItems": 2, "maxItems": 12, "items": {"type": "object", "properties": {
                       "label": {"type": "string"}, "thickness_cm": {"type": "number"},
                       "material": {"type": "string", "enum": list(HATCH)}}, "required": ["label", "thickness_cm", "material"], "additionalProperties": False}},
                   "left_label": {"type": ["string", "null"], "description": "o que está à esquerda (ex.: interior da casa)"},
                   "right_label": {"type": ["string", "null"], "description": "o que está à direita (ex.: parcela vizinha)"},
                   "features": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {
                       "kind": {"type": "string", "enum": ["console", "flashing", "footing", "drain", "membrane", "dilatation_joint", "note"]},
                       "label": {"type": "string"}, "layer_index": {"type": "integer", "description": "camada em causa (0 = primeira)"},
                       "value_cm": {"type": ["number", "null"], "description": "cota útil: altura da consola, largura da sapata, Ø do dreno, abertura da junta…"}},
                       "required": ["kind", "label", "layer_index", "value_cm"], "additionalProperties": False}},
                   "notes": {"type": "array", "maxItems": 6, "items": {"type": "string"}, "description": "hipóteses e pontos a validar, impressos sob o esquema"},
                   "orientation": {"type": "string", "enum": ["plan", "vertical"], "description": "plan = corte horizontal (vista em planta); vertical = corte vertical com solo, sapata, dreno"},
                   "vertical": {"anyOf": [{"type": "object", "properties": {
                       "height_above_ground_cm": {"type": "number"}, "footing_depth_cm": {"type": "number", "description": "profundidade da face inferior da sapata sob o pavimento acabado"},
                       "footing_width_cm": {"type": "number"}, "footing_height_cm": {"type": "number"},
                       "drain_depth_cm": {"type": ["number", "null"], "description": "profundidade do eixo do dreno sob o pavimento acabado"},
                       "drain_side": {"type": "string", "enum": ["left", "right"]}, "ground_label": {"type": ["string", "null"]}},
                       "required": ["height_above_ground_cm", "footing_depth_cm", "footing_width_cm", "footing_height_cm", "drain_depth_cm", "drain_side", "ground_label"], "additionalProperties": False}, {"type": "null"}],
                       "description": "obligatoire si orientation = vertical"}},
                   "required": ["title", "layers", "left_label", "right_label", "features", "notes", "orientation", "vertical"], "additionalProperties": False}}


def _font(size):
    for name in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _hatch(draw, box, material):
    x0, y0, x1, y1 = box
    draw.rectangle(box, fill=HATCH.get(material, "#dddddd"), outline="#222222", width=2)
    step = 14
    if material in ("masonry", "existing"):
        for y in range(int(y0) + step, int(y1), step):
            draw.line([(x0, y), (x1, y)], fill="#6b4f2a", width=1)
    elif material == "concrete":
        for i in range(int(x0), int(x1), 9):
            for j in range(int(y0) + 4, int(y1), 9):
                draw.point((i + (j // 9 % 2) * 4, j), fill="#444444")
    elif material == "insulation":
        w = max(6, int(x1 - x0))
        y = y0 + 6
        while y < y1 - 6:
            draw.arc([x0 + 2, y, x1 - 2, y + w], 180, 360, fill="#8a6d1d", width=2)
            y += w * 0.6
    elif material == "membrane":
        draw.rectangle(box, fill=HATCH["membrane"], outline="#1a3f5c", width=2)
    elif material == "soil":
        for y in range(int(y0), int(y1), 12):
            for x in range(int(x0), int(x1), 12):
                draw.line([(x, y + 6), (x + 6, y)], fill="#6b5a3e", width=1)


def draw_schema(args: dict) -> bytes:
    if args.get("orientation") == "vertical" and args.get("vertical"):
        return draw_vertical(args)
    layers = args["layers"]
    total_cm = sum(max(0.5, float(l["thickness_cm"])) for l in layers)
    n_feat, n_notes = len(args.get("features") or []), len(args.get("notes") or [])
    W = 1800
    margin_x, top = 140, 300
    draw_h = 560
    bottom = 70 + 36 * math.ceil(len(layers) / 2) + 20 + 28 * n_feat + 26 * n_notes + 90
    H = top + draw_h + bottom
    draw_w = W - 2 * margin_x
    scale = draw_w / total_cm
    # thin layers still visible
    widths = [max(18, float(l["thickness_cm"]) * scale) for l in layers]
    k = draw_w / sum(widths)
    widths = [w * k for w in widths]
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_title, f, f_small, f_dim = _font(38), _font(24), _font(19), _font(22)
    d.text((margin_x, 40), args["title"][:90], fill="#17483f", font=f_title)
    d.text((margin_x, 92), "Esquema de princípio — corte horizontal (vista em planta) — não contratual, não vale como validação de execução", fill="#8a6d00", font=f_small)
    y0, y1 = top, H - bottom
    x = margin_x
    boxes = []
    for l, w in zip(layers, widths):
        box = (x, y0, x + w, y1)
        _hatch(d, box, l["material"])
        boxes.append(box)
        x += w
    # side context labels
    if args.get("left_label"):
        d.text((margin_x, y1 + 18), f"◄ {args['left_label'][:40]}", fill="#333333", font=f_small)
    if args.get("right_label"):
        t = f"{args['right_label'][:40]} ►"
        d.text((W - margin_x - d.textlength(t, font=f_small), y1 + 18), t, fill="#333333", font=f_small)
    # dimension chain (top)
    yd = top - 60
    d.line([(margin_x, yd), (W - margin_x, yd)], fill="#111111", width=2)
    for (bx0, _, bx1, _), l in zip(boxes, layers):
        for bx in (bx0, bx1):
            d.line([(bx, yd - 12), (bx, yd + 12)], fill="#111111", width=2)
            d.line([(bx, yd), (bx, top)], fill="#999999", width=1)
        t = f"{float(l['thickness_cm']):g}"
        tw = d.textlength(t, font=f_dim)
        cx = (bx0 + bx1) / 2
        d.text((cx - tw / 2, yd - 42), t, fill="#111111", font=f_dim)
    tot = f"Σ {total_cm:g} cm"
    d.text((W - margin_x - d.textlength(tot, font=f_dim), yd - 100), tot, fill="#17483f", font=f_dim)
    # numbered labels with leaders into a legend
    legend_y = y1 + 70
    col_w = (W - 2 * margin_x) / 2
    for i, ((bx0, _, bx1, _), l) in enumerate(zip(boxes, layers)):
        cx = (bx0 + bx1) / 2
        n = str(i + 1)
        r = 19
        cy = y0 + 40 + (i % 3) * 46
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="white", outline="#17483f", width=3)
        d.text((cx - d.textlength(n, font=f) / 2, cy - 15), n, fill="#17483f", font=f)
        col, row = i % 2, i // 2
        lx, ly = margin_x + col * col_w, legend_y + row * 36
        mat = LABELS.get(l["material"], "")
        d.text((lx, ly), f"{n}. {l['label'][:48]} — {float(l['thickness_cm']):g} cm" + (f" ({mat})" if mat and mat.lower() not in l["label"].lower() else ""), fill="#222222", font=f)
    # features
    fy = legend_y + (math.ceil(len(layers) / 2)) * 36 + 20
    for feat in args.get("features") or []:
        idx = min(max(feat["layer_index"], 0), len(boxes) - 1)
        bx0, _, bx1, _ = boxes[idx]
        cx = (bx0 + bx1) / 2
        kind, val = feat["kind"], feat.get("value_cm")
        if kind == "console":
            d.rectangle([bx0 - 6, y1 - 36, bx1 + 6, y1 - 20], fill=HATCH["metal"], outline="#333333", width=2)
            d.polygon([(bx0 - 6, y1 - 20), (bx1 + 6, y1 - 20), (cx, y1 - 4)], fill="#5b6570")
        elif kind == "flashing":
            d.line([(bx0 - 8, y0 + 8), (bx1 + 8, y0 + 8), (bx1 + 8, y0 + 40)], fill="#4a5a6a", width=6)
        elif kind == "footing":
            fw = min(max(bx1 - bx0 + 60, (val or 0) * scale), (bx1 - bx0) * 3 + 60)
            d.rectangle([cx - fw / 2, y1 + 4, cx + fw / 2, y1 + 40], fill=HATCH["concrete"], outline="#333333", width=2)
        elif kind == "drain":
            r = min(22, max(10, (val or 10) * scale / 2))
            d.ellipse([bx1 + 30 - r, y1 + 22 - r, bx1 + 30 + r, y1 + 22 + r], fill="#cfe3f5", outline="#1a3f5c", width=3)
            d.text((bx1 + 30 + r + 6, y1 + 8), f"drain Ø{float(val):g}" if val else "drain", fill="#1a3f5c", font=f_small)
        elif kind == "membrane":
            d.line([(bx1 - 4, y0), (bx1 - 4, y1)], fill=HATCH["membrane"], width=6)
        elif kind == "dilatation_joint":
            for yy in range(y0 + 10, y1 - 10, 40):
                d.line([(cx - 8, yy), (cx + 8, yy + 20)], fill="#c0392b", width=3)
        d.text((margin_x, fy), f"• {feat['label'][:110]}" + (f" — {float(val):g} cm" if val else ""), fill="#333333", font=f_small)
        fy += 28
    for note in args.get("notes") or []:
        d.text((margin_x, fy), f'Hipótese / a validar: {note[:120]}', fill="#8a6d00", font=f_small)
        fy += 26
    d.text((margin_x, H - 34), "ConstruPilot — esquema de princípio desenhado a partir dos dados do processo; cotas em cm; a validar pelo projetista / gabinete de projeto antes da execução.", fill="#555555", font=f_small)
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def _dim_v(d, x, y_a, y_b, text, font, color="#111111"):
    d.line([(x, y_a), (x, y_b)], fill=color, width=2)
    for y in (y_a, y_b):
        d.line([(x - 12, y), (x + 12, y)], fill=color, width=2)
    d.text((x + 10, (y_a + y_b) / 2 - 12), text, fill=color, font=font)


def draw_vertical(args: dict) -> bytes:
    """Vertical section: layers side by side (left→right), finished ground line, footing below, drain at its depth, vertical dimension chain."""
    layers, v = args["layers"], args["vertical"]
    h_up, f_depth, f_w, f_h = float(v["height_above_ground_cm"]), float(v["footing_depth_cm"]), float(v["footing_width_cm"]), float(v["footing_height_cm"])
    drain_d = v.get("drain_depth_cm")
    total_h = h_up + f_depth
    W = 1800
    margin_x, top = 160, 240
    draw_h = 720
    n_feat, n_notes = len(args.get("features") or []), len(args.get("notes") or [])
    bottom = 90 + 36 * math.ceil(len(layers) / 2) + 28 * n_feat + 26 * n_notes + 110
    H = top + draw_h + bottom
    sy = draw_h / total_h
    total_w_cm = sum(max(0.5, float(l["thickness_cm"])) for l in layers)
    avail_w = W - 2 * margin_x - 420
    sx = min(avail_w / max(total_w_cm, f_w), 9.0)
    widths = [max(16, float(l["thickness_cm"]) * sx) for l in layers]
    wall_w = sum(widths)
    x_left = margin_x + 120 + max(0, (f_w * sx - wall_w) / 2)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_title, f, f_small, f_dim = _font(38), _font(24), _font(19), _font(22)
    d.text((margin_x, 40), args["title"][:90], fill="#17483f", font=f_title)
    d.text((margin_x, 92), "Esquema de princípio — corte vertical — não contratual, não vale como validação de execução", fill="#8a6d00", font=f_small)
    y_top, y_ground = top, top + h_up * sy
    y_foot_bottom = y_ground + f_depth * sy
    y_foot_top = y_foot_bottom - f_h * sy
    # soil
    d.rectangle([margin_x, y_ground, W - margin_x - 300, y_foot_bottom + 40], fill=HATCH["soil"], outline=None)
    for yy in range(int(y_ground), int(y_foot_bottom + 40), 14):
        for xx in range(margin_x, int(W - margin_x - 300), 14):
            d.line([(xx, yy + 7), (xx + 7, yy)], fill="#7a6648", width=1)
    # footing
    cx = x_left + wall_w / 2
    d.rectangle([cx - f_w * sx / 2, y_foot_top, cx + f_w * sx / 2, y_foot_bottom], fill=HATCH["concrete"], outline="#222222", width=2)
    # layers
    x = x_left
    boxes = []
    for l, w in zip(layers, widths):
        box = (x, y_top, x + w, y_foot_top)
        _hatch(d, box, l["material"])
        boxes.append(box)
        x += w
    # ground line
    d.line([(margin_x, y_ground), (W - margin_x - 300, y_ground)], fill="#111111", width=4)
    d.text((margin_x, y_ground - 30), (v.get("ground_label") or "Pavimento exterior acabado")[:40] + "  ±0,00", fill="#111111", font=f_small)
    # drain
    if drain_d is not None:
        r = 16
        dx = (cx - f_w * sx / 2 - 40) if v.get("drain_side") == "left" else (cx + f_w * sx / 2 + 40)
        dy = y_ground + float(drain_d) * sy
        d.ellipse([dx - r, dy - r, dx + r, dy + r], fill="#cfe3f5", outline="#1a3f5c", width=3)
        d.rectangle([dx - 34, dy - 34, dx + 34, dy + 34], outline="#1a3f5c", width=1)
        d.text((dx + 40, dy - 12), f"drain  −{float(drain_d):g} cm", fill="#1a3f5c", font=f_small)
    # vertical dimension chain (right)
    xd = W - margin_x - 220
    _dim_v(d, xd, y_top, y_ground, f"{h_up:g} cm", f_dim)
    _dim_v(d, xd + 90, y_ground, y_foot_bottom, f"−{f_depth:g} cm", f_dim)
    _dim_v(d, xd, y_foot_top, y_foot_bottom, f"sapata {f_h:g} cm", f_dim, "#555555")
    # horizontal chain (top)
    yd = top - 50
    d.line([(x_left, yd), (x_left + wall_w, yd)], fill="#111111", width=2)
    for (bx0, _, bx1, _), l in zip(boxes, layers):
        for bx in (bx0, bx1):
            d.line([(bx, yd - 10), (bx, yd + 10)], fill="#111111", width=2)
        t = f"{float(l['thickness_cm']):g}"
        d.text(((bx0 + bx1) / 2 - d.textlength(t, font=f_dim) / 2, yd - 38), t, fill="#111111", font=f_dim)
    d.text((cx - f_w * sx / 2, y_foot_bottom + 46), f'sapata largura {f_w:g} cm', fill="#333333", font=f_small)
    if args.get("left_label"):
        d.text((margin_x, y_top), f"◄ {args['left_label'][:40]}", fill="#333333", font=f_small)
    if args.get("right_label"):
        d.text((x_left + wall_w + 20, y_top), f"{args['right_label'][:40]} ►", fill="#333333", font=f_small)
    if abs(sx / sy - 1) > 0.15:
        d.text((margin_x, H - 62), f'Escala horizontal dilatada ×{sx / sy:.1f} para a legibilidade das camadas (cotas exatas em cm).', fill="#8a6d00", font=f_small)
    for feat in args.get("features") or []:
        idx = min(max(feat["layer_index"], 0), len(boxes) - 1)
        bx0, _, bx1, _ = boxes[idx]
        val = feat.get("value_cm")
        if feat["kind"] == "console":
            yc = y_ground - (float(val) if val else 15) * sy
            d.rectangle([bx0 - 6, yc, bx1 + 6, yc + 10], fill=HATCH["metal"], outline="#333333", width=2)
            d.polygon([(bx0 - 6, yc + 10), (bx1 + 6, yc + 10), ((bx0 + bx1) / 2, yc + 26)], fill="#5b6570")
        elif feat["kind"] == "flashing":
            d.line([(bx0 - 8, y_top + 6), (bx1 + 8, y_top + 6), (bx1 + 8, y_top + 40)], fill="#4a5a6a", width=6)
        elif feat["kind"] == "membrane":
            d.line([(bx1 - 4, y_ground - 20), (bx1 - 4, y_foot_top)], fill=HATCH["membrane"], width=6)
    # legend, features, notes
    legend_y = y_foot_bottom + 90
    col_w = (W - 2 * margin_x) / 2
    for i, ((bx0, _, bx1, _), l) in enumerate(zip(boxes, layers)):
        n = str(i + 1); r = 19; cxl = (bx0 + bx1) / 2; cyl = y_top + 40 + (i % 3) * 46
        d.ellipse([cxl - r, cyl - r, cxl + r, cyl + r], fill="white", outline="#17483f", width=3)
        d.text((cxl - d.textlength(n, font=f) / 2, cyl - 15), n, fill="#17483f", font=f)
        lx, ly = margin_x + (i % 2) * col_w, legend_y + (i // 2) * 36
        d.text((lx, ly), f"{n}. {l['label'][:48]} — {float(l['thickness_cm']):g} cm", fill="#222222", font=f)
    fy = legend_y + math.ceil(len(layers) / 2) * 36 + 20
    for feat in args.get("features") or []:
        d.text((margin_x, fy), f"• {feat['label'][:110]}" + (f" — {float(feat['value_cm']):g} cm" if feat.get("value_cm") else ""), fill="#333333", font=f_small); fy += 28
    for note in args.get("notes") or []:
        d.text((margin_x, fy), f'Hipótese / a validar: {note[:120]}', fill="#8a6d00", font=f_small); fy += 26
    d.text((margin_x, H - 34), "ConstruPilot — esquema de princípio desenhado a partir dos dados do processo; cotas em cm; a validar pelo projetista / gabinete de projeto antes da execução.", fill="#555555", font=f_small)
    out = io.BytesIO(); img.save(out, "PNG", optimize=True)
    return out.getvalue()

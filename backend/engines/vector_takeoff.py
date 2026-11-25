"""Medição vetorial por layers (OCG) de um processo PDF — determinística, folha a folha, layer a layer.

Porque existe: o Assistente lia as plantas como IMAGENS (read_document) e media à vista. Num projeto de execução vetorial
(ex.: 79 folhas, 60 layers por folha, tramas de acabamentos, quadros de áreas na legenda) isso perde layers inteiras,
falha as fachadas (revestimentos desenhados em alçado), a cerâmica, o gesso cartonado e a pintura.

Este motor lê o PRÓPRIO desenho vetorial do PDF:
  1. Escala da folha (legenda «ESCALA 1:100»), tipo de peça (planta, alçado, corte, mapa de vãos, acabamentos…).
  2. TODAS as layers (Optional Content) com, para cada uma: nº de objetos, comprimento de traços, comprimento de FACES
     (traços colineares fundidos: uma parede/um revestimento desenhado a 2 linhas conta uma vez), ÁREA DE TRAMA
     (família de linhas paralelas regulares: Σ comprimento × espaçamento — é assim que os acabamentos são desenhados),
     área de preenchimentos e de elementos retangulares (réguas, painéis), área bruta (fecho morfológico).
  3. Texto: quantidades DECLARADAS na legenda («PV3- Flutuante … - 142.80 M2»), quadro de compartimentos,
     pés-direitos, mapas de vãos (Ve/Vi/MF: quantidade, dimensão), equipamentos («- 2 Uni.»), etiquetas (Rv1, TT2, Ve7…).
  4. Cruzamento: a amostra de cor da legenda liga cada código à sua layer → área medida na trama vs área declarada.
  5. Cobertura: cada ficheiro, cada página e cada layer é listado como MEDIDO ou IGNORADO com o motivo — nada fica por ler
     sem o dizer.

Nada é inventado: um valor ausente fica ausente; cada número vem com a folha e a layer de origem.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

ENGINE_VERSION = "vt-2026.11.25-1"
PT_PER_M = 72 / 0.0254                     # pontos PDF por metro de papel
MAX_PAGES = 6                              # páginas analisadas por ficheiro (folhas A0/A1: 1 página; cadernos: as 6 primeiras)

# ---------------------------------------------------------------------------------------------------------------- layers
_IGNORE = [
    (r"veget|arvor|arbust|ambient|relva\b|jardim", "vegetação / ambientação"),
    (r"mobil|automov|carro|eletrodom|electrodom|pessoas|human|pelucia", "mobiliário / figuras / equipamento móvel"),
    (r"folha|legenda|carimbo|consultor|logo|moldura|frame|title", "folha / legenda / carimbo"),
    (r"cotag|\bcota|dimens|\bdim\b", "cotagem (lida como texto, não medida como obra)"),
    (r"texto|text\b|^txt|anota", "texto"),
    (r"aux|constru[cç][aã]o_?aux|defpoints|viewport|vport", "linhas auxiliares"),
    (r"terreno|curvas|nivel|topo|top_|limite|lote|cadastr", "terreno / topografia / limites"),
    (r"puxador|ferrag|batente|calha|perfil$|^eq$|^n \d", "ferragens / acessórios desenhados"),
    (r"pe[cç]as sanit|sanitar|lou[cç]a", "louças (contadas pelo mapa de acabamentos, não por desenho)"),
    (r"hatch_?bound|eixo|axis|grelha estrut", "eixos / construção"),
]
_IGNORE = [(re.compile(p, re.I), why) for p, why in _IGNORE]


def layer_role(name: str) -> tuple[str, str]:
    """('medido'|'ignorado', motivo). A layer '0'/'' é medida mas marcada como genérica (muitos ficheiros põem tudo lá)."""
    n = (name or "").strip()
    if n in ("", "0"):
        return "medido", "layer genérica (0 / sem layer): medida, atribuição ao acabamento a confirmar"
    for rx, why in _IGNORE:
        if rx.search(n):
            return "ignorado", why
    return "medido", ""


# ---------------------------------------------------------------------------------------------------------------- texto
SHEET_TYPES = [
    ("alcado", r"AL[ÇC]ADO|FACHADA|ELEVATION|FA[ÇC]ADE"),
    ("corte", r"\bCORTE\b|SEC[ÇC][ÃA]O|\bCOUPE\b"),
    ("mapa_vaos", r"V[ÃA]OS (EXTERIORES|INTERIORES)|MAPA DE V[ÃA]OS|CAIXILHARIA"),
    ("mapa_acabamentos", r"MAPA DE ACABAMENTOS"),
    ("planta_pavimentos", r"PLANTA DE PAVIMENTOS|PAVIMENTOS E RODAP"),
    ("planta_tetos", r"TETOS|TECTOS"),
    ("planta_iluminacao", r"ILUMINA[ÇC][ÃA]O"),
    ("planta_cobertura", r"PLANTA DE COBERTURA"),
    ("planta_implantacao", r"IMPLANTA[ÇC][ÃA]O"),
    ("planta", r"\bPLANTA\b"),
    ("pormenor", r"PORMENOR|DETALHE"),
    ("acabamentos_divisao", r"\bACABAMENTOS?\b|INSTALA[ÇC][ÃA]O SANIT"),
]
SHEET_TYPES = [(k, re.compile(p)) for k, p in SHEET_TYPES]

CODE_RX = re.compile(r"^(PV|Pv|pv|RV|Rv|rv|TT|Tt|TO|To|Ve|VE|Vi|VI|MF|Mf|Gr|GR|RP|Rp)\s?\.?\s?(\d{1,3})$")
DECL_RX = re.compile(r"^\s*((?:PV|RV|TT|TO|RP|Pv|Rv|Tt|To)\s?\d{1,3})\s*[-–—:]\s*(.+?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)\s*(M2|m2|M²|m²|ML|ml|M3|m3|UN|un|Uni\.?)\s*$", re.S)
ROOM_RX = re.compile(r"^\s*(\d{1,3})\s*\.\s*([^\d\n][^\n]*?)\s*[-–]\s*(\d+(?:[.,]\d+)?)\s*m[²2]\s*$", re.I)
HEIGHT_RX = re.compile(r"^\s*(\d[.,]\d{2})\s*m\s*$")
UNI_RX = re.compile(r"^(.*?)\s*[-–]\s*(\d+)\s*Uni\.?\s*$", re.I)
SPLIT_CODES_RX = re.compile(r"\s+(?=(?:PV|RV|TT|TO|RP|Pv|Rv|Tt|To)\s?\d{1,3}\s*[-–—])")
SCALE_RX = re.compile(r"ESCALA\s*[:\n ]*\s*1\s*[:/]\s*(\d{1,4})", re.I)
SCALE_ANY_RX = re.compile(r"(?<![\d.,])1\s*[:/]\s*(\d{2,4})(?![\d.,])")
DIM_RX = re.compile(r"(\d{2,4})\s*[xX×]\s*(\d{2,4})\s*cm")


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def norm_code(raw: str) -> str | None:
    m = CODE_RX.match(raw.strip())
    if not m:
        return None
    return f"{m.group(1).upper()}{int(m.group(2))}"


def _lines(page) -> list[dict]:
    out = []
    for b in page.get_text("dict").get("blocks", []):
        for ln in b.get("lines", []):
            t = "".join(s.get("text", "") for s in ln.get("spans", [])).strip()
            if t:
                out.append({"t": t, "bbox": ln["bbox"], "block": b.get("number")})
    return out


def _blocks(page) -> list[str]:
    return [b[4].replace("\n", " ").strip() for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]


def sheet_scale(text: str) -> tuple[int | None, str]:
    m = SCALE_RX.search(text)
    if m:
        return int(m.group(1)), "legenda «ESCALA»"
    c = Counter(int(x) for x in SCALE_ANY_RX.findall(text) if 5 <= int(x) <= 5000)
    if c:
        return c.most_common(1)[0][0], "texto «1:N» na folha (sem rótulo ESCALA)"
    return None, "escala não encontrada"


def sheet_title(lines: list[dict], full: str) -> tuple[str, str]:
    up = full.upper()
    title = ""
    for ln in lines:
        t = ln["t"].strip()
        if t.isupper() and 6 <= len(t) <= 80 and re.search(r"PLANTA|AL[ÇC]ADO|CORTE|MAPA|PORMENOR|ACABAMENTO|V[ÃA]OS|INSTALA", t):
            title = t
            break
    for kind, rx in SHEET_TYPES:
        if rx.search(title.upper() if title else up):
            return kind, title
    for kind, rx in SHEET_TYPES:
        if rx.search(up):
            return kind, title
    return "outro", title


def parse_text(page, lines: list[dict]) -> dict:
    full = page.get_text()
    blocks = _blocks(page)
    tags = Counter()
    tag_pos = defaultdict(list)
    for ln in lines:
        c = norm_code(ln["t"])
        if c:
            tags[c] += 1
            if len(tag_pos[c]) < 80:
                x0, y0, x1, y1 = ln["bbox"]
                tag_pos[c].append((round((x0 + x1) / 2, 1), round((y0 + y1) / 2, 1)))
    declared = []
    pieces = []
    for b in blocks + [ln["t"] for ln in lines]:
        pieces += [x for x in SPLIT_CODES_RX.split(b) if x.strip()]
    for b in pieces:
        m = DECL_RX.match(b)
        if m:
            code = norm_code(m.group(1))
            if code and not any(d["codigo"] == code and abs(d["valor"] - _num(m.group(3))) < 1e-6 for d in declared):
                declared.append({"codigo": code, "descricao": re.sub(r"\s+", " ", m.group(2)).strip(" -"),
                                 "valor": _num(m.group(3)), "unidade": m.group(4).upper().replace("²", "2").replace("UNI.", "UN").replace("UNI", "UN")})
    rooms = {}
    for ln in lines:
        m = ROOM_RX.match(ln["t"])
        if m:
            rooms[int(m.group(1))] = {"n": int(m.group(1)), "nome": m.group(2).strip(), "area_m2": _num(m.group(3))}
    heights = Counter(_num(m.group(1)) for ln in lines for m in [HEIGHT_RX.match(ln["t"])] if m)
    units = []
    for b in blocks:
        for part in re.split(r"(?<=Uni\.)\s+", b):
            m = UNI_RX.match(part.strip())
            if m and len(m.group(1)) > 3:
                units.append({"descricao": re.sub(r"\s+", " ", m.group(1)).strip(" -|"), "quantidade": int(m.group(2))})
    # descrições dos códigos (mapa de acabamentos: código e descrição na mesma linha de base, descrição à direita)
    descr = {}
    for ln in lines:
        c = norm_code(ln["t"])
        if not c:
            continue
        x0, y0, x1, y1 = ln["bbox"]
        cy = (y0 + y1) / 2
        best = None
        for o in lines:
            ox0, oy0, ox1, oy1 = o["bbox"]
            if o is ln or ox0 < x1 or ox0 - x1 > 420 or abs((oy0 + oy1) / 2 - cy) > max(2.5, (y1 - y0) * 0.45):
                continue
            if norm_code(o["t"]) or len(o["t"]) < 6:
                continue
            if best is None or ox0 < best[0]:
                best = (ox0, o["t"])
        if best and c not in descr:
            descr[c] = best[1]
    sched = parse_schedule(full)
    return {"full": full, "tags": dict(tags), "tag_pos": dict(tag_pos), "declared": declared, "rooms": sorted(rooms.values(), key=lambda r: r["n"]),
            "heights": {f"{k:.2f}": v for k, v in sorted(heights.items())}, "units": units, "descricoes": descr, "schedule": sched,
            "callouts": [b for b in blocks if re.search(r"(?i)revestimento|etic|caixilharia|zinco|reboco|pintura|cer[âa]mic|pedra|madeira|painel|chapa|capoto|isolamento", b) and len(b) < 140][:40]}


def parse_schedule(full: str) -> dict | None:
    """Folha de mapa de vãos / móveis: DESIGNAÇÃO Ve 1 | QUANTIDADES 01 | DIMENSÃO 295 x 244 cm | LOCALIZAÇÃO …"""
    m = re.search(r"DESIGNA[ÇC][ÃA]O\s*\n\s*((?:Ve|Vi|MF|Gr)\s*\.?\s*\d+)", full)
    if not m:
        return None
    code = norm_code(m.group(1).replace(" ", ""))
    q = re.search(r"QUANTIDADES?\s*\n\s*(\d+)", full)
    d = DIM_RX.search(full.split("DIMENS")[-1]) if "DIMENS" in full else None
    func = re.search(r"FUNCIONAMENTO\s*\n\s*([^\n]+)", full)
    loc = re.search(r"LOCALIZA[ÇC][ÃA]O\s*\n\s*([^\n]+)", full)
    mat = re.search(r"ACABAMENTO\s*\n\s*([^\n]+)", full)
    out = {"codigo": code, "quantidade": int(q.group(1)) if q else None,
           "dimensao_cm": f"{d.group(1)} x {d.group(2)}" if d else None,
           "dim1_m": int(d.group(1)) / 100 if d else None, "dim2_m": int(d.group(2)) / 100 if d else None,
           "descricao": func.group(1).strip() if func else "", "material": mat.group(1).strip() if mat else "",
           "localizacao": loc.group(1).strip() if loc else ""}
    if out["dim1_m"] and out["dim2_m"] and out["quantidade"]:
        out["area_unit_m2"] = round(out["dim1_m"] * out["dim2_m"], 3)
        out["area_total_m2"] = round(out["area_unit_m2"] * out["quantidade"], 3)
    return out


# ---------------------------------------------------------------------------------------------------------------- geometria
def _quad_pts(q):
    ul, ur, ll, lr = q
    return [ul, ur, lr, ll]


def _rings(items) -> list[list]:
    rings, cur, last = [], [], None
    for it in items:
        k = it[0]
        if k == "re":
            x0, y0, x1, y1 = it[1]
            rings.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
            last = None
            continue
        if k == "qu":
            rings.append(_quad_pts(it[1]))
            last = None
            continue
        a, b = it[1], it[-1]
        if last is None or abs(a[0] - last[0]) > 1e-3 or abs(a[1] - last[1]) > 1e-3:
            if len(cur) >= 3:
                rings.append(cur)
            cur = [a]
        if k == "c":
            p0, p1, p2, p3 = it[1], it[2], it[3], it[4]
            for t in (0.25, 0.5, 0.75, 1.0):
                u = 1 - t
                cur.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                            u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
        else:
            cur.append(b)
        last = b
    if len(cur) >= 3:
        rings.append(cur)
    return rings


def _segments(items) -> list[tuple]:
    segs = []
    for it in items:
        k = it[0]
        if k == "l":
            segs.append((*it[1], *it[2]))
        elif k == "c":
            segs.append((*it[1], *it[4]))
        elif k == "re":
            x0, y0, x1, y1 = it[1]
            segs += [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]
        elif k == "qu":
            p = _quad_pts(it[1])
            segs += [(*p[i], *p[(i + 1) % 4]) for i in range(4)]
    return segs


def hatch_families(segs: list[tuple], m_per_pt: float, min_lines: int = 8) -> list[dict]:
    """Famílias de linhas paralelas regularmente espaçadas (tramas). Área = Σ comprimento × espaçamento modal.
    Só é aceite uma família cujo espaçamento é regular (≥ 60 % dos intervalos a ±20 % do modal, ou seus múltiplos)."""
    import numpy as np
    fam = defaultdict(list)
    for x0, y0, x1, y1 in segs:
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-6:
            continue
        ang = round(math.degrees(math.atan2(y1 - y0, x1 - x0))) % 180
        fam[ang].append((x0, y0, L))
    out = []
    for ang, ls in fam.items():
        if len(ls) < min_lines:
            continue
        th = math.radians(ang)
        nx, ny = -math.sin(th), math.cos(th)
        offs = np.unique(np.round(np.array([a * nx + b * ny for a, b, _ in ls]), 2))
        if len(offs) < min_lines:
            continue
        d = np.diff(offs)
        d = d[d > 0.05]
        if len(d) < min_lines - 1:
            continue
        # espaçamento modal (histograma fino)
        vals, counts = np.unique(np.round(d, 1), return_counts=True)
        sp = float(vals[np.argmax(counts)])
        if sp <= 0:
            continue
        ratio = d / sp
        regular = float(np.mean(np.abs(ratio - np.round(ratio)) < 0.2 * np.maximum(1, np.round(ratio)) / np.maximum(1, np.round(ratio))))
        share_modal = float(np.mean(np.abs(d - sp) <= 0.2 * sp))
        if share_modal < 0.5 or regular < 0.6:
            continue
        tot = sum(l for _, _, l in ls)
        out.append({"angulo_graus": int(ang), "linhas": len(ls), "espacamento_m": round(sp * m_per_pt, 4),
                    "comprimento_m": round(tot * m_per_pt, 2), "area_m2": round(tot * sp * m_per_pt * m_per_pt, 2),
                    "regularidade": round(share_modal, 2)})
    out.sort(key=lambda f: -f["area_m2"])
    return out


def face_length(segs: list[tuple], tol_pt: float) -> float:
    """Comprimento de faces: segmentos colineares/sobrepostos fundidos e linhas paralelas a menos de tol (2 linhas de um
    mesmo revestimento/parede fina) contadas uma vez. Devolve o comprimento em pontos."""
    groups = defaultdict(list)
    for x0, y0, x1, y1 in segs:
        L = math.hypot(x1 - x0, y1 - y0)
        if L < tol_pt * 0.5:
            continue
        ang = round(math.degrees(math.atan2(y1 - y0, x1 - x0))) % 180
        th = math.radians(ang)
        ux, uy, nx, ny = math.cos(th), math.sin(th), -math.sin(th), math.cos(th)
        off = x0 * nx + y0 * ny
        a, b = sorted((x0 * ux + y0 * uy, x1 * ux + y1 * uy))
        groups[ang].append((off, a, b))
    total = 0.0
    for ang, rows in groups.items():
        rows.sort()
        # agrupa os offsets próximos (< tol) num mesmo «alinhamento»
        clusters, cur, start = [], [], None
        for r in rows:
            if cur and r[0] - start > tol_pt:
                clusters.append(cur)
                cur = []
            if not cur:
                start = r[0]
            cur.append(r)
        if cur:
            clusters.append(cur)
        for cl in clusters:
            iv = sorted((a, b) for _, a, b in cl)
            s0, e0 = iv[0]
            for a, b in iv[1:]:
                if a <= e0 + tol_pt * 0.2:
                    e0 = max(e0, b)
                else:
                    total += e0 - s0
                    s0, e0 = a, b
            total += e0 - s0
    return total


def _union_area(polys, gap_pt: float = 0.0) -> tuple[float, float]:
    """(área líquida da união, área bruta após fecho morfológico de gap_pt) em pt²."""
    import shapely
    from shapely.geometry import Polygon
    geoms = []
    for p in polys:
        try:
            g = Polygon(p)
            if not g.is_valid:
                g = g.buffer(0)
            if not g.is_empty and g.area > 0:
                geoms.append(g)
        except Exception:  # noqa: BLE001 — anel degenerado
            continue
    if not geoms:
        return 0.0, 0.0
    u = shapely.union_all(geoms)
    net = u.area
    gross = u.buffer(gap_pt, join_style="mitre").buffer(-gap_pt, join_style="mitre").area if gap_pt > 0 else net
    return net, gross


def outline_area(segs: list[tuple], r_pt: float) -> float:
    """Área envolvida pelos traços de uma layer (silhueta): traços engrossados de r, buracos preenchidos, erosão de r.
    Num alçado dá a superfície de fachada desenhada por essa layer (fundo/máscara, revestimento, vãos)."""
    import shapely
    from shapely.geometry import LineString, Polygon
    lines = [LineString([(a, b), (c, d)]).buffer(r_pt, cap_style="square") for a, b, c, d in segs if abs(a - c) + abs(b - d) > 1e-6]
    if not lines:
        return 0.0
    g = shapely.union_all(lines)
    polys = [Polygon(x.exterior) for x in getattr(g, "geoms", [g]) if hasattr(x, "exterior")]
    return shapely.union_all(polys).buffer(-r_pt).area if polys else 0.0


# ---------------------------------------------------------------------------------------------------------------- página
def analyze_page(page, page_number: int = 1) -> dict:
    lines = _lines(page)
    txt = parse_text(page, lines)
    full = txt.pop("full")
    scale, scale_src = sheet_scale(full)
    kind, title = sheet_title(lines, full)
    W, H = page.rect.width, page.rect.height
    page_area = W * H
    m_per_pt = (scale / PT_PER_M) if scale else None
    raw_layers = {v["name"] for v in (page.parent.get_ocgs() or {}).values()}
    per = defaultdict(lambda: {"objetos": 0, "segs": [], "fills": [], "closed": [], "cores": Counter(), "por_cor": defaultdict(list)})
    swatches = []
    for d in page.get_cdrawings():
        L = d.get("layer") or ""
        e = per[L]
        e["objetos"] += 1
        items = d.get("items") or []
        x0, y0, x1, y1 = d["rect"]
        big = (x1 - x0) * (y1 - y0) > 0.5 * page_area
        if "s" in d.get("type", "") and not big:
            sg = _segments(items)
            e["segs"].extend(sg)
            if d.get("color"):
                col = tuple(round(c, 2) for c in d["color"])
                e["cores"][col] += 1
                e["por_cor"][col].extend(sg)
        if not big:
            if d.get("fill") is not None and "f" in d.get("type", ""):
                rs = _rings(items)
                e["fills"].extend(rs)
                if rs and (x1 - x0) * (y1 - y0) < 0.004 * page_area:
                    swatches.append((L, (x0, y0, x1, y1), tuple(round(c, 2) for c in d["fill"])))
            else:
                for it in items:
                    if it[0] == "qu":
                        e["closed"].append(_quad_pts(it[1]))
                    elif it[0] == "re":
                        a0, b0, a1, b1 = it[1]
                        e["closed"].append([(a0, b0), (a1, b0), (a1, b1), (a0, b1)])
    layers = []
    for name in sorted(set(per) | raw_layers):
        e = per.get(name)
        role, why = layer_role(name)
        row = {"layer": name or "(sem layer)", "estado": role, "motivo": why, "objetos": e["objetos"] if e else 0}
        if not e or not e["objetos"]:
            row.update(estado="vazio", motivo="layer declarada no PDF sem objetos nesta página")
            layers.append(row)
            continue
        if role == "medido" and m_per_pt:
            segs = e["segs"]
            row["comprimento_tracos_m"] = round(sum(math.hypot(a - c, b - d) for a, b, c, d in segs) * m_per_pt, 2)
            fams = hatch_families(segs, m_per_pt) if len(segs) >= 8 else []
            if fams:
                row["trama"] = fams[0]
                if len(fams) > 1:
                    row["tramas_secundarias"] = fams[1:3]
            # faces: traços fora da família de trama principal
            if fams and fams[0]["regularidade"] >= 0.5:
                ang = fams[0]["angulo_graus"]
                rest = [s for s in segs if round(math.degrees(math.atan2(s[3] - s[1], s[2] - s[0]))) % 180 != ang]
            else:
                rest = segs
            if len(rest) <= 60000:
                row["comprimento_faces_m"] = round(face_length(rest, 0.035 / m_per_pt) * m_per_pt, 2)
            if e["fills"] and len(e["fills"]) <= 40000:
                net, gross = _union_area(e["fills"], 0.05 / m_per_pt)
                row["area_preenchida_m2"] = round(net * m_per_pt ** 2, 2)
                row["area_preenchida_bruta_m2"] = round(gross * m_per_pt ** 2, 2)
            elif e["fills"]:
                row["area_preenchida_m2"] = None
                row["nota"] = f"{len(e['fills'])} preenchimentos: união não calculada (volume), ver tramas"
            if e["closed"] and len(e["closed"]) <= 40000:
                net, gross = _union_area(e["closed"], 0.05 / m_per_pt)
                row["area_retangulos_m2"] = round(net * m_per_pt ** 2, 2)
                row["area_retangulos_bruta_m2"] = round(gross * m_per_pt ** 2, 2)
                row["retangulos"] = len(e["closed"])
        if role == "medido" and m_per_pt and kind in ("alcado", "corte") and e["segs"] and len(e["segs"]) <= 60000:
            row["area_contorno_m2"] = round(outline_area(e["segs"], 0.10 / m_per_pt) * m_per_pt ** 2, 2)
        layers.append(row)
    # amostras da legenda: para cada linha «CÓDIGO- descrição», a amostra (pequeno preenchimento de uma layer) mais próxima à esquerda
    legend_map = {}
    sw = [(L, r, col) for L, r, col in swatches if layer_role(L)[0] == "medido" and L not in ("", "0")
          and (r[2] - r[0]) < 60 and (r[3] - r[1]) < 30]
    for ln in lines:
        m = re.match(r"\s*((?:PV|RV|TT|TO|RP|Pv|Rv|Tt|To)\s?\d{1,3})\s*[-–—]", ln["t"])
        if not m:
            continue
        code = norm_code(m.group(1))
        lx0, ly0, lx1, ly1 = ln["bbox"]
        cy = (ly0 + ly1) / 2
        best = None
        for L, (x0, y0, x1, y1), col in sw:
            gap = lx0 - x1
            if -2 <= gap <= 60 and abs((y0 + y1) / 2 - cy) <= max(3.0, (ly1 - ly0) * 0.6):
                key = (abs((y0 + y1) / 2 - cy) + gap * 0.1, "area" in L.lower())
                if best is None or key < best[0]:
                    best = (key, L, col)
        if code and best and code not in legend_map:
            L, col = best[1], best[2]
            entry = {"layer": L, "cor": list(col)}
            e = per.get(L)
            if e and m_per_pt:
                # a mesma layer pode ter várias cores (ex.: «teto 3.00» = TT3 e TT4): mede-se só a trama da cor da amostra
                cands = [(sum(abs(a - b) for a, b in zip(c, col)), c) for c in e["por_cor"]]
                cands = [c for c in cands if c[0] <= 0.12]
                if len(e["por_cor"]) > 1 and cands:
                    segs = e["por_cor"][min(cands)[1]]
                    entry["medicao_por_cor"] = True
                else:
                    segs = e["segs"]
                fams = hatch_families(segs, m_per_pt) if len(segs) >= 8 else []
                if fams:
                    entry["trama"] = fams[0]
            legend_map[code] = entry
    return {"pagina": page_number, "tipo": kind, "titulo": title, "escala": scale, "escala_origem": scale_src,
            "formato_pt": [round(W), round(H)], "layers": layers, "legenda_layers": legend_map, **txt}


def analyze_pdf(data: bytes, max_pages: int = MAX_PAGES) -> dict:
    import pymupdf
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "erro": f"PDF ilegível: {exc}"[:200], "versao": ENGINE_VERSION}
    pages = []
    with doc:
        n = len(doc)
        for i in range(min(n, max_pages)):
            try:
                pages.append(analyze_page(doc[i], i + 1))
            except Exception as exc:  # noqa: BLE001 — uma página com erro não anula as outras e fica assinalada
                pages.append({"pagina": i + 1, "erro": f"{type(exc).__name__}: {exc}"[:200]})
        layers_pdf = sorted({v["name"] for v in (doc.get_ocgs() or {}).values()})
    return {"ok": True, "versao": ENGINE_VERSION, "paginas_total": n, "paginas_analisadas": len(pages),
            "paginas_nao_analisadas": max(0, n - len(pages)), "layers_pdf": layers_pdf, "paginas": pages}


# ---------------------------------------------------------------------------------------------------------------- processo
PARTS = {
    "pavimentos": ("PV",), "paredes_revestimentos": ("RV",), "paredes_tosco": ("TO",), "tetos": ("TT",),
    "rodapes": ("RP",), "vaos_exteriores": ("VE",), "vaos_interiores": ("VI",), "moveis_fixos": ("MF",), "guardas": ("GR",),
}


def _part_of(code: str) -> str:
    p = re.match(r"[A-Z]+", code).group(0)
    for k, prefixes in PARTS.items():
        if p in prefixes:
            return k
    return "outros"


def aggregate(files: list[dict]) -> dict:
    """files: [{doc_id, filename, result}] → mapa do processo (declarado, medido, cruzamento, cobertura)."""
    cobertura, declared, descr, rooms, heights, sched, units = [], defaultdict(list), {}, {}, Counter(), {}, []
    tags_plan = Counter()
    fachadas, cruzamento, paredes_faces = [], [], []
    for f in files:
        r = f.get("result") or {}
        row = {"doc_id": f.get("doc_id"), "ficheiro": f.get("filename")}
        if not r.get("ok"):
            row.update(estado="ERRO", detalhe=r.get("erro") or "não analisado")
            cobertura.append(row)
            continue
        lay_med = lay_ign = lay_vaz = 0
        tipos = []
        for p in r["paginas"]:
            if p.get("erro"):
                row.setdefault("erros_paginas", []).append(p)
                continue
            tipos.append(p["tipo"])
            src = f"{f.get('filename')} p.{p['pagina']}"
            for l in p["layers"]:
                lay_med += l["estado"] == "medido"
                lay_ign += l["estado"] == "ignorado"
                lay_vaz += l["estado"] == "vazio"
            for d in p["declared"]:
                if not any(abs(x["valor"] - d["valor"]) < 1e-6 and x["unidade"] == d["unidade"] for x in declared[d["codigo"]]):
                    declared[d["codigo"]].append({**d, "origem": src})
            for k, v in p["descricoes"].items():
                descr.setdefault(k, v)
            for rm in p["rooms"]:
                rooms.setdefault(rm["n"], {**rm, "origem": src})
            heights.update(p["heights"])
            if p.get("schedule") and p["schedule"].get("codigo"):
                sched[p["schedule"]["codigo"]] = {**p["schedule"], "origem": src}
            for u in p["units"]:
                units.append({**u, "origem": src})
            if p["tipo"].startswith("planta") and p["tipo"] not in ("planta_implantacao",):
                for c, n in p["tags"].items():
                    if re.match(r"VE|VI|MF|GR", c):
                        tags_plan[(c, src)] = n
            med = [l for l in p["layers"] if l["estado"] == "medido"]
            # cruzamento legenda ↔ trama
            for code, ent in p["legenda_layers"].items():
                layer = ent["layer"]
                l = next((x for x in med if x["layer"] == layer), None)
                decl = next((d for d in p["declared"] if d["codigo"] == code), None)
                if l:
                    meas = (ent.get("trama") or {}).get("area_m2")
                    if not meas:
                        meas = l.get("area_preenchida_m2") or l.get("area_retangulos_m2")
                    item = {"codigo": code, "layer": layer, "folha": src, "medido_m2": meas, "metodo": "trama da cor da legenda" if ent.get("medicao_por_cor") else "trama da layer",
                            "declarado_m2": decl["valor"] if decl else None}
                    if meas and decl and decl["valor"]:
                        item["diferenca_pct"] = round((meas - decl["valor"]) / decl["valor"] * 100, 1)
                        item["estado"] = "CONFERE" if abs(item["diferenca_pct"]) <= 3 else ("PRÓXIMO" if abs(item["diferenca_pct"]) <= 8 else "DIVERGE — verificar")
                    cruzamento.append(item)
            if p["tipo"] == "alcado":
                fachadas.append({"folha": src, "titulo": p["titulo"], "escala": p["escala"], "anotacoes": p["callouts"][:12],
                                 "layers": [{k: l.get(k) for k in ("layer", "area_contorno_m2", "area_retangulos_m2", "area_retangulos_bruta_m2", "area_preenchida_m2",
                                                                    "area_preenchida_bruta_m2", "trama", "comprimento_faces_m") if l.get(k) not in (None, 0, 0.0)}
                                            for l in med if (l.get("area_retangulos_m2") or 0) + (l.get("area_preenchida_m2") or 0)
                                            + ((l.get("trama") or {}).get("area_m2") or 0) + (l.get("area_contorno_m2") or 0) >= 0.5]})
            if p["tipo"] == "planta":
                paredes_faces.append({"folha": src, "faces": [{"layer": l["layer"], "comprimento_faces_m": l.get("comprimento_faces_m"),
                                                               "area_trama_m2": (l.get("trama") or {}).get("area_m2")}
                                                              for l in med if (l.get("comprimento_faces_m") or 0) >= 1]})
        row.update(estado="LIDO", tipos=sorted(set(tipos)), paginas=r["paginas_analisadas"], paginas_nao_analisadas=r["paginas_nao_analisadas"],
                   layers_medidas=lay_med, layers_ignoradas=lay_ign, layers_vazias=lay_vaz)
        cobertura.append(row)
    # quantidades declaradas por parte
    partes = defaultdict(list)
    for code, vals in sorted(declared.items()):
        v = vals[0]
        partes[_part_of(code)].append({"codigo": code, "descricao": v["descricao"] or descr.get(code, ""), "quantidade": v["valor"],
                                       "unidade": v["unidade"], "origem": v["origem"], "fonte": "declarado no projeto",
                                       **({"valores_divergentes": vals[1:]} if len(vals) > 1 else {})})
    # ordem «L × A» ou «A × L» do mapa: decidida pelas fichas sem ambiguidade (uma só dimensão entre 1,80 e 3,20 m = altura)
    votes = Counter()
    for s in sched.values():
        if s.get("dim1_m") and s.get("dim2_m") and s["codigo"][:2] in ("VE", "VI"):
            a, b = 1.8 <= s["dim1_m"] <= 3.2, 1.8 <= s["dim2_m"] <= 3.2
            if a != b:
                votes["AxL" if a else "LxA"] += 1
    conv = votes.most_common(1)[0][0] if votes else "LxA"
    for s in sched.values():
        if s.get("dim1_m") and s.get("dim2_m"):
            h_first = conv == "AxL"
            if s["codigo"][:2] in ("VE", "VI"):
                a, b = 1.8 <= s["dim1_m"] <= 3.2, 1.8 <= s["dim2_m"] <= 3.2
                if a != b:
                    h_first = a
            s["altura_m"], s["largura_m"] = (s["dim1_m"], s["dim2_m"]) if h_first else (s["dim2_m"], s["dim1_m"])
        else:
            s["altura_m"] = s["largura_m"] = None
    for code, s in sorted(sched.items()):
        plan_n = sum(n for (c, _), n in tags_plan.items() if c == code)
        item = {"codigo": code, "descricao": s["descricao"], "material": s["material"], "quantidade": s["quantidade"], "unidade": "UN",
                "dimensao_cm": s.get("dimensao_cm"), "largura_m": s["largura_m"], "altura_m": s["altura_m"], "area_total_m2": s.get("area_total_m2"),
                "localizacao": s["localizacao"], "origem": s["origem"], "fonte": "mapa de vãos/móveis",
                "etiquetas_em_planta": plan_n or None}
        if plan_n and s["quantidade"] and plan_n != s["quantidade"]:
            item["alerta"] = f"mapa indica {s['quantidade']} un, planta mostra {plan_n} etiqueta(s): confirmar"
        partes[_part_of(code)].append(item)
    eq = Counter()
    eq_src = {}
    for u in units:
        k = u["descricao"]
        eq[k] += u["quantidade"]
        eq_src.setdefault(k, []).append(u["origem"])
    if eq:
        partes["loucas_equipamentos"] = [{"descricao": k, "quantidade": v, "unidade": "UN", "origem": "; ".join(sorted(set(eq_src[k])))[:200],
                                          "fonte": "fichas de acabamentos por divisão"} for k, v in eq.items()]
    codes_without_qty = sorted({c for c in descr if c not in declared and c not in sched and re.match(r"PV|RV|TT|TO", c)})
    total_files = len(files)
    lidos = sum(1 for c in cobertura if c["estado"] == "LIDO")
    return {
        "ok": True, "versao": ENGINE_VERSION,
        "cobertura": {"ficheiros": total_files, "lidos": lidos, "com_erro": total_files - lidos,
                      "layers_medidas": sum(c.get("layers_medidas", 0) for c in cobertura),
                      "layers_ignoradas_com_motivo": sum(c.get("layers_ignoradas", 0) for c in cobertura),
                      "completo": lidos == total_files and all(not c.get("paginas_nao_analisadas") for c in cobertura if c["estado"] == "LIDO"),
                      "detalhe": cobertura},
        "ordem_dimensoes_mapa_vaos": {"AxL": "altura × largura", "LxA": "largura × altura"}[conv] + f" (deduzida de {sum(votes.values())} fichas)",
        "codigos_acabamentos": descr,
        "quantidades_por_parte": dict(partes),
        "codigos_sem_quantidade_declarada": [{"codigo": c, "descricao": descr[c], "parte": _part_of(c)} for c in codes_without_qty],
        "cruzamento_legenda_vs_desenho": cruzamento,
        "fachadas_por_alcado": fachadas,
        "faces_em_planta": paredes_faces,
        "compartimentos": sorted(rooms.values(), key=lambda r: r["n"]),
        "pes_direitos_m": dict(heights),
    }


# ---------------------------------------------------------------------------------------------------------------- vista por layers
def render_layers(data: bytes, page_number: int, show: list[str] | None, hide: list[str] | None,
                  box: list[float] | None = None, max_px: int = 2200, highlight: list[str] | None = None) -> tuple[bytes, dict]:
    """Imagem PNG da página com SÓ as layers pedidas visíveis (show) ou sem as layers indicadas (hide).
    Permite verificar visualmente o que cada layer desenha (ex.: só o revestimento de fachada, só as tramas de teto)."""
    import pymupdf
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if not 1 <= page_number <= len(doc):
            raise ValueError(f"Página inexistente: documento de {len(doc)} página(s)")
        cfg = doc.layer_ui_configs() or []
        names = [c["text"] for c in cfg]
        want = {n.casefold() for n in (show or [])}
        drop = {n.casefold() for n in (hide or [])}
        unknown = sorted((set(show or []) | set(hide or []) | set(highlight or [])) - set(names), key=str.casefold)
        unknown = [u for u in unknown if u.casefold() not in {n.casefold() for n in names}]
        visible = []
        for c in cfg:
            on = (c["text"].casefold() in want) if want else (c["text"].casefold() not in drop)
            doc.set_layer_ui_config(c["number"], 0 if on else 2)   # 0 = ligar, 2 = desligar
            if on:
                visible.append(c["text"])
        page = doc[page_number - 1]
        hl = {n.casefold() for n in (highlight or [])}
        drawn = 0
        if hl:
            shape = page.new_shape()
            for d in page.get_cdrawings():
                if (d.get("layer") or "").casefold() not in hl:
                    continue
                x0, y0, x1, y1 = d["rect"]
                if (x1 - x0) * (y1 - y0) > 0.5 * page.rect.width * page.rect.height:
                    continue
                items = d.get("items") or []
                if d.get("fill") is not None and "f" in d.get("type", ""):
                    for ring in _rings(items):
                        shape.draw_polyline(ring + [ring[0]])
                        shape.finish(color=(0.85, 0, 0), fill=(1, 0.25, 0.25), fill_opacity=0.45, width=0.6)
                        drawn += 1
                for a, b, c, e in _segments(items):
                    shape.draw_line((a, b), (c, e))
                    drawn += 1
                if drawn and drawn % 2000 == 0:
                    shape.finish(color=(0.9, 0, 0), width=0.9)
            shape.finish(color=(0.9, 0, 0), width=0.9)
            shape.commit(overlay=True)
        clip = None
        if box:
            x0, y0, x1, y1 = box
            if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                raise ValueError("Zona inválida (x0<x1, y0<y1, entre 0 e 1)")
            r = page.rect
            clip = pymupdf.Rect(r.width * x0, r.height * y0, r.width * x1, r.height * y1)
        area = clip or page.rect
        zoom = min(8.0, max_px / max(area.width, area.height, 1))
        png = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False).tobytes("png")
    out = {"layers_visiveis": visible if len(visible) <= 80 else len(visible), "layers_desconhecidas": unknown, "layers_do_pdf": len(names)}
    if hl:
        out["objetos_destacados"] = drawn
    return png, out

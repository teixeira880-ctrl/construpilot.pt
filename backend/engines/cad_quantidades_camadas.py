"""Medição REAL por camadas de um DWG/DXF de implantação/arranjos exteriores.

14/11 (Valpaços): o mapa de quantidades saía com «Edifício 1775 m² × 1000 €», lotes e cadeias de cotas — nenhuma
quantidade de material. O desenho tinha as camadas certas (SMC_PAV BETUMINOSO, SMC_PAV PAVE DRENANTE, LANCIL,
SMC_EDIF ESP VERDES…) e ninguém as media. Este motor mede-as:

- ÁREAS: tramas (HATCH) da camada, área líquida (ilhas descontadas); se a camada não tem tramas, polilinhas fechadas.
- COMPRIMENTOS: linhas/polilinhas/arcos abertos; elementos desenhados com DUAS linhas paralelas (lancil: face e
  tardoz, 5–40 cm de afastamento) contam uma vez — senão o comprimento duplicava.
- CONTAGENS: blocos (candeeiros, hidrantes, sumidouros…).
- UNIDADES: o $INSUNITS declarado é confrontado com as áreas ESCRITAS no desenho («1481.55 m²»); se a área medida
  só coincide com outro fator (desenho em metros declarado em mm — o caso de Valpaços), usa-se esse fator e diz-se.

Nada é inventado: cada linha traz a camada, o tipo de entidade e o número de objetos medidos. Camadas sem material
no nome, ou de levantamento topográfico (existente), ficam listadas à parte, sem orçamento.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict

from engines.cad_geometry import hatch_area, polyline_length_area, walk_entities

VERSAO = 2
_FATORES = {"mm": 0.001, "cm": 0.01, "m": 1.0}
_INSUNITS = {4: "mm", 5: "cm", 6: "m"}


def _n(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[_\-.$]+", " ", s)


# (id, regex sobre o nome normalizado da camada, medida, capítulo, designação do artigo, material/descrição)
# A designação usa palavras que o mapa de materiais reconhece (betuminoso, pavê, lancil…).
CLASSES = [
    ("betuminoso", r"betumin|asfalt|enrobe", "area", ("Pavimentos", "Chaussées"), ("Pavimento betuminoso", "Chaussée en enrobé bitumineux"),
     ("Pavimento em mistura betuminosa", "Revêtement en enrobé bitumineux")),
    ("pave_drenante", r"pave.*(drenan|permeav|permeab)|(drenan|permeav|permeab).*pave|grelha.*enrelv|betao.*drenan|evergreen", "area",
     ("Pavimentos", "Chaussées"), ("Pavimento em pavê drenante/permeável", "Revêtement en pavés béton drainants/perméables"),
     ("Blocos de betão (pavê) drenantes/permeáveis", "Pavés béton drainants/perméables")),
    ("pave", r"\bpave\b|\bpaves\b|cubo|calcada|blocos? (de )?betao", "area", ("Pavimentos", "Chaussées"),
     ("Pavimento em pavê", "Revêtement en pavés béton"), ("Blocos de betão (pavê)", "Pavés béton")),
    ("verde", r"esp(acos)? verdes|zona verde|relva|relvado|ajardin|paisag.*verde|espaces? verts?|gazon|pelouse|verde", "area",
     ("Espaços verdes", "Espaces verts"), ("Espaços verdes — relvado/ajardinado", "Espaces verts — engazonnement"),
     ("Terra vegetal, sementeira e fertilização", "Terre végétale, semis et fertilisation")),
    ("lancil", r"lancil|lancis|guia|bordure", "comprimento", ("Lancis e remates", "Bordures"), ("Lancil", "Bordure béton"),
     ("Lancil de betão", "Bordure en béton")),
    ("vedacao", r"vedac|cloture", "comprimento", ("Vedações", "Clôtures"), ("Vedação", "Clôture"),
     ("Vedação (tipo a definir)", "Clôture (type à définir)")),
    ("muro", r"\bmuro|muret|\bmur\b", "comprimento", ("Muros", "Murets"), ("Muro", "Muret"), ("Muro (secção a definir)", "Muret (section à définir)")),
    ("pintura_rodov", r"pint(ura)? rodov|marca(s|cao)? rodov|mrodov|sinaliza(cao)? horiz|passadeira|marquage", "area",
     ("Sinalização", "Signalisation"), ("Marcação rodoviária (área pintada)", "Marquage au sol (surface peinte)"),
     ("Tinta de marcação rodoviária", "Peinture de marquage routier")),
    ("candeeiro", r"candeeiro|poste luz|ilumina|luminaria|eclairage|candelabre|mat d.eclairage", "contagem",
     ("Iluminação exterior", "Éclairage extérieur"), ("Candeeiro de iluminação exterior", "Candélabre d'éclairage extérieur"),
     ("Coluna e luminária", "Mât et luminaire")),
    ("hidrante", r"hidrante|marco (de )?incendio|bouche incendie|poteau incendie", "contagem", ("Redes", "Réseaux"),
     ("Hidrante / marco de incêndio", "Poteau / bouche d'incendie"), ("Hidrante", "Poteau d'incendie")),
    ("sumidouro", r"sumidouro|sarjeta|grelha de pavimento|avaloir", "contagem", ("Drenagem", "Assainissement"),
     ("Sumidouro / sarjeta", "Avaloir / grille"), ("Sumidouro", "Avaloir")),
]
# camadas de LEVANTAMENTO topográfico (existente): não são obra a orçamentar
_LEVANTAMENTO = re.compile(r"levant|topo|existente|exist\b|\bex\b|cadastr|_levantamento")
# o desenho tem camadas de projeto com prefixo (SMC_, A-, MC_…) e camadas de levantamento sem prefixo, em minúsculas
_PREFIXO_PROJETO = re.compile(r"^[A-Z0-9]{1,6}[_\-]")
_AREA_ESCRITA = re.compile(r"(\d{1,6}(?:[.,]\d{1,2})?)\s*m(?:2|²)", re.I)


def _classe(layer: str):
    n = _n(layer)
    for c in CLASSES:
        if re.search(c[1], n):
            return c
    return None


def _len(e) -> float:
    t = e.dxftype()
    if t == "LINE":
        return float(e.dxf.start.distance(e.dxf.end))
    if t == "ARC":
        return float(math.radians((e.dxf.end_angle - e.dxf.start_angle) % 360) * e.dxf.radius)
    if t in ("LWPOLYLINE", "POLYLINE"):
        return float(polyline_length_area(e)[0])
    return 0.0


def _pts(e):
    t = e.dxftype()
    try:
        if t == "LINE":
            return [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
        if t == "LWPOLYLINE":
            return [(float(p[0]), float(p[1])) for p in e.get_points("xy")]
        if t == "POLYLINE":
            return [(float(v.dxf.location.x), float(v.dxf.location.y)) for v in e.vertices]
        if t == "ARC":
            return [(float(p.x), float(p.y)) for p in e.flattening(0.05)]
    except Exception:  # noqa: BLE001
        return []
    return []


def _comprimento_eixo(itens: list[tuple[float, list]], u: float) -> tuple[float, int]:
    """Soma comprimentos contando uma vez os pares de linhas paralelas (face/tardoz) a 5–40 cm."""
    try:
        from shapely.geometry import LineString
    except Exception:  # noqa: BLE001
        return sum(l for l, _ in itens) * u, 0
    geoms = [(l, LineString(p) if len(p) >= 2 else None) for l, p in itens]
    usado, total, pares = set(), 0.0, 0
    ordem = sorted(range(len(geoms)), key=lambda i: -geoms[i][0])
    for i in ordem:
        if i in usado:
            continue
        li, gi = geoms[i]
        usado.add(i)
        par = None
        if gi is not None and li * u > 0.5:
            for j in ordem:
                if j in usado or geoms[j][1] is None:
                    continue
                lj, gj = geoms[j]
                if abs(lj - li) > 0.12 * max(li, lj) + 0.3 / u:
                    continue
                d = gi.hausdorff_distance(gj) * u
                if 0.05 <= d <= 0.40:
                    par = j
                    break
        if par is not None:
            usado.add(par)
            pares += 1
            total += (li + geoms[par][0]) / 2
        else:
            total += li
    return total * u, pares


def _t(pt: str, fr: str, lang: str) -> str:
    return fr if lang == "fr" else pt


def _fator_unidades(doc, areas_por_camada_bruta: dict[str, float], lang: str = "pt") -> tuple[float, str]:
    """Confronta as áreas medidas com as áreas escritas (m²) para escolher mm/cm/m."""
    declarado = _INSUNITS.get(int(doc.header.get("$INSUNITS", 0) or 0))
    escritas = []
    for e in doc.modelspace().query("TEXT MTEXT"):
        try:
            txt = e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
        except Exception:  # noqa: BLE001
            continue
        for m in _AREA_ESCRITA.finditer(txt or ""):
            v = float(m.group(1).replace(",", "."))
            if v >= 5:
                escritas.append(v)
    brutas = [a for a in areas_por_camada_bruta.values() if a > 0]
    melhor = None
    if escritas and brutas:
        for nome, f in _FATORES.items():
            hits = sum(1 for w in escritas if any(abs(a * f * f - w) <= 0.02 * w for a in brutas))
            if hits and (melhor is None or hits > melhor[2]):
                melhor = (nome, f, hits)
    if melhor and melhor[0] != declarado:
        return melhor[1], _t(f"unidades do desenho: declaradas {declarado or 'sem unidade'}, mas as áreas medidas só coincidem "
                             f"com as áreas escritas no desenho em {melhor[0]} ({melhor[2]} coincidência(s)) — usado {melhor[0]}",
                             f"unités du plan : déclarées {declarado or 'sans unité'}, mais les surfaces mesurées ne concordent avec les "
                             f"surfaces écrites sur le plan qu'en {melhor[0]} ({melhor[2]} concordance(s)) — {melhor[0]} retenu", lang)
    if melhor:
        return melhor[1], _t(f"unidades do desenho: {melhor[0]} (confirmadas por {melhor[2]} área(s) escrita(s))",
                             f"unités du plan : {melhor[0]} (confirmées par {melhor[2]} surface(s) écrite(s))", lang)
    if declarado:
        return _FATORES[declarado], _t(f"unidades do desenho: {declarado} (declaradas; sem área escrita para confirmar)",
                                       f"unités du plan : {declarado} (déclarées ; aucune surface écrite pour confirmer)", lang)
    return 1.0, _t("unidades do desenho não declaradas: assumido metro — CONFIRMAR", "unités du plan non déclarées : mètre retenu — À CONFIRMER", lang)


def medir(doc, entidades=None, lang: str = "pt") -> dict:
    """Medição por camadas → linhas de mapa de quantidades (com a origem de cada quantidade).

    `entidades`: lista já explodida pela importação da planta (evita explodir os blocos duas vezes)."""
    diag = []
    por = defaultdict(lambda: {"hatch": 0.0, "hatch_n": 0, "fechada": 0.0, "fechada_n": 0, "linhas": [], "blocos": 0})
    cls_cache: dict[str, object] = {}
    fonte = entidades if entidades is not None else walk_entities(doc, explode_dimensions=False, diagnostics=diag)
    for e in doc.modelspace().query("INSERT"):             # contagens: blocos inseridos no espaço modelo
        por[e.dxf.get("layer", "0")]["blocos"] += 1
    from engines.estrutura_implantacao import _CAMADA_EDIF
    cand_edif = []
    for e in fonte:
        layer = e.dxf.get("layer", "0")
        if getattr(e, "_cp_role", None) == "dimension":
            continue
        t = e.dxftype()
        if t in ("HATCH", "LWPOLYLINE") and _CAMADA_EDIF.search(layer):
            cand_edif.append(e)
        if layer not in cls_cache:
            cls_cache[layer] = _classe(layer)
        if cls_cache[layer] is None and t != "HATCH" and not (t in ("LWPOLYLINE", "POLYLINE") and getattr(e, "closed", False)):
            continue                                          # camada sem classe: só interessam áreas (para a lista «sem material»)
        r = por[layer]
        if t == "HATCH":
            try:
                r["hatch"] += hatch_area(e)
                r["hatch_n"] += 1
            except Exception:  # noqa: BLE001
                pass
        elif t in ("LWPOLYLINE", "POLYLINE"):
            length, area = polyline_length_area(e)
            if area > 0:
                r["fechada"] += area
                r["fechada_n"] += 1
            r["linhas"].append((length, _pts(e)))
        elif t in ("LINE", "ARC"):
            r["linhas"].append((_len(e), _pts(e)))
    brutas = {k: (v["hatch"] or v["fechada"]) for k, v in por.items()}
    u, nota_unidades = _fator_unidades(doc, brutas, lang)
    L = 1 if lang == "fr" else 0
    tem_prefixo = any(_PREFIXO_PROJETO.match(k) for k in por)

    linhas, excluidas = [], []
    for layer, r in sorted(por.items()):
        c = _classe(layer)
        if c is None:
            continue
        cid, _, medida, cap, desig, mat = c[0], c[1], c[2], c[3][L], c[4][L], c[5][L]
        levant = bool(_LEVANTAMENTO.search(_n(layer))) or (tem_prefixo and not _PREFIXO_PROJETO.match(layer) and layer == layer.lower())
        if medida == "area":
            if r["hatch_n"]:
                q, origem = r["hatch"] * u * u, _t(f"{r['hatch_n']} trama(s) (HATCH), área líquida", f"{r['hatch_n']} hachure(s) (HATCH), surface nette", lang)
            elif r["fechada_n"]:
                q, origem = r["fechada"] * u * u, _t(f"{r['fechada_n']} polilinha(s) fechada(s)", f"{r['fechada_n']} polyligne(s) fermée(s)", lang)
            else:
                excluidas.append({"camada": layer, "motivo": _t("camada de áreas sem tramas nem polilinhas fechadas — área não mensurável",
                                                                "calque de surfaces sans hachures ni polylignes fermées — surface non mesurable", lang)})
                continue
            un = "m2"
        elif medida == "comprimento":
            if not r["linhas"]:
                continue
            q, pares = _comprimento_eixo(r["linhas"], u)
            origem = _t(f"{len(r['linhas'])} linha(s)", f"{len(r['linhas'])} ligne(s)", lang) + (
                _t(f", {pares} par(es) de linhas paralelas contados uma vez (face/tardoz)",
                   f", {pares} paire(s) de lignes parallèles comptées une fois (face avant/arrière)", lang) if pares else "")
            un = "m"
        else:
            if not r["blocos"]:
                continue
            q, origem, un = float(r["blocos"]), _t(f"{r['blocos']} bloco(s) inseridos", f"{r['blocos']} bloc(s) inséré(s)", lang), "un"
        if q <= 0:
            continue
        if levant:
            excluidas.append({"camada": layer, "motivo": _t(f"camada de levantamento/existente ({round(q, 2)} {un}) — não orçamentada; confirmar se é obra nova",
                                                            f"calque de relevé/existant ({round(q, 2)} {un}) — non chiffré ; confirmer s'il s'agit de travaux neufs", lang),
                              "quantidade": round(q, 2), "unidade": un})
            continue
        linhas.append({"kind": "item", "category": cap, "designation": _t(f"{desig} — camada {layer}", f"{desig} — calque {layer}", lang),
                       "unit": un, "qty": round(q, 2), "classe": cid, "camada": layer,
                       "description": _t(f"{mat}. Medido no desenho CAD: camada «{layer}», {origem}. {nota_unidades}.",
                                         f"{mat}. Mesuré sur le plan CAO : calque « {layer} », {origem}. {nota_unidades}.", lang)})
    edificio, altitude = None, None
    try:
        from engines import estrutura_implantacao as EI
        ed = EI.escolher(EI.contornos(doc, cand_edif, u), EI.area_implantacao_escrita(doc), lang)
        if ed:
            edificio = {"camada": ed["camada"], "area_m2": ed["area_m2"], "origem": ed["origem"],
                        "pontos": [[round(x, 3), round(y, 3)] for x, y in ed["pontos"]][:2000]}
        altitude = EI.cota_soleira(doc)
    except Exception:  # noqa: BLE001 — a medição das camadas nunca falha por causa do contorno
        pass
    sem_material = [k for k, v in por.items() if _classe(k) is None and (v["hatch_n"] or v["fechada_n"]) and _PREFIXO_PROJETO.match(k)]
    return {"versao": VERSAO, "linhas": linhas, "excluidas": excluidas, "edificio": edificio, "altitude_m": altitude, "unidades": nota_unidades, "fator_m": u,
            "camadas_area_sem_material": sorted(sem_material)[:40],
            "nota": _t("Quantidades medidas na geometria do desenho, camada a camada. Espessuras, perfis e secções não estão no "
                       "desenho de implantação: o mapa de materiais usa o perfil-tipo declarado (hipótese) ou deixa o material «em falta».",
                       "Quantités mesurées sur la géométrie du plan, calque par calque. Épaisseurs, profils et sections ne figurent pas sur "
                       "le plan de masse : la liste des matériaux applique le profil type déclaré (hypothèse) ou laisse le matériau « manquant ».", lang)}


def medir_bytes(dxf: bytes, lang: str = "pt") -> dict:
    """DXF em bytes → medição (para plantas já importadas antes deste motor)."""
    import os
    import tempfile

    import ezdxf
    from ezdxf.recover import readfile as recover_readfile
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        f.write(dxf)
        path = f.name
    try:
        try:
            doc = ezdxf.readfile(path)
        except (ezdxf.DXFError, UnicodeError):
            doc, _ = recover_readfile(path)
    finally:
        os.unlink(path)
    return medir(doc, lang=lang)

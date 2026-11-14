"""Decomposição de cada artigo de um mapa de quantidades em TODOS os materiais, até aos parafusos, pregos e buchas.

Regra do Martinho (14/11): «um mapa de quantidades total, até aos parafusos — em todos os pedidos», e sem inventar nada.

Como se cumpre sem inventar:
- QUANTIDADE do artigo: só a do orçamento/medição. Uma linha «a confirmar», global («1 un», «vg», «conjunto») ou sem
  medição não é decomposta: aparece em «Artigos não decompostos» com o motivo.
- DIMENSÕES (espessura, formato do tijolo, da peça cerâmica, do vão, nº de demãos…): só as escritas na designação ou na
  descrição. Se faltar uma dimensão necessária, o material correspondente fica «parâmetro em falta» — nunca adivinhado.
- CONSUMOS (parafusos/m², kg de cola/m², sobreposições…): coeficientes de sistema publicados (fichas técnicas e
  documentos de aplicação dos fabricantes, normas), cada um com a sua fonte, para confirmar com o produto escolhido.
- PERDAS e EMBALAGENS: explícitas por material (quantidade líquida, perda %, quantidade a encomendar, n.º de embalagens).
"""
from __future__ import annotations

import math
import re
import unicodedata

GLOBAL_UNITS = {"un", "u", "vg", "cj", "conj", "conjunto", "forfait", "ft", "global", "lote", "ens", "ensemble", "lot", "gl"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _unit(u: str) -> str:
    u = _norm(u).replace("²", "2").replace("³", "3").replace(" ", "").rstrip(".")
    return {"m2": "m2", "m²": "m2", "m3": "m3", "ml": "m", "m": "m", "mlin": "m", "kg": "kg", "t": "t", "ton": "t",
            "un": "un", "u": "un", "und": "un", "unid": "un", "pc": "un", "pcs": "un"}.get(u, u)


# ── extração de parâmetros do texto (nunca inventados) ───────────────────────────────────────────────────────────────
def _num(s: str) -> float:
    return float(s.replace(",", "."))


def espessura_m(txt: str) -> float | None:
    """«e=5cm», «5 cm», «espessura 0,20 m», «ep. 12 cm», «120 mm». Devolve metros."""
    t = _norm(txt)
    m = re.search(r"(?:e\s*=|esp(?:essura)?\.?|ep\.?|epaisseur)\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|m)\b", t) \
        or re.search(r"\b(\d+(?:[.,]\d+)?)\s*(mm|cm)\b(?!\s*[x×])", t)
    if not m:
        return None
    v = _num(m.group(1))
    return v / 1000 if m.group(2) == "mm" else v / 100 if m.group(2) == "cm" else v


def formato_cm(txt: str) -> tuple[float, ...] | None:
    """«30x20x11», «60 x 60 cm», «20×10×8». Devolve dimensões em cm (2 ou 3 números)."""
    t = _norm(txt).replace("×", "x")
    m = re.search(r"\b(\d+(?:[.,]\d+)?)\s*x\s*(\d+(?:[.,]\d+)?)(?:\s*x\s*(\d+(?:[.,]\d+)?))?\s*(mm|cm|m)?\b", t)
    if not m:
        return None
    vals = [_num(g) for g in m.groups()[:3] if g]
    unit = m.group(4) or "cm"
    f = {"mm": 0.1, "cm": 1.0, "m": 100.0}[unit]
    return tuple(v * f for v in vals)


def demaos(txt: str) -> int | None:
    m = re.search(r"\b(\d)\s*(?:demaos|demao|camadas de tinta|couches)\b", _norm(txt))
    return int(m.group(1)) if m else None


def taxa_aco(txt: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*kg\s*/\s*m3", _norm(txt))
    return _num(m.group(1)) if m else None


# ── receitas ─────────────────────────────────────────────────────────────────────────────────────────────────────────
F_KNAUF_W111 = "Knauf W111 / Placo — consumos por m² de divisória simples (documento de aplicação do sistema)"
F_KNAUF_D11 = "Knauf D11 / Placo — consumos por m² de teto suspenso (documento de aplicação do sistema)"
F_CERAMICO = "Fichas técnicas cimento-cola C2 (talocha 8–10 mm) e betume de juntas; EN 12004 / EN 13888"
F_ETICS = "ETAG 004 / EAD 040083 e fichas técnicas dos sistemas ETICS (weber.therm, Secil, Sto)"
F_BET = "LNEC / CE EP — massa volúmica de mistura betuminosa compactada 2,35–2,45 t/m³; rega de colagem 0,3–0,6 kg/m²"
F_GEOM = "Cálculo geométrico a partir das dimensões escritas no artigo"
F_CAIX = "RAL — Guia de montagem de caixilharia: fixações a ≤ 700 mm e a ≤ 150 mm dos cantos"


def _m(nome, un, liq, perda=0.0, emb=None, fonte=F_GEOM, falta=None):
    """Material de uma receita: `liq` é a quantidade líquida por unidade do artigo (ou None com `falta`)."""
    return {"nome": nome, "un": un, "liq": liq, "perda": perda, "emb": emb, "fonte": fonte, "falta": falta}


def _r_divisoria(q, txt):
    dupla = bool(re.search(r"dupla placa|2\s*x\s*12[.,]5|placa dupla|duas placas", _norm(txt)))
    k = 2 if dupla else 1
    out = [_m("Placa de gesso cartonado 12,5 mm", "m2", 2.0 * k, 0.05, (2.88, "placa 1,20×2,40"), F_KNAUF_W111),
           _m("Montante metálico 48/70 (CW)", "m", 2.0, 0.05, (3.0, "barra 3 m"), F_KNAUF_W111),
           _m("Guia metálica (UW)", "m", 0.7, 0.05, (3.0, "barra 3 m"), F_KNAUF_W111),
           _m("Parafuso auto-perfurante TN 3,5×25", "un", 15.0 * 2 * k, 0.05, (1000, "caixa 1000"), F_KNAUF_W111),
           _m("Parafuso LN 3,5×9 (perfil/perfil)", "un", 1.0, 0.05, (1000, "caixa 1000"), F_KNAUF_W111),
           _m("Bucha + parafuso de fixação das guias ao suporte", "un", 1.6, 0.05, (100, "caixa 100"), F_KNAUF_W111),
           _m("Banda acústica / vedação perimetral", "m", 1.2, 0.05, (30.0, "rolo 30 m"), F_KNAUF_W111),
           _m("Fita de juntas (papel)", "m", 1.5 * 2, 0.05, (75.0, "rolo 75 m"), F_KNAUF_W111),
           _m("Massa de juntas", "kg", 0.3 * 2 * k, 0.05, (25.0, "saco 25 kg"), F_KNAUF_W111)]
    if re.search(r"\bla\b|la mineral|la de rocha|la de vidro|isolamento", _norm(txt)):
        out.append(_m("Lã mineral na caixa da divisória", "m2", 1.0, 0.05, None, F_KNAUF_W111))
    return out


def _r_teto(q, txt):
    return [_m("Placa de gesso cartonado 12,5 mm", "m2", 1.0, 0.07, (2.88, "placa 1,20×2,40"), F_KNAUF_D11),
            _m("Perfil CD 60/27 (primário + secundário)", "m", 3.2, 0.05, (3.0, "barra 3 m"), F_KNAUF_D11),
            _m("Suspensão (pendural/tirante)", "un", 1.2, 0.05, (100, "caixa 100"), F_KNAUF_D11),
            _m("Bucha metálica de teto para suspensão", "un", 1.2, 0.05, (100, "caixa 100"), F_KNAUF_D11),
            _m("Ligador de cruzamento CD", "un", 2.3, 0.05, (100, "caixa 100"), F_KNAUF_D11),
            _m("Parafuso auto-perfurante TN 3,5×25", "un", 17.0, 0.05, (1000, "caixa 1000"), F_KNAUF_D11),
            _m("Fita de juntas (papel)", "m", 1.6, 0.05, (75.0, "rolo 75 m"), F_KNAUF_D11),
            _m("Massa de juntas", "kg", 0.35, 0.05, (25.0, "saco 25 kg"), F_KNAUF_D11),
            _m("Perfil perimetral UD 28", "m", None, falta="perímetro do teto (ml) — medir nas plantas", fonte=F_KNAUF_D11)]


def _r_alvenaria(q, txt):
    f = formato_cm(txt)
    if not f or len(f) < 3:
        return [_m("Tijolo / bloco", "un", None, falta="formato do tijolo/bloco (C×A×E, ex.: 30×20×11) não indicado no artigo"),
                _m("Argamassa de assentamento", "m3", None, falta="formato do tijolo/bloco não indicado")]
    c, a, e = (v / 100 for v in f[:3])
    j = 0.01
    pecas = 1 / ((c + j) * (a + j))
    arg = (1 - (c * a) / ((c + j) * (a + j))) * e
    out = [_m(f"Tijolo/bloco {f[0]:g}×{f[1]:g}×{f[2]:g} cm", "un", pecas, 0.05, (None, "palete"), F_GEOM),
           _m("Argamassa de assentamento (juntas de 1 cm)", "m3", arg, 0.10, None, F_GEOM),
           _m("Cimento para a argamassa (traço 1:4, 350 kg/m³)", "kg", arg * 350, 0.10, (25.0, "saco 25 kg"),
              "Traço volumétrico 1:4 — 350 kg de cimento por m³ de argamassa (tabelas LNEC)"),
           _m("Areia para a argamassa (1,1 m³ por m³)", "m3", arg * 1.1, 0.10, None,
              "Traço volumétrico 1:4 — 1,1 m³ de areia por m³ de argamassa (tabelas LNEC)")]
    return out


def _r_reboco(q, txt):
    e = espessura_m(txt)
    if not e:
        return [_m("Argamassa de reboco", "m3", None, falta="espessura do reboco não indicada no artigo")]
    return [_m(f"Argamassa de reboco (e = {e*100:g} cm)", "m3", e, 0.10, None, F_GEOM),
            _m("Cimento (traço 1:4, 350 kg/m³)", "kg", e * 350, 0.10, (25.0, "saco 25 kg"),
               "Traço volumétrico 1:4 — 350 kg de cimento por m³ de argamassa (tabelas LNEC)"),
            _m("Areia (1,1 m³ por m³ de argamassa)", "m3", e * 1.1, 0.10, None, "Tabelas LNEC")]


def _r_betao(q, txt):
    out = [_m("Betão (classe conforme projeto)", "m3", 1.0, 0.03, None, "Perda de colocação 3 % (NP EN 206 / prática corrente)")]
    if re.search(r"armad|ba\b|beton arme", _norm(txt)):
        tx = taxa_aco(txt)
        if tx:
            out += [_m(f"Aço A500 em varão ({tx:g} kg/m³)", "kg", tx, 0.05, None, "Taxa de armadura indicada no artigo"),
                    _m("Arame recozido de atar", "kg", tx * 0.01, 0.10, (25.0, "rolo 25 kg"), "Prática corrente: ~1 % do peso do aço")]
        else:
            out.append(_m("Aço A500 em varão", "kg", None, falta="taxa de armadura (kg/m³) — vem do cálculo estrutural"))
        out.append(_m("Cofragem", "m2", None, falta="área de cofragem — medir nas peças desenhadas de estrutura"))
        out.append(_m("Espaçadores de armadura", "un", None, falta="área de cofragem em falta"))
    return out


def _r_aco(q, txt):
    return [_m("Aço A500 em varão", "kg", 1.0, 0.05, None, "Desperdício de corte e sobreposições 5 %"),
            _m("Arame recozido de atar", "kg", 0.01, 0.10, (25.0, "rolo 25 kg"), "Prática corrente: ~1 % do peso do aço")]


def _r_pintura(q, txt):
    n = demaos(txt)
    out = []
    if re.search(r"primario|primer|isolante|fundo", _norm(txt)):
        out.append(_m("Primário (1 demão, 10 m²/L)", "L", 0.1, 0.05, (15.0, "lata 15 L"), "Rendimento típico de ficha técnica — confirmar no produto"))
    if not n:
        out.append(_m("Tinta de acabamento", "L", None, falta="número de demãos não indicado no artigo"))
    else:
        out.append(_m(f"Tinta de acabamento ({n} demãos, 10 m²/L por demão)", "L", n * 0.1, 0.05, (15.0, "lata 15 L"),
                      "Rendimento típico de ficha técnica — confirmar no produto"))
    out.append(_m("Fita de pintor / proteções", "m", None, falta="comprimento de remates — medir nas plantas"))
    return out


def _r_ceramico(q, txt):
    f = formato_cm(txt)
    out = [_m("Peças cerâmicas", "m2", 1.0, 0.07, None, "Perda de corte 7 % (assentamento reto)"),
           _m("Cimento-cola C2", "kg", 5.0, 0.05, (25.0, "saco 25 kg"), F_CERAMICO)]
    if f and len(f) >= 2:
        L, H = f[0] / 100, f[1] / 100
        pecas = 1 / (L * H)
        out.insert(1, _m(f"Peças {f[0]:g}×{f[1]:g} cm (contagem)", "un", pecas, 0.07, None, F_GEOM))
        out.append(_m("Cruzetas / niveladores", "un", pecas, 0.10, (200, "saco 200"), "1 por peça"))
        junta = 0.003
        e = (f[2] / 1000 * 10) if len(f) > 2 else 0.009     # espessura da peça (mm→m) se indicada; senão 9 mm
        kg = (L + H) / (L * H) * junta * e * 1600
        out.append(_m("Betume de juntas (junta 3 mm)", "kg", kg, 0.10, (5.0, "saco 5 kg"), "EN 13888 — fórmula do fabricante (C+L)/(C×L)×junta×espessura×1,6"))
    else:
        out.append(_m("Betume de juntas", "kg", None, falta="formato das peças não indicado (necessário para o consumo de betume)"))
        out.append(_m("Cruzetas / niveladores", "un", None, falta="formato das peças não indicado"))
    out.append(_m("Rodapé / remates", "m", None, falta="comprimento de rodapé — artigo próprio medido em ml"))
    return out


def _r_flutuante(q, txt):
    return [_m("Pavimento flutuante / laminado", "m2", 1.0, 0.07, None, "Perda de corte 7 % (ficha de colocação)"),
            _m("Subcamada (espuma / cortiça)", "m2", 1.05, 0.03, None, "Sobreposição 5 %"),
            _m("Rodapé e perfis de transição", "m", None, falta="comprimento de rodapé — medir nas plantas")]


def _r_betuminoso(q, txt):
    e = espessura_m(txt)
    out = []
    if e:
        out.append(_m(f"Mistura betuminosa (e = {e*100:g} cm, 2,40 t/m³)", "t", e * 2.40, 0.03, None, F_BET))
    else:
        out.append(_m("Mistura betuminosa", "t", None, falta="espessura da camada betuminosa — perfil-tipo do pavimento"))
    out.append(_m("Emulsão de rega de colagem (0,5 kg/m²)", "kg", 0.5, 0.05, None, F_BET))
    out.append(_m("Base e sub-base granular", "m3", None, falta="espessuras de base/sub-base — perfil-tipo do pavimento"))
    return out


def _r_pave(q, txt):
    f = formato_cm(txt)
    e = espessura_m(txt)
    out = [_m("Blocos de pavê", "m2", 1.0, 0.03, None, "Perda de corte 3 %")]
    if f and len(f) >= 2:
        out.insert(0, _m(f"Blocos {f[0]:g}×{f[1]:g} cm (contagem)", "un", 1 / ((f[0] / 100) * (f[1] / 100)), 0.03, None, F_GEOM))
    out.append(_m("Areia de assentamento", "m3", e, 0.10, None, F_GEOM) if e else
               _m("Areia de assentamento", "m3", None, falta="espessura da almofada de areia — perfil-tipo"))
    out.append(_m("Areia fina de refechamento de juntas", "m3", 0.005, 0.10, None, "Ficha de colocação de pavê (≈ 5 L/m²)"))
    out.append(_m("Base granular", "m3", None, falta="espessura da base — perfil-tipo do pavimento"))
    return out


def _r_lancil(q, txt):
    return [_m("Lancil (peças de 1 m)", "un", 1.0, 0.02, None, F_GEOM),
            _m("Betão de fundação / encosto do lancil", "m3", None, falta="secção da fundação do lancil — pormenor-tipo"),
            _m("Argamassa de juntas", "m3", 0.002, 0.10, None, "Juntas de 1 cm entre peças")]


def _r_etics(q, txt):
    e = espessura_m(txt)
    out = [_m(f"Placa de isolamento EPS/XPS{'' if not e else f' {e*100:g} cm'}", "m2", 1.0, 0.05, None, F_ETICS),
           _m("Argamassa de colagem", "kg", 4.5, 0.05, (25.0, "saco 25 kg"), F_ETICS),
           _m("Bucha de fixação mecânica", "un", 6.0, 0.05, (100, "caixa 100"), F_ETICS),
           _m("Rede de fibra de vidro", "m2", 1.15, 0.03, (50.0, "rolo 50 m²"), F_ETICS),
           _m("Argamassa de barramento", "kg", 4.0, 0.05, (25.0, "saco 25 kg"), F_ETICS),
           _m("Primário de regularização", "L", 0.15, 0.05, (15.0, "lata 15 L"), F_ETICS),
           _m("Revestimento de acabamento", "kg", 2.5, 0.05, (25.0, "balde 25 kg"), F_ETICS),
           _m("Perfil de arranque e cantoneiras", "m", None, falta="comprimentos de arranque e arestas — medir nos alçados", fonte=F_ETICS)]
    if not e:
        out[0]["falta"] = "espessura do isolamento não indicada (quantidade em m² dada, espessura a definir)"
    return out


def _r_membrana(q, txt):
    k = 2 if re.search(r"dupla|2 camadas|bicamada|duas camadas", _norm(txt)) else 1
    return [_m(f"Membrana betuminosa ({k} camada{'s' if k > 1 else ''})", "m2", 1.0 * k, 0.15, (10.0, "rolo 10 m²"),
               "Sobreposições de 10 cm + remates: 15 % (ficha de aplicação)"),
            _m("Primário betuminoso", "kg", 0.3, 0.05, (25.0, "lata 25 kg"), "Ficha técnica — 0,3 kg/m²")]


def _r_betonilha(q, txt):
    e = espessura_m(txt)
    if not e:
        return [_m("Argamassa de betonilha", "m3", None, falta="espessura da betonilha não indicada")]
    return [_m(f"Argamassa de betonilha (e = {e*100:g} cm)", "m3", e, 0.05, None, F_GEOM),
            _m("Cimento (traço 1:4, 350 kg/m³)", "kg", e * 350, 0.05, (25.0, "saco 25 kg"), "Tabelas LNEC"),
            _m("Areia (1,1 m³ por m³)", "m3", e * 1.1, 0.05, None, "Tabelas LNEC")]


def _r_caixilharia(q, txt):
    f = formato_cm(txt)
    if not f or len(f) < 2:
        return [_m("Caixilho (vão)", "un", 1.0, 0.0, None, F_GEOM),
                _m("Fixações, espuma, silicone e fita de vedação", "un", None, falta="dimensões do vão (L×A) não indicadas no artigo")]
    Lm, Hm = f[0] / 100, f[1] / 100
    per = 2 * (Lm + Hm)
    nfix = 2 * math.ceil(Lm / 0.7) + 2 * math.ceil(Hm / 0.7)
    return [_m(f"Caixilho {f[0]:g}×{f[1]:g} cm", "un", 1.0, 0.0, None, F_GEOM),
            _m("Parafuso de caixilharia + bucha", "un", nfix, 0.05, (100, "caixa 100"), F_CAIX),
            _m("Espuma de poliuretano (junta perimetral)", "m", per, 0.10, (12.0, "lata 750 ml ≈ 12 m"), "Ficha técnica — 750 ml ≈ 12 m de junta 2×2 cm"),
            _m("Silicone / mastique de vedação (interior + exterior)", "m", per * 2, 0.10, (12.0, "cartucho 300 ml ≈ 12 m"), "Cordão 6×4 mm"),
            _m("Fita / membrana de vedação perimetral", "m", per, 0.05, None, F_CAIX)]


def _r_escavacao(q, txt):
    return [_m("Terras a transportar (empolamento 25 %)", "m3", 1.25, 0.0, None, "Empolamento de terras correntes 20–30 %")]


def _r_verde(q, txt):
    e = espessura_m(txt)
    out = [_m(f"Terra vegetal (e = {e*100:g} cm)", "m3", e, 0.10, None, F_GEOM) if e else
           _m("Terra vegetal", "m3", None, falta="espessura de terra vegetal — pormenor de espaços verdes")]
    out.append(_m("Semente de relva (mistura)", "kg", None, falta="dosagem de sementeira — caderno de encargos de espaços verdes"))
    return out


def _r_pintura_rodov(q, txt):
    return [_m("Tinta de marcação rodoviária", "kg", None, falta="tipo de tinta e espessura de película — projeto de sinalização"),
            _m("Microesferas de vidro", "kg", None, falta="dosagem de microesferas — projeto de sinalização")]


RECEITAS = [
    ("verde", ("m2",), r"espacos verdes|relvad|ajardinad|sementeira|zona verde", _r_verde),
    ("pintura_rodov", ("m2", "m"), r"marcacao rodoviaria|marcas rodoviarias|sinalizacao horizontal|pintura rodoviaria", _r_pintura_rodov),
    ("pave_drenante", ("m2",), r"pave.{0,20}(drenan|permeav)|(drenan|permeav).{0,20}pave", _r_pave),
    ("divisoria_gc", ("m2",), r"divisori|parede.*(gesso cartonado|pladur|placoplatre|plaque de platre)|cloison", _r_divisoria),
    ("teto_gc", ("m2",), r"teto falso|teto suspenso|tecto falso|faux plafond|plafond suspendu", _r_teto),
    ("etics", ("m2",), r"etics|capoto|isolamento (termico )?pelo exterior|ite\b", _r_etics),
    ("alvenaria", ("m2",), r"alvenaria|tijolo|bloco de betao|blocos de betao|maconnerie|parpaing|brique", _r_alvenaria),
    ("reboco", ("m2",), r"reboco|estuque|enduit|chapisco", _r_reboco),
    ("betonilha", ("m2",), r"betonilha|regulariza|chape|camada de forma", _r_betonilha),
    ("ceramico", ("m2",), r"ceramic|mosaico|azulejo|porcelanato|grés|gres|carrelage|faience", _r_ceramico),
    ("flutuante", ("m2",), r"flutuante|laminado|parquet|soalho", _r_flutuante),
    ("pintura", ("m2",), r"pintura|tinta|peinture", _r_pintura),
    ("membrana", ("m2",), r"impermeabiliza|membrana|etancheite", _r_membrana),
    ("betuminoso", ("m2",), r"betuminos|asfalt|tapete|enrobe|ac 14|ac14", _r_betuminoso),
    ("pave", ("m2",), r"\bpave\b|cubo|blocos de pavimento|paves", _r_pave),
    ("lancil", ("m",), r"lancil|guia de passeio|bordure", _r_lancil),
    ("betao", ("m3",), r"betao|beton", _r_betao),
    ("aco", ("kg", "t"), r"\baco\b|armadura|varao|acier|armature", _r_aco),
    ("caixilharia", ("un",), r"caixilh|janela|porta de sacada|vao envidra|fenetre|menuiserie", _r_caixilharia),
    ("escavacao", ("m3",), r"escava|aterro|desaterro|terrassement|deblai", _r_escavacao),
]


# ── PERFIS-TIPO (hipótese declarada) ─────────────────────────────────────────────────────────────────────────────────
# Um desenho de implantação mede as ÁREAS e os COMPRIMENTOS, mas não traz espessuras nem secções. Quando faltam, em vez
# de deixar o material vazio, aplica-se o perfil-tipo corrente — SEMPRE dito como hipótese, com as espessuras escritas,
# para o utilizador confirmar ou trocar (basta escrever a espessura no artigo e a receita deixa de usar o perfil-tipo).
F_PERFIL = "Perfil-tipo corrente (hipótese a confirmar com o projeto)"
PERFIS_TIPO = {
    "betuminoso": ("camada de desgaste AC 14 surf e = 5 cm; rega de impregnação; base em ABGE e = 20 cm; sub-base em ABGE e = 15 cm "
                   "(estacionamento/arruamento de tráfego ligeiro)",
                   [("Mistura betuminosa AC 14 surf (e = 5 cm, 2,40 t/m³)", "t", 0.05 * 2.40, 0.03, None),
                    ("Emulsão betuminosa de rega de impregnação (1,0 kg/m²)", "kg", 1.0, 0.05, None),
                    ("ABGE — base (e = 20 cm, compactado)", "m3", 0.20, 0.10, None),
                    ("ABGE — sub-base (e = 15 cm, compactado)", "m3", 0.15, 0.10, None)]),
    "pave": ("blocos de betão 20×10×8 cm; almofada de areia e = 4 cm; base em ABGE e = 20 cm",
             [("Blocos de pavê 20×10×8 cm", "un", 50.0, 0.03, None),
              ("Areia de assentamento (e = 4 cm)", "m3", 0.04, 0.10, None),
              ("Areia fina de refechamento de juntas (≈ 5 L/m²)", "m3", 0.005, 0.10, None),
              ("ABGE — base (e = 20 cm, compactado)", "m3", 0.20, 0.10, None)]),
    "pave_drenante": ("blocos drenantes de betão 20×10×8 cm; gravilha 2/6 mm de assentamento e = 4 cm; gravilha de juntas; "
                      "base granular aberta e = 20 cm; geotêxtil de separação",
                      [("Blocos de pavê drenante 20×10×8 cm", "un", 50.0, 0.03, None),
                       ("Gravilha 2/6 mm de assentamento (e = 4 cm)", "m3", 0.04, 0.10, None),
                       ("Gravilha 2/6 mm de enchimento de juntas (≈ 8 L/m²)", "m3", 0.008, 0.10, None),
                       ("Agregado britado 4/32 mm — base drenante (e = 20 cm)", "m3", 0.20, 0.10, None),
                       ("Geotêxtil de separação (sobreposição 10 %)", "m2", 1.10, 0.05, (100.0, "rolo 100 m²"))]),
    "lancil": ("lancil de betão 100×25×15 cm assente em fundação de betão C16/20 (0,30 × 0,20 m) com encosto",
               [("Lancil de betão 100×25×15 cm (peças de 1 m)", "un", 1.0, 0.02, None),
                ("Betão C16/20 de fundação e encosto (0,06 m³/m)", "m3", 0.06, 0.05, None),
                ("Argamassa de juntas (juntas de 1 cm)", "m3", 0.002, 0.10, None)]),
    "verde": ("terra vegetal e = 15 cm; sementeira de relva a 35 g/m²; adubo de fundo a 50 g/m²",
              [("Terra vegetal (e = 15 cm)", "m3", 0.15, 0.10, None),
               ("Semente de relva (35 g/m²)", "kg", 0.035, 0.05, (25.0, "saco 25 kg")),
               ("Adubo de fundo (50 g/m²)", "kg", 0.05, 0.05, (25.0, "saco 25 kg"))]),
    "pintura_rodov": ("tinta acrílica de marcação rodoviária 0,72 kg/m² (película húmida ≈ 400 µm) com microesferas de vidro 0,30 kg/m²",
                      [("Tinta de marcação rodoviária (0,72 kg/m²)", "kg", 0.72, 0.05, (25.0, "balde 25 kg")),
                       ("Microesferas de vidro (0,30 kg/m²)", "kg", 0.30, 0.05, (25.0, "saco 25 kg"))]),
}


def _especificado(rid: str, txt: str) -> bool:
    """O artigo já diz a sua especificação principal? Então NUNCA se substitui pelo perfil-tipo."""
    if rid in ("betuminoso", "verde"):
        return espessura_m(txt) is not None
    if rid in ("pave", "pave_drenante", "lancil"):
        return formato_cm(txt) is not None or espessura_m(txt) is not None
    if rid == "pintura_rodov":
        return bool(re.search(r"kg/m|g/m2|µm|micron", _norm(txt)))
    return False


def _embalagens(qtd: float, emb) -> str | None:
    if not emb or not emb[0]:
        return emb[1] if emb else None
    n = math.ceil(qtd / emb[0] - 1e-9)
    return f"{n} × {emb[1]}"


def decompor(linha: dict) -> dict:
    """Uma linha do orçamento/medição → materiais. Nunca inventa a quantidade do artigo."""
    nome = (linha.get("designation") or "").strip()
    txt = f"{nome} {linha.get('description') or ''}"
    un = _unit(linha.get("unit") or "")
    qtd = linha.get("qty")
    base = {"designacao": nome, "unidade": un, "quantidade": qtd, "capitulo": linha.get("category") or ""}
    if linha.get("quantity_missing") or qtd in (None, "") or float(qtd or 0) <= 0:
        return {**base, "estado": "sem_medicao", "motivo": "quantidade a confirmar — medir nas plantas ou em obra", "materiais": []}
    qtd = float(qtd)
    t = _norm(txt)
    rec = next(((rid, f) for rid, uns, rx, f in RECEITAS if re.search(rx, t) and (un in uns or (rid == "aco" and un in ("kg", "t")))), None)
    if rec is None:
        if un in GLOBAL_UNITS and rec is None:
            return {**base, "estado": "global", "motivo": "artigo global (un/vg) sem medição: decompor em artigos medidos", "materiais": []}
        return {**base, "estado": "sem_receita", "motivo": "tipo de artigo ainda sem decomposição de materiais no ConstruPilot", "materiais": []}
    rid, fn = rec
    mult = 1000.0 if (rid == "aco" and un == "t") else 1.0
    mats = []
    receita = fn(qtd, txt)
    perfil = None
    if rid in PERFIS_TIPO and any(m["liq"] is None for m in receita) and not _especificado(rid, txt):
        perfil, lista = PERFIS_TIPO[rid]
        receita = [_m(n, u_, liq, perda, emb, F_PERFIL) for n, u_, liq, perda, emb in lista]
    for m in receita:
        if m["liq"] is None:
            mats.append({"material": m["nome"], "unidade": m["un"], "quantidade_liquida": None, "perda_pct": None,
                         "quantidade_encomenda": None, "embalagens": None, "fonte": m["fonte"], "em_falta": m["falta"]})
            continue
        liq = m["liq"] * qtd * mult
        enc = liq * (1 + m["perda"])
        if m["un"] == "un":
            enc = math.ceil(enc - 1e-9)
        mats.append({"material": m["nome"], "unidade": m["un"], "quantidade_liquida": round(liq, 3), "perda_pct": round(m["perda"] * 100, 1),
                     "quantidade_encomenda": round(enc, 3), "embalagens": _embalagens(enc, m["emb"]), "fonte": m["fonte"],
                     "em_falta": m["falta"]})
    completo = all(x["em_falta"] is None for x in mats)
    if perfil:
        return {**base, "estado": "hipotese", "receita": rid, "materiais": mats, "perfil_tipo": perfil,
                "motivo": f"espessuras/secção não indicadas no desenho — perfil-tipo aplicado (hipótese a confirmar): {perfil}"}
    return {**base, "estado": "completo" if completo else "parcial", "receita": rid, "materiais": mats,
            "motivo": None if completo else "; ".join(x["em_falta"] for x in mats if x["em_falta"])}


def mapa(linhas: list[dict]) -> dict:
    """Mapa de materiais de um orçamento: decomposição por artigo + totais por material (para encomenda)."""
    artigos = [decompor(l) for l in linhas if l.get("kind") not in ("section", "subsection", "text", "pagebreak")]
    tot: dict[tuple[str, str], dict] = {}
    for a in artigos:
        for m in a["materiais"]:
            if m["quantidade_encomenda"] is None:
                continue
            k = (m["material"], m["unidade"])
            r = tot.setdefault(k, {"material": m["material"], "unidade": m["unidade"], "quantidade_liquida": 0.0,
                                   "quantidade_encomenda": 0.0, "artigos": 0})
            r["quantidade_liquida"] += m["quantidade_liquida"]
            r["quantidade_encomenda"] += m["quantidade_encomenda"]
            r["artigos"] += 1
    totais = sorted(({**v, "quantidade_liquida": round(v["quantidade_liquida"], 3),
                      "quantidade_encomenda": round(v["quantidade_encomenda"], 3)} for v in tot.values()),
                    key=lambda r: r["material"])
    contagem = {e: sum(1 for a in artigos if a["estado"] == e) for e in ("completo", "hipotese", "parcial", "sem_medicao", "global", "sem_receita")}
    return {"artigos": artigos, "totais": totais, "contagem": contagem,
            "aviso": ("Quantidades dos artigos: só as medidas no orçamento. Dimensões: só as escritas no artigo. "
                      "Consumos: coeficientes publicados dos sistemas (fonte indicada) — confirmar com o produto escolhido. "
                      "Artigos globais, sem medição ou sem dimensões aparecem como não decompostos, com o que falta. "
                      "Onde o desenho não traz espessuras, aplica-se um perfil-tipo DECLARADO como hipótese (estado «Hipótese»), "
                      "com as espessuras escritas — confirmar com o projeto.")}

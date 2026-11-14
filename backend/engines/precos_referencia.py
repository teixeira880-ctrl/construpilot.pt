"""Preços de referência (Portugal) para os artigos que os motores CAD produzem — passo determinístico entre a biblioteca
da empresa e a pesquisa de mercado online.

Fonte: CYPE Gerador de Preços Portugal (geradordeprecos.info, obra nova), consultado a 14/11/2026. São CUSTOS DIRETOS
(materiais + mão de obra + 2 % complementares, sem custos indiretos, encargos, margem nem IVA). O preço de venda do
orçamento = custo direto × (1 + 3 % custos indiretos CYPE) × (1 + encargos gerais da empresa) ÷ (1 − margem-alvo da
empresa) — os dois últimos vêm dos recursos da empresa (dossier económico), por defeito 12 % e 20 % em Portugal.
O custo direto fica em cost_price_ht: o dossier económico usa-o como custo conhecido.

Só preenche linhas SEM preço (price_missing) depois da biblioteca, só para obras em Portugal e só quando a designação
e a unidade correspondem sem ambiguidade a um artigo da tabela. Nada aqui inventa quantidades."""
import re
import unicodedata

FONTE = "CYPE Gerador de Preços PT"
DATA = "11/2026"
CUSTOS_INDIRETOS = 0.03

# (código, regex sobre a designação normalizada, unidade, custo direto €/un, descrição curta da unidade de obra)
TABELA = [
    ("UJC020", r"espacos verdes|relvad|ajardinad", "m2", 12.77, "relvado por sementeira com terra vegetal 15 cm"),
    ("MSH030", r"marcacao rodoviaria|marcas? rodoviaria|pintura rodoviaria", "m2", 5.28, "marca rodoviária acrílica retrorrefletora"),
    ("UXB020", r"\blancil\b", "ml", 28.38, "lancil de betão A1 (C1 em via: 37,21 €/m)"),
    ("UXF010", r"pavimento betuminoso|\bbetuminoso\b", "m2", 11.17, "camada de desgaste AC16 surf 5 cm — base e sub-base não incluídas"),
    ("UXR230", r"pave drenante|pave permeavel|pavimento .*drenante", "m2", 40.90, "pavê drenante — base não incluída"),
    ("EAT030", r"\bmadres\b", "kg", 2.97, "madres em perfis laminados aparafusadas, parafusaria incluída, primário incluído"),
    ("EAV010", r"perfis .*\bvigas?\b|contraventament", "kg", 2.03, "aço S275 em vigas/tirantes, primário antioxidante incluído"),
    ("EAS010", r"perfis .*\bpilares?\b|chapas de ligacao|placas de base", "kg", 2.49, "aço S275 em pilares/chapas, primário antioxidante incluído"),
    ("EAS005", r"chumbadouro", "u", 9.20, "placa de ancoragem com 4 pernos (36,80 €/Ud) repartida por chumbadouro"),
    ("ADE010", r"escavacao .*(sapata|funda|cabouco|vala)", "m3", 28.36, "escavação mecânica de caboucos — transporte a vazadouro não incluído"),
    ("CRL010", r"betao de limpeza", "m3", 84.78, "betão de limpeza C12/15"),
    ("CSZ010", r"betao .*\bsapatas?\b", "m3", 198.01, "sapata de betão armado C25/30 com armadura (~50 kg/m³) incluída"),
    ("CSV010", r"betao .*vigas? de fundacao|sapata continua", "m3", 287.46, "viga de fundação/sapata contínua C25/30 com armadura (~100 kg/m³) incluída"),
    ("ANS010", r"laje terrea|massame", "m2", 17.78, "massame de betão — confirmar espessura e malha"),
    ("MBG010", r"base em agregado britado|base granular|\babge\b", "m3", 38.40, "base de agregado britado de granulometria extensa"),
    ("QTM010", r"painel sandwich de cobertura|cobertura .*painel sandwich", "m2", 42.16, "cobertura em painel sandwich"),
    ("FLA030", r"painel sandwich de fachada|fachada .*painel sandwich", "m2", 66.06, "fachada em painel sandwich 50 mm lã de rocha"),
]

# Linhas que ficam INCLUÍDAS noutra unidade de obra (para não contar duas vezes): (regex da linha, código que a inclui)
INCLUIDOS = [
    (r"aco a500 .*sapatas", "CSZ010"),
    (r"aco a500 .*vigas? de fundacao", "CSV010"),
    (r"parafusos m12 .*madres", "EAT030"),
]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s)


def _unit(u: str) -> str:
    from engines.assistant_quote_pricing import unit_key
    k = unit_key(u)
    return {"m": "ml", "un": "u", "ud": "u", "m²": "m2", "m³": "m3"}.get(k, k)


def procurar(designation: str, unit: str):
    """(código, custo, descrição) ou None. Ambíguo (2 códigos diferentes) → None."""
    d, u = _norm(designation), _unit(unit)
    hits = [(c, p, t) for c, rx, un, p, t in TABELA if un == u and re.search(rx, d)]
    codes = {h[0] for h in hits}
    if len(codes) != 1:
        return None
    return hits[0]


def coeficiente(params: dict | None) -> float:
    p = params or {}
    enc = float(p.get("overhead_pct") or 12.0) / 100
    marg = min(0.6, float(p.get("target_margin_pct") or 20.0) / 100)
    return (1 + CUSTOS_INDIRETOS) * (1 + enc) / (1 - marg)


def preencher(lines: list[dict], params: dict | None = None) -> int:
    """Preenche in-place as linhas sem preço. Devolve o n.º de linhas preenchidas."""
    k = coeficiente(params)
    n = 0
    usados = {}
    for r in lines:
        if not r.get("price_missing"):
            continue
        hit = procurar(r.get("designation", ""), r.get("unit", ""))
        if not hit:
            continue
        code, custo, txt = hit
        r.update(unit_price_ht=round(custo * k, 2), cost_price_ht=custo, price_source="reference_cype", price_estimated=True,
                 price_missing=False, price_reference=f"cype_pt:{code}",
                 price_reference_label=f"{FONTE} {code} ({DATA}) — custo direto {custo:.2f} € + encargos e margem; {txt}; a verificar"[:300])
        usados[code] = r.get("designation", "")
        n += 1
    for r in lines:
        if not r.get("price_missing"):
            continue
        d = _norm(r.get("designation", ""))
        for rx, code in INCLUIDOS:
            if code in usados and re.search(rx, d):
                r.update(unit_price_ht=0, cost_price_ht=0, price_source="reference_included", price_estimated=True, price_missing=False,
                         price_reference=f"cype_pt:{code}",
                         price_reference_label=f"Incluído no artigo «{usados[code][:80]}» ({FONTE} {code})"[:300])
                n += 1
                break
    return n

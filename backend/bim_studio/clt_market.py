"""Market reference prices per country for the CLT module.

A company that has not typed its own price for an item gets the market reference of ITS country when a dated public
source exists; otherwise the general reference of the library stays (and says so). The company's own prices always
win. Every value carries its source and date; nothing here is an estimate without a source.
"""
from __future__ import annotations

from decimal import Decimal

UAH_PER_EUR = Decimal("51.0795")          # National Bank of Ukraine, official rate of 11.11.2026
_RATE = "câmbio oficial do BNU de 11.11.2026: 51,0795 UAH/€"

# country → code → (cost €, origin, source)
REFERENCES = {
    "UA": {
        "EN-ELETRICIDADE": (str((Decimal("10.247") / UAH_PER_EUR).quantize(Decimal("0.0001"))), "mercado",
                            f"GlobalPetrolPrices, Ucrânia, eletricidade para empresas, 01.03.2026: 10,247 UAH/kWh; {_RATE}"),
        "COL-OPERADOR": (str((Decimal("30515") * Decimal("1.22") / Decimal("166.7") / UAH_PER_EUR).quantize(Decimal("0.01"))), "mercado",
                         "Derzhstat (Interfax-Ukraine): salário médio de abril de 2026, 30 515 UAH/mês, mais 22 % de contribuição social do "
                         f"empregador, 166,7 h/mês; {_RATE}. Média de todos os setores: confirmar com o custo real dos operadores"),
    },
}
# items with no dated public source in the country: the general reference stays, and the dossier says it
NO_LOCAL_SOURCE = {
    "UA": {"MP-LAMELA": "sem preço público de lamela C24 seca e aplainada na Ucrânia; fica a referência da Europa Central",
           "VENDA-CLT": "sem preço público de venda de CLT na Ucrânia; fica a referência europeia"},
}


def country_of(user: dict | None) -> str | None:
    c = ((user or {}).get("brand_country") or "").strip().upper()
    return c or None


def apply(library: dict, saved: dict | None, country: str | None) -> dict:
    """Overlays the country references on the items the company has not saved itself."""
    own = {code for code, item in (saved or {}).items() if not item.get("deleted")}
    for code, (cost, origin, source) in (REFERENCES.get(country or "") or {}).items():
        if code in library and code not in own:
            library[code] = {**library[code], "cost_eur": cost, "origin": origin, "source": source}
    for code, why in (NO_LOCAL_SOURCE.get(country or "") or {}).items():
        if code in library and code not in own and why not in str(library[code].get("source", "")):
            library[code] = {**library[code], "source": f"{library[code].get('source', '')} ({why})".strip()}
    return library

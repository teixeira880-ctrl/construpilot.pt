"""Mercado do site construpilot.pt — Portugal (fonte única para país, língua e IVA)."""
SITE_COUNTRY = "PT"
SITE_LANG = "pt"
SITE_LOCALE = "pt-PT"
SITE_URL = "https://construpilot.pt"
CURRENCY = "EUR"

# Taxas de IVA (Código do IVA, art. 18.º) por região fiscal.
VAT_RATES = {
    "continente": {"normal": 23.0, "intermedia": 13.0, "reduzida": 6.0},
    "madeira": {"normal": 22.0, "intermedia": 12.0, "reduzida": 5.0},
    "acores": {"normal": 16.0, "intermedia": 9.0, "reduzida": 4.0},
}
ALLOWED_VAT = sorted({0.0, *(r for reg in VAT_RATES.values() for r in reg.values())})
DEFAULT_VAT = VAT_RATES["continente"]["normal"]
# Verba 2.27 da Lista I anexa ao CIVA: empreitadas de reabilitação de imóveis de habitação (taxa reduzida).
REHAB_VAT = VAT_RATES["continente"]["reduzida"]


def region_for(district: str | None) -> str:
    d = (district or "").lower()
    if "madeira" in d or "funchal" in d:
        return "madeira"
    if "açores" in d or "acores" in d or "ponta delgada" in d or "angra" in d or "horta" in d:
        return "acores"
    return "continente"


def vat_for(kind: str = "normal", district: str | None = None) -> float:
    """Taxa de IVA em % para o tipo pedido ('normal', 'intermedia', 'reduzida') e a região."""
    return VAT_RATES[region_for(district)].get(kind, DEFAULT_VAT)
